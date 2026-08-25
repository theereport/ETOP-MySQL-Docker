"""Service-level tests for Pricing & Contracts, using fake repositories.

These tests never touch MaddenCo or SQLite; they verify the mapping and
scoping logic the service performs over repository-shaped dict rows.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from datetime import datetime, timezone

from modules.pricing_contracts.schemas import PricingNoteCreate
from modules.pricing_contracts.service import (
    DiscountNotFound,
    PricingContractsService,
)


FIXED_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


class FakePricingContractsRepository:
    def __init__(self, discount_rows=None, customer_class_rows=None):
        self._discount_rows = discount_rows or []
        self._customer_class_rows = customer_class_rows or []

    def search_discounts(
        self,
        *,
        customer_number=None,
        product_number="",
        product_class="",
        vendor_code="",
        active_only=False,
        limit=50,
        offset=0,
    ):
        rows = list(self._discount_rows)
        if customer_number is not None:
            rows = [r for r in rows if int(r["DCCUSTNO"]) == customer_number]
        if product_number:
            rows = [
                r for r in rows
                if product_number in str(r["DCPRODNO"]).strip()
            ]
        if product_class:
            rows = [
                r for r in rows
                if str(r["DCPRODCLAS"]).strip() == product_class
            ]
        if vendor_code:
            rows = [
                r for r in rows
                if str(r["DCVENDOR"]).strip() == vendor_code
            ]
        if active_only:
            rows = [
                r for r in rows
                if str(r.get("DCDELETE") or "").strip() == ""
            ]
        return rows[offset:offset + limit]

    def get_discount(
        self,
        *,
        customer_number,
        vendor_code,
        product_class,
        product_number,
        product_type,
    ):
        for row in self._discount_rows:
            if (
                int(row["DCCUSTNO"]) == customer_number
                and str(row["DCVENDOR"]).strip() == vendor_code.strip()
                and str(row["DCPRODCLAS"]).strip() == product_class.strip()
                and str(row["DCPRODNO"]).strip() == product_number.strip()
                and str(row["DCPRODTYPE"]).strip() == product_type.strip()
            ):
                return row
        return None

    def get_customer_classes(
        self, *, search="", active_only=False, limit=100, offset=0
    ):
        return self._customer_class_rows[offset:offset + limit]


class FakeNotesRepository:
    def __init__(self):
        self._notes: dict[str, dict] = {}

    def list_notes(
        self,
        customer_number,
        *,
        vendor_code=None,
        product_class=None,
        product_number=None,
        product_type=None,
    ):
        results = [
            note
            for note in self._notes.values()
            if note["customer_number"] == customer_number
        ]
        if vendor_code is not None:
            results = [n for n in results if n.get("vendor_code") == vendor_code]
        if product_class is not None:
            results = [n for n in results if n.get("product_class") == product_class]
        if product_number is not None:
            results = [n for n in results if n.get("product_number") == product_number]
        if product_type is not None:
            results = [n for n in results if n.get("product_type") == product_type]
        return results

    def create_note(self, record):
        snapshot_json = json.dumps(
            record["evidence_snapshot"],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        )
        stored = dict(record)
        stored["evidence_snapshot_sha256"] = hashlib.sha256(
            snapshot_json.encode("utf-8")
        ).hexdigest()
        stored["erp_write"] = False
        self._notes[record["note_id"]] = stored
        return stored


def make_discount_row(**overrides):
    row = {
        "DCCUSTNO": 1234567,
        "DCVENDOR": "007",
        "DCPRODCLAS": "10",
        "DCPRODNO": "TIRE-1",
        "DCPRODTYPE": "STK",
        "DCDELETE": "",
        "DCAMTFIX": 2.50,
        "DCCHAIN": 0,
        "DCFACTOR": 0.900,
        "DCPRICE": 89.99,
        "DCPRICECD": 1,
        "DCDTEADD": "20260101",
        "DCDTECHG": "20260110",
        "DCTIMADD": "08301500",
        "DCTIMCHG": "09151500",
        "DCUSRADD": "JCORBIT",
        "DCUSRCHG": "JCORBIT",
        "PRODCLASSNAME": "Passenger Tires",
        "PRODCLASSITEMTYPE": "T",
        "PRODCLASSACTIVE": "Y",
    }
    row.update(overrides)
    return row


def make_customer_class_row(**overrides):
    row = {
        "ID": 42,
        "CLASSNUM": "05",
        "CLASSNAME": "Fleet Accounts",
        "ACTIVE": "Y",
        "CRTSTAMP": datetime(2025, 1, 1, 9, 0, 0),
        "CRTUSER": "JCORBIT",
        "CHGSTAMP": datetime(2025, 6, 1, 9, 0, 0),
        "CHGUSER": "JCORBIT",
    }
    row.update(overrides)
    return row


class DiscountEvidenceTests(unittest.TestCase):
    def test_get_discount_raises_when_not_found(self):
        service = PricingContractsService(
            repository=FakePricingContractsRepository(discount_rows=[]),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        with self.assertRaises(DiscountNotFound):
            service.get_discount(
                customer_number=9999999,
                vendor_code="007",
                product_class="10",
                product_number="TIRE-1",
                product_type="STK",
            )

    def test_discount_mapping_from_tmdisc_row(self):
        service = PricingContractsService(
            repository=FakePricingContractsRepository(
                discount_rows=[make_discount_row()]
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_discount(
            customer_number=1234567,
            vendor_code="007",
            product_class="10",
            product_number="TIRE-1",
            product_type="STK",
        )
        discount = evidence.discount
        self.assertEqual(discount.customer_number, 1234567)
        self.assertEqual(discount.vendor_code, "007")
        self.assertEqual(discount.product_class, "10")
        self.assertEqual(discount.product_class_label, "Passenger Tires")
        self.assertTrue(discount.product_class_active)
        self.assertEqual(discount.product_number, "TIRE-1")
        self.assertTrue(discount.active)
        self.assertEqual(discount.fixed_amount, 2.50)
        self.assertEqual(discount.factor, 0.900)
        self.assertEqual(discount.override_price, 89.99)
        self.assertEqual(discount.price_code, 1)
        self.assertEqual(discount.date_added, "2026-01-01")
        self.assertEqual(discount.record_key, "1234567:10:TIRE-1:STK:007")

    def test_inactive_discount_flag_from_delete_code(self):
        service = PricingContractsService(
            repository=FakePricingContractsRepository(
                discount_rows=[make_discount_row(DCDELETE="D")]
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_discount(
            customer_number=1234567,
            vendor_code="007",
            product_class="10",
            product_number="TIRE-1",
            product_type="STK",
        )
        self.assertFalse(evidence.discount.active)

    def test_product_class_label_unresolved_when_join_misses(self):
        row = make_discount_row(
            PRODCLASSNAME=None, PRODCLASSITEMTYPE=None, PRODCLASSACTIVE=None
        )
        service = PricingContractsService(
            repository=FakePricingContractsRepository(discount_rows=[row]),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_discount(
            customer_number=1234567,
            vendor_code="007",
            product_class="10",
            product_number="TIRE-1",
            product_type="STK",
        )
        self.assertEqual(evidence.discount.product_class_label, "")
        self.assertIsNone(evidence.discount.product_class_active)

    def test_search_discounts_filters_and_counts(self):
        rows = [
            make_discount_row(),
            make_discount_row(DCVENDOR="008", DCPRODNO="TIRE-2"),
        ]
        service = PricingContractsService(
            repository=FakePricingContractsRepository(discount_rows=rows),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        response = service.search_discounts(customer_number=1234567, vendor_code="008")
        self.assertEqual(response.count, 1)
        self.assertEqual(response.discounts[0].product_number, "TIRE-2")

    def test_gaps_list_is_always_present_and_names_dcvendor_identity_gap(self):
        service = PricingContractsService(
            repository=FakePricingContractsRepository(
                discount_rows=[make_discount_row()]
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        response = service.search_discounts(customer_number=1234567)
        gap_codes = {gap.code for gap in response.gaps}
        self.assertIn("vendor_rebate_accrual_ledger", gap_codes)
        self.assertIn("contract_compliance_scoring", gap_codes)
        self.assertIn("vendor_code_identity_resolution", gap_codes)
        self.assertIn("price_code_mechanism_mapping", gap_codes)


class CustomerClassTests(unittest.TestCase):
    def test_customer_class_mapping(self):
        service = PricingContractsService(
            repository=FakePricingContractsRepository(
                customer_class_rows=[make_customer_class_row()]
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        response = service.list_customer_classes()
        self.assertEqual(response.count, 1)
        record = response.customer_classes[0]
        self.assertEqual(record.class_num, "05")
        self.assertEqual(record.class_name, "Fleet Accounts")
        self.assertTrue(record.active)
        self.assertEqual(record.created_at, "2025-01-01T09:00:00")


class PricingNoteTests(unittest.TestCase):
    def test_create_note_embeds_matched_discount_snapshot_and_is_append_only_shaped(self):
        service = PricingContractsService(
            repository=FakePricingContractsRepository(
                discount_rows=[make_discount_row()]
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
            note_id_factory=lambda: "pricing-note-fixed",
        )
        record = service.create_note(
            PricingNoteCreate(
                customer_number=1234567,
                vendor_code="007",
                author_identity="J. Buyer",
                note="Vendor promised a 2% Q1 rebate on fleet volume.",
            )
        )
        self.assertEqual(record.note_id, "pricing-note-fixed")
        self.assertEqual(record.customer_number, 1234567)
        self.assertEqual(record.vendor_code, "007")
        self.assertEqual(record.matched_discount_count, 1)
        self.assertEqual(record.decision_effect, "none")
        self.assertFalse(record.erp_write)
        self.assertEqual(
            record.evidence_snapshot["scope"]["customer_number"], 1234567
        )
        self.assertEqual(
            len(record.evidence_snapshot["matched_discounts"]), 1
        )
        self.assertEqual(len(record.evidence_snapshot_sha256), 64)

        history = service.list_notes(1234567)
        self.assertEqual(history.count, 1)
        self.assertEqual(history.notes[0].note_id, "pricing-note-fixed")

    def test_create_note_succeeds_with_zero_matching_discounts(self):
        service = PricingContractsService(
            repository=FakePricingContractsRepository(discount_rows=[]),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        record = service.create_note(
            PricingNoteCreate(
                customer_number=7654321,
                vendor_code="123",
                author_identity="J. Buyer",
                note="Vendor rebate program commitment, no override row yet.",
            )
        )
        self.assertEqual(record.matched_discount_count, 0)
        self.assertEqual(record.evidence_snapshot["matched_discounts"], [])

    def test_list_notes_filters_by_vendor_code(self):
        service = PricingContractsService(
            repository=FakePricingContractsRepository(
                discount_rows=[make_discount_row()]
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        service.create_note(
            PricingNoteCreate(
                customer_number=1234567,
                vendor_code="007",
                author_identity="A",
                note="Rebate note for vendor 007.",
            )
        )
        service.create_note(
            PricingNoteCreate(
                customer_number=1234567,
                vendor_code="008",
                author_identity="A",
                note="Rebate note for vendor 008.",
            )
        )
        filtered = service.list_notes(1234567, vendor_code="008")
        self.assertEqual(filtered.count, 1)
        self.assertEqual(filtered.notes[0].vendor_code, "008")

        unfiltered = service.list_notes(1234567)
        self.assertEqual(unfiltered.count, 2)


if __name__ == "__main__":
    unittest.main()
