"""Pure deterministic matching for warehouse Payment Notes evidence."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Sequence


MATCH_RULE_VERSION = "payment-notes-match@1.0.0"
INVOICE_EXTRACTION_RULE_VERSION = "payment-notes-invoice-reference@1.0.0"


def normalize_check_number(value: Any) -> str:
    """Remove leading zeroes while preserving a stable all-zero identity.

    Blank remains blank. Numeric values returned by a database driver are
    rendered without an integral decimal suffix. Non-numeric characters are
    otherwise retained; this function does not invent a numeric check number.
    """

    if value is None:
        return ""
    if isinstance(value, bool):
        text = str(value)
    elif isinstance(value, int):
        text = str(value)
    elif isinstance(value, (float, Decimal)):
        try:
            number = Decimal(str(value))
        except InvalidOperation:
            text = str(value).strip()
        else:
            text = str(int(number)) if number == number.to_integral_value() else str(value)
    else:
        text = str(value).strip()

    if not text:
        return ""
    numeric = re.fullmatch(r"([0-9]+)(?:\.0+)?", text)
    if numeric:
        digits = numeric.group(1)
        return digits.lstrip("0") or "0"
    normalized = text.lstrip("0")
    return normalized or "0"


def money(value: Any) -> Decimal:
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"Invalid payment amount: {value!r}") from exc


def extract_invoice_numbers(value: Any) -> tuple[str, ...]:
    """Extract only bounded standalone 8-10 digit invoice references.

    The source serialization delimiter is intentionally not assumed. Unparsed
    source text remains on ExpectedPayment.raw_invoices.
    """

    text = str(value or "")
    return tuple(dict.fromkeys(re.findall(r"(?<!\d)(\d{8,10})(?!\d)", text)))


def extract_invoice_references(value: Any) -> tuple[tuple[str, ...], str]:
    """Return provisional references plus an explicit interpretation status."""

    text = str(value or "").strip()
    if not text:
        return (), "blank"
    references = extract_invoice_numbers(text)
    if not references:
        return (), "unparsed_preserved_raw"
    residual = re.sub(r"(?<!\d)\d{8,10}(?!\d)", "", text)
    if residual.strip(" ,;/|\t\r\n"):
        return references, "provisional_partial_8_10_digit_tokens"
    return references, "provisional_8_10_digit_tokens"


@dataclass(frozen=True)
class BankPaymentItem:
    item_id: str
    source_row_number: int
    location_key: str
    store_number: str
    deposit_number: str
    item_type: str
    raw_check_number: str
    normalized_check_number: str
    amount: Decimal
    raw_amount: str
    source_record_sha256: str


@dataclass(frozen=True)
class SignatureEvidence:
    customer_number: str
    invoice_number: str
    signer_name: str
    filename: str
    created_at: str
    uploaded_at: str
    rrn: str

    @property
    def evidence_status(self) -> str:
        if self.filename:
            return "signature_image_available"
        return "signature_record_without_image"


@dataclass(frozen=True)
class ExpectedPayment:
    payment_id: str
    customer_number: str
    route: str
    payment_type: str
    raw_check_number: str
    normalized_check_number: str
    amount: Decimal
    authorization_number: str = ""
    notes: str = ""
    raw_invoices: str = ""
    invoice_numbers: tuple[str, ...] = ()
    invoice_reference_status: str = "blank"
    received: str = ""
    received_at: str = ""
    created_at: str = ""


@dataclass(frozen=True)
class MatchCandidate:
    expected_payment: ExpectedPayment
    matched_factors: tuple[str, ...]
    conflicting_factors: tuple[str, ...]
    candidate_tier: str
    signatures: tuple[SignatureEvidence, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self.expected_payment)
        payload["amount"] = str(self.expected_payment.amount)
        if self.expected_payment.invoice_reference_status != "provisional_8_10_digit_tokens":
            signature_lookup_status = "SIGNATURE_UNDETERMINED"
        elif self.signatures:
            signature_lookup_status = "SIGNATURE_EVIDENCE_FOUND"
        else:
            signature_lookup_status = "SIGNATURE_EVIDENCE_NOT_FOUND"
        payload.update(
            {
                "matched_factors": list(self.matched_factors),
                "conflicting_factors": list(self.conflicting_factors),
                "candidate_tier": self.candidate_tier,
                "signature_lookup_status": signature_lookup_status,
                "signatures": [
                    {**asdict(item), "evidence_status": item.evidence_status}
                    for item in self.signatures
                ],
            }
        )
        return payload


@dataclass(frozen=True)
class MatchDecision:
    disposition: str
    tier: str
    selected_payment_id: str | None
    candidates: tuple[MatchCandidate, ...]
    warnings: tuple[str, ...] = ()
    rule_version: str = MATCH_RULE_VERSION
    source_complete: bool = True
    candidate_total_count: int = 0
    candidate_display_cap: int = 0
    candidate_population_complete: bool = True
    cross_run_reuse_evidence: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.candidates and self.candidate_total_count == 0:
            object.__setattr__(self, "candidate_total_count", len(self.candidates))
        if self.candidates and self.candidate_display_cap == 0:
            object.__setattr__(self, "candidate_display_cap", len(self.candidates))

    def to_dict(self) -> dict[str, Any]:
        return {
            "disposition": self.disposition,
            "tier": self.tier,
            "selected_payment_id": self.selected_payment_id,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "warnings": list(self.warnings),
            "rule_version": self.rule_version,
            "source_complete": self.source_complete,
            "candidate_total_count": self.candidate_total_count,
            "candidate_display_cap": self.candidate_display_cap,
            "candidate_population_complete": self.candidate_population_complete,
            "cross_run_reuse_evidence": [
                dict(item) for item in self.cross_run_reuse_evidence
            ],
        }


def _candidate(
    payment: ExpectedPayment,
    bank_item: BankPaymentItem,
    *,
    tier: str,
) -> MatchCandidate:
    matched = ["location_route_date_scope"]
    conflicts: list[str] = []
    if payment.normalized_check_number == bank_item.normalized_check_number:
        matched.append("normalized_check_number")
    else:
        conflicts.append("normalized_check_number")
    if payment.amount == bank_item.amount:
        matched.append("amount")
    else:
        conflicts.append("amount")
    return MatchCandidate(
        expected_payment=payment,
        matched_factors=tuple(matched),
        conflicting_factors=tuple(conflicts),
        candidate_tier=tier,
    )


def match_payment_item(
    bank_item: BankPaymentItem,
    expected_payments: Sequence[ExpectedPayment],
    *,
    source_complete: bool = True,
    max_amount_review_candidates: int = 25,
) -> MatchDecision:
    """Match one bank item without fuzzy selection or hidden tie-breaking.

    The caller supplies the already bounded location/route/date population.
    Amount may disambiguate repeated check numbers only when it leaves one
    candidate. Date, RECEIVED, customer, invoice, and signature evidence never
    break a tie between otherwise equal check+amount candidates.
    """

    ordered = sorted(
        expected_payments,
        key=lambda item: (
            item.normalized_check_number,
            item.amount,
            item.created_at,
            item.payment_id,
        ),
    )
    if not source_complete:
        exact = [
            _candidate(item, bank_item, tier="T0_SOURCE_INCOMPLETE")
            for item in ordered
            if bank_item.normalized_check_number
            and item.normalized_check_number == bank_item.normalized_check_number
        ]
        return MatchDecision(
            disposition="SOURCE_INCOMPLETE",
            tier="T0_SOURCE_INCOMPLETE",
            selected_payment_id=None,
            candidates=tuple(exact),
            warnings=(
                "The bounded ERP population was incomplete; no automatic selection was made.",
            ),
            source_complete=False,
        )

    exact_check = [
        item
        for item in ordered
        if bank_item.normalized_check_number
        and item.normalized_check_number == bank_item.normalized_check_number
    ]
    if len(exact_check) == 1:
        only = exact_check[0]
        if only.amount == bank_item.amount:
            candidate = _candidate(only, bank_item, tier="T1_EXACT_CHECK_AMOUNT")
            return MatchDecision(
                disposition="EXACT_UNIQUE",
                tier="T1_EXACT_CHECK_AMOUNT",
                selected_payment_id=only.payment_id,
                candidates=(candidate,),
            )
        candidate = _candidate(only, bank_item, tier="T3_CHECK_AMOUNT_CONFLICT")
        return MatchDecision(
            disposition="AMOUNT_CONFLICT",
            tier="T3_CHECK_AMOUNT_CONFLICT",
            selected_payment_id=None,
            candidates=(candidate,),
            warnings=("The normalized check number matched, but the amount did not.",),
        )

    if len(exact_check) > 1:
        check_and_amount = [
            item for item in exact_check if item.amount == bank_item.amount
        ]
        if len(check_and_amount) == 1:
            only = check_and_amount[0]
            candidates = tuple(
                _candidate(item, bank_item, tier="T2_AMOUNT_DISAMBIGUATED_CHECK")
                for item in exact_check
            )
            return MatchDecision(
                disposition="EXACT_AMOUNT_DISAMBIGUATED",
                tier="T2_AMOUNT_DISAMBIGUATED_CHECK",
                selected_payment_id=only.payment_id,
                candidates=candidates,
                warnings=(
                    "The check number repeated in scope; exact amount left one candidate.",
                ),
            )
        candidates = tuple(
            _candidate(item, bank_item, tier="T3_AMBIGUOUS_EXACT_CHECK")
            for item in exact_check
        )
        warning = (
            "Multiple in-scope Payment Notes have the same normalized check and amount."
            if len(check_and_amount) > 1
            else "The check number repeated in scope and none matched the bank amount."
        )
        return MatchDecision(
            disposition="AMBIGUOUS",
            tier="T3_AMBIGUOUS_EXACT_CHECK",
            selected_payment_id=None,
            candidates=candidates,
            warnings=(warning,),
        )

    all_amount_only = [item for item in ordered if item.amount == bank_item.amount]
    amount_only = all_amount_only[:max_amount_review_candidates]
    if amount_only:
        population_complete = len(all_amount_only) <= max_amount_review_candidates
        warnings = [
            "No normalized check matched. Amount-only candidates require human review."
        ]
        if not population_complete:
            warnings.append(
                "Amount-only candidate display is truncated to "
                f"{max_amount_review_candidates} of {len(all_amount_only)}; "
                "candidate acceptance is blocked until the complete population is presented."
            )
        return MatchDecision(
            disposition="AMOUNT_ONLY_REVIEW",
            tier="T4_AMOUNT_ONLY_REVIEW",
            selected_payment_id=None,
            candidates=tuple(
                _candidate(item, bank_item, tier="T4_AMOUNT_ONLY_REVIEW")
                for item in amount_only
            ),
            warnings=tuple(warnings),
            candidate_total_count=len(all_amount_only),
            candidate_display_cap=max_amount_review_candidates,
            candidate_population_complete=population_complete,
        )
    return MatchDecision(
        disposition="UNMATCHED",
        tier="T5_UNMATCHED",
        selected_payment_id=None,
        candidates=(),
        warnings=("No in-scope Payment Note matched the check number or amount.",),
    )


def block_cross_run_reuse(
    decision: MatchDecision,
    prior_uses: Sequence[Mapping[str, Any]],
) -> MatchDecision:
    """Fail closed when an automatic selection was used by an earlier run.

    Cross-run reuse policy is deliberately unresolved. Prior-use evidence is
    presented for human investigation, but it never silently chooses whether
    the earlier or current association is correct.
    """

    selected = decision.selected_payment_id
    relevant = tuple(
        dict(item)
        for item in prior_uses
        if selected and str(item.get("payment_id") or "") == selected
    )
    if not relevant:
        return decision
    return MatchDecision(
        disposition="CROSS_RUN_REUSE_POLICY_UNRESOLVED",
        tier="T0_CROSS_RUN_REUSE_POLICY_UNRESOLVED",
        selected_payment_id=None,
        candidates=decision.candidates,
        warnings=decision.warnings
        + (
            "The selected Payment Note appears in prior run evidence; cross-run reuse policy is unresolved and selection is blocked.",
        ),
        rule_version=decision.rule_version,
        source_complete=decision.source_complete,
        candidate_total_count=decision.candidate_total_count,
        candidate_display_cap=decision.candidate_display_cap,
        candidate_population_complete=decision.candidate_population_complete,
        cross_run_reuse_evidence=relevant,
    )


def enrich_signatures(
    decision: MatchDecision,
    signatures: Mapping[tuple[str, str], Sequence[SignatureEvidence]],
) -> MatchDecision:
    """Attach signature evidence without changing disposition or selection."""

    enriched: list[MatchCandidate] = []
    for candidate in decision.candidates:
        payment = candidate.expected_payment
        evidence: list[SignatureEvidence] = []
        for invoice in payment.invoice_numbers:
            evidence.extend(signatures.get((payment.customer_number, invoice), ()))
        # Stable presentation only. Timestamp fields have no ordering or
        # precedence semantics until their source time zones are governed.
        evidence.sort(key=lambda item: (item.rrn, item.filename, item.created_at, item.uploaded_at))
        enriched.append(
            MatchCandidate(
                expected_payment=payment,
                matched_factors=candidate.matched_factors,
                conflicting_factors=candidate.conflicting_factors,
                candidate_tier=candidate.candidate_tier,
                signatures=tuple(evidence),
            )
        )
    return MatchDecision(
        disposition=decision.disposition,
        tier=decision.tier,
        selected_payment_id=decision.selected_payment_id,
        candidates=tuple(enriched),
        warnings=decision.warnings,
        rule_version=decision.rule_version,
        source_complete=decision.source_complete,
        candidate_total_count=decision.candidate_total_count,
        candidate_display_cap=decision.candidate_display_cap,
        candidate_population_complete=decision.candidate_population_complete,
        cross_run_reuse_evidence=decision.cross_run_reuse_evidence,
    )


def enforce_deposit_one_to_one(
    decisions: Mapping[str, MatchDecision],
) -> dict[str, MatchDecision]:
    """Prevent one WHSIGPAY identity from satisfying multiple bank items.

    This does not greedily solve ambiguous graphs. Any per-item ambiguity stays
    ambiguous, and duplicate automatic reservations are returned to review.
    """

    reservations: dict[str, list[str]] = {}
    for item_id, decision in decisions.items():
        if decision.selected_payment_id:
            reservations.setdefault(decision.selected_payment_id, []).append(item_id)
    conflicted = {
        item_id
        for item_ids in reservations.values()
        if len(item_ids) > 1
        for item_id in item_ids
    }
    result = dict(decisions)
    for item_id in sorted(conflicted):
        prior = decisions[item_id]
        result[item_id] = MatchDecision(
            disposition="AMBIGUOUS_ASSIGNMENT",
            tier="T3_DEPOSIT_ASSIGNMENT_CONFLICT",
            selected_payment_id=None,
            candidates=prior.candidates,
            warnings=prior.warnings
            + (
                "The same Payment Note would satisfy multiple bank items in this deposit; no assignment was made.",
            ),
            rule_version=prior.rule_version,
            source_complete=prior.source_complete,
            candidate_total_count=prior.candidate_total_count,
            candidate_display_cap=prior.candidate_display_cap,
            candidate_population_complete=prior.candidate_population_complete,
            cross_run_reuse_evidence=prior.cross_run_reuse_evidence,
        )
    return result


__all__ = [
    "BankPaymentItem",
    "ExpectedPayment",
    "INVOICE_EXTRACTION_RULE_VERSION",
    "MATCH_RULE_VERSION",
    "MatchCandidate",
    "MatchDecision",
    "SignatureEvidence",
    "block_cross_run_reuse",
    "enrich_signatures",
    "enforce_deposit_one_to_one",
    "extract_invoice_references",
    "extract_invoice_numbers",
    "match_payment_item",
    "money",
    "normalize_check_number",
]
