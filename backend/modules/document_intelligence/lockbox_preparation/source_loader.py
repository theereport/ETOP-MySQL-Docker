"""Load immutable Lockbox evidence for the Increment 3I candidate generation.

The original saved parser result remains the evidence floor.  A versioned
Increment 3I parse may add rows or customer assertions, but it cannot remove a
saved row, replace a conflicting amount, import editable review state, or use
the PDF's displayed ``Num Pages`` value as a transaction boundary.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping

from invoice_number_rules import ERP_INVOICE_RULE_VERSION

from ..pnc_lockbox_parser import EXTRACTION_VERSION, parse_pnc_lockbox
from .policy import normalize_invoice

DocumentJobLoader = Callable[[str], dict[str, Any]]
LockboxResultLoader = Callable[[str], dict[str, Any]]
LockboxParser = Callable[[str | Path], dict[str, Any]]

VERSIONED_EXTRACTION_DIR = (
    Path(__file__).resolve().parents[1]
    / "lockbox_results"
    / "versioned_extractions"
)
EXPECTED_BOUNDARY_RULE = "next_transaction_information"

_CUSTOMER_FIELDS = (
    "customer_number",
    "printed_customer_number",
    "statement_customer_number",
    "for_customer_number",
    "customer_name",
    "customer_phone",
    "customer_address_line_1",
    "customer_address_line_2",
    "customer_city",
    "customer_state",
    "customer_postal_code",
)

_CANDIDATE_EVIDENCE_FIELDS = (
    "remittance_pages",
    "remittance_pages_examined",
    "remittance_candidate_pages",
    "ocr_attempted_pages",
    "ocr_successful_pages",
    "ocr_attempts",
    "rejected_remittance_candidates",
    "remittance_incomplete_pages",
    "remittance_ocr_errors",
    "customer_identity_confidence",
    "customer_identity_evidence",
    "customer_identity_block",
    "customer_identity_strategy",
    "customer_identity_attempts",
    "check_region",
    "printed_customer_number_evidence",
    "printed_customer_number_candidates",
    "statement_customer_number_evidence",
    "statement_customer_number_candidates",
    "for_customer_number_evidence",
    "for_customer_number_candidates",
)


def _get_document_job(source_job_id: str) -> dict[str, Any]:
    from ..service import get_job

    return get_job(source_job_id)


def _get_saved_lockbox_result(source_job_id: str) -> dict[str, Any]:
    from ..lockbox_service import get_raw_lockbox_result

    return get_raw_lockbox_result(source_job_id)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def _allocation_amount(allocation: Mapping[str, Any]) -> Decimal:
    return _money(
        allocation.get("net_invoice_amount")
        if "net_invoice_amount" in allocation
        else allocation.get("apply_amount")
    )


def _allocation_key(
    allocation: Mapping[str, Any],
) -> tuple[str, Decimal]:
    return (
        normalize_invoice(allocation.get("invoice_number")),
        _allocation_amount(allocation),
    )


def _normalized_phone(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 11 and digits.startswith("1"):
        return digits[1:]
    return digits


def _normalized_postal(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))[:5]


def _candidate_has_complete_contact_anchor(
    candidate: Mapping[str, Any],
) -> bool:
    try:
        confidence = float(
            candidate.get("customer_identity_confidence") or 0
        )
    except (TypeError, ValueError):
        confidence = 0.0
    return bool(
        len(_normalized_phone(candidate.get("customer_phone"))) == 10
        and len(
            _normalized_postal(candidate.get("customer_postal_code"))
        ) == 5
        and str(candidate.get("customer_address_line_1") or "").strip()
        and str(candidate.get("customer_name") or "").strip()
        and confidence >= 0.90
    )


def _merge_customer_evidence(
    baseline: dict[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    conflict_fields: list[str] = []
    for key in _CUSTOMER_FIELDS:
        old = str(baseline.get(key) or "").strip()
        new = str(candidate.get(key) or "").strip()
        if old and new and old.casefold() != new.casefold():
            conflict_fields.append(key)
        elif not old and new:
            baseline[key] = deepcopy(candidate.get(key))

    name_only_payee_conflict = bool(
        conflict_fields == ["customer_name"]
        and _candidate_has_complete_contact_anchor(candidate)
        and len(_normalized_phone(baseline.get("customer_phone"))) in {0, 10}
        and len(
            _normalized_postal(baseline.get("customer_postal_code"))
        ) in {0, 5}
    )
    return {
        "material_conflict_count": (
            0 if name_only_payee_conflict else len(conflict_fields)
        ),
        "nonmaterial_name_conflict_count": int(name_only_payee_conflict),
        "conflict_fields": conflict_fields,
        "candidate_complete_contact_anchor": (
            _candidate_has_complete_contact_anchor(candidate)
        ),
    }


def _merge_transaction(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    coverage_exact: bool,
) -> dict[str, Any]:
    merged = deepcopy(dict(baseline))
    customer_conflicts = _merge_customer_evidence(merged, candidate)
    baseline_allocations = deepcopy(list(baseline.get("allocations", [])))
    candidate_allocations = deepcopy(list(candidate.get("allocations", [])))
    merged_allocations = deepcopy(baseline_allocations)

    exact_keys = {
        _allocation_key(item)
        for item in merged_allocations
        if normalize_invoice(item.get("invoice_number"))
    }
    amounts_by_invoice: dict[str, set[Decimal]] = {}
    for invoice, amount in exact_keys:
        amounts_by_invoice.setdefault(invoice, set()).add(amount)

    added = 0
    allocation_conflicts = 0
    for allocation in candidate_allocations:
        invoice, amount = _allocation_key(allocation)
        if not invoice or amount == 0:
            continue
        if (
            invoice in amounts_by_invoice
            and amount not in amounts_by_invoice[invoice]
        ):
            allocation_conflicts += 1
            continue
        if (invoice, amount) in exact_keys:
            continue
        merged_allocations.append(deepcopy(allocation))
        exact_keys.add((invoice, amount))
        amounts_by_invoice.setdefault(invoice, set()).add(amount)
        added += 1

    baseline_keys = {
        _allocation_key(item)
        for item in baseline_allocations
        if normalize_invoice(item.get("invoice_number"))
    }
    candidate_keys = {
        _allocation_key(item)
        for item in candidate_allocations
        if normalize_invoice(item.get("invoice_number"))
    }
    parser_confirms_baseline = baseline_keys.issubset(candidate_keys)
    boundary_rule = str(candidate.get("transaction_boundary_rule") or "")
    boundary_closed = bool(candidate.get("transaction_boundary_closed"))
    retained_rejections = list(
        candidate.get("rejected_remittance_candidates", [])
    )
    unresolved_rejection_count = len(retained_rejections)
    incomplete_pages = {
        int(page)
        for page in candidate.get("remittance_incomplete_pages", [])
        if str(page).strip().isdigit()
    }
    unresolved_incomplete_pages = sorted(incomplete_pages)
    parser_complete = bool(candidate.get("remittance_evidence_complete"))
    remittance_complete = bool(
        coverage_exact
        and boundary_rule == EXPECTED_BOUNDARY_RULE
        and boundary_closed
        and parser_complete
        and parser_confirms_baseline
        and allocation_conflicts == 0
        and customer_conflicts["material_conflict_count"] == 0
    )

    for key in _CANDIDATE_EVIDENCE_FIELDS:
        if candidate.get(key) not in (None, "", [], {}):
            merged[key] = deepcopy(candidate.get(key))
    merged.update(
        {
            "allocations": merged_allocations,
            "original_allocations": deepcopy(merged_allocations),
            "transaction_boundary_rule": boundary_rule,
            "transaction_boundary_closed": boundary_closed,
            "remittance_evidence_complete": remittance_complete,
            "projection_evidence": {
                "baseline_allocation_count": len(baseline_allocations),
                "candidate_parsed_allocation_count": len(
                    candidate.get("allocations", [])
                ),
                "source_recovered_allocation_count": 0,
                "merged_allocation_count": len(merged_allocations),
                "added_allocation_count": added,
                "removed_allocation_count": 0,
                "allocation_conflict_count": allocation_conflicts,
                "customer_conflict_count": customer_conflicts[
                    "material_conflict_count"
                ],
                "customer_nonmaterial_name_conflict_count": (
                    customer_conflicts["nonmaterial_name_conflict_count"]
                ),
                "customer_conflict_fields": list(
                    customer_conflicts["conflict_fields"]
                ),
                "candidate_complete_contact_anchor": bool(
                    customer_conflicts[
                        "candidate_complete_contact_anchor"
                    ]
                ),
                "pages_examined_count": len(
                    candidate.get("remittance_pages_examined", [])
                ),
                "boundary_rule": boundary_rule,
                "boundary_closed": boundary_closed,
                "remittance_evidence_complete": remittance_complete,
                "parser_reported_remittance_evidence_complete": bool(
                    candidate.get("remittance_evidence_complete")
                ),
                "parser_confirms_baseline": parser_confirms_baseline,
                "retained_rejection_count": len(retained_rejections),
                "source_recovered_rejection_count": 0,
                "unresolved_rejection_count": (
                    unresolved_rejection_count
                ),
                "unresolved_incomplete_pages": (
                    unresolved_incomplete_pages
                ),
                "erp_invoice_rule_version": ERP_INVOICE_RULE_VERSION,
                "baseline_evidence_preserved": True,
                "review_edits_used_as_extraction": False,
            },
        }
    )
    return merged


def merge_extractions(
    saved_result: Mapping[str, Any],
    candidate_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Add candidate evidence without deleting immutable saved evidence."""

    saved_transactions = list(saved_result.get("transactions", []))
    candidate_transactions = list(candidate_result.get("transactions", []))
    saved_ids = [
        str(item.get("transaction_id") or "")
        for item in saved_transactions
    ]
    candidate_ids = [
        str(item.get("transaction_id") or "")
        for item in candidate_transactions
    ]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError(
            "The Increment 3I parse produced duplicate transaction IDs."
        )

    if saved_ids:
        coverage_exact = (
            len(saved_ids) == len(candidate_ids)
            and set(saved_ids) == set(candidate_ids)
            and len(saved_ids) == len(set(saved_ids))
        )
        if not coverage_exact:
            raise ValueError(
                "The Increment 3I parse did not preserve the complete saved "
                "Lockbox transaction set."
            )
        candidate_by_id = {
            str(item.get("transaction_id") or ""): item
            for item in candidate_transactions
        }
        merged_transactions = [
            _merge_transaction(
                item,
                candidate_by_id[str(item.get("transaction_id") or "")],
                coverage_exact=True,
            )
            for item in saved_transactions
        ]
    else:
        coverage_exact = bool(candidate_transactions)
        merged_transactions = [
            _merge_transaction(
                {},
                item,
                coverage_exact=coverage_exact,
            )
            for item in candidate_transactions
        ]
        for merged, candidate in zip(
            merged_transactions,
            candidate_transactions,
            strict=True,
        ):
            merged.update(
                {
                    key: deepcopy(value)
                    for key, value in candidate.items()
                    if key not in {
                        "allocations",
                        "original_allocations",
                        "projection_evidence",
                    }
                }
            )

    merged_result = deepcopy(dict(saved_result))
    merged_result.update(
        {
            key: deepcopy(value)
            for key, value in candidate_result.items()
            if key not in {"transactions", "transaction_count"}
        }
    )
    merged_result.update(
        {
            "prior_extraction_version": str(
                saved_result.get("extraction_version")
                or saved_result.get("parser_version")
                or "unknown"
            ),
            "parser_version": EXTRACTION_VERSION,
            "extraction_version": EXTRACTION_VERSION,
            "transactions": merged_transactions,
            "transaction_count": len(merged_transactions),
            "candidate_coverage_exact": coverage_exact,
            "review_edits_used_as_extraction": False,
            "erp_invoice_rule_version": ERP_INVOICE_RULE_VERSION,
        }
    )
    return merged_result


class SavedLockboxSourceLoader:
    """Bind the original PDF to one evidence-preserving 3I extraction."""

    def __init__(
        self,
        *,
        job_loader: DocumentJobLoader = _get_document_job,
        result_loader: LockboxResultLoader = _get_saved_lockbox_result,
        review_loader: LockboxResultLoader | None = None,
        parser: LockboxParser = parse_pnc_lockbox,
        versioned_extraction_dir: str | Path | None = None,
    ) -> None:
        self._job_loader = job_loader
        self._result_loader = result_loader
        # Kept only for constructor compatibility.  Human review is never
        # invoked or admitted as extraction input in Increment 3I.
        self._review_loader = review_loader
        self._parser = parser
        self._versioned_extraction_dir = Path(
            versioned_extraction_dir or VERSIONED_EXTRACTION_DIR
        ).resolve()

    def _versioned_extraction_path(
        self,
        source_job_id: str,
        source_file_hash: str,
    ) -> Path:
        safe_job_id = re.sub(
            r"[^A-Za-z0-9_.-]+",
            "-",
            source_job_id,
        ).strip("-.") or "lockbox"
        version_hash = hashlib.sha256(
            EXTRACTION_VERSION.encode("utf-8")
        ).hexdigest()[:16]
        return self._versioned_extraction_dir / (
            f"{safe_job_id}-{source_file_hash}-{version_hash}.json"
        )

    def _current_extraction(
        self,
        *,
        source_job_id: str,
        stored_path: Path,
        source_file_hash: str,
    ) -> dict[str, Any]:
        cache_path = self._versioned_extraction_path(
            source_job_id,
            source_file_hash,
        )
        if cache_path.is_file():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if (
                cached.get("extraction_version") != EXTRACTION_VERSION
                or cached.get("source_file_hash") != source_file_hash
            ):
                raise ValueError(
                    "The versioned Lockbox extraction cache does not match "
                    "the Increment 3I parser and source PDF."
                )
            return cached

        parsed = deepcopy(self._parser(stored_path))
        parsed.update(
            {
                "job_id": source_job_id,
                "parser_version": EXTRACTION_VERSION,
                "extraction_version": EXTRACTION_VERSION,
                "erp_invoice_rule_version": ERP_INVOICE_RULE_VERSION,
                "source_file_hash": source_file_hash,
            }
        )
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(parsed, indent=2, ensure_ascii=False)
        try:
            with cache_path.open("x", encoding="utf-8") as destination:
                destination.write(serialized)
        except FileExistsError:
            pass
        return parsed

    def identity(self, source_job_id: str) -> dict[str, Any]:
        """Read immutable source identity without parsing or creating data."""

        job = self._job_loader(source_job_id)
        stored_path_value = str(job.get("stored_path") or "").strip()
        if not stored_path_value:
            raise FileNotFoundError(
                "The original Lockbox PDF path is unavailable."
            )
        stored_path = Path(stored_path_value).resolve()
        if not stored_path.is_file():
            raise FileNotFoundError("The original Lockbox PDF is unavailable.")
        if stored_path.suffix.lower() != ".pdf":
            raise ValueError("The saved Lockbox source is not a PDF.")
        return {
            "stored_path": str(stored_path),
            "source_file_hash": sha256_file(stored_path),
            "source_reference": str(
                job.get("original_file_name") or stored_path.name
            ),
        }

    def __call__(self, source_job_id: str) -> dict[str, Any]:
        identity = self.identity(source_job_id)
        stored_path = Path(identity["stored_path"])
        source_file_hash = str(identity["source_file_hash"])
        saved_result = deepcopy(self._result_loader(source_job_id))
        saved_version = str(
            saved_result.get("extraction_version")
            or saved_result.get("parser_version")
            or ""
        ).strip()
        candidate = (
            deepcopy(saved_result)
            if saved_version == EXTRACTION_VERSION
            else deepcopy(
                self._current_extraction(
                    source_job_id=source_job_id,
                    stored_path=stored_path,
                    source_file_hash=source_file_hash,
                )
            )
        )
        result = merge_extractions(saved_result, candidate)
        result.update(
            {
                "source_file_hash": source_file_hash,
                "source_reference": str(identity["source_reference"]),
                "parser_version": EXTRACTION_VERSION,
                "extraction_version": EXTRACTION_VERSION,
                "erp_invoice_rule_version": ERP_INVOICE_RULE_VERSION,
            }
        )
        return result
