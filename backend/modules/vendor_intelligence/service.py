from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from .notes_repository import VendorNotesRepository, vendor_notes_repository
from .po_fill_rate_cache_source import (
    PoFillRateCacheRefreshFailed,
    scan_all_vendor_po_fill_rates,
)
from .repository import VendorRepository, vendor_repository
from .schemas import (
    DiscountCaptureMetric,
    OpenPayableInvoice,
    OpenPurchaseOrder,
    PaidPayableInvoice,
    PayablesEvidence,
    PurchaseOrderEvidence,
    ReceivingEvent,
    ReceivingEvidence,
    SourceEvidence,
    VendorEvidenceGap,
    VendorEvidenceResponse,
    VendorIdentityEvidence,
    VendorNoteCreate,
    VendorNoteHistoryResponse,
    VendorNoteRecord,
    VendorPerformanceSummary,
    VendorPurchaseVolumeEvidence,
    VendorSearchResponse,
    VendorSearchResult,
)


class VendorNotFound(LookupError):
    """Raised when MaddenCo has no vendor matching the requested number."""


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


def _discount_capture_rate(taken: float, lost: float) -> DiscountCaptureMetric:
    denominator = round(taken + lost, 2)
    if denominator <= 0:
        return DiscountCaptureMetric(
            value=None,
            status="unavailable",
            explanation=(
                "No discount was either taken or lost for this period, so "
                "a capture rate is not computed."
            ),
        )
    rate = round((taken / denominator) * 100, 2)
    return DiscountCaptureMetric(
        value=rate,
        status="available",
        explanation=(
            f"{taken:.2f} taken of {denominator:.2f} available "
            f"({lost:.2f} lost) for this period."
        ),
    )


def _address_lines(row: dict[str, Any]) -> list[str]:
    lines = [
        _clean_text(row.get(key))
        for key in ("PVADDR1", "PVADDR2", "PVADDR3", "PVADDR4")
    ]
    return [line for line in lines if line]


_GAPS = [
    VendorEvidenceGap(
        code="vendor_scorecard",
        label="Vendor scorecard / weighted rating",
        explanation=(
            "No approved vendor scorecard weighting or scoring model is "
            "configured. This module presents evidence only; it computes "
            "no vendor rating, rank, or automatic recommendation."
        ),
    ),
    VendorEvidenceGap(
        code="on_time_delivery_definition",
        label="On-time delivery / receiving performance",
        explanation=(
            "Confirmed live: TMPOHD's requested/required delivery date "
            "field (TPHDTEREQ) is populated on 0.003% of rows, and no "
            "promised-delivery-date field exists to compare a receipt "
            "date against. This is a real data absence in this MaddenCo "
            "instance, not a pending configuration - no on-time "
            "percentage is computed."
        ),
    ),
    VendorEvidenceGap(
        code="quality_and_chargeback_data",
        label="Quality, return, and chargeback history",
        explanation=(
            "Confirmed live against this instance's full 47-table MaddenCo "
            "schema: no returns, chargeback, or quality-hold table exists "
            "at all. This is a permanent data absence, not a missing "
            "connection - no quality or chargeback signal is computed."
        ),
    ),
    VendorEvidenceGap(
        code="terms_description_text",
        label="Payment terms description text",
        explanation=(
            "PMVEND stores only a terms code (PVCODTREM); no governed "
            "terms-code-to-description lookup table is connected."
        ),
    ),
    VendorEvidenceGap(
        code="city_state_fields",
        label="Discrete city / state fields",
        explanation=(
            "PMVEND has no discrete city or state columns in the current "
            "schema; only free-text address lines are available."
        ),
    ),
    VendorEvidenceGap(
        code="rebate_accrual",
        label="Vendor rebate accrual",
        explanation=(
            "No vendor rebate accrual table is available in the current "
            "MaddenCo schema; rebate tracking is out of scope for this "
            "module."
        ),
    ),
]


class VendorIntelligenceService:
    """Build source-grounded, evidence-only vendor intelligence responses."""

    def __init__(
        self,
        *,
        repository: VendorRepository = vendor_repository,
        notes_repository: VendorNotesRepository = vendor_notes_repository,
        clock: Callable[[], datetime] = _now,
        note_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._repository = repository
        self._notes_repository = notes_repository
        self._clock = clock
        self._note_id_factory = note_id_factory or (
            lambda: f"vendor-note-{uuid4().hex}"
        )

    def search_vendors(
        self,
        *,
        search: str = "",
        active_only: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> VendorSearchResponse:
        rows = self._repository.search_vendors(
            search=search,
            active_only=active_only,
            limit=limit,
            offset=offset,
        )
        retrieved_at = self._clock().astimezone(UTC).isoformat()
        results = [
            VendorSearchResult(
                vendor_number=int(row["PVNUMVEN"]),
                vendor_name=_clean_text(row.get("PVNAMVEN")),
                contact_name=_clean_text(row.get("PVNAMCNT")),
                phone=_clean_text(row.get("PVPHONE")),
                email=_clean_text(row.get("PVEMAIL")),
                zip_code=_clean_text(row.get("PVZIP")),
                active=_clean_text(row.get("PVCODDEL")) in ("", "A"),
                po_required=_clean_text(row.get("PVPOREQ")).upper() == "Y",
            )
            for row in rows
        ]
        return VendorSearchResponse(
            source=SourceEvidence(retrieved_at=retrieved_at),
            count=len(results),
            vendors=results,
        )

    def get_vendor_evidence(self, vendor_number: int) -> VendorEvidenceResponse:
        row = self._repository.get_vendor(vendor_number)
        if row is None:
            raise VendorNotFound(
                f"Vendor {vendor_number} was not found in MaddenCo."
            )

        retrieved_at = self._clock().astimezone(UTC).isoformat()
        source = SourceEvidence(retrieved_at=retrieved_at)

        identity = VendorIdentityEvidence(
            vendor_number=int(row["PVNUMVEN"]),
            vendor_name=_clean_text(row.get("PVNAMVEN")),
            sort_name=_clean_text(row.get("PVNAMSRT")),
            contact_name=_clean_text(row.get("PVNAMCNT")),
            address_lines=_address_lines(row),
            zip_code=_clean_text(row.get("PVZIP")),
            country=_clean_text(row.get("PVCOUNTRY")),
            phone=_clean_text(row.get("PVPHONE")),
            fax=_clean_text(row.get("PVNBFAX")),
            email=_clean_text(row.get("PVEMAIL")),
            active=_clean_text(row.get("PVCODDEL")) in ("", "A"),
            vendor_type=_clean_text(row.get("PVTYPVEN")),
            store_number=_optional_int(row.get("PVSTOREN")),
            terms_code=_clean_text(row.get("PVCODTREM")),
            po_required=_clean_text(row.get("PVPOREQ")).upper() == "Y",
            do_not_create_ap_from_receiving=(
                _clean_text(row.get("PVFLGNORCV")).upper() == "Y"
            ),
            is_1099=_clean_text(row.get("PV1099OP")).upper() == "Y",
            tax_1099_code=_clean_text(row.get("PVCOD1099")),
            tax_1099_manual_amount=_optional_number(row.get("PVAMT1099")),
            federal_id_on_file=bool(_clean_text(row.get("PVIDFED"))),
            payment_type=_clean_text(row.get("PVTYPPMT")),
            bank_account_type=_clean_text(row.get("PVTYPBNK")),
            eft_bank_info_on_file=bool(
                _clean_text(row.get("PVACCBNK"))
            ) or bool(_optional_int(row.get("PVROUBNK"))),
        )

        discount_mtd = _number(row.get("PVDISCMTD"))
        discount_ytd = _number(row.get("PVDISCYTD"))
        discount_lost_mtd = _number(row.get("PVDISCLMTD"))
        discount_lost_ytd = _number(row.get("PVDISCLYTD"))
        purchase_volume = VendorPurchaseVolumeEvidence(
            month_to_date=_number(row.get("PVPURMTD")),
            year_to_date=_number(row.get("PVPURYTD")),
            last_year=_number(row.get("PVPURLSTYR")),
            discount_month_to_date=discount_mtd,
            discount_year_to_date=discount_ytd,
            discount_lost_month_to_date=discount_lost_mtd,
            discount_lost_year_to_date=discount_lost_ytd,
            discount_capture_rate_month_to_date=_discount_capture_rate(
                discount_mtd, discount_lost_mtd
            ),
            discount_capture_rate_year_to_date=_discount_capture_rate(
                discount_ytd, discount_lost_ytd
            ),
            amount_last_paid=_optional_number(row.get("PVAMTLPD")),
            date_last_paid=_parse_erp_date(row.get("PVDTELPD")),
            check_number_last_paid=_optional_int(row.get("PVCHKLPD")),
        )

        purchase_orders = self._build_purchase_order_evidence(vendor_number)
        receiving = self._build_receiving_evidence(vendor_number)
        performance = self._build_performance_summary(vendor_number)
        payables = self._build_payables_evidence(vendor_number)

        return VendorEvidenceResponse(
            generated_at=retrieved_at,
            source=source,
            identity=identity,
            purchase_volume=purchase_volume,
            purchase_orders=purchase_orders,
            receiving=receiving,
            performance=performance,
            payables=payables,
            gaps=list(_GAPS),
        )

    def refresh_po_fill_rate_cache(
        self, *, window_days: int = 365
    ) -> dict[str, Any]:
        """Full TMPOHD/TMPODT scan (minutes, not part of interactive page
        loads) - call this once, then periodically, to keep every vendor's
        fill-rate summary current for _build_performance_summary()."""

        try:
            rows = scan_all_vendor_po_fill_rates(window_days=window_days)
        except PoFillRateCacheRefreshFailed as exc:
            return {"status": "unavailable_source_capability", "message": str(exc)}
        refreshed_at = self._clock().astimezone(UTC).isoformat()
        self._notes_repository.replace_po_fill_rate_cache(
            rows, window_days=window_days, refreshed_at=refreshed_at
        )
        return {
            "status": "ok",
            "vendors_cached": len(rows),
            "window_days": window_days,
            "refreshed_at": refreshed_at,
        }

    def _build_performance_summary(
        self,
        vendor_number: int,
        *,
        window_days: int = 365,
    ) -> VendorPerformanceSummary:
        # get_po_fill_rate_summary()'s live TMPOHD/TMPODT join is fine for
        # most vendors but can take anywhere from ~1s to ~40s for the
        # highest-volume vendors (TMPOHD has no index on TPHDTECRT, and
        # TMPODT is 6.2M+ rows), occasionally exceeding the shared 60s
        # MySQL statement timeout. This now reads refresh_po_fill_rate_cache()'s
        # pre-aggregated local cache instead of running that join live on
        # the interactive vendor-evidence request path - the same pattern
        # cash_flow_forecasting already uses for its AP due-date cache. A
        # vendor with no cached row (cache never refreshed, or genuinely no
        # PO activity in the window) reports "unavailable", matching this
        # summary's existing no-data behavior rather than falling back to
        # the slow live query.
        row = self._notes_repository.get_po_fill_rate_cache(vendor_number)
        if row is not None and row["window_days"] != window_days:
            row = None
        quantity_ordered = _number((row or {}).get("quantity_ordered"))
        quantity_received = _number((row or {}).get("quantity_received"))
        quantity_backorder = _number((row or {}).get("quantity_backorder"))
        po_count = int((row or {}).get("po_count") or 0)
        fill_rate_percent = (
            round(quantity_received / quantity_ordered * 100, 1)
            if quantity_ordered > 0
            else None
        )
        return VendorPerformanceSummary(
            window_days=window_days,
            po_count=po_count,
            quantity_ordered=quantity_ordered,
            quantity_received=quantity_received,
            quantity_backorder=quantity_backorder,
            fill_rate_percent=fill_rate_percent,
            fill_rate_status="available" if fill_rate_percent is not None else "unavailable",
        )

    def _build_purchase_order_evidence(
        self,
        vendor_number: int,
    ) -> PurchaseOrderEvidence:
        rows = self._repository.get_open_purchase_orders(vendor_number)
        orders = [
            OpenPurchaseOrder(
                po_number=int(row["TPHNB"]),
                po_date=_parse_erp_date(row.get("TPHDTE")),
                date_required=_parse_erp_date(row.get("TPHDTEREQ")),
                status_code=_clean_text(row.get("TPHCDSTS")),
                complete=_clean_text(row.get("TPHFLGCMP")).upper() == "Y",
                total_cost=_number(row.get("TPHTOTCST")),
                ship_via=_clean_text(row.get("TPHVIA")),
                buyer_number=_optional_int(row.get("TPHBUYNUM")),
                ordered_quantity=_number(row.get("TOTAL_ORDERED")),
                received_quantity=_number(row.get("TOTAL_RECEIVED")),
                backorder_quantity=_number(row.get("TOTAL_BACKORDER")),
                line_count=int(row.get("LINE_COUNT") or 0),
            )
            for row in rows
        ]
        return PurchaseOrderEvidence(
            open_order_count=len(orders),
            open_order_total_cost=round(
                sum(order.total_cost for order in orders), 2
            ),
            open_orders=orders,
        )

    def _build_receiving_evidence(
        self,
        vendor_number: int,
    ) -> ReceivingEvidence:
        # TRCDCOSDIF (the dedicated cost-variance column) is confirmed
        # live to be exactly 0 across all 450,925 TTRCVD rows this
        # instance has ever recorded - it has never been populated with a
        # real observation, and TRCDCOS is confirmed to always just copy
        # TRCDCOSPO whenever the latter is set. Treating those zeros as
        # "complete, no variance" would misreport a data void as a clean
        # match; there is no usable price/cost variance signal in this
        # ERP instance's receiving data at all, so this is always
        # disclosed as unavailable rather than summed to a false $0.00.
        rows = self._repository.get_receiving_history(vendor_number)
        events = [
            ReceivingEvent(
                po_number=int(row["TRCDNUMPO"]),
                product_number=_clean_text(row.get("TRCDNUMPRD")),
                product_description=_clean_text(row.get("TRCDPRDDSC")),
                quantity=_number(row.get("TRCDQTY")),
                actual_cost=_optional_number(row.get("TRCDCOS")),
                po_cost=_optional_number(row.get("TRCDCOSPO")),
                cost_variance=_optional_number(row.get("TRCDCOSDIF")),
                dot_number=_clean_text(row.get("TRCDDOT")),
                dot_date=_parse_erp_date(row.get("TRCDDOTDTE")),
                received_date=_parse_erp_date(row.get("TRCDDTECRT")),
            )
            for row in rows
        ]

        return ReceivingEvidence(
            receipt_count=len(events),
            total_cost_variance=None,
            cost_variance_completeness="unavailable",
            recent_receipts=events,
        )

    def _build_payables_evidence(
        self,
        vendor_number: int,
    ) -> PayablesEvidence:
        open_rows = self._repository.get_open_payable_invoices(vendor_number)
        paid_rows = self._repository.get_paid_payable_invoices(vendor_number)

        open_invoices = [
            OpenPayableInvoice(
                invoice_number=_clean_text(row.get("PMHNBINV")),
                invoice_amount=_number(row.get("PMHAMTINV")),
                discount_amount=_number(row.get("PMHAMTDIS")),
                invoice_date=_parse_erp_date(row.get("PMHDTEINV")),
                due_date=_parse_erp_date(row.get("PMHDTEDUE")),
                on_hold=_clean_text(row.get("PMHFLGHLD")).upper() == "Y",
                period=_optional_int(row.get("PMHPR")),
                year=_optional_int(row.get("PMHYR")),
            )
            for row in open_rows
        ]
        paid_invoices = [
            PaidPayableInvoice(
                invoice_number=_clean_text(row.get("PTHNBINV")),
                invoice_amount=_number(row.get("PTHAMTINV")),
                invoice_date=_parse_erp_date(row.get("PTHDTEINV")),
                due_date=_parse_erp_date(row.get("PTHDTEDUE")),
                status=_clean_text(row.get("PTHSTAT")),
                amount_paid=_optional_number(row.get("PTYAMT")),
                discount_taken=_optional_number(row.get("PTYAMTDIS")),
            )
            for row in paid_rows
        ]

        return PayablesEvidence(
            open_invoice_count=len(open_invoices),
            open_invoice_total=round(
                sum(invoice.invoice_amount for invoice in open_invoices), 2
            ),
            open_invoices=open_invoices,
            recent_paid_invoices=paid_invoices,
        )

    def list_notes(self, vendor_number: int) -> VendorNoteHistoryResponse:
        records = [
            VendorNoteRecord(**record)
            for record in self._notes_repository.list_notes(vendor_number)
        ]
        return VendorNoteHistoryResponse(
            vendor_number=vendor_number,
            count=len(records),
            notes=records,
        )

    def create_note(
        self,
        vendor_number: int,
        payload: VendorNoteCreate,
    ) -> VendorNoteRecord:
        evidence = self.get_vendor_evidence(vendor_number)
        created_at = self._clock().astimezone(UTC).isoformat()
        record = {
            "note_id": self._note_id_factory(),
            "vendor_number": vendor_number,
            "vendor_name": evidence.identity.vendor_name,
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
        return VendorNoteRecord(
            **self._notes_repository.create_note(record)
        )


vendor_intelligence_service = VendorIntelligenceService()
