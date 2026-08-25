from decimal import Decimal
import unittest

from modules.payment_notes.matching import (
    BankPaymentItem,
    ExpectedPayment,
    SignatureEvidence,
    enforce_deposit_one_to_one,
    enrich_signatures,
    match_payment_item,
    normalize_check_number,
)


def bank(check="00042", amount="10.00", item_id="bank-1"):
    return BankPaymentItem(item_id, 2, "L22", "22", "D1", "Business Check", check,
                           normalize_check_number(check), Decimal(amount), amount, "a" * 64)


def expected(payment_id, check="42", amount="10.00", invoice_numbers=()):
    return ExpectedPayment(payment_id, "C1", "R1", "CHECK", check,
                           normalize_check_number(check), Decimal(amount),
                           invoice_numbers=invoice_numbers)


class MatchingTests(unittest.TestCase):
    def test_check_normalization_removes_zeroes_and_preserves_all_zero_identity(self):
        self.assertEqual(normalize_check_number("00042"), "42")
        self.assertEqual(normalize_check_number("000"), "0")
        self.assertEqual(normalize_check_number(0), "0")
        self.assertEqual(normalize_check_number(""), "")

    def test_amount_disambiguates_but_equal_exact_candidates_stay_ambiguous(self):
        decision = match_payment_item(bank(), [expected("p1", amount="9.00"), expected("p2")])
        self.assertEqual(decision.disposition, "EXACT_AMOUNT_DISAMBIGUATED")
        self.assertEqual(decision.selected_payment_id, "p2")
        tied = match_payment_item(bank(), [expected("p1"), expected("p2")])
        self.assertEqual(tied.disposition, "AMBIGUOUS")
        self.assertIsNone(tied.selected_payment_id)

    def test_signature_is_post_match_enrichment_and_never_breaks_tie(self):
        tied = match_payment_item(bank(), [expected("p1", invoice_numbers=("10000001",)), expected("p2")])
        enriched = enrich_signatures(tied, {("C1", "10000001"): (
            SignatureEvidence("C1", "10000001", "Signer", "proof.png", "", "", "1"),)})
        self.assertIsNone(enriched.selected_payment_id)
        self.assertEqual(enriched.disposition, "AMBIGUOUS")
        self.assertTrue(enriched.candidates[0].signatures)

    def test_run_wide_one_to_one_blocks_duplicate_automatic_reservation(self):
        decisions = {"a": match_payment_item(bank(item_id="a"), [expected("p1")]),
                     "b": match_payment_item(bank(item_id="b"), [expected("p1")])}
        safe = enforce_deposit_one_to_one(decisions)
        self.assertEqual({value.disposition for value in safe.values()}, {"AMBIGUOUS_ASSIGNMENT"})
        self.assertTrue(all(value.selected_payment_id is None for value in safe.values()))

    def test_amount_only_population_reports_truncation_and_completeness(self):
        candidates = [
            expected(f"p{index}", check=str(1000 + index))
            for index in range(30)
        ]
        decision = match_payment_item(
            bank(check="999999"),
            candidates,
            max_amount_review_candidates=25,
        )
        self.assertEqual(decision.disposition, "AMOUNT_ONLY_REVIEW")
        self.assertEqual(decision.candidate_total_count, 30)
        self.assertEqual(decision.candidate_display_cap, 25)
        self.assertEqual(len(decision.candidates), 25)
        self.assertFalse(decision.candidate_population_complete)
        self.assertTrue(any("truncated" in warning for warning in decision.warnings))
