from __future__ import annotations

import unittest
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


BACKEND_ROOT = Path(__file__).resolve().parent
customer_360_package = types.ModuleType("modules.customer_360")
customer_360_package.__path__ = [
    str(BACKEND_ROOT / "modules" / "customer_360")
]
sys.modules.setdefault("modules.customer_360", customer_360_package)

if "core.database" not in sys.modules:
    core_database = types.ModuleType("core.database")
    core_database.madden_database = SimpleNamespace(
        fetch_all=lambda *_args, **_kwargs: [],
        fetch_one=lambda *_args, **_kwargs: None,
    )
    sys.modules["core.database"] = core_database

from modules.customer_360 import repository as repository_module
from modules.customer_360.repository import CustomerRepository
from modules.customer_360.service import CustomerService


class CustomerOpenInvoiceSearchTest(unittest.TestCase):
    def test_governed_open_invoice_is_searched_read_only(self) -> None:
        captured: dict[str, object] = {}

        def fetch_all(sql, parameters):
            captured["sql"] = sql
            captured["parameters"] = list(parameters)
            return []

        with patch.object(
            repository_module.madden_database,
            "fetch_all",
            fetch_all,
        ):
            CustomerRepository().search_customers(
                search="812-345-678",
                active_only=False,
            )

        sql = str(captured["sql"])
        parameters = list(captured["parameters"])
        self.assertIn("FROM TMAROP AS OPEN_AR", sql)
        self.assertIn("OPEN_AR.TAROAMTOPN <> 0", sql)
        self.assertNotIn("CUCITY", sql.upper())
        self.assertEqual(sql.count("%s"), len(parameters))
        self.assertEqual(parameters.count("812345678"), 4)
        self.assertNotIn("UPDATE ", sql.upper())
        self.assertNotIn("INSERT ", sql.upper())
        self.assertNotIn("DELETE ", sql.upper())

    def test_non_invoice_search_cannot_become_invoice_lookup(self) -> None:
        captured: dict[str, object] = {}

        def fetch_all(sql, parameters):
            captured["sql"] = sql
            captured["parameters"] = list(parameters)
            return []

        with patch.object(
            repository_module.madden_database,
            "fetch_all",
            fetch_all,
        ):
            CustomerRepository().search_customers(
                search="Sample Customer",
                active_only=False,
            )

        self.assertEqual(
            list(captured["parameters"]).count(""),
            4,
        )

    def test_customer_search_returns_address_context(self) -> None:
        row = {
            "CUNUMBER": 654321,
            "CUNAME": "SYNTHETIC CUSTOMER",
            "CUADDRESS4": "",
            "CUROUTECD": "",
            "CUSTORENUM": 1,
            "CUSALESMAN": 2,
            "CUTYPE": "",
            "CUCLASS": "",
            "CUDELETECD": "",
            "CUPHONE": "5550102468",
            "CUEMAIL": "",
            "CUADDRESS1": "400 TEST AVE",
            "CUADDRESS2": "SAMPLE CITY NY 10001",
            "CUSTATE": "NY",
            "CUZIP": "10001",
            "CUCRLIMIT": 1000,
            "CUBALANCE": 100,
            "CUONORDER": 0,
            "CUONORDAR": 0,
            "CURVCPM30": 0,
            "CURVCPM60": 0,
            "CURVCPM90": 0,
            "CURVCPM120": 0,
        }
        with patch.object(
            repository_module.customer_repository,
            "search_customers",
            return_value=[row],
        ):
            result = CustomerService().search(
                search="812345678",
                route_code=None,
                store_number=None,
                active_only=False,
                limit=100,
                offset=0,
            )

        customer = result["customers"][0]
        self.assertEqual(customer["customer_number"], 654321)
        self.assertEqual(customer["address_line_1"], "400 TEST AVE")
        self.assertEqual(customer["address_line_2"], "SAMPLE CITY NY 10001")
        self.assertEqual(customer["city"], "")
        self.assertEqual(customer["state"], "NY")
        self.assertEqual(customer["postal_code"], "10001")


if __name__ == "__main__":
    unittest.main()
