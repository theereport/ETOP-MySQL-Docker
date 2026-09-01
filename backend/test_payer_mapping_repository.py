import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine

from modules.document_intelligence.resolution.payer_mapping_repository import (
    PayerCustomerMappingRepository,
)


class PayerCustomerMappingRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            f"sqlite:///{Path(self._tmpdir.name) / 'mapping.db'}"
        )
        self.repo = PayerCustomerMappingRepository(engine=self.engine)
        self.repo.initialize()

    def tearDown(self) -> None:
        self.engine.dispose()
        self._tmpdir.cleanup()

    def test_confirmed_mapping_round_trips(self) -> None:
        self.repo.upsert("076401251", "1234", "GOTHENBURG TIR&SVC", "640194", 1.0)

        found = self.repo.find_confirmed_customer_numbers("076401251", "1234")

        self.assertEqual(found, ["640194"])

    def test_unconfirmed_mapping_is_not_returned(self) -> None:
        self.repo.upsert(
            "076401251", "1234", "GOTHENBURG TIR&SVC", "640194", 0.5,
            confirmed_by_user=False,
        )

        found = self.repo.find_confirmed_customer_numbers("076401251", "1234")

        self.assertEqual(found, [])

    def test_different_payer_names_on_the_same_account_both_count(self) -> None:
        self.repo.upsert("076401251", "1234", "GOTHENBURG TIRE", "640194", 1.0)
        self.repo.upsert("076401251", "1234", "GOTHENBURG TIR&SVC", "640194", 1.0)

        found = self.repo.find_confirmed_customer_numbers("076401251", "1234")

        self.assertEqual(found, ["640194"])

    def test_two_distinct_confirmed_customers_are_both_returned(self) -> None:
        self.repo.upsert("076401251", "1234", "PAYER A", "640194", 1.0)
        self.repo.upsert("076401251", "1234", "PAYER B", "700001", 1.0)

        found = self.repo.find_confirmed_customer_numbers("076401251", "1234")

        self.assertEqual(sorted(found), ["640194", "700001"])

    def test_missing_routing_or_account_returns_empty(self) -> None:
        self.assertEqual(
            self.repo.find_confirmed_customer_numbers("", "1234"), []
        )
        self.assertEqual(
            self.repo.find_confirmed_customer_numbers("076401251", ""), []
        )

    def test_different_account_does_not_match(self) -> None:
        self.repo.upsert("076401251", "1234", "GOTHENBURG TIRE", "640194", 1.0)

        found = self.repo.find_confirmed_customer_numbers("076401251", "5678")

        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
