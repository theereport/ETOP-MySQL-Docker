from __future__ import annotations

import unittest
from datetime import date

from modules.document_intelligence.integrations.receivables_repository import (
    ReceivablesRepository,
)


class ZeroBalanceOpenInvoicesTest(unittest.TestCase):
    def _row(self, invoice_number, changed_date):
        return {
            "customer_number": "640194",
            "invoice_number": invoice_number,
            "invoice_count": 1,
            "invoice_date": "20260101",
            "due_date": "20260201",
            "original_amount": "100.00",
            "open_amount": "0.00",
            "open_memo_amount": "0.00",
            "discountable_amount": "0.00",
            "cash_discount": "0.00",
            "debit_credit": "D",
            "transaction_type": "I",
            "selling_store": "41",
            "reference_number": "",
            "adjustment_reason": "",
            "changed_date": changed_date,
        }

    def test_queries_tmarop_for_zero_balance_rows_only(self) -> None:
        class FakeDatabase:
            def __init__(self, rows):
                self.calls = []
                self._rows = rows

            def fetch_all(self, query, parameters):
                self.calls.append((query, parameters))
                return self._rows

        database = FakeDatabase([self._row("12345678", "20260830")])
        repository = ReceivablesRepository(database)

        invoices = repository.get_zero_balance_open_invoices(
            "640194", date(2026, 9, 2),
        )

        self.assertEqual(len(invoices), 1)
        self.assertEqual(invoices[0].invoice_number, "12345678")
        self.assertEqual(invoices[0].open_amount, 0)
        query, parameters = database.calls[0]
        self.assertIn("TAROAMTOPN = 0", query)
        self.assertEqual(parameters, {"customer_number": "640194"})

    def test_excludes_rows_last_changed_before_the_cutoff(self) -> None:
        rows = [
            self._row("11111111", "20260830"),  # within 5 days
            self._row("22222222", "20260101"),  # long past
        ]

        class FakeDatabase:
            def fetch_all(self, query, parameters):
                return rows

        repository = ReceivablesRepository(FakeDatabase())

        invoices = repository.get_zero_balance_open_invoices(
            "640194", date(2026, 9, 2), days=5,
        )

        self.assertEqual(
            [invoice.invoice_number for invoice in invoices],
            ["11111111"],
        )


class RecentlyClosedInvoicesTest(unittest.TestCase):
    def _repository(self, tmarop_invoice_numbers, history_rows):
        class FakeDatabase:
            def fetch_all(self, query, parameters):
                if "TMIHSH" in query:
                    return history_rows
                return [
                    {"invoice_number": number}
                    for number in tmarop_invoice_numbers
                ]

        return ReceivablesRepository(FakeDatabase())

    def _history_row(self, invoice_number, changed_date, type_code="I"):
        return {
            "customer_number": "640194",
            "invoice_number": invoice_number,
            "invoice_count": 1,
            "invoice_date": "20260101",
            "due_date": "20260201",
            "original_amount": "50.00",
            "type_code": type_code,
            "changed_date": changed_date,
        }

    def test_excludes_invoices_still_present_on_tmarop(self) -> None:
        repository = self._repository(
            tmarop_invoice_numbers=["12345678"],
            history_rows=[
                self._history_row("12345678", "20260815"),
                self._history_row("87654321", "20260815"),
            ],
        )

        invoices = repository.get_recently_closed_invoices(
            "640194", date(2026, 9, 2),
        )

        self.assertEqual(
            [invoice.invoice_number for invoice in invoices],
            ["87654321"],
        )

    def test_excludes_rows_older_than_the_cutoff(self) -> None:
        repository = self._repository(
            tmarop_invoice_numbers=[],
            history_rows=[
                self._history_row("11111111", "20260815"),  # within 60 days
                self._history_row("22222222", "20260101"),  # older than 60 days
            ],
        )

        invoices = repository.get_recently_closed_invoices(
            "640194", date(2026, 9, 2), days=60,
        )

        self.assertEqual(
            [invoice.invoice_number for invoice in invoices],
            ["11111111"],
        )

    def test_type_code_c_maps_to_credit(self) -> None:
        repository = self._repository(
            tmarop_invoice_numbers=[],
            history_rows=[self._history_row("33333333", "20260815", type_code="C")],
        )

        invoices = repository.get_recently_closed_invoices(
            "640194", date(2026, 9, 2),
        )

        self.assertEqual(invoices[0].debit_credit, "C")
        self.assertEqual(invoices[0].aging_bucket, "Closed")
        self.assertEqual(invoices[0].open_amount, 0)


if __name__ == "__main__":
    unittest.main()
