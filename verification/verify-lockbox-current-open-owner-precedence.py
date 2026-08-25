from __future__ import annotations

import runpy
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# Reuse the governed dependency stubs from the retained fresh-source verifier.
# Loading it under a non-main name installs only the stubs and definitions; it
# does not execute that verifier's main routine.
runpy.run_path(
    str(ROOT / "verification" / "verify-lockbox-fresh-source-bootstrap.py"),
    run_name="__etop_increment3u_dependency_boundary__",
)

from modules.document_intelligence.lockbox_preparation.control_projection import (
    EXPECTED_BOUNDARY_RULE,
    FRESH_SOURCE_PROJECTION_VERSION,
    PROJECTION_VERSION,
    apply_fresh_source_projection,
    promotion_assessment,
)


SELECTED_CUSTOMER = "SYNTHETIC-CURRENT-OWNER"


def projection_evidence() -> dict[str, Any]:
    return {
        "removed_allocation_count": 0,
        "allocation_conflict_count": 0,
        "customer_conflict_count": 0,
        "customer_conflict_fields": [],
        "boundary_rule": EXPECTED_BOUNDARY_RULE,
        "boundary_closed": True,
        "remittance_evidence_complete": True,
        "review_edits_used_as_extraction": False,
    }


def current_open_result(
    invoices: tuple[str, ...],
    *,
    failed_gates: tuple[str, ...] = (),
    partial: bool = False,
    duplicate_phone_count: int = 0,
) -> dict[str, Any]:
    return {
        "customer_resolution": {
            "status": "resolved",
            "customer_number": SELECTED_CUSTOMER,
            "selection_basis": "current_open_invoice_owner",
            "confidence_basis": "unique_current_open_invoice_owner",
            "selected_confidence": 1.0,
            "candidates": [SELECTED_CUSTOMER],
            "matching_evidence": {
                "valid_invoice_count": len(invoices),
                "selected_basis": "current_open_invoice_owner",
                "current_open_status": "resolved",
                "invoice_owner_conflict": False,
                "unresolved_invoice_owner_count": 2 if partial else 0,
                "partial_invoice_owner_evidence": partial,
                "contact_candidate_complete": True,
                "phone_candidate_complete": True,
                "address_candidate_complete": True,
                "exact_phone_postal_match_count": 0,
                "exact_phone_match_count": duplicate_phone_count,
                "exact_address_postal_match_count": 0,
                "payer_account_directive_verified": False,
                "payer_account_directive_conflict": False,
                "failed_selection_gates": list(failed_gates),
            },
        },
        "customer_snapshot": {
            "fields": {"customer_number": SELECTED_CUSTOMER},
        },
        "customer_conflict_assessment": {
            "status": "resolved",
            "customer_number": SELECTED_CUSTOMER,
            "candidate_customer_numbers": [SELECTED_CUSTOMER],
            "remittance_invoice_numbers": list(invoices),
            "broad_invoice_owners": {invoice: [] for invoice in invoices},
            "current_open_invoice_owners": {
                invoice: [SELECTED_CUSTOMER] for invoice in invoices
            },
            "missing_current_open_invoices": [],
            "unavailable_customer_numbers": [],
            "current_open_ar_sources": {},
            "current_open_invoice_sources": {
                invoice: {
                    "source_reference": (
                        "ERP TMAROP current open invoice ownership"
                    ),
                    "as_of_time": "2026-08-05T01:00:00+00:00",
                }
                for invoice in invoices
            },
            "rule_version": (
                "lockbox-current-open-ar-customer-resolution@1.1.0"
            ),
            "requires_human_review": True,
            "can_auto_approve": False,
            "erp_write_performed": False,
        },
        "recommendation": {
            "status": "recommended",
            "method": "exact_remittance_invoices",
            "difference": "0.00",
            "allocations": [
                {
                    "customer_number": SELECTED_CUSTOMER,
                    "invoice_number": invoice,
                    "business_type": "Debit",
                    "apply_amount": "10.00",
                }
                for invoice in invoices
            ],
            "can_auto_approve": False,
        },
        "prepared_not_approved": True,
        "can_auto_approve": False,
        "erp_write_performed": False,
    }


def phone_result() -> dict[str, Any]:
    return {
        "customer_resolution": {
            "status": "resolved",
            "customer_number": "SYNTHETIC-PHONE-OWNER",
            "selection_basis": "exact_phone_and_zip",
            "selected_confidence": 0.97,
            "candidates": ["SYNTHETIC-PHONE-OWNER"],
            "matching_evidence": {
                "contact_candidate_complete": True,
                "phone_candidate_complete": True,
                "exact_phone_postal_match_count": 1,
                "exact_phone_match_count": 1,
                "failed_selection_gates": [],
            },
        },
        "customer_snapshot": {
            "fields": {"customer_number": "SYNTHETIC-PHONE-OWNER"},
        },
        "recommendation": {
            "status": "recommended",
            "method": "exact_total_open_balance",
            "difference": "0.00",
            "allocations": [
                {"business_type": "Debit", "apply_amount": "10.00"},
            ],
            "can_auto_approve": False,
        },
        "prepared_not_approved": True,
        "can_auto_approve": False,
        "erp_write_performed": False,
    }


def transaction(
    ordinal: int,
    *,
    state: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    transaction_id = f"SYNTHETIC-{ordinal:03d}"
    return {
        "job_id": "synthetic-61-candidate",
        "transaction_id": transaction_id,
        "ordinal": ordinal,
        "state": state,
        "source": {
            "transaction_id": transaction_id,
            "original_source": {"transaction_id": transaction_id},
            "projection_evidence": projection_evidence(),
        },
        "result": result,
        "error": (
            {}
            if state == "prepared_balanced"
            else {
                "type": "PreparationPolicyError",
                "message": "Synthetic professional-review exception.",
                "stage": "customer_resolution",
                "retry_eligible": False,
            }
        ),
    }


def current_invoices(ordinal: int, count: int) -> tuple[str, ...]:
    return tuple(
        f"{ordinal:02d}{index:06d}"
        for index in range(1, count + 1)
    )


def snapshot_61() -> dict[str, Any]:
    current_open_shapes = {
        18: current_open_result(
            current_invoices(18, 3),
            failed_gates=("partial_invoice_owner_evidence",),
            partial=True,
        ),
        19: current_open_result(
            current_invoices(19, 29),
            failed_gates=("partial_invoice_owner_evidence",),
            partial=True,
        ),
        20: current_open_result(
            current_invoices(20, 2),
            failed_gates=(
                "duplicate_exact_phone",
                "supporting_evidence_only",
                "existing_rank_lead_not_met",
            ),
            duplicate_phone_count=2,
        ),
        21: current_open_result(
            current_invoices(21, 7),
            failed_gates=("partial_invoice_owner_evidence",),
            partial=True,
        ),
    }
    transactions: list[dict[str, Any]] = []
    for ordinal in range(1, 62):
        if ordinal <= 17:
            transactions.append(
                transaction(
                    ordinal,
                    state="prepared_balanced",
                    result=phone_result(),
                )
            )
        elif ordinal <= 21:
            transactions.append(
                transaction(
                    ordinal,
                    state="prepared_balanced",
                    result=current_open_shapes[ordinal],
                )
            )
        else:
            review_result = {
                "customer_resolution": {
                    "status": "ambiguous",
                    "customer_number": "",
                    "candidates": [],
                    "matching_evidence": {},
                },
                "recommendation": {
                    "status": "review_required",
                    "method": "no_exact_match",
                    "difference": "10.00",
                    "allocations": [],
                    "can_auto_approve": False,
                },
                "exception_analysis": {
                    "classifier_version": "synthetic-classifier",
                    "primary_reason": {
                        "code": "customer_rank_ambiguity",
                        "category": "customer",
                    },
                    "contributing_reasons": [],
                    "reason_codes": ["customer_rank_ambiguity"],
                    "stage": "customer_resolution",
                    "retry_eligible": False,
                },
                "can_auto_approve": False,
                "erp_write_performed": False,
            }
            transactions.append(
                transaction(
                    ordinal,
                    state="prepared_exception",
                    result=review_result,
                )
            )
    return {
        "job_id": "synthetic-61-candidate",
        "source_job_id": "synthetic-61-source",
        "source_file_hash": "6" * 64,
        "state": "complete",
        "complete": True,
        "counts_final": True,
        "expected_count": 61,
        "terminal_count": 61,
        "balanced_count": 21,
        "exception_count": 40,
        "preserved_count": 0,
        "transactions": transactions,
    }


def assert_blocked(candidate: dict[str, Any]) -> None:
    control = deepcopy(candidate)
    control["state"] = "prepared_exception"
    control["result"] = {}
    admitted, blockers = promotion_assessment(control, candidate)
    assert not admitted
    assert "customer_evidence_not_deterministic" in blockers


def main() -> None:
    assert PROJECTION_VERSION.endswith("increment3x")
    assert FRESH_SOURCE_PROJECTION_VERSION.endswith("increment3x")

    projected = apply_fresh_source_projection(snapshot_61())
    assert projected["expected_count"] == 61
    assert projected["terminal_count"] == 61
    assert projected["balanced_count"] == 21
    assert projected["exception_count"] == 40
    assert projected["admitted_promotion_count"] == 21
    assert projected["blocked_promotion_count"] == 0
    assert all(projected["projection_release_gates"].values())
    assert not projected["can_auto_approve"]
    assert not projected["erp_write_performed"]
    for index in range(17, 21):
        item = projected["transactions"][index]
        assert item["state"] == "prepared_balanced"
        assert (
            item["result"]["control_projection"]["outcome"]
            == "promotion_admitted"
        )
        assert not item["result"]["control_projection"][
            "promotion_blockers"
        ]

    base = snapshot_61()["transactions"][17]

    mismatch = deepcopy(base)
    mismatch["result"]["customer_conflict_assessment"][
        "customer_number"
    ] = "OTHER"
    assert_blocked(mismatch)

    missing = deepcopy(base)
    missing["result"]["customer_conflict_assessment"][
        "missing_current_open_invoices"
    ] = [current_invoices(18, 3)[0]]
    assert_blocked(missing)

    duplicate = deepcopy(base)
    first_invoice = current_invoices(18, 3)[0]
    duplicate["result"]["customer_conflict_assessment"][
        "current_open_invoice_owners"
    ][first_invoice] = [SELECTED_CUSTOMER, "OTHER"]
    assert_blocked(duplicate)

    unavailable = deepcopy(base)
    unavailable["result"]["customer_conflict_assessment"][
        "unavailable_customer_numbers"
    ] = [SELECTED_CUSTOMER]
    assert_blocked(unavailable)

    stale = deepcopy(base)
    stale["result"]["customer_conflict_assessment"][
        "current_open_invoice_sources"
    ][first_invoice]["as_of_time"] = ""
    assert_blocked(stale)

    incomplete = deepcopy(base)
    incomplete["result"]["customer_resolution"]["matching_evidence"][
        "current_open_status"
    ] = "incomplete"
    assert_blocked(incomplete)

    payer_conflict = deepcopy(base)
    payer_conflict["result"]["customer_resolution"]["matching_evidence"][
        "payer_account_directive_conflict"
    ] = True
    assert_blocked(payer_conflict)

    projection_conflict = deepcopy(base)
    projection_conflict["source"]["projection_evidence"].update(
        {
            "customer_conflict_count": 1,
            "customer_conflict_fields": ["customer_phone"],
        }
    )
    review_control = deepcopy(projection_conflict)
    review_control["state"] = "prepared_exception"
    review_control["result"] = {}
    admitted, blockers = promotion_assessment(
        review_control,
        projection_conflict,
    )
    assert not admitted
    assert "customer_evidence_conflict" in blockers

    difference = deepcopy(base)
    difference["result"]["recommendation"]["difference"] = "0.02"
    review_control = deepcopy(difference)
    review_control["state"] = "prepared_exception"
    review_control["result"] = {}
    admitted, blockers = promotion_assessment(review_control, difference)
    assert not admitted
    assert "allocation_not_reconciled" in blockers

    automatic_approval = deepcopy(base)
    automatic_approval["result"]["can_auto_approve"] = True
    review_control = deepcopy(automatic_approval)
    review_control["state"] = "prepared_exception"
    review_control["result"] = {}
    admitted, blockers = promotion_assessment(
        review_control,
        automatic_approval,
    )
    assert not admitted
    assert "automatic_approval_reported" in blockers

    erp_write = deepcopy(base)
    erp_write["result"]["erp_write_performed"] = True
    review_control = deepcopy(erp_write)
    review_control["state"] = "prepared_exception"
    review_control["result"] = {}
    admitted, blockers = promotion_assessment(review_control, erp_write)
    assert not admitted
    assert "erp_write_reported" in blockers

    duplicate_phone = snapshot_61()["transactions"][0]
    duplicate_phone["result"]["customer_resolution"]["matching_evidence"].update(
        {
            "exact_phone_postal_match_count": 2,
            "exact_phone_match_count": 2,
            "failed_selection_gates": ["duplicate_exact_phone_zip"],
        }
    )
    assert_blocked(duplicate_phone)

    print(
        "Increment 3U current-open owner precedence verification passed: "
        "the synthetic 61-item fresh source projects to 21 balanced and 40 "
        "review only when the complete current-open ownership envelope "
        "reconciles; partial broad-owner and duplicate contact-rank flags "
        "cannot veto that stronger proof, while incomplete, mismatched, "
        "conflicting, nonzero, approval, and ERP-write paths remain closed."
    )


if __name__ == "__main__":
    main()
