import tempfile
import unittest
from pathlib import Path

from modules.document_intelligence.resolution.manual_enterprise_group_repository import (
    ManualEnterpriseGroupRepository,
)


class ManualEnterpriseGroupRepositoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.repo = ManualEnterpriseGroupRepository(
            db_path=Path(self._tmpdir.name) / "groups.db"
        )
        self.repo.initialize()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_linking_two_new_customers_creates_a_group(self) -> None:
        self.repo.link_customers("101824", "111824", "jcorbit")

        self.assertEqual(
            sorted(self.repo.find_group_members("101824")),
            ["101824", "111824"],
        )
        self.assertEqual(
            sorted(self.repo.find_group_members("111824")),
            ["101824", "111824"],
        )

    def test_linking_a_third_customer_joins_the_existing_group(self) -> None:
        self.repo.link_customers("101824", "111824", "jcorbit")
        self.repo.link_customers("101824", "222222", "jcorbit")

        self.assertEqual(
            sorted(self.repo.find_group_members("222222")),
            ["101824", "111824", "222222"],
        )

    def test_linking_already_grouped_customers_is_idempotent(self) -> None:
        self.repo.link_customers("101824", "111824", "jcorbit")
        self.repo.link_customers("101824", "111824", "jcorbit")

        self.assertEqual(
            sorted(self.repo.find_group_members("101824")),
            ["101824", "111824"],
        )

    def test_linking_two_customers_from_different_groups_raises(self) -> None:
        self.repo.link_customers("101824", "111824", "jcorbit")
        self.repo.link_customers("300000", "400000", "jcorbit")

        with self.assertRaises(ValueError):
            self.repo.link_customers("101824", "300000", "jcorbit")

    def test_linking_a_customer_to_itself_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.repo.link_customers("101824", "101824", "jcorbit")

    def test_unlinked_customer_returns_empty(self) -> None:
        self.assertEqual(self.repo.find_group_members("999999"), [])

    def test_unlink_removes_only_that_customer(self) -> None:
        self.repo.link_customers("101824", "111824", "jcorbit")
        self.repo.link_customers("101824", "222222", "jcorbit")

        self.repo.unlink_customer("222222")

        self.assertEqual(
            sorted(self.repo.find_group_members("101824")),
            ["101824", "111824"],
        )
        self.assertEqual(self.repo.find_group_members("222222"), [])


if __name__ == "__main__":
    unittest.main()
