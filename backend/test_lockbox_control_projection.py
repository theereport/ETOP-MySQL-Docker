from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from modules.document_intelligence.lockbox_preparation.control_projection import (
    CONTROL_RULE_VERSION,
    CONTROL_SERVICE_VERSION,
    EXPECTED_BOUNDARY_RULE,
    FRESH_SOURCE_PROJECTION_VERSION,
    apply_control_projection,
    apply_fresh_source_projection,
    promotion_assessment,
)


def evidence(*, complete: bool = False, removed: int = 0) -> dict:
    return {
        "baseline_allocation_count": 0,
        "candidate_parsed_allocation_count": 0,
        "merged_allocation_count": 0,
        "added_allocation_count": 0,
        "removed_allocation_count": removed,
        "allocation_conflict_count": 0,
        "customer_conflict_count": 0,
        "pages_examined_count": 1,
        "boundary_rule": EXPECTED_BOUNDARY_RULE,
        "boundary_closed": True,
        "remittance_evidence_complete": complete,
        "review_edits_used_as_extraction": False,
    }


def result(
    *,
    customer: str = "",
    method: str = "no_exact_match",
    difference: str = "1.00",
    allocations: list[dict] | None = None,
    basis: str = "",
    confidence: float = 0,
    matching_evidence: dict | None = None,
) -> dict:
    default_matching_evidence: dict = {}
    if basis in {
        "exact_phone_and_zip",
        "unique_phone_zip_with_address_confirmation",
    }:
        default_matching_evidence = {
            "contact_candidate_complete": True,
            "phone_candidate_complete": True,
            "exact_phone_postal_match_count": 1,
            "exact_phone_match_count": 1,
            "failed_selection_gates": [],
        }
    elif basis in {
        "unique_exact_phone",
        "unique_phone_with_contact_confirmation",
    }:
        default_matching_evidence = {
            "phone_candidate_complete": True,
            "exact_phone_match_count": 1,
            "failed_selection_gates": [],
        }
    elif basis in {"exact_address_and_zip", "unique_exact_address_and_zip"}:
        default_matching_evidence = {
            "address_candidate_complete": True,
            "exact_address_postal_match_count": 1,
            "failed_selection_gates": [],
        }
    elif basis == "payer_supplied_customer_number":
        default_matching_evidence = {
            "payer_account_directive_verified": True,
            "payer_account_directive_conflict": False,
            "failed_selection_gates": [],
        }
    return {
        "customer_resolution": {
            "status": "resolved" if customer else "ambiguous",
            "customer_number": customer,
            "selection_basis": basis,
            "selected_confidence": confidence,
            "candidates": [customer] if customer else [],
            "matching_evidence": (
                matching_evidence
                if matching_evidence is not None
                else default_matching_evidence
            ),
        },
        "customer_snapshot": {
            "fields": {"customer_number": customer} if customer else {},
        },
        "recommendation": {
            "status": "recommended" if difference == "0.00" else "review_required",
            "method": method,
            "difference": difference,
            "allocations": allocations or [],
            "can_auto_approve": False,
        },
        "prepared_not_approved": True,
        "can_auto_approve": False,
        "erp_write_performed": False,
    }


def transaction(
    ordinal: int,
    state: str,
    transaction_result: dict,
    *,
    transaction_evidence: dict | None = None,
) -> dict:
    transaction_id = f"G-{ordinal}"
    return {
        "job_id": "job",
        "transaction_id": transaction_id,
        "ordinal": ordinal,
        "state": state,
        "source": {
            "transaction_id": transaction_id,
            "projection_evidence": transaction_evidence or evidence(),
            "original_source": {"transaction_id": transaction_id},
        },
        "result": deepcopy(transaction_result),
        "error": (
            {}
            if state == "prepared_balanced"
            else {
                "stage": "allocation",
                "message": "Professional review is required.",
                "retry_eligible": False,
            }
        ),
    }


def snapshots() -> tuple[dict, dict]:
    control_transactions = []
    candidate_transactions = []
    for ordinal in range(1, 79):
        control_balanced = ordinal <= 30
        control_result = result(
            customer="CONTROL" if control_balanced else "",
            method="exact_remittance_invoices" if control_balanced else "no_exact_match",
            difference="0.00" if control_balanced else "1.00",
            allocations=([{"apply_amount": "10.00"}] if control_balanced else []),
            basis="unique_current_open_invoice_owner" if control_balanced else "",
            confidence=1.0 if control_balanced else 0,
        )
        control_transactions.append(
            transaction(
                ordinal,
                "prepared_balanced" if control_balanced else "prepared_exception",
                control_result,
            )
        )

        candidate_balanced = ordinal <= 8 or 31 <= ordinal <= 44
        candidate_method = "same_due_date_exact_match"
        candidate_evidence = evidence()
        if ordinal == 32:
            candidate_method = "exact_remittance_plus_oldest_open_items"
            candidate_evidence = evidence(complete=False)
        candidate_result = result(
            customer=(
                "CONTROL" if ordinal <= 8
                else "CANDIDATE" if 31 <= ordinal <= 45
                else ""
            ),
            method=(candidate_method if candidate_balanced else "partial_exact_remittance" if ordinal in {33, 34} else "no_exact_match"),
            difference="0.00" if candidate_balanced else "1.00",
            allocations=([{"apply_amount": "10.00"}] if (
                ordinal <= 8 or 31 <= ordinal <= 44
            ) else []),
            basis=(
                "exact_phone_and_zip"
                if 31 <= ordinal <= 45
                else "unique_current_open_invoice_owner"
                if ordinal <= 8
                else ""
            ),
            confidence=(
                1.0 if ordinal <= 8 or 31 <= ordinal <= 45 else 0
            ),
        )
        candidate_transactions.append(
            transaction(
                ordinal,
                "prepared_balanced" if candidate_balanced else "prepared_exception",
                candidate_result,
                transaction_evidence=candidate_evidence,
            )
        )

    control = {
        "job_id": "control-job",
        "source_job_id": "source-job",
        "source_file_hash": "a" * 64,
        "state": "complete",
        "complete": True,
        "counts_final": True,
        "expected_count": 78,
        "terminal_count": 78,
        "balanced_count": 30,
        "exception_count": 48,
        "preserved_count": 0,
        "rule_version": CONTROL_RULE_VERSION,
        "service_version": CONTROL_SERVICE_VERSION,
        "transactions": control_transactions,
    }
    candidate = {
        "job_id": "candidate-job",
        "source_job_id": "source-job",
        "source_file_hash": "a" * 64,
        "state": "complete",
        "complete": True,
        "counts_final": True,
        "expected_count": 78,
        "terminal_count": 78,
        "balanced_count": 22,
        "exception_count": 56,
        "preserved_count": 0,
        "rule_version": "candidate-rule",
        "service_version": "candidate-service",
        "transactions": candidate_transactions,
    }
    return control, candidate


def fresh_snapshot(transaction_count: int = 187) -> dict:
    transactions = []
    for ordinal in range(1, transaction_count + 1):
        balanced = ordinal in {1, 2}
        matching_evidence = None
        if ordinal == 2:
            matching_evidence = {
                "contact_candidate_complete": True,
                "phone_candidate_complete": True,
                "exact_phone_postal_match_count": 2,
                "exact_phone_match_count": 2,
                "failed_selection_gates": ["duplicate_exact_phone_zip"],
            }
        transaction_result = result(
            customer="SYNTHETIC-CUSTOMER" if balanced else "",
            method=(
                "exact_total_open_balance"
                if balanced
                else "no_exact_match"
            ),
            difference="0.00" if balanced else "1.00",
            allocations=([{"apply_amount": "25.00"}] if balanced else []),
            basis="exact_phone_and_zip" if balanced else "",
            confidence=0.97 if balanced else 0,
            matching_evidence=matching_evidence,
        )
        transactions.append(
            transaction(
                ordinal,
                "prepared_balanced" if balanced else "prepared_exception",
                transaction_result,
            )
        )
    return {
        "job_id": "fresh-candidate-job",
        "source_job_id": "fresh-source-job",
        "source_file_hash": "f" * 64,
        "state": "complete",
        "complete": True,
        "counts_final": True,
        "expected_count": transaction_count,
        "terminal_count": transaction_count,
        "balanced_count": 2,
        "exception_count": transaction_count - 2,
        "preserved_count": 0,
        "rule_version": "fresh-candidate-rule",
        "service_version": "fresh-candidate-service",
        "transactions": transactions,
    }


def current_open_owner_result(
    *,
    customer: str = "CURRENT-OWNER",
    invoices: tuple[str, ...] = ("12345678", "23456789"),
    failed_selection_gates: tuple[str, ...] = (),
    partial_invoice_owner_evidence: bool = False,
    invoice_owner_conflict: bool = False,
) -> dict:
    transaction_result = result(
        customer=customer,
        method="exact_remittance_invoices",
        difference="0.00",
        allocations=[
            {
                "customer_number": customer,
                "invoice_number": invoice,
                "apply_amount": "10.00",
            }
            for invoice in invoices
        ],
        basis="unique_current_open_invoice_owner",
        confidence=1.0,
        matching_evidence={
            "valid_invoice_count": len(invoices),
            "selected_basis": "current_open_invoice_owner",
            "current_open_status": "resolved",
            "invoice_owner_conflict": invoice_owner_conflict,
            "unresolved_invoice_owner_count": (
                1 if partial_invoice_owner_evidence else 0
            ),
            "partial_invoice_owner_evidence": (
                partial_invoice_owner_evidence
            ),
            "contact_candidate_complete": True,
            "phone_candidate_complete": True,
            "address_candidate_complete": True,
            "exact_phone_postal_match_count": 0,
            "exact_phone_match_count": 0,
            "exact_address_postal_match_count": 0,
            "payer_account_directive_verified": False,
            "payer_account_directive_conflict": False,
            "failed_selection_gates": list(failed_selection_gates),
        },
    )
    transaction_result["customer_resolution"]["confidence_basis"] = (
        "unique_current_open_invoice_owner"
    )
    transaction_result["customer_conflict_assessment"] = {
        "status": "resolved",
        "customer_number": customer,
        "candidate_customer_numbers": [customer],
        "remittance_invoice_numbers": list(invoices),
        "broad_invoice_owners": {invoice: [] for invoice in invoices},
        "current_open_invoice_owners": {
            invoice: [customer] for invoice in invoices
        },
        "missing_current_open_invoices": [],
        "unavailable_customer_numbers": [],
        "current_open_ar_sources": {},
        "current_open_invoice_sources": {
            invoice: {
                "source_reference": "ERP TMAROP current open invoice ownership",
                "as_of_time": "2026-08-05T01:00:00+00:00",
            }
            for invoice in invoices
        },
        "explanation": (
            "Every admitted remittance invoice is currently open under one "
            "same ERP customer."
        ),
        "rule_version": (
            "lockbox-current-open-ar-customer-resolution@1.1.0"
        ),
        "requires_human_review": True,
        "can_auto_approve": False,
        "erp_write_performed": False,
    }
    return transaction_result


class ControlProjectionTest(unittest.TestCase):
    def test_current_open_owner_precedes_partial_broad_owner_flags(
        self,
    ) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        candidate_item["result"] = current_open_owner_result(
            invoices=("12345678", "23456789", "34567890"),
            failed_selection_gates=("partial_invoice_owner_evidence",),
            partial_invoice_owner_evidence=True,
        )

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertTrue(admitted, blockers)

    def test_current_open_owner_precedes_duplicate_contact_rank_flags(
        self,
    ) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        candidate_item["result"] = current_open_owner_result(
            failed_selection_gates=(
                "duplicate_exact_phone",
                "supporting_evidence_only",
                "existing_rank_lead_not_met",
            ),
        )
        matching = candidate_item["result"]["customer_resolution"][
            "matching_evidence"
        ]
        matching["exact_phone_match_count"] = 2

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertTrue(admitted, blockers)

    def test_current_open_owner_requires_complete_reconciled_assessment(
        self,
    ) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        base_candidate = deepcopy(candidate["transactions"][30])
        base_candidate["result"] = current_open_owner_result()

        mutations = {
            "different_selected_owner": lambda value: value["result"][
                "customer_conflict_assessment"
            ].update({"customer_number": "OTHER"}),
            "missing_current_invoice": lambda value: value["result"][
                "customer_conflict_assessment"
            ].update({"missing_current_open_invoices": ["23456789"]}),
            "duplicate_current_owner": lambda value: value["result"][
                "customer_conflict_assessment"
            ]["current_open_invoice_owners"].update(
                {"23456789": ["CURRENT-OWNER", "OTHER"]}
            ),
            "missing_source_time": lambda value: value["result"][
                "customer_conflict_assessment"
            ]["current_open_invoice_sources"]["23456789"].update(
                {"as_of_time": ""}
            ),
            "incomplete_status": lambda value: value["result"][
                "customer_resolution"
            ]["matching_evidence"].update(
                {"current_open_status": "incomplete"}
            ),
            "invoice_count_mismatch": lambda value: value["result"][
                "customer_resolution"
            ]["matching_evidence"].update({"valid_invoice_count": 3}),
            "payer_directive_conflict": lambda value: value["result"][
                "customer_resolution"
            ]["matching_evidence"].update(
                {"payer_account_directive_conflict": True}
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                candidate_item = deepcopy(base_candidate)
                mutate(candidate_item)
                admitted, blockers = promotion_assessment(
                    control_item,
                    candidate_item,
                )
                self.assertFalse(admitted)
                self.assertIn(
                    "customer_evidence_not_deterministic",
                    blockers,
                )

    def test_current_open_owner_does_not_bypass_projection_conflict(
        self,
    ) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        candidate_item["result"] = current_open_owner_result()
        candidate_item["source"]["projection_evidence"].update(
            {
                "customer_conflict_count": 1,
                "customer_conflict_fields": ["customer_phone"],
            }
        )

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertFalse(admitted)
        self.assertIn("customer_evidence_conflict", blockers)

    def test_fresh_187_item_source_gets_its_own_fail_closed_projection(
        self,
    ) -> None:
        projected = apply_fresh_source_projection(fresh_snapshot())

        self.assertEqual(projected["expected_count"], 187)
        self.assertEqual(projected["terminal_count"], 187)
        self.assertEqual(projected["balanced_count"], 1)
        self.assertEqual(projected["exception_count"], 186)
        self.assertEqual(projected["admitted_promotion_count"], 1)
        self.assertEqual(projected["blocked_promotion_count"], 1)
        self.assertEqual(projected["projection_mode"], "fresh_source_initial")
        self.assertEqual(projected["control_job_id"], "")
        self.assertEqual(
            projected["control_projection_version"],
            FRESH_SOURCE_PROJECTION_VERSION,
        )
        self.assertTrue(all(projected["projection_release_gates"].values()))
        self.assertEqual(
            projected["transactions"][0]["state"],
            "prepared_balanced",
        )
        self.assertEqual(
            projected["transactions"][1]["state"],
            "prepared_exception",
        )
        self.assertIn(
            "customer_evidence_not_deterministic",
            projected["transactions"][1]["result"]["control_projection"][
                "promotion_blockers"
            ],
        )
        self.assertFalse(projected["can_auto_approve"])
        self.assertFalse(projected["erp_write_performed"])

    def test_fresh_source_requires_exact_terminal_coverage(self) -> None:
        candidate = fresh_snapshot(3)
        candidate["transactions"].pop()

        with self.assertRaisesRegex(RuntimeError, "complete, reconciled"):
            apply_fresh_source_projection(candidate)

    def test_fresh_source_preserves_existing_exception_classification(
        self,
    ) -> None:
        candidate = fresh_snapshot(3)
        raw_exception = candidate["transactions"][2]
        raw_exception["error"] = {
            "type": "PreparationPolicyError",
            "message": "Synthetic professional-review exception.",
            "stage": "customer_resolution",
            "retry_eligible": False,
        }
        raw_exception["result"]["exception_analysis"] = {
            "classifier_version": "synthetic-classifier",
            "primary_reason": {
                "code": "customer_not_found",
                "category": "customer",
            },
            "contributing_reasons": [],
            "reason_codes": ["customer_not_found"],
            "stage": "customer_resolution",
            "retry_eligible": False,
        }
        expected_error = deepcopy(raw_exception["error"])
        expected_analysis = deepcopy(
            raw_exception["result"]["exception_analysis"]
        )

        projected = apply_fresh_source_projection(candidate)
        review_item = projected["transactions"][2]

        self.assertEqual(review_item["state"], "prepared_exception")
        self.assertEqual(review_item["error"], expected_error)
        self.assertEqual(
            review_item["result"]["exception_analysis"],
            expected_analysis,
        )
        self.assertEqual(
            review_item["result"]["control_projection"]["outcome"],
            "review_preserved",
        )
        self.assertNotEqual(
            review_item["result"]["exception_analysis"][
                "primary_reason"
            ]["code"],
            "preparation_failure",
        )

    def test_fresh_source_fails_closed_on_automatic_approval_signal(
        self,
    ) -> None:
        candidate = fresh_snapshot(3)
        candidate["transactions"][0]["result"]["can_auto_approve"] = True

        with self.assertRaisesRegex(
            RuntimeError,
            "recommendation_never_auto_approves",
        ):
            apply_fresh_source_projection(candidate)

    def test_accepted_increment3q_projection_reconstructs_43_35(self) -> None:
        control, candidate = snapshots()

        projected = apply_control_projection(control, candidate)

        self.assertEqual(projected["balanced_count"], 43)
        self.assertEqual(projected["exception_count"], 35)
        self.assertEqual(projected["admitted_promotion_count"], 13)
        self.assertEqual(projected["blocked_promotion_count"], 1)
        self.assertEqual(projected["operator_assisted_review_count"], 1)
        self.assertEqual(projected["raw_candidate_regressions_contained"], 22)
        self.assertEqual(projected["projected_regression_count"], 0)
        self.assertTrue(all(projected["projection_release_gates"].values()))

    def test_raw_candidate_regression_never_replaces_control_balance(self) -> None:
        control, candidate = snapshots()

        projected = apply_control_projection(control, candidate)
        first_regressed = projected["transactions"][8]

        self.assertEqual(first_regressed["transaction_id"], "G-9")
        self.assertEqual(first_regressed["state"], "prepared_balanced")
        self.assertEqual(
            first_regressed["result"]["control_projection"]["outcome"],
            "control_preserved",
        )

    def test_accepted_increment3q_projected_floor_is_release_gate(self) -> None:
        control, candidate = snapshots()
        candidate_item = candidate["transactions"][30]
        candidate_item["state"] = "prepared_exception"
        candidate_item["result"] = result()
        candidate["balanced_count"] = 21
        candidate["exception_count"] = 57

        with self.assertRaisesRegex(
            RuntimeError,
            "accepted_increment3q_projection_preserved",
        ):
            apply_control_projection(control, candidate)

    def test_payer_recovery_can_add_one_review_promotion(self) -> None:
        control, candidate = snapshots()
        recovered = candidate["transactions"][44]
        recovered["state"] = "prepared_balanced"
        recovered["result"]["recommendation"].update(
            {
                "status": "recommended",
                "method": "exact_remittance_invoices",
                "difference": "0.00",
                "allocations": [{"apply_amount": "10.00"}],
            }
        )
        candidate["balanced_count"] = 23
        candidate["exception_count"] = 55

        projected = apply_control_projection(control, candidate)

        self.assertEqual(projected["balanced_count"], 44)
        self.assertEqual(projected["exception_count"], 34)
        self.assertEqual(projected["admitted_promotion_count"], 14)
        self.assertEqual(projected["projected_regression_count"], 0)
        self.assertTrue(all(projected["projection_release_gates"].values()))

    def test_oldest_residual_requires_complete_remittance(self) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][31]
        candidate_item = candidate["transactions"][31]

        admitted, blockers = promotion_assessment(control_item, candidate_item)

        self.assertFalse(admitted)
        self.assertIn(
            "residual_completion_requires_complete_remittance",
            blockers,
        )

    def test_complete_oldest_residual_can_pass_strict_gate(self) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][31]
        candidate_item = deepcopy(candidate["transactions"][31])
        candidate_item["source"]["projection_evidence"] = evidence(complete=True)

        admitted, blockers = promotion_assessment(control_item, candidate_item)

        self.assertTrue(admitted, blockers)

    def test_erp_backed_invoice_po_row_can_pass_strict_gate(self) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        candidate_item["result"]["recommendation"]["method"] = (
            "exact_remittance_invoices"
        )
        selected_customer = candidate_item["result"][
            "customer_resolution"
        ]["customer_number"]
        candidate_item["result"][
            "remittance_row_disambiguation_assessment"
        ] = {
            "status": "resolved",
            "rule_version": "BR-LOCKBOX-041@0.7.0-wave2-increment3x",
            "selected_customer_number": selected_customer,
            "preserved_rejection_count": 1,
            "recovered_row_count": 1,
            "unresolved_row_count": 0,
            "recovered_total": "10.00",
            "recovered_allocations": [{
                "invoice_number": "430630101",
                "net_invoice_amount": "10.00",
                "source_rejection_preserved": True,
                "source_row_disambiguation_rule_version": (
                    "BR-LOCKBOX-041@0.7.0-wave2-increment3x"
                ),
            }],
            "row_assessments": [{
                "status": "resolved",
                "rejection_reason": "multiple_governed_invoice_candidates",
                "raw_candidate_count": 2,
                "governed_candidate_count": 2,
                "candidate_match_counts": {
                    "430630101": 1,
                    "00053001": 0,
                },
                "selected_invoice_number": "430630101",
                "selected_open_item_key": (
                    f"{selected_customer}|Debit|430630101"
                ),
            }],
            "all_rows_resolved": True,
            "original_rejections_preserved": True,
            "can_auto_approve": False,
            "erp_write_performed": False,
        }

        admitted, blockers = promotion_assessment(control_item, candidate_item)

        self.assertTrue(admitted, blockers)

    def test_two_erp_valid_row_candidates_fail_strict_gate(self) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        candidate_item["result"]["recommendation"]["method"] = (
            "exact_remittance_invoices"
        )
        selected_customer = candidate_item["result"][
            "customer_resolution"
        ]["customer_number"]
        candidate_item["result"][
            "remittance_row_disambiguation_assessment"
        ] = {
            "status": "resolved",
            "rule_version": "BR-LOCKBOX-041@0.7.0-wave2-increment3x",
            "selected_customer_number": selected_customer,
            "preserved_rejection_count": 1,
            "recovered_row_count": 1,
            "unresolved_row_count": 0,
            "recovered_total": "10.00",
            "recovered_allocations": [{
                "invoice_number": "430630101",
                "net_invoice_amount": "10.00",
                "source_rejection_preserved": True,
                "source_row_disambiguation_rule_version": (
                    "BR-LOCKBOX-041@0.7.0-wave2-increment3x"
                ),
            }],
            "row_assessments": [{
                "status": "resolved",
                "rejection_reason": "multiple_governed_invoice_candidates",
                "raw_candidate_count": 2,
                "governed_candidate_count": 2,
                "candidate_match_counts": {
                    "430630101": 1,
                    "430630102": 1,
                },
                "selected_invoice_number": "430630101",
                "selected_open_item_key": (
                    f"{selected_customer}|Debit|430630101"
                ),
            }],
            "all_rows_resolved": True,
            "original_rejections_preserved": True,
            "can_auto_approve": False,
            "erp_write_performed": False,
        }

        admitted, blockers = promotion_assessment(control_item, candidate_item)

        self.assertFalse(admitted)
        self.assertIn("remittance_row_disambiguation_not_verified", blockers)

    def test_unique_open_item_residual_requires_complete_remittance(self) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        candidate_item["result"]["recommendation"]["method"] = (
            "exact_remittance_plus_unique_open_item"
        )
        candidate_item["source"]["projection_evidence"] = evidence(
            complete=False,
        )

        admitted, blockers = promotion_assessment(control_item, candidate_item)

        self.assertFalse(admitted)
        self.assertIn(
            "residual_completion_requires_complete_remittance",
            blockers,
        )

    def test_unique_open_item_residual_can_pass_strict_gate(self) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        candidate_item["result"]["recommendation"]["method"] = (
            "exact_remittance_plus_unique_open_item"
        )
        candidate_item["source"]["projection_evidence"] = evidence(
            complete=True,
        )

        admitted, blockers = promotion_assessment(control_item, candidate_item)

        self.assertTrue(admitted, blockers)

    def test_unique_residual_accepts_full_current_erp_reconciliation(self) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        candidate_item["result"]["recommendation"]["method"] = (
            "exact_remittance_plus_unique_open_item"
        )
        candidate_item["source"]["projection_evidence"] = evidence(
            complete=False,
        )
        selected_customer = candidate_item["result"][
            "customer_resolution"
        ]["customer_number"]
        candidate_item["result"]["remittance_completion_assessment"] = {
            "status": "reconciled",
            "rule_version": "BR-LOCKBOX-040@0.7.0-wave2-increment3w",
            "selected_customer_number": selected_customer,
            "extracted_invoice_count": 12,
            "source_allocation_row_count": 12,
            "invoice_sets_equal": True,
            "one_source_amount_per_invoice": True,
            "one_current_open_item_per_invoice": True,
            "all_items_owned_by_selected_customer": True,
            "source_amounts_match_full_signed_open_amounts": True,
            "boundary_rule": EXPECTED_BOUNDARY_RULE,
            "boundary_closed": True,
            "allocation_conflict_count": 0,
            "removed_allocation_count": 0,
            "customer_conflict_count": 0,
            "review_edits_used_as_extraction": False,
            "eligible_for_residual_completion": True,
            "can_auto_approve": False,
            "erp_write_performed": False,
        }

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertTrue(admitted, blockers)

    def test_reconciliation_label_without_full_evidence_stays_blocked(self) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        candidate_item["result"]["recommendation"]["method"] = (
            "exact_remittance_plus_unique_open_item"
        )
        candidate_item["source"]["projection_evidence"] = evidence(
            complete=False,
        )
        selected_customer = candidate_item["result"][
            "customer_resolution"
        ]["customer_number"]
        candidate_item["result"]["remittance_completion_assessment"] = {
            "status": "reconciled",
            "rule_version": "BR-LOCKBOX-040@0.7.0-wave2-increment3w",
            "selected_customer_number": selected_customer,
            "extracted_invoice_count": 12,
            "source_allocation_row_count": 12,
            "invoice_sets_equal": True,
            "one_source_amount_per_invoice": True,
            "one_current_open_item_per_invoice": True,
            "all_items_owned_by_selected_customer": True,
            "source_amounts_match_full_signed_open_amounts": False,
            "boundary_rule": EXPECTED_BOUNDARY_RULE,
            "boundary_closed": True,
            "allocation_conflict_count": 0,
            "removed_allocation_count": 0,
            "customer_conflict_count": 0,
            "review_edits_used_as_extraction": False,
            "eligible_for_residual_completion": True,
            "can_auto_approve": False,
            "erp_write_performed": False,
        }

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertFalse(admitted)
        self.assertIn(
            "residual_completion_requires_complete_remittance",
            blockers,
        )

    def test_unique_exact_phone_can_promote_only_with_strict_balance(self) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        resolution = candidate_item["result"]["customer_resolution"]
        resolution["selection_basis"] = "unique_exact_phone"
        resolution["confidence_basis"] = "unique_exact_phone"
        resolution["selected_confidence"] = 0.99

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertTrue(admitted, blockers)

    def test_unique_exact_phone_below_confidence_gate_cannot_promote(
        self,
    ) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        resolution = candidate_item["result"]["customer_resolution"]
        resolution["selection_basis"] = "unique_exact_phone"
        resolution["confidence_basis"] = "unique_exact_phone"
        resolution["selected_confidence"] = 0.98

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertFalse(admitted)
        self.assertIn("customer_evidence_not_deterministic", blockers)

    def test_check_phone_number_match_can_promote(self) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        candidate_item["result"] = result(
            customer="640194",
            method="exact_remittance_invoices",
            difference="0.00",
            allocations=[{"apply_amount": "10.00"}],
            basis="check_phone_number_match",
            confidence=1.0,
            matching_evidence={
                "check_phone_number_verified": True,
                "check_phone_number_conflict": False,
                "failed_selection_gates": [],
            },
        )

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertTrue(admitted, blockers)

    def test_check_phone_number_match_with_conflict_cannot_promote(
        self,
    ) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        candidate_item["result"] = result(
            customer="640194",
            method="exact_remittance_invoices",
            difference="0.00",
            allocations=[{"apply_amount": "10.00"}],
            basis="check_phone_number_match",
            confidence=1.0,
            matching_evidence={
                "check_phone_number_verified": True,
                "check_phone_number_conflict": True,
                "failed_selection_gates": [],
            },
        )

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertFalse(admitted)
        self.assertIn("customer_evidence_not_deterministic", blockers)

    def test_learned_payer_bank_account_mapping_can_promote(self) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        candidate_item["result"] = result(
            customer="640194",
            method="exact_remittance_invoices",
            difference="0.00",
            allocations=[{"apply_amount": "10.00"}],
            basis="learned_payer_bank_account_mapping",
            confidence=1.0,
            matching_evidence={
                "learned_payer_bank_account_verified": True,
                "learned_payer_bank_account_conflict": False,
                "failed_selection_gates": [],
            },
        )

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertTrue(admitted, blockers)

    def test_learned_payer_bank_account_mapping_with_conflict_cannot_promote(
        self,
    ) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        candidate_item["result"] = result(
            customer="640194",
            method="exact_remittance_invoices",
            difference="0.00",
            allocations=[{"apply_amount": "10.00"}],
            basis="learned_payer_bank_account_mapping",
            confidence=1.0,
            matching_evidence={
                "learned_payer_bank_account_verified": True,
                "learned_payer_bank_account_conflict": True,
                "failed_selection_gates": [],
            },
        )

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertFalse(admitted)
        self.assertIn("customer_evidence_not_deterministic", blockers)

    def test_unique_open_ar_bucket_match_can_promote(self) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        candidate_item["result"] = result(
            customer="640194",
            method="exact_remittance_invoices",
            difference="0.00",
            allocations=[{"apply_amount": "10.00"}],
            basis="unique_open_ar_bucket_match",
            confidence=1.0,
            matching_evidence={
                "unique_open_ar_bucket_match_verified": True,
                "unique_open_ar_bucket_match_conflict": False,
                "failed_selection_gates": [],
            },
        )

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertTrue(admitted, blockers)

    def test_unique_open_ar_bucket_match_with_conflict_cannot_promote(
        self,
    ) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        candidate_item["result"] = result(
            customer="640194",
            method="exact_remittance_invoices",
            difference="0.00",
            allocations=[{"apply_amount": "10.00"}],
            basis="unique_open_ar_bucket_match",
            confidence=1.0,
            matching_evidence={
                "unique_open_ar_bucket_match_verified": True,
                "unique_open_ar_bucket_match_conflict": True,
                "failed_selection_gates": [],
            },
        )

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertFalse(admitted)
        self.assertIn("customer_evidence_not_deterministic", blockers)

    def test_complete_exact_phone_and_zip_can_promote_at_resolver_score(
        self,
    ) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        resolution = candidate_item["result"]["customer_resolution"]
        resolution["selection_basis"] = "exact_phone_and_zip"
        resolution["confidence_basis"] = "exact_phone_and_zip"
        resolution["selected_confidence"] = 0.97

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertTrue(admitted, blockers)

    def test_exact_phone_and_zip_requires_complete_unique_candidate_set(
        self,
    ) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        resolution = candidate_item["result"]["customer_resolution"]
        resolution["selection_basis"] = "exact_phone_and_zip"
        resolution["confidence_basis"] = "exact_phone_and_zip"
        resolution["selected_confidence"] = 0.97
        resolution["matching_evidence"]["contact_candidate_complete"] = False
        resolution["matching_evidence"]["failed_selection_gates"] = [
            "contact_candidate_set_incomplete"
        ]

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertFalse(admitted)
        self.assertIn("customer_evidence_not_deterministic", blockers)

    def test_duplicate_exact_phone_and_zip_cannot_promote(self) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        resolution = candidate_item["result"]["customer_resolution"]
        resolution["selection_basis"] = "exact_phone_and_zip"
        resolution["confidence_basis"] = "exact_phone_and_zip"
        resolution["selected_confidence"] = 0.97
        resolution["matching_evidence"]["exact_phone_postal_match_count"] = 2
        resolution["matching_evidence"]["failed_selection_gates"] = [
            "duplicate_exact_phone_zip"
        ]

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertFalse(admitted)
        self.assertIn("customer_evidence_not_deterministic", blockers)

    def test_unique_exact_address_and_zip_can_promote(self) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        resolution = candidate_item["result"]["customer_resolution"]
        resolution["selection_basis"] = "exact_address_and_zip"
        resolution["confidence_basis"] = "unique_exact_address_and_zip"
        resolution["selected_confidence"] = 1.0
        resolution["matching_evidence"] = {
            "address_candidate_complete": True,
            "exact_address_postal_match_count": 1,
            "failed_selection_gates": [],
        }

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertTrue(admitted, blockers)

    def test_name_only_payee_conflict_can_promote_after_exact_address_proof(
        self,
    ) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        resolution = candidate_item["result"]["customer_resolution"]
        resolution["selection_basis"] = "exact_address_and_zip"
        resolution["confidence_basis"] = "unique_exact_address_and_zip"
        resolution["selected_confidence"] = 1.0
        resolution["matching_evidence"] = {
            "address_candidate_complete": True,
            "exact_address_postal_match_count": 1,
            "failed_selection_gates": [],
        }
        candidate_item["source"]["projection_evidence"].update(
            {
                "customer_conflict_count": 1,
                "customer_conflict_fields": ["customer_name"],
            }
        )

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertTrue(admitted, blockers)

    def test_name_only_conflict_stays_blocked_without_complete_identity_proof(
        self,
    ) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        resolution = candidate_item["result"]["customer_resolution"]
        resolution["selection_basis"] = "exact_address_and_zip"
        resolution["confidence_basis"] = "unique_exact_address_and_zip"
        resolution["selected_confidence"] = 1.0
        resolution["matching_evidence"] = {
            "address_candidate_complete": False,
            "exact_address_postal_match_count": 1,
            "failed_selection_gates": ["address_candidate_set_incomplete"],
        }
        candidate_item["source"]["projection_evidence"].update(
            {
                "customer_conflict_count": 1,
                "customer_conflict_fields": ["customer_name"],
            }
        )

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertFalse(admitted)
        self.assertIn("customer_evidence_not_deterministic", blockers)
        self.assertIn("customer_evidence_conflict", blockers)

    def test_phone_or_address_conflict_never_uses_name_only_override(
        self,
    ) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        resolution = candidate_item["result"]["customer_resolution"]
        resolution["selection_basis"] = "exact_address_and_zip"
        resolution["confidence_basis"] = "unique_exact_address_and_zip"
        resolution["selected_confidence"] = 1.0
        resolution["matching_evidence"] = {
            "address_candidate_complete": True,
            "exact_address_postal_match_count": 1,
            "failed_selection_gates": [],
        }
        candidate_item["source"]["projection_evidence"].update(
            {
                "customer_conflict_count": 2,
                "customer_conflict_fields": [
                    "customer_name",
                    "customer_phone",
                ],
            }
        )

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertFalse(admitted)
        self.assertIn("customer_evidence_conflict", blockers)

    def test_unique_phone_postal_can_ignore_name_and_city_conflicts(
        self,
    ) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        resolution = candidate_item["result"]["customer_resolution"]
        resolution["selection_basis"] = "exact_phone_and_zip"
        resolution["selected_confidence"] = 0.97
        resolution["matching_evidence"] = {
            "valid_invoice_count": 0,
            "invoice_owner_conflict": False,
            "partial_invoice_owner_evidence": False,
            "contact_candidate_complete": True,
            "phone_candidate_complete": True,
            "address_candidate_complete": True,
            "exact_phone_postal_match_count": 1,
            "exact_phone_match_count": 1,
            "exact_address_postal_match_count": 0,
            "payer_account_directive_verified": False,
            "payer_account_directive_conflict": False,
            "failed_selection_gates": [],
        }
        candidate_item["result"]["recommendation"]["method"] = (
            "exact_aging_bucket_match"
        )
        candidate_item["source"]["projection_evidence"].update(
            {
                "customer_conflict_count": 2,
                "customer_conflict_fields": [
                    "customer_name",
                    "customer_city",
                ],
            }
        )

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertTrue(admitted, blockers)

    def test_corroborating_conflict_projection_can_reach_44_34_unapproved(
        self,
    ) -> None:
        control, candidate = snapshots()
        candidate_item = candidate["transactions"][31]
        candidate_item["result"]["recommendation"]["method"] = (
            "exact_aging_bucket_match"
        )
        candidate_item["result"]["customer_resolution"].update(
            {
                "selection_basis": "exact_phone_and_zip",
                "selected_confidence": 0.97,
                "matching_evidence": {
                    "valid_invoice_count": 0,
                    "invoice_owner_conflict": False,
                    "partial_invoice_owner_evidence": False,
                    "contact_candidate_complete": True,
                    "phone_candidate_complete": True,
                    "address_candidate_complete": True,
                    "exact_phone_postal_match_count": 1,
                    "exact_phone_match_count": 1,
                    "exact_address_postal_match_count": 0,
                    "payer_account_directive_verified": False,
                    "payer_account_directive_conflict": False,
                    "failed_selection_gates": [],
                },
            }
        )
        candidate_item["source"]["projection_evidence"].update(
            {
                "customer_conflict_count": 2,
                "customer_conflict_fields": [
                    "customer_name",
                    "customer_city",
                ],
            }
        )

        projected = apply_control_projection(control, candidate)
        promoted = projected["transactions"][31]

        self.assertEqual(projected["balanced_count"], 44)
        self.assertEqual(projected["exception_count"], 34)
        self.assertEqual(projected["admitted_promotion_count"], 14)
        self.assertEqual(
            promoted["result"]["control_projection"][
                "nonmaterial_customer_conflict_fields"
            ],
            [
                "customer_name",
                "customer_city",
            ],
        )
        self.assertFalse(promoted["result"]["can_auto_approve"])
        self.assertFalse(promoted["result"]["erp_write_performed"])

    def test_city_conflict_remains_blocked_for_address_owner(self) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        resolution = candidate_item["result"]["customer_resolution"]
        resolution["selection_basis"] = "unique_exact_address_and_zip"
        resolution["confidence_basis"] = "unique_exact_address_and_zip"
        resolution["selected_confidence"] = 1.0
        resolution["matching_evidence"] = {
            "address_candidate_complete": True,
            "exact_address_postal_match_count": 1,
            "failed_selection_gates": [],
        }
        candidate_item["source"]["projection_evidence"].update(
            {
                "customer_conflict_count": 2,
                "customer_conflict_fields": [
                    "customer_name",
                    "customer_city",
                ],
            }
        )

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertFalse(admitted)
        self.assertIn("customer_evidence_conflict", blockers)

    def test_phone_postal_owner_does_not_override_contact_conflict(self) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        resolution = candidate_item["result"]["customer_resolution"]
        resolution["selection_basis"] = "exact_phone_and_zip"
        resolution["selected_confidence"] = 0.97
        resolution["matching_evidence"] = {
            "contact_candidate_complete": True,
            "exact_phone_postal_match_count": 1,
            "failed_selection_gates": [],
        }
        candidate_item["source"]["projection_evidence"].update(
            {
                "customer_conflict_count": 3,
                "customer_conflict_fields": [
                    "customer_name",
                    "customer_city",
                    "customer_phone",
                ],
            }
        )

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertFalse(admitted)
        self.assertIn("customer_evidence_conflict", blockers)

    def test_corroborating_conflict_override_requires_complete_identity_proof(
        self,
    ) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        resolution = candidate_item["result"]["customer_resolution"]
        resolution["selection_basis"] = "exact_phone_and_zip"
        resolution["selected_confidence"] = 0.97
        resolution["matching_evidence"] = {
            "contact_candidate_complete": False,
            "exact_phone_postal_match_count": 1,
            "failed_selection_gates": ["contact_candidate_set_incomplete"],
        }
        candidate_item["source"]["projection_evidence"].update(
            {
                "customer_conflict_count": 2,
                "customer_conflict_fields": [
                    "customer_name",
                    "customer_city",
                ],
            }
        )

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertFalse(admitted)
        self.assertIn("customer_evidence_not_deterministic", blockers)
        self.assertIn("customer_evidence_conflict", blockers)

    def test_conflict_count_mismatch_remains_blocked(self) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        resolution = candidate_item["result"]["customer_resolution"]
        resolution["selection_basis"] = "exact_phone_and_zip"
        resolution["selected_confidence"] = 0.97
        resolution["matching_evidence"] = {
            "contact_candidate_complete": True,
            "exact_phone_postal_match_count": 1,
            "failed_selection_gates": [],
        }
        candidate_item["source"]["projection_evidence"].update(
            {
                "customer_conflict_count": 3,
                "customer_conflict_fields": [
                    "customer_name",
                    "customer_city",
                ],
            }
        )

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertFalse(admitted)
        self.assertIn("customer_evidence_conflict", blockers)

    def test_exact_total_open_balance_is_governed_but_unapproved(self) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        candidate_item["result"]["recommendation"]["method"] = (
            "exact_total_open_balance"
        )

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertTrue(admitted, blockers)
        self.assertFalse(
            candidate_item["result"]["recommendation"]["can_auto_approve"]
        )

    def test_payer_account_and_unique_service_charge_can_promote(self) -> None:
        control, candidate = snapshots()
        control_item = control["transactions"][30]
        candidate_item = deepcopy(candidate["transactions"][30])
        resolution = candidate_item["result"]["customer_resolution"]
        resolution["selection_basis"] = "payer_supplied_customer_number"
        resolution["confidence_basis"] = "payer_supplied_customer_number"
        resolution["selected_confidence"] = 1.0
        resolution["matching_evidence"] = {
            "payer_account_directive_verified": True,
            "payer_account_directive_conflict": False,
            "failed_selection_gates": [],
        }
        candidate_item["result"]["recommendation"]["method"] = (
            "exact_remittance_invoice_cap_plus_service_charge"
        )

        admitted, blockers = promotion_assessment(
            control_item,
            candidate_item,
        )

        self.assertTrue(admitted, blockers)

    def test_final_supplement_replaces_stale_ambiguity_reason(self) -> None:
        control, candidate = snapshots()
        control["transactions"][44]["result"]["exception_analysis"] = {
            "primary_reason": {"code": "customer_rank_ambiguity"},
        }

        projected = apply_control_projection(control, candidate)
        review_item = projected["transactions"][44]
        result_payload = review_item["result"]

        self.assertEqual(
            result_payload["exception_analysis"]["primary_reason"]["code"],
            "customer_resolved_no_exact_allocation",
        )
        self.assertEqual(
            result_payload["final_decision_state"]["primary_reason_code"],
            "customer_resolved_no_exact_allocation",
        )
        self.assertEqual(
            review_item["error"]["stage"],
            "allocation_evaluation",
        )

    def test_balanced_candidate_blocker_has_final_projection_reason(self) -> None:
        control, candidate = snapshots()

        projected = apply_control_projection(control, candidate)
        blocked_item = projected["transactions"][31]

        self.assertEqual(
            blocked_item["result"]["exception_analysis"][
                "primary_reason"
            ]["code"],
            "projection_evidence_gate_blocked",
        )
        self.assertEqual(blocked_item["error"]["stage"], "control_projection")

    def test_existing_customer_conflict_blocks_promotion(self) -> None:
        control, candidate = snapshots()
        control_item = deepcopy(control["transactions"][30])
        control_item["result"] = result(customer="ACCEPTED")
        candidate_item = candidate["transactions"][30]

        admitted, blockers = promotion_assessment(control_item, candidate_item)

        self.assertFalse(admitted)
        self.assertIn("accepted_customer_conflict", blockers)

    def test_missing_transaction_fails_closed(self) -> None:
        control, candidate = snapshots()
        candidate["transactions"].pop()

        with self.assertRaisesRegex(RuntimeError, "exactly match all 78"):
            apply_control_projection(control, candidate)

    def test_source_row_loss_fails_global_release_gate(self) -> None:
        control, candidate = snapshots()
        candidate["transactions"][40]["source"]["projection_evidence"][
            "removed_allocation_count"
        ] = 1

        with self.assertRaisesRegex(RuntimeError, "source_rows"):
            apply_control_projection(control, candidate)

    def test_signed_credit_must_remain_negative(self) -> None:
        control, candidate = snapshots()
        candidate["transactions"][30]["result"]["recommendation"][
            "allocations"
        ].append({"business_type": "Credit", "apply_amount": "1.00"})

        with self.assertRaisesRegex(RuntimeError, "signed_credits"):
            apply_control_projection(control, candidate)


if __name__ == "__main__":
    unittest.main()
