from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4

import core.jobs as job_queue

from .extraction import (
    PROVISIONAL_OCR_REVIEW_THRESHOLD,
    PROVISIONAL_OCR_THRESHOLD_SOURCE,
)
from .erp_ledger_repository import (
    AccountsPayableErpLedgerRepository,
    accounts_payable_erp_ledger_repository,
    parse_madden_date,
)
from .erp_ledger_scan import (
    scan_gl_divisions_for_open_invoices,
    scan_open_ap_ledger,
    scan_vendor_terms_codes,
)
from .repository import (
    AccountsPayableRepository,
    accounts_payable_repository,
)
from .schemas import (
    APDuplicateEvidence,
    APExceptionEvidence,
    APExceptionActionCreate,
    APExceptionActionHistoryResponse,
    APExceptionActionRecord,
    APExceptionOperationsGovernance,
    APExceptionOperationsResponse,
    APExceptionOperationsSummary,
    APExceptionQueueItem,
    APExceptionReason,
    APExtractedField,
    APGovernance,
    APControlCaseCreate,
    APControlCaseDetail,
    APControlCaseListResponse,
    APControlCaseSummary,
    APControlGate,
    APControlReviewCreate,
    APControlReviewRecord,
    APCashScenarioCreate,
    APCashScenarioHistoryResponse,
    APCashScenarioRecord,
    APCashWindow,
    APInvoiceDetailResponse,
    APInvoiceFilters,
    APInvoiceListResponse,
    APInvoiceSummary,
    APMetric,
    APOverviewResponse,
    APSourceDocument,
    APSyncResponse,
    APSegregationCheck,
    APVendorCashCoverage,
    APVendorCashGovernance,
    APVendorCashIntelligenceResponse,
    APVendorInsight,
    APTimelineEvent,
    APWarehouseApprovalActionRecord,
    APWarehouseApprovalItem,
    APWarehouseApprovalQueueResponse,
    AccountsPayableMetrics,
    DeferredCapability,
    SourceCoverageItem,
)
from .source import (
    DocumentEvidenceSource,
    build_projections,
    document_intelligence_source,
)


class APInvoiceNotFound(LookupError):
    """Raised when the requested local AP invoice projection is absent."""


class APControlCaseNotFound(LookupError):
    """Raised when the requested AP control case is absent."""


class APControlConflict(RuntimeError):
    """Raised when a requested control transition contradicts its evidence."""


class APDocumentJobNotEligible(LookupError):
    """Raised when an exact Document Intelligence job is not sync-eligible."""


class APDocumentReviewConflict(RuntimeError):
    """Raised when exact-job sync lacks current-run extraction review."""


def _now() -> datetime:
    return datetime.now(UTC)


def _float(value: Any) -> float | None:
    return float(value) if value is not None else None


def _clean_gl_code(value: Any) -> str | None:
    """Stringifies a GL division/account/department value without treating
    a genuine 0 as missing - these arrive as NOT NULL decimal columns from
    MaddenCo, so `Decimal(0) or None` would wrongly discard a real code."""

    return str(value).strip() or None if value is not None else None


def _default_on_ledger_job_started(job_id: str) -> None:
    job_queue.enqueue(
        job_id,
        "accounts_payable_erp_ledger_refresh",
        "AP open-ledger ERP refresh",
    )
    job_queue.mark_running(job_id)


def _default_on_ledger_job_complete(
    job_id: str,
    result: dict[str, Any] | None,
    error: BaseException | None,
) -> None:
    if error is not None:
        job_queue.mark_failed(job_id, message=str(error))
        return
    result = result or {}
    divisions_populated = result.get("divisions_populated")
    division_suffix = (
        f", {divisions_populated} GL divisions matched"
        if divisions_populated
        else ""
    )
    job_queue.mark_completed(
        job_id,
        message=(
            f"{result.get('total_count', 0)} open invoices, "
            f"${result.get('total_balance', 0):,.2f} balance{division_suffix}"
        ),
        result_module="Accounts Payable",
        result_reference=job_id,
    )


class AccountsPayableService:
    """Build read-only AP intelligence from existing document evidence."""

    def __init__(
        self,
        *,
        repository: AccountsPayableRepository = accounts_payable_repository,
        source: DocumentEvidenceSource = document_intelligence_source,
        clock: Callable[[], datetime] = _now,
        id_factory: Callable[[], str] | None = None,
        control_case_id_factory: Callable[[], str] | None = None,
        control_review_id_factory: Callable[[], str] | None = None,
        cash_scenario_id_factory: Callable[[], str] | None = None,
        exception_action_id_factory: Callable[[], str] | None = None,
        erp_ledger_repository: AccountsPayableErpLedgerRepository = (
            accounts_payable_erp_ledger_repository
        ),
        open_ledger_scan: Callable[[], list[dict[str, Any]]] = (
            scan_open_ap_ledger
        ),
        vendor_terms_scan: Callable[[], list[dict[str, Any]]] = (
            scan_vendor_terms_codes
        ),
        gl_division_scan: Callable[
            [list[str], list[int]], list[dict[str, Any]]
        ] = scan_gl_divisions_for_open_invoices,
        on_ledger_job_started: Callable[[str], None] = (
            _default_on_ledger_job_started
        ),
        on_ledger_job_complete: Callable[
            [str, dict[str, Any] | None, BaseException | None], None
        ] = _default_on_ledger_job_complete,
        warehouse_action_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self._repository = repository
        self._source = source
        self._clock = clock
        self._id_factory = id_factory or (
            lambda: f"ap-sync-{uuid4().hex}"
        )
        self._control_case_id_factory = control_case_id_factory or (
            lambda: f"ap-control-{uuid4().hex}"
        )
        self._control_review_id_factory = control_review_id_factory or (
            lambda: f"ap-control-review-{uuid4().hex}"
        )
        self._cash_scenario_id_factory = cash_scenario_id_factory or (
            lambda: f"ap-cash-scenario-{uuid4().hex}"
        )
        self._exception_action_id_factory = exception_action_id_factory or (
            lambda: f"ap-exception-action-{uuid4().hex}"
        )
        self._erp_ledger_repository = erp_ledger_repository
        self._open_ledger_scan = open_ledger_scan
        self._vendor_terms_scan = vendor_terms_scan
        self._gl_division_scan = gl_division_scan
        self._on_ledger_job_started = on_ledger_job_started
        self._on_ledger_job_complete = on_ledger_job_complete
        self._warehouse_action_id_factory = warehouse_action_id_factory or (
            lambda: f"ap-warehouse-action-{uuid4().hex}"
        )
        self._erp_ledger_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="etop-ap-erp-ledger",
        )

    @staticmethod
    def governance() -> APGovernance:
        return APGovernance(
            statements=[
                "This module is a local projection of saved Document Intelligence evidence plus append-only control-readiness records.",
                "Document extraction review is not AP invoice approval or payment authorization, even when its status is approved.",
                "Unknown source facts remain unavailable; classifier confidence is never relabeled as OCR confidence.",
                "Duplicate candidates are review evidence only and never suppress, approve, post, or pay an invoice.",
                "Control-case dispositions document evidence readiness only; operator-supplied identities do not establish approval or payment authority.",
                (
                    f"The {PROVISIONAL_OCR_REVIEW_THRESHOLD:.0%} OCR review "
                    f"threshold is provisional and inherited from "
                    f"{PROVISIONAL_OCR_THRESHOLD_SOURCE}; it grants no "
                    "straight-through authority."
                ),
            ]
        )

    @staticmethod
    def deferred_capabilities() -> list[DeferredCapability]:
        return [
            DeferredCapability(
                key="vendor_master",
                label="Authoritative Vendor Performance",
                reason=(
                    "Purchase volume, discount capture, and PO fill-rate are now "
                    "real via Vendor Intelligence's vendor evidence page. On-time "
                    "delivery and quality/chargeback history are a permanent gap, "
                    "not a future increment - no promised-delivery-date field or "
                    "returns/chargeback/quality table exists anywhere in the "
                    "connected MaddenCo instance to compute them from."
                ),
                missing_sources=["on-time delivery data", "quality/chargeback history"],
            ),
            DeferredCapability(
                key="governed_approval_workflow",
                label="Authorized Invoice Approval and SLA",
                reason=(
                    "Increment 2 records local control-readiness cases and review "
                    "dispositions, but authenticated identity, delegated authority, "
                    "notifications, and the shared Workflow/Decision Services remain unavailable."
                ),
                missing_sources=[
                    "shared workflow service",
                    "authority matrix",
                    "authentication",
                    "notification contract",
                ],
            ),
            DeferredCapability(
                key="cash_forecast",
                label="Authoritative Cash Forecast",
                reason=(
                    "The ERP open-ledger cache and vendor terms reference now make "
                    "current AP balance and flat-days discount eligibility real "
                    "(Increment 6), but projecting AP outflows against actual bank "
                    "cash position and treasury policy remains unconnected."
                ),
                missing_sources=["bank cash position", "treasury policy"],
            ),
            DeferredCapability(
                key="ai_and_image_similarity",
                label="AI Recommendations and Image Similarity",
                reason="Increment 1 uses deterministic evidence only and does not invoke AI or image comparison.",
                missing_sources=["approved AI service", "approved image-similarity control"],
            ),
        ]

    def source_coverage(self) -> list[SourceCoverageItem]:
        statistics = self._repository.source_statistics()
        count = int(statistics["count"])
        ocr_count = int(statistics["ocr_count"])
        structured_count = int(statistics["structured_count"])
        ledger_summary = self._erp_ledger_repository.open_ledger_summary(
            self._clock().date()
        )
        ledger_refreshed_at = ledger_summary["refreshed_at"]
        return [
            SourceCoverageItem(
                key="document_intelligence_vendor_invoices",
                label="Saved Vendor-Invoice Results",
                status="available",
                source="document_intelligence.doc_jobs/doc_results",
                as_of=statistics["as_of"],
                record_count=count,
                explanation=(
                    "Completed vendor-invoice jobs with saved results are the only imported source."
                ),
            ),
            SourceCoverageItem(
                key="structured_invoice_fields",
                label="Structured or Human-Corrected Invoice Fields",
                status=(
                    "available"
                    if count > 0 and structured_count == count
                    else "partial"
                    if structured_count > 0
                    else "unavailable"
                ),
                source="document_intelligence.parsed/document_extraction_review",
                as_of=statistics["as_of"],
                record_count=structured_count,
                explanation=(
                    "Structured extraction and human correction evidence take precedence over source-text candidates."
                ),
            ),
            SourceCoverageItem(
                key="ocr_confidence",
                label="OCR Confidence",
                status=(
                    "available"
                    if count > 0 and ocr_count == count
                    else "partial"
                    if ocr_count > 0
                    else "unavailable"
                ),
                source="document_intelligence.saved_result",
                as_of=statistics["as_of"],
                record_count=ocr_count,
                explanation=(
                    "Only explicit saved OCR confidence is counted. Document classification confidence is separate."
                ),
            ),
            SourceCoverageItem(
                key="erp_accounts_payable",
                label="ERP Accounts Payable Open Ledger",
                status="available" if ledger_refreshed_at else "not_connected",
                source=(
                    "accounts_payable.erp_open_ledger_cache"
                    if ledger_refreshed_at
                    else None
                ),
                as_of=ledger_refreshed_at,
                record_count=(
                    int(ledger_summary["total_count"])
                    if ledger_refreshed_at
                    else None
                ),
                explanation=(
                    "MaddenCo's open, unpaid, non-voided PMHD balance and vendor "
                    "terms are connected via the ERP ledger refresh job. "
                    "Per-invoice GL account/division/department and authoritative "
                    "payment/check/ACH history are not yet part of this module's "
                    "own coverage."
                    if ledger_refreshed_at
                    else "Trigger an ERP ledger refresh from the Executive Dashboard to connect this source."
                ),
            ),
        ]

    @staticmethod
    def _common_warnings() -> list[str]:
        return [
            "AP totals describe imported document evidence, not the ERP AP subledger.",
            "Source-text candidates require professional validation before downstream use.",
        ]

    def sync(self) -> APSyncResponse:
        source_items = self._source.list_vendor_invoice_evidence()
        return self._sync_source_items(source_items)

    def sync_document_job(self, job_id: str) -> APSyncResponse:
        from modules.document_intelligence.service import (
            processing_review_boundary,
        )

        with processing_review_boundary():
            evidence = self._source.get_vendor_invoice_evidence(job_id)
            if evidence is None:
                raise APDocumentJobNotEligible(
                    "The exact job is not a completed vendor-invoice result."
                )
            result = evidence.get("result")
            review_envelope = evidence.get("review")
            result = result if isinstance(result, dict) else {}
            review_envelope = (
                review_envelope if isinstance(review_envelope, dict) else {}
            )
            review = review_envelope.get("review")
            review = review if isinstance(review, dict) else {}
            current_run_id = result.get("processing_run_id")
            if (
                not current_run_id
                or review.get("processing_run_id") != current_run_id
                or review.get("status") != "approved"
            ):
                raise APDocumentReviewConflict(
                    "The exact current processing run must have extraction evidence "
                    "reviewed before controlled AP synchronization."
                )
            return self._sync_source_items([evidence])

    def _sync_source_items(
        self,
        source_items: list[dict[str, Any]],
    ) -> APSyncResponse:
        started = self._clock().astimezone(UTC).isoformat()
        projections = []
        warnings: list[str] = []
        skipped = 0
        for evidence in source_items:
            source_warning = evidence.get("source_warning")
            if source_warning:
                warnings.append(str(source_warning))
            built = build_projections(evidence)
            if not built:
                skipped += 1
                continue
            projections.extend(built)

        recorded_at = self._clock().astimezone(UTC).isoformat()
        result = self._repository.sync_projections(projections, recorded_at)
        completed = self._clock().astimezone(UTC).isoformat()
        warnings = list(dict.fromkeys(warnings))
        status = "completed_with_warnings" if warnings else "completed"
        return APSyncResponse(
            status=status,
            imported_count=result["imported"],
            updated_count=result["updated"],
            unchanged_count=result["unchanged"],
            skipped_count=skipped,
            eligible_job_count=len(source_items),
            duplicate_candidate_count=result["duplicate_candidates"],
            imported_event_count=result["events"],
            sync_id=self._id_factory(),
            started_at=started,
            completed_at=completed,
            message=(
                "Accounts Payable evidence sync completed. No PDF was opened, "
                "no OCR was run, and no ERP or financial transaction was changed."
            ),
            source_coverage=self.source_coverage(),
            governance=self.governance(),
            deferred_capabilities=self.deferred_capabilities(),
            warnings=warnings,
        )

    @staticmethod
    def _summary(row: dict[str, Any]) -> APInvoiceSummary:
        duplicate_count = int(row["duplicate_candidate_count"])
        review_required = bool(row["base_review_required"] or duplicate_count)
        return APInvoiceSummary(
            ap_invoice_id=row["ap_invoice_id"],
            document_job_id=row["document_job_id"],
            document_result_id=row["document_result_id"],
            source_record_index=row["source_record_index"],
            source_file_name=row["source_file_name"],
            vendor_number=row["vendor_number"],
            vendor_name=row["vendor_name"],
            invoice_number=row["invoice_number"],
            invoice_date=row["invoice_date"],
            received_at=row["received_at"],
            due_date=row["due_date"],
            purchase_order_number=row["purchase_order_number"],
            subtotal=_float(row["subtotal"]),
            tax=_float(row["tax"]),
            freight=_float(row["freight"]),
            discount=_float(row["discount"]),
            total_amount=_float(row["total_amount"]),
            currency=row["currency"],
            terms=row["terms"],
            status=("review_required" if review_required else "evidence_available"),
            review_required=review_required,
            ocr_review_required=bool(row["ocr_review_required"]),
            classification_confidence=row["classification_confidence"],
            ocr_confidence=row["ocr_confidence"],
            exception_count=len(row["exceptions"]),
            duplicate_candidate_count=duplicate_count,
            warnings=row["warnings"],
            processed_at=row["processed_at"],
            source_as_of=row["source_as_of"],
            last_synced_at=row["last_synced_at"],
        )

    def list_invoices(
        self,
        *,
        query: str | None,
        status: str | None,
        exception: bool | None,
        duplicate: bool | None,
        exception_code: str | None,
        limit: int,
        offset: int,
        sort_by: str,
        sort_order: str,
    ) -> APInvoiceListResponse:
        rows, total = self._repository.list_invoices(
            query=query,
            status=status,
            exception=exception,
            duplicate=duplicate,
            exception_code=exception_code,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        return APInvoiceListResponse(
            items=[self._summary(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
            filter_options=APInvoiceFilters(
                statuses=[
                    "review_required",
                    "evidence_available",
                    "ocr_review",
                ]
            ),
            source_coverage=self.source_coverage(),
            governance=self.governance(),
            deferred_capabilities=self.deferred_capabilities(),
            warnings=self._common_warnings(),
        )

    def get_invoice(self, ap_invoice_id: str) -> APInvoiceDetailResponse:
        row = self._repository.get_invoice(ap_invoice_id)
        if row is None:
            raise APInvoiceNotFound(
                f"Accounts Payable invoice {ap_invoice_id} was not found."
            )
        summary = self._summary(row).model_dump()
        duplicates = []
        for candidate in self._repository.list_duplicates(ap_invoice_id):
            evidence = candidate["evidence"]
            duplicates.append(
                APDuplicateEvidence(
                    candidate_id=candidate["candidate_id"],
                    candidate_ap_invoice_id=candidate[
                        "candidate_ap_invoice_id"
                    ],
                    candidate_invoice_number=candidate[
                        "candidate_invoice_number"
                    ],
                    candidate_vendor_name=candidate["candidate_vendor_name"],
                    candidate_amount=_float(candidate["candidate_amount"]),
                    match_factors=evidence["match_factors"],
                    amount_corroboration=candidate[
                        "amount_corroboration"
                    ],
                    date_corroboration=candidate["date_corroboration"],
                    explanation=evidence["explanation"],
                )
            )
        revision_count = self._repository.revision_count(ap_invoice_id)
        provenance = [
            f"Current evidence SHA-256: {row['source_evidence_sha256']}",
            f"Immutable AP evidence revisions retained: {revision_count}",
            f"Source result identity: document_intelligence.doc_results.job_id={row['document_result_id']}",
            "Field priority: document extraction review correction, then structured extraction, then saved source-text candidate.",
            "Document extraction review status is not AP approval, posting authority, or payment authorization.",
        ]
        return APInvoiceDetailResponse(
            **summary,
            source_document=APSourceDocument(
                job_id=row["document_job_id"],
                result_id=row["document_result_id"],
                file_name=row["source_file_name"],
                file_endpoint=(
                    f"/api/v1/documents/jobs/{row['document_job_id']}/file"
                ),
                content_type=row["content_type"],
                document_type=row["document_type"],
                status=row["document_status"],
                classifier=row["classifier"],
                parser_name=row["parser_name"],
                parser_version=row["parser_version"],
                classification_confidence=row["classification_confidence"],
                classification_evidence=row["classification_evidence"],
                created_at=row["received_at"],
                updated_at=row["processed_at"],
                result_created_at=row["source_result_created_at"],
                result_updated_at=row["source_result_updated_at"],
            ),
            extracted_fields=[
                APExtractedField(**field) for field in row["field_evidence"]
            ],
            exceptions=[
                APExceptionEvidence(**item) for item in row["exceptions"]
            ],
            duplicate_evidence=duplicates,
            timeline=[
                APTimelineEvent(**event)
                for event in self._repository.list_events(ap_invoice_id)
            ],
            source_coverage=self.source_coverage(),
            governance=self.governance(),
            deferred_capabilities=self.deferred_capabilities(),
            provenance=provenance,
            source_evidence_sha256=row["source_evidence_sha256"],
            evidence_revision_count=revision_count,
        )

    def create_control_case(
        self,
        ap_invoice_id: str,
        payload: APControlCaseCreate,
    ) -> APControlCaseDetail:
        invoice = self.get_invoice(ap_invoice_id)
        created_at = self._clock().astimezone(UTC).isoformat()
        stored = self._repository.create_control_case(
            {
                "control_case_id": self._control_case_id_factory(),
                "ap_invoice_id": ap_invoice_id,
                "intended_action": payload.intended_action,
                "requested_by": payload.requested_by,
                "assigned_reviewer": payload.assigned_reviewer,
                "payment_preparer": payload.payment_preparer,
                "notes": payload.notes,
                "created_at": created_at,
                "source_evidence_sha256": invoice.source_evidence_sha256,
                "evidence_snapshot": invoice.model_dump(mode="json"),
                "actor_identity_source": "operator_supplied",
                "actor_authority_status": "not_independently_verified",
                "approval_effect": "none",
                "payment_effect": "none",
            }
        )
        return self._control_case_detail(stored)

    def list_control_cases(
        self,
        *,
        intended_action: str | None,
        limit: int,
        offset: int,
    ) -> APControlCaseListResponse:
        rows, total = self._repository.list_control_cases(
            intended_action=intended_action,
            limit=limit,
            offset=offset,
        )
        return APControlCaseListResponse(
            items=[self._control_case_summary(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
            source_coverage=self.source_coverage(),
            governance=self.governance(),
            deferred_capabilities=self.deferred_capabilities(),
            warnings=self._control_warnings(),
        )

    def get_control_case(
        self,
        control_case_id: str,
    ) -> APControlCaseDetail:
        stored = self._repository.get_control_case(control_case_id)
        if stored is None:
            raise APControlCaseNotFound(
                f"AP control case {control_case_id} was not found."
            )
        return self._control_case_detail(stored)

    def create_control_review(
        self,
        control_case_id: str,
        payload: APControlReviewCreate,
    ) -> APControlCaseDetail:
        stored = self._repository.get_control_case(control_case_id)
        if stored is None:
            raise APControlCaseNotFound(
                f"AP control case {control_case_id} was not found."
            )
        if (
            payload.reviewer_identity.casefold()
            != str(stored["assigned_reviewer"]).casefold()
        ):
            raise APControlConflict(
                "The operator-supplied reviewer must match the assigned "
                "reviewer on this immutable control case."
            )

        current = self._control_case_summary(stored)
        if payload.disposition == "evidence_ready":
            blockers = [
                gate.label
                for gate in current.evidence_gates
                if gate.status == "blocked"
            ]
            blockers.extend(
                check.label
                for check in current.segregation_checks
                if check.status == "blocked"
            )
            if blockers:
                raise APControlConflict(
                    "Evidence cannot be marked ready while these controls are "
                    f"blocked: {', '.join(blockers)}."
                )

        created_at = self._clock().astimezone(UTC).isoformat()
        self._repository.create_control_review(
            {
                "review_id": self._control_review_id_factory(),
                "control_case_id": control_case_id,
                "reviewer_identity": payload.reviewer_identity,
                "disposition": payload.disposition,
                "notes": payload.notes,
                "created_at": created_at,
                "actor_identity_source": "operator_supplied",
                "actor_authority_status": "not_independently_verified",
                "approval_effect": "none",
                "payment_effect": "none",
            }
        )
        return self.get_control_case(control_case_id)

    def _control_case_detail(
        self,
        stored: dict[str, Any],
    ) -> APControlCaseDetail:
        summary = self._control_case_summary(stored)
        return APControlCaseDetail(
            **summary.model_dump(),
            reviews=[
                APControlReviewRecord(**review)
                for review in self._repository.list_control_reviews(
                    stored["control_case_id"]
                )
            ],
            source_evidence_sha256=stored["source_evidence_sha256"],
            evidence_snapshot=stored["evidence_snapshot"],
            evidence_snapshot_sha256=stored[
                "evidence_snapshot_sha256"
            ],
            source_coverage=self.source_coverage(),
            governance=self.governance(),
            deferred_capabilities=self.deferred_capabilities(),
            warnings=self._control_warnings(),
        )

    def _control_case_summary(
        self,
        stored: dict[str, Any],
    ) -> APControlCaseSummary:
        invoice_row = self._repository.get_invoice(stored["ap_invoice_id"])
        if invoice_row is None:
            raise APInvoiceNotFound(
                f"AP invoice {stored['ap_invoice_id']} was not found."
            )
        invoice = self._summary(invoice_row)
        duplicates = self._repository.list_duplicates(
            stored["ap_invoice_id"]
        )
        evidence_current = (
            invoice_row["source_evidence_sha256"]
            == stored["source_evidence_sha256"]
        )
        gates = self._control_gates(
            invoice_row,
            duplicate_count=len(duplicates),
            evidence_current=evidence_current,
            intended_action=stored["intended_action"],
        )
        segregation_checks = self._segregation_checks(stored)
        reviews = self._repository.list_control_reviews(
            stored["control_case_id"]
        )
        latest_review = (
            APControlReviewRecord(**reviews[0]) if reviews else None
        )
        status = (
            latest_review.disposition
            if latest_review is not None
            else "control_review_pending"
        )
        if not evidence_current and status == "evidence_ready":
            status = "not_ready"
        document_ready = not any(
            gate.status == "blocked" for gate in gates
        ) and not any(
            check.status == "blocked" for check in segregation_checks
        )
        return APControlCaseSummary(
            control_case_id=stored["control_case_id"],
            ap_invoice_id=stored["ap_invoice_id"],
            intended_action=stored["intended_action"],
            requested_by=stored["requested_by"],
            assigned_reviewer=stored["assigned_reviewer"],
            payment_preparer=stored["payment_preparer"],
            notes=stored["notes"],
            created_at=stored["created_at"],
            invoice=invoice,
            control_status=status,
            latest_review=latest_review,
            document_evidence_ready=document_ready,
            evidence_current=evidence_current,
            evidence_gates=gates,
            segregation_checks=segregation_checks,
        )

    @staticmethod
    def _control_gates(
        invoice: dict[str, Any],
        *,
        duplicate_count: int,
        evidence_current: bool,
        intended_action: str,
    ) -> list[APControlGate]:
        def presence_gate(
            code: str,
            label: str,
            present: bool,
            source: str,
        ) -> APControlGate:
            return APControlGate(
                code=code,
                label=label,
                status="passed" if present else "blocked",
                source=source if present else None,
                explanation=(
                    f"{label} is present in saved source evidence."
                    if present
                    else f"{label} is missing from saved source evidence."
                ),
            )

        gates = [
            presence_gate(
                "vendor_identity",
                "Vendor identity",
                bool(invoice.get("vendor_number") or invoice.get("vendor_name")),
                "Document Intelligence invoice evidence",
            ),
            presence_gate(
                "invoice_number",
                "Invoice number",
                bool(invoice.get("invoice_number")),
                "Document Intelligence invoice evidence",
            ),
            presence_gate(
                "invoice_date",
                "Invoice date",
                bool(invoice.get("invoice_date")),
                "Document Intelligence invoice evidence",
            ),
            presence_gate(
                "invoice_total",
                "Invoice total",
                invoice.get("total_amount") is not None,
                "Document Intelligence invoice evidence",
            ),
            APControlGate(
                code="deterministic_exceptions",
                label="Deterministic exceptions",
                status=(
                    "passed" if not invoice.get("exceptions") else "blocked"
                ),
                source="Accounts Payable Increment 1 exception evidence",
                explanation=(
                    "No deterministic exception evidence is attached."
                    if not invoice.get("exceptions")
                    else "One or more deterministic exceptions require professional review."
                ),
            ),
            APControlGate(
                code="duplicate_candidates",
                label="Duplicate candidates",
                status="passed" if duplicate_count == 0 else "blocked",
                source="Accounts Payable exact-identity duplicate rule v1",
                explanation=(
                    "No duplicate candidate evidence is attached."
                    if duplicate_count == 0
                    else f"{duplicate_count} duplicate candidate relationship(s) require review."
                ),
            ),
            APControlGate(
                code="source_evidence_current",
                label="Source evidence current",
                status="passed" if evidence_current else "blocked",
                source="Accounts Payable immutable evidence revisions",
                explanation=(
                    "The control case is bound to the current source evidence revision."
                    if evidence_current
                    else "Source evidence changed after case creation; create a new control case from the current revision."
                ),
            ),
            APControlGate(
                code="erp_vendor_master",
                label="ERP vendor master verification",
                status="unavailable",
                source=None,
                explanation="No governed ERP vendor-master source is connected.",
            ),
            APControlGate(
                code="erp_ap_open_item",
                label="ERP AP open-item verification",
                status="unavailable",
                source=None,
                explanation="No governed ERP AP open-item/payment-status source is connected.",
            ),
            APControlGate(
                code="approval_authority",
                label="Authenticated approval authority",
                status="unavailable",
                source=None,
                explanation="Authentication, delegated authority, and approval tiers are not connected.",
            ),
        ]
        if intended_action == "payment_preparation":
            gates.append(
                APControlGate(
                    code="payment_execution",
                    label="Payment execution authority",
                    status="unavailable",
                    source=None,
                    explanation="Bank/payment rails, dual authorization, and ERP payment posting are not connected.",
                )
            )
        return gates

    @staticmethod
    def _segregation_checks(
        stored: dict[str, Any],
    ) -> list[APSegregationCheck]:
        requester = str(stored["requested_by"]).strip()
        reviewer = str(stored["assigned_reviewer"]).strip()
        preparer = str(stored.get("payment_preparer") or "").strip()
        requester_reviewer_distinct = (
            requester.casefold() != reviewer.casefold()
        )
        checks = [
            APSegregationCheck(
                code="requester_reviewer_distinct",
                label="Requester and reviewer are distinct",
                status=(
                    "passed" if requester_reviewer_distinct else "blocked"
                ),
                identities=[requester, reviewer],
                explanation=(
                    "The operator-supplied requester and reviewer names are distinct."
                    if requester_reviewer_distinct
                    else "The same operator-supplied identity cannot request and review this case."
                ),
            )
        ]
        if stored["intended_action"] == "payment_preparation":
            if not preparer:
                checks.append(
                    APSegregationCheck(
                        code="reviewer_payment_preparer_distinct",
                        label="Reviewer and payment preparer are distinct",
                        status="blocked",
                        identities=[reviewer],
                        explanation="A payment-preparation case requires an operator-supplied preparer identity.",
                    )
                )
            else:
                distinct = reviewer.casefold() != preparer.casefold()
                checks.append(
                    APSegregationCheck(
                        code="reviewer_payment_preparer_distinct",
                        label="Reviewer and payment preparer are distinct",
                        status="passed" if distinct else "blocked",
                        identities=[reviewer, preparer],
                        explanation=(
                            "The operator-supplied reviewer and payment preparer names are distinct."
                            if distinct
                            else "The same operator-supplied identity cannot review and prepare payment evidence."
                        ),
                    )
                )
        else:
            checks.append(
                APSegregationCheck(
                    code="reviewer_payment_preparer_distinct",
                    label="Reviewer and payment preparer are distinct",
                    status="not_applicable",
                    identities=[reviewer],
                    explanation="This case is for approval review, not payment preparation.",
                )
            )
        return checks

    @staticmethod
    def _control_warnings() -> list[str]:
        return [
            "Control cases and dispositions use operator-supplied identities; they do not prove organizational authority.",
            "Evidence-ready means the local document/control packet passed its available gates. It is not invoice approval.",
            "Payment preparation remains unavailable until ERP payable status, vendor authority, payment rails, and dual authorization are governed.",
        ]

    def vendor_cash_intelligence(
        self,
        as_of_date: date | None = None,
    ) -> APVendorCashIntelligenceResponse:
        rows = self._repository.list_all_invoices()
        effective_date = as_of_date or self._clock().astimezone(UTC).date()
        generated_at = self._clock().astimezone(UTC).isoformat()
        source_as_of = (
            max(row["source_as_of"] for row in rows) if rows else None
        )
        vendor_groups: dict[str, dict[str, Any]] = {}
        cash_buckets: dict[str, dict[str, Any]] = {
            "past_due": {"label": "Past due by document date", "rows": []},
            "due_today": {"label": "Due today by document date", "rows": []},
            "next_7_days": {"label": "Due in next 7 days", "rows": []},
            "days_8_to_14": {"label": "Due in 8–14 days", "rows": []},
            "days_15_to_30": {"label": "Due in 15–30 days", "rows": []},
            "beyond_30_days": {"label": "Due beyond 30 days", "rows": []},
            "due_date_unavailable": {"label": "Due date unavailable", "rows": []},
        }

        for row in rows:
            vendor_number = str(row.get("vendor_number") or "").strip()
            vendor_name = str(row.get("vendor_name") or "").strip()
            if vendor_number:
                vendor_key = f"vendor-number:{vendor_number.casefold()}"
                identity_basis = "vendor_number"
            elif vendor_name:
                normalized = " ".join(vendor_name.casefold().split())
                vendor_key = f"vendor-name:{normalized}"
                identity_basis = "vendor_name"
            else:
                vendor_key = "unidentified"
                identity_basis = "unidentified"
            group = vendor_groups.setdefault(
                vendor_key,
                {
                    "identity_basis": identity_basis,
                    "vendor_number": vendor_number or None,
                    "vendor_name": vendor_name or None,
                    "rows": [],
                    "ocr_values": [],
                },
            )
            if group["vendor_name"] is None and vendor_name:
                group["vendor_name"] = vendor_name
            group["rows"].append(row)
            if row.get("ocr_confidence") is not None:
                group["ocr_values"].append(float(row["ocr_confidence"]))

            due_value = str(row.get("due_date") or "").strip()
            try:
                due = date.fromisoformat(due_value)
            except ValueError:
                cash_buckets["due_date_unavailable"]["rows"].append(row)
                continue
            days = (due - effective_date).days
            if days < 0:
                code = "past_due"
            elif days == 0:
                code = "due_today"
            elif days <= 7:
                code = "next_7_days"
            elif days <= 14:
                code = "days_8_to_14"
            elif days <= 30:
                code = "days_15_to_30"
            else:
                code = "beyond_30_days"
            cash_buckets[code]["rows"].append(row)

        vendors: list[APVendorInsight] = []
        for vendor_key, group in vendor_groups.items():
            vendor_rows = group["rows"]
            known_totals = [
                float(row["total_amount"])
                for row in vendor_rows
                if row.get("total_amount") is not None
            ]
            review_count = sum(
                bool(
                    row.get("base_review_required")
                    or row.get("duplicate_candidate_count")
                )
                for row in vendor_rows
            )
            exception_count = sum(
                bool(row.get("exceptions")) for row in vendor_rows
            )
            duplicate_count = sum(
                int(row.get("duplicate_candidate_count", 0)) > 0
                for row in vendor_rows
            )
            alerts: list[str] = []
            if group["identity_basis"] == "unidentified":
                alerts.append("Vendor identity is unavailable in saved evidence.")
            if review_count:
                alerts.append(
                    f"{review_count} invoice(s) require document or duplicate review."
                )
            if len(known_totals) != len(vendor_rows):
                alerts.append("One or more invoice totals are unavailable.")
            if sum(bool(row.get("due_date")) for row in vendor_rows) != len(vendor_rows):
                alerts.append("One or more due dates are unavailable.")
            ocr_values = group["ocr_values"]
            vendors.append(
                APVendorInsight(
                    vendor_key=vendor_key,
                    identity_basis=group["identity_basis"],
                    vendor_number=group["vendor_number"],
                    vendor_name=group["vendor_name"],
                    invoice_count=len(vendor_rows),
                    known_total_count=len(known_totals),
                    extracted_total_amount=round(sum(known_totals), 2),
                    due_date_count=sum(
                        bool(row.get("due_date")) for row in vendor_rows
                    ),
                    review_required_count=review_count,
                    exception_invoice_count=exception_count,
                    duplicate_candidate_invoice_count=duplicate_count,
                    ocr_average_confidence=(
                        round(sum(ocr_values) / len(ocr_values), 4)
                        if ocr_values
                        else None
                    ),
                    evidence_alerts=alerts,
                )
            )
        vendors.sort(
            key=lambda vendor: (
                -vendor.extracted_total_amount,
                -vendor.invoice_count,
                (vendor.vendor_name or vendor.vendor_number or "").casefold(),
            )
        )

        explanations = {
            "past_due": "Due date is before the selected as-of date; current payable/payment status is unknown.",
            "due_today": "Due date equals the selected as-of date; current payable/payment status is unknown.",
            "next_7_days": "Due date is 1–7 days after the selected as-of date.",
            "days_8_to_14": "Due date is 8–14 days after the selected as-of date.",
            "days_15_to_30": "Due date is 15–30 days after the selected as-of date.",
            "beyond_30_days": "Due date is more than 30 days after the selected as-of date.",
            "due_date_unavailable": "No valid saved document due date is available for classification.",
        }
        cash_windows = []
        for code, bucket in cash_buckets.items():
            bucket_rows = bucket["rows"]
            known_amounts = [
                float(row["total_amount"])
                for row in bucket_rows
                if row.get("total_amount") is not None
            ]
            cash_windows.append(
                APCashWindow(
                    code=code,
                    label=bucket["label"],
                    invoice_count=len(bucket_rows),
                    known_amount_count=len(known_amounts),
                    extracted_amount=round(sum(known_amounts), 2),
                    explanation=explanations[code],
                )
            )

        return APVendorCashIntelligenceResponse(
            generated_at=generated_at,
            as_of_date=effective_date,
            coverage=APVendorCashCoverage(
                imported_invoice_count=len(rows),
                identified_vendor_invoice_count=sum(
                    bool(row.get("vendor_number") or row.get("vendor_name"))
                    for row in rows
                ),
                due_date_invoice_count=sum(bool(row.get("due_date")) for row in rows),
                known_amount_invoice_count=sum(
                    row.get("total_amount") is not None for row in rows
                ),
                review_required_invoice_count=sum(
                    bool(
                        row.get("base_review_required")
                        or row.get("duplicate_candidate_count")
                    )
                    for row in rows
                ),
                source_as_of=source_as_of,
            ),
            vendors=vendors,
            cash_windows=cash_windows,
            governance=APVendorCashGovernance(
                statements=[
                    "Vendor groups are document-evidence aggregates, not reconciled ERP vendor-master entities.",
                    "Cash windows use saved invoice due dates and extracted totals; they do not prove a current unpaid liability.",
                    "No vendor score, payment proposal, approval, authorization, posting, or ERP write is produced.",
                ]
            ),
            source_coverage=self.source_coverage(),
            deferred_capabilities=self.deferred_capabilities(),
            warnings=[
                "Paid, voided, disputed, credited, and currently open ERP payable status is not connected.",
                "Vendor terms, discounts, master identity, PO/receipt performance, and payment outcomes are not connected.",
            ],
        )

    def create_cash_scenario(
        self,
        payload: APCashScenarioCreate,
    ) -> APCashScenarioRecord:
        rows = self._repository.list_all_invoices()
        horizon_end = payload.as_of_date + timedelta(days=payload.horizon_days)
        included: list[dict[str, Any]] = []
        excluded_review = 0
        excluded_due = 0
        for row in rows:
            due_value = str(row.get("due_date") or "").strip()
            try:
                due = date.fromisoformat(due_value)
            except ValueError:
                excluded_due += 1
                continue
            if due > horizon_end:
                continue
            review_required = bool(
                row.get("base_review_required")
                or row.get("duplicate_candidate_count")
            )
            if review_required and not payload.include_review_required:
                excluded_review += 1
                continue
            included.append(row)
        known_amounts = [
            float(row["total_amount"])
            for row in included
            if row.get("total_amount") is not None
        ]
        evidence_snapshot = {
            "as_of_date": payload.as_of_date.isoformat(),
            "horizon_days": payload.horizon_days,
            "horizon_end_date": horizon_end.isoformat(),
            "include_review_required": payload.include_review_required,
            "source_authority": "document_intelligence_extracted_evidence",
            "current_payable_status_known": False,
            "invoices": [
                {
                    "ap_invoice_id": row["ap_invoice_id"],
                    "vendor_number": row.get("vendor_number"),
                    "vendor_name": row.get("vendor_name"),
                    "invoice_number": row.get("invoice_number"),
                    "due_date": row.get("due_date"),
                    "total_amount": row.get("total_amount"),
                    "review_required": bool(
                        row.get("base_review_required")
                        or row.get("duplicate_candidate_count")
                    ),
                    "source_as_of": row["source_as_of"],
                    "source_evidence_sha256": row[
                        "source_evidence_sha256"
                    ],
                }
                for row in included
            ],
        }
        record = {
            "cash_scenario_id": self._cash_scenario_id_factory(),
            "as_of_date": payload.as_of_date.isoformat(),
            "horizon_days": payload.horizon_days,
            "horizon_end_date": horizon_end.isoformat(),
            "include_review_required": payload.include_review_required,
            "prepared_by": payload.prepared_by,
            "rationale": payload.rationale,
            "created_at": self._clock().astimezone(UTC).isoformat(),
            "included_invoice_count": len(included),
            "included_known_amount_count": len(known_amounts),
            "extracted_amount": round(sum(known_amounts), 2),
            "excluded_review_required_count": excluded_review,
            "excluded_missing_due_date_count": excluded_due,
            "excluded_missing_amount_count": len(included) - len(known_amounts),
            "actor_identity_source": "operator_supplied",
            "actor_authority_status": "not_independently_verified",
            "scenario_classification": "analytical_scenario",
            "approval_effect": "none",
            "payment_effect": "none",
            "erp_write": False,
            "evidence_snapshot": evidence_snapshot,
        }
        return APCashScenarioRecord(
            **self._repository.create_cash_scenario(record)
        )

    def list_cash_scenarios(self) -> APCashScenarioHistoryResponse:
        records = [
            APCashScenarioRecord(**record)
            for record in self._repository.list_cash_scenarios()
        ]
        return APCashScenarioHistoryResponse(
            count=len(records),
            scenarios=records,
            governance=APVendorCashGovernance(
                statements=[
                    "Saved scenarios are immutable document-evidence analyses, not payment proposals or batches.",
                ]
            ),
            warnings=[
                "Current ERP payable/payment status remains unavailable; historical scenario amounts may include invoices no longer payable.",
            ],
        )

    @staticmethod
    def _exception_reasons(row: dict[str, Any]) -> list[APExceptionReason]:
        reasons = [
            APExceptionReason(
                code=str(exception.get("code") or "saved_exception"),
                label=str(exception.get("label") or "Saved exception"),
                severity=str(exception.get("severity") or "review"),
                source="saved_exception",
                explanation=str(
                    exception.get("explanation")
                    or "Document Intelligence retained this exception."
                ),
            )
            for exception in row.get("exceptions", [])
        ]
        if int(row.get("duplicate_candidate_count", 0)) > 0:
            reasons.append(
                APExceptionReason(
                    code="duplicate_candidate",
                    label="Duplicate candidate evidence",
                    severity="review",
                    source="duplicate_candidate",
                    explanation=(
                        f"{int(row['duplicate_candidate_count'])} deterministic "
                        "duplicate candidate relationship(s) require professional review."
                    ),
                )
            )
        if bool(row.get("ocr_review_required")) and not any(
            reason.source == "saved_exception"
            and "ocr" in reason.code.casefold()
            for reason in reasons
        ):
            reasons.append(
                APExceptionReason(
                    code="ocr_review_required",
                    label="OCR review required",
                    severity="review",
                    source="ocr_review",
                    explanation=(
                        "The saved source evidence requires OCR review under the "
                        "existing provisional document-review rule."
                    ),
                )
            )
        if not reasons and bool(row.get("base_review_required")):
            reasons.append(
                APExceptionReason(
                    code="source_review_required",
                    label="Source review required",
                    severity="review",
                    source="source_review_flag",
                    explanation=(
                        "The imported source marks this invoice for review but "
                        "supplies no more specific current exception reason."
                    ),
                )
            )
        return reasons

    def exception_operations(
        self,
        as_of_date: date | None = None,
    ) -> APExceptionOperationsResponse:
        rows = self._repository.list_all_invoices()
        effective_date = as_of_date or self._clock().astimezone(UTC).date()
        latest_actions = self._repository.list_latest_exception_actions()
        queue_rows: list[dict[str, Any]] = []
        severity_rank = {"high": 0, "medium": 1, "review": 2, "low": 3}
        state_rank = {
            "source_changed": 0,
            "follow_up_overdue": 1,
            "unworked": 2,
            "follow_up_scheduled": 3,
            "documented": 4,
            "documented_for_next_step": 5,
        }

        for row in rows:
            review_required = bool(
                row.get("base_review_required")
                or row.get("duplicate_candidate_count")
            )
            if not review_required:
                continue
            latest_row = latest_actions.get(str(row["ap_invoice_id"]))
            latest = (
                APExceptionActionRecord(**latest_row)
                if latest_row is not None
                else None
            )
            if latest is None:
                work_state = "unworked"
            elif latest.source_evidence_sha256 != row["source_evidence_sha256"]:
                work_state = "source_changed"
            elif latest.follow_up_date is not None:
                work_state = (
                    "follow_up_overdue"
                    if latest.follow_up_date < effective_date
                    else "follow_up_scheduled"
                )
            elif latest.disposition == "ready_for_control_case":
                work_state = "documented_for_next_step"
            else:
                work_state = "documented"
            reasons = self._exception_reasons(row)
            queue_rows.append(
                {
                    "ap_invoice_id": row["ap_invoice_id"],
                    "vendor_number": row.get("vendor_number"),
                    "vendor_name": row.get("vendor_name"),
                    "invoice_number": row.get("invoice_number"),
                    "invoice_date": row.get("invoice_date"),
                    "due_date": row.get("due_date"),
                    "total_amount": _float(row.get("total_amount")),
                    "source_file_name": row["source_file_name"],
                    "source_as_of": row["source_as_of"],
                    "source_evidence_sha256": row["source_evidence_sha256"],
                    "exception_count": len(row.get("exceptions", [])),
                    "duplicate_candidate_count": int(
                        row.get("duplicate_candidate_count", 0)
                    ),
                    "ocr_review_required": bool(row.get("ocr_review_required")),
                    "reasons": reasons,
                    "work_state": work_state,
                    "latest_action": latest,
                    "_sort": (
                        state_rank[work_state],
                        min(
                            (severity_rank[reason.severity] for reason in reasons),
                            default=4,
                        ),
                        str(row.get("received_at") or row["source_as_of"]),
                        str(row["ap_invoice_id"]),
                    ),
                }
            )

        queue_rows.sort(key=lambda item: item["_sort"])
        items = []
        for rank, item in enumerate(queue_rows, start=1):
            item.pop("_sort")
            items.append(APExceptionQueueItem(queue_rank=rank, **item))
        known_amounts = [
            item.total_amount for item in items if item.total_amount is not None
        ]
        return APExceptionOperationsResponse(
            generated_at=self._clock().astimezone(UTC).isoformat(),
            as_of_date=effective_date,
            summary=APExceptionOperationsSummary(
                queue_count=len(items),
                unworked_count=sum(item.work_state == "unworked" for item in items),
                follow_up_scheduled_count=sum(
                    item.work_state == "follow_up_scheduled" for item in items
                ),
                follow_up_overdue_count=sum(
                    item.work_state == "follow_up_overdue" for item in items
                ),
                source_changed_count=sum(
                    item.work_state == "source_changed" for item in items
                ),
                documented_count=sum(
                    item.work_state in {"documented", "documented_for_next_step"}
                    for item in items
                ),
                duplicate_review_count=sum(
                    item.duplicate_candidate_count > 0 for item in items
                ),
                ocr_review_count=sum(item.ocr_review_required for item in items),
                known_amount_count=len(known_amounts),
                extracted_amount=round(sum(known_amounts), 2),
            ),
            items=items,
            source_coverage=self.source_coverage(),
            governance=APExceptionOperationsGovernance(
                statements=[
                    "The queue contains imported invoices with existing deterministic review evidence only.",
                    "Ordering uses follow-up/source state, saved exception severity, source time, and invoice identity without a hidden score.",
                    "Actions are append-only operator-supplied work metadata and never clear source exceptions or duplicate evidence.",
                ]
            ),
            deferred_capabilities=self.deferred_capabilities(),
            warnings=[
                "No approved SLA, authenticated assignment, escalation, notification, invoice approval, or payment authority is connected.",
                "Document corrections remain owned by Document Intelligence; this queue preserves follow-up metadata only.",
            ],
        )

    def create_exception_action(
        self,
        ap_invoice_id: str,
        payload: APExceptionActionCreate,
    ) -> APExceptionActionRecord:
        queue = self.exception_operations()
        item = next(
            (
                candidate
                for candidate in queue.items
                if candidate.ap_invoice_id == ap_invoice_id
            ),
            None,
        )
        if item is None:
            if self._repository.get_invoice(ap_invoice_id) is None:
                raise APInvoiceNotFound(
                    f"Accounts Payable invoice {ap_invoice_id} was not found."
                )
            raise APControlConflict(
                "Exception actions require current saved exception, OCR-review, "
                "or duplicate-candidate evidence."
            )
        evidence_snapshot = item.model_dump(
            mode="json",
            exclude={"latest_action"},
        )
        evidence_snapshot["prior_action"] = (
            {
                "action_id": item.latest_action.action_id,
                "disposition": item.latest_action.disposition,
                "created_at": item.latest_action.created_at,
                "evidence_snapshot_sha256": (
                    item.latest_action.evidence_snapshot_sha256
                ),
            }
            if item.latest_action is not None
            else None
        )
        record = {
            "action_id": self._exception_action_id_factory(),
            "ap_invoice_id": ap_invoice_id,
            "disposition": payload.disposition,
            "owner_identity": payload.owner_identity,
            "actor_identity": payload.actor_identity,
            "notes": payload.notes,
            "follow_up_date": (
                payload.follow_up_date.isoformat()
                if payload.follow_up_date is not None
                else None
            ),
            "created_at": self._clock().astimezone(UTC).isoformat(),
            "source_evidence_sha256": item.source_evidence_sha256,
            "actor_identity_source": "operator_supplied",
            "owner_identity_source": "operator_supplied",
            "authority_status": "not_independently_verified",
            "action_classification": "professional_workflow_metadata",
            "approval_effect": "none",
            "payment_effect": "none",
            "erp_write": False,
            "evidence_snapshot": evidence_snapshot,
        }
        return APExceptionActionRecord(
            **self._repository.create_exception_action(record)
        )

    def list_exception_actions(
        self,
        ap_invoice_id: str,
    ) -> APExceptionActionHistoryResponse:
        if self._repository.get_invoice(ap_invoice_id) is None:
            raise APInvoiceNotFound(
                f"Accounts Payable invoice {ap_invoice_id} was not found."
            )
        actions = [
            APExceptionActionRecord(**record)
            for record in self._repository.list_exception_actions(ap_invoice_id)
        ]
        return APExceptionActionHistoryResponse(
            ap_invoice_id=ap_invoice_id,
            count=len(actions),
            actions=actions,
            governance=APExceptionOperationsGovernance(
                statements=[
                    "Exception action history is append-only professional work metadata with no approval, payment, or ERP effect."
                ]
            ),
        )

    def refresh_erp_ledger(self, *, background: bool = True) -> dict[str, Any]:
        job_id = f"ap-erp-ledger-refresh-{uuid4().hex}"
        self._on_ledger_job_started(job_id)
        if background:
            self._erp_ledger_executor.submit(
                self._run_erp_ledger_refresh_job,
                job_id,
            )
            return {"job_id": job_id, "status": "queued"}
        result = self._execute_erp_ledger_refresh()
        self._on_ledger_job_complete(job_id, result, None)
        return {"job_id": job_id, "status": "completed", **result}

    def _run_erp_ledger_refresh_job(self, job_id: str) -> None:
        try:
            result = self._execute_erp_ledger_refresh()
        except Exception as error:  # noqa: BLE001 - always reported, never lost
            self._on_ledger_job_complete(job_id, None, error)
            return
        self._on_ledger_job_complete(job_id, result, None)

    def _execute_erp_ledger_refresh(self) -> dict[str, Any]:
        ledger_rows = self._open_ledger_scan()
        terms_rows = self._vendor_terms_scan()
        ledger_count = self._erp_ledger_repository.replace_open_ledger(
            ledger_rows
        )
        self._erp_ledger_repository.replace_vendor_terms_cache(terms_rows)
        divisions_populated = self._refresh_open_ledger_divisions(ledger_rows)
        summary = self._erp_ledger_repository.open_ledger_summary(
            self._clock().date()
        )
        return {
            "ledger_count": ledger_count,
            "divisions_populated": divisions_populated,
            **summary,
        }

    def _refresh_open_ledger_divisions(
        self, ledger_rows: list[dict[str, Any]]
    ) -> int:
        """Scopes the PMGLDS division scan to just the vendors/years behind
        currently open invoices, then keeps only GL lines matching an open
        invoice identity - a vendor's full-year GL activity from the scan
        includes paid invoices too, which must never receive GL detail
        here. When more than one GL line exists for an invoice, the line
        with the largest PMGAMTINV is used - a disclosed simplification,
        not a guarantee of the "true" distribution line. Account and
        department are taken from that same winning line."""

        open_keys: set[tuple[str, str]] = set()
        vendor_numbers: set[str] = set()
        years: set[int] = set()
        for row in ledger_rows:
            vendor_number = str(row.get("PMHNBVND") or "").strip()
            invoice_number = str(row.get("PMHNBINV") or "").strip()
            if not vendor_number or vendor_number == "0" or not invoice_number:
                continue
            open_keys.add((vendor_number, invoice_number))
            vendor_numbers.add(vendor_number)
            invoice_date = parse_madden_date(row.get("PMHDTEINV"))
            if invoice_date is not None:
                years.add(invoice_date.year)

        if not open_keys or not vendor_numbers or not years:
            return 0

        division_rows = self._gl_division_scan(
            sorted(vendor_numbers), sorted(years)
        )
        best: dict[tuple[str, str], tuple[float, str, str | None, str | None]] = {}
        for row in division_rows:
            vendor_number = str(row.get("PMGNBVND") or "").strip()
            invoice_number = str(row.get("PMGNBINV") or "").strip()
            key = (vendor_number, invoice_number)
            if key not in open_keys:
                continue
            # PMGNBGLDV/PMGNBGL/PMGNBGLDP are NOT NULL decimal columns - a
            # genuine value of 0 (e.g. department 0) is a valid GL code,
            # not a missing one. `x or ""` would wrongly treat Decimal(0)
            # as falsy and drop it, so None is checked explicitly instead.
            division = _clean_gl_code(row.get("PMGNBGLDV"))
            if not division:
                continue
            account = _clean_gl_code(row.get("PMGNBGL"))
            department = _clean_gl_code(row.get("PMGNBGLDP"))
            amount = float(row.get("PMGAMTINV") or 0)
            existing = best.get(key)
            if existing is None or amount > existing[0]:
                best[key] = (amount, division, account, department)

        gl_fields = {
            key: (division, account, department)
            for key, (_, division, account, department) in best.items()
        }
        return self._erp_ledger_repository.update_open_ledger_gl_fields(
            gl_fields
        )

    def _erp_ledger_metrics(self) -> dict[str, APMetric]:
        summary = self._erp_ledger_repository.open_ledger_summary(
            self._clock().date()
        )
        refreshed_at = summary["refreshed_at"]

        def unavailable(label: str) -> APMetric:
            return APMetric(
                value=None,
                status="unavailable",
                source=None,
                as_of=None,
                explanation=(
                    f"{label} is unavailable until the ERP open-ledger cache "
                    "has been refreshed at least once. Trigger a refresh from "
                    "the Executive Dashboard."
                ),
            )

        if refreshed_at is None:
            return {
                "current_ap_balance": unavailable("Current AP balance"),
                "due_today_count": unavailable("Invoices due today"),
                "due_today_amount": unavailable("Amount due today"),
                "past_due_count": unavailable("Past-due invoice count"),
                "past_due_amount": unavailable("Past-due amount"),
                "due_within_7_days_amount": unavailable(
                    "Cash required within seven days"
                ),
            }

        def available(value: int | float, explanation: str) -> APMetric:
            return APMetric(
                value=value,
                status="available",
                source="accounts_payable.erp_open_ledger_cache",
                as_of=refreshed_at,
                explanation=explanation,
            )

        return {
            "current_ap_balance": available(
                round(summary["total_balance"], 2),
                (
                    f"Sum of open PMHD invoices net of discount "
                    f"({summary['total_count']} invoices cached); excludes "
                    f"{summary['on_hold_count']} on-hold invoices totaling "
                    f"${summary['on_hold_amount']:,.2f}, disclosed separately."
                ),
            ),
            "due_today_count": available(
                summary["due_today_count"],
                "Open, not-on-hold invoices whose PMHD due date is today.",
            ),
            "due_today_amount": available(
                round(summary["due_today_amount"], 2),
                "Net amount for invoices due today, excluding on-hold invoices.",
            ),
            "past_due_count": available(
                summary["past_due_count"],
                "Open, not-on-hold invoices whose PMHD due date is before today.",
            ),
            "past_due_amount": available(
                round(summary["past_due_amount"], 2),
                "Net amount for past-due invoices, excluding on-hold invoices.",
            ),
            "due_within_7_days_amount": available(
                round(summary["due_within_7_days_amount"], 2),
                (
                    "Net amount due today through 7 days from today, "
                    "excluding on-hold invoices."
                ),
            ),
        }

    def _average_approval_time_metric(self) -> APMetric:
        stats = self._repository.approval_time_stats("approval_review")
        if stats["case_count"] == 0 or stats["average_hours"] is None:
            return APMetric(
                value=None,
                status="unavailable",
                source=None,
                as_of=None,
                explanation="No reviewed approval-readiness cases exist yet.",
            )
        return APMetric(
            value=round(stats["average_hours"], 2),
            status="available",
            source="accounts_payable.local_projection",
            as_of=stats["latest_reviewed_at"],
            explanation=(
                "Average hours from control-case creation to its first "
                "recorded review disposition, across approval-review cases. "
                "This is local review-readiness turnaround, not a governed "
                "invoice-approval SLA."
            ),
        )

    def list_vendor_terms_reference(self) -> list[dict[str, Any]]:
        return self._erp_ledger_repository.list_vendor_terms_reference()

    def upsert_vendor_terms_reference(self, terms_code: str, fields: dict[str, Any]) -> None:
        self._erp_ledger_repository.upsert_vendor_terms_reference(
            terms_code=terms_code,
            discount_percent=fields["discount_percent"],
            num_periods=fields.get("num_periods"),
            num_months=fields.get("num_months"),
            num_days=fields.get("num_days"),
            second_period=fields.get("second_period"),
            third_period=fields.get("third_period"),
            next_period=fields.get("next_period"),
            day_of_month=fields.get("day_of_month"),
            cutoff_day=fields.get("cutoff_day"),
            description=fields.get("description", ""),
        )

    def warehouse_approval_queue(
        self, division: str | None
    ) -> APWarehouseApprovalQueueResponse:
        result = self._erp_ledger_repository.warehouse_approval_queue(division)
        buckets: dict[str, list[APWarehouseApprovalItem]] = {
            "needs_approval": [],
            "approved_by_warehouse": [],
            "approved_and_entered_by_ap": [],
        }
        for row in result["items"]:
            item = APWarehouseApprovalItem(
                vendor_number=row["vendor_number"],
                vendor_name=row["vendor_name"],
                invoice_number=row["invoice_number"],
                invoice_date=row["invoice_date"],
                due_date=row["due_date"],
                amount_invoiced=row["amount_invoiced"],
                amount_discount=row["amount_discount"],
                on_hold=bool(row["on_hold"]),
                gl_account=row["gl_account"],
                gl_division=row["gl_division"],
                gl_department=row["gl_department"],
                status=row["status"],
                last_actor_identity=row["last_actor_identity"],
                last_action_at=row["last_action_at"],
                linked_ap_invoice_id=row["linked_ap_invoice_id"],
            )
            buckets[item.status].append(item)
        return APWarehouseApprovalQueueResponse(
            division=division,
            available_divisions=result["available_divisions"],
            needs_approval=buckets["needs_approval"],
            approved_by_warehouse=buckets["approved_by_warehouse"],
            approved_and_entered_by_ap=buckets["approved_and_entered_by_ap"],
            governance=self.governance(),
        )

    def record_warehouse_approval_action(
        self,
        *,
        vendor_number: str,
        invoice_number: str,
        to_status: str,
        actor_identity: str,
        notes: str,
    ) -> APWarehouseApprovalActionRecord:
        record = self._erp_ledger_repository.record_warehouse_approval_action(
            action_id=self._warehouse_action_id_factory(),
            vendor_number=vendor_number,
            invoice_number=invoice_number,
            to_status=to_status,
            actor_identity=actor_identity,
            actor_identity_source="operator_supplied",
            notes=notes,
            created_at=self._clock().isoformat(),
        )
        return APWarehouseApprovalActionRecord(**record)

    def _discounts_available_metric(self) -> APMetric:
        ledger_refreshed_at = self._erp_ledger_repository.open_ledger_refreshed_at()
        if ledger_refreshed_at is None:
            return APMetric(
                value=None,
                status="unavailable",
                source=None,
                as_of=None,
                explanation=(
                    "Eligible payment discounts is unavailable until the ERP "
                    "open-ledger cache has been refreshed at least once."
                ),
            )
        summary = self._erp_ledger_repository.discount_eligibility_summary(
            self._clock().date()
        )
        if not summary["has_reference_data"]:
            return APMetric(
                value=None,
                status="unavailable",
                source=None,
                as_of=None,
                explanation=(
                    "No vendor terms reference data has been entered yet. "
                    "Add terms codes under Vendor Intelligence to compute "
                    "eligible payment discounts."
                ),
            )
        excluded = summary["excluded_codes"]
        explanation = (
            f"Sum of discount-eligible amounts for open, not-on-hold "
            f"invoices still inside a flat N-days-from-invoice-date "
            f"discount window ({summary['eligible_count']} invoices)."
        )
        if excluded:
            codes = ", ".join(
                f"{row['terms_code']} ({row['description']})" if row["description"]
                else row["terms_code"]
                for row in excluded
            )
            explanation += (
                f" {len(excluded)} discount-bearing terms code(s) use "
                f"day-of-month/cutoff logic, not yet modeled, and are "
                f"excluded from this figure rather than counted as zero: "
                f"{codes}."
            )
        return APMetric(
            value=round(summary["eligible_amount"], 2),
            status="partial" if excluded else "available",
            source="accounts_payable.erp_open_ledger_cache",
            as_of=ledger_refreshed_at,
            explanation=explanation,
        )

    def overview(self) -> APOverviewResponse:
        rows = self._repository.list_all_invoices()
        generated_at = self._clock().astimezone(UTC).isoformat()
        source_as_of = (
            max(row["source_as_of"] for row in rows) if rows else None
        )
        review_count = sum(
            bool(row["base_review_required"] or row["duplicate_candidate_count"])
            for row in rows
        )
        exception_count = sum(len(row["exceptions"]) for row in rows)
        duplicate_count = sum(row["duplicate_candidate_count"] for row in rows) // 2
        ocr_values = [
            float(row["ocr_confidence"])
            for row in rows
            if row["ocr_confidence"] is not None
        ]
        extracted_totals = [
            float(row["total_amount"])
            for row in rows
            if row["total_amount"] is not None
        ]

        def local_metric(value: int | float, explanation: str) -> APMetric:
            return APMetric(
                value=value,
                status="available",
                source="accounts_payable.local_projection",
                as_of=source_as_of,
                explanation=explanation,
            )

        ocr_average = (
            round(sum(ocr_values) / len(ocr_values), 6)
            if ocr_values
            else None
        )
        ocr_metric = APMetric(
            value=ocr_average,
            status=(
                "available"
                if rows and len(ocr_values) == len(rows)
                else "partial"
                if ocr_values
                else "unavailable"
            ),
            source=(
                "document_intelligence.saved_result" if ocr_values else None
            ),
            as_of=source_as_of if ocr_values else None,
            explanation=(
                "Average of explicit saved OCR confidence values only; classification confidence is excluded."
            ),
        )
        return APOverviewResponse(
            generated_at=generated_at,
            metrics=AccountsPayableMetrics(
                imported_invoice_count=local_metric(
                    len(rows),
                    "Current locally imported vendor-invoice evidence objects.",
                ),
                review_required_count=local_metric(
                    review_count,
                    "Imported invoices with deterministic exceptions or duplicate candidates.",
                ),
                exception_count=local_metric(
                    exception_count,
                    "Deterministic exception records attached to imported invoice evidence.",
                ),
                duplicate_candidate_count=local_metric(
                    duplicate_count,
                    "Conservative unordered duplicate pairs under the exact-identity v1 rule.",
                ),
                ocr_processed_count=local_metric(
                    len(ocr_values),
                    "Imported invoices carrying explicit saved OCR confidence evidence.",
                ),
                ocr_average_confidence=ocr_metric,
                extracted_invoice_total=APMetric(
                    value=(
                        round(sum(extracted_totals), 2)
                        if extracted_totals
                        else None
                    ),
                    status="partial" if extracted_totals else "unavailable",
                    source=(
                        "document_intelligence.saved_result"
                        if extracted_totals
                        else None
                    ),
                    as_of=source_as_of if extracted_totals else None,
                    explanation=(
                        "Sum of source-present totals across imported document "
                        "evidence. It is not the current ERP AP balance and may "
                        "include reviewed, duplicate, paid, voided, or otherwise "
                        "non-open items."
                    ),
                ),
                **self._erp_ledger_metrics(),
                discounts_available=self._discounts_available_metric(),
                average_approval_time=self._average_approval_time_metric(),
            ),
            source_coverage=self.source_coverage(),
            governance=self.governance(),
            deferred_capabilities=self.deferred_capabilities(),
            warnings=self._common_warnings(),
        )


accounts_payable_service = AccountsPayableService()
