from __future__ import annotations

import unittest
import sys
from pathlib import Path


DOCUMENT_INTELLIGENCE_ROOT = (
    Path(__file__).resolve().parent / "modules" / "document_intelligence"
)
BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(DOCUMENT_INTELLIGENCE_ROOT) not in sys.path:
    sys.path.insert(0, str(DOCUMENT_INTELLIGENCE_ROOT))

from remittance_understanding import (
    extract_remittance_evidence,
)


class RemittanceUnderstandingTest(unittest.TestCase):
    def test_money_integer_part_cannot_mask_valid_invoice(self) -> None:
        evidence = extract_remittance_evidence(
            "431063896 12345.67",
            4,
        )

        self.assertEqual(len(evidence.allocations), 1)
        self.assertEqual(
            evidence.allocations[0].invoice_number,
            "431063896",
        )
        self.assertEqual(evidence.allocations[0].net_invoice_amount, 12345.67)

    def test_pnc_trailing_minus_amounts_remain_signed_credits(self) -> None:
        evidence = extract_remittance_evidence(
            "\n".join(
                (
                    "100000001 67.98-",
                    "100000002 166.00-",
                    "100000003 914.58-",
                )
            ),
            48,
        )

        self.assertEqual(
            [item.net_invoice_amount for item in evidence.allocations],
            [-67.98, -166.00, -914.58],
        )

    def test_duplicate_leading_and_trailing_negative_sign_is_normalized(
        self,
    ) -> None:
        evidence = extract_remittance_evidence(
            "431063896 -96.00-",
            48,
            extraction_source="ocr",
            ocr_psm=6,
        )

        self.assertEqual(len(evidence.allocations), 1)
        self.assertEqual(evidence.allocations[0].invoice_number, "431063896")
        self.assertEqual(evidence.allocations[0].net_invoice_amount, -96.00)

    def test_cba_signed_remit_arithmetic_matches_check(self) -> None:
        evidence = extract_remittance_evidence(
            "\n".join(
                (
                    "100000001 34,959.36",
                    "100000002 5,696.13-",
                )
            ),
            48,
        )

        absolute_total = sum(
            abs(item.net_invoice_amount) for item in evidence.allocations
        )
        signed_total = sum(
            item.net_invoice_amount for item in evidence.allocations
        )
        self.assertAlmostEqual(absolute_total, 40655.49, places=2)
        self.assertAlmostEqual(signed_total, 29263.23, places=2)

    def test_only_unique_governed_invoice_candidate_is_admitted(self) -> None:
        evidence = extract_remittance_evidence(
            "Invoice 43051670 PO 123456 Amount 125.00",
            2,
        )

        self.assertEqual(
            [item.invoice_number for item in evidence.allocations],
            ["43051670"],
        )
        self.assertEqual(evidence.rejected_candidates, [])

    def test_invalid_lengths_are_retained_but_not_admitted(self) -> None:
        for raw in (
            "12345",
            "123456",
            "1234567",
            "1234567890",
            "12345678901",
            "123456789012",
            "9999999999",
        ):
            with self.subTest(raw=raw):
                evidence = extract_remittance_evidence(
                    f"Invoice {raw} 10.00",
                    3,
                )
                self.assertEqual(evidence.allocations, [])
                self.assertEqual(len(evidence.rejected_candidates), 1)
                self.assertIn(
                    raw,
                    evidence.rejected_candidates[0].raw_invoice_candidates,
                )

    def test_two_governed_candidates_on_one_row_remain_ambiguous(self) -> None:
        evidence = extract_remittance_evidence(
            "431063896 431063897 25.00",
            6,
        )

        self.assertEqual(evidence.allocations, [])
        self.assertEqual(len(evidence.rejected_candidates), 1)
        self.assertEqual(
            evidence.rejected_candidates[0].reason,
            "multiple_governed_invoice_candidates",
        )

    def test_horizontal_invoice_amount_pairs_are_all_admitted(self) -> None:
        evidence = extract_remittance_evidence(
            "\n".join(
                (
                    "431067399 1121.76 431067401 1240.20 "
                    "550488667 841.32 550488669 3100.50",
                    "550489157 240.00",
                )
            ),
            44,
            extraction_source="ocr",
            ocr_psm=6,
        )

        self.assertEqual(
            [item.invoice_number for item in evidence.allocations],
            [
                "431067399",
                "431067401",
                "550488667",
                "550488669",
                "550489157",
            ],
        )
        self.assertAlmostEqual(
            sum(item.net_invoice_amount for item in evidence.allocations),
            6543.78,
            places=2,
        )
        self.assertTrue(
            all(item.extraction_source == "ocr" for item in evidence.allocations)
        )
        self.assertTrue(all(item.ocr_psm == 6 for item in evidence.allocations))
        self.assertEqual(evidence.rejected_candidates, [])

    def test_labeled_hyphenated_invoice_uses_shared_normalizer(self) -> None:
        evidence = extract_remittance_evidence(
            "Invoice No: 43-106-3896 77.00",
            7,
        )

        self.assertEqual(
            [item.invoice_number for item in evidence.allocations],
            ["431063896"],
        )

    def test_arbitrary_whitespace_fragments_are_not_joined(self) -> None:
        evidence = extract_remittance_evidence(
            "43 106 3896 77.00",
            7,
        )

        self.assertEqual(evidence.allocations, [])

    def test_metadata_lines_remain_excluded(self) -> None:
        for label in (
            "Routing",
            "Account",
            "Check Number",
            "Transaction",
            "Reported Amount",
        ):
            with self.subTest(label=label):
                evidence = extract_remittance_evidence(
                    f"{label} 431063896 77.00",
                    8,
                )
                self.assertEqual(evidence.allocations, [])
                self.assertEqual(evidence.rejected_candidates, [])


if __name__ == "__main__":
    unittest.main()