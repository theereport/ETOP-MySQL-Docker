from __future__ import annotations

import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
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


class StaleTransactionReviewSaveIsRejectedTests(unittest.TestCase):
    """save_transaction_review previously read the review once (check) and
    wrote much later (use) with no re-check in between - a second reviewer
    (or a stale second tab) could silently overwrite an intervening save.
    Mirrors the expected_processing_run_id optimistic-concurrency check
    service.py's save_current_job_review already used for document review
    saves, which this lockbox review save never had."""

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

    def _payload(self, *, expected_reviewed_at: str | None, **overrides) -> dict:
        base = SaveTransactionReviewRequest(
            allocations=[
                {"invoice_number": "12345678", "net_invoice_amount": 100.00}
            ],
            expected_reviewed_at=expected_reviewed_at,
            status="corrected",
            customer_number="640194",
            customer_name="Gothenburg Tire",
        ).model_dump()
        base.update(overrides)
        return base

    def test_second_save_with_stale_expected_reviewed_at_is_rejected(self) -> None:
        with patch.object(
            review_service,
            "get_lockbox_result",
            lambda _job_id: deepcopy(_source(self._transaction())),
        ):
            first = review_service.save_transaction_review(
                "job-1", "T-1", self._payload(expected_reviewed_at=None)
            )
            first_reviewed_at = first["transactions"][0]["reviewed_at"]
            self.assertIsNotNone(first_reviewed_at)

            # Simulates a second reviewer (or a stale second tab) that still
            # has the pre-review state loaded - expected_reviewed_at=None
            # no longer matches what is actually stored.
            with self.assertRaises(HTTPException) as raised:
                review_service.save_transaction_review(
                    "job-1",
                    "T-1",
                    self._payload(
                        expected_reviewed_at=None,
                        notes="A second, stale reviewer's edit.",
                    ),
                )
            self.assertEqual(raised.exception.status_code, 409)

            # The correct current token is always accepted.
            second = review_service.save_transaction_review(
                "job-1",
                "T-1",
                self._payload(
                    expected_reviewed_at=first_reviewed_at,
                    notes="A caught-up reviewer's edit.",
                ),
            )
            self.assertEqual(
                second["transactions"][0]["notes"],
                "A caught-up reviewer's edit.",
            )


if __name__ == "__main__":
    unittest.main()
