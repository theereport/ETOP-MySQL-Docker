from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any, Literal

from fastapi import HTTPException

from modules.freight_logistics.service import (
    FreightLogisticsService,
    freight_logistics_service,
)

from . import repository
from .providers.samsara_provider import SamsaraProvider, get_samsara_provider
from .schemas import (
    ActualRun,
    BusinessRule,
    CustomerProfile,
    DataQualityIssue,
    DataQualityReport,
    Driver,
    DriverAvailability,
    RoutePerformanceResponse,
    SamsaraAddress,
    SamsaraImportResult,
    SyncState,
    Vehicle,
    VehicleCapacity,
    VehicleRunPerformance,
    WarehouseWorkloadSummary,
    WorkloadSummaryResponse,
)

MAX_REPORTED_ISSUES = 200


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _map_customer_profile(row: dict[str, Any]) -> CustomerProfile:
    return CustomerProfile(
        customer_number=row["customer_number"],
        latitude=row.get("latitude"),
        longitude=row.get("longitude"),
        receiving_window_start=row.get("receiving_window_start") or "",
        receiving_window_end=row.get("receiving_window_end") or "",
        closed_days=json.loads(row.get("closed_days_json") or "[]"),
        preferred_delivery_days=json.loads(
            row.get("preferred_delivery_days_json") or "[]"
        ),
        priority=row.get("priority") or "",
        normal_unloading_minutes=row.get("normal_unloading_minutes"),
        vehicle_access_restrictions=row.get("vehicle_access_restrictions") or "",
        delivery_instructions=row.get("delivery_instructions") or "",
        notes=row.get("notes") or "",
        updated_at=row.get("updated_at") or "",
        updated_by=row.get("updated_by") or "",
        samsara_address_id=row.get("samsara_address_id"),
    )


def _map_vehicle_capacity(row: dict[str, Any]) -> VehicleCapacity:
    return VehicleCapacity(
        capacity_id=row["capacity_id"],
        vehicle_id=row["vehicle_id"],
        weight_capacity=row.get("weight_capacity"),
        cube_capacity=row.get("cube_capacity"),
        tire_equivalent_capacity=row.get("tire_equivalent_capacity"),
        max_stops=row.get("max_stops"),
        effective_date=row.get("effective_date") or "",
    )


def _map_vehicle(row: dict[str, Any]) -> Vehicle:
    capacities = [
        _map_vehicle_capacity(item)
        for item in repository.list_vehicle_capacities(row["vehicle_id"])
    ]
    return Vehicle(
        vehicle_id=row["vehicle_id"],
        unit_number=row["unit_number"],
        vehicle_type=row.get("vehicle_type") or "",
        home_warehouse_number=row.get("home_warehouse_number"),
        active=bool(row.get("active", True)),
        notes=row.get("notes") or "",
        updated_at=row.get("updated_at") or "",
        vin=row.get("vin"),
        samsara_vehicle_id=row.get("samsara_vehicle_id"),
        capacities=capacities,
    )


def _map_driver_availability(row: dict[str, Any]) -> DriverAvailability:
    return DriverAvailability(
        availability_id=row["availability_id"],
        driver_id=row["driver_id"],
        day_of_week=row["day_of_week"],
        available=bool(row.get("available", True)),
        shift_start=row.get("shift_start") or "",
        shift_end=row.get("shift_end") or "",
    )


def _map_driver(row: dict[str, Any]) -> Driver:
    availability = [
        _map_driver_availability(item)
        for item in repository.list_driver_availability(row["driver_id"])
    ]
    return Driver(
        driver_id=row["driver_id"],
        name=row["name"],
        home_warehouse_number=row.get("home_warehouse_number"),
        active=bool(row.get("active", True)),
        qualifications=row.get("qualifications") or "",
        notes=row.get("notes") or "",
        updated_at=row.get("updated_at") or "",
        samsara_driver_id=row.get("samsara_driver_id"),
        availability=availability,
    )


def _map_business_rule(row: dict[str, Any]) -> BusinessRule:
    return BusinessRule(
        rule_key=row["rule_key"],
        rule_value=row["rule_value"],
        description=row.get("description") or "",
        updated_at=row.get("updated_at") or "",
        updated_by=row.get("updated_by") or "",
    )


# --- customer profiles ---------------------------------------------------

def get_customer_profile(customer_number: str) -> CustomerProfile:
    row = repository.get_customer_profile(customer_number)
    if row is None:
        return CustomerProfile(customer_number=customer_number)
    return _map_customer_profile(row)


def list_customer_profiles() -> list[CustomerProfile]:
    return [_map_customer_profile(row) for row in repository.list_customer_profiles()]


def save_customer_profile(
    customer_number: str, payload: dict[str, Any]
) -> CustomerProfile:
    customer_number = customer_number.strip()
    if not customer_number:
        raise HTTPException(status_code=400, detail="A customer number is required.")
    values = {
        "latitude": payload.get("latitude"),
        "longitude": payload.get("longitude"),
        "receiving_window_start": payload.get("receiving_window_start", ""),
        "receiving_window_end": payload.get("receiving_window_end", ""),
        "closed_days_json": json.dumps(
            payload.get("closed_days") or [], ensure_ascii=False
        ),
        "preferred_delivery_days_json": json.dumps(
            payload.get("preferred_delivery_days") or [], ensure_ascii=False
        ),
        "priority": payload.get("priority", ""),
        "normal_unloading_minutes": payload.get("normal_unloading_minutes"),
        "vehicle_access_restrictions": payload.get(
            "vehicle_access_restrictions", ""
        ),
        "delivery_instructions": payload.get("delivery_instructions", ""),
        "notes": payload.get("notes", ""),
        "updated_by": payload.get("updated_by", ""),
    }
    row = repository.save_customer_profile(customer_number, values)
    return _map_customer_profile(row)


# --- vehicles / capacities -----------------------------------------------

def list_vehicles() -> list[Vehicle]:
    return [_map_vehicle(row) for row in repository.list_vehicles()]


def create_vehicle(payload: dict[str, Any]) -> Vehicle:
    row = repository.create_vehicle(
        {
            "unit_number": payload["unit_number"],
            "vehicle_type": payload.get("vehicle_type", ""),
            "home_warehouse_number": payload.get("home_warehouse_number"),
            "active": payload.get("active", True),
            "notes": payload.get("notes", ""),
        }
    )
    return _map_vehicle(row)


def update_vehicle(vehicle_id: int, payload: dict[str, Any]) -> Vehicle:
    row = repository.update_vehicle(
        vehicle_id,
        {
            "unit_number": payload["unit_number"],
            "vehicle_type": payload.get("vehicle_type", ""),
            "home_warehouse_number": payload.get("home_warehouse_number"),
            "active": payload.get("active", True),
            "notes": payload.get("notes", ""),
        },
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Vehicle {vehicle_id} not found.")
    return _map_vehicle(row)


def add_vehicle_capacity(vehicle_id: int, payload: dict[str, Any]) -> Vehicle:
    if repository.get_vehicle(vehicle_id) is None:
        raise HTTPException(status_code=404, detail=f"Vehicle {vehicle_id} not found.")
    repository.add_vehicle_capacity(
        vehicle_id,
        {
            "weight_capacity": payload.get("weight_capacity"),
            "cube_capacity": payload.get("cube_capacity"),
            "tire_equivalent_capacity": payload.get("tire_equivalent_capacity"),
            "max_stops": payload.get("max_stops"),
            "effective_date": payload.get("effective_date", ""),
        },
    )
    row = repository.get_vehicle(vehicle_id)
    assert row is not None  # pragma: no cover - just verified above
    return _map_vehicle(row)


# --- drivers / availability -----------------------------------------------

def list_drivers() -> list[Driver]:
    return [_map_driver(row) for row in repository.list_drivers()]


def create_driver(payload: dict[str, Any]) -> Driver:
    row = repository.create_driver(
        {
            "name": payload["name"],
            "home_warehouse_number": payload.get("home_warehouse_number"),
            "active": payload.get("active", True),
            "qualifications": payload.get("qualifications", ""),
            "notes": payload.get("notes", ""),
        }
    )
    return _map_driver(row)


def update_driver(driver_id: int, payload: dict[str, Any]) -> Driver:
    row = repository.update_driver(
        driver_id,
        {
            "name": payload["name"],
            "home_warehouse_number": payload.get("home_warehouse_number"),
            "active": payload.get("active", True),
            "qualifications": payload.get("qualifications", ""),
            "notes": payload.get("notes", ""),
        },
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"Driver {driver_id} not found.")
    return _map_driver(row)


def set_driver_availability(driver_id: int, payload: dict[str, Any]) -> Driver:
    if repository.get_driver(driver_id) is None:
        raise HTTPException(status_code=404, detail=f"Driver {driver_id} not found.")
    repository.set_driver_availability(
        driver_id,
        payload["day_of_week"],
        {
            "available": payload.get("available", True),
            "shift_start": payload.get("shift_start", ""),
            "shift_end": payload.get("shift_end", ""),
        },
    )
    row = repository.get_driver(driver_id)
    assert row is not None  # pragma: no cover - just verified above
    return _map_driver(row)


# --- business rules ---------------------------------------------------

def list_business_rules() -> list[BusinessRule]:
    return [_map_business_rule(row) for row in repository.list_business_rules()]


def save_business_rule(rule_key: str, payload: dict[str, Any]) -> BusinessRule:
    rule_key = rule_key.strip()
    if not rule_key:
        raise HTTPException(status_code=400, detail="A rule key is required.")
    row = repository.save_business_rule(
        rule_key,
        {
            "rule_value": payload["rule_value"],
            "description": payload.get("description", ""),
            "updated_by": payload.get("updated_by", ""),
        },
    )
    return _map_business_rule(row)


# --- Samsara passthrough (read-only) ---------------------------------

def _call_samsara(
    action: str,
    fn,
    *args,
    samsara: SamsaraProvider | None = None,
    **kwargs,
):
    """Run one Samsara provider call, converting the Unconfigured stub's
    (or a real API failure's) RuntimeError into a clear HTTP error instead
    of an unhandled 500."""

    provider = samsara or get_samsara_provider()
    try:
        return getattr(provider, fn)(*args, **kwargs)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Unable to {action}: {exc}",
        ) from exc


def list_samsara_vehicles(*, samsara: SamsaraProvider | None = None) -> list[dict[str, Any]]:
    return _call_samsara("list Samsara vehicles", "list_vehicles", samsara=samsara)


def list_samsara_drivers(*, samsara: SamsaraProvider | None = None) -> list[dict[str, Any]]:
    return _call_samsara("list Samsara drivers", "list_drivers", samsara=samsara)


def list_samsara_driver_vehicle_assignments(
    *, samsara: SamsaraProvider | None = None
) -> list[dict[str, Any]]:
    return _call_samsara(
        "list Samsara driver-vehicle assignments",
        "list_driver_vehicle_assignments",
        samsara=samsara,
    )


def get_samsara_customer_geofence(
    customer_number: str, *, samsara: SamsaraProvider | None = None
) -> dict[str, Any] | None:
    return _call_samsara(
        f"look up a Samsara geofence for customer {customer_number}",
        "get_customer_geofence",
        customer_number,
        samsara=samsara,
    )


def get_samsara_live_gps(
    vehicle_id: str, *, samsara: SamsaraProvider | None = None
) -> dict[str, Any] | None:
    return _call_samsara(
        f"get live GPS for Samsara vehicle {vehicle_id}",
        "get_live_gps",
        vehicle_id,
        samsara=samsara,
    )


# --- Samsara import / linking / historical sync ---------------------------

def import_samsara_vehicles(
    *, samsara: SamsaraProvider | None = None
) -> SamsaraImportResult:
    """Create/update route_vehicles from the real Samsara fleet, keyed by
    samsara_vehicle_id. Samsara is the source of truth for these fields -
    this is an import, not a two-way reconciliation."""

    vehicles = list_samsara_vehicles(samsara=samsara)
    created = 0
    updated = 0
    for vehicle in vehicles:
        samsara_vehicle_id = str(vehicle.get("id") or "").strip()
        if not samsara_vehicle_id:
            continue
        _row, was_created = repository.upsert_vehicle_from_samsara(
            samsara_vehicle_id,
            {
                "unit_number": str(vehicle.get("name") or samsara_vehicle_id),
                "vehicle_type": str(vehicle.get("type") or ""),
                "vin": vehicle.get("vin"),
                "active": True,
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1
    return SamsaraImportResult(
        samsara_count=len(vehicles), created_count=created, updated_count=updated
    )


def import_samsara_drivers(
    *, samsara: SamsaraProvider | None = None
) -> SamsaraImportResult:
    """Create/update route_drivers from the real Samsara driver list,
    keyed by samsara_driver_id - see import_samsara_vehicles()."""

    drivers = list_samsara_drivers(samsara=samsara)
    created = 0
    updated = 0
    for driver in drivers:
        samsara_driver_id = str(driver.get("id") or "").strip()
        if not samsara_driver_id:
            continue
        _row, was_created = repository.upsert_driver_from_samsara(
            samsara_driver_id,
            {
                "name": str(driver.get("name") or samsara_driver_id),
                "active": True,
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1
    return SamsaraImportResult(
        samsara_count=len(drivers), created_count=created, updated_count=updated
    )


def search_samsara_addresses(
    query: str, *, samsara: SamsaraProvider | None = None
) -> list[SamsaraAddress]:
    addresses = _call_samsara(
        "search Samsara addresses", "list_addresses", samsara=samsara
    )
    normalized_query = query.strip().lower()
    results = [
        SamsaraAddress(
            id=str(address.get("id") or ""),
            name=str(address.get("name") or ""),
            formatted_address=str(address.get("formattedAddress") or ""),
            latitude=address.get("latitude"),
            longitude=address.get("longitude"),
        )
        for address in addresses
        if not normalized_query
        or normalized_query in str(address.get("name") or "").lower()
        or normalized_query in str(address.get("formattedAddress") or "").lower()
    ]
    return results[:50]


def link_customer_samsara_address(
    customer_number: str, samsara_address_id: str | None
) -> CustomerProfile:
    customer_number = customer_number.strip()
    if not customer_number:
        raise HTTPException(status_code=400, detail="A customer number is required.")
    row = repository.set_customer_samsara_address_id(
        customer_number, samsara_address_id
    )
    return _map_customer_profile(row)


def _map_actual_run(row: dict[str, Any]) -> ActualRun:
    return ActualRun(
        run_id=row["run_id"],
        samsara_trip_id=row["samsara_trip_id"],
        vehicle_id=row.get("vehicle_id"),
        driver_id=row.get("driver_id"),
        start_time=row.get("start_time"),
        end_time=row.get("end_time"),
        start_latitude=row.get("start_latitude"),
        start_longitude=row.get("start_longitude"),
        end_latitude=row.get("end_latitude"),
        end_longitude=row.get("end_longitude"),
        distance_meters=row.get("distance_meters"),
        completion_status=row.get("completion_status") or "",
        ingested_at=row.get("ingested_at") or "",
    )


def _map_sync_state(row: dict[str, Any]) -> SyncState:
    return SyncState(
        sync_key=row["sync_key"],
        last_synced_through=row.get("last_synced_through"),
        last_run_at=row.get("last_run_at"),
        last_run_status=row.get("last_run_status") or "",
        last_run_message=row.get("last_run_message") or "",
    )


def get_trip_sync_state() -> SyncState:
    row = repository.get_sync_state("trips")
    if row is None:
        return SyncState(sync_key="trips")
    return _map_sync_state(row)


def list_actual_runs(
    *, date_from: str | None = None, date_to: str | None = None
) -> list[ActualRun]:
    return [
        _map_actual_run(row)
        for row in repository.list_actual_runs(date_from=date_from, date_to=date_to)
    ]


def sync_samsara_trips(
    date_from: date, date_to: date, *, samsara: SamsaraProvider | None = None
) -> tuple[list[ActualRun], SyncState]:
    """Pull Samsara trip history for a date range and upsert it into
    route_actual_runs. A trip whose vehicle/driver hasn't been imported
    yet is still stored (vehicle_id/driver_id left null) rather than
    silently dropped - compute_data_quality_report() surfaces those.
    """

    now = _now()
    try:
        trips = _call_samsara(
            "sync Samsara trip history",
            "list_historical_routes",
            date_from=date_from,
            date_to=date_to,
            samsara=samsara,
        )
    except HTTPException as exc:
        repository.save_sync_state(
            "trips",
            {
                "last_run_at": now,
                "last_run_status": "failed",
                "last_run_message": str(exc.detail),
            },
        )
        raise

    runs: list[ActualRun] = []
    for trip in trips:
        samsara_trip_id = str(
            trip.get("id")
            or f"{trip.get('asset', {}).get('id', '')}:{trip.get('tripStartTime', '')}"
        )
        asset = trip.get("asset") or {}
        samsara_vehicle_id = str(asset.get("id") or "").strip()
        vehicle = (
            repository.get_vehicle_by_samsara_id(samsara_vehicle_id)
            if samsara_vehicle_id
            else None
        )
        start_location = trip.get("startLocation") or {}
        end_location = trip.get("endLocation") or {}
        row = repository.upsert_actual_run(
            samsara_trip_id,
            {
                "vehicle_id": vehicle["vehicle_id"] if vehicle else None,
                # /trips/stream's response schema has no driver ID field
                # (confirmed against developers.samsara.com) - a trip
                # can't be linked to a driver from this endpoint alone.
                # Left null and surfaced by the Data Quality Center's
                # "unresolved link" check rather than guessed at.
                "driver_id": None,
                "start_time": trip.get("tripStartTime"),
                "end_time": trip.get("tripEndTime"),
                "start_latitude": start_location.get("latitude"),
                "start_longitude": start_location.get("longitude"),
                "end_latitude": end_location.get("latitude"),
                "end_longitude": end_location.get("longitude"),
                # Confirmed live 2026-09-04 (RI-2 verification): a real
                # /trips/stream trip payload carries no distance field at
                # all under any name - not "finalDistanceMeters" or
                # anything else, alongside tripStartTime/tripEndTime/
                # startLocation/endLocation/asset/completionStatus. This
                # is a permanent API limitation (same shape as the
                # always-absent driver field above), not a wrong field
                # name to fix - distance_meters will stay null for every
                # trip ingested from this endpoint until a different data
                # source is used (e.g. estimating from start/end lat-lon
                # via travel_matrix_provider.py's straight-line Haversine
                # provider, which would be an approximation, not actual
                # driven distance - a real design decision, not done
                # here).
                "distance_meters": trip.get("finalDistanceMeters"),
                "completion_status": trip.get("completionStatus") or "",
                "ingested_at": now,
            },
        )
        runs.append(_map_actual_run(row))

    repository.save_sync_state(
        "trips",
        {
            "last_synced_through": date_to.isoformat(),
            "last_run_at": now,
            "last_run_status": "success",
            "last_run_message": f"Synced {len(runs)} trip(s).",
        },
    )
    return runs, get_trip_sync_state()


# --- workload / capacity dashboard (RI-2, read-only) -----------------------

_DEFAULT_WORKLOAD_WARNING_PCT = 80.0
_DEFAULT_WORKLOAD_CRITICAL_PCT = 100.0


def _get_threshold(rule_key: str, default: float) -> float:
    """Reads a configurable threshold from route_business_rules, falling
    back to `default` when the rule is missing or not a valid number -
    the table is a generic, currently-empty KV store (no seed rows), so a
    working default is required for the dashboard to function before any
    admin has configured one."""

    rule = repository.get_business_rule(rule_key)
    if rule is None:
        return default
    try:
        return float(rule["rule_value"])
    except (TypeError, ValueError):
        return default


def _classify_workload_status(
    utilization_pct: float | None, *, warning_pct: float, critical_pct: float
) -> Literal["ok", "warning", "critical", "unknown"]:
    if utilization_pct is None:
        return "unknown"
    if utilization_pct >= critical_pct:
        return "critical"
    if utilization_pct >= warning_pct:
        return "warning"
    return "ok"


def compute_workload_summary(
    date_from: date,
    date_to: date,
    *,
    freight_service: FreightLogisticsService = freight_logistics_service,
) -> WorkloadSummaryResponse:
    """Warehouse-level demand (real MaddenCo load weight/quantity) vs.
    this module's own fleet capacity records, for a date range - computed
    live, no snapshot, same style as the Data Quality Center.

    Deliberately warehouse-level, not route-level: no schema anywhere
    links a MaddenCo route_code to a specific vehicle/driver (see the
    module README's "matching a trip to a route_code" deferral), so a
    per-route capacity comparison would have to guess at an assignment
    that doesn't exist. warehouse_number (home_warehouse_number on
    route_vehicles, warehouse_number from freight_logistics) is the one
    join key both sides genuinely share today.
    """

    warning_pct = _get_threshold(
        "workload_warning_threshold_pct", _DEFAULT_WORKLOAD_WARNING_PCT
    )
    critical_pct = _get_threshold(
        "workload_critical_threshold_pct", _DEFAULT_WORKLOAD_CRITICAL_PCT
    )

    vehicles_by_warehouse: dict[int, list[dict[str, Any]]] = {}
    for vehicle in repository.list_vehicles():
        if not vehicle.get("active", True):
            continue
        warehouse_number = vehicle.get("home_warehouse_number")
        if warehouse_number is None:
            continue
        vehicles_by_warehouse.setdefault(warehouse_number, []).append(vehicle)

    known_warehouses = freight_service.list_warehouses()
    warehouse_names = {
        warehouse.warehouse_number: warehouse.warehouse_location_name
        for warehouse in known_warehouses.warehouses
    }
    # Union with every warehouse number that actually has a vehicle home-
    # based there, even one freight_logistics's own warehouse master
    # doesn't list - confirmed live 2026-09-04 that WH_DASHBOARD_LOCATIONS
    # (what list_warehouses() reads) only covers a subset of K&M's real
    # warehouses (17 of 51), while get_load_lines_for_warehouse() still
    # returns real MaddenCo demand for the other warehouse numbers just
    # fine (they're valid KMROUTES.RTEWHSE values, just missing a
    # dashboard-location row). Driving this loop by list_warehouses()
    # alone would silently drop most of the real fleet from the report.
    all_warehouse_numbers = set(warehouse_names) | set(vehicles_by_warehouse)

    summaries: list[WarehouseWorkloadSummary] = []
    for warehouse_number in sorted(all_warehouse_numbers):
        vehicles = vehicles_by_warehouse.get(warehouse_number, [])
        total_weight_capacity = 0.0
        total_cube_capacity = 0.0
        total_tire_capacity = 0.0
        total_max_stops = 0
        for vehicle in vehicles:
            capacity = repository.get_current_vehicle_capacity(vehicle["vehicle_id"])
            if capacity is None:
                continue
            total_weight_capacity += capacity.get("weight_capacity") or 0.0
            total_cube_capacity += capacity.get("cube_capacity") or 0.0
            total_tire_capacity += capacity.get("tire_equivalent_capacity") or 0.0
            total_max_stops += capacity.get("max_stops") or 0

        load_lines = freight_service.get_load_lines_for_warehouse(
            warehouse_number, date_from=date_from, date_to=date_to,
        )
        total_weight_demand = sum(line.weight or 0.0 for line in load_lines.lines)
        total_quantity_demand = sum(line.quantity or 0.0 for line in load_lines.lines)
        route_count_with_activity = len(
            {line.route for line in load_lines.lines if line.route}
        )

        utilization_pct = (
            round(total_weight_demand / total_weight_capacity * 100, 1)
            if total_weight_capacity > 0
            else None
        )
        status = _classify_workload_status(
            utilization_pct, warning_pct=warning_pct, critical_pct=critical_pct
        )

        summaries.append(
            WarehouseWorkloadSummary(
                warehouse_number=warehouse_number,
                warehouse_location_name=warehouse_names.get(warehouse_number, ""),
                vehicle_count=len(vehicles),
                total_weight_capacity=total_weight_capacity,
                total_cube_capacity=total_cube_capacity,
                total_tire_capacity=total_tire_capacity,
                total_max_stops=total_max_stops,
                total_weight_demand=total_weight_demand,
                total_quantity_demand=total_quantity_demand,
                route_count_with_activity=route_count_with_activity,
                weight_utilization_pct=utilization_pct,
                status=status,
            )
        )

    return WorkloadSummaryResponse(
        generated_at=_now(),
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        warehouses=summaries,
    )


def compute_vehicle_performance(
    date_from: date, date_to: date
) -> RoutePerformanceResponse:
    """Actual per-vehicle Samsara trip performance for a date range - the
    honest read-only proxy for "route performance" since no MaddenCo
    route_code is linked to a vehicle anywhere in this schema (see the
    module README)."""

    vehicles_by_id = {
        vehicle["vehicle_id"]: vehicle for vehicle in repository.list_vehicles()
    }
    rows = repository.aggregate_actual_runs_by_vehicle(
        date_from=date_from.isoformat(), date_to=date_to.isoformat()
    )
    performance: list[VehicleRunPerformance] = []
    for row in rows:
        vehicle = vehicles_by_id.get(row["vehicle_id"])
        if vehicle is None:
            continue
        performance.append(
            VehicleRunPerformance(
                vehicle_id=vehicle["vehicle_id"],
                unit_number=vehicle["unit_number"],
                home_warehouse_number=vehicle.get("home_warehouse_number"),
                run_count=row["run_count"] or 0,
                total_distance_meters=row.get("total_distance_meters") or 0.0,
                average_distance_meters=row.get("average_distance_meters") or 0.0,
            )
        )
    performance.sort(key=lambda item: item.unit_number)
    return RoutePerformanceResponse(
        generated_at=_now(),
        date_from=date_from.isoformat(),
        date_to=date_to.isoformat(),
        vehicles=performance,
    )


def compute_data_quality_report(
    *,
    freight_service: FreightLogisticsService = freight_logistics_service,
    samsara: SamsaraProvider | None = None,
) -> DataQualityReport:
    """Live, always-fresh MaddenCo/Samsara-vs-ETOP-master-data consistency
    check - no stored snapshot, so there is no staleness to reason about.

    Checks route-code/store-number validity against freight_logistics's
    MaddenCo reads, ETOP's own master-data completeness (customer
    coordinates, vehicle capacities, driver availability), and (RI-1)
    which real Samsara vehicles/drivers haven't been imported yet plus any
    ingested trip that couldn't be linked to an imported vehicle/driver.

    `samsara` defaults to get_samsara_provider() (real API if configured)
    - tests should always pass a fake explicitly rather than relying on
    that default, since a real SAMSARA_API_TOKEN may legitimately be
    present in the environment (this repo's own .env has one).
    """

    customers = repository.list_customer_route_assignments()
    warehouses = freight_service.list_warehouses()
    valid_warehouse_numbers = {
        warehouse.warehouse_number for warehouse in warehouses.warehouses
    }
    routes = freight_service.search_routes(search="", active_only=True, limit=5000)
    valid_route_codes = {
        route.route_code for route in routes.routes if route.route_code
    }

    issues: list[DataQualityIssue] = []
    matched_route = 0
    matched_store = 0

    for customer in customers:
        customer_number = str(customer.get("CUNUMBER") or "").strip()
        customer_name = str(customer.get("CUNAME") or "").strip()
        route_code = str(customer.get("CUROUTECD") or "").strip()
        subject = f"{customer_number} ({customer_name})".strip()

        if route_code:
            if route_code in valid_route_codes:
                matched_route += 1
            else:
                issues.append(
                    DataQualityIssue(
                        category="customer_route_code_unmatched",
                        subject=subject,
                        message=(
                            f"Route code '{route_code}' does not match any "
                            "active MaddenCo route."
                        ),
                    )
                )

        store_number = customer.get("CUSTORENUM")
        try:
            store_number_int = int(store_number) if store_number is not None else None
        except (TypeError, ValueError):
            store_number_int = None
        if store_number_int is not None:
            if store_number_int in valid_warehouse_numbers:
                matched_store += 1
            else:
                issues.append(
                    DataQualityIssue(
                        category="customer_store_number_unmatched",
                        subject=subject,
                        message=(
                            f"Store number {store_number_int} does not "
                            "match any known warehouse."
                        ),
                    )
                )

    for profile in repository.list_customer_profiles():
        if profile.get("latitude") is None or profile.get("longitude") is None:
            issues.append(
                DataQualityIssue(
                    category="customer_profile_missing_coordinates",
                    subject=profile["customer_number"],
                    message="No latitude/longitude on file for this customer profile.",
                )
            )

    for vehicle in repository.list_vehicles():
        if not repository.list_vehicle_capacities(vehicle["vehicle_id"]):
            issues.append(
                DataQualityIssue(
                    category="vehicle_missing_capacity",
                    subject=vehicle["unit_number"],
                    message="This vehicle has no capacity profile on file.",
                )
            )

    for driver in repository.list_drivers():
        if not repository.list_driver_availability(driver["driver_id"]):
            issues.append(
                DataQualityIssue(
                    category="driver_missing_availability",
                    subject=driver["name"],
                    message="This driver has no availability schedule on file.",
                )
            )

    # Samsara-based checks are skipped (not failed) when Samsara isn't
    # connected, so a deployment without a token still gets the full
    # MaddenCo-side report rather than a 502 for the whole thing.
    try:
        provider = samsara or get_samsara_provider()
        samsara_vehicles = provider.list_vehicles()
        samsara_drivers = provider.list_drivers()
    except RuntimeError:
        samsara_vehicles = None
        samsara_drivers = None

    if samsara_vehicles is not None:
        imported_vehicle_ids = {
            vehicle["samsara_vehicle_id"]
            for vehicle in repository.list_vehicles()
            if vehicle.get("samsara_vehicle_id")
        }
        for vehicle in samsara_vehicles:
            samsara_id = str(vehicle.get("id") or "")
            if samsara_id and samsara_id not in imported_vehicle_ids:
                issues.append(
                    DataQualityIssue(
                        category="samsara_vehicle_not_imported",
                        subject=str(vehicle.get("name") or samsara_id),
                        message="This Samsara vehicle has not been imported yet.",
                    )
                )

    if samsara_drivers is not None:
        imported_driver_ids = {
            driver["samsara_driver_id"]
            for driver in repository.list_drivers()
            if driver.get("samsara_driver_id")
        }
        for driver in samsara_drivers:
            samsara_id = str(driver.get("id") or "")
            if samsara_id and samsara_id not in imported_driver_ids:
                issues.append(
                    DataQualityIssue(
                        category="samsara_driver_not_imported",
                        subject=str(driver.get("name") or samsara_id),
                        message="This Samsara driver has not been imported yet.",
                    )
                )

    unresolved_run_count = repository.count_actual_runs_with_unresolved_links()
    if unresolved_run_count:
        issues.append(
            DataQualityIssue(
                category="actual_run_unresolved_link",
                subject=f"{unresolved_run_count} ingested trip(s)",
                message=(
                    "These ingested Samsara trips reference a vehicle that "
                    "hasn't been imported yet - import vehicles from "
                    "Samsara, then re-sync to resolve them."
                ),
            )
        )

    customers_checked = len(customers)
    return DataQualityReport(
        generated_at=_now(),
        customers_checked=customers_checked,
        matched_route_code_count=matched_route,
        matched_store_number_count=matched_store,
        route_code_match_rate=(
            round(matched_route / customers_checked, 4) if customers_checked else 0.0
        ),
        store_number_match_rate=(
            round(matched_store / customers_checked, 4) if customers_checked else 0.0
        ),
        total_issue_count=len(issues),
        issues=issues[:MAX_REPORTED_ISSUES],
    )
