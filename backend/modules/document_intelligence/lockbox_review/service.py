from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException

from invoice_number_rules import normalize_erp_invoice

from ..lockbox_service import get_lockbox_result
from ..pnc_lockbox_export import export_pnc_workbook
from ..resolution.normalization import last4, normalize_company_name
from ..resolution.payer_mapping_repository import PayerCustomerMappingRepository
from .database import (
    append_customer_note as append_customer_note_record,
    get_customer_notes as get_customer_note_records,
    get_reviews,
    list_approved_carryover_origin_transaction_ids,
    list_carryover_job_ids,
    migrate_legacy_reviews,
    save_review,
)
from .queue_export import _safe_file_part, export_review_queue_workbook
from core.test_path_override import resolve_test_path_override

MODULE_DIR = Path(__file__).resolve().parent
EXPORT_DIR = resolve_test_path_override(
    "ETOP_TEST_LOCKBOX_REVIEW_EXPORT_DIR",
    MODULE_DIR / "exports",
    kind="directory",
)
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

BALANCE_TOLERANCE = 0.01
REVIEW_STATUSES = {
    "balanced",
    "review_required",
    "no_remittance",
    "corrected",
    "held",
    "carryover",
    "approved",
}
# Carryover is a durable human disposition like held/corrected/approved (a
# reviewer deliberately deferred this transaction), but unlike held it is
# never re-surfaced as an unresolved "review exception" and never blocks
# export - see _status_counts and build_reviewed_result.
PROTECTED_HUMAN_DRAFT_STATUSES = {"corrected", "held", "carryover", "approved"}
MISC_GL_REASON_CODES: dict[str, str] = {
    "Service Charge ADJ": "3880",
    "AR Variance": "3950",
}
GovernedPreparationLoader = Callable[[str], dict[str, Any]]
CurrentOpenARLoader = Callable[[str, date], dict[str, Any]]
_governed_preparation_loader: GovernedPreparationLoader | None = None
_current_open_ar_loader: CurrentOpenARLoader | None = None


def configure_governed_preparation_loader(
    loader: GovernedPreparationLoader,
) -> None:
    global _governed_preparation_loader
    _governed_preparation_loader = loader


def configure_current_open_ar_loader(
    loader: CurrentOpenARLoader,
) -> None:
    """Bind the existing read-only ERP Open-A/R query for review validation."""

    global _current_open_ar_loader
    _current_open_ar_loader = loader


def _money(value: Any) -> float:
    return round(float(value or 0), 2)


def _as_of_date(value: Any) -> date:
    text = str(value or "").strip()
    for pattern in ("%Y-%m-%d", "%m/%d/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(text[:10], pattern).date()
        except ValueError:
            continue
    return date.today()


def _normalize_allocation(allocation: dict[str, Any]) -> dict[str, Any]:
    allocation_kind = str(
        allocation.get("allocation_kind") or "invoice"
    ).strip()
    if allocation_kind not in {"invoice", "service_charge"}:
        allocation_kind = "invoice"
    return {
        "invoice_number": str(allocation.get("invoice_number") or "").strip(),
        "net_invoice_amount": _money(allocation.get("net_invoice_amount")),
        "invoice_page": str(allocation.get("invoice_page") or ""),
        "confidence": max(0.0, min(1.0, float(allocation.get("confidence", 1.0) or 0))),
        "raw_invoice_candidates": [
            str(value)
            for value in allocation.get("raw_invoice_candidates", [])
        ],
        "extraction_source": str(
            allocation.get("extraction_source") or ""
        ),
        "ocr_psm": (
            int(allocation["ocr_psm"])
            if allocation.get("ocr_psm") is not None
            else None
        ),
        "allocation_kind": allocation_kind,
        "erp_transaction_type": str(
            allocation.get("erp_transaction_type")
            or allocation.get("raw_transaction_type")
            or ""
        ).strip(),
        "open_item_key": str(allocation.get("open_item_key") or "").strip(),
        "normalized_invoice_number": str(
            allocation.get("normalized_invoice_number")
            or normalize_erp_invoice(allocation.get("invoice_number"))
        ),
        "invoice_count": (
            int(allocation["invoice_count"])
            if allocation.get("invoice_count") is not None
            else None
        ),
    }


def _status_counts(transactions: list[dict[str, Any]]) -> dict[str, int]:
    """Return mutually exclusive workflow counts for the review queues."""

    return {
        "balanced_count": sum(
            1 for item in transactions if item.get("status") == "balanced"
        ),
        "review_count": sum(
            1
            for item in transactions
            if item.get("status")
            not in {
                "balanced",
                "corrected",
                "held",
                "carryover",
                "approved",
            }
        ),
        "held_count": sum(
            1 for item in transactions if item.get("status") == "held"
        ),
        "carryover_count": sum(
            1 for item in transactions if item.get("status") == "carryover"
        ),
        "approved_count": sum(
            1 for item in transactions if item.get("status") == "approved"
        ),
        "corrected_count": sum(
            1 for item in transactions if item.get("status") == "corrected"
        ),
    }


def _build_review(job_id: str) -> dict[str, Any]:
    source = deepcopy(get_lockbox_result(job_id))
    migrate_legacy_reviews(
        job_id,
        {
            str(item.get("transaction_id") or ""): [
                _normalize_allocation(allocation)
                for allocation in item.get("original_allocations")
                or item.get("allocations", [])
            ]
            for item in source.get("transactions", [])
        },
    )
    stored = get_reviews(job_id)
    transactions: list[dict[str, Any]] = []

    for original in source.get("transactions", []):
        transaction_id = str(original.get("transaction_id") or "")
        original_allocations = [
            _normalize_allocation(item)
            for item in original.get("allocations", [])
        ]
        review = stored.get(transaction_id)
        allocations = (
            [_normalize_allocation(item) for item in review["allocations"]]
            if review
            else deepcopy(original_allocations)
        )
        allocation_total = _money(sum(item["net_invoice_amount"] for item in allocations))
        check_amount = _money(original.get("check_amount"))
        misc_gl = review.get("misc_gl") or {} if review else {}
        misc_gl_amount = _money(misc_gl.get("amount") or 0)
        difference = _money(check_amount - allocation_total - misc_gl_amount)
        balanced = abs(difference) <= BALANCE_TOLERANCE

        if review:
            status = review["status"]
        elif original.get("status") == "no_remittance":
            status = "no_remittance"
        elif balanced:
            status = "balanced"
        else:
            status = "review_required"

        customer = review.get("customer", {}) if review else {}
        transactions.append(
            {
                **original,
                **{
                    key: value
                    for key, value in customer.items()
                    if value
                },
                "original_allocations": original_allocations,
                "allocations": allocations,
                "allocation_total": allocation_total,
                "difference": difference,
                "balanced": balanced,
                "status": status,
                "reviewer": review["reviewer"] if review else "",
                "notes": review["notes"] if review else "",
                "override_reason": review["override_reason"] if review else "",
                "misc_gl": misc_gl,
                "reviewed_at": review["reviewed_at"] if review else None,
            }
        )

    allocation_count = sum(len(item["allocations"]) for item in transactions)
    total_check_amount = _money(sum(_money(item.get("check_amount")) for item in transactions))
    total_allocation_amount = _money(sum(item["allocation_total"] for item in transactions))
    counts = _status_counts(transactions)

    return {
        "job_id": job_id,
        "parser_version": source.get("parser_version", ""),
        "extraction_version": source.get("extraction_version", ""),
        "source_file_name": source.get("source_file_name", ""),
        "lockbox": source.get("lockbox", ""),
        "transaction_date": source.get("transaction_date", ""),
        "transaction_count": len(transactions),
        "allocation_count": allocation_count,
        "total_check_amount": total_check_amount,
        "total_allocation_amount": total_allocation_amount,
        "total_difference": _money(total_check_amount - total_allocation_amount),
        **counts,
        "transactions": transactions,
        "warnings": source.get("warnings", []),
    }


def _project_governed_preparation(
    review: dict[str, Any],
    preparation: dict[str, Any],
) -> dict[str, Any]:
    if not (
        preparation.get("complete")
        and preparation.get("counts_final")
        and preparation.get("reconciled")
        and preparation.get("current_for_rule") is not False
        and preparation.get("recommendation_not_decision")
        and not preparation.get("can_auto_approve")
        and not preparation.get("erp_write_performed")
    ):
        return review
    durable_by_id = {
        str(item.get("transaction_id") or ""): item
        for item in preparation.get("transactions", [])
    }
    if set(durable_by_id) != {
        str(item.get("transaction_id") or "")
        for item in review["transactions"]
    }:
        raise HTTPException(
            status_code=409,
            detail=(
                "The governed preparation does not reconcile to the "
                "current Lockbox review transaction set."
            ),
        )

    for transaction in review["transactions"]:
        if transaction["status"] in PROTECTED_HUMAN_DRAFT_STATUSES:
            continue
        durable = durable_by_id[transaction["transaction_id"]]
        state = str(durable.get("state") or "")
        result = durable.get("result") or {}
        if state == "prepared_balanced":
            recommendation = result.get("recommendation") or {}
            transaction["allocations"] = [
                _normalize_allocation(
                    {
                        "invoice_number": item.get("invoice_number"),
                        "net_invoice_amount": item.get("apply_amount"),
                        "invoice_page": "",
                        "confidence": 1.0,
                        "allocation_kind": item.get("allocation_kind"),
                        "erp_transaction_type": item.get(
                            "raw_transaction_type"
                        ),
                        "open_item_key": item.get("open_item_key"),
                        "normalized_invoice_number": item.get(
                            "normalized_invoice_number"
                        ),
                        "invoice_count": item.get("invoice_count"),
                    }
                )
                for item in recommendation.get("allocations", [])
            ]
            transaction["status"] = "balanced"
        elif state == "prepared_exception":
            transaction["status"] = (
                "no_remittance"
                if transaction["status"] == "no_remittance"
                else "review_required"
            )
        snapshot = (result.get("customer_snapshot") or {}).get(
            "fields", {}
        )
        if snapshot.get("customer_number"):
            transaction.update(
                {
                    "customer_number": str(
                        snapshot.get("customer_number") or ""
                    ),
                    "customer_name": str(
                        snapshot.get("customer_name") or ""
                    ),
                    "customer_phone": str(snapshot.get("phone") or ""),
                    "customer_address_line_1": str(
                        snapshot.get("address_line_1") or ""
                    ),
                    "customer_address_line_2": str(
                        snapshot.get("address_line_2") or ""
                    ),
                    "customer_city": str(snapshot.get("city") or ""),
                    "customer_state": str(snapshot.get("state") or ""),
                    "customer_postal_code": str(
                        snapshot.get("postal_code") or ""
                    ),
                }
            )
        allocation_total = _money(
            sum(
                item["net_invoice_amount"]
                for item in transaction["allocations"]
            )
        )
        transaction["allocation_total"] = allocation_total
        transaction["difference"] = _money(
            transaction["check_amount"] - allocation_total
        )
        transaction["balanced"] = state == "prepared_balanced"

    review["allocation_count"] = sum(
        len(item["allocations"]) for item in review["transactions"]
    )
    review["total_allocation_amount"] = _money(
        sum(item["allocation_total"] for item in review["transactions"])
    )
    review["total_difference"] = _money(
        review["total_check_amount"] - review["total_allocation_amount"]
    )
    review.update(_status_counts(review["transactions"]))
    return review


def get_unprojected_lockbox_review(job_id: str) -> dict[str, Any]:
    try:
        return _build_review(job_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


def get_lockbox_review(job_id: str) -> dict[str, Any]:
    try:
        review = get_unprojected_lockbox_review(job_id)
        if _governed_preparation_loader is None:
            return review
        try:
            preparation = _governed_preparation_loader(job_id)
        except (KeyError, FileNotFoundError):
            return review
        return _project_governed_preparation(review, preparation)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


def _record_confirmed_payer_mapping(
    transaction: dict[str, Any],
    customer_number: str,
    customer_name: str,
) -> None:
    """Best-effort: remember this check's bank account as belonging to the
    customer a reviewer just confirmed, so the same bank account resolves
    automatically next time (a fallback tier in active_provider.py reads
    this back). Never allowed to fail the actual review save."""

    if not customer_number:
        return
    routing_number = str(transaction.get("aba_routing") or "").strip()
    bank_account_last4 = last4(transaction.get("account_number"))
    if not routing_number or len(bank_account_last4) != 4:
        return
    try:
        PayerCustomerMappingRepository().upsert(
            routing_number,
            bank_account_last4,
            normalize_company_name(customer_name),
            customer_number,
            1.0,
            confirmed_by_user=True,
        )
    except Exception:
        pass


def save_transaction_review(
    job_id: str,
    transaction_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    review = get_lockbox_review(job_id)
    transaction = next(
        (item for item in review["transactions"] if item["transaction_id"] == transaction_id),
        None,
    )
    if not transaction:
        raise HTTPException(status_code=404, detail="Lockbox transaction was not found.")

    status = str(payload.get("status") or "corrected")
    if status not in REVIEW_STATUSES:
        raise HTTPException(status_code=400, detail="Unknown Lockbox review status.")

    allocations = [_normalize_allocation(item) for item in payload.get("allocations", [])]
    if status not in {"held", "carryover"} and any(
        not item["invoice_number"] for item in allocations
    ):
        raise HTTPException(status_code=400, detail="Every allocation requires an invoice number.")

    customer_number = str(
        payload.get("customer_number")
        or transaction.get("customer_number")
        or ""
    ).strip()
    # Hold and Carryover are durable parking actions, not allocation
    # dispositions. Keep partial draft rows exactly available for later work;
    # full identifier and current-ERP checks still run for every other
    # save/approval disposition.
    if status not in {"held", "carryover"}:
        _validate_allocation_identifiers(
            job_id,
            transaction_id,
            allocations,
            customer_number=customer_number,
            as_of_date=_as_of_date(transaction.get("date")),
        )

    misc_gl_reason = str(payload.get("misc_gl_reason") or "").strip()
    misc_gl_amount = _money(payload.get("misc_gl_amount") or 0)
    if misc_gl_reason and misc_gl_reason not in MISC_GL_REASON_CODES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown Misc G/L reason: {misc_gl_reason}",
        )
    if misc_gl_amount and not misc_gl_reason:
        raise HTTPException(
            status_code=400,
            detail="A Misc G/L reason is required when an amount is entered.",
        )
    misc_gl = {
        "reason": misc_gl_reason,
        "gl_code": MISC_GL_REASON_CODES.get(misc_gl_reason, ""),
        "location": str(payload.get("misc_gl_location") or "").strip(),
        "department": str(payload.get("misc_gl_department") or "").strip(),
        "amount": misc_gl_amount,
    }

    allocation_total = _money(sum(item["net_invoice_amount"] for item in allocations))
    difference = _money(
        _money(transaction["check_amount"]) - allocation_total - misc_gl_amount
    )
    balanced = abs(difference) <= BALANCE_TOLERANCE
    override_reason = str(payload.get("override_reason") or "").strip()

    if status == "approved" and not balanced and not override_reason:
        raise HTTPException(
            status_code=400,
            detail="An override reason is required to approve an unbalanced transaction.",
        )

    # Optimistic concurrency: `transaction` above was read at the top of
    # this function, before all the validation work just done - a second
    # reviewer (or a stale second tab) could have saved a review for this
    # exact transaction in the meantime. Re-check the truly current
    # reviewed_at right before writing, matching the
    # expected_processing_run_id pattern service.py's
    # save_current_job_review already uses for document review saves.
    current_reviewed_at = get_reviews(job_id).get(transaction_id, {}).get("reviewed_at")
    if payload.get("expected_reviewed_at") != current_reviewed_at:
        raise HTTPException(
            status_code=409,
            detail=(
                "This lockbox transaction was reviewed by someone else after "
                "this review was loaded. Reload the transaction before saving."
            ),
        )

    save_review(
        job_id,
        transaction_id,
        original_allocations=transaction["original_allocations"],
        allocations=allocations,
        customer={
            key: str(payload.get(key) or "").strip()
            for key in (
                "customer_number",
                "customer_name",
                "customer_phone",
                "customer_address_line_1",
                "customer_address_line_2",
                "customer_city",
                "customer_state",
                "customer_postal_code",
            )
        },
        status=status,
        reviewer=str(payload.get("reviewer") or "").strip(),
        notes=str(payload.get("notes") or "").strip(),
        override_reason=override_reason,
        misc_gl=misc_gl,
    )
    if status not in {"held", "carryover"}:
        _record_confirmed_payer_mapping(
            transaction,
            customer_number,
            str(payload.get("customer_name") or "").strip(),
        )
    return get_lockbox_review(job_id)


def _customer_note_context(
    job_id: str,
    transaction_id: str,
) -> tuple[dict[str, Any], str, str]:
    review = get_lockbox_review(job_id)
    transaction = next(
        (
            item
            for item in review["transactions"]
            if item["transaction_id"] == transaction_id
        ),
        None,
    )
    if not transaction:
        raise HTTPException(
            status_code=404,
            detail="Lockbox transaction was not found.",
        )

    customer_number = str(
        transaction.get("customer_number") or ""
    ).strip()
    if not customer_number:
        raise HTTPException(
            status_code=409,
            detail=(
                "Select and save an ERP customer before adding a customer "
                "note."
            ),
        )
    customer_name = str(transaction.get("customer_name") or "").strip()
    return transaction, customer_number, customer_name


def get_transaction_customer_notes(
    job_id: str,
    transaction_id: str,
) -> dict[str, Any]:
    _transaction, customer_number, customer_name = _customer_note_context(
        job_id,
        transaction_id,
    )
    return {
        "customer_number": customer_number,
        "customer_name": customer_name,
        "notes": get_customer_note_records(customer_number),
    }


def append_transaction_customer_note(
    job_id: str,
    transaction_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    transaction, customer_number, customer_name = _customer_note_context(
        job_id,
        transaction_id,
    )
    body = str(payload.get("body") or "").strip()
    author = str(payload.get("author") or "").strip()
    if not body:
        raise HTTPException(
            status_code=400,
            detail="Enter a customer note before saving.",
        )
    if not author:
        raise HTTPException(
            status_code=400,
            detail="Enter the note author before saving.",
        )

    append_customer_note_record(
        customer_number,
        customer_name=customer_name,
        body=body,
        author=author,
        source_job_id=job_id,
        source_transaction_id=transaction_id,
        source_check_number=str(
            transaction.get("check_number") or ""
        ).strip(),
    )
    return {
        "customer_number": customer_number,
        "customer_name": customer_name,
        "notes": get_customer_note_records(customer_number),
    }


def _validate_allocation_identifiers(
    job_id: str,
    transaction_id: str,
    allocations: list[dict[str, Any]],
    *,
    customer_number: str = "",
    as_of_date: date | None = None,
) -> None:
    nonstandard = [
        item
        for item in allocations
        if not normalize_erp_invoice(item["invoice_number"])
        and item["invoice_number"] != "9999999999"
    ]
    if not nonstandard:
        return
    if (
        _governed_preparation_loader is None
        and _current_open_ar_loader is None
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "A non-invoice ERP open item requires current governed "
                "preparation evidence."
            ),
        )
    result: dict[str, Any] = {}
    if _governed_preparation_loader is not None:
        preparation = _governed_preparation_loader(job_id)
        durable = next(
            (
                item
                for item in preparation.get("transactions", [])
                if str(item.get("transaction_id") or "") == transaction_id
            ),
            None,
        )
        result = durable.get("result") or {} if durable else {}

    open_ar = result.get("open_ar") or {}
    evidence_label = "saved governed preparation"
    if _current_open_ar_loader is not None:
        if not customer_number:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Select an ERP customer before saving a service-charge "
                    "allocation."
                ),
            )
        try:
            open_ar = _current_open_ar_loader(
                customer_number,
                as_of_date or date.today(),
            )
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Current ERP Open A/R could not be refreshed, so the "
                    "service-charge allocation was not saved."
                ),
            ) from error

        snapshot_customer = str(
            open_ar.get("customer_number") or ""
        ).strip().removesuffix(".0")
        if snapshot_customer != customer_number.removesuffix(".0"):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Current ERP Open A/R did not reconcile to the selected "
                    "customer, so the service-charge allocation was not saved."
                ),
            )
        evidence_label = "current ERP Open A/R"

    recommendation = result.get("recommendation") or {}
    recommended = {
        (
            str(item.get("open_item_key") or ""),
            str(item.get("invoice_number") or ""),
            str(item.get("allocation_kind") or ""),
            str(item.get("raw_transaction_type") or "").strip().upper(),
        )
        for item in recommendation.get("allocations", [])
    } if _current_open_ar_loader is None else set()
    current_sc_counts: dict[tuple[str, str, str, str], int] = {}
    for item in open_ar.get("invoices", []):
        if str(item.get("raw_transaction_type") or "").strip().upper() != "SC":
            continue
        identity = (
            str(item.get("open_item_key") or ""),
            str(item.get("invoice_number") or ""),
            "service_charge",
            "SC",
        )
        current_sc_counts[identity] = current_sc_counts.get(identity, 0) + 1

    allowed = recommended | {
        identity
        for identity, count in current_sc_counts.items()
        if count == 1 and identity[0]
    }
    used_sc_open_item_keys: set[str] = set()
    for item in nonstandard:
        identity = (
            item["open_item_key"],
            item["invoice_number"],
            item["allocation_kind"],
            item["erp_transaction_type"].upper(),
        )
        if (
            item["allocation_kind"] != "service_charge"
            or item["erp_transaction_type"].upper() != "SC"
            or not item["open_item_key"]
            or identity not in allowed
            or current_sc_counts.get(identity, 0) > 1
            or item["open_item_key"] in used_sc_open_item_keys
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Each service-charge row must match a different SC item "
                    f"in the selected customer's {evidence_label}. Multiple "
                    "service charges are allowed, but a closed, missing, "
                    "or ambiguous item cannot be approved, and the same open "
                    "item cannot be used more than once."
                ),
            )
        used_sc_open_item_keys.add(item["open_item_key"])


def build_reviewed_result(job_id: str) -> dict[str, Any]:
    review = get_lockbox_review(job_id)
    # Carryover transactions are deliberately excluded from export - they're
    # parked for a later session (working something out, waiting on a
    # customer), not ready to post. Recompute every aggregate below from the
    # exported subset so the workbook's own header totals/counts match what
    # actually landed in it, rather than the full review's totals.
    exported_transactions = [
        {
            key: value
            for key, value in transaction.items()
            if key not in {
                "original_allocations", "reviewer", "notes",
                "override_reason", "reviewed_at",
            }
        }
        for transaction in review["transactions"]
        if transaction.get("status") != "carryover"
    ]
    total_check_amount = _money(
        sum(_money(item.get("check_amount")) for item in exported_transactions)
    )
    total_allocation_amount = _money(
        sum(item["allocation_total"] for item in exported_transactions)
    )
    return {
        "job_id": review["job_id"],
        "source_file_name": review["source_file_name"],
        "lockbox": review["lockbox"],
        "transaction_date": review["transaction_date"],
        "transaction_count": len(exported_transactions),
        "allocation_count": sum(
            len(item["allocations"]) for item in exported_transactions
        ),
        "total_check_amount": total_check_amount,
        "total_allocation_amount": total_allocation_amount,
        "total_difference": _money(
            total_check_amount - total_allocation_amount
        ),
        "balanced_count": review["balanced_count"],
        "review_count": review["review_count"],
        "held_count": review["held_count"],
        "carryover_count": review["carryover_count"],
        "transactions": exported_transactions,
        "warnings": review["warnings"],
    }


def create_reviewed_export(job_id: str) -> Path:
    review = get_lockbox_review(job_id)
    if _governed_preparation_loader is None:
        raise HTTPException(
            status_code=503,
            detail="The governed preparation export gate is unavailable.",
        )
    try:
        preparation = _governed_preparation_loader(job_id)
    except (KeyError, FileNotFoundError) as error:
        raise HTTPException(
            status_code=409,
            detail="No current governed preparation is available for export.",
        ) from error
    if not (
        preparation.get("complete")
        and preparation.get("counts_final")
        and preparation.get("reconciled")
        and preparation.get("current_for_rule") is not False
    ):
        raise HTTPException(
            status_code=409,
            detail="The current governed preparation is not final and reconciled.",
        )
    if review.get("held_count", 0):
        raise HTTPException(
            status_code=409,
            detail=(
                f'{review["held_count"]} held transaction(s) must be '
                "returned to professional review and resolved before "
                "reviewed export."
            ),
        )
    if review["review_count"]:
        raise HTTPException(
            status_code=409,
            detail=(
                f'{review["review_count"]} professional review exception(s) '
                "must be resolved before reviewed export."
            ),
        )
    output = (
        EXPORT_DIR
        / f"{_safe_file_part(job_id, 'lockbox')}_PNC_Lockbox_Reviewed.xlsx"
    )
    return export_pnc_workbook(build_reviewed_result(job_id), output)


def list_carryover_transactions() -> list[dict[str, Any]]:
    """Every transaction currently carried over, across every lockbox job.

    Each entry is a transaction dict (same shape the per-job review
    workspace uses) with job_id/source_file_name attached, so the Carryover
    Dashboard can list them and open the right job's review workspace to
    work one.
    """

    transactions: list[dict[str, Any]] = []
    for job_id in list_carryover_job_ids():
        try:
            review = get_lockbox_review(job_id)
        except (KeyError, FileNotFoundError):
            # A job's saved reviews reference a source result that no
            # longer exists (e.g. deleted upload) - skip it rather than
            # failing the whole cross-job listing.
            continue
        for transaction in review.get("transactions", []):
            if transaction.get("status") != "carryover":
                continue
            transactions.append({
                **transaction,
                "job_id": job_id,
                "source_file_name": review.get("source_file_name", ""),
            })
    return transactions


def create_carryover_export() -> Path:
    """Export every transaction that originated from a carryover
    disposition and is now approved, across every lockbox job.

    Separate from create_reviewed_export - that export is scoped to one
    job and explicitly excludes carryover transactions; this one is scoped
    to the carryover-approved set across all jobs, regardless of job.
    """

    pairs = list_approved_carryover_origin_transaction_ids()
    by_job: dict[str, set[str]] = {}
    for job_id, transaction_id in pairs:
        by_job.setdefault(job_id, set()).add(transaction_id)

    transactions: list[dict[str, Any]] = []
    for job_id, transaction_ids in by_job.items():
        try:
            review = get_lockbox_review(job_id)
        except (KeyError, FileNotFoundError):
            continue
        for transaction in review.get("transactions", []):
            if transaction.get("transaction_id") not in transaction_ids:
                continue
            transactions.append({
                key: value
                for key, value in transaction.items()
                if key not in {
                    "original_allocations", "reviewer", "notes",
                    "override_reason", "reviewed_at",
                }
            })

    result = {
        "job_id": "carryover-dashboard",
        "source_file_name": "Multiple lockbox jobs",
        "lockbox": "Multiple",
        "transaction_date": date.today().isoformat(),
        "transaction_count": len(transactions),
        "transactions": transactions,
        "warnings": [],
    }
    output = EXPORT_DIR / "Carryover_Approved_PNC_Lockbox.xlsx"
    return export_pnc_workbook(result, output)


def create_review_queue_export(
    job_id: str,
    transaction_ids: list[str],
    queue_label: str,
    reason_code: str,
) -> Path:
    """Create an informational Excel projection from canonical review data."""

    try:
        return export_review_queue_workbook(
            get_lockbox_review(job_id),
            transaction_ids,
            queue_label,
            reason_code,
            EXPORT_DIR,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
