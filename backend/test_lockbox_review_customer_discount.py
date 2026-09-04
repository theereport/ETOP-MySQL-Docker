from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine

from data.mysql import _reset_engine_override, _set_engine_override
from modules.document_intelligence.lockbox_review import service as review_service


class CustomerDiscountTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.engine = create_engine(
            f"sqlite:///{Path(self._tmpdir.name) / 'review.db'}"
        )
        _set_engine_override(self.engine)
        self.addCleanup(_reset_engine_override)
        self.addCleanup(self.engine.dispose)

    def test_unset_customer_returns_default(self) -> None:
        result = review_service.get_customer_discount("640194")
        self.assertEqual(result["customer_number"], "640194")
        self.assertFalse(result["is_discount_customer"])
        self.assertEqual(result["discount_percent"], 0.0)

    def test_save_and_reload_round_trips(self) -> None:
        review_service.save_customer_discount(
            "640194",
            {
                "is_discount_customer": True,
                "discount_percent": 2.5,
                "updated_by": "jcorbit",
            },
        )
        result = review_service.get_customer_discount("640194")
        self.assertTrue(result["is_discount_customer"])
        self.assertEqual(result["discount_percent"], 2.5)
        self.assertEqual(result["updated_by"], "jcorbit")

    def test_save_overwrites_prior_value(self) -> None:
        review_service.save_customer_discount(
            "640194",
            {"is_discount_customer": True, "discount_percent": 2.0},
        )
        review_service.save_customer_discount(
            "640194",
            {"is_discount_customer": False, "discount_percent": 0.0},
        )
        result = review_service.get_customer_discount("640194")
        self.assertFalse(result["is_discount_customer"])
        self.assertEqual(result["discount_percent"], 0.0)

    def test_setting_is_scoped_per_customer(self) -> None:
        review_service.save_customer_discount(
            "640194",
            {"is_discount_customer": True, "discount_percent": 2.0},
        )
        other = review_service.get_customer_discount("999999")
        self.assertFalse(other["is_discount_customer"])

    def test_blank_customer_number_is_rejected(self) -> None:
        with self.assertRaises(Exception):
            review_service.get_customer_discount("  ")
        with self.assertRaises(Exception):
            review_service.save_customer_discount(
                "  ", {"is_discount_customer": True, "discount_percent": 2.0}
            )


if __name__ == "__main__":
    unittest.main()
