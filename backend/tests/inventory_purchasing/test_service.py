"""Service-level tests for Inventory & Purchasing, using fake repositories.

These tests never touch MaddenCo or SQLite; they verify the arithmetic and
mapping the service performs over repository-shaped dict rows.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from datetime import datetime, timezone

from modules.inventory_purchasing.schemas import InventoryNoteCreate
from modules.inventory_purchasing.service import (
    InventoryPurchasingService,
    ProductNotFound,
)


FIXED_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


class FakeInventoryPurchasingRepository:
    def __init__(
        self,
        product_row=None,
        month_end_rows=None,
        open_pos=None,
        receipts=None,
    ):
        self._product_row = product_row
        self._month_end_rows = month_end_rows or []
        self._open_pos = open_pos or []
        self._receipts = receipts or []

    def search_products(self, **kwargs):
        return [self._product_row] if self._product_row else []

    def get_product(self, product_number):
        if (
            self._product_row
            and _clean(self._product_row["PDNUMBER"]) == product_number
        ):
            return self._product_row
        return None

    def get_month_end_inventory(self, product_number, limit=24):
        return self._month_end_rows

    def get_open_purchase_orders_for_product(self, product_number, limit=50):
        return self._open_pos

    def get_receiving_history_for_product(self, product_number, limit=50):
        return self._receipts


def _clean(value):
    return str(value).strip()


class FakeNotesRepository:
    def __init__(self):
        self._notes: dict[str, dict] = {}

    def list_notes(self, product_number):
        return [
            note
            for note in self._notes.values()
            if note["product_number"] == product_number
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


def make_product_row(**overrides):
    row = {
        "PDNUMBER": "TIRE-100",
        "PDSEARCHKY": "TIRE100",
        "PDDESCRIP": "Widget Radial Tire 100",
        "PDCLASS": "10",
        "PDTYPE": "TR",
        "PDBRAND": "WGT",
        "PDSIZE": "225/50R17",
        "PDLOADINDX": "94",
        "PDSPEEDRAT": "V",
        "PDMFGPRDNO": "MFG-9988",
        "PDBARCODE": "012345678905",
        "PDUNITMEAS": "EA",
        "PDVENDOR": "123",
        "PDSTORE": 1,
        "PDWAREHSE": "A1",
        "PDWAREHALT": "",
        "PDDELETE": "A",
        "PDNONINV": "N",
        "PDALLOWPO": "Y",
        "PDDTECRT": "20200101",
        "PDRECVDATE": "20260105",
        "PDSOLDDATE": "20260110",
        "PDVENDCOST": 55.00,
        "PDACTCOST": 56.25,
        "PDREPLCOST": 57.00,
        "PDLYRCOST": 52.00,
        "PDPRICE1": 89.99,
        "PDPRICE2": 84.99,
        "PDPRICE3": 79.99,
        "PDPRICE4": 74.99,
        "PDPRICE5": 69.99,
        "PDPRICE6": 64.99,
        "PDINVENTRY": 42.0,
        "PDONORDER": 20.0,
        "PDALLOCATD": 5.0,
        "PDMIN": 10.0,
        "PDMAX": 60.0,
        "PDINVTURNS": 4.2,
        "PDLEADTIM": 7,
    }
    row.update(overrides)
    return row


class ProductEvidenceTests(unittest.TestCase):
    def test_get_product_evidence_raises_when_not_found(self):
        service = InventoryPurchasingService(
            repository=FakeInventoryPurchasingRepository(product_row=None),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        with self.assertRaises(ProductNotFound):
            service.get_product_evidence("MISSING-1")

    def test_identity_costing_and_inventory_position_map_from_tmprod(self):
        service = InventoryPurchasingService(
            repository=FakeInventoryPurchasingRepository(
                product_row=make_product_row()
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_product_evidence("TIRE-100")

        self.assertEqual(evidence.identity.product_number, "TIRE-100")
        self.assertEqual(evidence.identity.description, "Widget Radial Tire 100")
        self.assertTrue(evidence.identity.active)
        self.assertTrue(evidence.identity.allow_po_creation)
        self.assertEqual(evidence.identity.date_last_received, "2026-01-05")
        self.assertEqual(evidence.costing.vendor_cost, 55.00)
        self.assertEqual(evidence.costing.price_1, 89.99)
        self.assertEqual(evidence.inventory_position.on_hand, 42.0)
        self.assertEqual(evidence.inventory_position.configured_minimum, 10.0)
        self.assertEqual(evidence.inventory_position.ordering_lead_time_days, 7)

    def test_inactive_product_flag_from_delete_code(self):
        service = InventoryPurchasingService(
            repository=FakeInventoryPurchasingRepository(
                product_row=make_product_row(PDDELETE="D")
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_product_evidence("TIRE-100")
        self.assertFalse(evidence.identity.active)

    def test_month_end_inventory_latest_period_sums_across_stores(self):
        month_end_rows = [
            {
                "STORENUM": 1, "MONTH": 12, "YEAR": 2025,
                "VENDNUM": "123", "CLASSNUM": "10",
                "UNITS": 30, "TOTALCOST": 1500.00, "TOTALFET": 12.00,
            },
            {
                "STORENUM": 2, "MONTH": 12, "YEAR": 2025,
                "VENDNUM": "123", "CLASSNUM": "10",
                "UNITS": 10, "TOTALCOST": 500.00, "TOTALFET": 4.00,
            },
            {
                "STORENUM": 1, "MONTH": 11, "YEAR": 2025,
                "VENDNUM": "123", "CLASSNUM": "10",
                "UNITS": 25, "TOTALCOST": 1250.00, "TOTALFET": 10.00,
            },
        ]
        service = InventoryPurchasingService(
            repository=FakeInventoryPurchasingRepository(
                product_row=make_product_row(),
                month_end_rows=month_end_rows,
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_product_evidence("TIRE-100")
        self.assertEqual(evidence.month_end_inventory.period_count, 3)
        self.assertEqual(
            evidence.month_end_inventory.latest_period_total_units, 40.0
        )
        self.assertEqual(
            evidence.month_end_inventory.latest_period_total_cost, 2000.00
        )

    def test_month_end_inventory_empty_has_no_latest_totals(self):
        service = InventoryPurchasingService(
            repository=FakeInventoryPurchasingRepository(
                product_row=make_product_row(), month_end_rows=[],
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_product_evidence("TIRE-100")
        self.assertEqual(evidence.month_end_inventory.period_count, 0)
        self.assertIsNone(evidence.month_end_inventory.latest_period_total_units)
        self.assertIsNone(evidence.month_end_inventory.latest_period_total_cost)

    def test_open_purchase_order_totals_sum_line_aggregates(self):
        open_pos = [
            {
                "TPHNB": 7001, "TPHNBVND": 555000, "TPHDTE": "20260101",
                "TPHDTEREQ": "20260201", "TPHCDSTS": "O", "TPHFLGCMP": "N",
                "TPHVIA": "UPS", "TPHBUYNUM": 12,
                "total_ordered": 100, "total_received": 40,
                "total_backorder": 60, "average_unit_cost": 50.0,
                "line_total_cost": 5000.0,
            },
            {
                "TPHNB": 7002, "TPHNBVND": 555001, "TPHDTE": "20260105",
                "TPHDTEREQ": None, "TPHCDSTS": "O", "TPHFLGCMP": "N",
                "TPHVIA": "", "TPHBUYNUM": 0,
                "total_ordered": 20, "total_received": 20,
                "total_backorder": 0, "average_unit_cost": 48.0,
                "line_total_cost": 960.0,
            },
        ]
        service = InventoryPurchasingService(
            repository=FakeInventoryPurchasingRepository(
                product_row=make_product_row(), open_pos=open_pos,
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_product_evidence("TIRE-100")
        self.assertEqual(evidence.purchase_exposure.open_order_count, 2)
        self.assertEqual(
            evidence.purchase_exposure.open_order_total_cost, 5960.0
        )
        self.assertIsNone(evidence.purchase_exposure.open_orders[1].buyer_number)
        self.assertEqual(
            evidence.purchase_exposure.open_orders[0].vendor_number, 555000
        )

    def test_receiving_cost_variance_completeness_states(self):
        service_complete = InventoryPurchasingService(
            repository=FakeInventoryPurchasingRepository(
                product_row=make_product_row(),
                receipts=[
                    {
                        "TRCDNUMPO": 7001, "TPHNBVND": 555000,
                        "TRCDQTY": 10, "TRCDCOS": 50.0, "TRCDCOSPO": 48.0,
                        "TRCDCOSDIF": 2.0, "TRCDDOT": "ABC123",
                        "TRCDDOTDTE": "20260101", "TRCDDTECRT": "20260102",
                    },
                ],
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        complete_evidence = service_complete.get_product_evidence("TIRE-100")
        self.assertEqual(
            complete_evidence.receiving.cost_variance_completeness, "complete"
        )
        self.assertEqual(complete_evidence.receiving.total_cost_variance, 2.0)
        self.assertEqual(
            complete_evidence.receiving.recent_receipts[0].vendor_number,
            555000,
        )

        service_unavailable = InventoryPurchasingService(
            repository=FakeInventoryPurchasingRepository(
                product_row=make_product_row(), receipts=[],
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        empty_evidence = service_unavailable.get_product_evidence("TIRE-100")
        self.assertEqual(
            empty_evidence.receiving.cost_variance_completeness, "unavailable"
        )
        self.assertIsNone(empty_evidence.receiving.total_cost_variance)

    def test_gaps_list_is_always_present_and_non_empty(self):
        service = InventoryPurchasingService(
            repository=FakeInventoryPurchasingRepository(
                product_row=make_product_row()
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_product_evidence("TIRE-100")
        gap_codes = {gap.code for gap in evidence.gaps}
        self.assertIn("reorder_point_formula", gap_codes)
        self.assertIn("real_time_onhand_by_warehouse", gap_codes)
        self.assertIn("demand_forecast_turnover_rate", gap_codes)


class InventoryNoteTests(unittest.TestCase):
    def test_create_note_embeds_product_evidence_snapshot_and_is_append_only_shaped(
        self,
    ):
        service = InventoryPurchasingService(
            repository=FakeInventoryPurchasingRepository(
                product_row=make_product_row()
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
            note_id_factory=lambda: "inventory-note-fixed",
        )
        record = service.create_note(
            "TIRE-100",
            InventoryNoteCreate(
                author_identity="J. Buyer",
                note="Confirmed lead time improved to 5 days.",
            ),
        )
        self.assertEqual(record.note_id, "inventory-note-fixed")
        self.assertEqual(record.product_description, "Widget Radial Tire 100")
        self.assertEqual(record.decision_effect, "none")
        self.assertFalse(record.erp_write)
        self.assertEqual(
            record.evidence_snapshot["identity"]["product_number"], "TIRE-100"
        )
        self.assertEqual(len(record.evidence_snapshot_sha256), 64)

        history = service.list_notes("TIRE-100")
        self.assertEqual(history.count, 1)
        self.assertEqual(history.notes[0].note_id, "inventory-note-fixed")

    def test_create_note_raises_for_unknown_product(self):
        service = InventoryPurchasingService(
            repository=FakeInventoryPurchasingRepository(product_row=None),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        with self.assertRaises(ProductNotFound):
            service.create_note(
                "TIRE-100",
                InventoryNoteCreate(author_identity="J. Buyer", note="test"),
            )


if __name__ == "__main__":
    unittest.main()
