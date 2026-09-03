from __future__ import annotations

import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine

from data.mysql import _reset_engine_override, _set_engine_override
from modules.document_intelligence.lockbox_review import service as review_service
from modules.document_intelligence.lockbox_review.schemas import (
    SaveTransactionReviewRequest,
)


class FakePayerMappingRepository:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def upsert(self, *_args, **_kwargs) -> None:
        pass


def _source(transaction: dict) -> dict:
    return {"transactions": [transaction]}


class MiscGlEntryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.engine = create_engine(
            f"sqlite:///{Path(self._tmpdir.name) / 'review.db'}"
        )
        _set_engine_override(self.engine)
        self.addCleanup(_reset_engine_override)
        self.addCleanup(self.engine.dispose)
        self._patches = [
            patch.object(
                review_service,
                "PayerCustomerMappingRepository",
                FakePayerMappingRepository,
            ),
            patch.object(review_service, "_governed_preparation_loader", None),
            patch.object(review_service, "_current_open_ar_loader", None),
        ]
        for patcher in self._patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def _transaction(self, **overrides) -> dict:
        base = {
            "transaction_id": "T-1",
            "check_amount": 100.00,
            "aba_routing": "076401251",
            "account_number": "998877661234",
            "original_allocations": [],
            "allocations": [],
        }
        base.update(overrides)
        return base

    def _payload(self, **overrides) -> dict:
        base = SaveTransactionReviewRequest(
            allocations=[
                {"invoice_number": "12345678", "net_invoice_amount": 90.00}
            ],
            expected_reviewed_at=None,
            status="corrected",
            customer_number="640194",
            customer_name="Gothenburg Tire",
        ).model_dump()
        base.update(overrides)
        return base

    def test_misc_gl_amount_covers_the_remaining_difference(self) -> None:
        with patch.object(
            review_service,
            "get_lockbox_result",
            lambda _job_id: deepcopy(_source(self._transaction())),
        ):
            result = review_service.save_transaction_review(
                "job-1",
                "T-1",
                self._payload(
                    misc_gl_reason="Service Charge ADJ",
                    misc_gl_amount=10.00,
                ),
            )

        transaction = result["transactions"][0]
        self.assertEqual(transaction["difference"], 0.0)
        self.assertTrue(transaction["balanced"])
        self.assertEqual(transaction["misc_gl"]["gl_code"], "3880")
        self.assertEqual(transaction["misc_gl"]["amount"], 10.0)

    def test_ar_variance_reason_resolves_to_its_own_gl_code(self) -> None:
        with patch.object(
            review_service,
            "get_lockbox_result",
            lambda _job_id: deepcopy(_source(self._transaction())),
        ):
            result = review_service.save_transaction_review(
                "job-ar-variance",
                "T-1",
                self._payload(
                    misc_gl_reason="AR Variance",
                    misc_gl_amount=10.00,
                ),
            )

        transaction = result["transactions"][0]
        self.assertEqual(transaction["misc_gl"]["gl_code"], "3950")
        self.assertEqual(transaction["misc_gl"]["amount"], 10.0)

    def test_unknown_reason_is_rejected(self) -> None:
        with patch.object(
            review_service,
            "get_lockbox_result",
            lambda _job_id: deepcopy(_source(self._transaction())),
        ):
            with self.assertRaises(Exception):
                review_service.save_transaction_review(
                    "job-2",
                    "T-1",
                    self._payload(
                        misc_gl_reason="Not A Real Reason",
                        misc_gl_amount=10.00,
                    ),
                )

    def test_amount_without_reason_is_rejected(self) -> None:
        with patch.object(
            review_service,
            "get_lockbox_result",
            lambda _job_id: deepcopy(_source(self._transaction())),
        ):
            with self.assertRaises(Exception):
                review_service.save_transaction_review(
                    "job-3",
                    "T-1",
                    self._payload(misc_gl_amount=10.00),
                )

    def test_misc_gl_entry_round_trips_on_reload(self) -> None:
        with patch.object(
            review_service,
            "get_lockbox_result",
            lambda _job_id: deepcopy(_source(self._transaction())),
        ):
            review_service.save_transaction_review(
                "job-4",
                "T-1",
                self._payload(
                    misc_gl_reason="Service Charge ADJ",
                    misc_gl_location="DAL",
                    misc_gl_department="AR",
                    misc_gl_amount=10.00,
                ),
            )
            reloaded = review_service.get_lockbox_review("job-4")

        misc_gl = reloaded["transactions"][0]["misc_gl"]
        self.assertEqual(misc_gl["reason"], "Service Charge ADJ")
        self.assertEqual(misc_gl["gl_code"], "3880")
        self.assertEqual(misc_gl["location"], "DAL")
        self.assertEqual(misc_gl["department"], "AR")
        self.assertEqual(misc_gl["amount"], 10.0)


if __name__ == "__main__":
    unittest.main()
