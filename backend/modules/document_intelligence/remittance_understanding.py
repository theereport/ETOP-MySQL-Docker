from __future__ import annotations

import re
from dataclasses import dataclass, field

from invoice_number_rules import normalize_erp_invoice

MONEY_RE = re.compile(
    r"(?<!\d)(?:\$?\s*)"
    r"(-?(?:\d{1,3}(?:,\d{3})*|\d+)\.\d{2}-?)"
)
INVOICE_RE = re.compile(r"\b\d{5,12}\b")
LABELED_INVOICE_RE = re.compile(
    r"\b(?:invoice|inv)\s*(?:number|no|#)?\s*[:#-]?\s*"
    r"(?P<value>\d[\d.-]{6,18}\d)\b",
    re.IGNORECASE,
)
_REJECTED_LINE_TERMS = (
    "routing",
    "account",
    "check number",
    "transaction",
    "reported amount",
)

_REMIT_TO_RE = re.compile(
    r"\bremit(?:\s+payment)?\s+to\b",
    re.IGNORECASE,
)
_KM_TIRE_RE = re.compile(
    r"\bk\s*(?:&|and|a|6|g)?\s*m\s+tire(?:\s+inc\.?\b)?",
    re.IGNORECASE,
)
_STATEMENT_PAREN_CUSTOMER_RE = re.compile(
    r"(?P<label>[A-Za-z][A-Za-z0-9&'., /-]{2,120}?)"
    r"\s*\(\s*(?P<number>\d{6,7})\s*\)",
    re.IGNORECASE,
)
_STATEMENT_DASH_CUSTOMER_RE = re.compile(
    r"(?P<label>[A-Za-z][A-Za-z0-9&'., /-]{2,120}?)"
    r"\s*[-\u2013\u2014]\s*[^0-9\r\n]{0,3}"
    r"(?P<number>\d{6,7})\b",
    re.IGNORECASE,
)

@dataclass
class AllocationCandidate:
    invoice_number: str
    net_invoice_amount: float
    invoice_page: str
    confidence: float = 0.72
    raw_invoice_candidates: tuple[str, ...] = ()
    extraction_source: str = "embedded_text"
    ocr_psm: int | None = None


@dataclass
class RejectedRemittanceCandidate:
    raw_invoice_candidates: tuple[str, ...]
    net_invoice_amount: float
    invoice_page: str
    reason: str
    extraction_source: str = "embedded_text"
    ocr_psm: int | None = None


@dataclass
class RemittanceEvidence:
    allocations: list[AllocationCandidate] = field(default_factory=list)
    rejected_candidates: list[RejectedRemittanceCandidate] = field(
        default_factory=list
    )


def _statement_text_windows(text: str) -> list[str]:
    lines = [" ".join(line.split()).strip() for line in str(text or "").splitlines()]
    lines = [line for line in lines if line]
    windows = list(lines)
    windows.extend(
        f"{left} {right}"
        for left, right in zip(lines, lines[1:])
    )
    return windows


def extract_km_statement_customer_directives(
    text: str,
) -> list[dict[str, str]]:
    """Extract K&M customer numbers only from recognizable statement blocks.

    The remit-to heading and K&M Tire identity are both required.  Customer
    numbers must then appear in one of the two governed statement formats:
    ``CUSTOMER NAME (123456)`` or ``CUSTOMER NAME - 123456``, six or seven
    digits (MaddenCo TMCUST.CUNUMBER is decimal(7,0)).  This excludes PO
    boxes, ZIP codes, phone numbers, street numbers, and other bare digits
    in the remit-to address.
    """

    normalized_text = str(text or "")
    remit_match = _REMIT_TO_RE.search(normalized_text)
    km_match = _KM_TIRE_RE.search(normalized_text)
    if not remit_match or not km_match:
        return []
    if km_match.start() < remit_match.start():
        return []

    customer_area = normalized_text[km_match.end():]
    matches: list[dict[str, str]] = []
    seen: set[str] = set()
    for line in _statement_text_windows(customer_area):
        for pattern in (
            _STATEMENT_PAREN_CUSTOMER_RE,
            _STATEMENT_DASH_CUSTOMER_RE,
        ):
            match = pattern.search(line)
            if not match:
                continue
            number = match.group("number")
            if number in seen:
                break
            seen.add(number)
            matches.append(
                {
                    "customer_number": number,
                    "evidence_text": line,
                    "customer_label": " ".join(
                        match.group("label").split()
                    ).strip(" -"),
                }
            )
            break
    return matches

def _money(value: str) -> float:
    normalized = value.replace("$", "").replace(",", "").strip()
    is_negative = normalized.startswith("-") or normalized.endswith("-")
    normalized = normalized.removeprefix("-").removesuffix("-")
    amount = float(normalized)
    return -amount if is_negative else amount


def _mask_money_spans(line: str, matches: list[re.Match[str]]) -> str:
    """Prevent the integer part of a dollar amount becoming an invoice."""

    characters = list(line)
    for match in matches:
        for index in range(match.start(), match.end()):
            characters[index] = " "
    return "".join(characters)


def _invoice_field_candidates(line_without_money: str) -> tuple[str, ...]:
    candidates = list(INVOICE_RE.findall(line_without_money))
    for match in LABELED_INVOICE_RE.finditer(line_without_money):
        candidates.append(match.group("value"))
    return tuple(dict.fromkeys(candidates))


def _governed_candidate_positions(
    line_without_money: str,
) -> list[tuple[int, str]]:
    """Locate governed candidates without changing the shared number rule.

    PNC sometimes renders several invoice/amount columns on one visual line.
    The prior whole-line rule correctly rejected an unstructured
    ``invoice invoice amount`` line, but it also rejected a complete ordered
    ``invoice amount invoice amount`` sequence.  Positions let us treat each
    ordered pair as its own evidence segment while keeping ambiguous layouts
    closed.
    """

    positioned: list[tuple[int, str]] = []
    for match in INVOICE_RE.finditer(line_without_money):
        if invoice := normalize_erp_invoice(match.group(0)):
            positioned.append((match.start(), invoice))
    for match in LABELED_INVOICE_RE.finditer(line_without_money):
        if invoice := normalize_erp_invoice(match.group("value")):
            positioned.append((match.start("value"), invoice))
    return sorted(set(positioned), key=lambda item: (item[0], item[1]))


def _ordered_pair_segments(
    line: str,
    money_matches: list[re.Match[str]],
) -> list[tuple[str, float, tuple[str, ...]]] | None:
    """Return complete horizontal invoice/amount pairs when unambiguous.

    Each governed invoice owns the monetary spans after it and before the
    next governed invoice.  The last amount in that bounded segment is used,
    retaining the established behavior for rows that repeat original,
    balance, and payment columns.  A missing amount or more than one distinct
    governed field inside any segment fails closed to the whole-line rejection
    path.
    """

    masked = _mask_money_spans(line, money_matches)
    positions = _governed_candidate_positions(masked)
    if len({invoice for _, invoice in positions}) <= 1:
        return None

    pairs: list[tuple[str, float, tuple[str, ...]]] = []
    for index, (start, expected_invoice) in enumerate(positions):
        end = positions[index + 1][0] if index + 1 < len(positions) else len(line)
        segment = line[start:end]
        segment_money = list(MONEY_RE.finditer(segment))
        if not segment_money:
            return None
        segment_masked = _mask_money_spans(segment, segment_money)
        raw_candidates = _invoice_field_candidates(segment_masked)
        governed = tuple(
            dict.fromkeys(
                invoice
                for candidate in raw_candidates
                if (invoice := normalize_erp_invoice(candidate))
            )
        )
        if governed != (expected_invoice,):
            return None
        amount = _money(segment_money[-1].group(1))
        if amount == 0:
            return None
        pairs.append((expected_invoice, amount, raw_candidates))
    return pairs


def extract_remittance_evidence(
    text: str,
    page_number: int,
    *,
    extraction_source: str = "embedded_text",
    ocr_psm: int | None = None,
) -> RemittanceEvidence:
    """Extract only uniquely governed invoice rows and retain rejections.

    A monetary span is masked before invoice scanning so an amount such as
    ``12345.67`` cannot contribute the false invoice ``12345``.  The shared
    ERP rule remains authoritative: a row is admitted only when exactly one
    distinct 8/9-digit invoice field survives normalization. Rejected and
    ambiguous raw fields remain available for professional review, but never
    enter allocation arithmetic or ERP matching.
    """

    allocations: list[AllocationCandidate] = []
    rejected: list[RejectedRemittanceCandidate] = []
    seen_allocations: set[tuple[str, float]] = set()
    seen_rejections: set[tuple[tuple[str, ...], float, str]] = set()
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split())
        lowered = line.lower()
        if any(term in lowered for term in _REJECTED_LINE_TERMS):
            continue

        money_matches = list(MONEY_RE.finditer(line))
        if not money_matches:
            continue
        ordered_pairs = _ordered_pair_segments(line, money_matches)
        if ordered_pairs:
            page_reference = f"{page_number};1"
            for invoice, amount, raw_candidates in ordered_pairs:
                allocation_key = (invoice, amount)
                if allocation_key in seen_allocations:
                    continue
                seen_allocations.add(allocation_key)
                allocations.append(
                    AllocationCandidate(
                        invoice_number=invoice,
                        net_invoice_amount=amount,
                        invoice_page=page_reference,
                        raw_invoice_candidates=raw_candidates,
                        extraction_source=extraction_source,
                        ocr_psm=ocr_psm,
                    )
                )
            continue
        raw_candidates = _invoice_field_candidates(
            _mask_money_spans(line, money_matches)
        )
        if not raw_candidates:
            continue

        amount = _money(money_matches[-1].group(1))
        if amount == 0:
            continue

        governed_candidates = tuple(
            dict.fromkeys(
                invoice
                for candidate in raw_candidates
                if (invoice := normalize_erp_invoice(candidate))
            )
        )
        page_reference = f"{page_number};1"
        if len(governed_candidates) != 1:
            reason = (
                "no_governed_invoice_candidate"
                if not governed_candidates
                else "multiple_governed_invoice_candidates"
            )
            rejection_key = (raw_candidates, amount, reason)
            if rejection_key in seen_rejections:
                continue
            seen_rejections.add(rejection_key)
            rejected.append(
                RejectedRemittanceCandidate(
                    raw_invoice_candidates=raw_candidates,
                    net_invoice_amount=amount,
                    invoice_page=page_reference,
                    reason=reason,
                    extraction_source=extraction_source,
                    ocr_psm=ocr_psm,
                )
            )
            continue

        invoice = governed_candidates[0]
        allocation_key = (invoice, amount)
        if allocation_key in seen_allocations:
            continue
        seen_allocations.add(allocation_key)
        allocations.append(
            AllocationCandidate(
                invoice_number=invoice,
                net_invoice_amount=amount,
                invoice_page=page_reference,
                raw_invoice_candidates=raw_candidates,
                extraction_source=extraction_source,
                ocr_psm=ocr_psm,
            )
        )
    return RemittanceEvidence(
        allocations=allocations,
        rejected_candidates=rejected,
    )


def extract_allocations(
    text: str,
    page_number: int,
) -> list[AllocationCandidate]:
    """Compatibility wrapper returning governed allocations only."""

    return extract_remittance_evidence(text, page_number).allocations
