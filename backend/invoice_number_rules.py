"""Shared ERP invoice-number admission rule.

OCR may retain broader numeric candidates as source evidence. Only normalized
8- or 9-digit values enter ERP invoice-owner or allocation matching. The
10-digit no-remittance placeholder remains a review convention and never ERP
evidence.
"""

from __future__ import annotations

import re
from typing import Any


ERP_INVOICE_RULE_VERSION = "erp-invoice-number-admission@1.2.0"
ERP_INVOICE_DIGIT_LENGTHS = frozenset({8, 9})
NO_REMITTANCE_INVOICE = "9999999999"


def normalize_erp_invoice(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if (
        len(digits) not in ERP_INVOICE_DIGIT_LENGTHS
        or digits == NO_REMITTANCE_INVOICE
    ):
        return ""
    return digits


def is_valid_erp_invoice(value: Any) -> bool:
    return bool(normalize_erp_invoice(value))
