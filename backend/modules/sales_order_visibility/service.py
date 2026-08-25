from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

from .notes_repository import OrderNotesRepository, order_notes_repository
from .repository import SalesOrderRepository, sales_order_repository
from .schemas import (
    DeliveryEvidence,
    DeliveryManifestLine,
    InvoiceAuthorization,
    InvoiceAuthorizationEvidence,
    InvoiceEvidenceResponse,
    InvoiceHeaderEvidence,
    InvoiceLineEvidence,
    InvoiceLineItem,
    InvoiceMemo,
    InvoiceMemoEvidence,
    InvoiceSearchResponse,
    InvoiceSearchResult,
    OrderNoteCreate,
    OrderNoteHistoryResponse,
    OrderNoteRecord,
    SalesOrderEvidenceGap,
    SalesSummaryResponse,
    SalesSummaryRow,
    SourceEvidence,
)


class InvoiceNotFound(LookupError):
    """Raised when MaddenCo has no invoice matching the requested number."""


def _now() -> datetime:
    return datetime.now(UTC)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.upper() == "NONE" else text


def _parse_erp_date(value: Any) -> str | None:
    raw = _clean_text(value)
    if not raw or raw == "0" * len(raw):
        return None
    for pattern in ("%Y%m%d", "%m%d%Y"):
        try:
            return datetime.strptime(raw, pattern).date().isoformat()
        except ValueError:
            continue
    return raw


def _datetime_to_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return _parse_erp_date(value)


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
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed != 0 else None


def _ship_to_lines(row: dict[str, Any]) -> list[str]:
    lines = [
        _clean_text(row.get(key))
        for key in ("TIHHSHPTO1", "TIHHSHPTO2", "TIHHSHPTO3", "TIHHSHPTO5")
    ]
    return [line for line in lines if line]


_GAPS = [
    SalesOrderEvidenceGap(
        code="open_order_queue",
        label="Open / pre-invoice order queue",
        explanation=(
            "The current MaddenCo schema (DTA273) has no open-order-entry "
            "header table (no OEHDR-style table). This module reads only "
            "invoice-history tables (TMIHSH/TMIHSI/TMIHSL/TMIHSM/TMIHSA), "
            "so it shows invoice-forward history — completed or in-process "
            "invoices — never a live pending/pre-invoice order pipeline."
        ),
    ),
    SalesOrderEvidenceGap(
        code="fulfillment_sla_definition",
        label="Fulfillment SLA / on-time-ship definition",
        explanation=(
            "No approved on-time-ship or fulfillment SLA definition is "
            "configured. The delivery evidence below is INWHLOAD's own "
            "delivered/not-delivered flag (DLVSTAMP null-check), not a "
            "computed SLA judgment."
        ),
    ),
    SalesOrderEvidenceGap(
        code="extended_price_not_stored",
        label="Line extended price is derived, not stored",
        explanation=(
            "TMIHSL does not store its own extended line amount. Each "
            "line's extended price shown here is the arithmetic product of "
            "TIHLQTY (quantity) and TIHLPRC (unit price)."
        ),
    ),
    SalesOrderEvidenceGap(
        code="delivery_manifest_optional",
        label="Delivery manifest coverage is not guaranteed",
        explanation=(
            "INWHLOAD only carries rows for invoices routed through a "
            "warehouse delivery load (for example a route truck). Will-"
            "call, counter pickup, or otherwise unrouted invoices may have "
            "no INWHLOAD rows at all; that is reported as "
            "'no_records_found', not as evidence of a missed delivery."
        ),
    ),
]


class SalesOrderVisibilityService:
    """Build source-grounded, evidence-only sales order visibility responses.

    Scope boundary: MaddenCo (DTA273) has no open/pre-invoice order-entry
    table. This service is invoice-forward only — it never presents a live
    pending-order pipeline.
    """

    def __init__(
        self,
        *,
        repository: SalesOrderRepository = sales_order_repository,
        notes_repository: OrderNotesRepository = order_notes_repository,
        clock: Callable[[], datetime] = _now,
        note_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._repository = repository
        self._notes_repository = notes_repository
        self._clock = clock
        self._note_id_factory = note_id_factory or (
            lambda: f"order-note-{uuid4().hex}"
        )

    def search_invoices(
        self,
        *,
        search: str = "",
        customer_number: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> InvoiceSearchResponse:
        rows = self._repository.search_invoices(
            search=search,
            customer_number=customer_number,
            limit=limit,
            offset=offset,
        )
        retrieved_at = self._clock().astimezone(UTC).isoformat()
        results = [
            InvoiceSearchResult(
                invoice_number=int(row["TIHHNUMINV"]),
                customer_number=int(row["TIHHNUMCST"]),
                customer_name=_clean_text(row.get("CUNAME")),
                invoice_date=_parse_erp_date(row.get("TIHHDTEINV")),
                type_code=_clean_text(row.get("TIHHCODTYP")),
                total_amount=_number(row.get("TIHHTOTINV")),
                void=_clean_text(row.get("TIHHVOIDYN")).upper() == "Y",
                route_code=_clean_text(row.get("TIHHCDRTE")),
                store_number=_optional_int(row.get("TIHHNUMSTR")),
                po_number=_clean_text(row.get("TIHHNUMPO")),
            )
            for row in rows
        ]
        return InvoiceSearchResponse(
            source=SourceEvidence(retrieved_at=retrieved_at),
            count=len(results),
            invoices=results,
        )

    def get_invoice_evidence(self, invoice_number: int) -> InvoiceEvidenceResponse:
        row = self._repository.get_invoice_header(invoice_number)
        if row is None:
            raise InvoiceNotFound(
                f"Invoice {invoice_number} was not found in MaddenCo."
            )

        retrieved_at = self._clock().astimezone(UTC).isoformat()
        source = SourceEvidence(retrieved_at=retrieved_at)

        header = InvoiceHeaderEvidence(
            invoice_number=int(row["TIHHNUMINV"]),
            customer_number=int(row["TIHHNUMCST"]),
            customer_name=_clean_text(row.get("CUNAME")),
            invoice_date=_parse_erp_date(row.get("TIHHDTEINV")),
            due_date=_parse_erp_date(row.get("TIHHDTEDUE")),
            created_date=_parse_erp_date(row.get("TIHHDTECRT")),
            changed_date=_parse_erp_date(row.get("TIHHDTECHG")),
            type_code=_clean_text(row.get("TIHHCODTYP")),
            void=_clean_text(row.get("TIHHVOIDYN")).upper() == "Y",
            hold_reason=_clean_text(row.get("TIHHHLDRSN")),
            direct_ship=_clean_text(row.get("TIHHDIRSHP")).upper() == "Y",
            pickup=_clean_text(row.get("TIHHPICKUP")).upper() == "Y",
            route_code=_clean_text(row.get("TIHHCDRTE")),
            store_number=_optional_int(row.get("TIHHNUMSTR")),
            po_number=_clean_text(row.get("TIHHNUMPO")),
            reference_number=_clean_text(row.get("TIHHNUMREF")),
            terms_code=_clean_text(row.get("TIHHCODTRM")),
            tax_exempt_code=_clean_text(row.get("TIHHCODEXM")),
            customer_class=_clean_text(row.get("TIHHCLSCST")),
            customer_type=_clean_text(row.get("TIHHCSTTYP")),
            type_of_sale=_clean_text(row.get("TIHHTOS")),
            ship_to_lines=_ship_to_lines(row),
            ship_to_zip=_clean_text(row.get("TIHHSHPTOZ")),
            tracking_number=_clean_text(row.get("TIHHTRKNUM")),
            total_amount=_number(row.get("TIHHTOTINV")),
            total_units=_number(row.get("TIHHTOTUNT")),
            total_discount=_number(row.get("TIHHDISCST")),
            line_count=_optional_int(row.get("TIHHNUMLIN")),
            invoice_count=_optional_int(row.get("TIHHINVCNT")),
            selling_salesman=_optional_int(row.get("TIHHSLMSEL")),
            customer_salesman=_optional_int(row.get("TIHHSLMCST")),
            originating_salesman=_optional_int(row.get("TIHHSLMORG")),
            class_salesman=_optional_int(row.get("TIHHSLMCLS")),
            status=_clean_text(row.get("TIHHSTATUS")),
            status_secondary=_clean_text(row.get("TIHHSTAT2")),
        )

        lines = self._build_line_evidence(invoice_number)
        memos = self._build_memo_evidence(invoice_number)
        authorizations = self._build_authorization_evidence(invoice_number)
        delivery = self._build_delivery_evidence(invoice_number)

        return InvoiceEvidenceResponse(
            generated_at=retrieved_at,
            source=source,
            header=header,
            lines=lines,
            memos=memos,
            authorizations=authorizations,
            delivery=delivery,
            gaps=list(_GAPS),
        )

    def _build_line_evidence(self, invoice_number: int) -> InvoiceLineEvidence:
        line_rows = self._repository.get_invoice_lines(invoice_number)
        fit_rows = self._repository.get_invoice_line_fit_details(invoice_number)
        fit_by_line = {
            _optional_int(fit.get("TIHILINENO")): fit for fit in fit_rows
        }

        lines: list[InvoiceLineItem] = []
        for row in line_rows:
            line_number = int(row["TIHLLINENO"])
            quantity = _number(row.get("TIHLQTY"))
            unit_price = _number(row.get("TIHLPRC"))
            fit = fit_by_line.get(line_number)

            lines.append(
                InvoiceLineItem(
                    line_number=line_number,
                    type_code=_clean_text(row.get("TIHLCODTYP")),
                    delete_code=_clean_text(row.get("TIHLCODDEL")),
                    product_number=_clean_text(row.get("TIHLPRD")),
                    product_description=_clean_text(row.get("TIHLPRDDSC")),
                    product_vendor=_clean_text(row.get("TIHLVNDPRD")),
                    brand=_clean_text(row.get("TIHLBRAND")),
                    product_class=_clean_text(row.get("TIHLCLSPRD")),
                    quantity=quantity,
                    quantity_ordered=_number(row.get("TIHLQTYORD")),
                    quantity_backorder=_number(row.get("TIHLQTYBO")),
                    unit_price=unit_price,
                    extended_price=round(quantity * unit_price, 2),
                    actual_cost=_optional_number(row.get("TIHLCOSACT")),
                    replacement_cost=_optional_number(row.get("TIHLCOSREP")),
                    fet=_optional_number(row.get("TIHLFET")),
                    dot_number=_clean_text(row.get("TIHLDOT")),
                    dot_date=_parse_erp_date(row.get("TIHLDOTDTE")),
                    tire_position=_clean_text(row.get("TIHLTIRPOS")),
                    vehicle_make=_clean_text(
                        fit.get("TIHICARMAK") if fit else None
                    ),
                    vehicle_model=_clean_text(
                        fit.get("TIHICARMOD") if fit else None
                    ),
                    vehicle_year=_optional_int(
                        fit.get("TIHICARYR") if fit else None
                    ),
                    mileage=_optional_number(
                        fit.get("TIHIMILAGE") if fit else None
                    ),
                )
            )

        return InvoiceLineEvidence(
            line_count=len(lines),
            total_extended_price=round(
                sum(line.extended_price for line in lines), 2
            ),
            total_quantity=round(sum(line.quantity for line in lines), 2),
            lines=lines,
        )

    def _build_memo_evidence(self, invoice_number: int) -> InvoiceMemoEvidence:
        rows = self._repository.get_invoice_memos(invoice_number)
        memos = [
            InvoiceMemo(
                line_number=_optional_int(row.get("TIHMLINENO")),
                type_code=_clean_text(row.get("TIHMCODTYP")),
                message=_clean_text(row.get("TIHMMSG")),
                created_date=_parse_erp_date(row.get("TIHMDTECRT")),
                created_by=_clean_text(row.get("TIHMUSRCRT")),
                print_on_invoice=(
                    _clean_text(row.get("TIHMPRTINV")).upper() == "Y"
                ),
            )
            for row in rows
        ]
        return InvoiceMemoEvidence(memo_count=len(memos), memos=memos)

    def _build_authorization_evidence(
        self,
        invoice_number: int,
    ) -> InvoiceAuthorizationEvidence:
        rows = self._repository.get_invoice_authorizations(invoice_number)
        authorizations = [
            InvoiceAuthorization(
                authorization_type=_clean_text(row.get("TIHACD")),
                type_code=_clean_text(row.get("TIHACODTYP")),
                amount_authorized=_optional_number(row.get("TIHAAMTAU")),
                date_requested=_parse_erp_date(row.get("TIHADATRQ")),
                date_authorized=_parse_erp_date(row.get("TIHADATAU")),
                time_requested=_clean_text(row.get("TIHATIMRQ")),
                time_authorized=_clean_text(row.get("TIHATIMAU")),
                salesman_requested=_optional_int(row.get("TIHASLMRQ")),
                salesman_authorized=_optional_int(row.get("TIHASLMAU")),
                requested_by=_clean_text(row.get("TIHAUSRRQ")),
                authorized_by=_clean_text(row.get("TIHAUSRAU")),
                text=_clean_text(row.get("TIHATXT")),
            )
            for row in rows
        ]
        return InvoiceAuthorizationEvidence(
            authorization_count=len(authorizations),
            authorizations=authorizations,
        )

    def _build_delivery_evidence(self, invoice_number: int) -> DeliveryEvidence:
        rows = self._repository.get_delivery_status(invoice_number)
        if not rows:
            return DeliveryEvidence(
                manifest_status="no_records_found",
                total_line_count=0,
                delivered_line_count=0,
                undelivered_line_count=0,
                is_fully_delivered=None,
                lines=[],
            )

        lines: list[DeliveryManifestLine] = []
        delivered_count = 0
        for row in rows:
            delivered_at = _datetime_to_iso(row.get("DLVSTAMP"))
            delivered = delivered_at is not None
            if delivered:
                delivered_count += 1
            lines.append(
                DeliveryManifestLine(
                    store_number=_optional_int(row.get("STORENUM")),
                    route=_clean_text(row.get("ROUTE")),
                    status=_clean_text(row.get("STATUS")),
                    line_number=_optional_int(row.get("LINENUM")),
                    sequence=_optional_int(row.get("SEQ")),
                    product_number=_clean_text(row.get("PRODNUM")),
                    description=_clean_text(row.get("DESC_")),
                    weight=_optional_number(row.get("WEIGHT")),
                    quantity=_optional_number(row.get("QUANTITY")),
                    created_at=_datetime_to_iso(row.get("CRTSTAMP")),
                    delivered_at=delivered_at,
                    delivered=delivered,
                )
            )

        return DeliveryEvidence(
            manifest_status="records_found",
            total_line_count=len(lines),
            delivered_line_count=delivered_count,
            undelivered_line_count=len(lines) - delivered_count,
            is_fully_delivered=delivered_count == len(lines),
            lines=lines,
        )

    def get_sales_summary(
        self,
        *,
        customer_number: int | None = None,
        product_number: str | None = None,
        limit: int = 200,
    ) -> SalesSummaryResponse:
        rows = self._repository.get_sales_summary(
            customer_number=customer_number,
            product_number=product_number,
            limit=limit,
        )
        retrieved_at = self._clock().astimezone(UTC).isoformat()

        summary_rows = [
            SalesSummaryRow(
                customer_number=_optional_int(row.get("customer_number")),
                product_number=_clean_text(row.get("product_number")),
                product_class=_clean_text(row.get("product_class")),
                product_type=_clean_text(row.get("product_type")),
                customer_class=_clean_text(row.get("customer_class")),
                customer_type=_clean_text(row.get("customer_type")),
                commission_code=_clean_text(row.get("commission_code")),
                vendor_number=_clean_text(row.get("vendor_number")),
                store_number=_optional_int(row.get("store_number")),
                year_period=_optional_int(row.get("year_period")),
                sales=_number(row.get("sales")),
                units=_number(row.get("units")),
                actual_cost=_optional_number(row.get("actual_cost")),
                replacement_cost=_optional_number(row.get("replacement_cost")),
                fet=_optional_number(row.get("fet")),
            )
            for row in rows
        ]

        return SalesSummaryResponse(
            generated_at=retrieved_at,
            source=SourceEvidence(retrieved_at=retrieved_at),
            row_count=len(summary_rows),
            total_sales=round(sum(row.sales for row in summary_rows), 2),
            total_units=round(sum(row.units for row in summary_rows), 2),
            total_actual_cost=round(
                sum(row.actual_cost or 0.0 for row in summary_rows), 2
            ),
            rows=summary_rows,
        )

    def list_notes(self, invoice_number: int) -> OrderNoteHistoryResponse:
        records = [
            OrderNoteRecord(**record)
            for record in self._notes_repository.list_notes(invoice_number)
        ]
        return OrderNoteHistoryResponse(
            invoice_number=invoice_number,
            count=len(records),
            notes=records,
        )

    def create_note(
        self,
        invoice_number: int,
        payload: OrderNoteCreate,
    ) -> OrderNoteRecord:
        evidence = self.get_invoice_evidence(invoice_number)
        created_at = self._clock().astimezone(UTC).isoformat()
        record = {
            "note_id": self._note_id_factory(),
            "invoice_number": invoice_number,
            "customer_number": evidence.header.customer_number,
            "customer_name": evidence.header.customer_name,
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
        return OrderNoteRecord(
            **self._notes_repository.create_note(record)
        )


sales_order_visibility_service = SalesOrderVisibilityService()
