from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from .notes_repository import RouteNotesRepository, route_notes_repository
from .repository import RouteRepository, route_repository
from .schemas import (
    AdjustmentEvidence,
    CodPayment,
    CodPaymentCorrection,
    CodPaymentDetailNote,
    DailyLoadTotal,
    DailyLoadTotalsResponse,
    DeliveryAdjustment,
    DeliveryException,
    ExceptionEvidence,
    FreightLogisticsGovernance,
    ImageEvidence,
    PaymentEvidence,
    RouteEvidenceGap,
    RouteEvidenceResponse,
    RouteIdentityEvidence,
    RouteLoadEvidence,
    RouteLoadLine,
    RouteNoteCreate,
    RouteNoteHistoryResponse,
    RouteNoteRecord,
    RouteScheduleDay,
    RouteSearchResponse,
    RouteSearchResult,
    SignatureCaptureEvidence,
    SignatureCaptureSession,
    SignatureImage,
    SourceEvidence,
    WarehouseDirectionLabel,
    WarehouseLabelEvidence,
    WarehouseListResponse,
    WarehouseLoadLinesResponse,
    WarehouseRouteListResponse,
    WarehouseSummary,
)


_WEEKDAYS: tuple[tuple[str, str, str], ...] = (
    ("Sunday", "DLVSUN", "NUMSUN"),
    ("Monday", "DLVMON", "NUMMON"),
    ("Tuesday", "DLVTUE", "NUMTUE"),
    ("Wednesday", "DLVWED", "NUMWED"),
    ("Thursday", "DLVTHU", "NUMTHU"),
    ("Friday", "DLVFRI", "NUMFRI"),
    ("Saturday", "DLVSAT", "NUMSAT"),
)


class RouteNotFound(LookupError):
    """Raised when MaddenCo has no route matching the requested route code."""


def _now() -> datetime:
    return datetime.now(UTC)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.upper() == "NONE" else text


def _iso(value: Any) -> str | None:
    """Format a MaddenCo datetime(6) value, treating an absent/zero-date
    sentinel the same as a missing value rather than a real timestamp."""

    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned or cleaned.startswith("0000") or cleaned.startswith("0001"):
            return None
        return cleaned
    year = getattr(value, "year", None)
    if year is not None and year <= 1:
        return None
    try:
        return value.isoformat()
    except AttributeError:
        return str(value)


def _number(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return default


def _optional_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _elapsed_minutes(created_at: Any, delivered_at: Any) -> float | None:
    if created_at is None or delivered_at is None:
        return None
    if not hasattr(created_at, "timestamp") or not hasattr(
        delivered_at, "timestamp"
    ):
        return None
    try:
        delta_seconds = (delivered_at - created_at).total_seconds()
    except TypeError:
        return None
    if delta_seconds < 0:
        return None
    return round(delta_seconds / 60.0, 1)


def _map_load_line(row: dict[str, Any]) -> RouteLoadLine:
    created_at = row.get("CRTSTAMP")
    delivered_at = row.get("DLVSTAMP")
    delivered_at_iso = _iso(delivered_at)
    delivered = delivered_at_iso is not None
    elapsed = _elapsed_minutes(created_at, delivered_at) if delivered else None
    return RouteLoadLine(
        store_number=_optional_int(row.get("STORENUM")),
        route=_clean_text(row.get("ROUTE")),
        status_code=_clean_text(row.get("STATUS")),
        invoice_number=_optional_int(row.get("INVNUM")),
        customer_number=_optional_int(row.get("CUSTNUM")),
        line_number=_optional_int(row.get("LINENUM")),
        seq=_optional_int(row.get("SEQ")),
        product_number=_clean_text(row.get("PRODNUM")),
        description=_clean_text(row.get("DESC")),
        weight=_optional_number(row.get("WEIGHT")),
        quantity=_optional_number(row.get("QUANTITY")),
        created_at=_iso(created_at),
        delivered_at=delivered_at_iso,
        delivered=delivered,
        elapsed_minutes=elapsed,
    )


_GAPS = [
    RouteEvidenceGap(
        code="route_profitability_formula",
        label="Route profitability / cost-efficiency",
        explanation=(
            "No approved route profitability or cost-efficiency formula "
            "is configured. This module presents load, payment, and "
            "exception evidence only; it computes no cost-per-stop, "
            "margin, or efficiency score."
        ),
    ),
    RouteEvidenceGap(
        code="on_time_delivery_definition",
        label="On-time delivery percentage",
        explanation=(
            "No approved definition of 'on time' exists for route "
            "deliveries, so an on-time percentage is not computed from "
            "the raw INWHLOAD creation/delivery timestamps below."
        ),
    ),
    RouteEvidenceGap(
        code="cod_reconciliation_authority",
        label="COD payment reconciliation authority",
        explanation=(
            "This module has no authority to reconcile, approve, or "
            "write back a COD payment. WHSIGPAY/WHSIGPAYC/WHSIGPAYD are "
            "shown as MaddenCo's own read-only record."
        ),
    ),
    RouteEvidenceGap(
        code="proof_of_delivery_image_retrieval",
        label="Proof-of-delivery image retrieval",
        explanation=(
            "WHSIGIMG stores only a signer name and image file name; this "
            "module lists that metadata but does not retrieve, store, or "
            "render the underlying signature image."
        ),
    ),
    RouteEvidenceGap(
        code="route_code_global_uniqueness",
        label="Route code global uniqueness",
        explanation=(
            "KMROUTES.RTECODE is not guaranteed unique across warehouses "
            "in the current schema. This module resolves a route by the "
            "first KMROUTES row matching the requested route code."
        ),
    ),
]


class FreightLogisticsService:
    """Build source-grounded, evidence-only route intelligence responses."""

    def __init__(
        self,
        *,
        repository: RouteRepository = route_repository,
        notes_repository: RouteNotesRepository = route_notes_repository,
        clock: Callable[[], datetime] = _now,
        note_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._repository = repository
        self._notes_repository = notes_repository
        self._clock = clock
        self._note_id_factory = note_id_factory or (
            lambda: f"route-note-{uuid4().hex}"
        )

    def search_routes(
        self,
        *,
        search: str = "",
        active_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> RouteSearchResponse:
        rows = self._repository.search_routes(
            search=search,
            active_only=active_only,
            limit=limit,
            offset=offset,
        )
        retrieved_at = self._clock().astimezone(UTC).isoformat()
        results = [
            RouteSearchResult(
                route_key=_clean_text(row.get("RTEKEY")),
                route_code=_clean_text(row.get("RTECODE")),
                warehouse_number=_optional_int(row.get("RTEWHSE")),
                warehouse_location_name=_clean_text(row.get("LOCATION_NAME")),
                status_code=_clean_text(row.get("RTESTATUS")),
                active=_clean_text(row.get("RTESTATUS")) in ("", "A"),
            )
            for row in rows
        ]
        return RouteSearchResponse(
            source=SourceEvidence(retrieved_at=retrieved_at),
            count=len(results),
            routes=results,
        )

    def list_warehouses(self) -> WarehouseListResponse:
        rows = self._repository.list_warehouses()
        retrieved_at = self._clock().astimezone(UTC).isoformat()
        warehouses = [
            WarehouseSummary(
                warehouse_number=_optional_int(row.get("LOCATION_NUMBER")) or 0,
                warehouse_location_name=_clean_text(row.get("LOCATION_NAME")),
            )
            for row in rows
        ]
        return WarehouseListResponse(
            source=SourceEvidence(retrieved_at=retrieved_at),
            count=len(warehouses),
            warehouses=warehouses,
        )

    def list_routes_for_warehouse(
        self,
        warehouse_number: int,
        *,
        active_only: bool = True,
    ) -> WarehouseRouteListResponse:
        rows = self._repository.list_routes_for_warehouse(
            warehouse_number, active_only=active_only,
        )
        retrieved_at = self._clock().astimezone(UTC).isoformat()
        routes = [
            RouteSearchResult(
                route_key=_clean_text(row.get("RTEKEY")),
                route_code=_clean_text(row.get("RTECODE")),
                warehouse_number=_optional_int(row.get("RTEWHSE")),
                status_code=_clean_text(row.get("RTESTATUS")),
                active=_clean_text(row.get("RTESTATUS")) in ("", "A"),
            )
            for row in rows
        ]
        return WarehouseRouteListResponse(
            source=SourceEvidence(retrieved_at=retrieved_at),
            warehouse_number=warehouse_number,
            count=len(routes),
            routes=routes,
        )

    def get_load_lines_for_warehouse(
        self,
        warehouse_number: int,
        *,
        date_from,
        date_to,
    ) -> WarehouseLoadLinesResponse:
        rows = self._repository.get_load_lines_for_warehouse(
            warehouse_number, date_from=date_from, date_to=date_to,
        )
        retrieved_at = self._clock().astimezone(UTC).isoformat()
        lines = [_map_load_line(row) for row in rows]
        return WarehouseLoadLinesResponse(
            source=SourceEvidence(retrieved_at=retrieved_at),
            warehouse_number=warehouse_number,
            date_from=date_from.isoformat(),
            date_to=date_to.isoformat(),
            line_count=len(lines),
            lines=lines,
        )

    def get_daily_load_totals_for_warehouse(
        self,
        warehouse_number: int,
        *,
        date_from,
        date_to,
    ) -> DailyLoadTotalsResponse:
        rows = self._repository.get_daily_load_totals_for_warehouse(
            warehouse_number, date_from=date_from, date_to=date_to,
        )
        retrieved_at = self._clock().astimezone(UTC).isoformat()
        totals = [
            DailyLoadTotal(
                load_date=(
                    row["load_date"].isoformat()
                    if hasattr(row["load_date"], "isoformat")
                    else str(row["load_date"])
                ),
                route_count=int(row.get("route_count") or 0),
                total_weight=float(row.get("total_weight") or 0.0),
                total_quantity=float(row.get("total_quantity") or 0.0),
                line_count=int(row.get("line_count") or 0),
            )
            for row in rows
        ]
        return DailyLoadTotalsResponse(
            source=SourceEvidence(retrieved_at=retrieved_at),
            warehouse_number=warehouse_number,
            date_from=date_from.isoformat(),
            date_to=date_to.isoformat(),
            totals=totals,
        )

    def get_route_evidence(self, route_code: str) -> RouteEvidenceResponse:
        row = self._repository.get_route(route_code)
        if row is None:
            raise RouteNotFound(
                f"Route '{route_code}' was not found in MaddenCo."
            )

        retrieved_at = self._clock().astimezone(UTC).isoformat()
        source = SourceEvidence(retrieved_at=retrieved_at)

        resolved_code = _clean_text(row.get("RTECODE")) or route_code
        warehouse_number = _optional_int(row.get("RTEWHSE"))

        schedule = [
            RouteScheduleDay(
                day=day_label,  # type: ignore[arg-type]
                scheduled=_clean_text(row.get(delivery_flag)).upper() == "Y",
                scheduled_stop_count=int(row.get(count_field) or 0),
            )
            for day_label, delivery_flag, count_field in _WEEKDAYS
        ]

        identity = RouteIdentityEvidence(
            route_key=_clean_text(row.get("RTEKEY")),
            route_code=resolved_code,
            warehouse_number=warehouse_number,
            status_code=_clean_text(row.get("RTESTATUS")),
            active=_clean_text(row.get("RTESTATUS")) in ("", "A"),
            schedule=schedule,
            created_at=_iso(row.get("CRTDATE")),
            created_by=_clean_text(row.get("CRTUSER")),
            changed_at=_iso(row.get("CHGDATE")),
            changed_by=_clean_text(row.get("CHGUSER")),
        )

        warehouse_label = self._build_warehouse_label(
            warehouse_number, resolved_code, _clean_text(row.get("LOCATION_NAME"))
        )
        load = self._build_load_evidence(resolved_code)
        payments = self._build_payment_evidence(resolved_code)
        exceptions = self._build_exception_evidence(resolved_code)
        adjustments = self._build_adjustment_evidence(resolved_code)
        signature_sessions = self._build_signature_session_evidence(resolved_code)
        images = self._build_image_evidence(resolved_code)

        return RouteEvidenceResponse(
            generated_at=retrieved_at,
            source=source,
            identity=identity,
            warehouse_label=warehouse_label,
            load=load,
            payments=payments,
            exceptions=exceptions,
            adjustments=adjustments,
            signature_sessions=signature_sessions,
            images=images,
            gaps=list(_GAPS),
        )

    def _build_warehouse_label(
        self,
        warehouse_number: int | None,
        route_code: str,
        location_name: str,
    ) -> WarehouseLabelEvidence:
        directions: list[WarehouseDirectionLabel] = []
        if warehouse_number is not None:
            rows = self._repository.get_warehouse_directions(
                warehouse_number, route_code
            )
            directions = [
                WarehouseDirectionLabel(
                    direction_name=_clean_text(row.get("DIRECTION_NAME")),
                    minimum_weight=_optional_int(row.get("MINIMUM_WEIGHT")),
                    maximum_weight=_optional_int(row.get("MAXIMUM_WEIGHT")),
                    quantity_limit=_optional_int(row.get("QUANTITY_LIMIT")),
                    limit_by=_clean_text(row.get("LIMIT_BY")),
                    active=_clean_text(row.get("ACTIVE")).upper() == "Y",
                )
                for row in rows
            ]
        return WarehouseLabelEvidence(
            warehouse_number=warehouse_number,
            warehouse_location_name=location_name,
            directions=directions,
        )

    def _build_load_evidence(self, route_code: str) -> RouteLoadEvidence:
        rows = self._repository.get_load_lines(route_code)
        lines: list[RouteLoadLine] = []
        delivered_count = 0
        total_weight = 0.0
        total_quantity = 0.0
        elapsed_values: list[float] = []

        for row in rows:
            line = _map_load_line(row)
            if line.delivered:
                delivered_count += 1
                if line.elapsed_minutes is not None:
                    elapsed_values.append(line.elapsed_minutes)
            total_weight += _number(row.get("WEIGHT"))
            total_quantity += _number(row.get("QUANTITY"))
            lines.append(line)

        line_count = len(lines)
        return RouteLoadEvidence(
            line_count=line_count,
            delivered_count=delivered_count,
            undelivered_count=line_count - delivered_count,
            total_weight=round(total_weight, 2),
            total_quantity=round(total_quantity, 2),
            average_elapsed_minutes=(
                round(sum(elapsed_values) / len(elapsed_values), 1)
                if elapsed_values
                else None
            ),
            lines=lines,
        )

    def _build_payment_evidence(self, route_code: str) -> PaymentEvidence:
        payment_rows = self._repository.get_cod_payments(route_code)
        correction_rows = self._repository.get_payment_corrections(route_code)
        detail_rows = self._repository.get_payment_details(route_code)

        corrections_by_payment: dict[int, list[CodPaymentCorrection]] = {}
        for row in correction_rows:
            payment_id = _optional_int(row.get("PAYMENT_ID"))
            if payment_id is None:
                continue
            corrections_by_payment.setdefault(payment_id, []).append(
                CodPaymentCorrection(
                    field=_clean_text(row.get("FIELD")),
                    before_value=_clean_text(row.get("BEFORE_VALUE")),
                    after_value=_clean_text(row.get("AFTER_VALUE")),
                    reason=_clean_text(row.get("REASON")),
                    changed_by=_clean_text(row.get("CRTUSER")),
                    changed_at=_iso(row.get("CRTSTAMP")),
                )
            )

        details_by_payment: dict[int, list[CodPaymentDetailNote]] = {}
        for row in detail_rows:
            payment_id = _optional_int(row.get("PAYMENT_ID"))
            if payment_id is None:
                continue
            details_by_payment.setdefault(payment_id, []).append(
                CodPaymentDetailNote(
                    notes=_clean_text(row.get("NOTES")),
                    created_at=_iso(row.get("CRTSTAMP")),
                    created_by=_clean_text(row.get("CRTUSER")),
                )
            )

        payments: list[CodPayment] = []
        received_count = 0
        total_amount = 0.0
        for row in payment_rows:
            payment_id = _optional_int(row.get("ID"))
            received = _clean_text(row.get("RECEIVED")).upper() == "Y"
            if received:
                received_count += 1
            amount = _number(row.get("AMOUNT"))
            total_amount += amount
            payments.append(
                CodPayment(
                    payment_id=payment_id or 0,
                    customer_number=_optional_int(row.get("CUSTNUM")),
                    route=_clean_text(row.get("ROUTE")),
                    payment_type=_clean_text(row.get("TYPE")),
                    check_number=_clean_text(row.get("CHECKNUM")),
                    auth_number=_clean_text(row.get("AUTHNUM")),
                    amount=amount,
                    notes=_clean_text(row.get("NOTES")),
                    invoices=_clean_text(row.get("INVOICES")),
                    received=received,
                    received_at=_iso(row.get("RECSTAMP")),
                    created_at=_iso(row.get("CRTSTAMP")),
                    corrections=(
                        corrections_by_payment.get(payment_id, [])
                        if payment_id is not None
                        else []
                    ),
                    detail_notes=(
                        details_by_payment.get(payment_id, [])
                        if payment_id is not None
                        else []
                    ),
                )
            )

        payment_count = len(payments)
        return PaymentEvidence(
            payment_count=payment_count,
            total_amount=round(total_amount, 2),
            received_count=received_count,
            unreceived_count=payment_count - received_count,
            payments=payments,
        )

    def _build_exception_evidence(self, route_code: str) -> ExceptionEvidence:
        rows = self._repository.get_delivery_exceptions(route_code)
        exceptions: list[DeliveryException] = []
        approved_count = 0
        for row in rows:
            approved = _clean_text(row.get("APPROVED")).upper() == "Y"
            if approved:
                approved_count += 1
            exceptions.append(
                DeliveryException(
                    customer_number=_optional_int(row.get("CUSTNUM")),
                    route=_clean_text(row.get("ROUTE")),
                    invoice_number=_optional_int(row.get("INVNUM")),
                    line_number=_optional_int(row.get("LINENUM")),
                    quantity=_optional_number(row.get("QUANTITY")),
                    option_code=_clean_text(row.get("OPTION_CODE")),
                    notes=_clean_text(row.get("NOTES")),
                    approved=approved,
                    credit_invoice_number=_optional_int(row.get("CREDITINV")),
                    approval_notes=_clean_text(row.get("APPNOTES")),
                    approved_by=_clean_text(row.get("APPROVBY")),
                    created_at=_iso(row.get("CRTSTAMP")),
                    approved_at=_iso(row.get("APPRSTAMP")),
                )
            )
        exception_count = len(exceptions)
        return ExceptionEvidence(
            exception_count=exception_count,
            approved_count=approved_count,
            unapproved_count=exception_count - approved_count,
            exceptions=exceptions,
        )

    def _build_adjustment_evidence(self, route_code: str) -> AdjustmentEvidence:
        rows = self._repository.get_delivery_adjustments(route_code)
        adjustments = [
            DeliveryAdjustment(
                route=_clean_text(row.get("ROUTE")),
                invoice_number=_optional_int(row.get("INVNUM")),
                customer_number=_optional_int(row.get("CUSTNUM")),
                line_number=_optional_int(row.get("LINENUM")),
                seq=_optional_int(row.get("SEQ")),
                line_type=_clean_text(row.get("LINETYPE")),
                product_number=_clean_text(row.get("PRODNUM")),
                description=_clean_text(row.get("DESC")),
                quantity=_optional_number(row.get("QUANTITY")),
                created_at=_iso(row.get("CRTSTAMP")),
                uploaded_at=_iso(row.get("UPLDSTAMP")),
            )
            for row in rows
        ]
        return AdjustmentEvidence(
            adjustment_count=len(adjustments),
            adjustments=adjustments,
        )

    def _build_signature_session_evidence(
        self, route_code: str
    ) -> SignatureCaptureEvidence:
        rows = self._repository.get_signature_sessions(route_code)
        sessions = [
            SignatureCaptureSession(
                serial_number=_clean_text(row.get("SERIALNUM")),
                route=_clean_text(row.get("ROUTE")),
                session_type=_clean_text(row.get("RTETYPE")),
                created_at=_iso(row.get("CRTSTAMP")),
                created_by=_clean_text(row.get("CRTUSER")),
            )
            for row in rows
        ]
        return SignatureCaptureEvidence(
            session_count=len(sessions),
            sessions=sessions,
        )

    def _build_image_evidence(self, route_code: str) -> ImageEvidence:
        rows = self._repository.get_signature_images(route_code)
        images = [
            SignatureImage(
                customer_number=_optional_int(row.get("CUSTNUM")),
                invoice_number=_optional_int(row.get("INVNUM")),
                signer_name=_clean_text(row.get("SIGNAME")),
                file_name=_clean_text(row.get("FILENAME")),
                created_at=_iso(row.get("CRTSTAMP")),
                uploaded_at=_iso(row.get("UPLDSTAMP")),
            )
            for row in rows
        ]
        return ImageEvidence(
            image_count=len(images),
            images=images,
        )

    def list_notes(self, route_code: str) -> RouteNoteHistoryResponse:
        records = [
            RouteNoteRecord(**record)
            for record in self._notes_repository.list_notes(route_code)
        ]
        return RouteNoteHistoryResponse(
            route_code=route_code,
            count=len(records),
            notes=records,
        )

    def create_note(
        self,
        route_code: str,
        payload: RouteNoteCreate,
    ) -> RouteNoteRecord:
        evidence = self.get_route_evidence(route_code)
        created_at = self._clock().astimezone(UTC).isoformat()
        record = {
            "note_id": self._note_id_factory(),
            "route_code": evidence.identity.route_code,
            "warehouse_number": evidence.identity.warehouse_number,
            "author_identity": payload.author_identity,
            "note": payload.note,
            "created_at": created_at,
            "source_as_of": evidence.source.retrieved_at,
            "actor_identity_source": "operator_supplied",
            "actor_authority_status": "not_independently_verified",
            "note_classification": "professional_workflow_metadata",
            "decision_effect": "none",
            "evidence_snapshot": evidence.model_dump(mode="json"),
        }
        return RouteNoteRecord(
            **self._notes_repository.create_note(record)
        )


freight_logistics_service = FreightLogisticsService()
