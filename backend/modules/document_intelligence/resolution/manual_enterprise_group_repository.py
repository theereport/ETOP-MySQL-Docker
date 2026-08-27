import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from core.test_path_override import resolve_test_path_override


class ManualEnterpriseGroupRepository:
    def __init__(self, db_path=None):
        self.db_path = Path(
            db_path
            if db_path is not None
            else resolve_test_path_override(
                "ETOP_TEST_MANUAL_ENTERPRISE_GROUP_DB",
                "data/modules/document_intelligence/document_intelligence.db",
            )
        )

    def initialize(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(self.db_path)
        try:
            with c:
                c.execute("""CREATE TABLE IF NOT EXISTS manual_enterprise_groups(
                    group_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_by TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL)""")
                c.execute("""CREATE TABLE IF NOT EXISTS manual_enterprise_group_members(
                    group_id INTEGER NOT NULL,
                    customer_number TEXT NOT NULL UNIQUE,
                    added_by TEXT NOT NULL DEFAULT '',
                    added_at TEXT NOT NULL,
                    FOREIGN KEY(group_id) REFERENCES manual_enterprise_groups(group_id))""")
        finally:
            c.close()

    def find_group_members(self, customer_number):
        """Every customer number manually grouped with this one (including
        itself), or [] if this customer is not in a manual group."""
        customer_number = (customer_number or "").strip()
        if not customer_number:
            return []
        self.initialize()
        c = sqlite3.connect(self.db_path)
        try:
            c.row_factory = sqlite3.Row
            own_group = c.execute(
                "SELECT group_id FROM manual_enterprise_group_members "
                "WHERE customer_number = ?",
                (customer_number,),
            ).fetchone()
            if not own_group:
                return []
            rows = c.execute(
                "SELECT customer_number FROM manual_enterprise_group_members "
                "WHERE group_id = ?",
                (own_group["group_id"],),
            ).fetchall()
        finally:
            c.close()
        return [row["customer_number"] for row in rows]

    def link_customers(self, customer_number, link_to_customer_number, added_by=""):
        """Link two customers as a manual enterprise group for payment
        purposes. Merges into whichever group either side already belongs
        to, or creates a new group if neither does. Idempotent when both
        already share a group. Raises ValueError when the two customers
        already belong to two different existing groups - a reviewer must
        unlink one side first rather than have groups silently merged."""
        customer_number = (customer_number or "").strip()
        link_to_customer_number = (link_to_customer_number or "").strip()
        if not customer_number or not link_to_customer_number:
            raise ValueError("Both customer numbers are required.")
        if customer_number == link_to_customer_number:
            raise ValueError("A customer cannot be linked to itself.")

        self.initialize()
        now = datetime.now(timezone.utc).isoformat()
        c = sqlite3.connect(self.db_path)
        try:
            c.row_factory = sqlite3.Row
            with c:
                existing_a = c.execute(
                    "SELECT group_id FROM manual_enterprise_group_members "
                    "WHERE customer_number = ?",
                    (customer_number,),
                ).fetchone()
                existing_b = c.execute(
                    "SELECT group_id FROM manual_enterprise_group_members "
                    "WHERE customer_number = ?",
                    (link_to_customer_number,),
                ).fetchone()

                if existing_a and existing_b:
                    if existing_a["group_id"] != existing_b["group_id"]:
                        raise ValueError(
                            "Both customers already belong to different "
                            "manual enterprise groups. Unlink one before "
                            "merging them."
                        )
                    return existing_a["group_id"]

                if existing_a:
                    group_id = existing_a["group_id"]
                    c.execute(
                        "INSERT INTO manual_enterprise_group_members"
                        "(group_id, customer_number, added_by, added_at) "
                        "VALUES(?,?,?,?)",
                        (group_id, link_to_customer_number, added_by, now),
                    )
                    return group_id

                if existing_b:
                    group_id = existing_b["group_id"]
                    c.execute(
                        "INSERT INTO manual_enterprise_group_members"
                        "(group_id, customer_number, added_by, added_at) "
                        "VALUES(?,?,?,?)",
                        (group_id, customer_number, added_by, now),
                    )
                    return group_id

                cursor = c.execute(
                    "INSERT INTO manual_enterprise_groups"
                    "(created_by, created_at) VALUES(?,?)",
                    (added_by, now),
                )
                group_id = cursor.lastrowid
                c.executemany(
                    "INSERT INTO manual_enterprise_group_members"
                    "(group_id, customer_number, added_by, added_at) "
                    "VALUES(?,?,?,?)",
                    [
                        (group_id, customer_number, added_by, now),
                        (group_id, link_to_customer_number, added_by, now),
                    ],
                )
                return group_id
        finally:
            c.close()

    def unlink_customer(self, customer_number):
        """Remove a customer from its manual enterprise group, if any."""
        customer_number = (customer_number or "").strip()
        if not customer_number:
            return
        self.initialize()
        c = sqlite3.connect(self.db_path)
        try:
            with c:
                c.execute(
                    "DELETE FROM manual_enterprise_group_members "
                    "WHERE customer_number = ?",
                    (customer_number,),
                )
        finally:
            c.close()
