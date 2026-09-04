from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


WEEKDAY = Literal[
    "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"
]


# --- customer profiles ---------------------------------------------------

class CustomerProfile(BaseModel):
    customer_number: str
    latitude: float | None = None
    longitude: float | None = None
    receiving_window_start: str = ""
    receiving_window_end: str = ""
    closed_days: list[str] = Field(default_factory=list)
    preferred_delivery_days: list[str] = Field(default_factory=list)
    priority: str = ""
    normal_unloading_minutes: float | None = None
    vehicle_access_restrictions: str = ""
    delivery_instructions: str = ""
    notes: str = ""
    updated_at: str = ""
    updated_by: str = ""
    samsara_address_id: str | None = None


class SaveCustomerProfileRequest(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    receiving_window_start: str = Field(default="", max_length=16)
    receiving_window_end: str = Field(default="", max_length=16)
    closed_days: list[str] = Field(default_factory=list)
    preferred_delivery_days: list[str] = Field(default_factory=list)
    priority: str = Field(default="", max_length=32)
    normal_unloading_minutes: float | None = None
    vehicle_access_restrictions: str = Field(default="", max_length=2000)
    delivery_instructions: str = Field(default="", max_length=2000)
    notes: str = Field(default="", max_length=2000)
    updated_by: str = Field(default="", max_length=200)


class CustomerProfileListResponse(BaseModel):
    count: int
    profiles: list[CustomerProfile]


# --- vehicles / capacities ------------------------------------------------

class VehicleCapacity(BaseModel):
    capacity_id: int
    vehicle_id: int
    weight_capacity: float | None = None
    cube_capacity: float | None = None
    tire_equivalent_capacity: float | None = None
    max_stops: int | None = None
    effective_date: str = ""


class AddVehicleCapacityRequest(BaseModel):
    weight_capacity: float | None = None
    cube_capacity: float | None = None
    tire_equivalent_capacity: float | None = None
    max_stops: int | None = Field(default=None, ge=0)
    effective_date: str = Field(default="", max_length=32)


class Vehicle(BaseModel):
    vehicle_id: int
    unit_number: str
    vehicle_type: str = ""
    home_warehouse_number: int | None = None
    active: bool = True
    notes: str = ""
    updated_at: str = ""
    vin: str | None = None
    samsara_vehicle_id: str | None = None
    capacities: list[VehicleCapacity] = Field(default_factory=list)


class CreateVehicleRequest(BaseModel):
    unit_number: str = Field(min_length=1, max_length=64)
    vehicle_type: str = Field(default="", max_length=64)
    home_warehouse_number: int | None = None
    active: bool = True
    notes: str = Field(default="", max_length=2000)


class UpdateVehicleRequest(CreateVehicleRequest):
    pass


class VehicleListResponse(BaseModel):
    count: int
    vehicles: list[Vehicle]


# --- drivers / availability ------------------------------------------------

class DriverAvailability(BaseModel):
    availability_id: int
    driver_id: int
    day_of_week: WEEKDAY
    available: bool = True
    shift_start: str = ""
    shift_end: str = ""


class SetDriverAvailabilityRequest(BaseModel):
    day_of_week: WEEKDAY
    available: bool = True
    shift_start: str = Field(default="", max_length=16)
    shift_end: str = Field(default="", max_length=16)


class Driver(BaseModel):
    driver_id: int
    name: str
    home_warehouse_number: int | None = None
    active: bool = True
    qualifications: str = ""
    notes: str = ""
    updated_at: str = ""
    samsara_driver_id: str | None = None
    availability: list[DriverAvailability] = Field(default_factory=list)


class CreateDriverRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    home_warehouse_number: int | None = None
    active: bool = True
    qualifications: str = Field(default="", max_length=2000)
    notes: str = Field(default="", max_length=2000)


class UpdateDriverRequest(CreateDriverRequest):
    pass


class DriverListResponse(BaseModel):
    count: int
    drivers: list[Driver]


# --- business rules ---------------------------------------------------

class BusinessRule(BaseModel):
    rule_key: str
    rule_value: str
    description: str = ""
    updated_at: str = ""
    updated_by: str = ""


class SaveBusinessRuleRequest(BaseModel):
    rule_value: str = Field(min_length=1, max_length=4000)
    description: str = Field(default="", max_length=2000)
    updated_by: str = Field(default="", max_length=200)


class BusinessRuleListResponse(BaseModel):
    count: int
    rules: list[BusinessRule]


# --- Samsara import / linking / historical sync --------------------------

class SamsaraImportResult(BaseModel):
    samsara_count: int
    created_count: int
    updated_count: int


class SamsaraAddress(BaseModel):
    id: str
    name: str = ""
    formatted_address: str = ""
    latitude: float | None = None
    longitude: float | None = None


class SamsaraAddressSearchResponse(BaseModel):
    count: int
    addresses: list[SamsaraAddress]


class LinkCustomerSamsaraAddressRequest(BaseModel):
    samsara_address_id: str | None = Field(default=None, max_length=64)


class ActualRun(BaseModel):
    run_id: int
    samsara_trip_id: str
    vehicle_id: int | None = None
    driver_id: int | None = None
    start_time: str | None = None
    end_time: str | None = None
    start_latitude: float | None = None
    start_longitude: float | None = None
    end_latitude: float | None = None
    end_longitude: float | None = None
    distance_meters: float | None = None
    completion_status: str = ""
    ingested_at: str = ""


class ActualRunListResponse(BaseModel):
    count: int
    runs: list[ActualRun]


class SyncSamsaraTripsRequest(BaseModel):
    date_from: str
    date_to: str


class SyncSamsaraTripsResult(BaseModel):
    trip_count: int
    resolved_count: int
    unresolved_count: int
    sync_state: "SyncState"


class SyncState(BaseModel):
    sync_key: str
    last_synced_through: str | None = None
    last_run_at: str | None = None
    last_run_status: str = ""
    last_run_message: str = ""


# --- workload / capacity dashboard (RI-2, read-only) ----------------------

class WarehouseWorkloadSummary(BaseModel):
    warehouse_number: int
    warehouse_location_name: str = ""
    vehicle_count: int
    total_weight_capacity: float
    total_cube_capacity: float
    total_tire_capacity: float
    total_max_stops: int
    total_weight_demand: float
    total_quantity_demand: float
    route_count_with_activity: int
    weight_utilization_pct: float | None = None
    status: Literal["ok", "warning", "critical", "unknown"]


class WorkloadSummaryResponse(BaseModel):
    generated_at: str
    date_from: str
    date_to: str
    warehouses: list[WarehouseWorkloadSummary]


class VehicleRunPerformance(BaseModel):
    vehicle_id: int
    unit_number: str
    home_warehouse_number: int | None = None
    run_count: int
    total_distance_meters: float
    average_distance_meters: float


class RoutePerformanceResponse(BaseModel):
    generated_at: str
    date_from: str
    date_to: str
    vehicles: list[VehicleRunPerformance]


# --- data quality --------------------------------------------------------

class DataQualityIssue(BaseModel):
    category: Literal[
        "customer_route_code_unmatched",
        "customer_store_number_unmatched",
        "customer_profile_missing_coordinates",
        "vehicle_missing_capacity",
        "driver_missing_availability",
        "samsara_vehicle_not_imported",
        "samsara_driver_not_imported",
        "actual_run_unresolved_link",
    ]
    subject: str
    message: str


class DataQualityReport(BaseModel):
    generated_at: str
    customers_checked: int
    matched_route_code_count: int
    matched_store_number_count: int
    route_code_match_rate: float
    store_number_match_rate: float
    total_issue_count: int
    issues: list[DataQualityIssue]
