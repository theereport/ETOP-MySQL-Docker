"""ETOP-owned master data for Route Intelligence, plus the one MaddenCo
read (customer route/store assignment) that doesn't belong to any other
module's public surface.

Warehouses and routes themselves are intentionally NOT read here - they
already live in MaddenCo and are read through freight_logistics_service
(see service.py), per Module Rule 2 (cross-module deps reach a module's
service.py, not another module's repository.py or raw ERP tables).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from core.database import madden_database
from data.mysql import (
    get_engine,
    metadata,
    route_business_rules_table,
    route_customer_profiles_table,
    route_driver_availability_table,
    route_drivers_table,
    route_vehicle_capacities_table,
    route_vehicles_table,
)

_TABLES = [
    route_customer_profiles_table,
    route_vehicles_table,
    route_vehicle_capacities_table,
    route_drivers_table,
    route_driver_availability_table,
    route_business_rules_table,
]


def initialize_database() -> None:
    metadata.create_all(get_engine(), checkfirst=True, tables=_TABLES)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- MaddenCo read: customer route/store assignment -------------------

GET_CUSTOMER_ROUTE_ASSIGNMENTS_SQL = """
    SELECT
        CUNUMBER,
        TRIM(CUNAME) AS CUNAME,
        TRIM(CUROUTECD) AS CUROUTECD,
        CUSTORENUM
    FROM TMCUST
    WHERE CUSTORENUM > 0
    ORDER BY CUNUMBER
    LIMIT %s
"""


def list_customer_route_assignments(limit: int = 20000) -> list[dict[str, Any]]:
    """Every K&M customer's route-code/store assignment from MaddenCo.

    Scoped to CUSTORENUM > 0 as the simplest available proxy for "a real,
    assigned customer" - TMCUST has no confirmed active/inactive flag
    elsewhere in this codebase, so this is a documented simplifying
    assumption (see the module README), not a verified business rule.
    """

    return madden_database.fetch_all(
        GET_CUSTOMER_ROUTE_ASSIGNMENTS_SQL, (limit,)
    )


# --- route_customer_profiles --------------------------------------------

def get_customer_profile(customer_number: str) -> dict[str, Any] | None:
    initialize_database()
    table = route_customer_profiles_table
    with get_engine().connect() as connection:
        row = connection.execute(
            select(table).where(table.c.customer_number == customer_number)
        ).mappings().first()
    return dict(row) if row is not None else None


def list_customer_profiles() -> list[dict[str, Any]]:
    initialize_database()
    table = route_customer_profiles_table
    with get_engine().connect() as connection:
        rows = connection.execute(select(table)).mappings().all()
    return [dict(row) for row in rows]


def save_customer_profile(
    customer_number: str,
    values: dict[str, Any],
) -> dict[str, Any]:
    initialize_database()
    table = route_customer_profiles_table
    payload = {**values, "updated_at": _now()}
    with get_engine().begin() as connection:
        existing = connection.execute(
            select(table.c.customer_number).where(
                table.c.customer_number == customer_number
            )
        ).first()
        if existing is None:
            connection.execute(
                table.insert().values(customer_number=customer_number, **payload)
            )
        else:
            connection.execute(
                table.update()
                .where(table.c.customer_number == customer_number)
                .values(**payload)
            )
    profile = get_customer_profile(customer_number)
    assert profile is not None  # pragma: no cover - just written above
    return profile


# --- route_vehicles / route_vehicle_capacities --------------------------

def list_vehicles() -> list[dict[str, Any]]:
    initialize_database()
    table = route_vehicles_table
    with get_engine().connect() as connection:
        rows = connection.execute(select(table)).mappings().all()
    return [dict(row) for row in rows]


def get_vehicle(vehicle_id: int) -> dict[str, Any] | None:
    initialize_database()
    table = route_vehicles_table
    with get_engine().connect() as connection:
        row = connection.execute(
            select(table).where(table.c.vehicle_id == vehicle_id)
        ).mappings().first()
    return dict(row) if row is not None else None


def create_vehicle(values: dict[str, Any]) -> dict[str, Any]:
    initialize_database()
    table = route_vehicles_table
    with get_engine().begin() as connection:
        result = connection.execute(
            table.insert().values(updated_at=_now(), **values)
        )
        vehicle_id = result.inserted_primary_key[0]
    vehicle = get_vehicle(vehicle_id)
    assert vehicle is not None  # pragma: no cover
    return vehicle


def update_vehicle(vehicle_id: int, values: dict[str, Any]) -> dict[str, Any] | None:
    initialize_database()
    table = route_vehicles_table
    with get_engine().begin() as connection:
        result = connection.execute(
            table.update()
            .where(table.c.vehicle_id == vehicle_id)
            .values(updated_at=_now(), **values)
        )
        if result.rowcount != 1:
            return None
    return get_vehicle(vehicle_id)


def list_vehicle_capacities(vehicle_id: int) -> list[dict[str, Any]]:
    initialize_database()
    table = route_vehicle_capacities_table
    with get_engine().connect() as connection:
        rows = connection.execute(
            select(table).where(table.c.vehicle_id == vehicle_id)
        ).mappings().all()
    return [dict(row) for row in rows]


def add_vehicle_capacity(vehicle_id: int, values: dict[str, Any]) -> dict[str, Any]:
    initialize_database()
    table = route_vehicle_capacities_table
    with get_engine().begin() as connection:
        result = connection.execute(
            table.insert().values(vehicle_id=vehicle_id, **values)
        )
        capacity_id = result.inserted_primary_key[0]
    with get_engine().connect() as connection:
        row = connection.execute(
            select(table).where(table.c.capacity_id == capacity_id)
        ).mappings().first()
    assert row is not None  # pragma: no cover
    return dict(row)


# --- route_drivers / route_driver_availability --------------------------

def list_drivers() -> list[dict[str, Any]]:
    initialize_database()
    table = route_drivers_table
    with get_engine().connect() as connection:
        rows = connection.execute(select(table)).mappings().all()
    return [dict(row) for row in rows]


def get_driver(driver_id: int) -> dict[str, Any] | None:
    initialize_database()
    table = route_drivers_table
    with get_engine().connect() as connection:
        row = connection.execute(
            select(table).where(table.c.driver_id == driver_id)
        ).mappings().first()
    return dict(row) if row is not None else None


def create_driver(values: dict[str, Any]) -> dict[str, Any]:
    initialize_database()
    table = route_drivers_table
    with get_engine().begin() as connection:
        result = connection.execute(
            table.insert().values(updated_at=_now(), **values)
        )
        driver_id = result.inserted_primary_key[0]
    driver = get_driver(driver_id)
    assert driver is not None  # pragma: no cover
    return driver


def update_driver(driver_id: int, values: dict[str, Any]) -> dict[str, Any] | None:
    initialize_database()
    table = route_drivers_table
    with get_engine().begin() as connection:
        result = connection.execute(
            table.update()
            .where(table.c.driver_id == driver_id)
            .values(updated_at=_now(), **values)
        )
        if result.rowcount != 1:
            return None
    return get_driver(driver_id)


def list_driver_availability(driver_id: int) -> list[dict[str, Any]]:
    initialize_database()
    table = route_driver_availability_table
    with get_engine().connect() as connection:
        rows = connection.execute(
            select(table).where(table.c.driver_id == driver_id)
        ).mappings().all()
    return [dict(row) for row in rows]


def set_driver_availability(
    driver_id: int,
    day_of_week: str,
    values: dict[str, Any],
) -> dict[str, Any]:
    """Upsert one day's availability for a driver (driver_id + day_of_week
    is the natural key, even though it isn't a DB-enforced unique
    constraint - a v1 recurring-weekly-schedule simplification)."""

    initialize_database()
    table = route_driver_availability_table
    with get_engine().begin() as connection:
        existing = connection.execute(
            select(table.c.availability_id).where(
                table.c.driver_id == driver_id,
                table.c.day_of_week == day_of_week,
            )
        ).first()
        if existing is None:
            result = connection.execute(
                table.insert().values(
                    driver_id=driver_id, day_of_week=day_of_week, **values
                )
            )
            availability_id = result.inserted_primary_key[0]
        else:
            availability_id = existing[0]
            connection.execute(
                table.update()
                .where(table.c.availability_id == availability_id)
                .values(**values)
            )
    with get_engine().connect() as connection:
        row = connection.execute(
            select(table).where(table.c.availability_id == availability_id)
        ).mappings().first()
    assert row is not None  # pragma: no cover
    return dict(row)


# --- route_business_rules -----------------------------------------------

def list_business_rules() -> list[dict[str, Any]]:
    initialize_database()
    table = route_business_rules_table
    with get_engine().connect() as connection:
        rows = connection.execute(select(table)).mappings().all()
    return [dict(row) for row in rows]


def get_business_rule(rule_key: str) -> dict[str, Any] | None:
    initialize_database()
    table = route_business_rules_table
    with get_engine().connect() as connection:
        row = connection.execute(
            select(table).where(table.c.rule_key == rule_key)
        ).mappings().first()
    return dict(row) if row is not None else None


def save_business_rule(rule_key: str, values: dict[str, Any]) -> dict[str, Any]:
    initialize_database()
    table = route_business_rules_table
    payload = {**values, "updated_at": _now()}
    with get_engine().begin() as connection:
        existing = connection.execute(
            select(table.c.rule_key).where(table.c.rule_key == rule_key)
        ).first()
        if existing is None:
            connection.execute(
                table.insert().values(rule_key=rule_key, **payload)
            )
        else:
            connection.execute(
                table.update()
                .where(table.c.rule_key == rule_key)
                .values(**payload)
            )
    rule = get_business_rule(rule_key)
    assert rule is not None  # pragma: no cover
    return rule
