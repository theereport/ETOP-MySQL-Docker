from __future__ import annotations

import unittest
from unittest.mock import patch

from modules.customer_360 import service as customer_360_service


class DiscountCustomerFlagTest(unittest.TestCase):
    """CUCONTRACT ("discount structure") drives flags.discount_customer for
    the lockbox review workspace's "Discount Customer" warning banner - any
    nonzero, non-null value means yes, zero/blank means no."""

    def _summary(self, cucontract) -> dict:
        with patch.object(
            customer_360_service.customer_repository,
            "get_customer",
            return_value={"CUNUMBER": 640194, "CUCONTRACT": cucontract},
        ):
            return customer_360_service.customer_service.summary(640194)

    def test_nonzero_cucontract_is_flagged_as_discount_customer(self) -> None:
        self.assertTrue(self._summary(7)["flags"]["discount_customer"])

    def test_zero_cucontract_is_not_flagged(self) -> None:
        self.assertFalse(self._summary(0)["flags"]["discount_customer"])

    def test_blank_cucontract_is_not_flagged(self) -> None:
        self.assertFalse(self._summary(None)["flags"]["discount_customer"])


if __name__ == "__main__":
    unittest.main()
