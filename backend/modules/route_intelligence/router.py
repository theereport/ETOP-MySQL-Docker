from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from modules.freight_logistics.schemas import (
    WarehouseListResponse,
    WarehouseRouteListResponse,
)
from modules.freight_logistics.service import freight_logistics_service

from . import service
from .schemas import (
    ActualRunListResponse,
    AddVehicleCapacityRequest,
    BusinessRule,
    BusinessRuleListResponse,
    CreateDriverRequest,
    CreateVehicleRequest,
    CustomerProfile,
    CustomerProfileListResponse,
    DataQualityReport,
    Driver,
    DriverListResponse,
    LinkCustomerSamsaraAddressRequest,
    SamsaraAddressSearchResponse,
    SamsaraImportResult,
    SaveBusinessRuleRequest,
    SaveCustomerProfileRequest,
    SetDriverAvailabilityRequest,
    SyncSamsaraTripsRequest,
    SyncSamsaraTripsResult,
    UpdateDriverRequest,
    UpdateVehicleRequest,
    Vehicle,
    VehicleListResponse,
)

router = APIRouter(
    prefix="/api/v1/route-intelligence",
    tags=["Route Intelligence"],
)


@router.get("/health")
def get_health() -> dict:
    return {"status": "ok", "module": "route_intelligence"}


# --- warehouses & routes (read-only passthrough to freight_logistics) -----

@router.get("/warehouses", response_model=WarehouseListResponse)
def list_warehouses() -> WarehouseListResponse:
    return freight_logistics_service.list_warehouses()


@router.get(
    "/warehouses/{warehouse_number}/routes",
    response_model=WarehouseRouteListResponse,
)
def list_routes_for_warehouse(
    warehouse_number: int,
    active_only: bool = Query(default=True),
) -> WarehouseRouteListResponse:
    return freight_logistics_service.list_routes_for_warehouse(
        warehouse_number, active_only=active_only,
    )


# --- customer profiles ---------------------------------------------------

@router.get("/customer-profiles", response_model=CustomerProfileListResponse)
def list_customer_profiles() -> CustomerProfileListResponse:
    profiles = service.list_customer_profiles()
    return CustomerProfileListResponse(count=len(profiles), profiles=profiles)


@router.get(
    "/customer-profiles/{customer_number}",
    response_model=CustomerProfile,
)
def get_customer_profile(customer_number: str) -> CustomerProfile:
    return service.get_customer_profile(customer_number)


@router.put(
    "/customer-profiles/{customer_number}",
    response_model=CustomerProfile,
)
def save_customer_profile(
    customer_number: str,
    payload: SaveCustomerProfileRequest,
) -> CustomerProfile:
    return service.save_customer_profile(customer_number, payload.model_dump())


@router.put(
    "/customer-profiles/{customer_number}/samsara-address",
    response_model=CustomerProfile,
)
def link_customer_samsara_address(
    customer_number: str,
    payload: LinkCustomerSamsaraAddressRequest,
) -> CustomerProfile:
    return service.link_customer_samsara_address(
        customer_number, payload.samsara_address_id
    )


# --- vehicles / capacities -----------------------------------------------

@router.get("/vehicles", response_model=VehicleListResponse)
def list_vehicles() -> VehicleListResponse:
    vehicles = service.list_vehicles()
    return VehicleListResponse(count=len(vehicles), vehicles=vehicles)


@router.post("/vehicles", response_model=Vehicle, status_code=201)
def create_vehicle(payload: CreateVehicleRequest) -> Vehicle:
    return service.create_vehicle(payload.model_dump())


@router.put("/vehicles/{vehicle_id}", response_model=Vehicle)
def update_vehicle(vehicle_id: int, payload: UpdateVehicleRequest) -> Vehicle:
    return service.update_vehicle(vehicle_id, payload.model_dump())


@router.post(
    "/vehicles/{vehicle_id}/capacities",
    response_model=Vehicle,
    status_code=201,
)
def add_vehicle_capacity(
    vehicle_id: int,
    payload: AddVehicleCapacityRequest,
) -> Vehicle:
    return service.add_vehicle_capacity(vehicle_id, payload.model_dump())


# --- drivers / availability -----------------------------------------------

@router.get("/drivers", response_model=DriverListResponse)
def list_drivers() -> DriverListResponse:
    drivers = service.list_drivers()
    return DriverListResponse(count=len(drivers), drivers=drivers)


@router.post("/drivers", response_model=Driver, status_code=201)
def create_driver(payload: CreateDriverRequest) -> Driver:
    return service.create_driver(payload.model_dump())


@router.put("/drivers/{driver_id}", response_model=Driver)
def update_driver(driver_id: int, payload: UpdateDriverRequest) -> Driver:
    return service.update_driver(driver_id, payload.model_dump())


@router.put(
    "/drivers/{driver_id}/availability",
    response_model=Driver,
)
def set_driver_availability(
    driver_id: int,
    payload: SetDriverAvailabilityRequest,
) -> Driver:
    return service.set_driver_availability(driver_id, payload.model_dump())


# --- business rules ---------------------------------------------------

@router.get("/business-rules", response_model=BusinessRuleListResponse)
def list_business_rules() -> BusinessRuleListResponse:
    rules = service.list_business_rules()
    return BusinessRuleListResponse(count=len(rules), rules=rules)


@router.put("/business-rules/{rule_key}", response_model=BusinessRule)
def save_business_rule(
    rule_key: str, payload: SaveBusinessRuleRequest
) -> BusinessRule:
    return service.save_business_rule(rule_key, payload.model_dump())


# --- Samsara (read-only) ---------------------------------------------

@router.get("/samsara/vehicles")
def list_samsara_vehicles() -> dict:
    return {"vehicles": service.list_samsara_vehicles()}


@router.get("/samsara/drivers")
def list_samsara_drivers() -> dict:
    return {"drivers": service.list_samsara_drivers()}


@router.get("/samsara/driver-vehicle-assignments")
def list_samsara_driver_vehicle_assignments() -> dict:
    return {"assignments": service.list_samsara_driver_vehicle_assignments()}


@router.get("/samsara/customer-geofence/{customer_number}")
def get_samsara_customer_geofence(customer_number: str) -> dict:
    return {"geofence": service.get_samsara_customer_geofence(customer_number)}


@router.get("/samsara/vehicles/{vehicle_id}/live-gps")
def get_samsara_live_gps(vehicle_id: str) -> dict:
    return {"location": service.get_samsara_live_gps(vehicle_id)}


@router.post("/samsara/import/vehicles", response_model=SamsaraImportResult)
def import_samsara_vehicles() -> SamsaraImportResult:
    return service.import_samsara_vehicles()


@router.post("/samsara/import/drivers", response_model=SamsaraImportResult)
def import_samsara_drivers() -> SamsaraImportResult:
    return service.import_samsara_drivers()


@router.get(
    "/samsara/addresses/search",
    response_model=SamsaraAddressSearchResponse,
)
def search_samsara_addresses(
    q: str = Query(default="", max_length=100),
) -> SamsaraAddressSearchResponse:
    addresses = service.search_samsara_addresses(q)
    return SamsaraAddressSearchResponse(count=len(addresses), addresses=addresses)


@router.post("/samsara/sync-trips", response_model=SyncSamsaraTripsResult)
def sync_samsara_trips(payload: SyncSamsaraTripsRequest) -> SyncSamsaraTripsResult:
    date_from = date.fromisoformat(payload.date_from)
    date_to = date.fromisoformat(payload.date_to)
    runs, sync_state = service.sync_samsara_trips(date_from, date_to)
    resolved = sum(1 for run in runs if run.vehicle_id is not None)
    return SyncSamsaraTripsResult(
        trip_count=len(runs),
        resolved_count=resolved,
        unresolved_count=len(runs) - resolved,
        sync_state=sync_state,
    )


@router.get("/actual-runs", response_model=ActualRunListResponse)
def list_actual_runs(
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
) -> ActualRunListResponse:
    runs = service.list_actual_runs(date_from=date_from, date_to=date_to)
    return ActualRunListResponse(count=len(runs), runs=runs)


# --- data quality ----------------------------------------------------------

@router.get("/data-quality", response_model=DataQualityReport)
def get_data_quality_report() -> DataQualityReport:
    return service.compute_data_quality_report()
