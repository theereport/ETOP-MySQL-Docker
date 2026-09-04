export type WeekdayName =
  | 'Sunday'
  | 'Monday'
  | 'Tuesday'
  | 'Wednesday'
  | 'Thursday'
  | 'Friday'
  | 'Saturday'

// --- warehouses & routes (read-only, from freight_logistics) --------------

export interface WarehouseSummary {
  warehouse_number: number
  warehouse_location_name: string
}

export interface WarehouseListResponse {
  count: number
  warehouses: WarehouseSummary[]
}

export interface RouteSummary {
  route_key: string
  route_code: string
  warehouse_number: number | null
  status_code: string
  active: boolean
}

export interface WarehouseRouteListResponse {
  warehouse_number: number
  count: number
  routes: RouteSummary[]
}

// --- customer profiles ---------------------------------------------------

export interface CustomerProfile {
  customer_number: string
  latitude: number | null
  longitude: number | null
  receiving_window_start: string
  receiving_window_end: string
  closed_days: string[]
  preferred_delivery_days: string[]
  priority: string
  normal_unloading_minutes: number | null
  vehicle_access_restrictions: string
  delivery_instructions: string
  notes: string
  updated_at: string
  updated_by: string
  samsara_address_id: string | null
}

export interface CustomerProfileListResponse {
  count: number
  profiles: CustomerProfile[]
}

export interface SaveCustomerProfileRequest {
  latitude?: number | null
  longitude?: number | null
  receiving_window_start?: string
  receiving_window_end?: string
  closed_days?: string[]
  preferred_delivery_days?: string[]
  priority?: string
  normal_unloading_minutes?: number | null
  vehicle_access_restrictions?: string
  delivery_instructions?: string
  notes?: string
  updated_by?: string
}

// --- vehicles / capacities -------------------------------------------------

export interface VehicleCapacity {
  capacity_id: number
  vehicle_id: number
  weight_capacity: number | null
  cube_capacity: number | null
  tire_equivalent_capacity: number | null
  max_stops: number | null
  effective_date: string
}

export interface Vehicle {
  vehicle_id: number
  unit_number: string
  vehicle_type: string
  home_warehouse_number: number | null
  active: boolean
  notes: string
  updated_at: string
  vin: string | null
  samsara_vehicle_id: string | null
  capacities: VehicleCapacity[]
}

export interface VehicleListResponse {
  count: number
  vehicles: Vehicle[]
}

export interface CreateVehicleRequest {
  unit_number: string
  vehicle_type?: string
  home_warehouse_number?: number | null
  active?: boolean
  notes?: string
}

export interface AddVehicleCapacityRequest {
  weight_capacity?: number | null
  cube_capacity?: number | null
  tire_equivalent_capacity?: number | null
  max_stops?: number | null
  effective_date?: string
}

// --- drivers / availability -------------------------------------------------

export interface DriverAvailability {
  availability_id: number
  driver_id: number
  day_of_week: WeekdayName
  available: boolean
  shift_start: string
  shift_end: string
}

export interface Driver {
  driver_id: number
  name: string
  home_warehouse_number: number | null
  active: boolean
  qualifications: string
  notes: string
  updated_at: string
  samsara_driver_id: string | null
  availability: DriverAvailability[]
}

export interface DriverListResponse {
  count: number
  drivers: Driver[]
}

export interface CreateDriverRequest {
  name: string
  home_warehouse_number?: number | null
  active?: boolean
  qualifications?: string
  notes?: string
}

export interface SetDriverAvailabilityRequest {
  day_of_week: WeekdayName
  available?: boolean
  shift_start?: string
  shift_end?: string
}

// --- business rules ---------------------------------------------------

export interface BusinessRule {
  rule_key: string
  rule_value: string
  description: string
  updated_at: string
  updated_by: string
}

export interface BusinessRuleListResponse {
  count: number
  rules: BusinessRule[]
}

export interface SaveBusinessRuleRequest {
  rule_value: string
  description?: string
  updated_by?: string
}

// --- Samsara import / linking / historical sync ---------------------------

export interface SamsaraImportResult {
  samsara_count: number
  created_count: number
  updated_count: number
}

export interface SamsaraAddress {
  id: string
  name: string
  formatted_address: string
  latitude: number | null
  longitude: number | null
}

export interface SamsaraAddressSearchResponse {
  count: number
  addresses: SamsaraAddress[]
}

export interface LinkCustomerSamsaraAddressRequest {
  samsara_address_id: string | null
}

export interface ActualRun {
  run_id: number
  samsara_trip_id: string
  vehicle_id: number | null
  driver_id: number | null
  start_time: string | null
  end_time: string | null
  start_latitude: number | null
  start_longitude: number | null
  end_latitude: number | null
  end_longitude: number | null
  distance_meters: number | null
  completion_status: string
  ingested_at: string
}

export interface ActualRunListResponse {
  count: number
  runs: ActualRun[]
}

export interface SyncState {
  sync_key: string
  last_synced_through: string | null
  last_run_at: string | null
  last_run_status: string
  last_run_message: string
}

export interface SyncSamsaraTripsRequest {
  date_from: string
  date_to: string
}

export interface SyncSamsaraTripsResult {
  trip_count: number
  resolved_count: number
  unresolved_count: number
  sync_state: SyncState
}

// --- workload / capacity dashboard (RI-2, read-only) -----------------------

export type WorkloadStatus = 'ok' | 'warning' | 'critical' | 'unknown'

export interface WarehouseWorkloadSummary {
  warehouse_number: number
  warehouse_location_name: string
  vehicle_count: number
  total_weight_capacity: number
  total_cube_capacity: number
  total_tire_capacity: number
  total_max_stops: number
  total_weight_demand: number
  total_quantity_demand: number
  route_count_with_activity: number
  weight_utilization_pct: number | null
  status: WorkloadStatus
}

export interface WorkloadSummaryResponse {
  generated_at: string
  date_from: string
  date_to: string
  warehouses: WarehouseWorkloadSummary[]
}

export interface VehicleRunPerformance {
  vehicle_id: number
  unit_number: string
  home_warehouse_number: number | null
  run_count: number
  total_distance_meters: number
  average_distance_meters: number
}

export interface RoutePerformanceResponse {
  generated_at: string
  date_from: string
  date_to: string
  vehicles: VehicleRunPerformance[]
}

// --- data quality ----------------------------------------------------------

export interface DataQualityIssue {
  category:
    | 'customer_route_code_unmatched'
    | 'customer_store_number_unmatched'
    | 'customer_profile_missing_coordinates'
    | 'vehicle_missing_capacity'
    | 'driver_missing_availability'
    | 'samsara_vehicle_not_imported'
    | 'samsara_driver_not_imported'
    | 'actual_run_unresolved_link'
  subject: string
  message: string
}

export interface DataQualityReport {
  generated_at: string
  customers_checked: number
  matched_route_code_count: number
  matched_store_number_count: number
  route_code_match_rate: number
  store_number_match_rate: number
  total_issue_count: number
  issues: DataQualityIssue[]
}
