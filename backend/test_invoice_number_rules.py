from __future__ import annotations

import unittest

from invoice_number_rules import (
    ERP_INVOICE_RULE_VERSION,
    NO_REMITTANCE_INVOICE,
    is_valid_erp_invoice,
    normalize_erp_invoice,
)


class InvoiceNumberRuleTest(unittest.TestCase):
    def test_only_eight_or_nine_digits_enter_erp_matching(self) -> None:
        self.assertEqual(
            ERP_INVOICE_RULE_VERSION,
            "erp-invoice-number-admission@1.2.0",
        )
        self.assertEqual(normalize_erp_invoice("43-051-670"), "43051670")
        self.assertEqual(normalize_erp_invoice("431-051-670"), "431051670")
        self.assertTrue(is_valid_erp_invoice("43051670"))
        self.assertTrue(is_valid_erp_invoice("431051670"))
        self.assertFalse(is_valid_erp_invoice("1234567"))
        self.assertFalse(is_valid_erp_invoice("9999000001"))
        self.assertFalse(is_valid_erp_invoice(NO_REMITTANCE_INVOICE))


if __name__ == "__main__":
    unittest.main()
