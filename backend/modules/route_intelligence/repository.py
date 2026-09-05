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

from sqlalchemy import func, select

from core.database import madden_database
from data.mysql import (
    get_engine,
    metadata,
    route_actual_runs_table,
    route_business_rules_table,
    route_capacity_assessments_table,
    route_customer_profiles_table,
    route_driver_availability_table,
    route_drivers_table,
    route_forecast_runs_table,
    route_network_reviews_table,
    route_optimization_plans_table,
    route_optimization_runs_table,
    route_permanent_route_candidates_table,
    route_plan_decisions_table,
    route_vehicle_capacities_table,
    route_vehicles_table,
    route_warehouse_locations_table,
    samsara_sync_state_table,
)

_TABLES = [
    route_customer_profiles_table,
    route_vehicles_table,
    route_vehicle_capacities_table,
    route_drivers_table,
    route_driver_availability_table,
    route_business_rules_table,
    route_actual_runs_table,
    samsara_sync_state_table,
    route_forecast_runs_table,
    route_capacity_assessments_table,
    route_warehouse_locations_table,
    route_optimization_runs_table,
    route_optimization_plans_table,
    route_plan_decisions_table,
    route_network_reviews_table,
    route_permanent_route_candidates_table,
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


def set_customer_samsara_address_id(
    customer_number: str, samsara_address_id: str | None
) -> dict[str, Any]:
    """Kept separate from save_customer_profile() deliberately - that
    function's `values` dict is rebuilt from the general edit form on
    every save, which doesn't know about the linked Samsara address and
    would silently clobber it back to null otherwise."""

    initialize_database()
    table = route_customer_profiles_table
    now = _now()
    with get_engine().begin() as connection:
        existing = connection.execute(
            select(table.c.customer_number).where(
                table.c.customer_number == customer_number
            )
        ).first()
        if existing is None:
            connection.execute(
                table.insert().values(
                    customer_number=customer_number,
                    receiving_window_start="",
                    receiving_window_end="",
                    closed_days_json="[]",
                    preferred_delivery_days_json="[]",
                    priority="",
                    vehicle_access_restrictions="",
                    delivery_instructions="",
                    notes="",
                    updated_at=now,
                    samsara_address_id=samsara_address_id,
                )
            )
        else:
            connection.execute(
                table.update()
                .where(table.c.customer_number == customer_number)
                .values(samsara_address_id=samsara_address_id, updated_at=now)
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


def get_vehicle_by_samsara_id(samsara_vehicle_id: str) -> dict[str, Any] | None:
    initialize_database()
    table = route_vehicles_table
    with get_engine().connect() as connection:
        row = connection.execute(
            select(table).where(table.c.samsara_vehicle_id == samsara_vehicle_id)
        ).mappings().first()
    return dict(row) if row is not None else None


def upsert_vehicle_from_samsara(
    samsara_vehicle_id: str, values: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    """Create or update a route_vehicles row keyed by samsara_vehicle_id.

    Returns (row, created) - created=True the first time this Samsara
    vehicle is seen, False on a subsequent re-import that just refreshes
    name/vin/active. `notes`/`home_warehouse_number` are preserved from
    the existing row on re-import (not Samsara-sourced fields) rather
    than wiped back to blank/null every time someone re-imports.
    """

    existing = get_vehicle_by_samsara_id(samsara_vehicle_id)
    if existing is None:
        payload = {"notes": "", "home_warehouse_number": None, **values}
        created = create_vehicle(
            {**payload, "samsara_vehicle_id": samsara_vehicle_id}
        )
        return created, True
    payload = {
        "notes": existing.get("notes") or "",
        "home_warehouse_number": existing.get("home_warehouse_number"),
        **values,
    }
    updated = update_vehicle(
        existing["vehicle_id"], {**payload, "samsara_vehicle_id": samsara_vehicle_id}
    )
    assert updated is not None  # pragma: no cover - vehicle_id just read above
    return updated, False


def list_vehicle_capacities(vehicle_id: int) -> list[dict[str, Any]]:
    initialize_database()
    table = route_vehicle_capacities_table
    with get_engine().connect() as connection:
        rows = connection.execute(
            select(table).where(table.c.vehicle_id == vehicle_id)
        ).mappings().all()
    return [dict(row) for row in rows]


def get_current_vehicle_capacity(vehicle_id: int) -> dict[str, Any] | None:
    """The vehicle's most-recently-entered capacity row (highest
    effective_date, tied broken by capacity_id) - not a true point-in-time
    "as of" lookup, since effective_date is a free-text column with no
    enforced format today (no rows exist yet to validate a format
    against). Used by the workload/capacity dashboard (RI-2)."""

    initialize_database()
    table = route_vehicle_capacities_table
    with get_engine().connect() as connection:
        row = connection.execute(
            select(table)
            .where(table.c.vehicle_id == vehicle_id)
            .order_by(table.c.effective_date.desc(), table.c.capacity_id.desc())
            .limit(1)
        ).mappings().first()
    return dict(row) if row is not None else None


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


def get_driver_by_samsara_id(samsara_driver_id: str) -> dict[str, Any] | None:
    initialize_database()
    table = route_drivers_table
    with get_engine().connect() as connection:
        row = connection.execute(
            select(table).where(table.c.samsara_driver_id == samsara_driver_id)
        ).mappings().first()
    return dict(row) if row is not None else None


def upsert_driver_from_samsara(
    samsara_driver_id: str, values: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    """Create or update a route_drivers row keyed by samsara_driver_id -
    see upsert_vehicle_from_samsara's docstring for the same shape and
    the same reasoning for preserving notes/home_warehouse_number/
    qualifications across re-imports."""

    existing = get_driver_by_samsara_id(samsara_driver_id)
    if existing is None:
        payload = {
            "notes": "",
            "qualifications": "",
            "home_warehouse_number": None,
            **values,
        }
        created = create_driver({**payload, "samsara_driver_id": samsara_driver_id})
        return created, True
    payload = {
        "notes": existing.get("notes") or "",
        "qualifications": existing.get("qualifications") or "",
        "home_warehouse_number": existing.get("home_warehouse_number"),
        **values,
    }
    updated = update_driver(
        existing["driver_id"], {**payload, "samsara_driver_id": samsara_driver_id}
    )
    assert updated is not None  # pragma: no cover - driver_id just read above
    return updated, False


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


# --- route_actual_runs (Samsara historical trip ingestion) ---------------

def get_actual_run_by_samsara_trip_id(samsara_trip_id: str) -> dict[str, Any] | None:
    initialize_database()
    table = route_actual_runs_table
    with get_engine().connect() as connection:
        row = connection.execute(
            select(table).where(table.c.samsara_trip_id == samsara_trip_id)
        ).mappings().first()
    return dict(row) if row is not None else None


def upsert_actual_run(samsara_trip_id: str, values: dict[str, Any]) -> dict[str, Any]:
    initialize_database()
    table = route_actual_runs_table
    with get_engine().begin() as connection:
        existing = connection.execute(
            select(table.c.run_id).where(table.c.samsara_trip_id == samsara_trip_id)
        ).first()
        if existing is None:
            connection.execute(
                table.insert().values(samsara_trip_id=samsara_trip_id, **values)
            )
        else:
            connection.execute(
                table.update()
                .where(table.c.samsara_trip_id == samsara_trip_id)
                .values(**values)
            )
    run = get_actual_run_by_samsara_trip_id(samsara_trip_id)
    assert run is not None  # pragma: no cover
    return run


def list_actual_runs(
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    initialize_database()
    table = route_actual_runs_table
    query = select(table)
    if date_from:
        query = query.where(table.c.start_time >= date_from)
    if date_to:
        query = query.where(table.c.start_time < date_to)
    query = query.order_by(table.c.start_time.desc()).limit(limit)
    with get_engine().connect() as connection:
        rows = connection.execute(query).mappings().all()
    return [dict(row) for row in rows]


def count_actual_runs_with_unresolved_links() -> int:
    """Only checks vehicle_id, not driver_id - Samsara's /trips/stream
    never returns a driver on any trip (a real API limitation, confirmed
    live 2026-09-04, not a per-trip resolution gap), so counting
    driver_id IS NULL here would flag every single ingested trip
    permanently, which isn't an actionable signal for anyone."""

    initialize_database()
    table = route_actual_runs_table
    with get_engine().connect() as connection:
        return connection.scalar(
            select(func.count())
            .select_from(table)
            .where(table.c.vehicle_id.is_(None))
        ) or 0


def aggregate_actual_runs_by_vehicle(
    *, date_from: str | None = None, date_to: str | None = None
) -> list[dict[str, Any]]:
    """Grouped in SQL rather than pulling raw rows into Python - real live
    volume is on the order of thousands of trips per day (RI-1's live
    verification: 13,168 trips for a single 2-day window). Used by the
    vehicle-performance dashboard (RI-2). Rows with no vehicle_id are
    excluded - those are already surfaced separately by
    count_actual_runs_with_unresolved_links()."""

    initialize_database()
    table = route_actual_runs_table
    query = (
        select(
            table.c.vehicle_id,
            func.count().label("run_count"),
            func.sum(table.c.distance_meters).label("total_distance_meters"),
            func.avg(table.c.distance_meters).label("average_distance_meters"),
        )
        .where(table.c.vehicle_id.isnot(None))
    )
    if date_from:
        query = query.where(table.c.start_time >= date_from)
    if date_to:
        query = query.where(table.c.start_time < date_to)
    query = query.group_by(table.c.vehicle_id)
    with get_engine().connect() as connection:
        rows = connection.execute(query).mappings().all()
    return [dict(row) for row in rows]


# --- samsara_sync_state ---------------------------------------------------

def get_sync_state(sync_key: str) -> dict[str, Any] | None:
    initialize_database()
    table = samsara_sync_state_table
    with get_engine().connect() as connection:
        row = connection.execute(
            select(table).where(table.c.sync_key == sync_key)
        ).mappings().first()
    return dict(row) if row is not None else None


def save_sync_state(sync_key: str, values: dict[str, Any]) -> dict[str, Any]:
    initialize_database()
    table = samsara_sync_state_table
    with get_engine().begin() as connection:
        existing = connection.execute(
            select(table.c.sync_key).where(table.c.sync_key == sync_key)
        ).first()
        if existing is None:
            connection.execute(table.insert().values(sync_key=sync_key, **values))
        else:
            connection.execute(
                table.update().where(table.c.sync_key == sync_key).values(**values)
            )
    state = get_sync_state(sync_key)
    assert state is not None  # pragma: no cover
    return state


# --- route_forecast_runs / route_capacity_assessments (RI-3) ---------------

def save_forecast_run(values: dict[str, Any]) -> dict[str, Any]:
    initialize_database()
    table = route_forecast_runs_table
    with get_engine().begin() as connection:
        result = connection.execute(table.insert().values(**values))
        run_id = result.inserted_primary_key[0]
    with get_engine().connect() as connection:
        row = connection.execute(
            select(table).where(table.c.run_id == run_id)
        ).mappings().first()
    assert row is not None  # pragma: no cover
    return dict(row)


def update_forecast_run(run_id: int, values: dict[str, Any]) -> dict[str, Any]:
    initialize_database()
    table = route_forecast_runs_table
    with get_engine().begin() as connection:
        connection.execute(
            table.update().where(table.c.run_id == run_id).values(**values)
        )
    with get_engine().connect() as connection:
        row = connection.execute(
            select(table).where(table.c.run_id == run_id)
        ).mappings().first()
    assert row is not None  # pragma: no cover
    return dict(row)


def get_latest_forecast_run() -> dict[str, Any] | None:
    initialize_database()
    table = route_forecast_runs_table
    with get_engine().connect() as connection:
        row = connection.execute(
            select(table).order_by(table.c.run_id.desc()).limit(1)
        ).mappings().first()
    return dict(row) if row is not None else None


def upsert_capacity_assessment(
    warehouse_number: int, day_of_week: str, values: dict[str, Any]
) -> dict[str, Any]:
    """Latest-state upsert keyed by (warehouse_number, day_of_week) - each
    compute run overwrites the prior assessment rather than accumulating
    unbounded history, same style as samsara_sync_state."""

    initialize_database()
    table = route_capacity_assessments_table
    with get_engine().begin() as connection:
        existing = connection.execute(
            select(table.c.warehouse_number).where(
                table.c.warehouse_number == warehouse_number,
                table.c.day_of_week == day_of_week,
            )
        ).first()
        if existing is None:
            connection.execute(
                table.insert().values(
                    warehouse_number=warehouse_number,
                    day_of_week=day_of_week,
                    **values,
                )
            )
        else:
            connection.execute(
                table.update()
                .where(
                    table.c.warehouse_number == warehouse_number,
                    table.c.day_of_week == day_of_week,
                )
                .values(**values)
            )
    with get_engine().connect() as connection:
        row = connection.execute(
            select(table).where(
                table.c.warehouse_number == warehouse_number,
                table.c.day_of_week == day_of_week,
            )
        ).mappings().first()
    assert row is not None  # pragma: no cover
    return dict(row)


def list_capacity_assessments() -> list[dict[str, Any]]:
    initialize_database()
    table = route_capacity_assessments_table
    with get_engine().connect() as connection:
        rows = connection.execute(
            select(table).order_by(
                table.c.warehouse_number, table.c.day_of_week
            )
        ).mappings().all()
    return [dict(row) for row in rows]


# --- route_warehouse_locations (RI-4, manual depot coordinates) -----------

def get_warehouse_location(warehouse_number: int) -> dict[str, Any] | None:
    initialize_database()
    table = route_warehouse_locations_table
    with get_engine().connect() as connection:
        row = connection.execute(
            select(table).where(table.c.warehouse_number == warehouse_number)
        ).mappings().first()
    return dict(row) if row is not None else None


def list_warehouse_locations() -> list[dict[str, Any]]:
    initialize_database()
    table = route_warehouse_locations_table
    with get_engine().connect() as connection:
        rows = connection.execute(select(table)).mappings().all()
    return [dict(row) for row in rows]


def save_warehouse_location(warehouse_number: int, values: dict[str, Any]) -> dict[str, Any]:
    initialize_database()
    table = route_warehouse_locations_table
    payload = {**values, "updated_at": _now()}
    with get_engine().begin() as connection:
        existing = connection.execute(
            select(table.c.warehouse_number).where(
                table.c.warehouse_number == warehouse_number
            )
        ).first()
        if existing is None:
            connection.execute(
                table.insert().values(warehouse_number=warehouse_number, **payload)
            )
        else:
            connection.execute(
                table.update()
                .where(table.c.warehouse_number == warehouse_number)
                .values(**payload)
            )
    location = get_warehouse_location(warehouse_number)
    assert location is not None  # pragma: no cover
    return location


# --- route_optimization_runs / route_optimization_plans (RI-4) ------------

def save_optimization_run(values: dict[str, Any]) -> dict[str, Any]:
    initialize_database()
    table = route_optimization_runs_table
    with get_engine().begin() as connection:
        result = connection.execute(table.insert().values(**values))
        run_id = result.inserted_primary_key[0]
    run = get_optimization_run(run_id)
    assert run is not None  # pragma: no cover
    return run


def update_optimization_run(run_id: int, values: dict[str, Any]) -> dict[str, Any]:
    initialize_database()
    table = route_optimization_runs_table
    with get_engine().begin() as connection:
        connection.execute(
            table.update().where(table.c.run_id == run_id).values(**values)
        )
    run = get_optimization_run(run_id)
    assert run is not None  # pragma: no cover
    return run


def get_optimization_run(run_id: int) -> dict[str, Any] | None:
    initialize_database()
    table = route_optimization_runs_table
    with get_engine().connect() as connection:
        row = connection.execute(
            select(table).where(table.c.run_id == run_id)
        ).mappings().first()
    return dict(row) if row is not None else None


def save_optimization_plan(values: dict[str, Any]) -> dict[str, Any]:
    initialize_database()
    table = route_optimization_plans_table
    with get_engine().begin() as connection:
        result = connection.execute(table.insert().values(**values))
        plan_id = result.inserted_primary_key[0]
    with get_engine().connect() as connection:
        row = connection.execute(
            select(table).where(table.c.plan_id == plan_id)
        ).mappings().first()
    assert row is not None  # pragma: no cover
    return dict(row)


def list_optimization_plans_for_run(run_id: int) -> list[dict[str, Any]]:
    initialize_database()
    table = route_optimization_plans_table
    with get_engine().connect() as connection:
        rows = connection.execute(
            select(table)
            .where(table.c.run_id == run_id)
            .order_by(table.c.scenario, table.c.vehicle_slot)
        ).mappings().all()
    return [dict(row) for row in rows]


# --- route_plan_decisions (RI-5, append-only dispatcher decisions) --------

def save_plan_decision(values: dict[str, Any]) -> dict[str, Any]:
    initialize_database()
    table = route_plan_decisions_table
    with get_engine().begin() as connection:
        result = connection.execute(table.insert().values(**values))
        decision_id = result.inserted_primary_key[0]
    with get_engine().connect() as connection:
        row = connection.execute(
            select(table).where(table.c.decision_id == decision_id)
        ).mappings().first()
    assert row is not None  # pragma: no cover
    return dict(row)


def list_plan_decisions_for_run(run_id: int) -> list[dict[str, Any]]:
    initialize_database()
    table = route_plan_decisions_table
    with get_engine().connect() as connection:
        rows = connection.execute(
            select(table)
            .where(table.c.run_id == run_id)
            .order_by(table.c.decision_id)
        ).mappings().all()
    return [dict(row) for row in rows]


# --- route_network_reviews / route_permanent_route_candidates (RI-8) ------

def save_network_review(values: dict[str, Any]) -> dict[str, Any]:
    initialize_database()
    table = route_network_reviews_table
    with get_engine().begin() as connection:
        result = connection.execute(table.insert().values(**values))
        run_id = result.inserted_primary_key[0]
    run = get_network_review(run_id)
    assert run is not None  # pragma: no cover
    return run


def update_network_review(run_id: int, values: dict[str, Any]) -> dict[str, Any]:
    initialize_database()
    table = route_network_reviews_table
    with get_engine().begin() as connection:
        connection.execute(
            table.update().where(table.c.run_id == run_id).values(**values)
        )
    run = get_network_review(run_id)
    assert run is not None  # pragma: no cover
    return run


def get_network_review(run_id: int) -> dict[str, Any] | None:
    initialize_database()
    table = route_network_reviews_table
    with get_engine().connect() as connection:
        row = connection.execute(
            select(table).where(table.c.run_id == run_id)
        ).mappings().first()
    return dict(row) if row is not None else None


def save_permanent_route_candidate(values: dict[str, Any]) -> dict[str, Any]:
    initialize_database()
    table = route_permanent_route_candidates_table
    with get_engine().begin() as connection:
        result = connection.execute(table.insert().values(**values))
        candidate_id = result.inserted_primary_key[0]
    with get_engine().connect() as connection:
        row = connection.execute(
            select(table).where(table.c.candidate_id == candidate_id)
        ).mappings().first()
    assert row is not None  # pragma: no cover
    return dict(row)


def list_permanent_route_candidates_for_run(run_id: int) -> list[dict[str, Any]]:
    initialize_database()
    table = route_permanent_route_candidates_table
    with get_engine().connect() as connection:
        rows = connection.execute(
            select(table)
            .where(table.c.run_id == run_id)
            .order_by(table.c.warehouse_number)
        ).mappings().all()
    return [dict(row) for row in rows]
