"""Service-level tests for Freight & Logistics, using fake repositories.

These tests never touch MaddenCo or SQLite; they verify the arithmetic and
mapping the service performs over repository-shaped dict rows.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from datetime import datetime, timezone

from modules.freight_logistics.schemas import RouteNoteCreate
from modules.freight_logistics.service import (
    FreightLogisticsService,
    RouteNotFound,
)


FIXED_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


class FakeRouteRepository:
    def __init__(
        self,
        route_row=None,
        directions=None,
        load_lines=None,
        payments=None,
        payment_corrections=None,
        payment_details=None,
        exceptions=None,
        adjustments=None,
        signature_sessions=None,
        images=None,
    ):
        self._route_row = route_row
        self._directions = directions or []
        self._load_lines = load_lines or []
        self._payments = payments or []
        self._payment_corrections = payment_corrections or []
        self._payment_details = payment_details or []
        self._exceptions = exceptions or []
        self._adjustments = adjustments or []
        self._signature_sessions = signature_sessions or []
        self._images = images or []

    def search_routes(self, **kwargs):
        return [self._route_row] if self._route_row else []

    def get_route(self, route_code):
        if self._route_row and self._route_row["RTECODE"] == route_code:
            return self._route_row
        return None

    def get_warehouse_directions(self, warehouse_number, route_code, limit=25):
        return self._directions

    def get_load_lines(self, route_code, limit=1000):
        return self._load_lines

    def get_cod_payments(self, route_code, limit=100):
        return self._payments

    def get_payment_corrections(self, route_code, limit=200):
        return self._payment_corrections

    def get_payment_details(self, route_code, limit=200):
        return self._payment_details

    def get_delivery_exceptions(self, route_code, limit=100):
        return self._exceptions

    def get_delivery_adjustments(self, route_code, limit=100):
        return self._adjustments

    def get_signature_sessions(self, route_code, limit=50):
        return self._signature_sessions

    def get_signature_images(self, route_code, limit=100):
        return self._images


class FakeNotesRepository:
    def __init__(self):
        self._notes: dict[str, dict] = {}

    def list_notes(self, route_code):
        return [
            note
            for note in self._notes.values()
            if note["route_code"] == route_code
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


def make_route_row(**overrides):
    row = {
        "RTEKEY": "00100120",
        "RTECODE": "12",
        "DLVSUN": "N",
        "DLVMON": "Y",
        "DLVTUE": "Y",
        "DLVWED": "N",
        "DLVTHU": "Y",
        "DLVFRI": "Y",
        "DLVSAT": "N",
        "NUMSUN": 0,
        "NUMMON": 8,
        "NUMTUE": 6,
        "NUMWED": 0,
        "NUMTHU": 7,
        "NUMFRI": 9,
        "NUMSAT": 0,
        "CRTDATE": datetime(2020, 1, 1, 8, 0, 0),
        "CRTUSER": "JSMITH",
        "CHGDATE": datetime(2025, 6, 1, 9, 30, 0),
        "CHGUSER": "MJONES",
        "RTEWHSE": 100,
        "RTESTATUS": "A",
        "LOCATION_NAME": "Canton DC",
    }
    row.update(overrides)
    return row


class RouteEvidenceTests(unittest.TestCase):
    def test_get_route_evidence_raises_when_route_not_found(self):
        service = FreightLogisticsService(
            repository=FakeRouteRepository(route_row=None),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        with self.assertRaises(RouteNotFound):
            service.get_route_evidence("99")

    def test_identity_and_schedule_map_from_kmroutes(self):
        service = FreightLogisticsService(
            repository=FakeRouteRepository(route_row=make_route_row()),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_route_evidence("12")

        self.assertEqual(evidence.identity.route_code, "12")
        self.assertEqual(evidence.identity.route_key, "00100120")
        self.assertEqual(evidence.identity.warehouse_number, 100)
        self.assertTrue(evidence.identity.active)
        self.assertEqual(evidence.identity.created_by, "JSMITH")

        monday = next(
            day for day in evidence.identity.schedule if day.day == "Monday"
        )
        self.assertTrue(monday.scheduled)
        self.assertEqual(monday.scheduled_stop_count, 8)

        sunday = next(
            day for day in evidence.identity.schedule if day.day == "Sunday"
        )
        self.assertFalse(sunday.scheduled)
        self.assertEqual(sunday.scheduled_stop_count, 0)

        self.assertEqual(evidence.warehouse_label.warehouse_location_name, "Canton DC")

    def test_inactive_route_flag_from_status_code(self):
        service = FreightLogisticsService(
            repository=FakeRouteRepository(
                route_row=make_route_row(RTESTATUS="D")
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_route_evidence("12")
        self.assertFalse(evidence.identity.active)

    def test_load_evidence_counts_delivered_and_computes_elapsed_minutes(self):
        load_lines = [
            {
                "STORENUM": 5, "ROUTE": "12", "STATUS": "C", "INVNUM": 900001,
                "CUSTNUM": 123456, "LINENUM": 1, "SEQ": 1, "PRODNUM": "TIRE-A",
                "DESC": "Widget Tire A", "WEIGHT": 20.5, "QUANTITY": 4,
                "CRTSTAMP": datetime(2026, 1, 10, 6, 0, 0),
                "DLVSTAMP": datetime(2026, 1, 10, 8, 30, 0),
            },
            {
                "STORENUM": 5, "ROUTE": "12", "STATUS": "O", "INVNUM": 900002,
                "CUSTNUM": 123457, "LINENUM": 1, "SEQ": 2, "PRODNUM": "TIRE-B",
                "DESC": "Widget Tire B", "WEIGHT": 15.0, "QUANTITY": 2,
                "CRTSTAMP": datetime(2026, 1, 10, 6, 5, 0),
                "DLVSTAMP": None,
            },
        ]
        service = FreightLogisticsService(
            repository=FakeRouteRepository(
                route_row=make_route_row(), load_lines=load_lines,
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_route_evidence("12")

        self.assertEqual(evidence.load.line_count, 2)
        self.assertEqual(evidence.load.delivered_count, 1)
        self.assertEqual(evidence.load.undelivered_count, 1)
        self.assertEqual(evidence.load.total_weight, 35.5)
        self.assertEqual(evidence.load.total_quantity, 6.0)
        self.assertEqual(evidence.load.average_elapsed_minutes, 150.0)

        delivered_line = evidence.load.lines[0]
        self.assertTrue(delivered_line.delivered)
        self.assertEqual(delivered_line.elapsed_minutes, 150.0)

        undelivered_line = evidence.load.lines[1]
        self.assertFalse(undelivered_line.delivered)
        self.assertIsNone(undelivered_line.elapsed_minutes)
        self.assertIsNone(undelivered_line.delivered_at)

    def test_load_evidence_average_elapsed_is_none_with_no_delivered_lines(self):
        service = FreightLogisticsService(
            repository=FakeRouteRepository(route_row=make_route_row(), load_lines=[]),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_route_evidence("12")
        self.assertEqual(evidence.load.line_count, 0)
        self.assertIsNone(evidence.load.average_elapsed_minutes)

    def test_payment_evidence_joins_corrections_and_details_by_payment_id(self):
        payments = [
            {
                "ID": 5001, "CUSTNUM": 123456, "ROUTE": "12", "TYPE": "CHECK",
                "CHECKNUM": "1002", "AUTHNUM": "", "AMOUNT": 250.00,
                "NOTES": "Collected at dock", "INVOICES": "900001",
                "RECEIVED": "Y", "RECSTAMP": datetime(2026, 1, 10, 9, 0, 0),
                "CRTSTAMP": datetime(2026, 1, 10, 8, 45, 0),
            },
            {
                "ID": 5002, "CUSTNUM": 123457, "ROUTE": "12", "TYPE": "CASH",
                "CHECKNUM": "", "AUTHNUM": "", "AMOUNT": 75.00,
                "NOTES": "", "INVOICES": "900002",
                "RECEIVED": "N", "RECSTAMP": None,
                "CRTSTAMP": datetime(2026, 1, 10, 9, 15, 0),
            },
        ]
        corrections = [
            {
                "PAYMENT_ID": 5001, "FIELD": "AMOUNT", "BEFORE_VALUE": "200.00",
                "AFTER_VALUE": "250.00", "REASON": "Driver miskeyed amount",
                "CRTUSER": "MJONES", "CRTSTAMP": datetime(2026, 1, 10, 9, 5, 0),
            },
        ]
        details = [
            {
                "PAYMENT_ID": 5001, "NOTES": "Confirmed with customer",
                "CRTSTAMP": datetime(2026, 1, 10, 9, 10, 0), "CRTUSER": "MJONES",
            },
        ]
        service = FreightLogisticsService(
            repository=FakeRouteRepository(
                route_row=make_route_row(),
                payments=payments,
                payment_corrections=corrections,
                payment_details=details,
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_route_evidence("12")

        self.assertEqual(evidence.payments.payment_count, 2)
        self.assertEqual(evidence.payments.total_amount, 325.00)
        self.assertEqual(evidence.payments.received_count, 1)
        self.assertEqual(evidence.payments.unreceived_count, 1)

        first_payment = next(
            p for p in evidence.payments.payments if p.payment_id == 5001
        )
        self.assertEqual(len(first_payment.corrections), 1)
        self.assertEqual(first_payment.corrections[0].reason, "Driver miskeyed amount")
        self.assertEqual(len(first_payment.detail_notes), 1)

        second_payment = next(
            p for p in evidence.payments.payments if p.payment_id == 5002
        )
        self.assertEqual(second_payment.corrections, [])
        self.assertEqual(second_payment.detail_notes, [])
        self.assertFalse(second_payment.received)

    def test_exception_evidence_counts_approved_from_maddenco_flag(self):
        exceptions = [
            {
                "CUSTNUM": 123456, "ROUTE": "12", "INVNUM": 900001, "LINENUM": 1,
                "QUANTITY": 1, "OPTION_CODE": "R", "NOTES": "Damaged in transit",
                "APPROVED": "Y", "CREDITINV": 900050, "APPNOTES": "Approved for credit",
                "APPROVBY": "MJONES", "CRTSTAMP": datetime(2026, 1, 10, 8, 40, 0),
                "APPRSTAMP": datetime(2026, 1, 10, 10, 0, 0),
            },
            {
                "CUSTNUM": 123457, "ROUTE": "12", "INVNUM": 900002, "LINENUM": 1,
                "QUANTITY": 2, "OPTION_CODE": "S", "NOTES": "Customer short-shipped",
                "APPROVED": "N", "CREDITINV": None, "APPNOTES": "",
                "APPROVBY": "", "CRTSTAMP": datetime(2026, 1, 10, 9, 20, 0),
                "APPRSTAMP": None,
            },
        ]
        service = FreightLogisticsService(
            repository=FakeRouteRepository(
                route_row=make_route_row(), exceptions=exceptions,
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_route_evidence("12")
        self.assertEqual(evidence.exceptions.exception_count, 2)
        self.assertEqual(evidence.exceptions.approved_count, 1)
        self.assertEqual(evidence.exceptions.unapproved_count, 1)
        approved = next(e for e in evidence.exceptions.exceptions if e.approved)
        self.assertEqual(approved.credit_invoice_number, 900050)

    def test_warehouse_directions_are_included_when_present(self):
        directions = [
            {
                "DIRECTION_NAME": "North Loop", "MINIMUM_WEIGHT": 0,
                "MAXIMUM_WEIGHT": 5000, "QUANTITY_LIMIT": 200,
                "LIMIT_BY": "W", "ACTIVE": "Y",
            },
        ]
        service = FreightLogisticsService(
            repository=FakeRouteRepository(
                route_row=make_route_row(), directions=directions,
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_route_evidence("12")
        self.assertEqual(len(evidence.warehouse_label.directions), 1)
        self.assertEqual(
            evidence.warehouse_label.directions[0].direction_name, "North Loop"
        )

    def test_gaps_list_is_always_present_and_non_empty(self):
        service = FreightLogisticsService(
            repository=FakeRouteRepository(route_row=make_route_row()),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_route_evidence("12")
        gap_codes = {gap.code for gap in evidence.gaps}
        self.assertIn("route_profitability_formula", gap_codes)
        self.assertIn("on_time_delivery_definition", gap_codes)
        self.assertIn("cod_reconciliation_authority", gap_codes)


class RouteNoteTests(unittest.TestCase):
    def test_create_note_embeds_route_evidence_snapshot_and_is_append_only_shaped(self):
        service = FreightLogisticsService(
            repository=FakeRouteRepository(route_row=make_route_row()),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
            note_id_factory=lambda: "route-note-fixed",
        )
        record = service.create_note(
            "12",
            RouteNoteCreate(
                author_identity="J. Dispatcher",
                note="Confirmed driver ran the north loop early today.",
            ),
        )
        self.assertEqual(record.note_id, "route-note-fixed")
        self.assertEqual(record.route_code, "12")
        self.assertEqual(record.warehouse_number, 100)
        self.assertEqual(record.decision_effect, "none")
        self.assertFalse(record.erp_write)
        self.assertEqual(
            record.evidence_snapshot["identity"]["route_code"], "12"
        )
        self.assertEqual(len(record.evidence_snapshot_sha256), 64)

        history = service.list_notes("12")
        self.assertEqual(history.count, 1)
        self.assertEqual(history.notes[0].note_id, "route-note-fixed")

    def test_create_note_raises_for_unknown_route(self):
        service = FreightLogisticsService(
            repository=FakeRouteRepository(route_row=None),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        with self.assertRaises(RouteNotFound):
            service.create_note(
                "12",
                RouteNoteCreate(author_identity="J. Dispatcher", note="test"),
            )


if __name__ == "__main__":
    unittest.main()
