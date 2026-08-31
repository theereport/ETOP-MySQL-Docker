"""Service-level tests for Vendor Intelligence, using fake repositories.

These tests never touch MaddenCo or SQLite; they verify the arithmetic and
mapping the service performs over repository-shaped dict rows.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from datetime import datetime, timezone

from modules.vendor_intelligence.schemas import VendorNoteCreate
from modules.vendor_intelligence.service import (
    VendorIntelligenceService,
    VendorNotFound,
)


FIXED_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


class FakeVendorRepository:
    def __init__(self, vendor_row=None, open_pos=None, receipts=None,
                 open_invoices=None, paid_invoices=None,
                 fill_rate_summary=None):
        self._vendor_row = vendor_row
        self._open_pos = open_pos or []
        self._receipts = receipts or []
        self._open_invoices = open_invoices or []
        self._paid_invoices = paid_invoices or []
        self._fill_rate_summary = fill_rate_summary

    def search_vendors(self, **kwargs):
        return [self._vendor_row] if self._vendor_row else []

    def get_vendor(self, vendor_number):
        if self._vendor_row and int(self._vendor_row["PVNUMVEN"]) == vendor_number:
            return self._vendor_row
        return None

    def get_open_purchase_orders(self, vendor_number, limit=50):
        return self._open_pos

    def get_po_fill_rate_summary(self, vendor_number, *, window_days=365):
        return self._fill_rate_summary

    def get_receiving_history(self, vendor_number, limit=50):
        return self._receipts

    def get_open_payable_invoices(self, vendor_number, limit=100):
        return self._open_invoices

    def get_paid_payable_invoices(self, vendor_number, limit=50):
        return self._paid_invoices


class FakeNotesRepository:
    def __init__(self):
        self._notes: dict[str, dict] = {}

    def list_notes(self, vendor_number):
        return [
            note
            for note in self._notes.values()
            if note["vendor_number"] == vendor_number
        ]

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


def make_vendor_row(**overrides):
    row = {
        "PVNUMVEN": 1234567,
        "PVNAMVEN": "Acme Tire Supply",
        "PVNAMSRT": "ACME TIRE",
        "PVNAMCNT": "Jane Buyer",
        "PVADDR1": "100 Main St",
        "PVADDR2": "",
        "PVADDR3": "",
        "PVADDR4": "",
        "PVZIP": "44601",
        "PVCOUNTRY": "USA",
        "PVPHONE": 3305551234,
        "PVNBFAX": None,
        "PVEMAIL": "ap@acmetire.example",
        "PVCODDEL": "A",
        "PVTYPVEN": "1",
        "PVSTOREN": 0,
        "PVCODTREM": "030",
        "PVPOREQ": "Y",
        "PVFLGNORCV": "N",
        "PV1099OP": "Y",
        "PVCOD1099": "07",
        "PVAMT1099": None,
        "PVIDFED": "12-3456789",
        "PVTYPPMT": "ACH",
        "PVTYPBNK": "C",
        "PVACCBNK": "0012345678",
        "PVROUBNK": 41200555,
        "PVPURMTD": 15000.50,
        "PVPURYTD": 180000.75,
        "PVPURLSTYR": 900000.00,
        "PVDISCMTD": 150.25,
        "PVDISCYTD": 1800.00,
        "PVDISCLMTD": 25.00,
        "PVDISCLYTD": 200.00,
        "PVAMTLPD": 4200.00,
        "PVDTELPD": "20260110",
        "PVCHKLPD": 88421,
    }
    row.update(overrides)
    return row


class VendorEvidenceTests(unittest.TestCase):
    def test_get_vendor_evidence_raises_when_vendor_not_found(self):
        service = VendorIntelligenceService(
            repository=FakeVendorRepository(vendor_row=None),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        with self.assertRaises(VendorNotFound):
            service.get_vendor_evidence(9999999)

    def test_identity_and_purchase_volume_map_from_pmvend(self):
        service = VendorIntelligenceService(
            repository=FakeVendorRepository(vendor_row=make_vendor_row()),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_vendor_evidence(1234567)

        self.assertEqual(evidence.identity.vendor_number, 1234567)
        self.assertEqual(evidence.identity.vendor_name, "Acme Tire Supply")
        self.assertTrue(evidence.identity.active)
        self.assertTrue(evidence.identity.po_required)
        self.assertTrue(evidence.identity.is_1099)
        self.assertEqual(evidence.identity.tax_1099_code, "07")
        self.assertTrue(evidence.identity.federal_id_on_file)
        self.assertEqual(evidence.identity.payment_type, "ACH")
        self.assertTrue(evidence.identity.eft_bank_info_on_file)
        # The raw federal ID and bank account/routing numbers must never be
        # echoed back.
        dumped = evidence.model_dump_json()
        self.assertNotIn("12-3456789", dumped)
        self.assertNotIn("0012345678", dumped)
        self.assertNotIn("41200555", dumped)
        self.assertEqual(evidence.purchase_volume.year_to_date, 180000.75)
        self.assertEqual(evidence.purchase_volume.date_last_paid, "2026-01-10")

    def test_no_eft_info_when_bank_fields_blank(self):
        service = VendorIntelligenceService(
            repository=FakeVendorRepository(
                vendor_row=make_vendor_row(PVACCBNK="", PVROUBNK=0)
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_vendor_evidence(1234567)
        self.assertFalse(evidence.identity.eft_bank_info_on_file)

    def test_discount_capture_rate_computed_from_taken_and_lost(self):
        service = VendorIntelligenceService(
            repository=FakeVendorRepository(
                vendor_row=make_vendor_row(PVDISCYTD=900.0, PVDISCLYTD=100.0)
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_vendor_evidence(1234567)
        rate = evidence.purchase_volume.discount_capture_rate_year_to_date
        self.assertEqual(rate.status, "available")
        self.assertEqual(rate.value, 90.0)

    def test_discount_capture_rate_unavailable_when_nothing_taken_or_lost(self):
        service = VendorIntelligenceService(
            repository=FakeVendorRepository(
                vendor_row=make_vendor_row(PVDISCYTD=0.0, PVDISCLYTD=0.0)
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_vendor_evidence(1234567)
        rate = evidence.purchase_volume.discount_capture_rate_year_to_date
        self.assertEqual(rate.status, "unavailable")
        self.assertIsNone(rate.value)

    def test_inactive_vendor_flag_from_delete_code(self):
        service = VendorIntelligenceService(
            repository=FakeVendorRepository(
                vendor_row=make_vendor_row(PVCODDEL="D")
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_vendor_evidence(1234567)
        self.assertFalse(evidence.identity.active)

    def test_open_purchase_order_totals_sum_line_aggregates(self):
        open_pos = [
            {
                "TPHNB": 5001, "TPHDTE": "20260101", "TPHDTEREQ": "20260201",
                "TPHCDSTS": "O", "TPHFLGCMP": "N", "TPHTOTCST": 1000.00,
                "TPHVIA": "UPS", "TPHBUYNUM": 12,
                "TOTAL_ORDERED": 100, "TOTAL_RECEIVED": 40,
                "TOTAL_BACKORDER": 60, "LINE_COUNT": 3,
            },
            {
                "TPHNB": 5002, "TPHDTE": "20260105", "TPHDTEREQ": None,
                "TPHCDSTS": "O", "TPHFLGCMP": "N", "TPHTOTCST": 500.00,
                "TPHVIA": "", "TPHBUYNUM": 0,
                "TOTAL_ORDERED": 20, "TOTAL_RECEIVED": 20,
                "TOTAL_BACKORDER": 0, "LINE_COUNT": 1,
            },
        ]
        service = VendorIntelligenceService(
            repository=FakeVendorRepository(
                vendor_row=make_vendor_row(), open_pos=open_pos,
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_vendor_evidence(1234567)
        self.assertEqual(evidence.purchase_orders.open_order_count, 2)
        self.assertEqual(evidence.purchase_orders.open_order_total_cost, 1500.00)
        self.assertIsNone(evidence.purchase_orders.open_orders[1].buyer_number)

    def test_receiving_cost_variance_is_always_unavailable(self):
        # Confirmed live: TRCDCOSDIF is exactly 0 across every row this
        # MaddenCo instance has ever recorded (never a real observation),
        # and TRCDCOS always just copies TRCDCOSPO when set - there is no
        # usable price/cost variance signal in receiving data here, so
        # this is disclosed as unavailable regardless of what any single
        # row's TRCDCOSDIF happens to say. Per-line raw values are still
        # passed through, not hidden - only the misleading aggregate and
        # "complete" status are suppressed.
        service_with_receipts = VendorIntelligenceService(
            repository=FakeVendorRepository(
                vendor_row=make_vendor_row(),
                receipts=[
                    {
                        "TRCDNUMPO": 5001, "TRCDNUMPRD": "TIRE-1",
                        "TRCDPRDDSC": "Widget Tire", "TRCDQTY": 10,
                        "TRCDCOS": 50.0, "TRCDCOSPO": 48.0,
                        "TRCDCOSDIF": 2.0, "TRCDDOT": "ABC123",
                        "TRCDDOTDTE": "20260101", "TRCDDTECRT": "20260102",
                    },
                ],
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence_with_receipts = service_with_receipts.get_vendor_evidence(1234567)
        self.assertEqual(
            evidence_with_receipts.receiving.cost_variance_completeness, "unavailable"
        )
        self.assertIsNone(evidence_with_receipts.receiving.total_cost_variance)
        self.assertEqual(
            evidence_with_receipts.receiving.recent_receipts[0].cost_variance, 2.0
        )

        service_unavailable = VendorIntelligenceService(
            repository=FakeVendorRepository(vendor_row=make_vendor_row(), receipts=[]),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        empty_evidence = service_unavailable.get_vendor_evidence(1234567)
        self.assertEqual(empty_evidence.receiving.cost_variance_completeness, "unavailable")
        self.assertIsNone(empty_evidence.receiving.total_cost_variance)

    def test_performance_fill_rate_computed_from_po_history(self):
        service = VendorIntelligenceService(
            repository=FakeVendorRepository(
                vendor_row=make_vendor_row(),
                fill_rate_summary={
                    "po_count": 12,
                    "quantity_ordered": 200,
                    "quantity_received": 150,
                    "quantity_backorder": 50,
                },
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_vendor_evidence(1234567)
        self.assertEqual(evidence.performance.po_count, 12)
        self.assertEqual(evidence.performance.fill_rate_percent, 75.0)
        self.assertEqual(evidence.performance.fill_rate_status, "available")
        self.assertEqual(evidence.performance.on_time_delivery_status, "unavailable")
        self.assertEqual(
            evidence.performance.quality_and_chargeback_status, "unavailable"
        )

    def test_performance_fill_rate_unavailable_with_no_po_history(self):
        service = VendorIntelligenceService(
            repository=FakeVendorRepository(
                vendor_row=make_vendor_row(),
                fill_rate_summary={
                    "po_count": 0,
                    "quantity_ordered": 0,
                    "quantity_received": 0,
                    "quantity_backorder": 0,
                },
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_vendor_evidence(1234567)
        self.assertIsNone(evidence.performance.fill_rate_percent)
        self.assertEqual(evidence.performance.fill_rate_status, "unavailable")

    def test_payables_totals_sum_open_invoice_amounts(self):
        service = VendorIntelligenceService(
            repository=FakeVendorRepository(
                vendor_row=make_vendor_row(),
                open_invoices=[
                    {
                        "PMHNBINV": "INV-1", "PMHAMTINV": 100.0,
                        "PMHAMTDIS": 2.0, "PMHDTEINV": "20260101",
                        "PMHDTEDUE": "20260201", "PMHFLGHLD": "N",
                        "PMHPR": 1, "PMHYR": 2026,
                    },
                    {
                        "PMHNBINV": "INV-2", "PMHAMTINV": 250.0,
                        "PMHAMTDIS": 0.0, "PMHDTEINV": "20260103",
                        "PMHDTEDUE": "20260203", "PMHFLGHLD": "Y",
                        "PMHPR": 1, "PMHYR": 2026,
                    },
                ],
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_vendor_evidence(1234567)
        self.assertEqual(evidence.payables.open_invoice_count, 2)
        self.assertEqual(evidence.payables.open_invoice_total, 350.0)
        self.assertTrue(evidence.payables.open_invoices[1].on_hold)

    def test_gaps_list_is_always_present_and_non_empty(self):
        service = VendorIntelligenceService(
            repository=FakeVendorRepository(vendor_row=make_vendor_row()),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_vendor_evidence(1234567)
        gap_codes = {gap.code for gap in evidence.gaps}
        self.assertIn("vendor_scorecard", gap_codes)
        self.assertIn("on_time_delivery_definition", gap_codes)


class VendorNoteTests(unittest.TestCase):
    def test_create_note_embeds_vendor_evidence_snapshot_and_is_append_only_shaped(self):
        service = VendorIntelligenceService(
            repository=FakeVendorRepository(vendor_row=make_vendor_row()),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
            note_id_factory=lambda: "vendor-note-fixed",
        )
        record = service.create_note(
            1234567,
            VendorNoteCreate(
                author_identity="J. Buyer",
                note="Confirmed lead time improved to 3 days.",
            ),
        )
        self.assertEqual(record.note_id, "vendor-note-fixed")
        self.assertEqual(record.vendor_name, "Acme Tire Supply")
        self.assertEqual(record.decision_effect, "none")
        self.assertFalse(record.erp_write)
        self.assertEqual(
            record.evidence_snapshot["identity"]["vendor_number"], 1234567
        )
        self.assertEqual(len(record.evidence_snapshot_sha256), 64)

        history = service.list_notes(1234567)
        self.assertEqual(history.count, 1)
        self.assertEqual(history.notes[0].note_id, "vendor-note-fixed")

    def test_create_note_raises_for_unknown_vendor(self):
        service = VendorIntelligenceService(
            repository=FakeVendorRepository(vendor_row=None),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        with self.assertRaises(VendorNotFound):
            service.create_note(
                1234567,
                VendorNoteCreate(author_identity="J. Buyer", note="test"),
            )


if __name__ == "__main__":
    unittest.main()
