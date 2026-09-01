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
    """Records upsert() calls instead of touching a real database, so
    these tests verify what save_transaction_review *asks* to be
    remembered without depending on SQLite file locking/paths."""

    calls: list[tuple] = []

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def upsert(self, *args, **kwargs) -> None:
        FakePayerMappingRepository.calls.append((args, kwargs))


def _source(transaction: dict) -> dict:
    return {"transactions": [transaction]}


class SaveTransactionReviewPayerMappingTest(unittest.TestCase):
    def setUp(self) -> None:
        FakePayerMappingRepository.calls = []
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
            # Other test modules (and main.py's own startup wiring) call
            # configure_governed_preparation_loader/
            # configure_current_open_ar_loader, which sets process-global
            # state on this module. Pin both to None so this test's
            # behavior does not depend on what ran before it in the suite.
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
                {"invoice_number": "12345678", "net_invoice_amount": 100.00}
            ],
            status="corrected",
            customer_number="640194",
            customer_name="Gothenburg Tire",
        ).model_dump()
        base.update(overrides)
        return base

    def test_confirmed_save_records_a_payer_mapping(self) -> None:
        with patch.object(
            review_service,
            "get_lockbox_result",
            lambda _job_id: deepcopy(_source(self._transaction())),
        ):
            review_service.save_transaction_review(
                "job-1", "T-1", self._payload()
            )

        self.assertEqual(len(FakePayerMappingRepository.calls), 1)
        args, kwargs = FakePayerMappingRepository.calls[0]
        self.assertEqual(args[0], "076401251")
        self.assertEqual(args[1], "1234")
        self.assertEqual(args[3], "640194")
        self.assertEqual(args[4], 1.0)
        self.assertTrue(kwargs.get("confirmed_by_user"))

    def test_held_draft_does_not_record_a_mapping(self) -> None:
        with patch.object(
            review_service,
            "get_lockbox_result",
            lambda _job_id: deepcopy(_source(self._transaction())),
        ):
            review_service.save_transaction_review(
                "job-2",
                "T-1",
                self._payload(status="held"),
            )

        self.assertEqual(FakePayerMappingRepository.calls, [])

    def test_missing_routing_number_does_not_record_a_mapping(self) -> None:
        with patch.object(
            review_service,
            "get_lockbox_result",
            lambda _job_id: deepcopy(
                _source(self._transaction(aba_routing=""))
            ),
        ):
            review_service.save_transaction_review(
                "job-3", "T-1", self._payload()
            )

        self.assertEqual(FakePayerMappingRepository.calls, [])

    def test_blank_customer_number_does_not_record_a_mapping(self) -> None:
        with patch.object(
            review_service,
            "get_lockbox_result",
            lambda _job_id: deepcopy(_source(self._transaction())),
        ):
            review_service.save_transaction_review(
                "job-4",
                "T-1",
                self._payload(customer_number=""),
            )

        self.assertEqual(FakePayerMappingRepository.calls, [])


if __name__ == "__main__":
    unittest.main()
