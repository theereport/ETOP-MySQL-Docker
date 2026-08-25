"""Service-level tests for General Ledger, using fake repositories.

These tests never touch MaddenCo or SQLite; they verify the arithmetic and
mapping the service performs over repository-shaped dict rows. The fixture
values for the reconciliation tests mirror amounts empirically observed in
the live MaddenCo database while building this module (account 1010,
division 1, department 0, year 2025, period 1: debit total 200534.55,
credit total 189454.32, net 11080.23, matching GMBL.GBAMT exactly).
"""

from __future__ import annotations

import hashlib
import json
import unittest
from datetime import datetime, timezone

from modules.general_ledger.schemas import GLNoteCreate
from modules.general_ledger.service import (
    AccountNotFound,
    GeneralLedgerService,
    TemplateNotFound,
)


FIXED_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


class FakeGeneralLedgerRepository:
    def __init__(
        self,
        account_row=None,
        balances=None,
        balance_for_period=None,
        transactions=None,
        posted_totals=None,
        unposted_lines=None,
        template_header=None,
        template_lines=None,
    ):
        self._account_row = account_row
        self._balances = balances or []
        self._balance_for_period = balance_for_period
        self._transactions = transactions or []
        self._posted_totals = posted_totals or []
        self._unposted_lines = unposted_lines or []
        self._template_header = template_header
        self._template_lines = template_lines or []

    def search_accounts(self, **kwargs):
        return [self._account_row] if self._account_row else []

    def get_account(self, account_number, division, department):
        row = self._account_row
        if (
            row
            and int(row["GMNB"]) == account_number
            and int(row["GMNBDIV"]) == division
            and int(row["GMNBDPT"]) == department
        ):
            return row
        return None

    def get_balances(self, account_number, division, department, **kwargs):
        return self._balances

    def get_balance_for_period(
        self, account_number, division, department, year, period
    ):
        return self._balance_for_period

    def get_posted_transactions(
        self, account_number, division, department, **kwargs
    ):
        return self._transactions

    def get_posted_totals(
        self, account_number, division, department, *, year, period
    ):
        return self._posted_totals

    def get_unposted_journal_entry_lines(
        self, account_number, division, department, **kwargs
    ):
        return self._unposted_lines

    def search_templates(self, **kwargs):
        return [self._template_header] if self._template_header else []

    def get_template(self, name):
        if self._template_header and self._template_header["GSJNAME"] == name:
            return self._template_header
        return None

    def get_template_lines(self, name):
        return self._template_lines


class FakeNotesRepository:
    def __init__(self):
        self._notes: dict[str, dict] = {}

    def list_notes(self, account_number):
        return [
            note
            for note in self._notes.values()
            if note["account_number"] == account_number
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


def make_account_row(**overrides):
    row = {
        "GMNB": 1010,
        "GMNBCO": 0,
        "GMNBDIV": 1,
        "GMNBDPT": 0,
        "GMDCRACT": "K&M TIRE - WELLS FARGO CASH",
        "GMDCRACTSH": "WF CASH",
        "GMCDDBCR": "DB",
        "GMTYPACT": "ASST",
        "GMYNACTIVE": "Y",
        "GMYNCST": "N",
        "GMYNEMP": "N",
        "GMYNJOB": "N",
        "GMYNPO": "N",
        "GMDTECRT": "00000000",
        "GMDTECHG": "20230113",
        "GMUSRCRT": "",
        "GMUSRCHG": "MINDYG",
    }
    row.update(overrides)
    return row


class AccountEvidenceTests(unittest.TestCase):
    def test_get_account_evidence_raises_when_account_not_found(self):
        service = GeneralLedgerService(
            repository=FakeGeneralLedgerRepository(account_row=None),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        with self.assertRaises(AccountNotFound):
            service.get_account_evidence(9999, 0, 0)

    def test_identity_maps_from_gmgm(self):
        service = GeneralLedgerService(
            repository=FakeGeneralLedgerRepository(
                account_row=make_account_row()
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_account_evidence(1010, 1, 0)

        self.assertEqual(evidence.identity.account_number, 1010)
        self.assertEqual(evidence.identity.division, 1)
        self.assertEqual(evidence.identity.description, "K&M TIRE - WELLS FARGO CASH")
        self.assertTrue(evidence.identity.active)
        self.assertEqual(evidence.identity.debit_or_credit, "DB")
        # GMDTECRT of all zeros means "not recorded", not the epoch.
        self.assertIsNone(evidence.identity.date_created)
        self.assertEqual(evidence.identity.date_changed, "2023-01-13")

    def test_inactive_account_flag_from_active_code(self):
        service = GeneralLedgerService(
            repository=FakeGeneralLedgerRepository(
                account_row=make_account_row(GMYNACTIVE="N")
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_account_evidence(1010, 1, 0)
        self.assertFalse(evidence.identity.active)

    def test_gaps_list_is_always_present_and_non_empty(self):
        service = GeneralLedgerService(
            repository=FakeGeneralLedgerRepository(
                account_row=make_account_row()
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_account_evidence(1010, 1, 0)
        gap_codes = {gap.code for gap in evidence.gaps}
        self.assertIn("reconciliation_tolerance_threshold", gap_codes)
        self.assertIn("close_period_lock_authority", gap_codes)
        self.assertIn("automatic_balance_verdict", gap_codes)
        self.assertIn("unposted_je_line_retention", gap_codes)


class AccountBalanceTests(unittest.TestCase):
    def test_balances_map_from_gmbl_rows(self):
        service = GeneralLedgerService(
            repository=FakeGeneralLedgerRepository(
                account_row=make_account_row(),
                balances=[
                    {"GBYR": 2025, "GBPR": 1, "GBAMT": 11080.23},
                    {"GBYR": 2025, "GBPR": 2, "GBAMT": 15057.05},
                ],
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_account_balances(
            1010, 1, 0, year_from=2025, period_from=1, year_to=2025, period_to=2
        )
        self.assertEqual(len(evidence.balances), 2)
        self.assertEqual(evidence.balances[0].net_balance, 11080.23)

    def test_balances_raises_when_account_not_found(self):
        service = GeneralLedgerService(
            repository=FakeGeneralLedgerRepository(account_row=None),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        with self.assertRaises(AccountNotFound):
            service.get_account_balances(
                9999, 0, 0, year_from=2025, period_from=1, year_to=2025, period_to=13
            )


class TransactionEvidenceTests(unittest.TestCase):
    def test_reconciliation_matches_when_posted_detail_equals_period_balance(self):
        # Mirrors the live-database check performed for account 1010/1/0,
        # year 2025, period 1: DB total 200534.55, CR total 189454.32,
        # net 11080.23 — which matched GMBL.GBAMT exactly.
        service = GeneralLedgerService(
            repository=FakeGeneralLedgerRepository(
                account_row=make_account_row(),
                transactions=[],
                posted_totals=[
                    {"GACDDBCR": "DB", "TOTAL_AMT": 200534.55, "LINE_COUNT": 33},
                    {"GACDDBCR": "CR", "TOTAL_AMT": 189454.32, "LINE_COUNT": 5},
                ],
                balance_for_period={"GBAMT": 11080.23},
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_account_transactions(
            1010, 1, 0, year=2025, period=1
        )
        recon = evidence.reconciliation
        self.assertEqual(recon.posted_debit_total, 200534.55)
        self.assertEqual(recon.posted_credit_total, 189454.32)
        self.assertEqual(recon.posted_net_total, 11080.23)
        self.assertEqual(recon.period_balance, 11080.23)
        self.assertEqual(recon.difference, 0.0)

    def test_reconciliation_reports_nonzero_difference_without_a_verdict(self):
        service = GeneralLedgerService(
            repository=FakeGeneralLedgerRepository(
                account_row=make_account_row(),
                transactions=[],
                posted_totals=[
                    {"GACDDBCR": "DB", "TOTAL_AMT": 500.00, "LINE_COUNT": 1},
                ],
                balance_for_period={"GBAMT": 450.00},
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_account_transactions(
            1010, 1, 0, year=2025, period=1
        )
        recon = evidence.reconciliation
        self.assertEqual(recon.posted_net_total, 500.00)
        self.assertEqual(recon.difference, 50.00)
        # No pass/fail verdict field exists on the schema at all.
        self.assertNotIn("in_balance", recon.model_dump())

    def test_reconciliation_period_balance_none_when_gmbl_has_no_row(self):
        service = GeneralLedgerService(
            repository=FakeGeneralLedgerRepository(
                account_row=make_account_row(),
                posted_totals=[
                    {"GACDDBCR": "DB", "TOTAL_AMT": 100.0, "LINE_COUNT": 1},
                ],
                balance_for_period=None,
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_account_transactions(
            1010, 1, 0, year=2025, period=1
        )
        self.assertIsNone(evidence.reconciliation.period_balance)
        self.assertIsNone(evidence.reconciliation.difference)

    def test_transaction_maps_matched_journal_entry_when_join_finds_a_header(self):
        service = GeneralLedgerService(
            repository=FakeGeneralLedgerRepository(
                account_row=make_account_row(),
                transactions=[
                    {
                        "GASEQ": 20137200, "GAYR": 2025, "GAPR": 8,
                        "GAAMT": 3725.36, "GACDDBCR": "DB",
                        "GADSR": "05.01.25 WELLS FARGO CASH",
                        "GACDSYS": "JE", "GADTCRT": "20250501",
                        "GADTPST": "20250501", "GAJEDTECRT": "00000000",
                        "GAJETIMCRT": "", "GAJEUSRCRT": "CARLAE",
                        "GAJEWSCRT": "WL01E3055A", "GANBCST": 0,
                        "GANBEMP": 0, "GANBJOB": 0, "GANBPO": 0,
                        "GANBREF": 9091585, "GANBREFRC": 0, "GAMEMOID": 0,
                        "JE_REF": 9091585, "JE_PR": 8, "JE_YR": 2025,
                        "JE_CO": 0, "JE_TOTAL_DB": 1567603.47,
                        "JE_TOTAL_CR": 1567603.47, "JE_FLAG": "U",
                    },
                    {
                        "GASEQ": 20181030, "GAYR": 2025, "GAPR": 8,
                        "GAAMT": -292.00, "GACDDBCR": "DB",
                        "GADSR": "GOODYEAR TIRE & RUBBER CO",
                        "GACDSYS": "AP", "GADTCRT": "20250509",
                        "GADTPST": "20250509", "GAJEDTECRT": "20250510",
                        "GAJETIMCRT": "00:36:57", "GAJEUSRCRT": "U273UPDATE",
                        "GAJEWSCRT": "PPInvUpd", "GANBCST": 0, "GANBEMP": 0,
                        "GANBJOB": 0, "GANBPO": 0, "GANBREF": 196130,
                        "GANBREFRC": 0, "GAMEMOID": 0,
                        "JE_REF": None, "JE_PR": None, "JE_YR": None,
                        "JE_CO": None, "JE_TOTAL_DB": None,
                        "JE_TOTAL_CR": None, "JE_FLAG": None,
                    },
                ],
                posted_totals=[
                    {"GACDDBCR": "DB", "TOTAL_AMT": 3433.36, "LINE_COUNT": 2},
                ],
                balance_for_period={"GBAMT": 3433.36},
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_account_transactions(
            1010, 1, 0, year=2025, period=8
        )
        self.assertEqual(evidence.count, 2)
        je_matched, ap_unmatched = evidence.transactions
        self.assertIsNotNone(je_matched.matched_journal_entry)
        self.assertEqual(
            je_matched.matched_journal_entry.total_debit, 1567603.47
        )
        self.assertIsNone(ap_unmatched.matched_journal_entry)

    def test_unposted_journal_entry_lines_are_labeled_not_historical(self):
        service = GeneralLedgerService(
            repository=FakeGeneralLedgerRepository(
                account_row=make_account_row(),
                posted_totals=[],
                unposted_lines=[
                    {
                        "GJHNBREF": 9100088, "GJDNBSEQ": 1, "GMNB": 1010,
                        "GMNBDIV": 1, "GMNBDPT": 0, "GJDAMTDB": 500.0,
                        "GJDAMTCR": 0.0, "GJDDSC": "in progress",
                        "GJDNBCST": 0, "GJDNBEMP": 0, "GJDNBJOB": 0,
                        "GJDNBPO": 0,
                    },
                ],
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        evidence = service.get_account_transactions(
            1010, 1, 0, year=2025, period=8
        )
        self.assertEqual(len(evidence.unposted_journal_entry_lines), 1)
        self.assertIn("not a historical", evidence.unposted_explanation)

    def test_transactions_raises_for_unknown_account(self):
        service = GeneralLedgerService(
            repository=FakeGeneralLedgerRepository(account_row=None),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        with self.assertRaises(AccountNotFound):
            service.get_account_transactions(9999, 0, 0, year=2025, period=1)


class TemplateTests(unittest.TestCase):
    def test_template_detail_sums_line_totals(self):
        service = GeneralLedgerService(
            repository=FakeGeneralLedgerRepository(
                template_header={
                    "GSJNAME": "BECR R",
                    "GSJHDSC": "K&M RENT",
                    "GSJHDSCJE": "BECR - RENT FROM K&M",
                    "GSJHCDSTAT": "",
                    "GSJHNBSEQN": 2,
                    "GSJHUSRCRT": "MIRANDAB",
                    "GSJHUSRLST": "MIRANDAB",
                },
                template_lines=[
                    {
                        "GSJDNBSEQ": 1, "GMNB": 1010, "GMNBDIV": 98,
                        "GMNBDPT": 0, "GSJDAMTDB": 77000.00,
                        "GSJDAMTCR": 0.00, "GSJDDSCJE": "",
                        "GSJDNBCST": 0, "GSJDNBEMP": 0, "GSJDNBJOB": 0,
                        "GSJDNBPO": 0,
                    },
                    {
                        "GSJDNBSEQ": 2, "GMNB": 3920, "GMNBDIV": 98,
                        "GMNBDPT": 55, "GSJDAMTDB": 0.00,
                        "GSJDAMTCR": 77000.00, "GSJDDSCJE": "",
                        "GSJDNBCST": 0, "GSJDNBEMP": 0, "GSJDNBJOB": 0,
                        "GSJDNBPO": 0,
                    },
                ],
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        detail = service.get_template_detail("BECR R")
        self.assertEqual(len(detail.lines), 2)
        self.assertEqual(detail.line_debit_total, 77000.00)
        self.assertEqual(detail.line_credit_total, 77000.00)

    def test_template_not_found_raises(self):
        service = GeneralLedgerService(
            repository=FakeGeneralLedgerRepository(template_header=None),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        with self.assertRaises(TemplateNotFound):
            service.get_template_detail("UNKNOWN")


class GLNoteTests(unittest.TestCase):
    def test_create_note_embeds_identity_snapshot_and_is_append_only_shaped(self):
        service = GeneralLedgerService(
            repository=FakeGeneralLedgerRepository(
                account_row=make_account_row(),
                posted_totals=[
                    {"GACDDBCR": "DB", "TOTAL_AMT": 100.0, "LINE_COUNT": 1},
                ],
                balance_for_period={"GBAMT": 100.0},
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
            note_id_factory=lambda: "gl-note-fixed",
        )
        record = service.create_note(
            1010,
            GLNoteCreate(
                author_identity="J. Controller",
                note="Confirmed May cash activity ties to bank statement.",
                division=1,
                department=0,
                period=1,
                year=2025,
            ),
        )
        self.assertEqual(record.note_id, "gl-note-fixed")
        self.assertEqual(record.account_number, 1010)
        self.assertEqual(record.decision_effect, "none")
        self.assertFalse(record.erp_write)
        self.assertEqual(
            record.evidence_snapshot["identity"]["account_number"], 1010
        )
        self.assertIn("reconciliation", record.evidence_snapshot)
        self.assertEqual(len(record.evidence_snapshot_sha256), 64)

        history = service.list_notes(1010)
        self.assertEqual(history.count, 1)
        self.assertEqual(history.notes[0].note_id, "gl-note-fixed")

    def test_create_note_without_period_omits_reconciliation_snapshot(self):
        service = GeneralLedgerService(
            repository=FakeGeneralLedgerRepository(
                account_row=make_account_row()
            ),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        record = service.create_note(
            1010,
            GLNoteCreate(
                author_identity="J. Controller",
                note="General note.",
                division=1,
                department=0,
            ),
        )
        self.assertNotIn("reconciliation", record.evidence_snapshot)

    def test_create_note_raises_for_unknown_account(self):
        service = GeneralLedgerService(
            repository=FakeGeneralLedgerRepository(account_row=None),
            notes_repository=FakeNotesRepository(),
            clock=lambda: FIXED_NOW,
        )
        with self.assertRaises(AccountNotFound):
            service.create_note(
                9999,
                GLNoteCreate(author_identity="J. Controller", note="test"),
            )


if __name__ == "__main__":
    unittest.main()
