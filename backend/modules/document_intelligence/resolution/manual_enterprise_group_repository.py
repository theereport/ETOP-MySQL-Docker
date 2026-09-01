from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.engine import Engine

from data.mysql import (
    get_engine,
    manual_enterprise_group_members_table,
    manual_enterprise_groups_table,
    metadata,
)

_TABLES = [manual_enterprise_groups_table, manual_enterprise_group_members_table]


class ManualEnterpriseGroupRepository:
    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine or get_engine()

    def initialize(self):
        metadata.create_all(self._engine, checkfirst=True, tables=_TABLES)

    def find_group_members(self, customer_number):
        """Every customer number manually grouped with this one (including
        itself), or [] if this customer is not in a manual group."""
        customer_number = (customer_number or "").strip()
        if not customer_number:
            return []
        self.initialize()
        members = manual_enterprise_group_members_table
        with self._engine.connect() as connection:
            own_group = connection.execute(
                select(members.c.group_id).where(
                    members.c.customer_number == customer_number
                )
            ).first()
            if not own_group:
                return []
            rows = connection.execute(
                select(members.c.customer_number).where(
                    members.c.group_id == own_group[0]
                )
            ).all()
        return [row[0] for row in rows]

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
        groups = manual_enterprise_groups_table
        members = manual_enterprise_group_members_table
        with self._engine.begin() as connection:
            existing_a = connection.execute(
                select(members.c.group_id).where(
                    members.c.customer_number == customer_number
                )
            ).first()
            existing_b = connection.execute(
                select(members.c.group_id).where(
                    members.c.customer_number == link_to_customer_number
                )
            ).first()

            if existing_a and existing_b:
                if existing_a[0] != existing_b[0]:
                    raise ValueError(
                        "Both customers already belong to different "
                        "manual enterprise groups. Unlink one before "
                        "merging them."
                    )
                return existing_a[0]

            if existing_a:
                group_id = existing_a[0]
                connection.execute(
                    members.insert().values(
                        group_id=group_id,
                        customer_number=link_to_customer_number,
                        added_by=added_by,
                        added_at=now,
                    )
                )
                return group_id

            if existing_b:
                group_id = existing_b[0]
                connection.execute(
                    members.insert().values(
                        group_id=group_id,
                        customer_number=customer_number,
                        added_by=added_by,
                        added_at=now,
                    )
                )
                return group_id

            result = connection.execute(
                groups.insert().values(created_by=added_by, created_at=now)
            )
            group_id = result.inserted_primary_key[0]
            connection.execute(
                members.insert(),
                [
                    {
                        "group_id": group_id,
                        "customer_number": customer_number,
                        "added_by": added_by,
                        "added_at": now,
                    },
                    {
                        "group_id": group_id,
                        "customer_number": link_to_customer_number,
                        "added_by": added_by,
                        "added_at": now,
                    },
                ],
            )
            return group_id

    def unlink_customer(self, customer_number):
        """Remove a customer from its manual enterprise group, if any."""
        customer_number = (customer_number or "").strip()
        if not customer_number:
            return
        self.initialize()
        members = manual_enterprise_group_members_table
        with self._engine.begin() as connection:
            connection.execute(
                members.delete().where(members.c.customer_number == customer_number)
            )
