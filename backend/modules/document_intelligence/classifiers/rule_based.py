import re

from ..pnc_lockbox_contract import PNC_LOCKBOX_IDENTIFIER_RE


def classify_document(file_name: str, extracted_text: str) -> dict:
    combined = f"{file_name}\n{extracted_text[:20000]}".lower()
    evidence: list[str] = []

    score = 0.0

    # Strong PNC/lockbox indicators
    if "pnc" in combined:
        score += 0.30
        evidence.append("Found PNC")

    if "lockbox" in combined:
        score += 0.25
        evidence.append("Found lockbox")

    # PNC output reports use a three-letter processing-site code.  Site
    # identity is evidence, not a Pittsburgh-only format restriction.
    if PNC_LOCKBOX_IDENTIFIER_RE.search(combined):
        score += 0.25
        evidence.append("Found PNC lockbox identifier (AAA-######)")

    if "transactions for output" in combined:
        score += 0.15
        evidence.append("Found Transactions for Output")

    if "transaction level details" in combined:
        score += 0.15
        evidence.append("Found Transaction Level Details")

    if "reported amount" in combined:
        score += 0.10
        evidence.append("Found Reported Amount")

    if "transit" in combined and "check number" in combined:
        score += 0.10
        evidence.append("Found transit and check-number fields")

    if "envelope and check image" in combined:
        score += 0.10
        evidence.append("Found Envelope and Check Image")

    if "batch item" in combined:
        score += 0.05
        evidence.append("Found Batch Item")

    if re.search(r"\bg-\d{7}\b", combined):
        score += 0.10
        evidence.append("Found transaction identifier (G-#######)")

    if score >= 0.60:
        return {
            "document_type": "pnc_lockbox",
            "confidence": min(round(score, 2), 0.99),
            "classifier": "rule_based_v2",
            "evidence": evidence,
        }

    bank_terms = sum(
        term in combined
        for term in (
            "bank",
            "deposit",
            "routing",
            "account number",
            "check number",
            "remittance",
            "transit",
            "reported amount",
        )
    )

    if bank_terms >= 2:
        return {
            "document_type": "bank_report",
            "confidence": min(0.40 + bank_terms * 0.08, 0.85),
            "classifier": "rule_based_v2",
            "evidence": ["Matched multiple bank-report terms"],
        }

    invoice_terms = sum(
        term in combined
        for term in (
            "invoice",
            "vendor",
            "bill to",
            "ship to",
            "amount due",
        )
    )

    if invoice_terms >= 3:
        return {
            "document_type": "vendor_invoice",
            "confidence": min(0.45 + invoice_terms * 0.07, 0.85),
            "classifier": "rule_based_v2",
            "evidence": ["Matched multiple invoice terms"],
        }

    if "statement" in combined and any(
        term in combined for term in ("balance", "account", "period")
    ):
        return {
            "document_type": "statement",
            "confidence": 0.65,
            "classifier": "rule_based_v2",
            "evidence": ["Matched statement terms"],
        }

    return {
        "document_type": "unknown",
        "confidence": 0.20 if extracted_text.strip() else 0.05,
        "classifier": "rule_based_v2",
        "evidence": ["No supported document pattern met its threshold"],
    }
