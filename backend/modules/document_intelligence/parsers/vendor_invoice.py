from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import Any, Iterable

from .base import DocumentParser


VENDOR_INVOICE_FIELD_RULE_VERSION = "vendor-invoice-field-rules.v2"


def _pattern(expression: str) -> re.Pattern[str]:
    return re.compile(expression, re.IGNORECASE)


_NUMBER_VALUE_EXPRESSION = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]{1,4})?"
_AMOUNT_VALUE_EXPRESSION = (
    rf"(?:[-+]?\s*[$]?\s*{_NUMBER_VALUE_EXPRESSION}|"
    rf"\(\s*[$]?\s*{_NUMBER_VALUE_EXPRESSION}\s*\))"
)
_AMOUNT_VALUE = _pattern(rf"^\s*{_AMOUNT_VALUE_EXPRESSION}\s*$")
_TOKEN_VALUE = _pattern(r"^[A-Za-z0-9][A-Za-z0-9._/#-]{0,59}$")
_RECIPIENT_HEADING = _pattern(
    r"^\s*(?:sold\s+to|ship(?:ped)?\s+to|bill\s+to|deliver\s+to|customer|"
    r"service\s+at|invoice\s+to|buyer|recipient)\s*:?\s*$"
)
_REMIT_HEADING = _pattern(
    r"^\s*(?:(?:please\s+)?remit\s+to|pay\s+to|make\s+checks?\s+payable\s+to)"
    r"\s*[:#-]?\s*(.*?)\s*$"
)
_ADDRESS_OR_CONTACT = _pattern(
    r"(?:\b(?:p\.?\s*o\.?\s+box|phone|telephone|fax|email|www)\b|"
    r"https?://|@|^\s*(?:suite|unit|floor)\b)"
)
_STREET_ADDRESS = _pattern(
    r"^\s*\d+\s+.+\b(?:street|st\.?|road|rd\.?|avenue|ave\.?|"
    r"boulevard|blvd\.?|drive|dr\.?|lane|ln\.?|highway|hwy\.?)\b"
)
_COMPANY_DESIGNATOR = _pattern(
    r"\b(?:corporation|corp\.?|company|co\.?|incorporated|inc\.?|llc|ltd\.?|"
    r"limited|plc|lp|llp|group|systems?|services?|supply|equipment)\b"
)
_REMIT_INSTRUCTION = _pattern(
    r"(?:^|\b)(?:attn|attention|ach|wire|lockbox|cash\s+applications?|"
    r"accounts?\s+(?:payable|receivable)|payment\s+instructions?|"
    r"routing\s+(?:number|no\.?|#)|bank\s+account)(?:\b|\s*:)"
)


FIELD_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "vendor_number": (
        _pattern(
            r"^\s*(?:vendor|supplier)\s*(?:number|no\.?|#|id)"
            r"\s*[:#-]?\s*([A-Za-z0-9][A-Za-z0-9._/-]{0,39})\s*$"
        ),
    ),
    "vendor_name": (
        _pattern(
            r"^\s*(?:vendor|supplier)\s*(?:name)?\s*[:#-]\s*"
            r"(.{2,200}?)\s*$"
        ),
    ),
    "invoice_number": (
        _pattern(
            r"^\s*(?:invoice\s*(?:number|no\.?|#)|inv\s*(?:no\.?|#))"
            r"\s*[:#-]?\s*([A-Za-z0-9][A-Za-z0-9._/-]{0,59})\s*$"
        ),
        _pattern(
            r"^\s*invoice\s*[:#]\s*"
            r"([A-Za-z0-9][A-Za-z0-9._/-]{0,59})\s*$"
        ),
    ),
    "invoice_date": (
        _pattern(
            r"^\s*(?:invoice|issued?|issue)\s*date\s*[:#-]?\s*"
            r"([A-Za-z0-9, /.-]{4,40})\s*$"
        ),
    ),
    "due_date": (
        _pattern(
            r"^\s*(?:payment\s*)?due\s*date\s*[:#-]?\s*"
            r"([A-Za-z0-9, /.-]{4,40})\s*$"
        ),
    ),
    "purchase_order_number": (
        _pattern(
            r"^\s*(?:purchase\s*order|p\.?\s*o\.?)\s*"
            r"(?:number|no\.?|#)?\s*[:#-]?\s*"
            r"([A-Za-z0-9][A-Za-z0-9._/-]{0,59})\s*$"
        ),
    ),
    "terms": (
        _pattern(
            r"^\s*(?:payment\s*)?terms\s*[:#-]?\s*(.{2,120}?)\s*$"
        ),
    ),
    "subtotal": (
        _pattern(
            r"^\s*sub\s*total\s*[:#-]?\s*"
            rf"({_AMOUNT_VALUE_EXPRESSION})\s*$"
        ),
    ),
    "tax": (
        _pattern(
            r"^\s*(?:sales\s*)?tax(?:\s+amount)?\s*[:#-]?\s*"
            rf"({_AMOUNT_VALUE_EXPRESSION})\s*$"
        ),
    ),
    "freight": (
        _pattern(
            r"^\s*(?:freight|shipping)(?:\s+amount)?\s*[:#-]?\s*"
            rf"({_AMOUNT_VALUE_EXPRESSION})\s*$"
        ),
    ),
    "discount": (
        _pattern(
            r"^\s*(?:cash\s*)?discount(?:\s+amount)?\s*[:#-]?\s*"
            rf"({_AMOUNT_VALUE_EXPRESSION})\s*$"
        ),
    ),
    "total_amount": (
        _pattern(
            r"^\s*(?:invoice\s+total|grand\s+total|amount\s+due|balance\s+due|"
            r"total\s+due|total)"
            r"\s*[:#-]?\s*"
            rf"({_AMOUNT_VALUE_EXPRESSION})\s*$"
        ),
    ),
    "currency": (
        _pattern(r"^\s*currency(?:\s+code)?\s*[:#-]?\s*([A-Z]{3})\s*$"),
    ),
}


LABEL_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "vendor_number": (
        _pattern(r"^\s*(?:vendor|supplier)\s*(?:number|no\.?|#|id)\s*[:#-]?\s*$"),
    ),
    "vendor_name": (
        _pattern(r"^\s*(?:vendor|supplier)(?:\s+name)?\s*[:#-]\s*$"),
    ),
    "invoice_number": (
        # A punctuation marker is required for the short form so a document
        # title that merely says INVOICE is never treated as a field label.
        _pattern(r"^\s*invoice\s*[:#]\s*$"),
        _pattern(r"^\s*(?:invoice\s*(?:number|no\.?|#)|inv\s*(?:no\.?|#))\s*[:#-]?\s*$"),
    ),
    "invoice_date": (
        _pattern(r"^\s*(?:invoice|issued?|issue)\s*date\s*[:#-]?\s*$"),
    ),
    "due_date": (
        _pattern(r"^\s*(?:payment\s*)?due\s*date\s*[:#-]?\s*$"),
    ),
    "purchase_order_number": (
        # A bare table heading such as "Purchase Order" is deliberately not a
        # pairing label. The punctuation/number marker makes intent explicit.
        _pattern(
            r"^\s*(?:purchase\s*order|p\.?\s*o\.?)\s*"
            r"(?:(?:number|no\.?|#)\s*[:#-]?|[:#])\s*$"
        ),
    ),
    "terms": (
        _pattern(r"^\s*(?:payment\s*)?terms\s*[:#-]?\s*$"),
    ),
    "subtotal": (
        _pattern(r"^\s*sub\s*total\s*[:#-]?\s*$"),
    ),
    "tax": (
        _pattern(r"^\s*(?:sales\s*)?tax(?:\s+amount)?\s*[:#-]?\s*$"),
    ),
    "freight": (
        _pattern(r"^\s*(?:freight|shipping)(?:\s+amount)?\s*[:#-]?\s*$"),
    ),
    "discount": (
        _pattern(r"^\s*(?:cash\s*)?discount(?:\s+amount)?\s*[:#-]?\s*$"),
    ),
    "total_amount": (
        _pattern(
            r"^\s*(?:invoice\s+total|grand\s+total|amount\s+due|balance\s+due|"
            r"total\s+due|total)"
            r"\s*[:#-]?\s*$"
        ),
    ),
    "currency": (
        _pattern(r"^\s*currency(?:\s+code)?\s*[:#-]?\s*$"),
    ),
}


KEY_FIELDS = ("vendor_name", "invoice_number", "total_amount")
FIELD_DISPLAY_NAMES = {
    "vendor_name": "vendor name",
    "invoice_number": "invoice number",
    "total_amount": "invoice total",
}
MONEY_FIELDS = {"subtotal", "tax", "freight", "discount", "total_amount"}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _lines(page: dict[str, Any]) -> list[dict[str, Any]]:
    raw_lines = page.get("lines")
    if not isinstance(raw_lines, (list, tuple)):
        return []
    return [line for line in raw_lines if isinstance(line, dict)]


def _page_number(value: Any, fallback: int) -> int:
    try:
        page_number = int(value)
    except (TypeError, ValueError, OverflowError):
        return fallback
    return page_number if page_number > 0 else fallback


def _positive_finite(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return numeric if isfinite(numeric) and numeric > 0.0 else None


def _bbox(line: dict[str, Any]) -> tuple[float, float, float, float] | None:
    raw = line.get("bbox")
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    try:
        left, top, right, bottom = (float(item) for item in raw)
    except (TypeError, ValueError, OverflowError):
        return None
    if not all(isfinite(item) for item in (left, top, right, bottom)):
        return None
    if right < left or bottom < top:
        return None
    return left, top, right, bottom


def _line_confidence(line: dict[str, Any]) -> float | None:
    value = line.get("confidence")
    if value is None or isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not isfinite(numeric) or numeric < 0.0 or numeric > 1.0:
        return None
    return round(numeric, 6)


def _normalized_date(value: str) -> str | None:
    cleaned = _clean(value).strip().rstrip(".,")
    if not cleaned or not re.search(r"\d", cleaned):
        return None
    for date_format in (
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y/%m/%d",
        "%m-%d-%Y",
        "%m-%d-%y",
        "%Y-%m-%d",
        "%m.%d.%Y",
        "%Y.%m.%d",
        "%b %d, %Y",
        "%B %d, %Y",
        "%b %d %Y",
        "%B %d %Y",
        "%d %b %Y",
        "%d %B %Y",
    ):
        try:
            return datetime.strptime(cleaned.title(), date_format).date().isoformat()
        except ValueError:
            continue
    return None


def _canonical_candidate(field_name: str, value: str) -> str:
    cleaned = " ".join(value.split()).strip().upper()
    if field_name in MONEY_FIELDS:
        numeric = re.sub(r"[^0-9().+-]", "", cleaned)
        negative = numeric.startswith("(") and numeric.endswith(")")
        numeric = numeric.strip("()")
        try:
            amount = Decimal(numeric)
            if negative:
                amount = -amount
            return f"{amount.normalize():f}"
        except InvalidOperation:
            return numeric
    if field_name in {"invoice_date", "due_date"}:
        normalized_date = _normalized_date(value)
        if normalized_date is not None:
            return normalized_date
    return re.sub(r"\s+", "", cleaned)


def _matched_label_field(text: str) -> str | None:
    for field_name, patterns in LABEL_PATTERNS.items():
        if any(pattern.match(text) for pattern in patterns):
            return field_name
    return None


def _is_structural_label(text: str) -> bool:
    cleaned = _clean(text)
    lowered = cleaned.casefold().strip(" :#-")
    return bool(
        _matched_label_field(cleaned)
        or _RECIPIENT_HEADING.match(cleaned)
        or _REMIT_HEADING.match(cleaned)
        or lowered
        in {
            "invoice",
            "statement",
            "page",
            "requested by",
            "description",
            "quantity",
            "unit price",
            "extended price",
        }
    )


def _plausible_vendor_name(text: str) -> bool:
    cleaned = _clean(text).strip(" :#-")
    return bool(
        3 <= len(cleaned) <= 120
        and len(re.findall(r"[A-Za-z]", cleaned)) >= 3
        and not _is_structural_label(cleaned)
        and not _ADDRESS_OR_CONTACT.search(cleaned)
        and not _STREET_ADDRESS.search(cleaned)
        and not re.search(r"\b\d{5}(?:-\d{4})?\b", cleaned)
    )


def _plausible_remittance_payee(text: str) -> bool:
    cleaned = _clean(text).strip(" :#-")
    return bool(
        _plausible_vendor_name(cleaned)
        and _COMPANY_DESIGNATOR.search(cleaned)
        and not _REMIT_INSTRUCTION.search(cleaned)
    )


def _normalized_label(text: str) -> str:
    return re.sub(r"\s+", " ", _clean(text).casefold().strip(" :#-"))


def _is_bare_total_label(text: str) -> bool:
    return _normalized_label(text) == "total"


def _is_bare_total_inline(text: str) -> bool:
    return bool(
        re.fullmatch(
            rf"\s*total\s*[:#-]?\s*{_AMOUNT_VALUE_EXPRESSION}\s*",
            text,
            re.IGNORECASE,
        )
    )


def _is_generic_monetary_label(field_name: str, text: str) -> bool:
    if field_name not in MONEY_FIELDS:
        return False
    normalized = _normalized_label(text)
    strong_total_labels = {
        "invoice total",
        "grand total",
        "amount due",
        "balance due",
        "total due",
    }
    return field_name != "total_amount" or normalized not in strong_total_labels


def _valid_paired_value(field_name: str, text: str) -> bool:
    cleaned = _clean(text).strip()
    if not cleaned or _is_structural_label(cleaned):
        return False
    if field_name in MONEY_FIELDS:
        return bool(_AMOUNT_VALUE.fullmatch(cleaned))
    if field_name in {"vendor_number", "invoice_number", "purchase_order_number"}:
        return bool(_TOKEN_VALUE.fullmatch(cleaned))
    if field_name in {"invoice_date", "due_date"}:
        return _normalized_date(cleaned) is not None
    if field_name == "currency":
        return bool(re.fullmatch(r"[A-Z]{3}", cleaned))
    if field_name == "vendor_name":
        return _plausible_vendor_name(cleaned)
    if field_name == "terms":
        return 2 <= len(cleaned) <= 120 and bool(re.search(r"[A-Za-z0-9]", cleaned))
    return False


def _candidate(
    *,
    field_name: str,
    value: str,
    page: int,
    line: dict[str, Any],
    source: str,
    confidence: float | None,
    authority: str = "document_extraction",
    label_line: dict[str, Any] | None = None,
    pairing_method: str = "inline_labeled",
) -> dict[str, Any]:
    value_bbox = line.get("bbox")
    label_bbox = label_line.get("bbox") if label_line else None
    if isinstance(value_bbox, list) and isinstance(label_bbox, list):
        location = (
            f"page:{page};label_bbox:{','.join(str(item) for item in label_bbox)};"
            f"value_bbox:{','.join(str(item) for item in value_bbox)}"
        )
    elif isinstance(value_bbox, list):
        location = f"page:{page};bbox:{','.join(str(item) for item in value_bbox)}"
    else:
        location = f"page:{page};line:{line.get('line_number')}"
    def fragment(item: dict[str, Any], role: str) -> dict[str, Any]:
        return {
            "role": role,
            "fragment_id": item.get("fragment_id"),
            "text": item.get("text"),
            "bbox": item.get("bbox"),
            "source_method": item.get("source_method"),
            "confidence": item.get("confidence"),
        }

    evidence_fragments = (
        [fragment(label_line, "label"), fragment(line, "value")]
        if label_line is not None and label_line is not line
        else [fragment(line, "labeled_value")]
    )
    return {
        "field_name": field_name,
        "value": value.strip(),
        "source": source,
        "page": page,
        "location": location,
        "confidence": confidence,
        "authority": authority,
        "rule_version": VENDOR_INVOICE_FIELD_RULE_VERSION,
        "source_method": line.get("source_method"),
        "pairing_method": pairing_method,
        "evidence_fragments": evidence_fragments,
        "raw_line": line.get("text"),
        "raw_label": label_line.get("text") if label_line else None,
    }


def _coordinate_candidates(
    page: dict[str, Any],
    *,
    page_number: int,
) -> Iterable[dict[str, Any]]:
    lines = _lines(page)
    raw_page_width = page.get("page_width")
    if raw_page_width is None:
        raw_page_width = next(
            (line.get("page_width") for line in lines if line.get("page_width")),
            None,
        )
    page_width = _positive_finite(raw_page_width)
    max_horizontal_gap = 0.20 * page_width if page_width is not None else 160.0
    for label_line in lines:
        label_text = _clean(label_line.get("text"))
        field_name = _matched_label_field(label_text)
        label_box = _bbox(label_line)
        if field_name is None or label_box is None:
            continue

        label_height = max(label_box[3] - label_box[1], 1.0)
        label_center = (label_box[1] + label_box[3]) / 2.0
        same_row: list[tuple[float, float, dict[str, Any]]] = []
        below_label: list[tuple[float, float, dict[str, Any]]] = []
        for value_line in lines:
            if value_line is label_line:
                continue
            value_box = _bbox(value_line)
            if value_box is None:
                continue
            horizontal_gap = value_box[0] - label_box[2]
            value_height = max(value_box[3] - value_box[1], 1.0)
            center_delta = abs((value_box[1] + value_box[3]) / 2.0 - label_center)
            value_text = _clean(value_line.get("text"))
            if not _valid_paired_value(field_name, value_text):
                continue
            if (
                -2.0 <= horizontal_gap <= max_horizontal_gap
                and center_delta
                <= max(3.0, 0.65 * max(label_height, value_height))
            ):
                same_row.append((horizontal_gap, center_delta, value_line))
                continue

            vertical_gap = value_box[1] - label_box[3]
            horizontal_overlap = min(label_box[2], value_box[2]) - max(
                label_box[0], value_box[0]
            )
            same_column = abs(value_box[0] - label_box[0]) <= max(
                6.0,
                0.10 * max(label_box[2] - label_box[0], 1.0),
            )
            if (
                -1.0 <= vertical_gap <= 3.0 * max(label_height, value_height)
                and (horizontal_overlap > 0.0 or same_column)
                and not _is_generic_monetary_label(field_name, label_text)
            ):
                below_label.append(
                    (vertical_gap, abs(value_box[0] - label_box[0]), value_line)
                )

        if same_row:
            _, _, value_line = min(same_row, key=lambda item: (item[0], item[1]))
            pairing_method = "same_row_right"
        elif below_label:
            _, _, value_line = min(
                below_label,
                key=lambda item: (item[0], item[1]),
            )
            pairing_method = "below_label"
        else:
            continue
        source_method = value_line.get("source_method")
        candidate = _candidate(
            field_name=field_name,
            value=_clean(value_line.get("text")),
            page=page_number,
            line=value_line,
            label_line=label_line,
            source=(
                "vendor_invoice_parser.coordinate_paired_ocr_text"
                if source_method == "local_tesseract_ocr"
                else "vendor_invoice_parser.coordinate_paired_native_text"
            ),
            confidence=_line_confidence(value_line),
            pairing_method=pairing_method,
        )
        if field_name == "total_amount" and _is_bare_total_label(label_text):
            candidate["requires_strong_total_context"] = True
        yield candidate


def _remittance_vendor_candidates(
    pages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for page_index, page in enumerate(pages, start=1):
        page_number = _page_number(page.get("page_number"), page_index)
        lines = _lines(page)
        for label_line in lines:
            match = _REMIT_HEADING.match(_clean(label_line.get("text")))
            if not match:
                continue
            inline_value = _clean(match.group(1)).strip(" :#-")
            if inline_value:
                if _plausible_remittance_payee(inline_value):
                    candidates.append(
                        _candidate(
                            field_name="vendor_name",
                            value=inline_value,
                            page=page_number,
                            line=label_line,
                            source="vendor_invoice_parser.remittance_issuer_candidate",
                            confidence=_line_confidence(label_line),
                            authority="analytical_inference",
                            pairing_method="remit_payee_block",
                        )
                    )
                    continue

            label_box = _bbox(label_line)
            if label_box is None:
                continue
            below: list[tuple[float, float, dict[str, Any]]] = []
            for candidate_line in lines:
                candidate_box = _bbox(candidate_line)
                if candidate_line is label_line or candidate_box is None:
                    continue
                vertical_gap = candidate_box[1] - label_box[3]
                if vertical_gap < -1.0 or vertical_gap > 72.0:
                    continue
                if candidate_box[0] < label_box[0] - 48.0:
                    continue
                if candidate_box[0] > label_box[2] + 180.0:
                    continue
                text = _clean(candidate_line.get("text"))
                if _plausible_remittance_payee(text):
                    below.append((vertical_gap, candidate_box[0], candidate_line))
            for _, _, value_line in sorted(
                below,
                key=lambda item: (item[0], item[1]),
            ):
                candidates.append(
                    _candidate(
                        field_name="vendor_name",
                        value=_clean(value_line.get("text")),
                        page=page_number,
                        line=value_line,
                        label_line=label_line,
                        source="vendor_invoice_parser.remittance_issuer_candidate",
                        confidence=_line_confidence(value_line),
                        authority="analytical_inference",
                        pairing_method="remit_payee_block",
                    )
                )
    return candidates


def _header_vendor_candidate(pages: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not pages:
        return None
    raw_lines = _lines(pages[0])
    positioned = [(line, _bbox(line)) for line in raw_lines]
    recipient_tops = [
        box[1]
        for line, box in positioned
        if box is not None and _RECIPIENT_HEADING.match(_clean(line.get("text")))
    ]
    recipient_top = min(recipient_tops) if recipient_tops else None
    ordered = sorted(
        positioned,
        key=lambda item: (
            item[1][1] if item[1] is not None else float("inf"),
            item[1][0] if item[1] is not None else float("inf"),
            _page_number(item[0].get("line_number"), 1),
        ),
    )
    eligible: list[tuple[int, float, dict[str, Any]]] = []
    for line, box in ordered[:24]:
        if box is not None and recipient_top is not None and box[1] >= recipient_top:
            continue
        text = _clean(line.get("text")).strip(" :#-")
        if (
            re.search(r"\d", text)
            or not _plausible_vendor_name(text)
            or not _COMPANY_DESIGNATOR.search(text)
        ):
            continue
        if any(
            term in text.casefold()
            for term in (
                "invoice",
                "bill to",
                "sold to",
                "ship to",
                "shipped to",
                "remit to",
                "purchase order",
                "statement",
                "customer",
                "terms",
                "due date",
                "page ",
            )
        ):
            continue
        company_score = 1 if _COMPANY_DESIGNATOR.search(text) else 0
        top = (
            box[1]
            if box is not None
            else float(_page_number(line.get("line_number"), 1))
        )
        eligible.append((-company_score, top, line))
    if not eligible:
        return None
    _, _, line = min(eligible, key=lambda item: (item[0], item[1]))
    return _candidate(
        field_name="vendor_name",
        value=_clean(line.get("text")).strip(" :#-"),
        page=1,
        line=line,
        source="vendor_invoice_parser.header_issuer_candidate",
        confidence=_line_confidence(line),
        authority="analytical_inference",
        pairing_method="header_issuer_candidate",
    )


def _text_source(pages: list[dict[str, Any]]) -> str:
    methods = {
        str(line.get("source_method") or "")
        for page in pages
        for line in _lines(page)
        if line.get("text")
    }
    methods.discard("")
    if methods == {"native_pdf_text"}:
        return "native_pdf_text"
    if methods == {"local_tesseract_ocr"}:
        return "local_tesseract_ocr"
    if methods:
        return "mixed_native_and_ocr"
    return "unavailable"


class VendorInvoiceParser(DocumentParser):
    document_type = "vendor_invoice"
    parser_name = "deterministic_vendor_invoice_parser"
    parser_version = "2.0.0"

    def parse(self, document: dict) -> dict:
        envelope = document if isinstance(document, dict) else {}
        raw_extraction = envelope.get("extraction")
        extraction = raw_extraction if isinstance(raw_extraction, dict) else {}
        raw_pages = extraction.get("pages")
        pages = (
            [page for page in raw_pages if isinstance(page, dict)]
            if isinstance(raw_pages, (list, tuple))
            else []
        )
        candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
        recognized_labels: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for page_index, page in enumerate(pages, start=1):
            page_number = _page_number(page.get("page_number"), page_index)
            for line in _lines(page):
                text = str(line.get("text") or "")
                if not text:
                    continue
                label_field = _matched_label_field(text)
                if label_field is not None:
                    recognized_labels[label_field].append(
                        {"page": page_number, "line": line}
                    )
                for field_name, patterns in FIELD_PATTERNS.items():
                    for pattern in patterns:
                        match = pattern.match(text)
                        if not match:
                            continue
                        value = _clean(match.group(1))
                        if not _valid_paired_value(field_name, value):
                            continue
                        candidate = _candidate(
                            field_name=field_name,
                            value=value,
                            page=page_number,
                            line=line,
                            source=(
                                "vendor_invoice_parser.labeled_ocr_text"
                                if line.get("source_method") == "local_tesseract_ocr"
                                else "vendor_invoice_parser.labeled_native_text"
                            ),
                            confidence=_line_confidence(line),
                        )
                        if (
                            field_name == "total_amount"
                            and _is_bare_total_inline(text)
                        ):
                            candidate["requires_strong_total_context"] = True
                            recognized_labels[field_name].append(
                                {"page": page_number, "line": line}
                            )
                        candidates[field_name].append(
                            candidate
                        )
                        break
            for paired in _coordinate_candidates(page, page_number=page_number):
                candidates[str(paired["field_name"])].append(paired)

        if not candidates.get("vendor_name"):
            candidates["vendor_name"].extend(
                _remittance_vendor_candidates(pages)
            )
        if not candidates.get("vendor_name"):
            header = _header_vendor_candidate(pages)
            if header:
                candidates["vendor_name"].append(header)

        total_candidates = candidates.get("total_amount", [])
        if total_candidates:
            strong_total_values = {
                _canonical_candidate("total_amount", str(item["value"]))
                for item in total_candidates
                if not item.get("requires_strong_total_context")
            }
            retained_totals: list[dict[str, Any]] = []
            for item in total_candidates:
                requires_context = bool(
                    item.pop("requires_strong_total_context", False)
                )
                canonical_value = _canonical_candidate(
                    "total_amount",
                    str(item["value"]),
                )
                if not requires_context or canonical_value in strong_total_values:
                    if requires_context:
                        item["selection_context"] = (
                            "corroborated_by_strong_total_label"
                        )
                    retained_totals.append(item)
            candidates["total_amount"] = retained_totals

        ocr_confidence = extraction.get("ocr_average_confidence")
        ocr_confidence_value = _line_confidence(
            {"confidence": ocr_confidence}
        )
        if ocr_confidence_value is not None:
            candidates["ocr_confidence"].append(
                {
                    "field_name": "ocr_confidence",
                    "value": ocr_confidence_value,
                    "source": "vendor_invoice_extraction.ocr_average_confidence",
                    "page": None,
                    "location": "ocr_attempted_pages",
                    "confidence": ocr_confidence_value,
                    "authority": "document_extraction",
                    "rule_version": extraction.get("ocr_profile_version"),
                    "source_method": "local_tesseract_ocr",
                    "pairing_method": "extraction_summary",
                    "evidence_fragments": [],
                    "raw_line": None,
                    "raw_label": None,
                }
            )

        fields: dict[str, Any] = {}
        field_evidence: dict[str, dict[str, Any]] = {}
        ambiguous_fields: dict[str, list[dict[str, Any]]] = {}
        for field_name in (*FIELD_PATTERNS, "ocr_confidence"):
            field_candidates = candidates.get(field_name, [])
            distinct: dict[str, dict[str, Any]] = {}
            for item in field_candidates:
                key = _canonical_candidate(field_name, str(item["value"]))
                distinct.setdefault(key, item)
            if len(distinct) == 1:
                selected = next(iter(distinct.values()))
                if field_name == "total_amount":
                    selected_value = str(selected["value"]).strip()
                    selected = next(
                        (
                            item
                            for item in field_candidates
                            if item.get("selection_context")
                            != "corroborated_by_strong_total_label"
                            and str(item["value"]).strip() == selected_value
                        ),
                        selected,
                    )
                fields[field_name] = selected["value"]
                field_evidence[field_name] = {
                    **selected,
                    "validation_status": "available",
                    "candidate_count": 1,
                    "observation_count": len(field_candidates),
                    "observations": field_candidates,
                }
            elif len(distinct) > 1:
                ambiguous_fields[field_name] = list(distinct.values())
                field_evidence[field_name] = {
                    "field_name": field_name,
                    "value": None,
                    "source": "vendor_invoice_parser.ambiguous_candidates",
                    "page": None,
                    "location": None,
                    "confidence": None,
                    "authority": "unavailable",
                    "rule_version": VENDOR_INVOICE_FIELD_RULE_VERSION,
                    "validation_status": "ambiguous",
                    "candidate_count": len(distinct),
                    "observation_count": len(field_candidates),
                    "candidates": list(distinct.values()),
                    "observations": field_candidates,
                }
            elif recognized_labels.get(field_name):
                recognized = recognized_labels[field_name][0]
                label_line = recognized["line"]
                label_box = label_line.get("bbox")
                location = (
                    f"page:{recognized['page']};label_bbox:"
                    + ",".join(str(item) for item in label_box)
                    if isinstance(label_box, list)
                    else f"page:{recognized['page']};line:{label_line.get('line_number')}"
                )
                field_evidence[field_name] = {
                    "field_name": field_name,
                    "value": None,
                    "source": "vendor_invoice_parser.label_without_value",
                    "page": recognized["page"],
                    "location": location,
                    "confidence": None,
                    "authority": "unavailable",
                    "rule_version": VENDOR_INVOICE_FIELD_RULE_VERSION,
                    "source_method": label_line.get("source_method"),
                    "pairing_method": "label_without_value",
                    "evidence_fragments": [
                        {
                            "role": "label",
                            "fragment_id": label_line.get("fragment_id"),
                            "text": label_line.get("text"),
                            "bbox": label_line.get("bbox"),
                            "source_method": label_line.get("source_method"),
                            "confidence": label_line.get("confidence"),
                        }
                    ],
                    "raw_line": None,
                    "raw_label": label_line.get("text"),
                    "validation_status": "present_without_value",
                    "candidate_count": 0,
                    "observation_count": 0,
                }
            else:
                field_evidence[field_name] = {
                    "field_name": field_name,
                    "value": None,
                    "source": "unavailable",
                    "page": None,
                    "location": None,
                    "confidence": None,
                    "authority": "unavailable",
                    "rule_version": VENDOR_INVOICE_FIELD_RULE_VERSION,
                    "validation_status": "unavailable",
                    "candidate_count": 0,
                    "observation_count": 0,
                }

        missing_key_fields = [
            field_name for field_name in KEY_FIELDS if field_name not in fields
        ]
        source_kind = str(
            extraction.get("text_source_summary") or _text_source(pages)
        )
        source_label = {
            "native_pdf_text": "Native PDF text was extracted",
            "local_tesseract_ocr": "Local OCR text was extracted",
            "mixed_native_and_ocr": "Native PDF and local OCR text were extracted",
            "unavailable": "Readable invoice text is unavailable",
        }.get(source_kind, "Invoice text was extracted")
        if missing_key_fields:
            readiness_message = (
                f"{source_label}, but key fields need review: "
                + ", ".join(FIELD_DISPLAY_NAMES[item] for item in missing_key_fields)
                + "."
            )
            readiness_status = "key_fields_need_review"
        else:
            readiness_message = (
                f"{source_label}; vendor name, invoice number, and invoice total "
                "were recognized. Human review remains required."
            )
            readiness_status = "key_fields_recognized"

        business_fields = list(FIELD_PATTERNS)
        available_business_fields = [
            field_name for field_name in business_fields if field_name in fields
        ]
        ambiguous_business_fields = [
            field_name
            for field_name in business_fields
            if field_evidence[field_name]["validation_status"] == "ambiguous"
        ]
        present_without_value_fields = [
            field_name
            for field_name in business_fields
            if field_evidence[field_name]["validation_status"]
            == "present_without_value"
        ]
        if source_kind == "unavailable":
            quality = "no_readable_text"
        elif not available_business_fields:
            quality = "text_fields_unresolved"
        elif missing_key_fields:
            quality = "partial_key_fields_requires_review"
        else:
            quality = "fields_available_requires_review"
        coverage_message = (
            f"{source_label}; {len(available_business_fields)} of "
            f"{len(business_fields)} invoice fields were recognized. "
            + (
                "Key fields need review: "
                + ", ".join(FIELD_DISPLAY_NAMES[item] for item in missing_key_fields)
                + "."
                if missing_key_fields
                else "All three key fields were recognized; human review remains required."
            )
        )

        errors: list[str] = []
        raw_warnings = extraction.get("warnings")
        if isinstance(raw_warnings, (list, tuple)):
            warnings = [str(item) for item in raw_warnings]
        elif isinstance(raw_warnings, str) and raw_warnings.strip():
            warnings = [raw_warnings]
        else:
            warnings = []
        for field_name in missing_key_fields:
            warnings.append(
                f"{field_name} was not determined from one unambiguous source candidate."
            )
        for field_name, items in ambiguous_fields.items():
            warnings.append(
                f"{field_name} has {len(items)} distinct candidates and requires human review."
            )
        if not str(extraction.get("full_text") or "").strip():
            errors.append("No readable native or OCR text is available for this invoice.")
        if extraction.get("ocr_failed_pages"):
            errors.append("One or more pages required OCR but local OCR did not complete.")
        vendor_evidence = field_evidence.get("vendor_name", {})
        remittance_vendor_present = any(
            item.get("source")
            == "vendor_invoice_parser.remittance_issuer_candidate"
            for item in candidates.get("vendor_name", [])
        )
        if remittance_vendor_present:
            warnings.append(
                "Vendor name evidence includes a remittance issuer candidate, not a verified vendor identity."
            )
        elif vendor_evidence.get("source") == "vendor_invoice_parser.header_issuer_candidate":
            warnings.append(
                "Vendor name is a header issuer candidate, not a verified vendor identity."
            )

        return {
            "parser": self.parser_name,
            "parser_version": self.parser_version,
            "field_rule_version": VENDOR_INVOICE_FIELD_RULE_VERSION,
            "document_type": self.document_type,
            "fields": fields,
            "field_evidence": field_evidence,
            "records": [],
            "ambiguous_fields": ambiguous_fields,
            "review_required": True,
            "key_field_readiness": {
                "status": readiness_status,
                "text_source": source_kind,
                "required_fields": list(KEY_FIELDS),
                "missing_or_ambiguous_fields": missing_key_fields,
                "message": readiness_message,
            },
            "field_summary": {
                "quality": quality,
                "text_source": source_kind,
                "business_field_count": len(business_fields),
                "available_count": len(available_business_fields),
                "available_fields": available_business_fields,
                "ambiguous_fields": ambiguous_business_fields,
                "present_without_value_fields": present_without_value_fields,
                "unavailable_fields": [
                    field_name
                    for field_name in business_fields
                    if field_evidence[field_name]["validation_status"]
                    == "unavailable"
                ],
                "key_fields": {
                    field_name: field_evidence[field_name]["validation_status"]
                    for field_name in KEY_FIELDS
                },
                "message": coverage_message,
            },
            "authority": {
                "extraction_effect": "evidence_only",
                "invoice_approval_effect": "none",
                "payment_effect": "none",
                "erp_write": False,
            },
            "validation": {
                "status": "failed" if errors else "review_required",
                "errors": errors,
                "warnings": list(dict.fromkeys(warnings)),
            },
        }
