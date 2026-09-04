from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

from modules.freight_logistics.service import (
    FreightLogisticsService,
    freight_logistics_service,
)

from . import repository
from .schemas import (
    BusinessRule,
    CustomerProfile,
    DataQualityIssue,
    DataQualityReport,
    Driver,
    DriverAvailability,
    Vehicle,
    VehicleCapacity,
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


# --- data quality ----------------------------------------------------------

def compute_data_quality_report(
    *,
    freight_service: FreightLogisticsService = freight_logistics_service,
) -> DataQualityReport:
    """Live, always-fresh MaddenCo-vs-ETOP-master-data consistency check -
    no stored snapshot, so there is no staleness to reason about.

    Deliberately scoped to what's checkable WITHOUT Samsara: route-code and
    store-number validity against freight_logistics's MaddenCo reads, and
    ETOP's own master-data completeness (customer coordinates, vehicle
    capacities, driver availability). "Samsara/MaddenCo mapping failures"
    from the program plan's Data Quality Center section is intentionally
    absent here - there is nothing to map yet.
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
