import { requestJson } from '../../api/client'
import type {
  AddVehicleCapacityRequest,
  BusinessRuleListResponse,
  CreateDriverRequest,
  CreateVehicleRequest,
  CustomerProfile,
  CustomerProfileListResponse,
  DataQualityReport,
  Driver,
  DriverListResponse,
  SaveBusinessRuleRequest,
  SaveCustomerProfileRequest,
  SetDriverAvailabilityRequest,
  Vehicle,
  VehicleListResponse,
  WarehouseListResponse,
  WarehouseRouteListResponse,
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
