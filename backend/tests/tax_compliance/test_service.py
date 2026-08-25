"""Service-level tests for Tax Compliance, using fake repositories.

These tests never touch MaddenCo or SQLite; they verify the deterministic
matching/comparison logic the service performs over repository-shaped dict
rows (the same style as backend/tests/vendor_intelligence/test_service.py).
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from modules.tax_compliance.schemas import TaxComplianceNoteCreate
from modules.tax_compliance.service import (
    CustomerNotFound,
    ExemptionCodeNotFound,
    TaxAuthorityNotFound,
    TaxComplianceService,
)


FIXED_NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


class FakeTaxComplianceRepository:
    def __init__(
        self,
        *,
        authorities=None,
        exemption_codes=None,
        customer_rows=None,
    ):
        self._authorities = authorities or []
        self._exemption_codes = exemption_codes or []
        self._customer_rows = {
            row["CUNUMBER"]: row for row in (customer_rows or [])
        }

    def search_tax_authorities(self, **kwargs):
        return self._authorities

    def get_tax_authority(self, tax_authority, state_code):
        for row in self._authorities:
            if (
                row["TTAXAUTH"] == tax_authority
                and row["TTAXCODSTE"] == state_code
            ):
                return row
        return None

    def search_exemption_codes(self, **kwargs):
        return self._exemption_codes

    def get_exemption_codes_by_code(self, exempt_code):
        return [
            row
            for row in self._exemption_codes
            if row["TTXECODEXE"] == exempt_code
        ]

    def get_customer_tax_fields(self, customer_number):
        return self._customer_rows.get(customer_number)

    def get_customers_tax_fields(self, customer_numbers):
        return [
            self._customer_rows[number]
            for number in customer_numbers
            if number in self._customer_rows
        ]


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
        import hashlib
        import json

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


def make_authority_row(**overrides):
    row = {
        "TTAXAUTH": 100,
        "TTAXCODSTE": 39,
        "TTAXSTEABR": "OH",
        "TTAXDSC": "Ohio State Tax",
        "TTAXTYPCD": "ST",
        "TTAXRATPCT": 0.0575,
        "TTAXAMTMAX": None,
        "TTAXFETYN": "N",
        "TTAXSLCTFG": "Y",
        "TTAXAUTNXT": 0,
        "TTAXSTENXT": 0,
        "TTAXCODDEL": "A",
        "TTAXDTECRT": "20200101",
        "TTAXDTECHG": "20250101",
        "TTAXUSRCRT": "JADMIN",
        "TTAXUSRCHG": "JADMIN",
    }
    row.update(overrides)
    return row


def make_exemption_row(**overrides):
    row = {
        "TTXECODEXE": "RS",
        "TTXECODSTE": 39,
        "TTXEDSC": "Resale",
        "TTXETYPCD": "ST",
        "TTXEOORP": "O",
        "TTXEPCTTAX": 0.0,
        "TTXERATPCT": 0.0,
        "TTXEMAXTAX": None,
        "TTXECODDEL": "A",
        "TTXEDTECRT": "20200101",
        "TTXEDTECHG": "20250101",
        "TTXEUSRCRT": "JADMIN",
        "TTXEUSRCHG": "JADMIN",
    }
    row.update(overrides)
    return row


def make_customer_row(**overrides):
    row = {
        "CUNUMBER": 555444,
        "CUNAME": "K&M Test Customer",
        "CUSTATE": 39,
        "CUTAXEXCD": "RS",
        "CUFETEXMPT": "N",
        "CUDTETXEXP": "20261231",
    }
    row.update(overrides)
    return row


class TaxAuthorityTests(unittest.TestCase):
    def test_search_maps_authority_fields(self):
        service = TaxComplianceService(
            repository=FakeTaxComplianceRepository(
                authorities=[make_authority_row()]
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        response = service.search_tax_authorities()
        self.assertEqual(response.count, 1)
        authority = response.authorities[0]
        self.assertEqual(authority.tax_authority, 100)
        self.assertEqual(authority.state_abbreviation, "OH")
        self.assertEqual(authority.rate_percent, 0.0575)
        self.assertTrue(authority.active)
        self.assertFalse(authority.fet_applicable)
        self.assertIsNone(authority.next_tax_authority)

    def test_get_tax_authority_raises_when_not_found(self):
        service = TaxComplianceService(
            repository=FakeTaxComplianceRepository(authorities=[]),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        with self.assertRaises(TaxAuthorityNotFound):
            service.get_tax_authority(999, 99)

    def test_inactive_authority_flag_from_delete_code(self):
        service = TaxComplianceService(
            repository=FakeTaxComplianceRepository(
                authorities=[make_authority_row(TTAXCODDEL="D")]
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        authority = service.get_tax_authority(100, 39)
        self.assertFalse(authority.active)


class TaxExemptionCodeTests(unittest.TestCase):
    def test_search_maps_exemption_fields(self):
        service = TaxComplianceService(
            repository=FakeTaxComplianceRepository(
                exemption_codes=[make_exemption_row()]
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        response = service.search_exemption_codes()
        self.assertEqual(response.count, 1)
        code = response.exemption_codes[0]
        self.assertEqual(code.exempt_code, "RS")
        self.assertEqual(code.override_or_percent_code, "O")
        self.assertTrue(code.active)

    def test_get_exemption_code_raises_when_not_found(self):
        service = TaxComplianceService(
            repository=FakeTaxComplianceRepository(exemption_codes=[]),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        with self.assertRaises(ExemptionCodeNotFound):
            service.get_exemption_code("ZZ")

    def test_get_exemption_code_returns_all_matching_states(self):
        service = TaxComplianceService(
            repository=FakeTaxComplianceRepository(
                exemption_codes=[
                    make_exemption_row(TTXECODSTE=39),
                    make_exemption_row(TTXECODSTE=42),
                ]
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        codes = service.get_exemption_code("RS")
        self.assertEqual(len(codes), 2)
        self.assertEqual({code.state_code for code in codes}, {39, 42})


class CustomerExemptionCheckTests(unittest.TestCase):
    def test_raises_when_customer_not_found(self):
        service = TaxComplianceService(
            repository=FakeTaxComplianceRepository(customer_rows=[]),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        with self.assertRaises(CustomerNotFound):
            service.check_customer_exemption(9999999)

    def test_matched_status_when_code_exists_in_tmtaxe(self):
        service = TaxComplianceService(
            repository=FakeTaxComplianceRepository(
                exemption_codes=[make_exemption_row(TTXECODEXE="RS")],
                customer_rows=[make_customer_row(CUTAXEXCD="RS")],
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        response = service.check_customer_exemption(555444)
        self.assertEqual(response.result.match_status, "matched")
        self.assertEqual(len(response.result.matched_exemption_codes), 1)
        self.assertGreater(len(response.gaps), 0)

    def test_no_matching_exemption_code_found_is_reported_explicitly(self):
        service = TaxComplianceService(
            repository=FakeTaxComplianceRepository(
                exemption_codes=[],
                customer_rows=[make_customer_row(CUTAXEXCD="ZZ")],
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        response = service.check_customer_exemption(555444)
        self.assertEqual(
            response.result.match_status, "no_matching_exemption_code_found"
        )
        self.assertEqual(response.result.matched_exemption_codes, [])

    def test_no_exemption_code_on_customer_when_blank(self):
        service = TaxComplianceService(
            repository=FakeTaxComplianceRepository(
                exemption_codes=[make_exemption_row()],
                customer_rows=[make_customer_row(CUTAXEXCD="")],
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        response = service.check_customer_exemption(555444)
        self.assertEqual(
            response.result.match_status, "no_exemption_code_on_customer"
        )
        # A blank code is never silently treated as "not exempt" without
        # saying so explicitly.
        self.assertEqual(response.result.exemption_code_on_file, "")

    def test_expiration_status_current_expired_and_missing(self):
        service = TaxComplianceService(
            repository=FakeTaxComplianceRepository(
                exemption_codes=[make_exemption_row()],
                customer_rows=[
                    make_customer_row(
                        CUNUMBER=1, CUDTETXEXP="20261231"
                    ),
                    make_customer_row(
                        CUNUMBER=2, CUDTETXEXP="20250101"
                    ),
                    make_customer_row(CUNUMBER=3, CUDTETXEXP=""),
                ],
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        current = service.check_customer_exemption(1)
        expired = service.check_customer_exemption(2)
        missing = service.check_customer_exemption(3)
        self.assertEqual(current.result.expiration_status, "current")
        self.assertEqual(expired.result.expiration_status, "expired")
        self.assertEqual(
            missing.result.expiration_status, "no_expiration_date_on_file"
        )

    def test_batch_check_reports_not_found_customers_separately(self):
        service = TaxComplianceService(
            repository=FakeTaxComplianceRepository(
                exemption_codes=[make_exemption_row()],
                customer_rows=[
                    make_customer_row(CUNUMBER=1),
                    make_customer_row(CUNUMBER=2, CUTAXEXCD=""),
                ],
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        response = service.check_customers_exemption([1, 2, 3])
        self.assertEqual(response.checked_count, 2)
        self.assertEqual(response.not_found_customer_numbers, [3])
        statuses = {r.customer_number: r.match_status for r in response.results}
        self.assertEqual(statuses[1], "matched")
        self.assertEqual(statuses[2], "no_exemption_code_on_customer")


class TaxComplianceNoteTests(unittest.TestCase):
    def test_create_note_embeds_evidence_snapshot_and_is_append_only_shaped(self):
        service = TaxComplianceService(
            repository=FakeTaxComplianceRepository(
                exemption_codes=[make_exemption_row()],
                customer_rows=[make_customer_row()],
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
            note_id_factory=lambda: "tax-compliance-note-fixed",
        )
        record = service.create_note(
            555444,
            TaxComplianceNoteCreate(
                author_identity="J. Corbit",
                note="Confirmed resale certificate on file with the branch.",
            ),
        )
        self.assertEqual(record.note_id, "tax-compliance-note-fixed")
        self.assertEqual(record.customer_name, "K&M Test Customer")
        self.assertEqual(record.decision_effect, "none")
        self.assertFalse(record.erp_write)
        self.assertEqual(
            record.evidence_snapshot["result"]["customer_number"], 555444
        )
        self.assertEqual(len(record.evidence_snapshot_sha256), 64)

        history = service.list_notes(555444)
        self.assertEqual(history.count, 1)
        self.assertEqual(history.notes[0].note_id, "tax-compliance-note-fixed")

    def test_create_note_raises_for_unknown_customer(self):
        service = TaxComplianceService(
            repository=FakeTaxComplianceRepository(customer_rows=[]),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        with self.assertRaises(CustomerNotFound):
            service.create_note(
                555444,
                TaxComplianceNoteCreate(author_identity="J. Corbit", note="test"),
            )


if __name__ == "__main__":
    unittest.main()
