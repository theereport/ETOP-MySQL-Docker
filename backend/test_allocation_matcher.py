from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from modules.document_intelligence.business_objects.models import OpenInvoice
from modules.document_intelligence.resolution.allocation_matcher import (
    AllocationMatcher,
)


def _invoice(number: str, amount: str, *, days_ago: int, bucket: str = "CURRENT") -> OpenInvoice:
    return OpenInvoice(
        customer_number="1000",
        invoice_number=number,
        invoice_date=date(2026, 1, 1 + days_ago),
        open_amount=Decimal(amount),
        aging_bucket=bucket,
    )


class AllocationMatcherAmbiguousSinglesTests(unittest.TestCase):
    """Two or more open invoices each exactly matching the check amount is
    a real ambiguity a human must resolve - the matcher must not silently
    guess one of them via the oldest-first greedy accumulator."""

    def test_single_exact_match_is_still_automatic(self) -> None:
        matcher = AllocationMatcher()
        invoices = [_invoice("INV-1", "100.00", days_ago=0)]
        result = matcher.match(Decimal("100.00"), invoices)
        self.assertEqual(result.status, "exact")
        self.assertEqual(result.method, "single_invoice_exact")

    def test_two_invoices_matching_the_same_amount_are_flagged_for_review(
        self,
    ) -> None:
        matcher = AllocationMatcher()
        invoices = [
            _invoice("INV-OLD", "250.00", days_ago=0),
            _invoice("INV-NEW", "250.00", days_ago=10),
        ]
        result = matcher.match(Decimal("250.00"), invoices)
        self.assertEqual(result.status, "review_required")
        self.assertEqual(result.method, "ambiguous_exact_match")
        self.assertEqual(result.alternate_matches, 2)
        self.assertFalse(
            any(w == "" for w in result.warnings),
        )

    def test_three_invoices_matching_the_same_amount_report_all_alternates(
        self,
    ) -> None:
        matcher = AllocationMatcher()
        invoices = [
            _invoice("INV-A", "75.00", days_ago=0),
            _invoice("INV-B", "75.00", days_ago=5),
            _invoice("INV-C", "75.00", days_ago=10),
        ]
        result = matcher.match(Decimal("75.00"), invoices)
        self.assertEqual(result.status, "review_required")
        self.assertEqual(result.alternate_matches, 3)


if __name__ == "__main__":
    unittest.main()
