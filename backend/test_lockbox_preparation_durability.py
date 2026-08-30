from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import time
import unittest
import sys
from contextlib import closing
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent / "modules" / "document_intelligence"),
)

from lockbox_preparation.contracts import (
    CustomerGroupSnapshot,
    CustomerResolution,
    CustomerSnapshot,
    InvoiceOwnerEvidence,
    OpenARSnapshot,
    OpenInvoice,
    SourceTransaction,
    StartPreparationRequest,
)
from lockbox_preparation.coordinator import (
    DurableLockboxPreparationCoordinator,
)
from lockbox_preparation.errors import (
    FullCoverageError,
    IdempotencyConflictError,
    PreparationPolicyError,
    StateTransitionError,
)
from lockbox_preparation.policy import (
    RULE_VERSION,
    assess_remittance_reconciliation,
    disambiguate_remittance_rows,
    effective_invoice,
    find_unique_due_date_bucket_match,
    normalize_invoice,
    recommend_allocation,
    validate_application,
)
from lockbox_preparation.repository import (
    LockboxPreparationRepository,
)
from lockbox_preparation.reason_codes import (
    CLASSIFIER_VERSION,
    build_exception_summary,
    classify_exception,
)
from lockbox_preparation.states import (
    FileState,
    TransactionState,
)


class FakeReadOnlyProvider:
    def __init__(
        self,
        *,
        failed_transactions: set[str] | None = None,
        delay_seconds: float = 0.0,
        concurrency_gate_size: int = 0,
    ) -> None:
        self.failed_transactions = failed_transactions or set()
        self.delay_seconds = delay_seconds
        self.concurrency_gate_size = concurrency_gate_size
        self.resolve_calls = 0
        self.invoice_owner_calls = 0
        self.customer_load_calls = 0
        self.open_ar_load_calls = 0
        self.current_reads = 0
        self.maximum_reads = 0
        self.last_invoice_numbers = ()
        self._lock = threading.Lock()
        self._concurrency_gate = threading.Event()

    def resolve_invoice_owners(self, invoice_numbers):
        self.invoice_owner_calls += 1
        self.last_invoice_numbers = tuple(invoice_numbers)
        return {
            invoice: InvoiceOwnerEvidence(
                invoice_number=invoice,
                customer_numbers=("520459",),
                source_reference="fake-read-only-erp",
            )
            for invoice in invoice_numbers
        }

    def resolve_customer(self, transaction, invoice_owners):
        with self._lock:
            self.resolve_calls += 1
            self.current_reads += 1
            self.maximum_reads = max(
                self.maximum_reads,
                self.current_reads,
            )
            if (
                self.concurrency_gate_size
                and self.current_reads >= self.concurrency_gate_size
            ):
                self._concurrency_gate.set()
        try:
            if self.concurrency_gate_size:
                self._concurrency_gate.wait(timeout=5)
            if self.delay_seconds:
                time.sleep(self.delay_seconds)
            if transaction.transaction_id in self.failed_transactions:
                raise RuntimeError("simulated read failure")
            return CustomerResolution(
                status="resolved",
                customer_number="520459",
                customer_snapshot={"customer_name": "Test Customer"},
                matched_on=("invoice ownership",),
                source_reference="fake-read-only-erp",
            )
        finally:
            with self._lock:
                self.current_reads -= 1

    def load_customer(self, customer_number):
        with self._lock:
            self.customer_load_calls += 1
        return CustomerSnapshot(
            customer_number=customer_number,
            fields={"customer_name": "Test Customer"},
            source_reference="fake-read-only-erp",
        )

    def load_open_ar(self, customer_number, as_of_date):
        with self._lock:
            self.open_ar_load_calls += 1
        return OpenARSnapshot(
            customer_number=customer_number,
            invoices=(
                OpenInvoice(
                    customer_number=customer_number,
                    invoice_number="520000001",
                    open_amount=Decimal("100.00"),
                    signed_source_amount=Decimal("100.00"),
                    due_date=date(2026, 7, 10),
                    raw_transaction_type="Debit",
                    source_reference="fake-read-only-erp",
                ),
            ),
            as_of_time=as_of_date.isoformat(),
            source_reference="fake-read-only-erp",
        )

    def load_customer_group(self, customer):
        return CustomerGroupSnapshot(
            matched_customer_number=customer.customer_number,
            accounts=(customer,),
            source_reference="fake-read-only-erp-customer-master",
            as_of_time="2026-07-10T08:00:00+00:00",
        )


class FakeInvoicePurchaseOrderProvider(FakeReadOnlyProvider):
    ROWS = (
        ("430620101", "00052001", "610.11"),
        ("430620102", "00052002", "720.22"),
        ("430620103", "00052003", "530.33"),
        ("430620104", "00052004", "440.44"),
        ("430620105", "00052005", "250.55"),
    )

    def load_open_ar(self, customer_number, as_of_date):
        return OpenARSnapshot(
            customer_number=customer_number,
            invoices=tuple(
                OpenInvoice(
                    customer_number=customer_number,
                    invoice_number=invoice,
                    open_amount=Decimal(amount),
                    signed_source_amount=Decimal(amount),
                    due_date=date(2026, 8, 10),
                    raw_transaction_type="Debit",
                    source_reference="fake-read-only-current-open-ar",
                    open_item_key=f"{customer_number}|Debit|{invoice}",
                )
                for invoice, _, amount in self.ROWS
            ),
            as_of_time=as_of_date.isoformat(),
            source_reference="fake-read-only-current-open-ar",
        )


class FakeCustomerConflictProvider:
    def __init__(
        self,
        *,
        current_owners_by_invoice: dict[str, set[str]],
        unavailable_customers: set[str] | None = None,
        unavailable_customer_master: set[str] | None = None,
    ) -> None:
        self.current_owners_by_invoice = current_owners_by_invoice
        self.unavailable_customers = unavailable_customers or set()
        self.unavailable_customer_master = (
            unavailable_customer_master or set()
        )
        self.open_ar_load_calls: list[str] = []

    def resolve_invoice_owners(self, invoice_numbers):
        return {
            invoice: InvoiceOwnerEvidence(
                invoice_number=invoice,
                customer_numbers=("520459", "520460"),
                source_reference="broad-read-only-erp-owner-search",
                as_of_time="2026-07-10T08:00:00+00:00",
            )
            for invoice in invoice_numbers
        }

    def resolve_customer(self, transaction, invoice_owners):
        return CustomerResolution(
            status="ambiguous",
            candidates=("520459", "520460"),
            warnings=("Broad invoice-owner evidence conflicts.",),
            source_reference="broad-read-only-erp-owner-search",
            as_of_time="2026-07-10T08:00:00+00:00",
        )

    def load_customer(self, customer_number):
        if customer_number in self.unavailable_customer_master:
            raise RuntimeError("simulated customer master outage")
        return CustomerSnapshot(
            customer_number=customer_number,
            fields={
                "customer_number": customer_number,
                "customer_name": f"Test Customer {customer_number}",
            },
            source_reference="fake-read-only-erp-customer-master",
            as_of_time="2026-07-10T08:00:00+00:00",
        )

    def load_open_ar(self, customer_number, as_of_date):
        self.open_ar_load_calls.append(customer_number)
        if customer_number in self.unavailable_customers:
            raise RuntimeError("simulated current open AR outage")
        invoices = tuple(
            OpenInvoice(
                customer_number=customer_number,
                invoice_number=invoice_number,
                open_amount=Decimal("100.00"),
                signed_source_amount=Decimal("100.00"),
                due_date=as_of_date,
                raw_transaction_type="Debit",
                source_reference=(
                    "fake-read-only-erp-current-open-ar;"
                    f"customer={customer_number};"
                    f"invoice={invoice_number}"
                ),
            )
            for invoice_number, owners in (
                self.current_owners_by_invoice.items()
            )
            if customer_number in owners
        )
        return OpenARSnapshot(
            customer_number=customer_number,
            invoices=invoices,
            as_of_time=as_of_date.isoformat(),
            source_reference=(
                "fake-read-only-erp-current-open-ar;"
                f"customer={customer_number}"
            ),
        )

    def load_customer_group(self, customer):
        return CustomerGroupSnapshot(
            matched_customer_number=customer.customer_number,
            accounts=(customer,),
            source_reference="fake-read-only-erp-customer-master",
            as_of_time="2026-07-10T08:00:00+00:00",
        )


class FakeDirectCurrentOwnerProvider(FakeCustomerConflictProvider):
    def __init__(
        self,
        *,
        current_owners_by_invoice: dict[str, set[str]],
        current_read_error: bool = False,
        broad_owners_by_invoice: dict[str, set[str]] | None = None,
    ) -> None:
        super().__init__(
            current_owners_by_invoice=current_owners_by_invoice,
        )
        self.current_read_error = current_read_error
        self.broad_owners_by_invoice = broad_owners_by_invoice

    def resolve_invoice_owners(self, invoice_numbers):
        if self.broad_owners_by_invoice is None:
            return super().resolve_invoice_owners(invoice_numbers)
        return {
            invoice: InvoiceOwnerEvidence(
                invoice_number=invoice,
                customer_numbers=tuple(
                    sorted(
                        self.broad_owners_by_invoice.get(invoice, set())
                    )
                ),
                source_reference="fake-broad-owner-search",
                as_of_time="2026-08-01T08:00:00+00:00",
            )
            for invoice in invoice_numbers
        }

    def resolve_current_invoice_owners(self, invoice_numbers):
        if self.current_read_error:
            raise RuntimeError("simulated direct TMAROP outage")
        return {
            invoice: InvoiceOwnerEvidence(
                invoice_number=invoice,
                customer_numbers=tuple(
                    sorted(
                        self.current_owners_by_invoice.get(invoice, set())
                    )
                ),
                source_reference="fake-direct-tmarop-current-owner",
                as_of_time="2026-08-01T08:00:00+00:00",
            )
            for invoice in invoice_numbers
        }


class FakeEnterpriseGroupProvider:
    def __init__(
        self,
        *,
        group_customer_numbers=("520459", "520460", "700000"),
        unavailable_customers: set[str] | None = None,
        group_complete: bool = True,
        group_warnings: tuple[str, ...] = (),
        resolved_anchor: bool = False,
    ) -> None:
        self.group_customer_numbers = tuple(group_customer_numbers)
        self.unavailable_customers = unavailable_customers or set()
        self.group_complete = group_complete
        self.group_warnings = group_warnings
        self.resolved_anchor = resolved_anchor
        self.invoice_amounts = {
            "52000001": ("520459", Decimal("60.00")),
            "52000002": ("520460", Decimal("40.00")),
        }

    def resolve_invoice_owners(self, invoice_numbers):
        return {
            invoice: InvoiceOwnerEvidence(
                invoice_number=invoice,
                customer_numbers=(self.invoice_amounts[invoice][0],),
                source_reference="fake-broad-read-only-erp-owner-search",
                as_of_time="2026-07-10T08:00:00+00:00",
            )
            for invoice in invoice_numbers
        }

    def resolve_customer(self, transaction, invoice_owners):
        if self.resolved_anchor:
            return CustomerResolution(
                status="resolved",
                customer_number="520459",
                customer_snapshot={
                    "customer_number": "520459",
                    "enterprise_number": "700000",
                },
                matched_on=("simulated supported customer anchor",),
                source_reference="fake-read-only-erp-customer-match",
                as_of_time="2026-07-10T08:00:00+00:00",
            )
        return CustomerResolution(
            status="ambiguous",
            customer_snapshot={
                "customer_number": "520459",
                "customer_name": "Enterprise Tire",
                "phone": "4195551212",
                "postal_code": "45865",
                "enterprise_number": "700000",
            },
            candidates=("520459", "520460"),
            matched_on=(
                "Phone number and first five ZIP digits uniquely match one "
                "ERP customer, but conflicting invoice owners still require "
                "relationship verification.",
            ),
            warnings=("Broad invoice-owner evidence conflicts.",),
            source_reference="fake-read-only-erp-customer-match",
            as_of_time="2026-07-10T08:00:00+00:00",
        )

    def load_customer(self, customer_number):
        return CustomerSnapshot(
            customer_number=customer_number,
            fields={
                "customer_number": customer_number,
                "customer_name": f"Enterprise Tire {customer_number}",
                "phone": "4195551212",
                "postal_code": "45865",
                "enterprise_number": (
                    "0" if customer_number == "700000" else "700000"
                ),
            },
            source_reference="fake-read-only-erp-customer-master",
            as_of_time="2026-07-10T08:00:00+00:00",
        )

    def load_customer_group(self, customer):
        return CustomerGroupSnapshot(
            matched_customer_number=customer.customer_number,
            enterprise_number="700000",
            accounts=tuple(
                self.load_customer(customer_number)
                for customer_number in self.group_customer_numbers
            ),
            source_reference=(
                "fake-read-only-erp-tmcust; CUNUMENT=700000"
            ),
            as_of_time="2026-07-10T08:00:00+00:00",
            complete=self.group_complete,
            warnings=self.group_warnings,
        )

    def load_open_ar(self, customer_number, as_of_date):
        if customer_number in self.unavailable_customers:
            raise RuntimeError("simulated linked-account open AR outage")
        invoices = tuple(
            OpenInvoice(
                customer_number=owner,
                invoice_number=invoice_number,
                open_amount=amount,
                signed_source_amount=amount,
                due_date=as_of_date,
                raw_transaction_type="Debit",
                source_reference=(
                    "fake-read-only-erp-current-open-ar;"
                    f"customer={owner};invoice={invoice_number}"
                ),
            )
            for invoice_number, (owner, amount) in self.invoice_amounts.items()
            if owner == customer_number
        )
        return OpenARSnapshot(
            customer_number=customer_number,
            invoices=invoices,
            as_of_time=as_of_date.isoformat(),
            source_reference=(
                "fake-read-only-erp-current-open-ar;"
                f"customer={customer_number}"
            ),
        )


def build_request(
    count: int,
    *,
    source_job_id: str = "source-job",
    source_file_hash: str = "source-hash",
) -> StartPreparationRequest:
    return StartPreparationRequest(
        source_job_id=source_job_id,
        source_file_hash=source_file_hash,
        transactions=tuple(
            SourceTransaction(
                transaction_id=f"tx-{ordinal}",
                ordinal=ordinal,
                check_amount=Decimal("100.00"),
                extracted_invoice_numbers=("520000001",),
                original_source={
                    "transaction_id": f"tx-{ordinal}",
                    "check_amount": 100,
                },
                extraction_version="pnc-test@1",
                source_reference=f"page={ordinal}",
                source_hash=f"tx-hash-{ordinal}",
                payment_date=date(2026, 7, 10),
            )
            for ordinal in range(1, count + 1)
        ),
    )


class DurablePreparationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self.temp_directory.name) / "preparation.db"
        )

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def repository(self) -> LockboxPreparationRepository:
        return LockboxPreparationRepository(self.database_path)

    def run_customer_conflict(
        self,
        provider: FakeCustomerConflictProvider,
    ) -> dict:
        repository = self.repository()
        coordinator = DurableLockboxPreparationCoordinator(
            repository,
            provider,
            read_workers=2,
        )
        try:
            result = coordinator.start(
                build_request(1),
                background=False,
            )
            result["history"] = repository.list_events(result["job_id"])
            return result
        finally:
            coordinator.shutdown()

    def run_enterprise_group(
        self,
        provider: FakeEnterpriseGroupProvider,
    ) -> dict:
        source = build_request(1)
        source = replace(
            source,
            transactions=(
                replace(
                    source.transactions[0],
                    extracted_invoice_numbers=(
                        "52000001",
                        "52000002",
                    ),
                ),
            ),
        )
        repository = self.repository()
        coordinator = DurableLockboxPreparationCoordinator(
            repository,
            provider,
            read_workers=2,
        )
        try:
            result = coordinator.start(source, background=False)
            result["history"] = repository.list_events(result["job_id"])
            return result
        finally:
            coordinator.shutdown()

    def test_coordinator_balances_invoice_po_rows_without_mutating_source(self) -> None:
        provider = FakeInvoicePurchaseOrderProvider()
        rejected_rows = tuple(
            {
                "raw_invoice_candidates": [invoice, purchase_order],
                "net_invoice_amount": amount,
                "invoice_page": "12;1",
                "reason": "multiple_governed_invoice_candidates",
                "extraction_source": "ocr_visual_row",
                "ocr_psm": 11,
            }
            for invoice, purchase_order, amount in provider.ROWS
        )
        check_amount = sum(
            (Decimal(amount) for _, _, amount in provider.ROWS),
            Decimal("0.00"),
        )
        source = SourceTransaction(
            transaction_id="G-SYNTHETIC-ROW",
            ordinal=1,
            check_amount=check_amount,
            extracted_invoice_numbers=(),
            original_source={
                "allocations": [],
                "rejected_remittance_candidates": list(rejected_rows),
            },
            extraction_version="synthetic-row-disambiguation",
            source_reference="synthetic-source",
            source_hash="synthetic-source-hash",
            payment_date=date(2026, 8, 5),
            remittance_evidence_complete=False,
            projection_evidence={
                "boundary_rule": "next_transaction_information",
                "boundary_closed": True,
                "allocation_conflict_count": 0,
                "removed_allocation_count": 0,
                "customer_conflict_count": 0,
                "review_edits_used_as_extraction": False,
            },
        )
        request = StartPreparationRequest(
            source_job_id="synthetic-source-job",
            source_file_hash="synthetic-file-hash",
            transactions=(source,),
            job_id="synthetic-row-disambiguation-job",
        )
        repository = self.repository()
        coordinator = DurableLockboxPreparationCoordinator(
            repository,
            provider,
            read_workers=1,
        )
        try:
            result = coordinator.start(request, background=False)
            events = repository.list_events(result["job_id"])
        finally:
            coordinator.shutdown()

        self.assertEqual(result["balanced_count"], 1)
        self.assertEqual(result["exception_count"], 0)
        transaction = result["transactions"][0]
        recommendation = transaction["result"]["recommendation"]
        assessment = transaction["result"][
            "remittance_row_disambiguation_assessment"
        ]
        self.assertEqual(recommendation["method"], "exact_remittance_invoices")
        self.assertEqual(len(recommendation["allocations"]), 5)
        self.assertEqual(recommendation["difference"], "0.00")
        self.assertEqual(assessment["status"], "resolved")
        self.assertEqual(assessment["recovered_row_count"], 5)
        self.assertEqual(transaction["source"]["original_source"]["allocations"], [])
        self.assertEqual(
            len(
                transaction["source"]["original_source"][
                    "rejected_remittance_candidates"
                ]
            ),
            5,
        )
        self.assertIn(
            "remittance_rows_disambiguated",
            {event["event_type"] for event in events},
        )
        self.assertFalse(transaction["result"]["can_auto_approve"])
        self.assertFalse(transaction["result"]["erp_write_performed"])

    def test_cunument_group_exposes_cross_account_exact_invoices_for_review(
        self,
    ) -> None:
        result = self.run_enterprise_group(FakeEnterpriseGroupProvider())

        self.assertEqual(result["balanced_count"], 0)
        self.assertEqual(result["exception_count"], 1)
        transaction = result["transactions"][0]
        recommendation = transaction["result"]["recommendation"]
        group_assessment = transaction["result"][
            "enterprise_group_assessment"
        ]
        self.assertEqual(group_assessment["status"], "resolved")
        self.assertEqual(
            transaction["result"]["customer_resolution"]["customer_number"],
            "520459",
        )
        self.assertEqual(
            recommendation["method"],
            "enterprise_group_exact_remittance_review",
        )
        self.assertEqual(recommendation["suggested_total"], "100.00")
        self.assertEqual(recommendation["difference"], "0.00")
        self.assertEqual(
            transaction["exception_analysis"]["primary_reason"]["code"],
            "linked_customer_allocation_review",
        )
        self.assertEqual(
            {
                allocation["customer_number"]
                for allocation in recommendation["allocations"]
            },
            {"520459", "520460"},
        )
        self.assertFalse(transaction["result"]["can_auto_approve"])
        event_types = {event["event_type"] for event in result["history"]}
        self.assertIn("enterprise_customer_group_assessed", event_types)
        self.assertIn("enterprise_customer_group_loaded", event_types)

    def test_cunument_group_outside_candidate_keeps_customer_conflict(
        self,
    ) -> None:
        result = self.run_enterprise_group(
            FakeEnterpriseGroupProvider(
                group_customer_numbers=("520459", "700000"),
            )
        )

        transaction = result["transactions"][0]
        assessment = transaction["result"]["evidence"][
            "enterprise_group_assessment"
        ]
        self.assertEqual(assessment["status"], "ambiguous")
        self.assertEqual(
            transaction["exception_analysis"]["primary_reason"]["code"],
            "customer_conflict",
        )

    def test_cunument_linked_open_ar_failure_is_retryable(self) -> None:
        result = self.run_enterprise_group(
            FakeEnterpriseGroupProvider(
                unavailable_customers={"700000"},
            )
        )

        transaction = result["transactions"][0]
        self.assertTrue(transaction["retry_eligible"])
        self.assertEqual(
            transaction["error"]["stage"],
            "enterprise_group_open_ar",
        )
        self.assertEqual(
            transaction["exception_analysis"]["primary_reason"]["code"],
            "open_ar_unavailable",
        )
        self.assertEqual(
            transaction["result"]["evidence"]["customer_group"][
                "enterprise_number"
            ],
            "700000",
        )

    def test_incomplete_nonzero_cunument_group_never_balances(self) -> None:
        result = self.run_enterprise_group(
            FakeEnterpriseGroupProvider(
                group_customer_numbers=("520459",),
                group_complete=False,
                group_warnings=(
                    "simulated bounded group evidence is incomplete",
                ),
                resolved_anchor=True,
            )
        )

        self.assertEqual(result["balanced_count"], 0)
        self.assertEqual(result["exception_count"], 1)
        transaction = result["transactions"][0]
        self.assertEqual(
            transaction["error"]["stage"],
            "enterprise_group_evidence",
        )
        self.assertEqual(
            transaction["exception_analysis"]["primary_reason"]["code"],
            "enterprise_group_incomplete",
        )
        self.assertFalse(transaction["result"]["can_auto_approve"])

    def test_current_open_ar_uniquely_resolves_broad_owner_conflict(
        self,
    ) -> None:
        result = self.run_customer_conflict(
            FakeCustomerConflictProvider(
                current_owners_by_invoice={
                    "520000001": {"520459"},
                },
            )
        )

        self.assertEqual(result["balanced_count"], 1)
        self.assertEqual(result["exception_count"], 0)
        transaction = result["transactions"][0]
        resolution = transaction["result"]["customer_resolution"]
        assessment = transaction["result"][
            "customer_conflict_assessment"
        ]
        self.assertEqual(resolution["customer_number"], "520459")
        self.assertEqual(assessment["status"], "resolved")
        self.assertEqual(
            assessment["broad_invoice_owners"]["520000001"],
            ["520459", "520460"],
        )
        self.assertEqual(
            assessment["current_open_invoice_owners"]["520000001"],
            ["520459"],
        )
        self.assertTrue(assessment["requires_human_review"])
        self.assertFalse(transaction["result"]["can_auto_approve"])
        self.assertFalse(transaction["result"]["erp_write_performed"])
        assessment_event = next(
            event
            for event in result["history"]
            if event["event_type"] == "customer_conflict_assessed"
        )
        self.assertEqual(
            assessment_event["payload"]["assessment"]["status"],
            "resolved",
        )
        self.assertFalse(
            assessment_event["payload"]["can_auto_approve"]
        )

    def test_direct_current_owner_resolves_without_legacy_reassessment(
        self,
    ) -> None:
        result = self.run_customer_conflict(
            FakeDirectCurrentOwnerProvider(
                current_owners_by_invoice={
                    "520000001": {"520459"},
                },
            )
        )

        self.assertEqual(result["balanced_count"], 1)
        transaction = result["transactions"][0]
        assessment = transaction["result"][
            "customer_conflict_assessment"
        ]
        self.assertEqual(assessment["status"], "resolved")
        self.assertEqual(
            transaction["result"]["customer_resolution"][
                "selection_basis"
            ],
            "current_open_invoice_owner",
        )
        event_types = [event["event_type"] for event in result["history"]]
        self.assertIn("current_invoice_ownership_assessed", event_types)
        self.assertNotIn("customer_conflict_assessed", event_types)

    def test_direct_current_owner_resolves_when_broad_search_found_none(
        self,
    ) -> None:
        result = self.run_customer_conflict(
            FakeDirectCurrentOwnerProvider(
                current_owners_by_invoice={
                    "520000001": {"520459"},
                },
                broad_owners_by_invoice={"520000001": set()},
            )
        )

        self.assertEqual(result["balanced_count"], 1)
        assessment = result["transactions"][0]["result"][
            "customer_conflict_assessment"
        ]
        self.assertEqual(assessment["broad_invoice_owners"], {
            "520000001": [],
        })
        self.assertEqual(
            assessment["current_open_invoice_owners"],
            {"520000001": ["520459"]},
        )

    def test_direct_current_owner_outage_blocks_contact_fallback(
        self,
    ) -> None:
        result = self.run_customer_conflict(
            FakeDirectCurrentOwnerProvider(
                current_owners_by_invoice={},
                current_read_error=True,
            )
        )

        transaction = result["transactions"][0]
        assessment = transaction["result"]["evidence"][
            "customer_conflict_assessment"
        ]
        self.assertEqual(assessment["status"], "evidence_unavailable")
        self.assertTrue(transaction["retry_eligible"])
        self.assertEqual(
            transaction["exception_analysis"]["primary_reason"]["code"],
            "invoice_owner_evidence_incomplete",
        )
        event_types = [event["event_type"] for event in result["history"]]
        self.assertIn("current_invoice_owner_read_degraded", event_types)
        self.assertNotIn("customer_conflict_assessed", event_types)

    def test_direct_partial_current_owner_evidence_resolves_via_bucket_match(
        self,
    ) -> None:
        original = build_request(1)
        source = replace(
            original,
            transactions=(
                replace(
                    original.transactions[0],
                    extracted_invoice_numbers=(
                        "520000001",
                        "520000002",
                    ),
                ),
            ),
        )
        provider = FakeDirectCurrentOwnerProvider(
            current_owners_by_invoice={
                "520000001": {"520459"},
                "520000002": set(),
            }
        )
        repository = self.repository()
        coordinator = DurableLockboxPreparationCoordinator(
            repository,
            provider,
            read_workers=2,
        )
        try:
            result = coordinator.start(source, background=False)
        finally:
            coordinator.shutdown()

        transaction = result["transactions"][0]
        resolution = transaction["result"]["customer_resolution"]
        # Invoice-ownership evidence alone remains incomplete (one admitted
        # invoice has no current TMAROP owner), but candidate 520459 is the
        # only candidate whose own open AR has a due-date bucket that
        # exactly matches the check amount - that unique dollar match is
        # itself strong enough independent evidence to resolve and balance.
        self.assertEqual(resolution["selection_basis"], "unique_open_ar_bucket_match")
        self.assertEqual(resolution["customer_number"], "520459")
        self.assertEqual(result["balanced_count"], 1)

    def test_direct_partial_current_owner_evidence_without_bucket_match_never_selects(
        self,
    ) -> None:
        original = build_request(1)
        source = replace(
            original,
            transactions=(
                replace(
                    original.transactions[0],
                    check_amount=Decimal("999.00"),
                    extracted_invoice_numbers=(
                        "520000001",
                        "520000002",
                    ),
                ),
            ),
        )
        provider = FakeDirectCurrentOwnerProvider(
            current_owners_by_invoice={
                "520000001": {"520459"},
                "520000002": set(),
            }
        )
        repository = self.repository()
        coordinator = DurableLockboxPreparationCoordinator(
            repository,
            provider,
            read_workers=2,
        )
        try:
            result = coordinator.start(source, background=False)
        finally:
            coordinator.shutdown()

        transaction = result["transactions"][0]
        assessment = transaction["result"]["evidence"][
            "customer_conflict_assessment"
        ]
        # The only candidate's open AR ($100.00) does not match this
        # check ($999.00), so there is no bucket-match tie-break evidence
        # either - the transaction correctly stays in review.
        self.assertEqual(assessment["status"], "incomplete")
        self.assertEqual(result["balanced_count"], 0)
        self.assertFalse(transaction["result"]["can_auto_approve"])

    def test_current_open_ar_split_keeps_customer_conflict(
        self,
    ) -> None:
        result = self.run_customer_conflict(
            FakeCustomerConflictProvider(
                current_owners_by_invoice={
                    "520000001": {"520459", "520460"},
                },
            )
        )

        transaction = result["transactions"][0]
        assessment = transaction["result"]["evidence"][
            "customer_conflict_assessment"
        ]
        self.assertEqual(result["exception_count"], 1)
        self.assertEqual(assessment["status"], "ambiguous")
        self.assertEqual(
            transaction["exception_analysis"]["primary_reason"]["code"],
            "customer_conflict",
        )
        self.assertFalse(transaction["retry_eligible"])

    def test_missing_current_open_invoice_keeps_customer_conflict(
        self,
    ) -> None:
        result = self.run_customer_conflict(
            FakeCustomerConflictProvider(
                current_owners_by_invoice={},
            )
        )

        transaction = result["transactions"][0]
        assessment = transaction["result"]["evidence"][
            "customer_conflict_assessment"
        ]
        self.assertEqual(result["exception_count"], 1)
        self.assertEqual(assessment["status"], "incomplete")
        self.assertEqual(
            assessment["missing_current_open_invoices"],
            ["520000001"],
        )
        self.assertFalse(transaction["retry_eligible"])

    def test_current_open_ar_outage_keeps_conflict_retryable(
        self,
    ) -> None:
        result = self.run_customer_conflict(
            FakeCustomerConflictProvider(
                current_owners_by_invoice={
                    "520000001": {"520459"},
                },
                unavailable_customers={"520460"},
            )
        )

        transaction = result["transactions"][0]
        assessment = transaction["result"]["evidence"][
            "customer_conflict_assessment"
        ]
        self.assertEqual(result["exception_count"], 1)
        self.assertEqual(assessment["status"], "evidence_unavailable")
        self.assertEqual(
            assessment["unavailable_customer_numbers"],
            ["520460"],
        )
        self.assertTrue(transaction["retry_eligible"])
        self.assertEqual(
            transaction["exception_analysis"]["primary_reason"]["code"],
            "invoice_owner_evidence_incomplete",
        )

    def test_resolved_conflict_evidence_survives_later_read_failure(
        self,
    ) -> None:
        result = self.run_customer_conflict(
            FakeCustomerConflictProvider(
                current_owners_by_invoice={
                    "520000001": {"520459"},
                },
                unavailable_customer_master={"520459"},
            )
        )

        transaction = result["transactions"][0]
        assessment = transaction["result"]["evidence"][
            "customer_conflict_assessment"
        ]
        self.assertEqual(result["exception_count"], 1)
        self.assertEqual(assessment["status"], "resolved")
        self.assertTrue(transaction["retry_eligible"])
        self.assertEqual(
            transaction["error"]["stage"],
            "customer_master",
        )

    def test_idempotent_start_and_four_worker_bound(self) -> None:
        repository = self.repository()
        # Two simulated ERP reads rendezvous before either may return. This
        # proves actual overlap without relying on OS scheduling or a short
        # wall-clock sleep on Windows.
        provider = FakeReadOnlyProvider(concurrency_gate_size=2)
        coordinator = DurableLockboxPreparationCoordinator(
            repository,
            provider,
            read_workers=4,
        )
        request = build_request(20)
        first = coordinator.start(request, background=True)
        second = coordinator.start(request, background=True)
        self.assertEqual(first["job_id"], second["job_id"])
        try:
            result = coordinator.wait(first["job_id"], timeout=20)
        finally:
            coordinator.shutdown()

        self.assertTrue(result["complete"])
        self.assertEqual(result["terminal_count"], 20)
        self.assertEqual(provider.resolve_calls, 20)
        self.assertLessEqual(provider.maximum_reads, 4)
        self.assertGreaterEqual(provider.maximum_reads, 2)
        self.assertEqual(provider.invoice_owner_calls, 1)
        self.assertEqual(provider.customer_load_calls, 1)
        self.assertEqual(provider.open_ar_load_calls, 1)

    def test_job_queue_hooks_fire_once_on_successful_background_run(self) -> None:
        repository = self.repository()
        queued_job_ids: list[str] = []
        completions: list[tuple[str, dict | None, BaseException | None]] = []
        completed_event = threading.Event()

        def on_job_queued(job_id: str) -> None:
            queued_job_ids.append(job_id)

        def on_job_complete(
            job_id: str,
            result: dict | None,
            error: BaseException | None,
        ) -> None:
            completions.append((job_id, result, error))
            completed_event.set()

        coordinator = DurableLockboxPreparationCoordinator(
            repository,
            FakeReadOnlyProvider(),
            on_job_queued=on_job_queued,
            on_job_complete=on_job_complete,
        )
        try:
            started = coordinator.start(build_request(1), background=True)
            job_id = started["job_id"]
            self.assertTrue(completed_event.wait(timeout=10))
        finally:
            coordinator.shutdown()

        self.assertEqual(queued_job_ids, [job_id])
        self.assertEqual(len(completions), 1)
        completed_job_id, result, error = completions[0]
        self.assertEqual(completed_job_id, job_id)
        self.assertIsNone(error)
        self.assertTrue(result["complete"])

    def test_job_queue_hooks_forward_exception_on_failed_background_run(
        self,
    ) -> None:
        repository = self.repository()
        completions: list[tuple[str, dict | None, BaseException | None]] = []
        completed_event = threading.Event()

        def on_job_complete(
            job_id: str,
            result: dict | None,
            error: BaseException | None,
        ) -> None:
            completions.append((job_id, result, error))
            completed_event.set()

        coordinator = DurableLockboxPreparationCoordinator(
            repository,
            FakeReadOnlyProvider(),
            on_job_complete=on_job_complete,
        )
        try:
            registered = repository.register(build_request(1))
            job_id = registered["job_id"]

            def failing_run_job(job_id: str, retry_exceptions: bool) -> dict:
                raise RuntimeError("simulated coordinator crash")

            coordinator._run_job = failing_run_job  # type: ignore[assignment]
            coordinator.resume(job_id, background=True)
            self.assertTrue(completed_event.wait(timeout=10))
        finally:
            coordinator.shutdown()

        self.assertEqual(len(completions), 1)
        completed_job_id, result, error = completions[0]
        self.assertEqual(completed_job_id, job_id)
        self.assertIsNone(result)
        self.assertIsInstance(error, RuntimeError)
        self.assertEqual(str(error), "simulated coordinator crash")

    def test_begin_run_preserves_complete_remittance_evidence(self) -> None:
        repository = self.repository()
        original = build_request(1)
        complete_transaction = replace(
            original.transactions[0],
            remittance_evidence_complete=True,
        )
        request = replace(
            original,
            transactions=(complete_transaction,),
        )
        registered = repository.register(request)

        claimed = repository.begin_run(registered["job_id"])

        self.assertEqual(len(claimed), 1)
        self.assertTrue(claimed[0].remittance_evidence_complete)

    def test_restart_resumes_only_remaining_98_of_125(self) -> None:
        repository = self.repository()
        registered = repository.register(build_request(125))
        job_id = registered["job_id"]
        repository.begin_run(job_id)

        for ordinal in range(1, 28):
            transaction_id = f"tx-{ordinal}"
            repository.transition_transaction(
                job_id,
                transaction_id,
                TransactionState.RESOLVING_CUSTOMER,
            )
            repository.transition_transaction(
                job_id,
                transaction_id,
                TransactionState.LOADING_OPEN_AR,
            )
            repository.transition_transaction(
                job_id,
                transaction_id,
                TransactionState.EVALUATING_ALLOCATION,
            )
            repository.transition_transaction(
                job_id,
                transaction_id,
                TransactionState.PREPARED_BALANCED,
                result={"prepared": True},
            )

        restarted_repository = LockboxPreparationRepository(
            self.database_path
        )
        provider = FakeReadOnlyProvider()
        coordinator = DurableLockboxPreparationCoordinator(
            restarted_repository,
            provider,
            read_workers=4,
            recover_on_startup=True,
        )
        self.assertEqual(coordinator.recovered_job_ids, (job_id,))
        coordinator.resume_recovered()
        try:
            result = coordinator.wait(job_id, timeout=20)
        finally:
            coordinator.shutdown()

        self.assertTrue(result["complete"])
        self.assertEqual(result["terminal_count"], 125)
        self.assertEqual(result["balanced_count"], 125)
        self.assertEqual(provider.resolve_calls, 98)
        self.assertEqual(
            restarted_repository.get_transaction(
                job_id,
                "tx-1",
            )["attempt_count"],
            1,
        )

    def test_registered_job_recovers_after_pre_executor_crash(self) -> None:
        repository = self.repository()
        registered = repository.register(build_request(3))
        job_id = registered["job_id"]

        restarted_repository = LockboxPreparationRepository(
            self.database_path
        )
        provider = FakeReadOnlyProvider()
        coordinator = DurableLockboxPreparationCoordinator(
            restarted_repository,
            provider,
            recover_on_startup=True,
        )
        self.assertEqual(coordinator.recovered_job_ids, (job_id,))
        coordinator.resume_recovered()
        result = coordinator.wait(job_id, timeout=10)
        coordinator.shutdown()

        self.assertTrue(result["complete"])
        self.assertEqual(result["terminal_count"], 3)
        self.assertEqual(provider.resolve_calls, 3)

    def test_two_repository_instances_cannot_claim_same_transaction(self) -> None:
        first_repository = self.repository()
        job_id = first_repository.register(
            build_request(1)
        )["job_id"]
        second_repository = LockboxPreparationRepository(
            self.database_path
        )

        first_claim = first_repository.begin_run(job_id)
        second_claim = second_repository.begin_run(job_id)

        self.assertEqual(
            [transaction.transaction_id for transaction in first_claim],
            ["tx-1"],
        )
        self.assertEqual(second_claim, [])
        self.assertEqual(
            second_repository.get_transaction(job_id, "tx-1")["state"],
            TransactionState.RESOLVING_CUSTOMER.value,
        )

    def test_same_count_changed_source_conflicts_with_idempotency(self) -> None:
        repository = self.repository()
        original = build_request(1)
        repository.register(original)
        changed = replace(
            original,
            transactions=(
                replace(
                    original.transactions[0],
                    check_amount=Decimal("101.00"),
                    source_hash="changed-source-hash",
                ),
            ),
        )

        with self.assertRaises(IdempotencyConflictError):
            repository.register(changed)

    def test_coordinator_uses_reconciled_remit_for_unique_residual(self) -> None:
        class ResidualProvider(FakeReadOnlyProvider):
            def load_open_ar(self, customer_number, as_of_date):
                invoices = tuple(
                    OpenInvoice(
                        customer_number=customer_number,
                        invoice_number=invoice_number,
                        open_amount=amount,
                        signed_source_amount=amount,
                        due_date=due_date,
                        raw_transaction_type="I",
                        source_reference="fake-current-open-ar",
                    )
                    for invoice_number, amount, due_date in (
                        ("520000001", Decimal("100.00"), date(2026, 6, 10)),
                        ("520000002", Decimal("197.55"), date(2026, 7, 10)),
                        ("520000003", Decimal("75.00"), date(2026, 8, 10)),
                    )
                )
                return OpenARSnapshot(
                    customer_number=customer_number,
                    invoices=invoices,
                    as_of_time=as_of_date.isoformat(),
                    source_reference="fake-current-open-ar",
                )

        transaction = SourceTransaction(
            transaction_id="tx-residual",
            ordinal=1,
            check_amount=Decimal("372.55"),
            extracted_invoice_numbers=("520000001", "520000002"),
            original_source={
                "transaction_id": "tx-residual",
                "check_amount": "372.55",
                "allocations": [
                    {
                        "invoice_number": "520000001",
                        "net_invoice_amount": "100.00",
                    },
                    {
                        "invoice_number": "520000002",
                        "net_invoice_amount": "197.55",
                    },
                ],
            },
            extraction_version="pnc-test@1",
            source_reference="synthetic-source",
            source_hash="synthetic-source-hash",
            payment_date=date(2026, 7, 10),
            remittance_evidence_complete=False,
            projection_evidence={
                "boundary_rule": "next_transaction_information",
                "boundary_closed": True,
                "allocation_conflict_count": 0,
                "removed_allocation_count": 0,
                "customer_conflict_count": 0,
                "review_edits_used_as_extraction": False,
                "remittance_evidence_complete": False,
            },
        )
        request = StartPreparationRequest(
            source_job_id="source-residual",
            source_file_hash="source-residual-hash",
            transactions=(transaction,),
        )
        repository = self.repository()
        coordinator = DurableLockboxPreparationCoordinator(
            repository,
            ResidualProvider(),
            read_workers=1,
            recover_on_startup=False,
        )
        try:
            result = coordinator.start(request, background=False)
        finally:
            coordinator.shutdown()

        self.assertEqual(result["balanced_count"], 1)
        prepared = result["transactions"][0]
        assessment = prepared["result"][
            "remittance_completion_assessment"
        ]
        recommendation = prepared["result"]["recommendation"]
        self.assertEqual(assessment["status"], "reconciled")
        self.assertEqual(
            recommendation["method"],
            "exact_remittance_plus_unique_open_item",
        )
        self.assertEqual(recommendation["difference"], "0.00")
        self.assertEqual(len(recommendation["allocations"]), 3)
        self.assertFalse(prepared["result"]["can_auto_approve"])
        self.assertFalse(prepared["result"]["erp_write_performed"])

    def test_new_rule_version_creates_append_only_preparation_generation(
        self,
    ) -> None:
        source = build_request(1)
        legacy_repository = LockboxPreparationRepository(
            self.database_path,
            rule_version="ADR-001@0.6.9+BR-LOCKBOX-001..008",
            service_version="lockbox-preparation@0.7.0-wave2-increment3a",
        )
        legacy = legacy_repository.register(source)
        legacy_history = legacy_repository.list_events(legacy["job_id"])
        changed = replace(
            source,
            transactions=(
                replace(
                    source.transactions[0],
                    extracted_invoice_numbers=("12345678",),
                ),
            ),
        )

        current_repository = self.repository()
        current = current_repository.register(changed)
        repeated = current_repository.register(changed)

        self.assertNotEqual(current["job_id"], legacy["job_id"])
        self.assertEqual(legacy["preparation_generation"], 1)
        self.assertEqual(current["preparation_generation"], 2)
        self.assertEqual(repeated["job_id"], current["job_id"])
        self.assertEqual(
            legacy_repository.list_events(legacy["job_id"]),
            legacy_history,
        )
        registration = current_repository.list_events(
            current["job_id"]
        )[0]
        self.assertEqual(
            registration["payload"]["prior_preparation_job_ids"],
            [legacy["job_id"]],
        )

        conflicting = replace(
            changed,
            transactions=(
                replace(
                    changed.transactions[0],
                    check_amount=Decimal("101.00"),
                ),
            ),
        )
        with self.assertRaises(IdempotencyConflictError):
            current_repository.register(conflicting)

    def test_increment3x_becomes_generation_eight_without_mutating_3p(
        self,
    ) -> None:
        source = build_request(1)
        first_repository = LockboxPreparationRepository(
            self.database_path,
            rule_version="ADR-001@0.6.9+BR-LOCKBOX-001..008",
            service_version="lockbox-preparation@0.7.0-wave2-increment3a",
        )
        generation_one = first_repository.register(source)

        r2_source = replace(
            source,
            transactions=(
                replace(
                    source.transactions[0],
                    preexisting_human_disposition={
                        "status": "corrected",
                        "reviewer": "preserved-reviewer",
                    },
                ),
            ),
        )
        r2_repository = LockboxPreparationRepository(
            self.database_path,
            rule_version=(
                "ADR-001@0.7.0-wave2-increment3b+"
                "BR-LOCKBOX-001..008"
            ),
            service_version=(
                "lockbox-preparation@0.7.0-wave2-increment3b-r2"
            ),
        )
        generation_two = r2_repository.register(r2_source)
        r2_transaction_before = r2_repository.get_transaction(
            generation_two["job_id"],
            "tx-1",
        )
        r2_history_before = r2_repository.list_events(
            generation_two["job_id"]
        )

        increment3c_repository = LockboxPreparationRepository(
            self.database_path,
            rule_version=(
                "ADR-001@0.7.0-wave2-increment3c+"
                "BR-LOCKBOX-001..009"
            ),
            service_version=(
                "lockbox-preparation@0.7.0-wave2-increment3c"
            ),
        )
        generation_three = increment3c_repository.register(r2_source)
        generation_three_transaction_before = (
            increment3c_repository.get_transaction(
                generation_three["job_id"],
                "tx-1",
            )
        )
        generation_three_history_before = (
            increment3c_repository.list_events(generation_three["job_id"])
        )

        increment3d_repository = LockboxPreparationRepository(
            self.database_path,
            rule_version=(
                "ADR-001@0.7.0-wave2-increment3d+"
                "BR-LOCKBOX-001..011"
            ),
            service_version=(
                "lockbox-preparation@0.7.0-wave2-increment3d"
            ),
        )
        generation_four = increment3d_repository.register(r2_source)
        generation_four_transaction_before = (
            increment3d_repository.get_transaction(
                generation_four["job_id"],
                "tx-1",
            )
        )
        generation_four_history_before = (
            increment3d_repository.list_events(generation_four["job_id"])
        )

        increment3f_repository = LockboxPreparationRepository(
            self.database_path,
            rule_version=(
                "ADR-001@0.7.0-wave2-increment3e+"
                "BR-LOCKBOX-001..013"
            ),
            service_version=(
                "lockbox-preparation@0.7.0-wave2-increment3f"
            ),
        )
        generation_five = increment3f_repository.register(r2_source)
        generation_five_transaction_before = (
            increment3f_repository.get_transaction(
                generation_five["job_id"],
                "tx-1",
            )
        )
        generation_five_history_before = (
            increment3f_repository.list_events(generation_five["job_id"])
        )

        increment3g_repository = LockboxPreparationRepository(
            self.database_path,
            rule_version=(
                "ADR-001@0.7.0-wave2-increment3g+"
                "BR-LOCKBOX-001..019"
            ),
            service_version=(
                "lockbox-preparation@0.7.0-wave2-increment3g"
            ),
        )
        generation_six = increment3g_repository.register(r2_source)
        generation_six_transaction_before = (
            increment3g_repository.get_transaction(
                generation_six["job_id"],
                "tx-1",
            )
        )
        generation_six_history_before = (
            increment3g_repository.list_events(generation_six["job_id"])
        )

        increment3p_repository = LockboxPreparationRepository(
            self.database_path,
            rule_version=(
                "ADR-001@0.7.0-wave2-increment3p+"
                "BR-LOCKBOX-001..035"
            ),
            service_version=(
                "lockbox-preparation@0.7.0-wave2-increment3p"
            ),
        )
        generation_seven = increment3p_repository.register(r2_source)
        generation_seven_transaction_before = (
            increment3p_repository.get_transaction(
                generation_seven["job_id"],
                "tx-1",
            )
        )
        generation_seven_history_before = (
            increment3p_repository.list_events(generation_seven["job_id"])
        )

        current_repository = self.repository()
        generation_eight = current_repository.register(r2_source)

        self.assertEqual(generation_one["preparation_generation"], 1)
        self.assertEqual(generation_two["preparation_generation"], 2)
        self.assertEqual(generation_three["preparation_generation"], 3)
        self.assertEqual(generation_four["preparation_generation"], 4)
        self.assertEqual(generation_five["preparation_generation"], 5)
        self.assertEqual(generation_six["preparation_generation"], 6)
        self.assertEqual(generation_seven["preparation_generation"], 7)
        self.assertEqual(generation_eight["preparation_generation"], 8)
        self.assertEqual(generation_eight["rule_version"], RULE_VERSION)
        self.assertEqual(
            r2_repository.get_transaction(
                generation_two["job_id"],
                "tx-1",
            ),
            r2_transaction_before,
        )
        self.assertEqual(
            r2_repository.list_events(generation_two["job_id"]),
            r2_history_before,
        )
        self.assertEqual(
            increment3c_repository.get_transaction(
                generation_three["job_id"],
                "tx-1",
            ),
            generation_three_transaction_before,
        )
        self.assertEqual(
            increment3c_repository.list_events(generation_three["job_id"]),
            generation_three_history_before,
        )
        self.assertEqual(
            increment3d_repository.get_transaction(
                generation_four["job_id"],
                "tx-1",
            ),
            generation_four_transaction_before,
        )
        self.assertEqual(
            increment3d_repository.list_events(generation_four["job_id"]),
            generation_four_history_before,
        )
        self.assertEqual(
            increment3f_repository.get_transaction(
                generation_five["job_id"],
                "tx-1",
            ),
            generation_five_transaction_before,
        )
        self.assertEqual(
            increment3f_repository.list_events(generation_five["job_id"]),
            generation_five_history_before,
        )
        self.assertEqual(
            increment3g_repository.get_transaction(
                generation_six["job_id"],
                "tx-1",
            ),
            generation_six_transaction_before,
        )
        self.assertEqual(
            increment3g_repository.list_events(generation_six["job_id"]),
            generation_six_history_before,
        )
        self.assertEqual(
            increment3p_repository.get_transaction(
                generation_seven["job_id"],
                "tx-1",
            ),
            generation_seven_transaction_before,
        )
        self.assertEqual(
            increment3p_repository.list_events(generation_seven["job_id"]),
            generation_seven_history_before,
        )
        registration = current_repository.list_events(
            generation_eight["job_id"]
        )[0]
        self.assertEqual(
            registration["payload"]["prior_preparation_job_ids"],
            [
                generation_one["job_id"],
                generation_two["job_id"],
                generation_three["job_id"],
                generation_four["job_id"],
                generation_five["job_id"],
                generation_six["job_id"],
                generation_seven["job_id"],
            ],
        )

    def test_v2_schema_migration_preserves_history_and_allows_new_rule(
        self,
    ) -> None:
        source = build_request(1)
        source_payload = {
            "transaction_id": "tx-1",
            "ordinal": 1,
            "check_amount": "100.00",
            "extracted_invoice_numbers": ["1234567890"],
            "original_source": {
                "transaction_id": "tx-1",
                "check_amount": 100,
            },
            "extraction_version": "pnc-test@1",
            "source_reference": "page=1",
            "source_hash": "tx-hash-1",
            "payment_date": "2026-07-10",
            "preexisting_human_disposition": {
                "status": "corrected",
                "reviewer": "test-reviewer",
            },
        }
        legacy_result = {
            "source": source_payload,
            "preserved_human_disposition": {
                "status": "corrected",
                "reviewer": "test-reviewer",
            },
        }
        legacy_rule = "ADR-001@0.6.9+BR-LOCKBOX-001..008"
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.executescript(
                """
                PRAGMA foreign_keys=ON;
                CREATE TABLE preparation_schema (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    schema_version INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE preparation_jobs (
                    job_id TEXT PRIMARY KEY,
                    source_job_id TEXT NOT NULL,
                    source_file_hash TEXT NOT NULL,
                    source_reference TEXT NOT NULL DEFAULT '',
                    correlation_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    request_fingerprint TEXT NOT NULL DEFAULT '',
                    state TEXT NOT NULL,
                    expected_count INTEGER NOT NULL,
                    terminal_count INTEGER NOT NULL DEFAULT 0,
                    balanced_count INTEGER NOT NULL DEFAULT 0,
                    exception_count INTEGER NOT NULL DEFAULT 0,
                    preserved_count INTEGER NOT NULL DEFAULT 0,
                    rule_version TEXT NOT NULL,
                    service_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    UNIQUE(source_job_id, source_file_hash)
                );
                CREATE TABLE preparation_transactions (
                    job_id TEXT NOT NULL,
                    transaction_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    state TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    retry_eligible INTEGER NOT NULL DEFAULT 0,
                    source_json TEXT NOT NULL,
                    source_hash TEXT NOT NULL DEFAULT '',
                    extraction_version TEXT NOT NULL DEFAULT 'unknown',
                    result_json TEXT,
                    error_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    PRIMARY KEY(job_id, transaction_id),
                    UNIQUE(job_id, ordinal),
                    FOREIGN KEY(job_id) REFERENCES preparation_jobs(job_id)
                        ON DELETE RESTRICT
                );
                CREATE TABLE preparation_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    transaction_id TEXT,
                    event_type TEXT NOT NULL,
                    from_state TEXT,
                    to_state TEXT,
                    payload_json TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    FOREIGN KEY(job_id) REFERENCES preparation_jobs(job_id)
                        ON DELETE RESTRICT
                );
                """
            )
            connection.execute(
                "INSERT INTO preparation_schema VALUES (1, 2, ?)",
                ("2026-07-31T12:00:00+00:00",),
            )
            connection.execute(
                """
                INSERT INTO preparation_jobs (
                    job_id, source_job_id, source_file_hash,
                    source_reference, correlation_id, idempotency_key,
                    request_fingerprint, state, expected_count,
                    terminal_count, balanced_count, exception_count,
                    preserved_count, rule_version, service_version,
                    created_at, updated_at, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "legacy-job",
                    source.source_job_id,
                    source.source_file_hash,
                    "legacy.pdf",
                    "legacy-job",
                    f"{source.source_job_id}:{source.source_file_hash}",
                    "legacy-fingerprint",
                    "complete",
                    1,
                    1,
                    0,
                    0,
                    1,
                    legacy_rule,
                    "lockbox-preparation@0.7.0-wave2-increment3a",
                    "2026-07-31T12:00:00+00:00",
                    "2026-07-31T12:01:00+00:00",
                    "2026-07-31T12:00:01+00:00",
                    "2026-07-31T12:01:00+00:00",
                ),
            )
            connection.execute(
                """
                INSERT INTO preparation_transactions (
                    job_id, transaction_id, ordinal, state, source_json,
                    source_hash, extraction_version, result_json,
                    created_at, updated_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "legacy-job",
                    "tx-1",
                    1,
                    "preexisting_human_disposition",
                    json.dumps(source_payload, sort_keys=True),
                    "tx-hash-1",
                    "pnc-test@1",
                    json.dumps(legacy_result, sort_keys=True),
                    "2026-07-31T12:00:00+00:00",
                    "2026-07-31T12:01:00+00:00",
                    "2026-07-31T12:01:00+00:00",
                ),
            )
            connection.execute(
                """
                INSERT INTO preparation_events (
                    job_id, transaction_id, event_type, from_state,
                    to_state, payload_json, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "legacy-job",
                    "tx-1",
                    "human_disposition_preserved",
                    "identified",
                    "preexisting_human_disposition",
                    json.dumps({"status": "corrected"}),
                    "2026-07-31T12:01:00+00:00",
                ),
            )

        repository = self.repository()
        migrated = repository.get_job("legacy-job")
        current = repository.register(source)

        self.assertEqual(migrated["preparation_generation"], 1)
        self.assertEqual(migrated["rule_version"], legacy_rule)
        self.assertEqual(
            migrated["transactions"][0]["result"],
            legacy_result,
        )
        self.assertEqual(
            repository.list_events("legacy-job")[0]["event_type"],
            "human_disposition_preserved",
        )
        self.assertEqual(current["preparation_generation"], 2)
        with closing(sqlite3.connect(self.database_path)) as connection:
            schema_version = connection.execute(
                "SELECT schema_version FROM preparation_schema WHERE singleton = 1"
            ).fetchone()[0]
            foreign_key_violations = connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
        self.assertEqual(schema_version, 3)
        self.assertEqual(foreign_key_violations, [])

    def test_missing_history_raises_not_found(self) -> None:
        repository = self.repository()
        with self.assertRaises(KeyError):
            repository.list_events("missing-job")

    def test_one_failure_does_not_abort_later_transactions(self) -> None:
        repository = self.repository()
        provider = FakeReadOnlyProvider(
            failed_transactions={"tx-64"},
        )
        coordinator = DurableLockboxPreparationCoordinator(
            repository,
            provider,
            read_workers=4,
        )
        result = coordinator.start(build_request(125), background=False)
        coordinator.shutdown()

        self.assertTrue(result["complete"])
        self.assertEqual(result["terminal_count"], 125)
        self.assertEqual(result["balanced_count"], 124)
        self.assertEqual(result["exception_count"], 1)
        self.assertEqual(
            repository.get_transaction(
                result["job_id"],
                "tx-64",
            )["state"],
            TransactionState.PREPARED_EXCEPTION.value,
        )
        self.assertEqual(
            repository.get_transaction(
                result["job_id"],
                "tx-125",
            )["state"],
            TransactionState.PREPARED_BALANCED.value,
        )
        failed = repository.get_transaction(result["job_id"], "tx-64")
        self.assertEqual(
            failed["error"]["reason_code"],
            "preparation_failure",
        )
        self.assertEqual(
            failed["exception_analysis"]["classifier_version"],
            CLASSIFIER_VERSION,
        )
        self.assertEqual(
            result["exception_reason_summary"]["total_exception_count"],
            1,
        )

    def test_full_coverage_and_transition_gates(self) -> None:
        repository = self.repository()
        job = repository.register(build_request(2))
        with self.assertRaises(FullCoverageError):
            repository.finalize(job["job_id"])
        with self.assertRaises(StateTransitionError):
            repository.transition_transaction(
                job["job_id"],
                "tx-1",
                TransactionState.PREPARED_BALANCED,
            )

    def test_events_are_append_only_and_separate_source_from_result(self) -> None:
        repository = self.repository()
        provider = FakeReadOnlyProvider()
        coordinator = DurableLockboxPreparationCoordinator(
            repository,
            provider,
        )
        result = coordinator.start(build_request(1), background=False)
        coordinator.shutdown()

        transaction = repository.get_transaction(
            result["job_id"],
            "tx-1",
        )
        events = repository.list_events(result["job_id"])
        event_ids = [event["event_id"] for event in events]
        transaction_event_types = [
            event["event_type"]
            for event in events
            if event["transaction_id"] == "tx-1"
        ]
        self.assertEqual(event_ids, sorted(event_ids))
        self.assertEqual(len(event_ids), len(set(event_ids)))
        self.assertEqual(
            transaction_event_types[-4:],
            [
                "transaction_claimed",
                "open_ar_load_completed",
                "allocation_evaluation_completed",
                "preparation_balanced",
            ],
        )
        self.assertEqual(
            transaction["source"]["original_source"]["check_amount"],
            100,
        )
        self.assertEqual(
            transaction["result"]["source"]["original_source"][
                "check_amount"
            ],
            100,
        )
        self.assertFalse(
            transaction["result"]["erp_write_performed"]
        )
        self.assertTrue(
            transaction["result"]["prepared_not_approved"]
        )

    def test_provider_contract_has_no_write_or_approval_surface(self) -> None:
        provider = FakeReadOnlyProvider()
        for prohibited in (
            "approve",
            "post",
            "apply",
            "write",
            "reverse",
            "delete",
        ):
            self.assertFalse(hasattr(provider, prohibited))

    def test_only_governed_invoice_values_enter_owner_resolution(self) -> None:
        repository = self.repository()
        provider = FakeReadOnlyProvider()
        coordinator = DurableLockboxPreparationCoordinator(
            repository,
            provider,
        )
        request = StartPreparationRequest(
            source_job_id="invoice-filter",
            source_file_hash="invoice-filter-hash",
            transactions=(
                SourceTransaction(
                    transaction_id="tx-filter",
                    ordinal=1,
                    check_amount=Decimal("100.00"),
                    extracted_invoice_numbers=(
                        "1234567",
                        "12345678",
                        "9999999999",
                        "520000001",
                        "1234567890",
                    ),
                    payment_date=date(2026, 7, 10),
                ),
            ),
        )
        result = coordinator.start(request, background=False)
        coordinator.shutdown()
        self.assertTrue(result["complete"])
        self.assertEqual(
            provider.last_invoice_numbers,
            ("12345678", "520000001"),
        )

    def test_existing_increment2d_exception_is_classified_on_read(self) -> None:
        repository = self.repository()
        job_id = repository.register(build_request(1))["job_id"]
        repository.begin_run(job_id)
        repository.transition_transaction(
            job_id,
            "tx-1",
            TransactionState.PREPARED_EXCEPTION,
            result={
                "customer_resolution": {
                    "status": "resolved",
                    "customer_number": "520459",
                },
                "recommendation": {
                    "status": "review_required",
                    "method": "no_exact_match",
                    "allocations": [],
                    "check_amount": "100.00",
                    "suggested_total": "0.00",
                    "difference": "100.00",
                },
                "prepared_not_approved": True,
                "can_auto_approve": False,
                "erp_write_performed": False,
            },
            error={
                "stage": "allocation",
                "message": "Allocation requires professional review.",
                "retry_eligible": False,
            },
            retry_eligible=False,
            event_type="preparation_exception",
        )
        completed = repository.finalize(job_id)

        transaction = completed["transactions"][0]
        self.assertNotIn(
            "exception_analysis",
            transaction["result"],
        )
        self.assertEqual(
            transaction["exception_analysis"]["primary_reason"]["code"],
            "customer_resolved_no_exact_allocation",
        )
        summary = completed["exception_reason_summary"]
        self.assertEqual(summary["total_exception_count"], 1)
        self.assertEqual(summary["classified_exception_count"], 1)
        self.assertEqual(summary["unclassified_exception_count"], 0)
        self.assertEqual(
            summary["by_primary_reason"][0]["code"],
            "customer_resolved_no_exact_allocation",
        )

    def test_110_saved_exceptions_classify_without_history_mutation(self) -> None:
        repository = self.repository()
        job_id = repository.register(
            build_request(
                110,
                source_job_id="increment2d-110",
                source_file_hash="increment2d-110-hash",
            )
        )["job_id"]
        repository.begin_run(job_id)
        legacy_result = {
            "customer_resolution": {
                "status": "resolved",
                "customer_number": "520459",
            },
            "recommendation": {
                "status": "review_required",
                "method": "no_exact_match",
                "allocations": [],
                "check_amount": "100.00",
                "suggested_total": "0.00",
                "difference": "100.00",
            },
            "prepared_not_approved": True,
            "can_auto_approve": False,
            "erp_write_performed": False,
        }
        legacy_error = {
            "stage": "allocation",
            "message": "Allocation requires professional review.",
            "retry_eligible": False,
        }
        for ordinal in range(1, 111):
            repository.transition_transaction(
                job_id,
                f"tx-{ordinal}",
                TransactionState.PREPARED_EXCEPTION,
                result=legacy_result,
                error=legacy_error,
                retry_eligible=False,
                event_type="preparation_exception",
            )
        repository.finalize(job_id)
        before_history = repository.list_events(job_id)

        snapshot = repository.get_job(job_id)
        after_history = repository.list_events(job_id)

        summary = snapshot["exception_reason_summary"]
        self.assertEqual(snapshot["exception_count"], 110)
        self.assertEqual(summary["total_exception_count"], 110)
        self.assertEqual(summary["classified_exception_count"], 110)
        self.assertEqual(summary["unclassified_exception_count"], 0)
        self.assertEqual(
            summary["by_primary_reason"][0]["count"],
            110,
        )
        self.assertEqual(before_history, after_history)
        self.assertNotIn(
            "exception_analysis",
            snapshot["transactions"][0]["result"],
        )


class ExceptionReasonClassificationTest(unittest.TestCase):
    def source(self, *, invoices=("520000001",)) -> dict:
        return {
            "extracted_invoice_numbers": list(invoices),
            "source_reference": "page=1",
            "extraction_version": "pnc-test@1",
        }

    def test_conflicting_customers_have_a_specific_primary_reason(self) -> None:
        analysis = classify_exception(
            state=TransactionState.PREPARED_EXCEPTION.value,
            source=self.source(),
            result={
                "evidence": {
                    "customer_resolution": {
                        "status": "ambiguous",
                        "candidates": ["520459", "520460"],
                    }
                }
            },
            error={"stage": "customer_resolution"},
        )
        self.assertEqual(
            analysis["primary_reason"]["code"],
            "customer_rank_ambiguity",
        )
        self.assertFalse(analysis["can_auto_approve"])
        self.assertFalse(analysis["erp_write_performed"])

    def test_malformed_historical_contact_count_is_safe(self) -> None:
        analysis = classify_exception(
            state=TransactionState.PREPARED_EXCEPTION.value,
            source=self.source(),
            result={
                "evidence": {
                    "customer_resolution": {
                        "status": "ambiguous",
                        "candidates": ["520459"],
                        "matching_evidence": {
                            "exact_phone_postal_match_count": "unknown",
                        },
                    }
                }
            },
            error={"stage": "customer_resolution"},
        )

        self.assertEqual(
            analysis["primary_reason"]["code"],
            "customer_candidate_unconfirmed",
        )

    def test_missing_remittance_is_contributing_evidence_gap(self) -> None:
        analysis = classify_exception(
            state=TransactionState.PREPARED_EXCEPTION.value,
            source=self.source(invoices=()),
            result={
                "customer_resolution": {
                    "status": "resolved",
                    "customer_number": "520459",
                },
                "recommendation": {
                    "status": "review_required",
                    "method": "no_exact_match",
                    "allocations": [],
                    "check_amount": "100.00",
                    "suggested_total": "0.00",
                    "difference": "100.00",
                },
            },
            error={"stage": "allocation"},
        )
        self.assertEqual(
            analysis["primary_reason"]["code"],
            "customer_resolved_no_exact_allocation",
        )
        self.assertIn(
            "ocr_or_remittance_evidence_incomplete",
            analysis["reason_codes"],
        )

    def test_multiple_exact_allocations_remain_ambiguous(self) -> None:
        analysis = classify_exception(
            state=TransactionState.PREPARED_EXCEPTION.value,
            source=self.source(),
            result={
                "customer_resolution": {"status": "resolved"},
                "recommendation": {
                    "status": "review_required",
                    "method": "ambiguous_due_date_groups",
                    "allocations": [],
                    "check_amount": "100.00",
                    "suggested_total": "0.00",
                    "difference": "100.00",
                },
            },
            error={"stage": "allocation"},
        )
        self.assertEqual(
            analysis["primary_reason"]["code"],
            "multiple_valid_allocations",
        )

    def test_nonzero_unbalanced_proposal_identifies_amount_variance(self) -> None:
        analysis = classify_exception(
            state=TransactionState.PREPARED_EXCEPTION.value,
            source=self.source(),
            result={
                "customer_resolution": {"status": "resolved"},
                "recommendation": {
                    "status": "review_required",
                    "method": "partial_candidate",
                    "allocations": [{"apply_amount": "90.00"}],
                    "check_amount": "100.00",
                    "suggested_total": "90.00",
                    "difference": "10.00",
                },
            },
            error={"stage": "allocation"},
        )
        self.assertEqual(
            analysis["primary_reason"]["code"],
            "credit_or_short_pay_variance",
        )

    def test_summary_counts_primary_and_contributing_reasons(self) -> None:
        transactions = [
            {
                "state": TransactionState.PREPARED_EXCEPTION.value,
                "source": self.source(invoices=()),
                "result": {
                    "evidence": {
                        "customer_resolution": {"status": "not_found"}
                    }
                },
                "error": {"stage": "customer_resolution"},
            },
            {
                "state": TransactionState.PREPARED_EXCEPTION.value,
                "source": self.source(),
                "result": {
                    "evidence": {
                        "customer_resolution": {"status": "ambiguous"}
                    }
                },
                "error": {"stage": "customer_resolution"},
            },
        ]
        summary = build_exception_summary(transactions)
        self.assertEqual(summary["total_exception_count"], 2)
        self.assertEqual(summary["classified_exception_count"], 2)
        self.assertEqual(
            {row["code"]: row["count"] for row in summary["by_primary_reason"]},
            {"customer_not_found": 1, "customer_conflict": 1},
        )
        self.assertEqual(
            summary["by_contributing_reason"][0]["code"],
            "ocr_or_remittance_evidence_incomplete",
        )


class AllocationPolicyTest(unittest.TestCase):
    def test_invoice_and_purchase_order_rows_resolve_from_erp_and_amount(self) -> None:
        rejected_rows = tuple(
            {
                "raw_invoice_candidates": [invoice, purchase_order],
                "net_invoice_amount": amount,
                "invoice_page": "12;1",
                "reason": "multiple_governed_invoice_candidates",
                "extraction_source": "ocr_visual_row",
                "ocr_psm": 11,
            }
            for invoice, purchase_order, amount in (
                ("430610101", "00051001", "610.11"),
                ("430610102", "00051002", "720.22"),
                ("430610103", "00051003", "530.33"),
                ("430610104", "00051004", "440.44"),
                ("430610105", "00051005", "250.55"),
            )
        )
        open_invoices = tuple(
            OpenInvoice(
                customer_number="610001",
                invoice_number=invoice,
                open_amount=Decimal(amount),
                signed_source_amount=Decimal(amount),
                due_date=date(2026, 8, 10),
                raw_transaction_type="Debit",
                source_reference="read-only-current-open-ar",
                open_item_key=f"610001|Debit|{invoice}",
            )
            for invoice, _, amount in (
                ("430610101", "00051001", "610.11"),
                ("430610102", "00051002", "720.22"),
                ("430610103", "00051003", "530.33"),
                ("430610104", "00051004", "440.44"),
                ("430610105", "00051005", "250.55"),
            )
        )

        assessment = disambiguate_remittance_rows(
            selected_customer_number="610001",
            rejected_candidates=rejected_rows,
            open_invoices=open_invoices,
        )

        self.assertEqual(assessment["status"], "resolved")
        self.assertEqual(assessment["recovered_row_count"], 5)
        self.assertEqual(assessment["unresolved_row_count"], 0)
        self.assertEqual(
            [
                row["invoice_number"]
                for row in assessment["recovered_allocations"]
            ],
            [
                "430610101",
                "430610102",
                "430610103",
                "430610104",
                "430610105",
            ],
        )
        self.assertTrue(
            all(
                row["source_rejection_preserved"]
                for row in assessment["recovered_allocations"]
            )
        )

    def test_invoice_and_purchase_order_row_with_amount_mismatch_stays_review(self) -> None:
        assessment = disambiguate_remittance_rows(
            selected_customer_number="610001",
            rejected_candidates=({
                "raw_invoice_candidates": ["430610101", "00051001"],
                "net_invoice_amount": "610.12",
                "invoice_page": "12;1",
                "reason": "multiple_governed_invoice_candidates",
            },),
            open_invoices=(
                OpenInvoice(
                    customer_number="610001",
                    invoice_number="430610101",
                    open_amount=Decimal("610.11"),
                    signed_source_amount=Decimal("610.11"),
                    due_date=date(2026, 8, 10),
                    raw_transaction_type="Debit",
                    open_item_key="610001|Debit|430610101",
                ),
            ),
        )

        self.assertEqual(assessment["status"], "not_resolved")
        self.assertEqual(assessment["recovered_row_count"], 0)
        self.assertEqual(assessment["unresolved_row_count"], 1)

    def test_two_erp_candidates_with_same_amount_remain_ambiguous(self) -> None:
        assessment = disambiguate_remittance_rows(
            selected_customer_number="610001",
            rejected_candidates=({
                "raw_invoice_candidates": ["430610101", "430610102"],
                "net_invoice_amount": "610.11",
                "invoice_page": "12;1",
                "reason": "multiple_governed_invoice_candidates",
            },),
            open_invoices=tuple(
                OpenInvoice(
                    customer_number="610001",
                    invoice_number=invoice,
                    open_amount=Decimal("610.11"),
                    signed_source_amount=Decimal("610.11"),
                    due_date=date(2026, 8, 10),
                    raw_transaction_type="Debit",
                    open_item_key=f"610001|Debit|{invoice}",
                )
                for invoice in ("430610101", "430610102")
            ),
        )

        self.assertEqual(assessment["status"], "not_resolved")
        self.assertEqual(assessment["recovered_row_count"], 0)
        self.assertEqual(assessment["unresolved_row_count"], 1)

    def test_invoice_number_boundary_is_eight_or_nine_digits(self) -> None:
        self.assertEqual(normalize_invoice("43-051-670"), "43051670")
        self.assertEqual(normalize_invoice("431-051-670"), "431051670")
        self.assertEqual(normalize_invoice("1234567890"), "")
        self.assertEqual(normalize_invoice("1234567"), "")
        self.assertEqual(normalize_invoice("9999999999"), "")

    def test_exact_july_10_group_is_selected(self) -> None:
        amounts = (
            "83.00",
            "24.00",
            "337.36",
            "162.00",
            "274.00",
            "249.00",
        )
        invoices = tuple(
            OpenInvoice(
                customer_number="520459",
                invoice_number=invoice_number,
                open_amount=Decimal(amount),
                signed_source_amount=Decimal(amount),
                due_date=date(2026, 7, 10),
                raw_transaction_type="Debit",
            )
            for invoice_number, amount in zip(
                (
                    "520199578",
                    "471068556",
                    "520200104",
                    "471074502",
                    "471075656",
                    "520200656",
                ),
                amounts,
            )
        ) + (
            OpenInvoice(
                customer_number="520459",
                invoice_number="520210001",
                open_amount=Decimal("700.00"),
                signed_source_amount=Decimal("700.00"),
                due_date=date(2026, 8, 10),
                raw_transaction_type="Debit",
            ),
        )
        recommendation = recommend_allocation(
            check_amount=Decimal("1129.36"),
            extracted_invoice_numbers=(),
            open_invoices=invoices,
        )
        self.assertEqual(
            recommendation.method,
            "same_due_date_exact_match",
        )
        self.assertEqual(len(recommendation.allocations), 6)
        self.assertEqual(
            recommendation.suggested_total,
            Decimal("1129.36"),
        )
        self.assertNotIn(
            "520210001",
            {
                allocation.invoice_number
                for allocation in recommendation.allocations
            },
        )
        self.assertFalse(recommendation.can_auto_approve)

    def test_multiple_due_date_groups_remain_ambiguous(self) -> None:
        invoices = (
            OpenInvoice(
                customer_number="1",
                invoice_number="520000001",
                open_amount=Decimal("100.00"),
                due_date=date(2026, 7, 10),
                raw_transaction_type="Debit",
            ),
            OpenInvoice(
                customer_number="1",
                invoice_number="520000002",
                open_amount=Decimal("100.00"),
                due_date=date(2026, 8, 10),
                raw_transaction_type="Debit",
            ),
        )
        recommendation = recommend_allocation(
            check_amount=Decimal("100.00"),
            extracted_invoice_numbers=(),
            open_invoices=invoices,
        )
        self.assertEqual(
            recommendation.method,
            "ambiguous_due_date_groups",
        )
        self.assertEqual(recommendation.status, "review_required")

    def test_positive_sc_open_item_exactly_completes_remittance_residual(self) -> None:
        invoices = (
            OpenInvoice(
                customer_number="430547",
                invoice_number="340004960",
                open_amount=Decimal("460.00"),
                signed_source_amount=Decimal("460.00"),
                due_date=date(2026, 6, 10),
                raw_transaction_type="I",
                open_item_key="430547|I|340004960|",
            ),
            OpenInvoice(
                customer_number="430547",
                invoice_number="431037125",
                open_amount=Decimal("249.00"),
                signed_source_amount=Decimal("249.00"),
                due_date=date(2026, 6, 10),
                raw_transaction_type="I",
                open_item_key="430547|I|431037125|",
            ),
            OpenInvoice(
                customer_number="430547",
                invoice_number="8",
                open_amount=Decimal("14.18"),
                signed_source_amount=Decimal("14.18"),
                due_date=date(2026, 7, 10),
                raw_transaction_type="SC",
                invoice_count=8,
                open_item_key="430547|SC|8|8",
            ),
        )

        recommendation = recommend_allocation(
            check_amount=Decimal("723.18"),
            extracted_invoice_numbers=("340004960", "431037125"),
            open_invoices=invoices,
            remittance_evidence_complete=True,
        )

        self.assertEqual(
            recommendation.method,
            "exact_remittance_plus_oldest_open_items",
        )
        self.assertEqual(recommendation.status, "recommended")
        self.assertEqual(recommendation.suggested_total, Decimal("723.18"))
        self.assertEqual(recommendation.difference, Decimal("0.00"))
        self.assertEqual(recommendation.allocations[-1].invoice_number, "8")
        self.assertEqual(
            recommendation.allocations[-1].allocation_kind,
            "service_charge",
        )
        self.assertEqual(recommendation.allocations[-1].business_type, "Debit")
        self.assertFalse(recommendation.can_auto_approve)

    def test_incomplete_remittance_cannot_trigger_sc_residual_completion(self) -> None:
        invoices = (
            OpenInvoice(
                customer_number="430547",
                invoice_number="340004960",
                open_amount=Decimal("460.00"),
                due_date=date(2026, 6, 10),
                raw_transaction_type="I",
            ),
            OpenInvoice(
                customer_number="430547",
                invoice_number="8",
                open_amount=Decimal("14.18"),
                due_date=date(2026, 7, 10),
                raw_transaction_type="SC",
                open_item_key="430547|SC|8|8",
            ),
        )

        recommendation = recommend_allocation(
            check_amount=Decimal("474.18"),
            extracted_invoice_numbers=("340004960",),
            open_invoices=invoices,
            remittance_evidence_complete=False,
        )

        # The remittance-gated SC-residual-completion method correctly does
        # not fire without complete remittance evidence. But the customer's
        # full open balance (this invoice plus the SC) is a unique, complete
        # due-date-group combination that exactly matches the check - that
        # does not depend on remittance completeness, so it still resolves.
        self.assertEqual(
            recommendation.method, "unique_exact_due_date_group_combination"
        )
        self.assertEqual(recommendation.status, "recommended")
        self.assertEqual(recommendation.suggested_total, Decimal("474.18"))
        self.assertEqual(recommendation.difference, Decimal("0.00"))

    def test_complete_remittance_uses_all_items_in_oldest_due_date_prefix(self) -> None:
        invoices = (
            OpenInvoice(
                customer_number="770001",
                invoice_number="431900001",
                open_amount=Decimal("100.00"),
                due_date=date(2026, 6, 10),
                raw_transaction_type="I",
            ),
            OpenInvoice(
                customer_number="770001",
                invoice_number="431900002",
                open_amount=Decimal("120.00"),
                due_date=date(2026, 7, 10),
                raw_transaction_type="I",
            ),
            OpenInvoice(
                customer_number="770001",
                invoice_number="431900003",
                open_amount=Decimal("170.00"),
                due_date=date(2026, 7, 10),
                raw_transaction_type="I",
            ),
            OpenInvoice(
                customer_number="770001",
                invoice_number="431900004",
                open_amount=Decimal("280.00"),
                due_date=date(2026, 8, 10),
                raw_transaction_type="I",
            ),
        )

        recommendation = recommend_allocation(
            check_amount=Decimal("390.00"),
            extracted_invoice_numbers=("431900001",),
            open_invoices=invoices,
            remittance_evidence_complete=True,
        )

        self.assertEqual(
            recommendation.method,
            "exact_remittance_plus_oldest_open_items",
        )
        self.assertEqual(
            [line.invoice_number for line in recommendation.allocations],
            ["431900001", "431900002", "431900003"],
        )
        self.assertEqual(recommendation.difference, Decimal("0.00"))

    def test_unique_remaining_open_item_completes_remit_residual(self) -> None:
        invoices = (
            OpenInvoice(
                customer_number="1",
                invoice_number="431000010",
                open_amount=Decimal("100.00"),
                due_date=date(2026, 6, 10),
                raw_transaction_type="I",
            ),
            OpenInvoice(
                customer_number="1",
                invoice_number="431000011",
                open_amount=Decimal("50.00"),
                due_date=date(2026, 7, 10),
                raw_transaction_type="I",
            ),
            OpenInvoice(
                customer_number="1",
                invoice_number="431000012",
                open_amount=Decimal("100.00"),
                due_date=date(2026, 8, 10),
                raw_transaction_type="I",
            ),
        )

        recommendation = recommend_allocation(
            check_amount=Decimal("200.00"),
            extracted_invoice_numbers=("431000010",),
            open_invoices=invoices,
            remittance_evidence_complete=True,
        )

        self.assertEqual(
            recommendation.method,
            "exact_remittance_plus_unique_open_item",
        )
        self.assertEqual(recommendation.status, "recommended")
        self.assertEqual(
            [line.invoice_number for line in recommendation.allocations],
            ["431000010", "431000012"],
        )
        self.assertEqual(recommendation.difference, Decimal("0.00"))
        self.assertFalse(recommendation.can_auto_approve)

    def test_unique_remaining_credit_completes_remit_residual(self) -> None:
        invoices = (
            OpenInvoice(
                customer_number="1",
                invoice_number="431000020",
                open_amount=Decimal("120.00"),
                signed_source_amount=Decimal("120.00"),
                due_date=date(2026, 6, 10),
                raw_transaction_type="I",
            ),
            OpenInvoice(
                customer_number="1",
                invoice_number="431000021",
                open_amount=Decimal("20.00"),
                signed_source_amount=Decimal("-20.00"),
                due_date=date(2026, 7, 10),
                raw_transaction_type="Credit",
            ),
            OpenInvoice(
                customer_number="1",
                invoice_number="431000022",
                open_amount=Decimal("75.00"),
                signed_source_amount=Decimal("75.00"),
                due_date=date(2026, 5, 10),
                raw_transaction_type="I",
            ),
        )

        recommendation = recommend_allocation(
            check_amount=Decimal("100.00"),
            extracted_invoice_numbers=("431000020",),
            open_invoices=invoices,
            remittance_evidence_complete=True,
        )

        self.assertEqual(
            recommendation.method,
            "exact_remittance_plus_unique_open_item",
        )
        self.assertEqual(
            [line.apply_amount for line in recommendation.allocations],
            [Decimal("120.00"), Decimal("-20.00")],
        )
        self.assertEqual(recommendation.allocations[-1].business_type, "Credit")
        self.assertEqual(recommendation.difference, Decimal("0.00"))

    def test_duplicate_remaining_residual_matches_stay_in_review(self) -> None:
        invoices = (
            OpenInvoice(
                customer_number="1",
                invoice_number="431000030",
                open_amount=Decimal("100.00"),
                due_date=date(2026, 6, 10),
                raw_transaction_type="I",
            ),
            OpenInvoice(
                customer_number="1",
                invoice_number="431000031",
                open_amount=Decimal("37.50"),
                due_date=date(2026, 7, 10),
                raw_transaction_type="I",
            ),
            OpenInvoice(
                customer_number="1",
                invoice_number="431000032",
                open_amount=Decimal("37.50"),
                due_date=date(2026, 8, 10),
                raw_transaction_type="I",
            ),
        )

        recommendation = recommend_allocation(
            check_amount=Decimal("137.50"),
            extracted_invoice_numbers=("431000030",),
            open_invoices=invoices,
            remittance_evidence_complete=True,
        )

        self.assertEqual(
            recommendation.method,
            "ambiguous_remittance_residual_open_items",
        )
        self.assertEqual(recommendation.status, "review_required")
        self.assertEqual(
            [line.invoice_number for line in recommendation.allocations],
            ["431000030"],
        )
        self.assertIn("Multiple remaining", recommendation.warnings[0])

    def test_incomplete_remit_cannot_use_unique_remaining_open_item(self) -> None:
        invoices = (
            OpenInvoice(
                customer_number="1",
                invoice_number="431000040",
                open_amount=Decimal("100.00"),
                due_date=date(2026, 6, 10),
                raw_transaction_type="I",
            ),
            OpenInvoice(
                customer_number="1",
                invoice_number="431000041",
                open_amount=Decimal("37.50"),
                due_date=date(2026, 7, 10),
                raw_transaction_type="I",
            ),
        )

        recommendation = recommend_allocation(
            check_amount=Decimal("137.50"),
            extracted_invoice_numbers=("431000040",),
            open_invoices=invoices,
            remittance_evidence_complete=False,
        )

        # The remittance-gated unique-open-item-residual method correctly
        # does not fire without complete remittance evidence. But the
        # customer's full open balance (both invoices) is a unique, complete
        # due-date-group combination that exactly matches the check - that
        # does not depend on remittance completeness, so it still resolves.
        self.assertEqual(
            recommendation.method, "unique_exact_due_date_group_combination"
        )
        self.assertEqual(recommendation.status, "recommended")
        self.assertEqual(
            sorted(
                line.invoice_number for line in recommendation.allocations
            ),
            ["431000040", "431000041"],
        )
        self.assertEqual(recommendation.difference, Decimal("0.00"))

    def test_exact_erp_reconciliation_can_resolve_stale_page_completeness(
        self,
    ) -> None:
        invoices = (
            OpenInvoice(
                customer_number="1",
                invoice_number="431000060",
                open_amount=Decimal("100.00"),
                signed_source_amount=Decimal("100.00"),
                due_date=date(2026, 6, 10),
                raw_transaction_type="I",
            ),
            OpenInvoice(
                customer_number="1",
                invoice_number="431000061",
                open_amount=Decimal("197.55"),
                signed_source_amount=Decimal("197.55"),
                due_date=date(2026, 7, 10),
                raw_transaction_type="I",
            ),
            OpenInvoice(
                customer_number="1",
                invoice_number="431000062",
                open_amount=Decimal("75.00"),
                signed_source_amount=Decimal("75.00"),
                due_date=date(2026, 8, 10),
                raw_transaction_type="I",
            ),
        )
        assessment = assess_remittance_reconciliation(
            selected_customer_number="1",
            extracted_invoice_numbers=("431000060", "431000061"),
            open_invoices=invoices,
            remittance_allocations=(
                {
                    "invoice_number": "431000060",
                    "net_invoice_amount": "100.00",
                },
                {
                    "invoice_number": "431000061",
                    "net_invoice_amount": "197.55",
                },
            ),
            projection_evidence={
                "boundary_rule": "next_transaction_information",
                "boundary_closed": True,
                "allocation_conflict_count": 0,
                "removed_allocation_count": 0,
                "customer_conflict_count": 0,
                "review_edits_used_as_extraction": False,
                "remittance_evidence_complete": False,
            },
        )

        self.assertEqual(assessment["status"], "reconciled")
        self.assertTrue(assessment["eligible_for_residual_completion"])
        recommendation = recommend_allocation(
            check_amount=Decimal("372.55"),
            extracted_invoice_numbers=("431000060", "431000061"),
            open_invoices=invoices,
            remittance_allocations=(
                {
                    "invoice_number": "431000060",
                    "net_invoice_amount": "100.00",
                },
                {
                    "invoice_number": "431000061",
                    "net_invoice_amount": "197.55",
                },
            ),
            remittance_evidence_complete=assessment[
                "eligible_for_residual_completion"
            ],
        )
        self.assertEqual(
            recommendation.method,
            "exact_remittance_plus_unique_open_item",
        )
        self.assertEqual(recommendation.difference, Decimal("0.00"))

    def test_erp_reconciliation_rejects_source_amount_or_owner_mismatch(
        self,
    ) -> None:
        invoice = OpenInvoice(
            customer_number="2",
            invoice_number="431000070",
            open_amount=Decimal("100.00"),
            signed_source_amount=Decimal("100.00"),
            due_date=date(2026, 6, 10),
            raw_transaction_type="I",
        )

        assessment = assess_remittance_reconciliation(
            selected_customer_number="1",
            extracted_invoice_numbers=("431000070",),
            open_invoices=(invoice,),
            remittance_allocations=(
                {
                    "invoice_number": "431000070",
                    "net_invoice_amount": "99.00",
                },
            ),
            projection_evidence={
                "boundary_rule": "next_transaction_information",
                "boundary_closed": True,
                "allocation_conflict_count": 0,
                "removed_allocation_count": 0,
                "customer_conflict_count": 0,
                "review_edits_used_as_extraction": False,
            },
        )

        self.assertEqual(assessment["status"], "not_reconciled")
        self.assertFalse(
            assessment["all_items_owned_by_selected_customer"]
        )
        self.assertFalse(
            assessment["source_amounts_match_full_signed_open_amounts"]
        )
        self.assertFalse(assessment["eligible_for_residual_completion"])

    def test_erp_reconciliation_rejects_review_edits_or_source_conflict(
        self,
    ) -> None:
        invoice = OpenInvoice(
            customer_number="1",
            invoice_number="431000080",
            open_amount=Decimal("100.00"),
            signed_source_amount=Decimal("100.00"),
            due_date=date(2026, 6, 10),
            raw_transaction_type="I",
        )

        assessment = assess_remittance_reconciliation(
            selected_customer_number="1",
            extracted_invoice_numbers=("431000080",),
            open_invoices=(invoice,),
            remittance_allocations=(
                {
                    "invoice_number": "431000080",
                    "net_invoice_amount": "100.00",
                },
            ),
            projection_evidence={
                "boundary_rule": "next_transaction_information",
                "boundary_closed": True,
                "allocation_conflict_count": 1,
                "removed_allocation_count": 0,
                "customer_conflict_count": 0,
                "review_edits_used_as_extraction": True,
            },
        )

        self.assertEqual(assessment["status"], "not_reconciled")
        self.assertFalse(assessment["eligible_for_residual_completion"])

    def test_cross_customer_residual_item_is_never_selected(self) -> None:
        invoices = (
            OpenInvoice(
                customer_number="1",
                invoice_number="431000050",
                open_amount=Decimal("100.00"),
                due_date=date(2026, 6, 10),
                raw_transaction_type="I",
            ),
            OpenInvoice(
                customer_number="2",
                invoice_number="431000051",
                open_amount=Decimal("37.50"),
                due_date=date(2026, 7, 10),
                raw_transaction_type="I",
            ),
        )

        recommendation = recommend_allocation(
            check_amount=Decimal("137.50"),
            extracted_invoice_numbers=("431000050",),
            open_invoices=invoices,
            remittance_evidence_complete=True,
        )

        self.assertEqual(recommendation.method, "partial_exact_remittance")
        self.assertEqual(recommendation.status, "review_required")
        self.assertEqual(
            [line.customer_number for line in recommendation.allocations],
            ["1"],
        )

    def test_complete_signed_open_balance_includes_credit_and_sc(self) -> None:
        invoices = (
            OpenInvoice(
                customer_number="1",
                invoice_number="431100001",
                open_amount=Decimal("150.00"),
                signed_source_amount=Decimal("150.00"),
                due_date=date(2026, 6, 10),
                raw_transaction_type="I",
            ),
            OpenInvoice(
                customer_number="1",
                invoice_number="431100002",
                open_amount=Decimal("20.00"),
                signed_source_amount=Decimal("-20.00"),
                due_date=date(2026, 6, 10),
                raw_transaction_type="C",
            ),
            OpenInvoice(
                customer_number="1",
                invoice_number="5",
                open_amount=Decimal("10.00"),
                signed_source_amount=Decimal("10.00"),
                due_date=date(2026, 7, 10),
                raw_transaction_type="SC",
                invoice_count=5,
                open_item_key="1|SC|5|5",
            ),
        )

        recommendation = recommend_allocation(
            check_amount=Decimal("140.00"),
            extracted_invoice_numbers=(),
            open_invoices=invoices,
        )

        self.assertEqual(recommendation.method, "exact_total_open_balance")
        self.assertEqual(recommendation.difference, Decimal("0.00"))
        self.assertEqual(len(recommendation.allocations), 3)
        self.assertEqual(recommendation.allocations[1].apply_amount, Decimal("-20.00"))
        self.assertEqual(recommendation.allocations[2].allocation_kind, "service_charge")

    def test_one_exact_signed_aging_bucket_is_selected(self) -> None:
        invoices = (
            OpenInvoice(
                customer_number="1",
                invoice_number="431200001",
                open_amount=Decimal("125.00"),
                due_date=date(2026, 6, 10),
                raw_transaction_type="I",
                aging_bucket="31-60",
            ),
            OpenInvoice(
                customer_number="1",
                invoice_number="431200002",
                open_amount=Decimal("75.00"),
                due_date=date(2026, 7, 10),
                raw_transaction_type="I",
                aging_bucket="31-60",
            ),
            OpenInvoice(
                customer_number="1",
                invoice_number="431200003",
                open_amount=Decimal("40.00"),
                due_date=date(2026, 8, 10),
                raw_transaction_type="I",
                aging_bucket="CURRENT",
            ),
        )

        recommendation = recommend_allocation(
            check_amount=Decimal("200.00"),
            extracted_invoice_numbers=(),
            open_invoices=invoices,
        )

        self.assertEqual(recommendation.method, "exact_aging_bucket_match")
        self.assertEqual(
            [line.invoice_number for line in recommendation.allocations],
            ["431200001", "431200002"],
        )

    def test_multiple_exact_aging_buckets_remain_review(self) -> None:
        invoices = (
            OpenInvoice(
                customer_number="1",
                invoice_number="431210001",
                open_amount=Decimal("100.00"),
                due_date=date(2026, 5, 10),
                raw_transaction_type="I",
                aging_bucket="31-60",
            ),
            OpenInvoice(
                customer_number="1",
                invoice_number="431210002",
                open_amount=Decimal("100.00"),
                due_date=date(2026, 6, 10),
                raw_transaction_type="I",
                aging_bucket="61-90",
            ),
            OpenInvoice(
                customer_number="1",
                invoice_number="431210003",
                open_amount=Decimal("50.00"),
                due_date=date(2026, 7, 10),
                raw_transaction_type="I",
                aging_bucket="CURRENT",
            ),
        )

        recommendation = recommend_allocation(
            check_amount=Decimal("100.00"),
            extracted_invoice_numbers=(),
            open_invoices=invoices,
        )

        self.assertEqual(
            recommendation.method,
            "ambiguous_aging_bucket_matches",
        )
        self.assertEqual(recommendation.status, "review_required")
        self.assertFalse(recommendation.allocations)

    def test_unique_oldest_open_item_prefix_is_selected(self) -> None:
        invoices = (
            OpenInvoice(
                customer_number="1",
                invoice_number="431300001",
                open_amount=Decimal("100.00"),
                due_date=date(2026, 5, 10),
                raw_transaction_type="I",
            ),
            OpenInvoice(
                customer_number="1",
                invoice_number="431300002",
                open_amount=Decimal("50.00"),
                due_date=date(2026, 6, 10),
                raw_transaction_type="I",
            ),
            OpenInvoice(
                customer_number="1",
                invoice_number="431300003",
                open_amount=Decimal("75.00"),
                due_date=date(2026, 7, 10),
                raw_transaction_type="I",
            ),
        )

        recommendation = recommend_allocation(
            check_amount=Decimal("150.00"),
            extracted_invoice_numbers=(),
            open_invoices=invoices,
        )

        self.assertEqual(
            recommendation.method,
            "oldest_open_items_exact_match",
        )
        self.assertEqual(
            [line.invoice_number for line in recommendation.allocations],
            ["431300001", "431300002"],
        )
        self.assertEqual(recommendation.difference, Decimal("0.00"))

    def test_multiple_oldest_prefixes_remain_review(self) -> None:
        invoices = (
            OpenInvoice(
                customer_number="1",
                invoice_number="431310001",
                open_amount=Decimal("100.00"),
                due_date=date(2026, 5, 10),
                raw_transaction_type="I",
            ),
            OpenInvoice(
                customer_number="1",
                invoice_number="431310002",
                open_amount=Decimal("20.00"),
                due_date=date(2026, 5, 10),
                raw_transaction_type="I",
            ),
            OpenInvoice(
                customer_number="1",
                invoice_number="431310003",
                open_amount=Decimal("20.00"),
                signed_source_amount=Decimal("-20.00"),
                due_date=date(2026, 6, 10),
                raw_transaction_type="C",
            ),
            OpenInvoice(
                customer_number="1",
                invoice_number="431310004",
                open_amount=Decimal("50.00"),
                due_date=date(2026, 7, 10),
                raw_transaction_type="I",
            ),
        )

        recommendation = recommend_allocation(
            check_amount=Decimal("100.00"),
            extracted_invoice_numbers=(),
            open_invoices=invoices,
        )

        self.assertEqual(
            recommendation.method,
            "ambiguous_oldest_item_prefixes",
        )
        self.assertEqual(recommendation.status, "review_required")
        self.assertFalse(recommendation.allocations)

    def test_non_adjacent_due_date_groups_combine_when_oldest_prefix_finds_nothing(
        self,
    ) -> None:
        invoices = (
            OpenInvoice(
                customer_number="1",
                invoice_number="431320001",
                open_amount=Decimal("100.00"),
                due_date=date(2026, 5, 10),
                raw_transaction_type="I",
            ),
            OpenInvoice(
                customer_number="1",
                invoice_number="431320002",
                open_amount=Decimal("30.00"),
                due_date=date(2026, 6, 10),
                raw_transaction_type="I",
            ),
            OpenInvoice(
                customer_number="1",
                invoice_number="431320003",
                open_amount=Decimal("200.00"),
                due_date=date(2026, 7, 10),
                raw_transaction_type="I",
            ),
        )

        recommendation = recommend_allocation(
            check_amount=Decimal("300.00"),
            extracted_invoice_numbers=(),
            open_invoices=invoices,
        )

        # No single due-date group is $300, and no chronological
        # oldest-first prefix sums to $300 either (100, 130, 330). Only
        # the non-adjacent combination of the 5/10 and 7/10 groups does.
        self.assertEqual(
            recommendation.method,
            "unique_exact_due_date_group_combination",
        )
        self.assertEqual(
            sorted(
                line.invoice_number for line in recommendation.allocations
            ),
            ["431320001", "431320003"],
        )
        self.assertEqual(recommendation.difference, Decimal("0.00"))

    def test_find_unique_due_date_bucket_match_single_bucket(self) -> None:
        invoices = (
            OpenInvoice(
                customer_number="1",
                invoice_number="431400001",
                open_amount=Decimal("100.00"),
                due_date=date(2026, 8, 10),
                raw_transaction_type="I",
            ),
            OpenInvoice(
                customer_number="1",
                invoice_number="431400002",
                open_amount=Decimal("50.00"),
                due_date=date(2026, 9, 10),
                raw_transaction_type="I",
            ),
        )

        match = find_unique_due_date_bucket_match(
            check_amount=Decimal("100.00"),
            open_invoices=invoices,
        )

        self.assertIsNotNone(match)
        due_dates, matched_invoices = match
        self.assertEqual(due_dates, (date(2026, 8, 10),))
        self.assertEqual(
            [line.invoice_number for line in matched_invoices],
            ["431400001"],
        )

    def test_find_unique_due_date_bucket_match_combination(self) -> None:
        invoices = (
            OpenInvoice(
                customer_number="1",
                invoice_number="431400010",
                open_amount=Decimal("100.00"),
                due_date=date(2026, 8, 10),
                raw_transaction_type="I",
            ),
            OpenInvoice(
                customer_number="1",
                invoice_number="431400011",
                open_amount=Decimal("50.00"),
                due_date=date(2026, 9, 10),
                raw_transaction_type="I",
            ),
        )

        match = find_unique_due_date_bucket_match(
            check_amount=Decimal("150.00"),
            open_invoices=invoices,
        )

        self.assertIsNotNone(match)
        due_dates, matched_invoices = match
        self.assertEqual(
            sorted(due_dates),
            [date(2026, 8, 10), date(2026, 9, 10)],
        )
        self.assertEqual(
            sorted(line.invoice_number for line in matched_invoices),
            ["431400010", "431400011"],
        )

    def test_find_unique_due_date_bucket_match_returns_none_when_no_match(
        self,
    ) -> None:
        invoices = (
            OpenInvoice(
                customer_number="1",
                invoice_number="431400020",
                open_amount=Decimal("100.00"),
                due_date=date(2026, 8, 10),
                raw_transaction_type="I",
            ),
        )

        match = find_unique_due_date_bucket_match(
            check_amount=Decimal("999.00"),
            open_invoices=invoices,
        )

        self.assertIsNone(match)

    def test_find_unique_due_date_bucket_match_returns_none_when_multiple_single_buckets_match(
        self,
    ) -> None:
        invoices = (
            OpenInvoice(
                customer_number="1",
                invoice_number="431400030",
                open_amount=Decimal("100.00"),
                due_date=date(2026, 8, 10),
                raw_transaction_type="I",
            ),
            OpenInvoice(
                customer_number="1",
                invoice_number="431400031",
                open_amount=Decimal("100.00"),
                due_date=date(2026, 9, 10),
                raw_transaction_type="I",
            ),
        )

        match = find_unique_due_date_bucket_match(
            check_amount=Decimal("100.00"),
            open_invoices=invoices,
        )

        self.assertIsNone(match)

    def test_negative_debit_is_credit_and_positive_apply_is_rejected(self) -> None:
        invoice = effective_invoice(
            OpenInvoice(
                customer_number="220374",
                invoice_number="431063896",
                open_amount=Decimal("-916.00"),
                signed_source_amount=Decimal("-916.00"),
                due_date=date(2026, 7, 10),
                raw_transaction_type="Debit",
            )
        )
        self.assertEqual(invoice.business_type, "Credit")
        self.assertTrue(invoice.negative_debit_credit)
        self.assertEqual(
            invoice.effective_amount,
            Decimal("-916.00"),
        )
        with self.assertRaises(PreparationPolicyError):
            validate_application(invoice, Decimal("916.00"))

    def test_remittance_invoice_is_capped_and_one_unique_sc_closes_remainder(
        self,
    ) -> None:
        invoices = (
            OpenInvoice(
                customer_number="700001",
                invoice_number="431700001",
                open_amount=Decimal("95.00"),
                signed_source_amount=Decimal("95.00"),
                due_date=date(2026, 7, 10),
                raw_transaction_type="I",
                open_item_key="700001|I|431700001|",
            ),
            OpenInvoice(
                customer_number="700001",
                invoice_number="431700002",
                open_amount=Decimal("50.00"),
                signed_source_amount=Decimal("50.00"),
                due_date=date(2026, 7, 10),
                raw_transaction_type="I",
                open_item_key="700001|I|431700002|",
            ),
            OpenInvoice(
                customer_number="700001",
                invoice_number="17",
                open_amount=Decimal("5.00"),
                signed_source_amount=Decimal("5.00"),
                due_date=date(2026, 7, 10),
                raw_transaction_type="SC",
                invoice_count=17,
                open_item_key="700001|SC|17|17",
            ),
        )

        recommendation = recommend_allocation(
            check_amount=Decimal("150.00"),
            extracted_invoice_numbers=("431700001", "431700002"),
            open_invoices=invoices,
            remittance_allocations=(
                {
                    "invoice_number": "431700001",
                    "net_invoice_amount": "100.00",
                },
                {
                    "invoice_number": "431700002",
                    "net_invoice_amount": "50.00",
                },
            ),
            remittance_evidence_complete=True,
        )

        self.assertEqual(
            recommendation.method,
            "exact_remittance_invoice_cap_plus_service_charge",
        )
        self.assertEqual(recommendation.status, "recommended")
        self.assertEqual(recommendation.difference, Decimal("0.00"))
        self.assertEqual(
            [line.apply_amount for line in recommendation.allocations],
            [Decimal("95.00"), Decimal("50.00"), Decimal("5.00")],
        )
        self.assertEqual(
            recommendation.allocations[-1].allocation_kind,
            "service_charge",
        )
        self.assertFalse(recommendation.can_auto_approve)

    def test_multiple_matching_service_charges_remain_review(self) -> None:
        invoices = (
            OpenInvoice(
                customer_number="700001",
                invoice_number="431700001",
                open_amount=Decimal("95.00"),
                due_date=date(2026, 7, 10),
                raw_transaction_type="I",
            ),
            OpenInvoice(
                customer_number="700001",
                invoice_number="11",
                open_amount=Decimal("5.00"),
                due_date=date(2026, 7, 10),
                raw_transaction_type="SC",
                open_item_key="700001|SC|11|11",
            ),
            OpenInvoice(
                customer_number="700001",
                invoice_number="12",
                open_amount=Decimal("5.00"),
                due_date=date(2026, 7, 10),
                raw_transaction_type="SC",
                open_item_key="700001|SC|12|12",
            ),
        )

        recommendation = recommend_allocation(
            check_amount=Decimal("100.00"),
            extracted_invoice_numbers=("431700001",),
            open_invoices=invoices,
            remittance_allocations=({
                "invoice_number": "431700001",
                "net_invoice_amount": "100.00",
            },),
            remittance_evidence_complete=True,
        )

        self.assertEqual(
            recommendation.method,
            "service_charge_residual_review",
        )
        self.assertEqual(recommendation.status, "review_required")
        self.assertEqual(recommendation.difference, Decimal("5.00"))
        self.assertEqual(len(recommendation.allocations), 1)

    def test_missing_matching_service_charge_remains_review(self) -> None:
        recommendation = recommend_allocation(
            check_amount=Decimal("100.00"),
            extracted_invoice_numbers=("431700001",),
            open_invoices=(
                OpenInvoice(
                    customer_number="700001",
                    invoice_number="431700001",
                    open_amount=Decimal("95.00"),
                    due_date=date(2026, 7, 10),
                    raw_transaction_type="I",
                ),
            ),
            remittance_allocations=({
                "invoice_number": "431700001",
                "net_invoice_amount": "100.00",
            },),
            remittance_evidence_complete=True,
        )

        self.assertEqual(
            recommendation.method,
            "service_charge_residual_review",
        )
        self.assertEqual(recommendation.status, "review_required")
        self.assertEqual(recommendation.suggested_total, Decimal("95.00"))


if __name__ == "__main__":
    unittest.main()
