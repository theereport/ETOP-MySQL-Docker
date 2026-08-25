from __future__ import annotations

from collections import defaultdict
from typing import Any

TOLERANCE = 0.01


def _amount(value: Any) -> float:
    return round(float(value or 0), 2)


def _row(transaction_id: str, kind: str, invoice: str, expected=None, actual=None):
    return {
        "transaction_id": transaction_id,
        "difference_type": kind,
        "invoice_number": str(invoice or ""),
        "expected_amount": expected,
        "actual_amount": actual,
    }


def compare_lockbox(actual: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    actual_by_id = {str(t.get("transaction_id", "")): t for t in actual.get("transactions", [])}
    expected_by_id = {str(t.get("transaction_id", "")): t for t in expected.get("transactions", [])}
    transaction_ids = sorted(set(actual_by_id) | set(expected_by_id))

    comparisons = []
    total_matched = total_missing = total_extra = total_amount_errors = 0
    fully_matched_transactions = 0
    expected_amount_rows = 0
    exact_amount_rows = 0

    for transaction_id in transaction_ids:
        exp = expected_by_id.get(transaction_id)
        act = actual_by_id.get(transaction_id)
        exp_rows = list((exp or {}).get("allocations", []))
        act_rows = list((act or {}).get("allocations", []))
        expected_amount_rows += len(exp_rows)

        unmatched_actual = set(range(len(act_rows)))
        differences = []
        matched = amount_errors = 0

        # First match exact invoice and exact amount, preserving duplicates.
        unmatched_expected = []
        for exp_row in exp_rows:
            invoice = str(exp_row.get("invoice_number", ""))
            amount = _amount(exp_row.get("net_invoice_amount"))
            exact_index = next(
                (
                    index for index in unmatched_actual
                    if str(act_rows[index].get("invoice_number", "")) == invoice
                    and abs(_amount(act_rows[index].get("net_invoice_amount")) - amount) <= TOLERANCE
                ),
                None,
            )
            if exact_index is None:
                unmatched_expected.append(exp_row)
                continue
            unmatched_actual.remove(exact_index)
            matched += 1
            exact_amount_rows += 1
            differences.append(_row(transaction_id, "matched", invoice, amount, amount))

        # Then pair same-invoice rows with different amounts.
        still_missing = []
        for exp_row in unmatched_expected:
            invoice = str(exp_row.get("invoice_number", ""))
            amount = _amount(exp_row.get("net_invoice_amount"))
            same_invoice_index = next(
                (
                    index for index in unmatched_actual
                    if str(act_rows[index].get("invoice_number", "")) == invoice
                ),
                None,
            )
            if same_invoice_index is None:
                still_missing.append(exp_row)
                continue
            actual_amount = _amount(act_rows[same_invoice_index].get("net_invoice_amount"))
            unmatched_actual.remove(same_invoice_index)
            amount_errors += 1
            differences.append(_row(transaction_id, "amount_error", invoice, amount, actual_amount))

        for exp_row in still_missing:
            differences.append(
                _row(
                    transaction_id,
                    "missing",
                    str(exp_row.get("invoice_number", "")),
                    _amount(exp_row.get("net_invoice_amount")),
                    None,
                )
            )

        for index in sorted(unmatched_actual):
            act_row = act_rows[index]
            differences.append(
                _row(
                    transaction_id,
                    "extra",
                    str(act_row.get("invoice_number", "")),
                    None,
                    _amount(act_row.get("net_invoice_amount")),
                )
            )

        missing = len(still_missing)
        extra = len(unmatched_actual)
        expected_check = _amount((exp or {}).get("check_amount"))
        actual_check = _amount((act or {}).get("check_amount")) if act else None
        check_matches = actual_check is not None and abs(actual_check - expected_check) <= TOLERANCE
        balanced = bool(exp and act and check_matches and missing == 0 and extra == 0 and amount_errors == 0)
        if balanced:
            fully_matched_transactions += 1

        denominator = max(len(exp_rows), len(act_rows), 1)
        accuracy = round(100 * matched / denominator, 2)
        comparisons.append(
            {
                "transaction_id": transaction_id,
                "expected_check_amount": expected_check,
                "actual_check_amount": actual_check,
                "expected_row_count": len(exp_rows),
                "actual_row_count": len(act_rows),
                "matched_rows": matched,
                "missing_rows": missing,
                "extra_rows": extra,
                "amount_errors": amount_errors,
                "balanced": balanced,
                "accuracy": accuracy,
                "differences": differences,
            }
        )
        total_matched += matched
        total_missing += missing
        total_extra += extra
        total_amount_errors += amount_errors

    expected_rows = int(expected.get("allocation_count", 0))
    actual_rows = int(actual.get("allocation_count", sum(len(t.get("allocations", [])) for t in actual.get("transactions", []))))
    expected_transactions = int(expected.get("transaction_count", 0))
    actual_transactions = int(actual.get("transaction_count", len(actual_by_id)))
    row_denominator = max(expected_rows, actual_rows, 1)
    transaction_denominator = max(expected_transactions, actual_transactions, 1)
    invoice_accuracy = round(100 * total_matched / row_denominator, 2)
    amount_accuracy = round(100 * exact_amount_rows / max(expected_amount_rows, 1), 2)
    transaction_accuracy = round(100 * fully_matched_transactions / transaction_denominator, 2)
    overall_accuracy = round((invoice_accuracy * 0.5) + (amount_accuracy * 0.25) + (transaction_accuracy * 0.25), 2)

    return {
        "overall_accuracy": overall_accuracy,
        "transaction_accuracy": transaction_accuracy,
        "invoice_accuracy": invoice_accuracy,
        "amount_accuracy": amount_accuracy,
        "expected_transactions": expected_transactions,
        "actual_transactions": actual_transactions,
        "matched_transactions": fully_matched_transactions,
        "expected_rows": expected_rows,
        "actual_rows": actual_rows,
        "matched_rows": total_matched,
        "missing_rows": total_missing,
        "extra_rows": total_extra,
        "amount_errors": total_amount_errors,
        "transactions": comparisons,
    }
