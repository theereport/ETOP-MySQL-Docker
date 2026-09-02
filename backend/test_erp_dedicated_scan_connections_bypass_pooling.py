from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

import mysql.connector

os.environ.setdefault("MYSQL_HOST", "localhost")
os.environ.setdefault("MYSQL_USER", "test")
os.environ.setdefault("MYSQL_PASSWORD", "test")
os.environ.setdefault("MYSQL_DATABASE", "test")

from core.database import madden_database
from modules.accounts_payable import erp_ledger_scan
from modules.cash_flow_forecasting import ap_due_date_cache_source
from modules.document_intelligence.integrations import invoice_owner_cache


class DedicatedScanConnectionsExcludePoolingTests(unittest.TestCase):
    """madden_database's connect() config now carries pool_name/pool_size
    so its ordinary short read-only queries reuse a connection pool. The
    three modules that copy that config to open their own dedicated,
    extended-MAX_EXECUTION_TIME connection for a long full-table scan must
    NOT inherit those two keys - pool_reset_session doesn't clear a custom
    SESSION MAX_EXECUTION_TIME, so a pooled long-scan connection could hand
    its extended timeout to a later, unrelated short query, and a long scan
    would otherwise tie up one of the pool's few connections for its whole
    duration."""

    def setUp(self) -> None:
        self.assertIn("pool_name", madden_database.config)
        self.assertIn("pool_size", madden_database.config)

    def test_ap_ledger_scan_connection_excludes_pooling(self) -> None:
        with patch.object(
            erp_ledger_scan.mysql.connector,
            "connect",
            return_value=MagicMock(),
        ) as connect:
            erp_ledger_scan._connect()
        _, kwargs = connect.call_args
        self.assertNotIn("pool_name", kwargs)
        self.assertNotIn("pool_size", kwargs)

    def test_cash_flow_ap_cache_scan_connection_excludes_pooling(self) -> None:
        with patch.object(
            ap_due_date_cache_source.mysql.connector,
            "connect",
            side_effect=mysql.connector.Error("stop before any real query executes"),
        ) as connect:
            with self.assertRaises(
                ap_due_date_cache_source.ApDueDateCacheRefreshFailed
            ):
                ap_due_date_cache_source.scan_all_open_ap_invoices()
        _, kwargs = connect.call_args
        self.assertNotIn("pool_name", kwargs)
        self.assertNotIn("pool_size", kwargs)

    def test_invoice_owner_cache_scan_connection_excludes_pooling(self) -> None:
        with patch.object(
            invoice_owner_cache.mysql.connector,
            "connect",
            side_effect=mysql.connector.Error("stop before any real query executes"),
        ) as connect:
            with self.assertRaises(
                invoice_owner_cache.InvoiceOwnerCacheRefreshFailed
            ):
                invoice_owner_cache.scan_all_open_invoice_owners()
        _, kwargs = connect.call_args
        self.assertNotIn("pool_name", kwargs)
        self.assertNotIn("pool_size", kwargs)


if __name__ == "__main__":
    unittest.main()
