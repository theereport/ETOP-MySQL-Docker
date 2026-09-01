from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine

from modules.accounts_payable.erp_ledger_repository import (
    AccountsPayableErpLedgerRepository,
)
from modules.accounts_payable.repository import AccountsPayableRepository
from modules.accounts_payable.service import AccountsPayableService
from modules.accounts_payable.source import APSourceUnavailable


SOURCE_CREATED = "2026-08-01T12:00:00+00:00"
SOURCE_UPDATED = "2026-08-01T12:01:00+00:00"
SYNC_TIME = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


def _evidence(
    job_id: str,
    *,
    fields: dict | None = None,
    text: str = "",
    records: list[dict] | None = None,
    corrected_fields: dict | None = None,
    review_status: str = "pending",
    classifier_confidence: float = 0.85,
    result_updated_at: str = SOURCE_UPDATED,
    source_warning: str | None = None,
    include_result: bool = True,
) -> dict:
    job = {
        "job_id": job_id,
        "original_file_name": f"{job_id}.pdf",
        "content_type": "application/pdf",
        "document_type": "vendor_invoice",
        "status": "completed",
        "confidence": classifier_confidence,
        "created_at": SOURCE_CREATED,
        "updated_at": result_updated_at,
    }
    result = None
    if include_result:
        result = {
            "job_id": job_id,
            "classifier": "synthetic_rule_classifier",
            "classification_evidence": ["Synthetic vendor-invoice fixture"],
            "extraction": {
                "full_text": text,
                "ocr_recommended": False,
            },
            "parsed": {
                "parser": "synthetic_invoice_parser",
                "parser_version": "test-v1",
                "fields": fields or {},
                "records": records or [],
                "validation": {"errors": [], "warnings": []},
            },
            "created_at": SOURCE_UPDATED,
            "updated_at": result_updated_at,
        }
    return {
        "job": job,
        "result": result,
        "review": {
            "review": {
                "job_id": job_id,
                "status": review_status,
                "reviewer": "Synthetic Reviewer",
                "notes": "Synthetic fixture only.",
                "corrected_fields": corrected_fields or {},
                "created_at": SOURCE_UPDATED,
                "updated_at": result_updated_at,
            },
            "history": [],
        },
        "source_warning": source_warning,
    }


def _complete_fields(
    *,
    vendor_name: str = "SYNTH-VENDOR-ALPHA",
    vendor_number: str | None = "SYNTH-001",
    invoice_number: str = "SYNTH-INV-001",
    invoice_date: str = "2026-08-01",
    due_date: str = "2026-08-31",
    total: str = "100.00",
    ocr_confidence: float | None = None,
) -> dict:
    result = {
        "vendor_name": vendor_name,
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "due_date": due_date,
        "total_amount": total,
        "currency": "USD",
        "payment_terms": "Net 30",
        "purchase_order_number": "SYNTH-PO-001",
    }
    if vendor_number is not None:
        result["vendor_number"] = vendor_number
    if ocr_confidence is not None:
        result["ocr_confidence"] = ocr_confidence
    return result


class MutableSource:
    def __init__(self, items: list[dict]) -> None:
        self.items = items
        self.error: Exception | None = None

    def list_vendor_invoice_evidence(self) -> list[dict]:
        if self.error is not None:
            raise self.error
        return copy.deepcopy(self.items)


class AccountsPayableFoundationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self._temporary_directory.name) / "ap-foundation-test.db"
        )

        self.engine = create_engine(f"sqlite:///{self.database_path}")
        self.repository = AccountsPayableRepository(engine=self.engine)
        self.source = MutableSource([])
        self.service = AccountsPayableService(
            repository=self.repository,
            source=self.source,
            clock=lambda: SYNC_TIME,
            id_factory=lambda: "ap-sync-synthetic",
            erp_ledger_repository=AccountsPayableErpLedgerRepository(
                engine=self.engine
            ),
            open_ledger_scan=lambda: [],
            vendor_terms_scan=lambda: [],
            on_ledger_job_started=lambda job_id: None,
            on_ledger_job_complete=lambda job_id, result, error: None,
        )

    def tearDown(self) -> None:
        # Repository and direct-test connections are explicitly closed, so
        # Windows can remove this SQLite file without a cleanup harness.
        self.engine.dispose()
        self._temporary_directory.cleanup()

    def _sync_one(self, evidence: dict):
        self.source.items = [evidence]
        response = self.service.sync()
        listing = self.service.list_invoices(
            query=None,
            status=None,
            exception=None,
            duplicate=None,
            exception_code=None,
            limit=50,
            offset=0,
            sort_by="received_at",
            sort_order="desc",
        )
        self.assertEqual(listing.total, 1)
        return response, self.service.get_invoice(
            listing.items[0].ap_invoice_id
        )

    def test_saved_text_candidates_are_inference_and_require_review(self) -> None:
        response, detail = self._sync_one(
            _evidence(
                "synthetic-job-text",
                text=(
                    "Vendor: SYNTH-VENDOR-TEXT\n"
                    "Invoice Number: SYNTH-TEXT-01\n"
                    "Invoice Date: 08/01/2026\n"
                    "Due Date: 08/31/2026\n"
                    "Amount Due: $321.45\n"
                    "Currency: USD"
                ),
            )
        )
        self.assertEqual(response.imported_count, 1)
        self.assertEqual(detail.vendor_name, "SYNTH-VENDOR-TEXT")
        self.assertEqual(detail.invoice_number, "SYNTH-TEXT-01")
        self.assertEqual(detail.total_amount, 321.45)
        invoice_field = next(
            field
            for field in detail.extracted_fields
            if field.field_name == "invoice_number"
        )
        self.assertEqual(invoice_field.authority, "analytical_inference")
        self.assertEqual(invoice_field.rule_version, "ap-source-text-candidate.v1")
        self.assertTrue(detail.review_required)
        self.assertIn(
            "source_text_candidates_require_review",
            {item.code for item in detail.exceptions},
        )
        self.assertIsNone(detail.ocr_confidence)

    def test_missing_saved_text_remains_unavailable_not_zero_or_invented(self) -> None:
        _, detail = self._sync_one(_evidence("synthetic-job-empty"))
        self.assertIsNone(detail.vendor_name)
        self.assertIsNone(detail.vendor_number)
        self.assertIsNone(detail.invoice_number)
        self.assertIsNone(detail.invoice_date)
        self.assertIsNone(detail.total_amount)
        self.assertIsNone(detail.ocr_confidence)
        field_values = {
            field.field_name: field.normalized_value
            for field in detail.extracted_fields
        }
        self.assertIsNone(field_values["total_amount"])
        self.assertNotIn(0, field_values.values())
        codes = {item.code for item in detail.exceptions}
        self.assertIn("missing_vendor_identity", codes)
        self.assertIn("missing_invoice_number", codes)
        self.assertIn("missing_total_amount", codes)
        self.assertNotIn("source_text_candidates_require_review", codes)

    def test_review_correction_precedes_structured_without_ap_authority(self) -> None:
        _, detail = self._sync_one(
            _evidence(
                "synthetic-job-corrected",
                fields=_complete_fields(
                    vendor_name="SYNTH-STRUCTURED-VENDOR",
                    invoice_number="SYNTH-STRUCTURED-INV",
                ),
                text=(
                    "Vendor: SYNTH-TEXT-VENDOR\n"
                    "Invoice Number: SYNTH-TEXT-INV"
                ),
                corrected_fields={
                    "vendor_name": "SYNTH-CORRECTED-VENDOR",
                    "invoice_number": "SYNTH-CORRECTED-INV",
                },
                review_status="approved",
            )
        )
        self.assertEqual(detail.vendor_name, "SYNTH-CORRECTED-VENDOR")
        self.assertEqual(detail.invoice_number, "SYNTH-CORRECTED-INV")
        vendor_field = next(
            field
            for field in detail.extracted_fields
            if field.field_name == "vendor_name"
        )
        self.assertEqual(vendor_field.authority, "human_corrected_evidence")
        self.assertIn("document_extraction_review", vendor_field.source)
        self.assertEqual(detail.governance.approval_effect, "none")
        self.assertEqual(detail.governance.payment_effect, "none")
        self.assertFalse(detail.governance.automatic_approval)
        self.assertTrue(
            any(
                "not AP invoice approval" in statement
                for statement in detail.governance.statements
            )
        )

    def test_reviewer_unavailable_suppresses_machine_and_text_fallback(self) -> None:
        evidence = _evidence(
            "synthetic-job-reviewer-unavailable",
            fields=_complete_fields(invoice_number="SYNTH-MACHINE-INV"),
            text="Invoice Number: SYNTH-TEXT-INV",
            review_status="approved",
        )
        evidence["result"]["processing_run_id"] = "run-current"
        evidence["review"]["review"].update(
            {
                "processing_run_id": "run-current",
                "unavailable_fields": ["invoice_number"],
            }
        )

        _, detail = self._sync_one(evidence)

        self.assertIsNone(detail.invoice_number)
        invoice_field = next(
            field
            for field in detail.extracted_fields
            if field.field_name == "invoice_number"
        )
        self.assertIsNone(invoice_field.value)
        self.assertIsNone(invoice_field.normalized_value)
        self.assertEqual(invoice_field.validation_status, "unavailable")
        self.assertEqual(invoice_field.authority, "human_reviewed_unavailable")
        self.assertEqual(
            invoice_field.source,
            "document_extraction_review.unavailable_fields",
        )
        self.assertEqual(invoice_field.rule_version, "ap-review-unavailable.v1")
        self.assertIn(
            "missing_invoice_number",
            {item.code for item in detail.exceptions},
        )

    def test_prior_run_unavailable_does_not_suppress_current_machine_value(self) -> None:
        evidence = _evidence(
            "synthetic-job-prior-run-unavailable",
            fields=_complete_fields(invoice_number="SYNTH-CURRENT-INV"),
            review_status="approved",
        )
        evidence["result"]["processing_run_id"] = "run-current"
        evidence["review"]["review"].update(
            {
                "processing_run_id": "run-prior",
                "unavailable_fields": ["invoice_number"],
            }
        )

        _, detail = self._sync_one(evidence)

        self.assertEqual(detail.invoice_number, "SYNTH-CURRENT-INV")
        self.assertNotIn(
            "missing_invoice_number",
            {item.code for item in detail.exceptions},
        )

    def test_low_ocr_threshold_is_explicit_provisional_and_filterable(self) -> None:
        self.source.items = [
            _evidence(
                "synthetic-job-low-ocr",
                fields=_complete_fields(ocr_confidence=0.899),
                classifier_confidence=0.99,
            ),
            _evidence(
                "synthetic-job-high-ocr",
                fields=_complete_fields(
                    invoice_number="SYNTH-INV-002",
                    ocr_confidence=0.95,
                ),
                classifier_confidence=0.40,
            ),
        ]
        self.service.sync()
        ocr_review = self.service.list_invoices(
            query=None,
            status="ocr_review",
            exception=None,
            duplicate=None,
            exception_code=None,
            limit=50,
            offset=0,
            sort_by="received_at",
            sort_order="desc",
        )
        self.assertEqual(ocr_review.total, 1)
        self.assertTrue(ocr_review.items[0].ocr_review_required)
        self.assertEqual(ocr_review.items[0].ocr_confidence, 0.899)
        self.assertEqual(ocr_review.items[0].classification_confidence, 0.99)
        self.assertTrue(
            any("provisional" in item.lower() for item in ocr_review.governance.statements)
        )

    def test_repeated_identical_sync_is_database_noop(self) -> None:
        self.source.items = [
            _evidence(
                "synthetic-job-idempotent",
                fields=_complete_fields(),
            )
        ]
        first = self.service.sync()
        before = hashlib.sha256(self.database_path.read_bytes()).hexdigest()
        second = self.service.sync()
        after = hashlib.sha256(self.database_path.read_bytes()).hexdigest()
        self.assertEqual(first.imported_count, 1)
        self.assertEqual(second.imported_count, 0)
        self.assertEqual(second.updated_count, 0)
        self.assertEqual(second.unchanged_count, 1)
        self.assertEqual(second.imported_event_count, 0)
        self.assertEqual(before, after)

        connection = sqlite3.connect(self.database_path)
        try:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM ap_invoice_revisions"
                ).fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM ap_invoice_events"
                ).fetchone()[0],
                3,
            )
        finally:
            connection.close()

    def test_unsaved_default_review_timestamp_is_not_source_evidence(self) -> None:
        evidence = _evidence(
            "synthetic-job-default-review",
            fields=_complete_fields(),
        )
        review = evidence["review"]["review"]
        review.update(
            {
                "reviewer": "",
                "notes": "",
                "corrected_fields": {},
                "created_at": "2026-08-06T12:00:00+00:00",
                "updated_at": "2026-08-06T12:00:00+00:00",
            }
        )
        evidence["review"]["history"] = []
        self.source.items = [evidence]
        first = self.service.sync()

        # Existing Document Intelligence returns a newly generated default
        # timestamp when no review row exists. That synthetic timestamp must
        # not manufacture an AP evidence revision.
        evidence["review"]["review"]["created_at"] = (
            "2026-08-07T12:00:00+00:00"
        )
        evidence["review"]["review"]["updated_at"] = (
            "2026-08-07T12:00:00+00:00"
        )
        self.source.items = [evidence]
        second = self.service.sync()

        self.assertEqual(first.imported_count, 1)
        self.assertEqual(second.unchanged_count, 1)
        self.assertEqual(second.updated_count, 0)
        self.assertEqual(second.imported_event_count, 0)
        connection = sqlite3.connect(self.database_path)
        try:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM ap_invoice_revisions"
                ).fetchone()[0],
                1,
            )
        finally:
            connection.close()

    def test_changed_source_appends_revision_and_refresh_timeline(self) -> None:
        initial = _evidence(
            "synthetic-job-revision",
            fields=_complete_fields(total="100.00"),
        )
        _, first_detail = self._sync_one(initial)
        changed = _evidence(
            "synthetic-job-revision",
            fields=_complete_fields(total="125.00"),
            result_updated_at="2026-08-02T12:01:00+00:00",
        )
        self.source.items = [changed]
        result = self.service.sync()
        detail = self.service.get_invoice(first_detail.ap_invoice_id)
        self.assertEqual(result.updated_count, 1)
        self.assertEqual(detail.total_amount, 125.0)
        self.assertEqual(detail.evidence_revision_count, 2)
        self.assertNotEqual(
            detail.source_evidence_sha256,
            first_detail.source_evidence_sha256,
        )
        self.assertEqual(
            [event.event_type for event in detail.timeline].count(
                "ap_invoice_source_refreshed"
            ),
            1,
        )

        connection = sqlite3.connect(self.database_path)
        try:
            snapshots = [
                json.loads(row[0])
                for row in connection.execute(
                    """
                    SELECT snapshot_json FROM ap_invoice_revisions
                    WHERE ap_invoice_id = ? ORDER BY recorded_at, revision_id
                    """,
                    (detail.ap_invoice_id,),
                ).fetchall()
            ]
            totals = {
                next(
                    field["normalized_value"]
                    for field in snapshot["field_evidence"]
                    if field["field_name"] == "total_amount"
                )
                for snapshot in snapshots
            }
            self.assertEqual(totals, {"100.00", "125.00"})

            # Append-only is enforced by convention in the repository
            # layer (it never issues UPDATE/DELETE against this table),
            # not by a DB trigger - MySQL trigger creation needs a
            # privilege the etop account doesn't have.
        finally:
            connection.close()

    def test_duplicate_detection_requires_exact_identity_and_no_conflict(self) -> None:
        self.source.items = [
            _evidence(
                "synthetic-job-duplicate-a",
                fields=_complete_fields(total="100.00"),
            ),
            _evidence(
                "synthetic-job-duplicate-b",
                fields=_complete_fields(total="100.00"),
            ),
            _evidence(
                "synthetic-job-duplicate-conflict",
                fields=_complete_fields(total="200.00"),
            ),
            _evidence(
                "synthetic-job-other-vendor",
                fields=_complete_fields(
                    vendor_number="SYNTH-OTHER",
                    total="100.00",
                ),
            ),
        ]
        response = self.service.sync()
        self.assertEqual(response.duplicate_candidate_count, 1)
        duplicates = self.service.list_invoices(
            query=None,
            status=None,
            exception=None,
            duplicate=True,
            exception_code=None,
            limit=50,
            offset=0,
            sort_by="received_at",
            sort_order="desc",
        )
        self.assertEqual(duplicates.total, 2)
        detail = self.service.get_invoice(duplicates.items[0].ap_invoice_id)
        self.assertEqual(len(detail.duplicate_evidence), 1)
        candidate = detail.duplicate_evidence[0]
        self.assertIsNone(candidate.confidence)
        self.assertEqual(candidate.amount_corroboration, "matched")
        self.assertEqual(candidate.date_corroboration, "matched")
        self.assertIn("exact_normalized_vendor_identity", candidate.match_factors)
        self.assertTrue(detail.review_required)

    def test_sparse_exact_duplicate_retains_partial_corroboration(self) -> None:
        sparse = {
            "vendor_name": "SYNTH-SPARSE-VENDOR",
            "invoice_number": "SYNTH-SPARSE-INV",
            "invoice_date": None,
            "total_amount": None,
        }
        self.source.items = [
            _evidence("synthetic-job-sparse-a", fields=sparse),
            _evidence("synthetic-job-sparse-b", fields=sparse),
        ]
        response = self.service.sync()
        self.assertEqual(response.duplicate_candidate_count, 1)
        listing = self.service.list_invoices(
            query="SYNTH-SPARSE",
            status="review_required",
            exception=True,
            duplicate=True,
            exception_code="missing_total_amount",
            limit=1,
            offset=0,
            sort_by="vendor_name",
            sort_order="asc",
        )
        self.assertEqual(listing.total, 2)
        self.assertEqual(len(listing.items), 1)
        detail = self.service.get_invoice(listing.items[0].ap_invoice_id)
        self.assertEqual(
            detail.duplicate_evidence[0].amount_corroboration,
            "unavailable",
        )
        self.assertEqual(
            detail.duplicate_evidence[0].date_corroboration,
            "unavailable",
        )

    def test_overview_does_not_invent_ap_cash_or_approval_metrics(self) -> None:
        self.source.items = [
            _evidence(
                "synthetic-job-overview-a",
                fields=_complete_fields(total="100.00", ocr_confidence=0.98),
            ),
            _evidence(
                "synthetic-job-overview-b",
                fields=_complete_fields(
                    invoice_number="SYNTH-INV-002",
                    total="250.50",
                ),
            ),
        ]
        self.service.sync()
        overview = self.service.overview()
        self.assertEqual(overview.metrics.imported_invoice_count.value, 2)
        self.assertEqual(overview.metrics.extracted_invoice_total.value, 350.5)
        self.assertEqual(overview.metrics.extracted_invoice_total.status, "partial")
        self.assertIsNone(overview.metrics.current_ap_balance.value)
        self.assertEqual(overview.metrics.current_ap_balance.status, "unavailable")
        self.assertIsNone(overview.metrics.due_today_count.value)
        self.assertIsNone(overview.metrics.discounts_available.value)
        self.assertIsNone(overview.metrics.average_approval_time.value)
        self.assertEqual(overview.metrics.ocr_average_confidence.status, "partial")
        self.assertEqual(overview.governance.erp_access, "not_connected")
        self.assertFalse(overview.governance.erp_write)

    def test_amount_date_and_explicit_match_exceptions_use_source_facts(self) -> None:
        fields = _complete_fields(
            invoice_date="2026-08-10",
            due_date="2026-08-01",
            total="120.00",
        )
        fields.update(
            {
                "subtotal": "100.00",
                "tax": "5.00",
                "freight": "10.00",
                "discount": "0.00",
                "po_match_status": "mismatch",
                "receiving_match_status": False,
            }
        )
        _, detail = self._sync_one(
            _evidence("synthetic-job-mismatches", fields=fields)
        )
        codes = {item.code for item in detail.exceptions}
        self.assertIn("due_date_precedes_invoice_date", codes)
        self.assertIn("invoice_total_reconciliation_mismatch", codes)
        self.assertIn("purchase_order_mismatch", codes)
        self.assertIn("receiving_mismatch", codes)
        self.assertNotIn("tax_mismatch", codes)

    def test_multiple_structured_records_create_stable_distinct_objects(self) -> None:
        records = [
            _complete_fields(invoice_number="SYNTH-MULTI-001"),
            _complete_fields(invoice_number="SYNTH-MULTI-002"),
        ]
        self.source.items = [
            _evidence(
                "synthetic-job-multi",
                records=records,
                text="Invoice Number: SHOULD-NOT-BE-SHARED",
            )
        ]
        first = self.service.sync()
        self.assertEqual(first.imported_count, 2)
        listing = self.service.list_invoices(
            query="SYNTH-MULTI",
            status=None,
            exception=None,
            duplicate=None,
            exception_code=None,
            limit=50,
            offset=0,
            sort_by="invoice_date",
            sort_order="asc",
        )
        self.assertEqual(listing.total, 2)
        self.assertEqual(
            {item.source_record_index for item in listing.items},
            {0, 1},
        )
        self.assertEqual(len({item.ap_invoice_id for item in listing.items}), 2)
        self.assertNotIn(
            "SHOULD-NOT-BE-SHARED",
            {item.invoice_number for item in listing.items},
        )
        second = self.service.sync()
        self.assertEqual(second.unchanged_count, 2)

    def test_search_contract_matches_advertised_available_fields(self) -> None:
        self._sync_one(
            _evidence(
                "synthetic-job-search-contract",
                fields=_complete_fields(
                    vendor_name="SYNTH-SEARCH-VENDOR",
                    vendor_number="SYNTH-SEARCH-009",
                    invoice_number="SYNTH-SEARCH-INVOICE",
                ),
            )
        )
        advertised_queries = (
            "SYNTH-SEARCH-VENDOR",
            "SYNTH-SEARCH-009",
            "SYNTH-SEARCH-INVOICE",
            "SYNTH-PO-001",
            "synthetic-job-search-contract",
            "synthetic-job-search-contract.pdf",
        )
        for query in advertised_queries:
            with self.subTest(query=query):
                listing = self.service.list_invoices(
                    query=query,
                    status=None,
                    exception=None,
                    duplicate=None,
                    exception_code=None,
                    limit=50,
                    offset=0,
                    sort_by="received_at",
                    sort_order="desc",
                )
                self.assertEqual(listing.total, 1)

        for deferred_query in ("100.00", "2026-08-01"):
            with self.subTest(deferred_query=deferred_query):
                listing = self.service.list_invoices(
                    query=deferred_query,
                    status=None,
                    exception=None,
                    duplicate=None,
                    exception_code=None,
                    limit=50,
                    offset=0,
                    sort_by="received_at",
                    sort_order="desc",
                )
                self.assertEqual(listing.total, 0)

    def test_missing_result_is_skipped_and_disclosed(self) -> None:
        self.source.items = [
            _evidence(
                "synthetic-job-no-result",
                include_result=False,
                source_warning="Synthetic saved result is missing.",
            )
        ]
        result = self.service.sync()
        self.assertEqual(result.status, "completed_with_warnings")
        self.assertEqual(result.imported_count, 0)
        self.assertEqual(result.skipped_count, 1)
        self.assertIn("Synthetic saved result is missing.", result.warnings)

    def test_source_unavailability_is_not_an_empty_invoice_list(self) -> None:
        self.source.error = APSourceUnavailable("Synthetic source unavailable")
        with self.assertRaises(APSourceUnavailable):
            self.service.sync()
        overview = self.service.overview()
        self.assertEqual(overview.metrics.imported_invoice_count.value, 0)
        self.assertEqual(
            overview.metrics.current_ap_balance.status,
            "unavailable",
        )


if __name__ == "__main__":
    unittest.main()
