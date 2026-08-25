from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import fitz

from invoice_number_rules import ERP_INVOICE_RULE_VERSION

from .check_understanding import extract_customer_identity
from .ocr_engine import configure_tesseract, ocr_region
from .page_classifier import classify_page
from .pnc_lockbox_contract import (
    PNC_LOCKBOX_HEADER_RULE_VERSION,
    PNC_LOCKBOX_IDENTIFIER_PATTERN,
)
from .region_detector import find_check_regions
from .resolution.payer_parser import (
    check_customer_account_directives,
    check_for_customer_directives,
)
from .remittance_understanding import (
    AllocationCandidate,
    RejectedRemittanceCandidate,
    extract_km_statement_customer_directives,
    extract_remittance_evidence,
)


configure_tesseract()


EXTRACTION_VERSION = "pnc-lockbox-parser@0.7.0-r75.1"
DEFAULT_OCR_WORKERS = 6
MAX_OCR_WORKERS = 8

TRANSACTION_RE = re.compile(
    r"Transaction Information\s+"
    r"(?P<transaction>G-\d+)\s+"
    rf"(?P<lockbox>{PNC_LOCKBOX_IDENTIFIER_PATTERN})\s+"
    r"(?P<date>\d{4}/\d{2}/\d{2})",
    re.IGNORECASE,
)


@dataclass
class Allocation:
    invoice_number: str
    net_invoice_amount: float
    invoice_page: str
    confidence: float = 0.75
    raw_invoice_candidates: tuple[str, ...] = ()
    extraction_source: str = "embedded_text"
    ocr_psm: int | None = None


@dataclass
class PageRemittanceEvidence:
    allocations: list[AllocationCandidate] = field(default_factory=list)
    rejected_candidates: list[RejectedRemittanceCandidate] = field(
        default_factory=list
    )
    ocr_attempts: list[int] = field(default_factory=list)
    ocr_errors: list[str] = field(default_factory=list)
    statement_customer_directives: list[dict[str, str]] = field(
        default_factory=list
    )
    page_class: str = "unknown"
    extraction_complete: bool = False


@dataclass
class Transaction:
    transaction_id: str
    envelope_number: int | None = None
    lockbox: str = ""
    date: str = ""
    batch: int | None = None
    batch_item: int | None = None
    check_number: str = ""
    check_amount: float = 0.0
    aba_routing: str = ""
    account_number: str = ""
    printed_customer_number: str = ""
    printed_customer_number_evidence: str = ""
    printed_customer_number_candidates: list[str] = field(default_factory=list)
    for_customer_number: str = ""
    for_customer_number_evidence: str = ""
    for_customer_number_candidates: list[str] = field(default_factory=list)
    statement_customer_number: str = ""
    statement_customer_number_evidence: str = ""
    statement_customer_number_candidates: list[str] = field(
        default_factory=list
    )

    customer_name: str = ""
    customer_phone: str = ""
    customer_address_line_1: str = ""
    customer_address_line_2: str = ""
    customer_city: str = ""
    customer_state: str = ""
    customer_postal_code: str = ""
    customer_identity_confidence: float = 0.0
    customer_identity_evidence: list[str] = field(default_factory=list)
    customer_identity_block: dict[str, float] = field(default_factory=dict)
    check_region: dict[str, float] = field(default_factory=dict)
    customer_identity_strategy: str = ""
    customer_identity_attempts: list[dict[str, Any]] = field(
        default_factory=list
    )

    allocations: list[Allocation] = field(default_factory=list)
    check_page: int | None = None
    remittance_pages: list[int] = field(default_factory=list)
    remittance_pages_examined: list[int] = field(default_factory=list)
    remittance_candidate_pages: list[int] = field(default_factory=list)
    ocr_attempted_pages: list[int] = field(default_factory=list)
    ocr_successful_pages: list[int] = field(default_factory=list)
    ocr_attempts: list[dict[str, int]] = field(default_factory=list)
    rejected_remittance_candidates: list[dict[str, Any]] = field(
        default_factory=list
    )
    remittance_incomplete_pages: list[int] = field(default_factory=list)
    remittance_ocr_errors: list[str] = field(default_factory=list)
    remittance_evidence_complete: bool = False
    transaction_boundary_rule: str = "next_transaction_information"
    transaction_boundary_closed: bool = False

    def merge_allocations(
        self,
        candidates: list[AllocationCandidate],
    ) -> None:
        """Merge transaction-wide evidence without hiding page conflicts."""

        for candidate in candidates:
            invoice = candidate.invoice_number
            already_conflicted = any(
                rejection.get("reason")
                == "conflicting_cross_page_amount"
                and invoice in rejection.get("raw_invoice_candidates", [])
                for rejection in self.rejected_remittance_candidates
            )
            if already_conflicted:
                continue
            current = next(
                (
                    item
                    for item in self.allocations
                    if item.invoice_number == invoice
                ),
                None,
            )
            if current is None:
                self.allocations.append(
                    Allocation(
                        invoice_number=invoice,
                        net_invoice_amount=candidate.net_invoice_amount,
                        invoice_page=candidate.invoice_page,
                        confidence=candidate.confidence,
                        raw_invoice_candidates=(
                            candidate.raw_invoice_candidates
                        ),
                        extraction_source=candidate.extraction_source,
                        ocr_psm=candidate.ocr_psm,
                    )
                )
                continue
            if abs(
                current.net_invoice_amount - candidate.net_invoice_amount
            ) <= 0.01:
                pages = list(
                    dict.fromkeys(
                        filter(
                            None,
                            (
                                *current.invoice_page.split(","),
                                candidate.invoice_page,
                            ),
                        )
                    )
                )
                current.invoice_page = ",".join(pages)
                continue

            self.allocations = [
                item
                for item in self.allocations
                if item.invoice_number != invoice
            ]
            for item in (current, candidate):
                rejection = {
                    "raw_invoice_candidates": list(
                        item.raw_invoice_candidates or (invoice,)
                    ),
                    "net_invoice_amount": item.net_invoice_amount,
                    "invoice_page": item.invoice_page,
                    "reason": "conflicting_cross_page_amount",
                    "extraction_source": item.extraction_source,
                    "ocr_psm": item.ocr_psm,
                }
                if rejection not in self.rejected_remittance_candidates:
                    self.rejected_remittance_candidates.append(rejection)

    def apply_customer_identity(
        self,
        identity,
        *,
        strategy: str = "detected_check_image",
        attempts: list[dict[str, Any]] | None = None,
    ) -> None:
        for key, value in identity.as_transaction_fields().items():
            if key in {
                "customer_identity_confidence",
                "customer_identity_evidence",
                "customer_identity_block",
                "check_region",
            }:
                setattr(self, key, value)
            elif not getattr(self, key) and value:
                setattr(self, key, value)
        self.customer_identity_strategy = strategy
        self.customer_identity_attempts = list(attempts or [])

    def merge_statement_customer_directives(
        self,
        directives: list[dict[str, str]],
    ) -> None:
        evidence_by_number = {
            str(number or "").strip(): str(
                self.statement_customer_number_evidence or ""
            ).strip()
            for number in self.statement_customer_number_candidates
            if str(number or "").strip()
        }
        for directive in directives:
            number = str(directive.get("customer_number") or "").strip()
            evidence = str(directive.get("evidence_text") or "").strip()
            if number and number not in evidence_by_number:
                evidence_by_number[number] = evidence
        self.statement_customer_number_candidates = sorted(evidence_by_number)
        if len(evidence_by_number) == 1:
            number, evidence = next(iter(evidence_by_number.items()))
            self.statement_customer_number = number
            self.statement_customer_number_evidence = evidence
        else:
            self.statement_customer_number = ""
            self.statement_customer_number_evidence = ""

    def serialize(self) -> dict[str, Any]:
        self.remittance_evidence_complete = bool(
            self.allocations
            and self.transaction_boundary_closed
            and not self.rejected_remittance_candidates
            and not self.remittance_incomplete_pages
            and not self.remittance_ocr_errors
        )
        allocation_total = round(
            sum(item.net_invoice_amount for item in self.allocations),
            2,
        )
        difference = round(self.check_amount - allocation_total, 2)
        balanced = bool(self.allocations) and abs(difference) <= 0.01

        if balanced:
            status = "balanced"
        elif not self.allocations:
            status = "no_remittance"
        else:
            status = "review_required"

        payload = asdict(self)
        payload.update(
            {
                "original_allocations": [
                    asdict(item) for item in self.allocations
                ],
                "allocation_total": allocation_total,
                "difference": difference,
                "balanced": balanced,
                "status": status,
                "reviewer": "",
                "notes": "",
                "override_reason": "",
            }
        )
        return payload


def _line_value(text: str, label: str) -> str:
    match = re.search(
        rf"{re.escape(label)}\s+([^\n]+)",
        text,
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def _first_number(value: str) -> str:
    match = re.search(r"\d+", value)
    return match.group(0) if match else ""


def _transaction_from_page(
    embedded_text: str,
    page_number: int,
) -> Transaction | None:
    match = TRANSACTION_RE.search(embedded_text)

    if not match:
        return None

    reported = re.search(
        r"Reported Amount\s+\$\s*([\d,]+\.\d{2})",
        embedded_text,
        re.IGNORECASE,
    )

    transaction = Transaction(
        transaction_id=match.group("transaction"),
        lockbox=match.group("lockbox"),
        date=match.group("date"),
        check_page=page_number,
    )

    transaction.batch = int(
        _first_number(_line_value(embedded_text, "Batch")) or 0
    ) or None

    transaction.batch_item = int(
        _first_number(_line_value(embedded_text, "Batch Item")) or 0
    ) or None

    transaction.envelope_number = int(
        _first_number(_line_value(embedded_text, "Env Num")) or 0
    ) or None

    transaction.check_number = _first_number(
        _line_value(embedded_text, "Check Number")
    )
    transaction.aba_routing = _first_number(
        _line_value(embedded_text, "Transit")
    )
    transaction.account_number = _first_number(
        _line_value(embedded_text, "Account")
    )

    if reported:
        transaction.check_amount = float(
            reported.group(1).replace(",", "")
        )

    return transaction


def _meaningful_embedded_text(page: fitz.Page) -> tuple[str, str]:
    embedded = page.get_text("text").strip()
    meaningful = re.sub(
        r"Output Report.*?page\s+\d+",
        "",
        embedded,
        flags=re.IGNORECASE | re.DOTALL,
    ).strip()
    return embedded, meaningful


def _has_substantial_image(page: fitz.Page) -> bool:
    page_area = max(float(page.rect.width * page.rect.height), 1.0)
    for image in page.get_images(full=True):
        xref = image[0]
        for rect in page.get_image_rects(xref):
            image_area = max(float(rect.width * rect.height), 0.0)
            if image_area / page_area >= 0.10:
                return True
    return False


def _merge_rejections(
    *groups: list[RejectedRemittanceCandidate],
) -> list[RejectedRemittanceCandidate]:
    merged: list[RejectedRemittanceCandidate] = []
    seen: set[tuple[Any, ...]] = set()
    for group in groups:
        for item in group:
            key = (
                item.raw_invoice_candidates,
                item.net_invoice_amount,
                item.invoice_page,
                item.reason,
                item.extraction_source,
                item.ocr_psm,
            )
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def _merge_statement_directives(
    *groups: list[dict[str, str]],
) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            number = str(item.get("customer_number") or "").strip()
            if not number or number in seen:
                continue
            seen.add(number)
            merged.append(dict(item))
    return merged


def _merge_allocations(
    *groups: list[AllocationCandidate],
) -> tuple[list[AllocationCandidate], list[RejectedRemittanceCandidate]]:
    """Merge extraction modes without hiding cross-source disagreement."""

    selected: dict[str, AllocationCandidate] = {}
    conflicted: set[str] = set()
    conflicts: list[RejectedRemittanceCandidate] = []
    for group in groups:
        for item in group:
            invoice = item.invoice_number
            if invoice in conflicted:
                continue
            current = selected.get(invoice)
            if current is None:
                selected[invoice] = item
                continue
            if abs(current.net_invoice_amount - item.net_invoice_amount) <= 0.01:
                continue
            selected.pop(invoice, None)
            conflicted.add(invoice)
            for candidate in (current, item):
                conflicts.append(
                    RejectedRemittanceCandidate(
                        raw_invoice_candidates=(
                            candidate.raw_invoice_candidates
                            or (candidate.invoice_number,)
                        ),
                        net_invoice_amount=candidate.net_invoice_amount,
                        invoice_page=candidate.invoice_page,
                        reason="conflicting_cross_source_amount",
                        extraction_source=candidate.extraction_source,
                        ocr_psm=candidate.ocr_psm,
                    )
                )
    return list(selected.values()), conflicts


def _ocr_visual_row_text(data: dict[str, Any]) -> str:
    """Rebuild visual table rows when sparse OCR splits their columns.

    Tesseract's sparse-text mode can return an invoice, date, and amount in
    separate logical lines even when they share one visual row.  The normal
    line parser then sees neither a complete invoice/amount pair nor a
    rejection.  This function uses only the word boxes produced by the same
    governed OCR attempt and joins words whose boxes materially overlap on
    the vertical axis.  It never joins adjacent rows or invents a missing
    token.
    """

    texts = list(data.get("text") or [])
    keys = ("left", "top", "width", "height")
    if not texts or any(len(list(data.get(key) or [])) < len(texts) for key in keys):
        return ""

    words: list[dict[str, Any]] = []
    for index, raw_text in enumerate(texts):
        text = " ".join(str(raw_text or "").split())
        if not text:
            continue
        try:
            left = float(data["left"][index])
            top = float(data["top"][index])
            width = max(float(data["width"][index]), 0.0)
            height = max(float(data["height"][index]), 0.0)
        except (IndexError, TypeError, ValueError):
            continue
        if width <= 0 or height <= 0:
            continue
        words.append(
            {
                "text": text,
                "left": left,
                "top": top,
                "right": left + width,
                "bottom": top + height,
                "height": height,
            }
        )

    rows: list[dict[str, Any]] = []
    for word in sorted(words, key=lambda item: (item["top"], item["left"])):
        best_row: dict[str, Any] | None = None
        best_overlap = 0.0
        for row in rows:
            overlap = max(
                0.0,
                min(word["bottom"], row["bottom"])
                - max(word["top"], row["top"]),
            )
            smaller_height = min(word["height"], row["height"])
            overlap_ratio = overlap / smaller_height if smaller_height else 0.0
            if overlap_ratio >= 0.60 and overlap_ratio > best_overlap:
                best_row = row
                best_overlap = overlap_ratio

        if best_row is None:
            rows.append(
                {
                    "words": [word],
                    "top": word["top"],
                    "bottom": word["bottom"],
                    "height": word["height"],
                }
            )
            continue

        best_row["words"].append(word)
        best_row["top"] = min(best_row["top"], word["top"])
        best_row["bottom"] = max(best_row["bottom"], word["bottom"])
        best_row["height"] = best_row["bottom"] - best_row["top"]

    visual_lines: list[str] = []
    seen: set[str] = set()
    for row in sorted(rows, key=lambda item: (item["top"], item["bottom"])):
        row["words"].sort(key=lambda item: (item["left"], item["right"]))
        line = " ".join(item["text"] for item in row["words"]).strip()
        if line and line not in seen:
            seen.add(line)
            visual_lines.append(line)
    return "\n".join(visual_lines)


def _extract_page_remittance_evidence(
    page: fitz.Page,
    page_number: int,
) -> PageRemittanceEvidence:
    embedded, meaningful = _meaningful_embedded_text(page)
    page_class = classify_page(embedded)
    embedded_evidence = extract_remittance_evidence(
        embedded,
        page_number,
        extraction_source="embedded_text",
    )
    embedded_statement_directives = (
        extract_km_statement_customer_directives(embedded)
    )
    substantial_image = _has_substantial_image(page)
    supplemental_scan = bool(
        substantial_image or page_class in {"remittance", "statement"}
    )
    if embedded_evidence.allocations and not supplemental_scan:
        return PageRemittanceEvidence(
            allocations=embedded_evidence.allocations,
            rejected_candidates=embedded_evidence.rejected_candidates,
            statement_customer_directives=embedded_statement_directives,
            page_class=page_class,
            extraction_complete=not embedded_evidence.rejected_candidates,
        )

    should_ocr = bool(
        supplemental_scan
        or len(meaningful) < 80
    )
    if not should_ocr:
        return PageRemittanceEvidence(
            allocations=embedded_evidence.allocations,
            rejected_candidates=embedded_evidence.rejected_candidates,
            statement_customer_directives=embedded_statement_directives,
            page_class=page_class,
            extraction_complete=bool(
                embedded_evidence.allocations
                and not embedded_evidence.rejected_candidates
            ),
        )

    rejections = list(embedded_evidence.rejected_candidates)
    allocation_groups = [list(embedded_evidence.allocations)]
    statement_directive_groups = [embedded_statement_directives]
    attempts: list[int] = []
    errors: list[str] = []
    for psm in (6, 11):
        if psm == 11 and not (
            substantial_image or page_class in {"remittance", "statement"}
        ):
            break
        attempts.append(psm)
        try:
            ocr_result = ocr_region(
                page,
                scale=3.0,
                psm=psm,
                include_data=(psm == 11),
            )
        except Exception as error:
            errors.append(f"PSM {psm}: {type(error).__name__}: {error}")
            continue
        if isinstance(ocr_result, dict):
            ocr_text = _ocr_visual_row_text(ocr_result)
            extraction_source = "ocr_visual_row"
        else:
            ocr_text = str(ocr_result or "")
            extraction_source = "ocr"
        ocr_evidence = extract_remittance_evidence(
            ocr_text,
            page_number,
            extraction_source=extraction_source,
            ocr_psm=psm,
        )
        statement_directive_groups.append(
            extract_km_statement_customer_directives(ocr_text)
        )
        rejections = _merge_rejections(
            rejections,
            ocr_evidence.rejected_candidates,
        )
        allocation_groups.append(list(ocr_evidence.allocations))

    allocations, conflicts = _merge_allocations(*allocation_groups)
    rejections = _merge_rejections(rejections, conflicts)
    return PageRemittanceEvidence(
        allocations=allocations,
        rejected_candidates=rejections,
        ocr_attempts=attempts,
        ocr_errors=errors,
        statement_customer_directives=_merge_statement_directives(
            *statement_directive_groups
        ),
        page_class=page_class,
        extraction_complete=bool(
            allocations and not rejections and not errors
        ),
    )


def _identity_phone(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) == 11 and digits.startswith("1"):
        return digits[1:]
    return digits


def _identity_postal(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))[:5]


def _identity_rank(identity) -> tuple[int, int, int, int, int, int, float]:
    explicit_account = bool(identity.printed_customer_number)
    exact_phone = len(_identity_phone(identity.customer_phone)) == 10
    exact_postal = len(_identity_postal(identity.customer_postal_code)) == 5
    return (
        int(explicit_account),
        int(exact_phone and exact_postal),
        int(exact_phone),
        int(exact_postal),
        int(bool(identity.customer_address_line_1)),
        int(bool(identity.customer_name)),
        float(identity.confidence),
    )


def _complete_payer_identity(identity) -> bool:
    rank = _identity_rank(identity)
    # A payee name can appear inside the detected check crop while the actual
    # payer block sits elsewhere in the same check image.  Phone + ZIP + any
    # name therefore cannot close the search: the name may still be the stale
    # payee assertion.  A street anchor is required before the primary crop is
    # treated as a complete payer identity.  When no region contains a street,
    # every bounded region is still compared and the strongest evidence wins.
    return bool(rank[0] or (rank[1] and rank[4]))


def _extract_transaction_customer_identity(page, embedded_text: str):
    """Read the primary check crop, then bounded fallbacks when incomplete."""

    attempts: list[dict[str, Any]] = []
    identities: list[tuple[str, Any]] = []
    regions = find_check_regions(page, embedded_text)
    search_exhausted = True
    for index, (strategy, region) in enumerate(regions):
        identity = extract_customer_identity(page, region)
        identities.append((strategy, identity))
        attempts.append(
            {
                "strategy": strategy,
                "region": {
                    "x0": region.x0,
                    "y0": region.y0,
                    "x1": region.x1,
                    "y1": region.y1,
                },
                "confidence": identity.confidence,
                "printed_customer_number_present": bool(
                    identity.printed_customer_number
                ),
                "printed_customer_number_candidate_count": len(
                    identity.printed_customer_number_candidates
                ),
                "exact_phone_present": (
                    len(_identity_phone(identity.customer_phone)) == 10
                ),
                "five_digit_zip_present": (
                    len(_identity_postal(identity.customer_postal_code)) == 5
                ),
                "street_present": bool(identity.customer_address_line_1),
                "name_present": bool(identity.customer_name),
                "evidence": list(identity.evidence),
            }
        )
        if (
            index == 0
            and _complete_payer_identity(identity)
            and not identity.printed_customer_number_candidates
        ):
            search_exhausted = False
            break

    if not identities:
        raise ValueError("No bounded check-image region was available.")
    strategy, identity = max(
        identities,
        key=lambda item: _identity_rank(item[1]),
    )
    directive_evidence: dict[str, str] = {}
    for_directive_evidence: dict[str, str] = {}
    for _, candidate_identity in identities:
        numbers = candidate_identity.printed_customer_number_candidates
        if not numbers and candidate_identity.printed_customer_number:
            numbers = [candidate_identity.printed_customer_number]
        for number in numbers:
            normalized = str(number or "").strip()
            if normalized and normalized not in directive_evidence:
                directive_evidence[normalized] = str(
                    candidate_identity.printed_customer_number_evidence or ""
                )
        for_numbers = candidate_identity.for_customer_number_candidates
        if not for_numbers and candidate_identity.for_customer_number:
            for_numbers = [candidate_identity.for_customer_number]
        for number in for_numbers:
            normalized = str(number or "").strip()
            if normalized and normalized not in for_directive_evidence:
                for_directive_evidence[normalized] = str(
                    candidate_identity.for_customer_number_evidence or ""
                )

    broad_region = next(
        (
            region
            for candidate_strategy, region in regions
            if candidate_strategy == "below_label_full_width"
        ),
        regions[-1][1],
    )

    # The structured OCR path intentionally filters low-confidence tokens and
    # groups them by Tesseract line metadata for customer-name parsing.  On
    # real check scans that can discard a separator or place ``Account`` and
    # its number in different blocks even though image-to-string still reads
    # the instruction correctly.  Only after every bounded identity region
    # has failed to yield a customer number, run one raw-text pass over the
    # governed full-width check region.  This remains check-bounded, requires
    # a six-digit customer number, and retains the existing bank-context
    # exclusions in ``check_customer_account_directives``.
    if (
        not directive_evidence
        and search_exhausted
        and not _complete_payer_identity(identity)
    ):
        for psm in (6, 11):
            try:
                raw_text = str(
                    ocr_region(
                        page,
                        clip=broad_region.to_rect(),
                        scale=4.0,
                        psm=psm,
                        include_data=False,
                    )
                    or ""
                )
                raw_directives = check_customer_account_directives(raw_text)
                attempts.append(
                    {
                        "strategy": "bounded_raw_account_fallback",
                        "region": {
                            "x0": broad_region.x0,
                            "y0": broad_region.y0,
                            "x1": broad_region.x1,
                            "y1": broad_region.y1,
                        },
                        "psm": psm,
                        "printed_customer_number_candidate_count": len(
                            {
                                str(item.get("customer_number") or "").strip()
                                for item in raw_directives
                                if str(
                                    item.get("customer_number") or ""
                                ).strip()
                            }
                        ),
                        "ocr_error": "",
                    }
                )
            except Exception as error:
                attempts.append(
                    {
                        "strategy": "bounded_raw_account_fallback",
                        "region": {
                            "x0": broad_region.x0,
                            "y0": broad_region.y0,
                            "x1": broad_region.x1,
                            "y1": broad_region.y1,
                        },
                        "psm": psm,
                        "printed_customer_number_candidate_count": 0,
                        "ocr_error": f"{type(error).__name__}: {error}",
                    }
                )
                continue
            for directive in raw_directives:
                normalized = str(
                    directive.get("customer_number") or ""
                ).strip()
                if normalized and normalized not in directive_evidence:
                    directive_evidence[normalized] = str(
                        directive.get("evidence_text") or ""
                    ).strip()
            if raw_directives:
                break

    # The check's handwritten FOR line is the final customer-number evidence
    # source. It remains separate from stronger apply/account directives so
    # invoice ownership and K&M statement evidence retain priority. Only when
    # no stronger check account was found, focus OCR on the lower check band
    # containing FOR/MEMO content and preserve every six- or seven-digit
    # candidate (MaddenCo TMCUST.CUNUMBER is decimal(7,0)).
    if (
        not directive_evidence
        and not for_directive_evidence
        and search_exhausted
        and not _complete_payer_identity(identity)
    ):
        for_band = fitz.Rect(
            broad_region.x0,
            broad_region.y0 + broad_region.height * 0.42,
            broad_region.x1,
            broad_region.y0 + broad_region.height * 0.93,
        )
        for psm in (6, 7, 11, 13):
            try:
                raw_for_text = str(
                    ocr_region(
                        page,
                        clip=for_band,
                        scale=6.0,
                        psm=psm,
                        include_data=False,
                    )
                    or ""
                )
                raw_for_directives = check_for_customer_directives(
                    raw_for_text
                )
                attempts.append(
                    {
                        "strategy": "bounded_for_line_fallback",
                        "region": {
                            "x0": for_band.x0,
                            "y0": for_band.y0,
                            "x1": for_band.x1,
                            "y1": for_band.y1,
                        },
                        "psm": psm,
                        "for_customer_number_candidate_count": len(
                            {
                                str(
                                    item.get("customer_number") or ""
                                ).strip()
                                for item in raw_for_directives
                                if str(
                                    item.get("customer_number") or ""
                                ).strip()
                            }
                        ),
                        "ocr_error": "",
                    }
                )
            except Exception as error:
                attempts.append(
                    {
                        "strategy": "bounded_for_line_fallback",
                        "region": {
                            "x0": for_band.x0,
                            "y0": for_band.y0,
                            "x1": for_band.x1,
                            "y1": for_band.y1,
                        },
                        "psm": psm,
                        "for_customer_number_candidate_count": 0,
                        "ocr_error": f"{type(error).__name__}: {error}",
                    }
                )
                continue
            for directive in raw_for_directives:
                normalized = str(
                    directive.get("customer_number") or ""
                ).strip()
                if normalized and normalized not in for_directive_evidence:
                    for_directive_evidence[normalized] = str(
                        directive.get("evidence_text") or ""
                    ).strip()
            if raw_for_directives:
                break
    identity.printed_customer_number_candidates = sorted(directive_evidence)
    if len(directive_evidence) == 1:
        number, evidence_text = next(iter(directive_evidence.items()))
        identity.printed_customer_number = number
        identity.printed_customer_number_evidence = evidence_text
    else:
        identity.printed_customer_number = ""
        identity.printed_customer_number_evidence = ""
    identity.for_customer_number_candidates = sorted(for_directive_evidence)
    if len(for_directive_evidence) == 1:
        number, evidence_text = next(iter(for_directive_evidence.items()))
        identity.for_customer_number = number
        identity.for_customer_number_evidence = evidence_text
    else:
        identity.for_customer_number = ""
        identity.for_customer_number_evidence = ""
    if strategy != "detected_check_image":
        identity.evidence = list(
            dict.fromkeys(
                (*identity.evidence, "bounded check-region fallback")
            )
        )
    return identity, strategy, attempts


def _ocr_worker_count() -> int:
    raw = os.getenv("ETOP_LOCKBOX_OCR_WORKERS", "").strip()
    try:
        requested = int(raw) if raw else DEFAULT_OCR_WORKERS
    except ValueError:
        requested = DEFAULT_OCR_WORKERS
    return max(1, min(requested, MAX_OCR_WORKERS))


def _extract_planned_page(
    pdf_path: Path,
    page_number: int,
    task_type: str,
    embedded_text: str,
):
    """Open one worker-local PDF handle and extract one governed page.

    PyMuPDF page objects are not shared between threads. Each task gets its
    own short-lived document handle, while Tesseract performs the unchanged
    region/PSM work. Results are merged later in original page order.
    """

    with fitz.open(pdf_path) as document:
        page = document[page_number - 1]
        if task_type == "identity":
            return _extract_transaction_customer_identity(
                page,
                embedded_text,
            )
        return _extract_page_remittance_evidence(page, page_number)


def parse_pnc_lockbox(pdf_path: str | Path) -> dict[str, Any]:
    pdf_path = Path(pdf_path)
    transactions: list[Transaction] = []
    warnings: list[str] = []
    ocr_pages: list[int] = []
    planned_pages: list[tuple[str, int, int, str]] = []
    active_index: int | None = None

    with fitz.open(pdf_path) as document:
        for page_number, page in enumerate(document, start=1):
            embedded_text = page.get_text("text").strip()
            page_type = classify_page(embedded_text)

            if page_type == "transaction":
                detected = _transaction_from_page(
                    embedded_text,
                    page_number,
                )
                if detected is None:
                    continue
                if active_index is not None:
                    transactions[active_index].transaction_boundary_closed = True
                transactions.append(detected)
                active_index = len(transactions) - 1
                planned_pages.append(
                    ("identity", page_number, active_index, embedded_text)
                )
                continue

            if active_index is None:
                continue
            transactions[active_index].remittance_pages_examined.append(
                page_number
            )
            planned_pages.append(
                ("remittance", page_number, active_index, embedded_text)
            )

    if active_index is not None:
        transactions[active_index].transaction_boundary_closed = True

    worker_count = min(_ocr_worker_count(), len(planned_pages) or 1)
    with ThreadPoolExecutor(
        max_workers=worker_count,
        thread_name_prefix="etop-lockbox-ocr",
    ) as executor:
        futures = [
            executor.submit(
                _extract_planned_page,
                pdf_path,
                page_number,
                task_type,
                embedded_text,
            )
            for task_type, page_number, _, embedded_text in planned_pages
        ]

        # Merge in immutable source-page order even though OCR completes out
        # of order. This keeps transaction evidence and warnings deterministic.
        for planned, future in zip(planned_pages, futures, strict=True):
            task_type, page_number, transaction_index, _ = planned
            active = transactions[transaction_index]
            extracted = future.result()
            if task_type == "identity":
                identity, identity_strategy, identity_attempts = extracted
                active.apply_customer_identity(
                    identity,
                    strategy=identity_strategy,
                    attempts=identity_attempts,
                )
                if identity.confidence < 0.50:
                    warnings.append(
                        f"{active.transaction_id}: customer identity confidence "
                        f"is {identity.confidence:.0%}; reviewer confirmation "
                        "is recommended."
                    )
                continue

            evidence = extracted
            if evidence.statement_customer_directives:
                active.merge_statement_customer_directives(
                    evidence.statement_customer_directives
                )
            if (
                evidence.allocations
                or evidence.rejected_candidates
                or evidence.page_class in {"remittance", "statement"}
            ):
                active.remittance_candidate_pages.append(page_number)
                if not evidence.extraction_complete:
                    active.remittance_incomplete_pages.append(page_number)
            if evidence.ocr_attempts:
                active.ocr_attempted_pages.append(page_number)
                active.ocr_attempts.extend(
                    {"page": page_number, "psm": psm}
                    for psm in evidence.ocr_attempts
                )
                ocr_pages.append(page_number)
            if evidence.allocations:
                active.remittance_pages.append(page_number)
                if any(
                    item.extraction_source.startswith("ocr")
                    for item in evidence.allocations
                ):
                    active.ocr_successful_pages.append(page_number)
                active.merge_allocations(evidence.allocations)
            active.rejected_remittance_candidates.extend(
                asdict(item)
                for item in evidence.rejected_candidates
            )
            if evidence.ocr_errors:
                active.remittance_ocr_errors.extend(
                    f"page {page_number} {message}"
                    for message in evidence.ocr_errors
                )
                warnings.extend(
                    f"{active.transaction_id}: page {page_number} OCR {message}"
                    for message in evidence.ocr_errors
                )

    serialized = [
        item.serialize()
        for item in transactions
    ]

    for transaction in serialized:
        if transaction["status"] != "balanced":
            warnings.append(
                f'{transaction["transaction_id"]}: '
                f'check {transaction["check_number"] or "unknown"} '
                f'is not balanced. Difference '
                f'${transaction["difference"]:,.2f}.'
            )

    if ocr_pages:
        warnings.append(
            "OCR was used on image-heavy remittance pages: "
            + ", ".join(
                str(page)
                for page in sorted(set(ocr_pages))
            )
        )

    total_check = round(
        sum(
            item["check_amount"]
            for item in serialized
        ),
        2,
    )
    total_allocated = round(
        sum(
            item["allocation_total"]
            for item in serialized
        ),
        2,
    )

    return {
        "parser_version": EXTRACTION_VERSION,
        "extraction_version": EXTRACTION_VERSION,
        "erp_invoice_rule_version": ERP_INVOICE_RULE_VERSION,
        "pnc_lockbox_header_rule_version": (
            PNC_LOCKBOX_HEADER_RULE_VERSION
        ),
        "ocr_worker_count": worker_count,
        "ocr_execution": "bounded_page_pool",
        "source_file_name": pdf_path.name,
        "lockbox": (
            serialized[0]["lockbox"]
            if serialized
            else ""
        ),
        "transaction_date": (
            serialized[0]["date"]
            if serialized
            else ""
        ),
        "transaction_count": len(serialized),
        "allocation_count": sum(
            len(item["allocations"])
            for item in serialized
        ),
        "total_check_amount": total_check,
        "total_allocation_amount": total_allocated,
        "total_difference": round(
            total_check - total_allocated,
            2,
        ),
        "balanced_count": sum(
            1
            for item in serialized
            if item["balanced"]
        ),
        "review_count": sum(
            1
            for item in serialized
            if not item["balanced"]
        ),
        "transactions": serialized,
        "warnings": warnings,
    }


def save_result(
    result: dict[str, Any],
    output_path: str | Path,
) -> None:
    Path(output_path).write_text(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
