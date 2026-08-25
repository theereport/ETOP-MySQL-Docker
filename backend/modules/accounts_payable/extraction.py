from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable


NORMALIZATION_RULE_VERSION = "ap-invoice-normalization.v1"
SOURCE_TEXT_RULE_VERSION = "ap-source-text-candidate.v1"
REVIEW_UNAVAILABLE_RULE_VERSION = "ap-review-unavailable.v1"
PROVISIONAL_OCR_REVIEW_THRESHOLD = 0.90
PROVISIONAL_OCR_THRESHOLD_SOURCE = (
    "observed_current_document_review_ui"
)


FIELD_LABELS = {
    "vendor_number": "Vendor Number",
    "vendor_name": "Vendor Name",
    "invoice_number": "Invoice Number",
    "invoice_date": "Invoice Date",
    "due_date": "Due Date",
    "purchase_order_number": "Purchase Order",
    "terms": "Payment Terms",
    "subtotal": "Subtotal",
    "tax": "Tax",
    "freight": "Freight",
    "discount": "Discount",
    "total_amount": "Invoice Total",
    "currency": "Currency",
    "ocr_confidence": "OCR Confidence",
}


FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "vendor_number": (
        "vendor_number",
        "vendor_no",
        "vendor_id",
        "supplier_number",
        "supplier_id",
    ),
    "vendor_name": (
        "vendor_name",
        "supplier_name",
        "seller_name",
        "issuer_name",
        "vendor",
        "supplier",
    ),
    "invoice_number": (
        "invoice_number",
        "invoice_no",
        "invoice_id",
        "invoice",
    ),
    "invoice_date": ("invoice_date", "issued_date", "issue_date"),
    "due_date": ("due_date", "payment_due_date"),
    "purchase_order_number": (
        "purchase_order_number",
        "purchase_order",
        "po_number",
        "po_no",
        "po",
    ),
    "terms": ("payment_terms", "terms", "invoice_terms"),
    "subtotal": ("subtotal", "sub_total", "net_amount"),
    "tax": ("tax", "tax_amount", "sales_tax"),
    "freight": ("freight", "freight_amount", "shipping_amount"),
    "discount": (
        "discount",
        "discount_amount",
        "cash_discount",
    ),
    "total_amount": (
        "total_amount",
        "invoice_total",
        "amount_due",
        "grand_total",
        "total",
    ),
    "currency": ("currency", "currency_code"),
    "ocr_confidence": (
        "ocr_confidence",
        "ocr_average_confidence",
        "average_ocr_confidence",
    ),
}


CONTAINER_KEYS = (
    "field_evidence",
    "fields",
    "header",
    "invoice",
    "vendor",
    "supplier",
    "amounts",
    "totals",
    "payment",
    "ocr",
)


TEXT_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "vendor_number": (
        re.compile(
            r"(?im)^\s*(?:vendor|supplier)\s*(?:number|no\.?|#|id)"
            r"\s*[:#-]?\s*([A-Za-z0-9][A-Za-z0-9._/-]{0,39})\s*$"
        ),
    ),
    "vendor_name": (
        re.compile(
            r"(?im)^\s*(?:vendor|supplier)\s*(?:name)?\s*[:#-]\s*"
            r"([^\r\n]{2,200})\s*$"
        ),
    ),
    "invoice_number": (
        re.compile(
            r"(?im)^\s*(?:invoice\s*(?:number|no\.?|#)|inv\s*(?:no\.?|#))"
            r"\s*[:#-]?\s*([A-Za-z0-9][A-Za-z0-9._/-]{0,59})\s*$"
        ),
    ),
    "invoice_date": (
        re.compile(
            r"(?im)^\s*(?:invoice|issued?|issue)\s*date\s*[:#-]?\s*"
            r"([^\r\n]{4,40})\s*$"
        ),
    ),
    "due_date": (
        re.compile(
            r"(?im)^\s*(?:payment\s*)?due\s*date\s*[:#-]?\s*"
            r"([^\r\n]{4,40})\s*$"
        ),
    ),
    "purchase_order_number": (
        re.compile(
            r"(?im)^\s*(?:purchase\s*order|p\.?\s*o\.?)\s*"
            r"(?:number|no\.?|#)?\s*[:#-]?\s*"
            r"([A-Za-z0-9][A-Za-z0-9._/-]{0,59})\s*$"
        ),
    ),
    "terms": (
        re.compile(
            r"(?im)^\s*(?:payment\s*)?terms\s*[:#-]?\s*"
            r"([^\r\n]{2,120})\s*$"
        ),
    ),
    "subtotal": (
        re.compile(
            r"(?im)^\s*sub\s*total\s*[:#-]?\s*"
            r"(\(?[-+]?\s*[$]?\s*[0-9][0-9,]*(?:\.[0-9]{1,4})?\)?)\s*$"
        ),
    ),
    "tax": (
        re.compile(
            r"(?im)^\s*(?:sales\s*)?tax(?:\s+amount)?\s*[:#-]?\s*"
            r"(\(?[-+]?\s*[$]?\s*[0-9][0-9,]*(?:\.[0-9]{1,4})?\)?)\s*$"
        ),
    ),
    "freight": (
        re.compile(
            r"(?im)^\s*(?:freight|shipping)(?:\s+amount)?\s*[:#-]?\s*"
            r"(\(?[-+]?\s*[$]?\s*[0-9][0-9,]*(?:\.[0-9]{1,4})?\)?)\s*$"
        ),
    ),
    "discount": (
        re.compile(
            r"(?im)^\s*(?:cash\s*)?discount(?:\s+amount)?\s*[:#-]?\s*"
            r"(\(?[-+]?\s*[$]?\s*[0-9][0-9,]*(?:\.[0-9]{1,4})?\)?)\s*$"
        ),
    ),
    "total_amount": (
        re.compile(
            r"(?im)^\s*(?:invoice\s+total|grand\s+total|amount\s+due|"
            r"total\s+due)\s*[:#-]?\s*"
            r"(\(?[-+]?\s*[$]?\s*[0-9][0-9,]*(?:\.[0-9]{1,4})?\)?)\s*$"
        ),
    ),
    "currency": (
        re.compile(
            r"(?im)^\s*currency(?:\s+code)?\s*[:#-]?\s*"
            r"(USD|CAD|EUR|GBP|JPY|AUD|CHF|CNY|MXN)\s*$"
        ),
    ),
}


def canonical_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def normalize_identity(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", value.upper())


def normalize_invoice_number(value: str) -> str:
    return normalize_identity(value)


def normalize_vendor_identity(
    vendor_number: str | None,
    vendor_name: str | None,
) -> str | None:
    if vendor_number:
        normalized = normalize_identity(vendor_number)
        return f"number:{normalized}" if normalized else None
    if vendor_name:
        normalized = normalize_identity(vendor_name)
        return f"name:{normalized}" if normalized else None
    return None


def _walk_known_containers(
    mapping: dict[str, Any],
    prefix: str,
) -> list[tuple[dict[str, Any], str]]:
    containers: list[tuple[dict[str, Any], str]] = [(mapping, prefix)]
    normalized_keys = {canonical_key(str(key)): key for key in mapping}
    for container_key in CONTAINER_KEYS:
        original_key = normalized_keys.get(container_key)
        if original_key is None:
            continue
        child = mapping.get(original_key)
        if isinstance(child, dict):
            containers.append((child, f"{prefix}.{original_key}"))
    return containers


def find_structured_value(
    sources: list[tuple[dict[str, Any], str]],
    field_name: str,
) -> tuple[Any, str, dict[str, Any]] | None:
    aliases = set(FIELD_ALIASES[field_name])
    for source, prefix in sources:
        for container, container_path in _walk_known_containers(source, prefix):
            for key, value in container.items():
                if canonical_key(str(key)) in aliases and value not in (
                    None,
                    "",
                ):
                    if isinstance(value, dict) and "value" in value:
                        raw_value = value.get("value")
                        if raw_value in (None, ""):
                            continue
                        return raw_value, f"{container_path}.{key}", value
                    return value, f"{container_path}.{key}", {}
    return None


def find_text_candidate(text: str, field_name: str) -> tuple[str, str] | None:
    for pattern_index, pattern in enumerate(TEXT_PATTERNS.get(field_name, ())):
        match = pattern.search(text)
        if match:
            return match.group(1).strip(), f"full_text.pattern[{pattern_index}]"
    return None


def normalize_string(value: Any) -> str | None:
    if value is None or isinstance(value, (dict, list, tuple, bool)):
        return None
    normalized = str(value).strip()
    return normalized or None


def normalize_date(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    raw = normalize_string(value)
    if raw is None:
        return None
    cleaned = raw.strip().rstrip(".,")
    formats = (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y/%m/%d",
        "%b %d, %Y",
        "%B %d, %Y",
        "%b %d %Y",
        "%B %d %Y",
    )
    for format_string in formats:
        try:
            return datetime.strptime(cleaned, format_string).date().isoformat()
        except ValueError:
            continue
    return None


def normalize_amount(value: Any) -> str | None:
    if value is None or isinstance(value, (dict, list, tuple, bool)):
        return None
    if isinstance(value, Decimal):
        amount = value
    else:
        raw = str(value).strip()
        if not raw:
            return None
        negative = raw.startswith("(") and raw.endswith(")")
        raw = raw.strip("()").replace(",", "").replace("$", "").strip()
        raw = re.sub(r"\s+", "", raw)
        try:
            amount = Decimal(raw)
        except InvalidOperation:
            return None
        if negative:
            amount = -amount
    if not amount.is_finite():
        return None
    return str(amount.quantize(Decimal("0.01")))


def normalize_confidence(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    if confidence > 1.0 and confidence <= 100.0:
        confidence /= 100.0
    if confidence < 0.0 or confidence > 1.0:
        return None
    return round(confidence, 6)


NORMALIZERS: dict[str, Callable[[Any], Any]] = {
    "vendor_number": normalize_string,
    "vendor_name": normalize_string,
    "invoice_number": normalize_string,
    "invoice_date": normalize_date,
    "due_date": normalize_date,
    "purchase_order_number": normalize_string,
    "terms": normalize_string,
    "subtotal": normalize_amount,
    "tax": normalize_amount,
    "freight": normalize_amount,
    "discount": normalize_amount,
    "total_amount": normalize_amount,
    "currency": lambda value: (
        normalized.upper()
        if (normalized := normalize_string(value))
        and re.fullmatch(r"[A-Za-z]{3}", normalized)
        else None
    ),
    "ocr_confidence": normalize_confidence,
}


def extract_field_evidence(
    *,
    field_name: str,
    corrected_sources: list[tuple[dict[str, Any], str]],
    structured_sources: list[tuple[dict[str, Any], str]],
    source_text: str,
    allow_text_candidate: bool,
    unavailable_fields: set[str] | frozenset[str] | None = None,
) -> dict[str, Any]:
    if field_name in (unavailable_fields or ()):
        return {
            "field_name": field_name,
            "label": FIELD_LABELS[field_name],
            "value": None,
            "normalized_value": None,
            "confidence": None,
            "source": "document_extraction_review.unavailable_fields",
            "page": None,
            "location": None,
            "validation_status": "unavailable",
            "explanation": (
                "A reviewer explicitly marked this field unavailable for "
                "the current processing run. Machine extraction and source-"
                "text candidates were suppressed. This extraction review is "
                "not AP approval or payment authorization."
            ),
            "authority": "human_reviewed_unavailable",
            "rule_version": REVIEW_UNAVAILABLE_RULE_VERSION,
        }

    value_and_path = find_structured_value(corrected_sources, field_name)
    source_kind = "review_correction"
    authority = "human_corrected_evidence"
    source = "document_extraction_review.corrected_fields"
    rule_version: str | None = None

    if value_and_path is None:
        value_and_path = find_structured_value(structured_sources, field_name)
        source_kind = "structured_extraction"
        authority = "document_extraction"
        source = "document_intelligence.parsed"

    if (
        value_and_path is None
        and allow_text_candidate
        and field_name in TEXT_PATTERNS
    ):
        value_and_path = find_text_candidate(source_text, field_name)
        source_kind = "source_text_candidate"
        authority = "analytical_inference"
        source = "document_intelligence.extraction.full_text"
        rule_version = SOURCE_TEXT_RULE_VERSION

    if value_and_path is None:
        return {
            "field_name": field_name,
            "label": FIELD_LABELS[field_name],
            "value": None,
            "normalized_value": None,
            "confidence": None,
            "source": "unavailable",
            "page": None,
            "location": None,
            "validation_status": "unavailable",
            "explanation": "No source-present value was found.",
            "authority": "unavailable",
            "rule_version": None,
        }

    if len(value_and_path) == 2:
        raw_value, source_path = value_and_path
        metadata: dict[str, Any] = {}
    else:
        raw_value, source_path, metadata = value_and_path
    normalized_value = NORMALIZERS[field_name](raw_value)
    validation_status = (
        str(metadata.get("validation_status"))
        if metadata.get("validation_status")
        else "available" if normalized_value is not None else "invalid"
    )
    if source_kind == "source_text_candidate":
        explanation = (
            "Candidate derived deterministically from the already-preserved "
            "Document Intelligence text. It is analytical inference and "
            "requires human review."
        )
    elif source_kind == "review_correction":
        explanation = (
            "Value came from Document Intelligence review correction evidence. "
            "That review is not AP approval or payment authorization."
        )
    else:
        explanation = "Value came from the structured Document Intelligence result."

    if normalized_value is None:
        explanation += " The source value could not be normalized and was not used."

    confidence = normalize_confidence(metadata.get("confidence"))
    page = metadata.get("page")
    try:
        page = int(page) if page is not None else None
    except (TypeError, ValueError):
        page = None
    parser_location = metadata.get("location")
    parser_source = metadata.get("source")
    parser_authority = metadata.get("authority")
    if source_kind == "structured_extraction" and isinstance(parser_source, str):
        source = f"document_intelligence.parsed:{parser_source}"
    if source_kind == "structured_extraction" and parser_authority in {
        "document_extraction",
        "analytical_inference",
    }:
        authority = str(parser_authority)
    if source_kind == "structured_extraction" and metadata.get("rule_version"):
        rule_version = str(metadata["rule_version"])

    return {
        "field_name": field_name,
        "label": FIELD_LABELS[field_name],
        "value": raw_value if isinstance(raw_value, (str, int, float, bool)) else str(raw_value),
        "normalized_value": normalized_value,
        "confidence": confidence,
        "source": f"{source}:{source_path}",
        "page": page,
        "location": str(parser_location or source_path),
        "validation_status": validation_status,
        "explanation": explanation,
        "authority": authority,
        "rule_version": rule_version,
    }


def extraction_warnings(result: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    parsed = result.get("parsed")
    if isinstance(parsed, dict):
        validation = parsed.get("validation")
        if isinstance(validation, dict):
            for key in ("errors", "warnings"):
                values = validation.get(key)
                if isinstance(values, list):
                    warnings.extend(
                        str(value).strip()
                        for value in values
                        if str(value).strip()
                    )
    extraction = result.get("extraction")
    if isinstance(extraction, dict):
        values = extraction.get("warnings")
        if isinstance(values, list):
            warnings.extend(
                str(value).strip()
                for value in values
                if str(value).strip()
            )
        if extraction.get("ocr_recommended"):
            warnings.append(
                "Document Intelligence marked at least one page as OCR recommended."
            )
    return list(dict.fromkeys(warnings))
