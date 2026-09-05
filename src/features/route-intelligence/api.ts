import { requestJson } from '../../api/client'
import type {
  ActualRunListResponse,
  AddVehicleCapacityRequest,
  BusinessRuleListResponse,
  CapacityForecastListResponse,
  ComputeForecastRequest,
  ComputeOptimizationRequest,
  CreateDriverRequest,
  CreateVehicleRequest,
  CustomerProfile,
  CustomerProfileListResponse,
  DataQualityReport,
  Driver,
  DriverListResponse,
  ForecastRunStatus,
  LinkCustomerSamsaraAddressRequest,
  OptimizationReadiness,
  OptimizationRunStatus,
  RoutePerformanceResponse,
  SamsaraAddressSearchResponse,
  SamsaraImportResult,
  SaveBusinessRuleRequest,
  SaveCustomerProfileRequest,
  SaveWarehouseLocationRequest,
  SetDriverAvailabilityRequest,
  SyncSamsaraTripsRequest,
  SyncSamsaraTripsResult,
  Vehicle,
  VehicleListResponse,
  WarehouseListResponse,
  WarehouseLocationListResponse,
  WarehouseRouteListResponse,
  WorkloadSummaryResponse,
} from './types'

const BASE = '/route-intelligence'

export function getDataQualityReport(signal?: AbortSignal): Promise<DataQualityReport> {
  return requestJson<DataQualityReport>(`${BASE}/data-quality`, { signal })
}

export function listWarehouses(signal?: AbortSignal): Promise<WarehouseListResponse> {
  return requestJson<WarehouseListResponse>(`${BASE}/warehouses`, { signal })
}

export function listRoutesForWarehouse(
  warehouseNumber: number,
  signal?: AbortSignal,
): Promise<WarehouseRouteListResponse> {
  return requestJson<WarehouseRouteListResponse>(
    `${BASE}/warehouses/${warehouseNumber}/routes`,
    { signal },
  )
}

export function listCustomerProfiles(
  signal?: AbortSignal,
): Promise<CustomerProfileListResponse> {
  return requestJson<CustomerProfileListResponse>(`${BASE}/customer-profiles`, { signal })
}

export function getCustomerProfile(
  customerNumber: string,
  signal?: AbortSignal,
): Promise<CustomerProfile> {
  return requestJson<CustomerProfile>(
    `${BASE}/customer-profiles/${encodeURIComponent(customerNumber)}`,
    { signal },
  )
}

export function saveCustomerProfile(
  customerNumber: string,
  payload: SaveCustomerProfileRequest,
  signal?: AbortSignal,
): Promise<CustomerProfile> {
  return requestJson<CustomerProfile>(
    `${BASE}/customer-profiles/${encodeURIComponent(customerNumber)}`,
    { method: 'PUT', body: payload, signal },
  )
}

export function listVehicles(signal?: AbortSignal): Promise<VehicleListResponse> {
  return requestJson<VehicleListResponse>(`${BASE}/vehicles`, { signal })
}

export function createVehicle(
  payload: CreateVehicleRequest,
  signal?: AbortSignal,
): Promise<Vehicle> {
  return requestJson<Vehicle>(`${BASE}/vehicles`, {
    method: 'POST', body: payload, signal,
  })
}

export function updateVehicle(
  vehicleId: number,
  payload: CreateVehicleRequest,
  signal?: AbortSignal,
): Promise<Vehicle> {
  return requestJson<Vehicle>(`${BASE}/vehicles/${vehicleId}`, {
    method: 'PUT', body: payload, signal,
  })
}

export function addVehicleCapacity(
  vehicleId: number,
  payload: AddVehicleCapacityRequest,
  signal?: AbortSignal,
): Promise<Vehicle> {
  return requestJson<Vehicle>(`${BASE}/vehicles/${vehicleId}/capacities`, {
    method: 'POST', body: payload, signal,
  })
}

export function listDrivers(signal?: AbortSignal): Promise<DriverListResponse> {
  return requestJson<DriverListResponse>(`${BASE}/drivers`, { signal })
}

export function createDriver(
  payload: CreateDriverRequest,
  signal?: AbortSignal,
): Promise<Driver> {
  return requestJson<Driver>(`${BASE}/drivers`, {
    method: 'POST', body: payload, signal,
  })
}

export function updateDriver(
  driverId: number,
  payload: CreateDriverRequest,
  signal?: AbortSignal,
): Promise<Driver> {
  return requestJson<Driver>(`${BASE}/drivers/${driverId}`, {
    method: 'PUT', body: payload, signal,
  })
}

export function setDriverAvailability(
  driverId: number,
  payload: SetDriverAvailabilityRequest,
  signal?: AbortSignal,
): Promise<Driver> {
  return requestJson<Driver>(`${BASE}/drivers/${driverId}/availability`, {
    method: 'PUT', body: payload, signal,
  })
}

export function listBusinessRules(
  signal?: AbortSignal,
): Promise<BusinessRuleListResponse> {
  return requestJson<BusinessRuleListResponse>(`${BASE}/business-rules`, { signal })
}

export function saveBusinessRule(
  ruleKey: string,
  payload: SaveBusinessRuleRequest,
  signal?: AbortSignal,
) {
  return requestJson(`${BASE}/business-rules/${encodeURIComponent(ruleKey)}`, {
    method: 'PUT', body: payload, signal,
  })
}

export function importSamsaraVehicles(signal?: AbortSignal): Promise<SamsaraImportResult> {
  return requestJson<SamsaraImportResult>(`${BASE}/samsara/import/vehicles`, {
    method: 'POST', signal,
  })
}

export function importSamsaraDrivers(signal?: AbortSignal): Promise<SamsaraImportResult> {
  return requestJson<SamsaraImportResult>(`${BASE}/samsara/import/drivers`, {
    method: 'POST', signal,
  })
}

export function searchSamsaraAddresses(
  query: string,
  signal?: AbortSignal,
): Promise<SamsaraAddressSearchResponse> {
  const params = new URLSearchParams()
  if (query.trim()) params.set('q', query.trim())
  return requestJson<SamsaraAddressSearchResponse>(
    `${BASE}/samsara/addresses/search?${params.toString()}`,
    { signal },
  )
}

export function linkCustomerSamsaraAddress(
  customerNumber: string,
  payload: LinkCustomerSamsaraAddressRequest,
  signal?: AbortSignal,
): Promise<CustomerProfile> {
  return requestJson<CustomerProfile>(
    `${BASE}/customer-profiles/${encodeURIComponent(customerNumber)}/samsara-address`,
    { method: 'PUT', body: payload, signal },
  )
}

export function syncSamsaraTrips(
  payload: SyncSamsaraTripsRequest,
  signal?: AbortSignal,
): Promise<SyncSamsaraTripsResult> {
  return requestJson<SyncSamsaraTripsResult>(`${BASE}/samsara/sync-trips`, {
    method: 'POST', body: payload, signal,
  })
}

export function listActualRuns(
  params: { dateFrom?: string; dateTo?: string } = {},
  signal?: AbortSignal,
): Promise<ActualRunListResponse> {
  const search = new URLSearchParams()
  if (params.dateFrom) search.set('date_from', params.dateFrom)
  if (params.dateTo) search.set('date_to', params.dateTo)
  const query = search.toString()
  return requestJson<ActualRunListResponse>(
    `${BASE}/actual-runs${query ? `?${query}` : ''}`,
    { signal },
  )
}

export function getWorkloadSummary(
  params: { dateFrom: string; dateTo: string },
  signal?: AbortSignal,
): Promise<WorkloadSummaryResponse> {
  const search = new URLSearchParams()
  search.set('date_from', params.dateFrom)
  search.set('date_to', params.dateTo)
  return requestJson<WorkloadSummaryResponse>(
    `${BASE}/workload-summary?${search.toString()}`,
    { signal },
  )
}

export function getVehiclePerformance(
  params: { dateFrom: string; dateTo: string },
  signal?: AbortSignal,
): Promise<RoutePerformanceResponse> {
  const search = new URLSearchParams()
  search.set('date_from', params.dateFrom)
  search.set('date_to', params.dateTo)
  return requestJson<RoutePerformanceResponse>(
    `${BASE}/vehicle-performance?${search.toString()}`,
    { signal },
  )
}

export function computeCapacityForecast(
  payload: ComputeForecastRequest,
  signal?: AbortSignal,
): Promise<ForecastRunStatus> {
  return requestJson<ForecastRunStatus>(`${BASE}/forecast/compute`, {
    method: 'POST', body: payload, signal,
  })
}

export function listCapacityForecasts(
  signal?: AbortSignal,
): Promise<CapacityForecastListResponse> {
  return requestJson<CapacityForecastListResponse>(
    `${BASE}/forecast/capacity-assessments`,
    { signal },
  )
}

export function getForecastRunStatus(signal?: AbortSignal): Promise<ForecastRunStatus> {
  return requestJson<ForecastRunStatus>(`${BASE}/forecast/status`, { signal })
}

export function listWarehouseLocations(
  signal?: AbortSignal,
): Promise<WarehouseLocationListResponse> {
  return requestJson<WarehouseLocationListResponse>(
    `${BASE}/warehouse-locations`,
    { signal },
  )
}

export function saveWarehouseLocation(
  warehouseNumber: number,
  payload: SaveWarehouseLocationRequest,
  signal?: AbortSignal,
) {
  return requestJson(
    `${BASE}/warehouse-locations/${warehouseNumber}`,
    { method: 'PUT', body: payload, signal },
  )
}

export function getOptimizationReadiness(
  warehouseNumber: number,
  signal?: AbortSignal,
): Promise<OptimizationReadiness> {
  return requestJson<OptimizationReadiness>(
    `${BASE}/optimize/readiness/${warehouseNumber}`,
    { signal },
  )
}

export function computeRouteOptimization(
  payload: ComputeOptimizationRequest,
  signal?: AbortSignal,
): Promise<OptimizationRunStatus> {
  return requestJson<OptimizationRunStatus>(`${BASE}/optimize/compute`, {
    method: 'POST', body: payload, signal,
  })
}

export function getOptimizationRun(
  runId: number,
  signal?: AbortSignal,
): Promise<OptimizationRunStatus> {
  return requestJson<OptimizationRunStatus>(`${BASE}/optimize/runs/${runId}`, { signal })
}
