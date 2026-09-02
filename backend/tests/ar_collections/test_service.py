"""Service-level tests for AR Collections, using fake repositories.

These tests never touch MaddenCo or SQLite; they verify the arithmetic and
mapping the service performs over repository-shaped dict rows.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from datetime import datetime, timezone

from modules.ar_collections.schemas import ARCollectionsNoteCreate
from modules.ar_collections.service import (
    ARCollectionsCustomerNotFound,
    ARCollectionsService,
)


FIXED_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


class FakeCustomerSummaryService:
    def __init__(self, summary=None):
        self._summary = summary

    def summary(self, customer_number):
        if self._summary is None:
            return None
        if int(self._summary["customer_number"]) != customer_number:
            return None
        return self._summary


class FakeARCollectionsRepository:
    def __init__(
        self,
        *,
        open_items=None,
        item_history=None,
        transaction_headers=None,
        transaction_applications=None,
        gl_distributions=None,
        erp_collection_notes=None,
        credit_management_headers=None,
        credit_management_detail_by_key=None,
        aging_snapshots=None,
    ):
        self._open_items = open_items or []
        self._item_history = item_history or []
        self._transaction_headers = transaction_headers or []
        self._transaction_applications = transaction_applications or []
        self._gl_distributions = gl_distributions or []
        self._erp_collection_notes = erp_collection_notes or []
        self._credit_management_headers = credit_management_headers or []
        self._credit_management_detail_by_key = (
            credit_management_detail_by_key or {}
        )
        self._aging_snapshots = aging_snapshots or []

    def get_open_items(self, customer_number, limit=200):
        return self._open_items

    def get_item_history(self, customer_number, limit=200):
        return self._item_history

    def get_transaction_history(self, customer_number, limit=100):
        return self._transaction_headers

    def get_transaction_applications(self, customer_number, limit=200):
        return self._transaction_applications

    def get_gl_distributions(self, customer_number, limit=100):
        return self._gl_distributions

    def get_erp_collection_notes(self, customer_number, limit=100):
        return self._erp_collection_notes

    def get_credit_management_headers(self, customer_number, limit=50):
        return self._credit_management_headers

    def get_credit_management_detail(self, header_key):
        return self._credit_management_detail_by_key.get(header_key, [])

    def get_credit_management_detail_for_headers(self, header_keys):
        return [
            detail
            for header_key in header_keys
            for detail in self._credit_management_detail_by_key.get(
                header_key, []
            )
        ]

    def get_aging_snapshots(self, customer_number, limit=12):
        return self._aging_snapshots


class FakeNotesRepository:
    def __init__(self):
        self._notes: dict[str, dict] = {}

    def list_notes(self, customer_number):
        return [
            note
            for note in self._notes.values()
            if note["customer_number"] == customer_number
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


def make_customer_summary(**overrides):
    summary = {
        "customer_number": 555000,
        "customer_name": "Main Street Tire",
        "general": {
            "dba_name": "",
            "address_lines": ["100 Main St"],
            "zip_code": "44601",
            "country": "USA",
            "phone": "(330) 555-1234",
            "email": "ap@mainstreettire.example",
            "route_code": "R1",
            "store_number": 3,
            "salesman_number": 12,
            "customer_type": "1",
            "customer_class": "A",
            "active": True,
        },
    }
    summary.update(overrides)
    return summary


def make_service(
    *,
    summary=None,
    repository=None,
    notes_repository=None,
    note_id_factory=None,
):
    return ARCollectionsService(
        repository=repository or FakeARCollectionsRepository(),
        notes_repository=notes_repository or FakeNotesRepository(),
        customer_summary_service=FakeCustomerSummaryService(summary=summary),
        clock=lambda: FIXED_NOW,
        note_id_factory=note_id_factory,
    )


class ARCollectionsEvidenceTests(unittest.TestCase):
    def test_get_customer_collections_raises_when_customer_not_found(self):
        service = make_service(summary=None)
        with self.assertRaises(ARCollectionsCustomerNotFound):
            service.get_customer_collections(555000)

    def test_identity_maps_from_customer_360_summary(self):
        service = make_service(summary=make_customer_summary())
        evidence = service.get_customer_collections(555000)

        self.assertEqual(evidence.customer.customer_number, 555000)
        self.assertEqual(evidence.customer.customer_name, "Main Street Tire")
        self.assertEqual(evidence.customer.route_code, "R1")
        self.assertTrue(evidence.customer.active)

    def test_open_ar_days_past_due_and_total_are_arithmetic(self):
        open_items = [
            {
                "TARONUMCST": 555000, "TARONUMINV": 90001,
                "TAROTYPTRN": "IN", "TAROENTTYP": "01", "TARODBCR": "D",
                "TAROAMTORG": 500.00, "TAROAMTOPN": 500.00,
                "TAROAMTDSC": 0.0, "TAROCSHDSC": 0.0,
                "TAROCDTERM": "030", "TAROADJRSN": "",
                "TARONUMREF": "INV90001", "TARODTE": "20251215",
                "TARODTEDUE": "20260101", "TAROHISTYN": "N",
            },
            {
                "TARONUMCST": 555000, "TARONUMINV": 90002,
                "TAROTYPTRN": "IN", "TAROENTTYP": "01", "TARODBCR": "D",
                "TAROAMTORG": 250.00, "TAROAMTOPN": 250.00,
                "TAROAMTDSC": 0.0, "TAROCSHDSC": 0.0,
                "TAROCDTERM": "030", "TAROADJRSN": "",
                "TARONUMREF": "INV90002", "TARODTE": "20260110",
                "TARODTEDUE": "20260201", "TAROHISTYN": "N",
            },
            {
                "TARONUMCST": 555000, "TARONUMINV": 90003,
                "TAROTYPTRN": "CM", "TAROENTTYP": "02", "TARODBCR": "C",
                "TAROAMTORG": 50.00, "TAROAMTOPN": 50.00,
                "TAROAMTDSC": 0.0, "TAROCSHDSC": 0.0,
                "TAROCDTERM": "", "TAROADJRSN": "PRICE ADJ",
                "TARONUMREF": "", "TARODTE": "20260112",
                "TARODTEDUE": None, "TAROHISTYN": "N",
            },
        ]
        service = make_service(
            summary=make_customer_summary(),
            repository=FakeARCollectionsRepository(open_items=open_items),
        )
        evidence = service.get_customer_collections(555000)

        self.assertEqual(evidence.open_ar.item_count, 3)
        self.assertEqual(evidence.open_ar.total_open_amount, 800.00)

        first, second, third = evidence.open_ar.open_items
        # FIXED_NOW date is 2026-01-15.
        self.assertEqual(first.due_date, "2026-01-01")
        self.assertEqual(first.days_past_due, 14)
        self.assertEqual(second.due_date, "2026-02-01")
        self.assertEqual(second.days_past_due, -17)
        self.assertIsNone(third.due_date)
        self.assertIsNone(third.days_past_due)
        self.assertEqual(third.adjustment_reason, "PRICE ADJ")

    def test_item_history_maps_closed_arop_rows_separately_from_open(self):
        history_rows = [
            {
                "TARONUMCST": 555000, "TARONUMINV": 80001,
                "TAROTYPTRN": "IN", "TAROENTTYP": "01", "TARODBCR": "D",
                "TAROAMTORG": 402.00, "TAROAMTOPN": 0.0,
                "TAROAMTDSC": 0.0, "TAROCSHDSC": 0.0,
                "TAROCDTERM": "030", "TAROADJRSN": "",
                "TARONUMREF": "", "TARODTE": "20160430",
                "TARODTEDUE": "20160530", "TAROHISTYN": "Y",
            },
        ]
        service = make_service(
            summary=make_customer_summary(),
            repository=FakeARCollectionsRepository(
                open_items=[], item_history=history_rows,
            ),
        )
        evidence = service.get_customer_collections(555000)

        # Closed items never appear in open_ar...
        self.assertEqual(evidence.open_ar.item_count, 0)
        # ...they appear in item_history instead, with open_amount at 0.
        self.assertEqual(evidence.item_history.item_count, 1)
        closed_item = evidence.item_history.items[0]
        self.assertEqual(closed_item.invoice_number, 80001)
        self.assertEqual(closed_item.original_amount, 402.00)
        self.assertEqual(closed_item.open_amount, 0.0)
        self.assertTrue(closed_item.purged_to_history)

    def test_transaction_history_and_applications_map_and_join(self):
        headers = [
            {
                "TNARSEQ": 7001, "TNARNUMCUS": 555000, "TNARNUMINV": 90001,
                "TNARDTE": "20260110", "TNARDTEDUE": "20260201",
                "TNARAMTORG": 500.00, "TNARDBCR": "D", "TNARENTTYP": "01",
                "TNARTYPTRN": "IN", "TNARNUMREF": "INV90001",
                "TNARSTATUS": "O", "TNARPER": 1, "TNARYEAR": 2026,
                "TNARCSHDSC": 0.0,
            },
        ]
        applications = [
            {
                "HEADER_TNARSEQ": 7001, "HEADER_TNARNUMINV": 90001,
                "HEADER_TNARNUMREF": "INV90001", "HEADER_TNARDTE": "20260110",
                "TNARDTLSEQ": 1, "TNARINVAPL": 90001,
                "TNARAMTAPL": 500.00, "TNARDISAPL": 5.00,
                "TNARGLACCT": 1200, "TNARGLDIV": 1, "TNARGLDPT": 10,
                "TNARDTECRT": "20260110",
            },
        ]
        service = make_service(
            summary=make_customer_summary(),
            repository=FakeARCollectionsRepository(
                transaction_headers=headers,
                transaction_applications=applications,
            ),
        )
        evidence = service.get_customer_collections(555000)

        self.assertEqual(evidence.transactions.transaction_count, 1)
        self.assertEqual(evidence.transactions.application_count, 1)
        transaction = evidence.transactions.transactions[0]
        self.assertEqual(transaction.sequence, 7001)
        self.assertEqual(transaction.original_amount, 500.00)

        application = evidence.transactions.applications[0]
        self.assertEqual(application.header_sequence, 7001)
        self.assertEqual(application.applied_invoice_number, 90001)
        self.assertEqual(application.amount_applied, 500.00)
        self.assertEqual(application.gl_account, 1200)

    def test_gl_distribution_totals_sum_debit_and_credit(self):
        gl_rows = [
            {
                "TNGLNBCST": 555000, "TNGLNBACCT": 4000, "TNGLNBDV": 1,
                "TNGLNBDP": 10, "TNGLAMTDB": 100.00, "TNGLAMTCR": 0.0,
                "TNGLQTY": 4, "TNGLDSC": "Tire sale", "TNGLDTECRT": "20260110",
            },
            {
                "TNGLNBCST": 555000, "TNGLNBACCT": 1200, "TNGLNBDV": 1,
                "TNGLNBDP": 10, "TNGLAMTDB": 0.0, "TNGLAMTCR": 100.00,
                "TNGLQTY": 0, "TNGLDSC": "AR offset", "TNGLDTECRT": "20260110",
            },
        ]
        service = make_service(
            summary=make_customer_summary(),
            repository=FakeARCollectionsRepository(gl_distributions=gl_rows),
        )
        evidence = service.get_customer_collections(555000)

        self.assertEqual(evidence.gl_distributions.line_count, 2)
        self.assertEqual(
            evidence.gl_distributions.total_debit_amount, 100.00
        )
        self.assertEqual(
            evidence.gl_distributions.total_credit_amount, 100.00
        )

    def test_erp_notes_and_credit_management_notes_map(self):
        collection_notes = [
            {
                "CUSTNUM": 555000, "NOTES": "Called customer, promised pay.",
                "CRTSTAMP": datetime(2026, 1, 10, 9, 30),
                "CRTUSER": "JDOE", "CHGSTAMP": None, "CHGUSER": "",
            },
        ]
        credit_headers = [
            {
                "TCMOHNBKY": 42, "CUNUMBER": 555000,
                "TCMOHTXT": "Past due follow-up",
                "TCMOHDTDO": "20260120", "TCMOHDTDN": None,
                "TCMOHDTCRT": "20260110", "TCMOHUSRCR": "JDOE",
                "TCMOHDTCHG": "20260111", "TCMOHUSRCH": "JDOE",
            },
        ]
        credit_detail_by_key = {
            42: [
                {"TCMOHNBKY": 42, "TCMODNBSEQ": 1, "TCMODTXT": "Left voicemail."},
                {"TCMOHNBKY": 42, "TCMODNBSEQ": 2, "TCMODTXT": "Customer called back."},
            ],
        }
        service = make_service(
            summary=make_customer_summary(),
            repository=FakeARCollectionsRepository(
                erp_collection_notes=collection_notes,
                credit_management_headers=credit_headers,
                credit_management_detail_by_key=credit_detail_by_key,
            ),
        )
        evidence = service.get_customer_collections(555000)

        self.assertEqual(evidence.erp_collection_notes.count, 1)
        self.assertEqual(
            evidence.erp_collection_notes.notes[0].note_text,
            "Called customer, promised pay.",
        )

        self.assertEqual(evidence.erp_credit_management_notes.count, 1)
        note = evidence.erp_credit_management_notes.notes[0]
        self.assertEqual(note.header_key, 42)
        self.assertEqual(note.regarding, "Past due follow-up")
        self.assertEqual(
            note.detail_lines,
            ["Left voicemail.", "Customer called back."],
        )

    def test_credit_management_detail_is_grouped_by_the_right_header(self):
        # The batched detail lookup returns rows for every header in one
        # call - each header's notes must end up attached to exactly that
        # header, not mixed together or attached to the wrong one.
        credit_headers = [
            {
                "TCMOHNBKY": 42, "CUNUMBER": 555000,
                "TCMOHTXT": "Past due follow-up",
                "TCMOHDTDO": "20260120", "TCMOHDTDN": None,
                "TCMOHDTCRT": "20260110", "TCMOHUSRCR": "JDOE",
                "TCMOHDTCHG": "20260111", "TCMOHUSRCH": "JDOE",
            },
            {
                "TCMOHNBKY": 43, "CUNUMBER": 555000,
                "TCMOHTXT": "Dispute on invoice 9001",
                "TCMOHDTDO": "20260122", "TCMOHDTDN": None,
                "TCMOHDTCRT": "20260112", "TCMOHUSRCR": "ASMITH",
                "TCMOHDTCHG": None, "TCMOHUSRCH": "",
            },
        ]
        credit_detail_by_key = {
            42: [
                {"TCMOHNBKY": 42, "TCMODNBSEQ": 1, "TCMODTXT": "Left voicemail."},
            ],
            43: [
                {"TCMOHNBKY": 43, "TCMODNBSEQ": 1, "TCMODTXT": "Credit memo requested."},
                {"TCMOHNBKY": 43, "TCMODNBSEQ": 2, "TCMODTXT": "Credit memo issued."},
            ],
        }
        service = make_service(
            summary=make_customer_summary(),
            repository=FakeARCollectionsRepository(
                credit_management_headers=credit_headers,
                credit_management_detail_by_key=credit_detail_by_key,
            ),
        )
        evidence = service.get_customer_collections(555000)

        self.assertEqual(evidence.erp_credit_management_notes.count, 2)
        by_key = {
            note.header_key: note
            for note in evidence.erp_credit_management_notes.notes
        }
        self.assertEqual(by_key[42].detail_lines, ["Left voicemail."])
        self.assertEqual(
            by_key[43].detail_lines,
            ["Credit memo requested.", "Credit memo issued."],
        )

    def test_aging_history_snapshots_map(self):
        aging_rows = [
            {
                "TCCHNUMCUS": 555000, "TCCHDTE": "20260101",
                "TCCHAGE1": 0.0, "TCCHAGE2": 800.0, "TCCHAGE3": 0.0,
                "TCCHAGE4": 0.0, "TCCHAGE5": 0.0, "TCCHAGE6": 0.0,
                "TCCHBAL": 800.0, "TCCHBALHI": 1200.0, "TCCHDISMTD": 5.0,
                "TCCHCRDLMT": 5000.0, "TCCHDTELPD": "20251215",
                "TCCHDTELST": "20260101", "TCCHAMTLPD": 500.0,
                "TCCHNUMSLM": 12, "TCCHSALMTD": 2000.0,
            },
        ]
        service = make_service(
            summary=make_customer_summary(),
            repository=FakeARCollectionsRepository(aging_snapshots=aging_rows),
        )
        evidence = service.get_customer_collections(555000)

        self.assertEqual(evidence.aging_history.snapshot_count, 1)
        snapshot = evidence.aging_history.snapshots[0]
        self.assertEqual(snapshot.snapshot_date, "2026-01-01")
        self.assertEqual(snapshot.balance, 800.0)
        self.assertEqual(snapshot.credit_limit, 5000.0)

    def test_gaps_list_is_always_present_and_non_empty(self):
        service = make_service(summary=make_customer_summary())
        evidence = service.get_customer_collections(555000)
        gap_codes = {gap.code for gap in evidence.gaps}
        self.assertIn("collections_priority_ranking", gap_codes)
        self.assertIn("dunning_cadence_policy", gap_codes)
        self.assertIn("erp_disposition_write_back", gap_codes)


class ARCollectionsNoteTests(unittest.TestCase):
    def test_create_note_embeds_evidence_snapshot_and_round_trips(self):
        service = make_service(
            summary=make_customer_summary(),
            note_id_factory=lambda: "ar-collections-note-fixed",
        )
        record = service.create_note(
            555000,
            ARCollectionsNoteCreate(
                author_identity="J. Corbit",
                note="Confirmed payment plan for the past-due balance.",
            ),
        )
        self.assertEqual(record.note_id, "ar-collections-note-fixed")
        self.assertEqual(record.customer_name, "Main Street Tire")
        self.assertEqual(record.decision_effect, "none")
        self.assertFalse(record.erp_write)
        self.assertEqual(
            record.evidence_snapshot["customer"]["customer_number"], 555000
        )
        self.assertEqual(len(record.evidence_snapshot_sha256), 64)

        history = service.list_notes(555000)
        self.assertEqual(history.count, 1)
        self.assertEqual(history.notes[0].note_id, "ar-collections-note-fixed")

    def test_create_note_raises_for_unknown_customer(self):
        service = make_service(summary=None)
        with self.assertRaises(ARCollectionsCustomerNotFound):
            service.create_note(
                555000,
                ARCollectionsNoteCreate(
                    author_identity="J. Corbit", note="test"
                ),
            )


if __name__ == "__main__":
    unittest.main()
