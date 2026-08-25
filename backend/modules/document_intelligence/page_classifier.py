from __future__ import annotations
import re
from .vision_models import PageType
from .pnc_lockbox_contract import PNC_LOCKBOX_IDENTIFIER_PATTERN

TRANSACTION_RE = re.compile(
    rf"Transaction Information\s+G-\d+\s+"
    rf"{PNC_LOCKBOX_IDENTIFIER_PATTERN}\s+\d{{4}}/\d{{2}}/\d{{2}}",
    re.IGNORECASE,
)

def classify_page(embedded_text: str, ocr_text: str = "") -> PageType:
    combined = f"{embedded_text}\n{ocr_text}".strip()
    lowered = combined.lower()
    if not combined:
        return "blank"
    if TRANSACTION_RE.search(combined):
        return "transaction"
    if any(x in lowered for x in (
        "invoice number", "invoice #", "invoice no",
        "remittance advice", "payment detail", "amount due",
    )):
        return "remittance"
    if any(x in lowered for x in (
        "statement", "account summary", "previous balance", "current balance",
    )):
        return "statement"
    if len(re.sub(r"\s+", "", combined)) < 20:
        return "blank"
    return "unknown"
