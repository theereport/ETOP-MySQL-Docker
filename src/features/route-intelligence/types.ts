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

// --- data quality ----------------------------------------------------------

export interface DataQualityIssue {
  category:
    | 'customer_route_code_unmatched'
    | 'customer_store_number_unmatched'
    | 'customer_profile_missing_coordinates'
    | 'vehicle_missing_capacity'
    | 'driver_missing_availability'
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
