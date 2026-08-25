"""Service-level tests for Sales Order Visibility, using fake repositories.

These tests never touch MaddenCo or SQLite; they verify the arithmetic and
mapping the service performs over repository-shaped dict rows.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from datetime import datetime, timezone

from modules.sales_order_visibility.schemas import OrderNoteCreate
from modules.sales_order_visibility.service import (
    InvoiceNotFound,
    SalesOrderVisibilityService,
)


FIXED_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


class FakeSalesOrderRepository:
    def __init__(
        self,
        header_row=None,
        line_rows=None,
        fit_rows=None,
        memo_rows=None,
        auth_rows=None,
        delivery_rows=None,
        sales_summary_rows=None,
    ):
        self._header_row = header_row
        self._line_rows = line_rows or []
        self._fit_rows = fit_rows or []
        self._memo_rows = memo_rows or []
        self._auth_rows = auth_rows or []
        self._delivery_rows = delivery_rows or []
        self._sales_summary_rows = sales_summary_rows or []

    def search_invoices(self, **kwargs):
        return [self._header_row] if self._header_row else []

    def get_invoice_header(self, invoice_number):
        if (
            self._header_row
            and int(self._header_row["TIHHNUMINV"]) == invoice_number
        ):
            return self._header_row
        return None

    def get_invoice_lines(self, invoice_number):
        return self._line_rows

    def get_invoice_line_fit_details(self, invoice_number):
        return self._fit_rows

    def get_invoice_memos(self, invoice_number):
        return self._memo_rows

    def get_invoice_authorizations(self, invoice_number):
        return self._auth_rows

    def get_delivery_status(self, invoice_number):
        return self._delivery_rows

    def get_sales_summary(self, **kwargs):
        return self._sales_summary_rows


class FakeNotesRepository:
    def __init__(self):
        self._notes: dict[str, dict] = {}

    def list_notes(self, invoice_number):
        return [
            note
            for note in self._notes.values()
            if note["invoice_number"] == invoice_number
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


def make_header_row(**overrides):
    row = {
        "TIHHNUMINV": 8801234,
        "TIHHNUMCST": 555001,
        "CUNAME": "Main Street Tire",
        "TIHHDTEINV": "20260110",
        "TIHHDTEDUE": "20260210",
        "TIHHDTECRT": "20260109",
        "TIHHDTECHG": "20260110",
        "TIHHCODTYP": "I",
        "TIHHVOIDYN": "N",
        "TIHHHLDRSN": "",
        "TIHHDIRSHP": "N",
        "TIHHPICKUP": "N",
        "TIHHCDRTE": "12",
        "TIHHNUMSTR": 3,
        "TIHHNUMPO": "PO-998",
        "TIHHNUMREF": "REF-1",
        "TIHHCODTRM": "030",
        "TIHHCODEXM": "",
        "TIHHCLSCST": "A",
        "TIHHCSTTYP": "RTL",
        "TIHHTOS": "REG",
        "TIHHSHPTO1": "100 Main St",
        "TIHHSHPTO2": "",
        "TIHHSHPTO3": "",
        "TIHHSHPTO5": "",
        "TIHHSHPTOZ": "44601",
        "TIHHTRKNUM": "1Z999",
        "TIHHTOTINV": 542.10,
        "TIHHTOTUNT": 4,
        "TIHHDISCST": 10.00,
        "TIHHNUMLIN": 2,
        "TIHHINVCNT": 1,
        "TIHHSLMSEL": 42,
        "TIHHSLMCST": 42,
        "TIHHSLMORG": 0,
        "TIHHSLMCLS": 0,
        "TIHHSTATUS": "C",
        "TIHHSTAT2": "",
    }
    row.update(overrides)
    return row


class InvoiceEvidenceTests(unittest.TestCase):
    def test_get_invoice_evidence_raises_when_invoice_not_found(self):
        service = SalesOrderVisibilityService(
            repository=FakeSalesOrderRepository(header_row=None),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        with self.assertRaises(InvoiceNotFound):
            service.get_invoice_evidence(9999999)

    def test_header_maps_from_tmihsh_and_customer_join(self):
        service = SalesOrderVisibilityService(
            repository=FakeSalesOrderRepository(header_row=make_header_row()),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_invoice_evidence(8801234)

        self.assertEqual(evidence.header.invoice_number, 8801234)
        self.assertEqual(evidence.header.customer_number, 555001)
        self.assertEqual(evidence.header.customer_name, "Main Street Tire")
        self.assertEqual(evidence.header.invoice_date, "2026-01-10")
        self.assertFalse(evidence.header.void)
        self.assertEqual(evidence.header.total_amount, 542.10)
        self.assertEqual(evidence.header.ship_to_lines, ["100 Main St"])

    def test_void_flag_from_voidyn(self):
        service = SalesOrderVisibilityService(
            repository=FakeSalesOrderRepository(
                header_row=make_header_row(TIHHVOIDYN="Y")
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_invoice_evidence(8801234)
        self.assertTrue(evidence.header.void)

    def test_line_items_extended_price_is_quantity_times_price(self):
        line_rows = [
            {
                "TIHLLINENO": 1, "TIHLCODTYP": "I", "TIHLCODDEL": "",
                "TIHLPRD": "TIRE-100", "TIHLPRDDSC": "Widget Radial",
                "TIHLVNDPRD": "V01", "TIHLBRAND": "WID", "TIHLCLSPRD": "PC",
                "TIHLQTY": 4, "TIHLQTYORD": 4, "TIHLQTYBO": 0,
                "TIHLPRC": 120.50, "TIHLCOSACT": 90.00, "TIHLCOSREP": 95.00,
                "TIHLFET": 2.50, "TIHLDOT": "ABC123", "TIHLDOTDTE": "20260101",
                "TIHLTIRPOS": "FL",
            },
            {
                "TIHLLINENO": 2, "TIHLCODTYP": "I", "TIHLCODDEL": "",
                "TIHLPRD": "SVC-01", "TIHLPRDDSC": "Mount and balance",
                "TIHLVNDPRD": "", "TIHLBRAND": "", "TIHLCLSPRD": "SV",
                "TIHLQTY": 4, "TIHLQTYORD": 4, "TIHLQTYBO": 0,
                "TIHLPRC": 12.00, "TIHLCOSACT": None, "TIHLCOSREP": None,
                "TIHLFET": None, "TIHLDOT": "", "TIHLDOTDTE": None,
                "TIHLTIRPOS": "",
            },
        ]
        fit_rows = [
            {
                "TIHILINENO": 1, "TIHICARMAK": "Honda", "TIHICARMOD": "Civic",
                "TIHICARYR": 2019, "TIHIMILAGE": 42000,
            },
        ]
        service = SalesOrderVisibilityService(
            repository=FakeSalesOrderRepository(
                header_row=make_header_row(),
                line_rows=line_rows,
                fit_rows=fit_rows,
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_invoice_evidence(8801234)

        self.assertEqual(evidence.lines.line_count, 2)
        self.assertEqual(evidence.lines.lines[0].extended_price, 482.00)
        self.assertEqual(evidence.lines.lines[0].vehicle_make, "Honda")
        self.assertEqual(evidence.lines.lines[0].vehicle_year, 2019)
        self.assertEqual(evidence.lines.lines[1].vehicle_make, "")
        self.assertEqual(evidence.lines.total_extended_price, 530.00)

    def test_delivery_evidence_no_records_found_when_no_manifest_rows(self):
        service = SalesOrderVisibilityService(
            repository=FakeSalesOrderRepository(
                header_row=make_header_row(), delivery_rows=[],
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_invoice_evidence(8801234)
        self.assertEqual(evidence.delivery.manifest_status, "no_records_found")
        self.assertIsNone(evidence.delivery.is_fully_delivered)

    def test_delivery_evidence_partial_and_full_delivery_states(self):
        partial_rows = [
            {
                "STORENUM": 3, "ROUTE": "12", "STATUS": "L", "LINENUM": 1,
                "SEQ": 1, "PRODNUM": "TIRE-100", "DESC_": "Widget Radial",
                "WEIGHT": 20.0, "QUANTITY": 4,
                "CRTSTAMP": datetime(2026, 1, 10, 8, 0, 0),
                "DLVSTAMP": datetime(2026, 1, 10, 14, 30, 0),
            },
            {
                "STORENUM": 3, "ROUTE": "12", "STATUS": "L", "LINENUM": 2,
                "SEQ": 2, "PRODNUM": "SVC-01", "DESC_": "Mount and balance",
                "WEIGHT": 0.0, "QUANTITY": 4,
                "CRTSTAMP": datetime(2026, 1, 10, 8, 0, 0),
                "DLVSTAMP": None,
            },
        ]
        service = SalesOrderVisibilityService(
            repository=FakeSalesOrderRepository(
                header_row=make_header_row(), delivery_rows=partial_rows,
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_invoice_evidence(8801234)
        self.assertEqual(evidence.delivery.manifest_status, "records_found")
        self.assertEqual(evidence.delivery.delivered_line_count, 1)
        self.assertEqual(evidence.delivery.undelivered_line_count, 1)
        self.assertFalse(evidence.delivery.is_fully_delivered)
        self.assertTrue(evidence.delivery.lines[0].delivered)
        self.assertFalse(evidence.delivery.lines[1].delivered)

        full_rows = [dict(partial_rows[0]), dict(partial_rows[0])]
        full_rows[1]["LINENUM"] = 2
        service_full = SalesOrderVisibilityService(
            repository=FakeSalesOrderRepository(
                header_row=make_header_row(), delivery_rows=full_rows,
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        full_evidence = service_full.get_invoice_evidence(8801234)
        self.assertTrue(full_evidence.delivery.is_fully_delivered)

    def test_memo_and_authorization_mapping(self):
        memo_rows = [
            {
                "TIHMLINENO": 1, "TIHMCODTYP": "I",
                "TIHMMSG": "Customer requested morning delivery.",
                "TIHMDTECRT": "20260109", "TIHMUSRCRT": "JCORBIT",
                "TIHMPRTINV": "Y",
            },
        ]
        auth_rows = [
            {
                "TIHACD": "C", "TIHACODTYP": "I", "TIHAAMTAU": 542.10,
                "TIHADATRQ": "20260109", "TIHADATAU": "20260109",
                "TIHATIMRQ": "0900", "TIHATIMAU": "0905",
                "TIHASLMRQ": 42, "TIHASLMAU": 7,
                "TIHAUSRRQ": "JCORBIT", "TIHAUSRAU": "MANAGER1",
                "TIHATXT": "Approved over credit limit.",
            },
        ]
        service = SalesOrderVisibilityService(
            repository=FakeSalesOrderRepository(
                header_row=make_header_row(),
                memo_rows=memo_rows,
                auth_rows=auth_rows,
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_invoice_evidence(8801234)

        self.assertEqual(evidence.memos.memo_count, 1)
        self.assertTrue(evidence.memos.memos[0].print_on_invoice)
        self.assertEqual(evidence.authorizations.authorization_count, 1)
        self.assertEqual(
            evidence.authorizations.authorizations[0].amount_authorized,
            542.10,
        )
        self.assertEqual(
            evidence.authorizations.authorizations[0].authorized_by,
            "MANAGER1",
        )

    def test_gaps_list_is_always_present_and_includes_open_order_queue(self):
        service = SalesOrderVisibilityService(
            repository=FakeSalesOrderRepository(header_row=make_header_row()),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_invoice_evidence(8801234)
        gap_codes = {gap.code for gap in evidence.gaps}
        self.assertIn("open_order_queue", gap_codes)
        self.assertIn("fulfillment_sla_definition", gap_codes)


class SalesSummaryTests(unittest.TestCase):
    def test_sales_summary_totals_sum_rows(self):
        rows = [
            {
                "customer_number": 555001, "product_number": "TIRE-100",
                "product_class": "PC", "product_type": "TIRE",
                "customer_class": "A", "customer_type": "RTL",
                "commission_code": "01", "vendor_number": "007",
                "store_number": 3, "year_period": 202601,
                "sales": 4820.00, "units": 40, "actual_cost": 3600.00,
                "replacement_cost": 3800.00, "fet": 100.00,
            },
            {
                "customer_number": 555001, "product_number": "SVC-01",
                "product_class": "SV", "product_type": "SERV",
                "customer_class": "A", "customer_type": "RTL",
                "commission_code": "01", "vendor_number": "",
                "store_number": 3, "year_period": 202601,
                "sales": 480.00, "units": 40, "actual_cost": None,
                "replacement_cost": None, "fet": None,
            },
        ]
        service = SalesOrderVisibilityService(
            repository=FakeSalesOrderRepository(sales_summary_rows=rows),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        summary = service.get_sales_summary(customer_number=555001)

        self.assertEqual(summary.row_count, 2)
        self.assertEqual(summary.total_sales, 5300.00)
        self.assertEqual(summary.total_units, 80.00)
        self.assertEqual(summary.total_actual_cost, 3600.00)


class OrderNoteTests(unittest.TestCase):
    def test_create_note_embeds_invoice_evidence_snapshot_and_is_append_only_shaped(
        self,
    ):
        service = SalesOrderVisibilityService(
            repository=FakeSalesOrderRepository(header_row=make_header_row()),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
            note_id_factory=lambda: "order-note-fixed",
        )
        record = service.create_note(
            8801234,
            OrderNoteCreate(
                author_identity="J. Corbit",
                note="Confirmed customer received tires on route 12.",
            ),
        )
        self.assertEqual(record.note_id, "order-note-fixed")
        self.assertEqual(record.customer_name, "Main Street Tire")
        self.assertEqual(record.decision_effect, "none")
        self.assertFalse(record.erp_write)
        self.assertEqual(
            record.evidence_snapshot["header"]["invoice_number"], 8801234
        )
        self.assertEqual(len(record.evidence_snapshot_sha256), 64)

        history = service.list_notes(8801234)
        self.assertEqual(history.count, 1)
        self.assertEqual(history.notes[0].note_id, "order-note-fixed")

    def test_create_note_raises_for_unknown_invoice(self):
        service = SalesOrderVisibilityService(
            repository=FakeSalesOrderRepository(header_row=None),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        with self.assertRaises(InvoiceNotFound):
            service.create_note(
                8801234,
                OrderNoteCreate(author_identity="J. Corbit", note="test"),
            )


if __name__ == "__main__":
    unittest.main()
