import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  addVehicleCapacity,
  computeCapacityForecast,
  computeRouteOptimization,
  createDriver,
  createVehicle,
  getCustomerProfile,
  getDataQualityReport,
  getForecastRunStatus,
  getOptimizationReadiness,
  getVehiclePerformance,
  getWorkloadSummary,
  importSamsaraDrivers,
  importSamsaraVehicles,
  linkCustomerSamsaraAddress,
  listActualRuns,
  listBusinessRules,
  listCapacityForecasts,
  listCustomerProfiles,
  listDrivers,
  listOptimizationDecisions,
  listRoutesForWarehouse,
  listVehicles,
  listWarehouses,
  recordOptimizationDecision,
  saveBusinessRule,
  saveCustomerProfile,
  saveWarehouseLocation,
  searchSamsaraAddresses,
  setDriverAvailability,
  syncSamsaraTrips,
} from './api'
import type {
  ActualRun,
  BusinessRule,
  CapacityAssessment,
  CustomerProfile,
  DataQualityReport,
  Driver,
  ForecastStatus,
  OptimizationPlan,
  OptimizationReadiness,
  OptimizationRunStatus,
  PlanDecision,
  RouteSummary,
  RunDecisionRecord,
  SamsaraAddress,
  Vehicle,
  VehicleRunPerformance,
  WarehouseSummary,
  WarehouseWorkloadSummary,
  WeekdayName,
  WorkloadStatus,
} from './types'
import './RouteIntelligenceWorkspace.css'

type Tab =
  | 'data-quality'
  | 'warehouses'
  | 'vehicles'
  | 'drivers'
  | 'customer-profiles'
  | 'trip-history'
  | 'capacity-performance'
  | 'capacity-forecast'
  | 'route-optimizer'
  | 'business-rules'

const TABS: { id: Tab; label: string }[] = [
  { id: 'data-quality', label: 'Data Quality' },
  { id: 'warehouses', label: 'Warehouses & Routes' },
  { id: 'vehicles', label: 'Vehicles' },
  { id: 'drivers', label: 'Drivers' },
  { id: 'customer-profiles', label: 'Customer Profiles' },
  { id: 'trip-history', label: 'Trip History' },
  { id: 'capacity-performance', label: 'Capacity & Performance' },
  { id: 'capacity-forecast', label: 'Capacity Forecast' },
  { id: 'route-optimizer', label: 'Route Optimizer' },
  { id: 'business-rules', label: 'Business Rules' },
]

const WEEKDAYS: WeekdayName[] = [
  'Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday',
]

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

// --- Data Quality -----------------------------------------------------

function DataQualityTab() {
  const [report, setReport] = useState<DataQualityReport | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')

  const load = () => {
    setIsLoading(true)
    setError('')
    getDataQualityReport()
      .then(setReport)
      .catch((err) => setError(errorMessage(err, 'Unable to load the data quality report.')))
      .finally(() => setIsLoading(false))
  }

  useEffect(load, [])

  return (
    <div className="ri-panel">
      <div className="ri-panel-header">
        <div>
          <h3>Data Quality Center</h3>
          <p>
            Live check of every K&amp;M customer's MaddenCo route code and store
            number against MaddenCo's own route and warehouse masters, plus
            this module's own master-data completeness. Computed fresh on
            every load - nothing here is a stored snapshot.
          </p>
        </div>
        <button type="button" onClick={load} disabled={isLoading}>
          {isLoading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {error && <div className="ri-error">{error}</div>}

      {report && (
        <>
          <div className="ri-metrics">
            <div className="ri-metric">
              <strong>{report.customers_checked.toLocaleString()}</strong>
              <span>Customers Checked</span>
            </div>
            <div className="ri-metric">
              <strong>{formatPercent(report.route_code_match_rate)}</strong>
              <span>Route Code Match Rate</span>
            </div>
            <div className="ri-metric">
              <strong>{formatPercent(report.store_number_match_rate)}</strong>
              <span>Store Number Match Rate</span>
            </div>
            <div className="ri-metric">
              <strong>{report.total_issue_count.toLocaleString()}</strong>
              <span>Total Issues</span>
            </div>
          </div>

          <div className="ri-table-wrap">
            {report.issues.length === 0 ? (
              <div className="ri-empty">No issues found.</div>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Category</th>
                    <th>Subject</th>
                    <th>Message</th>
                  </tr>
                </thead>
                <tbody>
                  {report.issues.map((issue, index) => (
                    <tr key={index}>
                      <td>{issue.category.replaceAll('_', ' ')}</td>
                      <td>{issue.subject}</td>
                      <td>{issue.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {report.total_issue_count > report.issues.length && (
              <div className="ri-note">
                Showing the first {report.issues.length} of{' '}
                {report.total_issue_count} issues.
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

// --- Warehouses & Routes ------------------------------------------------

function WarehousesTab() {
  const [warehouses, setWarehouses] = useState<WarehouseSummary[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [routes, setRoutes] = useState<RouteSummary[]>([])
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    listWarehouses()
      .then((response) => setWarehouses(response.warehouses))
      .catch((err) => setError(errorMessage(err, 'Unable to load warehouses.')))
      .finally(() => setIsLoading(false))
  }, [])

  const openWarehouse = (warehouseNumber: number) => {
    setSelected(warehouseNumber)
    setError('')
    listRoutesForWarehouse(warehouseNumber)
      .then((response) => setRoutes(response.routes))
      .catch((err) => setError(errorMessage(err, 'Unable to load routes for this warehouse.')))
  }

  return (
    <div className="ri-panel">
      <div className="ri-panel-header">
        <div>
          <h3>Warehouses &amp; Routes</h3>
          <p>Read-only - from MaddenCo via the Freight &amp; Logistics module.</p>
        </div>
      </div>
      {error && <div className="ri-error">{error}</div>}
      <div className="ri-split">
        <div className="ri-table-wrap">
          {isLoading ? (
            <div className="ri-empty">Loading warehouses…</div>
          ) : (
            <table>
              <thead><tr><th>Warehouse #</th><th>Name</th></tr></thead>
              <tbody>
                {warehouses.map((warehouse) => (
                  <tr
                    key={warehouse.warehouse_number}
                    className={warehouse.warehouse_number === selected ? 'ri-row-selected' : ''}
                    onClick={() => openWarehouse(warehouse.warehouse_number)}
                  >
                    <td>{warehouse.warehouse_number}</td>
                    <td>{warehouse.warehouse_location_name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
        <div className="ri-table-wrap">
          {selected == null ? (
            <div className="ri-empty">Select a warehouse to see its routes.</div>
          ) : routes.length === 0 ? (
            <div className="ri-empty">No active routes for warehouse {selected}.</div>
          ) : (
            <table>
              <thead><tr><th>Route Code</th><th>Status</th></tr></thead>
              <tbody>
                {routes.map((route) => (
                  <tr key={route.route_key}>
                    <td>{route.route_code}</td>
                    <td>{route.active ? 'Active' : route.status_code || 'Inactive'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}

// --- Vehicles ---------------------------------------------------------

function VehiclesTab() {
  const [vehicles, setVehicles] = useState<Vehicle[]>([])
  const [error, setError] = useState('')
  const [unitNumber, setUnitNumber] = useState('')
  const [vehicleType, setVehicleType] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [isImporting, setIsImporting] = useState(false)
  const [importMessage, setImportMessage] = useState('')
  const [capacityDrafts, setCapacityDrafts] = useState<Record<number, string>>({})

  const load = () => {
    listVehicles()
      .then((response) => setVehicles(response.vehicles))
      .catch((err) => setError(errorMessage(err, 'Unable to load vehicles.')))
  }

  useEffect(load, [])

  const submitVehicle = (event: FormEvent) => {
    event.preventDefault()
    if (!unitNumber.trim() || isSaving) return
    setIsSaving(true)
    setError('')
    createVehicle({ unit_number: unitNumber.trim(), vehicle_type: vehicleType.trim() })
      .then(() => {
        setUnitNumber('')
        setVehicleType('')
        load()
      })
      .catch((err) => setError(errorMessage(err, 'Unable to create the vehicle.')))
      .finally(() => setIsSaving(false))
  }

  const submitCapacity = (vehicleId: number) => {
    const weight = Number(capacityDrafts[vehicleId] || '')
    if (!weight) return
    addVehicleCapacity(vehicleId, { weight_capacity: weight })
      .then(load)
      .catch((err) => setError(errorMessage(err, 'Unable to add capacity.')))
  }

  const runImport = () => {
    setIsImporting(true)
    setError('')
    setImportMessage('')
    importSamsaraVehicles()
      .then((result) => {
        setImportMessage(
          `Imported ${result.samsara_count} Samsara vehicles - `
          + `${result.created_count} new, ${result.updated_count} updated.`,
        )
        load()
      })
      .catch((err) => setError(errorMessage(err, 'Unable to import from Samsara.')))
      .finally(() => setIsImporting(false))
  }

  return (
    <div className="ri-panel">
      <div className="ri-panel-header">
        <div>
          <h3>Vehicles</h3>
          <p>Master vehicle list and weight-capacity profiles for route planning.</p>
        </div>
        <button type="button" onClick={runImport} disabled={isImporting}>
          {isImporting ? 'Importing…' : 'Import from Samsara'}
        </button>
      </div>
      {error && <div className="ri-error">{error}</div>}
      {importMessage && <div className="ri-note">{importMessage}</div>}

      <form className="ri-inline-form" onSubmit={submitVehicle}>
        <input
          placeholder="Unit number"
          value={unitNumber}
          onChange={(event) => setUnitNumber(event.target.value)}
        />
        <input
          placeholder="Vehicle type"
          value={vehicleType}
          onChange={(event) => setVehicleType(event.target.value)}
        />
        <button type="submit" disabled={isSaving}>Add Vehicle</button>
      </form>

      <div className="ri-table-wrap">
        {vehicles.length === 0 ? (
          <div className="ri-empty">No vehicles yet.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Unit #</th><th>Type</th><th>VIN</th><th>Samsara</th><th>Active</th>
                <th>Weight Capacity</th><th>Add Capacity (lb)</th>
              </tr>
            </thead>
            <tbody>
              {vehicles.map((vehicle) => (
                <tr key={vehicle.vehicle_id}>
                  <td>{vehicle.unit_number}</td>
                  <td>{vehicle.vehicle_type || '—'}</td>
                  <td>{vehicle.vin || '—'}</td>
                  <td>{vehicle.samsara_vehicle_id ? 'Linked' : '—'}</td>
                  <td>{vehicle.active ? 'Yes' : 'No'}</td>
                  <td>
                    {vehicle.capacities.length === 0
                      ? 'Not set'
                      : vehicle.capacities[vehicle.capacities.length - 1].weight_capacity ?? 'Not set'}
                  </td>
                  <td>
                    <div className="ri-capacity-cell">
                      <input
                        type="number"
                        value={capacityDrafts[vehicle.vehicle_id] || ''}
                        onChange={(event) => setCapacityDrafts((current) => ({
                          ...current, [vehicle.vehicle_id]: event.target.value,
                        }))}
                      />
                      <button type="button" onClick={() => submitCapacity(vehicle.vehicle_id)}>
                        Save
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// --- Drivers ------------------------------------------------------------

function DriversTab() {
  const [drivers, setDrivers] = useState<Driver[]>([])
  const [error, setError] = useState('')
  const [name, setName] = useState('')
  const [isSaving, setIsSaving] = useState(false)
  const [isImporting, setIsImporting] = useState(false)
  const [importMessage, setImportMessage] = useState('')

  const load = () => {
    listDrivers()
      .then((response) => setDrivers(response.drivers))
      .catch((err) => setError(errorMessage(err, 'Unable to load drivers.')))
  }

  useEffect(load, [])

  const submitDriver = (event: FormEvent) => {
    event.preventDefault()
    if (!name.trim() || isSaving) return
    setIsSaving(true)
    setError('')
    createDriver({ name: name.trim() })
      .then(() => { setName(''); load() })
      .catch((err) => setError(errorMessage(err, 'Unable to create the driver.')))
      .finally(() => setIsSaving(false))
  }

  const toggleAvailability = (driver: Driver, day: WeekdayName) => {
    const existing = driver.availability.find((item) => item.day_of_week === day)
    setDriverAvailability(driver.driver_id, {
      day_of_week: day,
      available: !(existing?.available ?? false),
    })
      .then(load)
      .catch((err) => setError(errorMessage(err, 'Unable to update availability.')))
  }

  const runImport = () => {
    setIsImporting(true)
    setError('')
    setImportMessage('')
    importSamsaraDrivers()
      .then((result) => {
        setImportMessage(
          `Imported ${result.samsara_count} Samsara drivers - `
          + `${result.created_count} new, ${result.updated_count} updated.`,
        )
        load()
      })
      .catch((err) => setError(errorMessage(err, 'Unable to import from Samsara.')))
      .finally(() => setIsImporting(false))
  }

  return (
    <div className="ri-panel">
      <div className="ri-panel-header">
        <div>
          <h3>Drivers</h3>
          <p>Master driver list and recurring weekly availability.</p>
        </div>
        <button type="button" onClick={runImport} disabled={isImporting}>
          {isImporting ? 'Importing…' : 'Import from Samsara'}
        </button>
      </div>
      {error && <div className="ri-error">{error}</div>}
      {importMessage && <div className="ri-note">{importMessage}</div>}

      <form className="ri-inline-form" onSubmit={submitDriver}>
        <input
          placeholder="Driver name"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <button type="submit" disabled={isSaving}>Add Driver</button>
      </form>

      <div className="ri-table-wrap">
        {drivers.length === 0 ? (
          <div className="ri-empty">No drivers yet.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th><th>Samsara</th>
                {WEEKDAYS.map((day) => <th key={day}>{day.slice(0, 3)}</th>)}
              </tr>
            </thead>
            <tbody>
              {drivers.map((driver) => (
                <tr key={driver.driver_id}>
                  <td>{driver.name}</td>
                  <td>{driver.samsara_driver_id ? 'Linked' : '—'}</td>
                  {WEEKDAYS.map((day) => {
                    const entry = driver.availability.find((item) => item.day_of_week === day)
                    return (
                      <td key={day}>
                        <button
                          type="button"
                          className={entry?.available ? 'ri-day-on' : 'ri-day-off'}
                          onClick={() => toggleAvailability(driver, day)}
                        >
                          {entry?.available ? '✓' : '—'}
                        </button>
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// --- Customer Profiles ---------------------------------------------------

function CustomerProfilesTab() {
  const [profiles, setProfiles] = useState<CustomerProfile[]>([])
  const [error, setError] = useState('')
  const [customerNumber, setCustomerNumber] = useState('')
  const [draft, setDraft] = useState<CustomerProfile | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [addressQuery, setAddressQuery] = useState('')
  const [addressResults, setAddressResults] = useState<SamsaraAddress[]>([])
  const [isSearchingAddresses, setIsSearchingAddresses] = useState(false)

  const load = () => {
    listCustomerProfiles()
      .then((response) => setProfiles(response.profiles))
      .catch((err) => setError(errorMessage(err, 'Unable to load customer profiles.')))
  }

  useEffect(load, [])

  const openCustomer = (number: string) => {
    setCustomerNumber(number)
    setAddressQuery('')
    setAddressResults([])
    getCustomerProfile(number)
      .then(setDraft)
      .catch((err) => setError(errorMessage(err, 'Unable to load this customer profile.')))
  }

  const searchAddresses = () => {
    setIsSearchingAddresses(true)
    setError('')
    searchSamsaraAddresses(addressQuery)
      .then((response) => setAddressResults(response.addresses))
      .catch((err) => setError(errorMessage(err, 'Unable to search Samsara addresses.')))
      .finally(() => setIsSearchingAddresses(false))
  }

  const linkAddress = (samsaraAddressId: string | null) => {
    if (!customerNumber.trim()) return
    linkCustomerSamsaraAddress(customerNumber.trim(), { samsara_address_id: samsaraAddressId })
      .then((saved) => { setDraft(saved); setAddressResults([]); load() })
      .catch((err) => setError(errorMessage(err, 'Unable to link this Samsara address.')))
  }

  const save = () => {
    if (!draft || !customerNumber.trim() || isSaving) return
    setIsSaving(true)
    saveCustomerProfile(customerNumber.trim(), {
      latitude: draft.latitude,
      longitude: draft.longitude,
      priority: draft.priority,
      normal_unloading_minutes: draft.normal_unloading_minutes,
      delivery_instructions: draft.delivery_instructions,
      notes: draft.notes,
    })
      .then((saved) => { setDraft(saved); load() })
      .catch((err) => setError(errorMessage(err, 'Unable to save this customer profile.')))
      .finally(() => setIsSaving(false))
  }

  return (
    <div className="ri-panel">
      <div className="ri-panel-header">
        <div>
          <h3>Customer Profiles</h3>
          <p>
            Delivery constraints MaddenCo has no field for - coordinates,
            priority, unloading time, and delivery instructions.
          </p>
        </div>
      </div>
      {error && <div className="ri-error">{error}</div>}

      <div className="ri-inline-form">
        <input
          placeholder="Customer number"
          value={customerNumber}
          onChange={(event) => setCustomerNumber(event.target.value)}
        />
        <button type="button" onClick={() => openCustomer(customerNumber)}>
          Open
        </button>
      </div>

      {draft && (
        <div className="ri-form-grid">
          <label>
            Latitude
            <input
              type="number"
              step="0.0001"
              value={draft.latitude ?? ''}
              onChange={(event) => setDraft({
                ...draft, latitude: event.target.value ? Number(event.target.value) : null,
              })}
            />
          </label>
          <label>
            Longitude
            <input
              type="number"
              step="0.0001"
              value={draft.longitude ?? ''}
              onChange={(event) => setDraft({
                ...draft, longitude: event.target.value ? Number(event.target.value) : null,
              })}
            />
          </label>
          <label>
            Priority
            <input
              value={draft.priority}
              onChange={(event) => setDraft({ ...draft, priority: event.target.value })}
            />
          </label>
          <label>
            Normal Unloading Minutes
            <input
              type="number"
              value={draft.normal_unloading_minutes ?? ''}
              onChange={(event) => setDraft({
                ...draft,
                normal_unloading_minutes: event.target.value ? Number(event.target.value) : null,
              })}
            />
          </label>
          <label className="ri-span-2">
            Delivery Instructions
            <textarea
              value={draft.delivery_instructions}
              onChange={(event) => setDraft({ ...draft, delivery_instructions: event.target.value })}
            />
          </label>
          <label className="ri-span-2">
            Notes
            <textarea
              value={draft.notes}
              onChange={(event) => setDraft({ ...draft, notes: event.target.value })}
            />
          </label>
          <button type="button" onClick={save} disabled={isSaving}>
            {isSaving ? 'Saving…' : 'Save Profile'}
          </button>

          <div className="ri-span-2">
            <strong>Samsara address: </strong>
            {draft.samsara_address_id ? (
              <>
                <span>{draft.samsara_address_id}</span>{' '}
                <button type="button" onClick={() => linkAddress(null)}>Unlink</button>
              </>
            ) : (
              <span>Not linked</span>
            )}
            <div className="ri-inline-form" style={{ marginTop: 8 }}>
              <input
                placeholder="Search Samsara addresses by name"
                value={addressQuery}
                onChange={(event) => setAddressQuery(event.target.value)}
              />
              <button type="button" onClick={searchAddresses} disabled={isSearchingAddresses}>
                {isSearchingAddresses ? 'Searching…' : 'Search'}
              </button>
            </div>
            {addressResults.length > 0 && (
              <ul>
                {addressResults.map((address) => (
                  <li key={address.id}>
                    {address.name} - {address.formatted_address}{' '}
                    <button type="button" onClick={() => linkAddress(address.id)}>Link</button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      <div className="ri-table-wrap">
        {profiles.length === 0 ? (
          <div className="ri-empty">No customer profiles saved yet.</div>
        ) : (
          <table>
            <thead>
              <tr><th>Customer #</th><th>Coordinates</th><th>Priority</th><th>Samsara Address</th></tr>
            </thead>
            <tbody>
              {profiles.map((profile) => (
                <tr key={profile.customer_number} onClick={() => openCustomer(profile.customer_number)}>
                  <td>{profile.customer_number}</td>
                  <td>
                    {profile.latitude != null && profile.longitude != null
                      ? `${profile.latitude}, ${profile.longitude}`
                      : 'Missing'}
                  </td>
                  <td>{profile.priority || '—'}</td>
                  <td>{profile.samsara_address_id ? 'Linked' : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// --- Trip History ---------------------------------------------------

function todayIsoDate(): string {
  return new Date().toISOString().slice(0, 10)
}

function daysAgoIsoDate(days: number): string {
  const date = new Date()
  date.setDate(date.getDate() - days)
  return date.toISOString().slice(0, 10)
}

function TripHistoryTab() {
  const [runs, setRuns] = useState<ActualRun[]>([])
  const [error, setError] = useState('')
  const [dateFrom, setDateFrom] = useState(daysAgoIsoDate(7))
  const [dateTo, setDateTo] = useState(todayIsoDate())
  const [isSyncing, setIsSyncing] = useState(false)
  const [syncMessage, setSyncMessage] = useState('')

  const load = () => {
    listActualRuns({ dateFrom, dateTo })
      .then((response) => setRuns(response.runs))
      .catch((err) => setError(errorMessage(err, 'Unable to load trip history.')))
  }

  useEffect(load, [])

  const runSync = () => {
    setIsSyncing(true)
    setError('')
    setSyncMessage('')
    syncSamsaraTrips({ date_from: dateFrom, date_to: dateTo })
      .then((result) => {
        setSyncMessage(
          `Synced ${result.trip_count} trip(s) - ${result.resolved_count} `
          + `resolved to a vehicle, ${result.unresolved_count} unresolved.`,
        )
        load()
      })
      .catch((err) => setError(errorMessage(err, 'Unable to sync Samsara trips.')))
      .finally(() => setIsSyncing(false))
  }

  return (
    <div className="ri-panel">
      <div className="ri-panel-header">
        <div>
          <h3>Trip History</h3>
          <p>
            Ingested Samsara trip history. A trip whose vehicle/driver
            hasn't been imported yet is still stored and flagged by the
            Data Quality Center, not dropped.
          </p>
        </div>
      </div>
      {error && <div className="ri-error">{error}</div>}
      {syncMessage && <div className="ri-note">{syncMessage}</div>}

      <div className="ri-inline-form">
        <label>
          From
          <input
            type="date"
            value={dateFrom}
            onChange={(event) => setDateFrom(event.target.value)}
          />
        </label>
        <label>
          To
          <input
            type="date"
            value={dateTo}
            onChange={(event) => setDateTo(event.target.value)}
          />
        </label>
        <button type="button" onClick={load}>Refresh</button>
        <button type="button" onClick={runSync} disabled={isSyncing}>
          {isSyncing ? 'Syncing…' : 'Sync Now'}
        </button>
      </div>

      <div className="ri-table-wrap">
        {runs.length === 0 ? (
          <div className="ri-empty">No trips ingested for this range yet.</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Vehicle</th><th>Driver</th><th>Start</th><th>End</th>
                <th>Distance (m)</th><th>Status</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.run_id}>
                  <td>{run.vehicle_id ?? 'Unresolved'}</td>
                  <td>{run.driver_id ?? 'Unresolved'}</td>
                  <td>{run.start_time || '—'}</td>
                  <td>{run.end_time || '—'}</td>
                  <td>{run.distance_meters ?? '—'}</td>
                  <td>{run.completion_status || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// --- Capacity & Performance ---------------------------------------------

function WorkloadStatusTag({ status }: { status: WorkloadStatus }) {
  return <span className={`ri-status-tag ri-status-tag--${status}`}>{status}</span>
}

function formatNumber(value: number): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: 1 })
}

function CapacityPerformanceTab() {
  const [warehouses, setWarehouses] = useState<WarehouseWorkloadSummary[]>([])
  const [vehicles, setVehicles] = useState<VehicleRunPerformance[]>([])
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [dateFrom, setDateFrom] = useState(daysAgoIsoDate(7))
  const [dateTo, setDateTo] = useState(todayIsoDate())

  const load = () => {
    setIsLoading(true)
    setError('')
    Promise.all([
      getWorkloadSummary({ dateFrom, dateTo }),
      getVehiclePerformance({ dateFrom, dateTo }),
    ])
      .then(([workload, performance]) => {
        setWarehouses(workload.warehouses)
        setVehicles(performance.vehicles)
      })
      .catch((err) => setError(errorMessage(err, 'Unable to load capacity & performance data.')))
      .finally(() => setIsLoading(false))
  }

  useEffect(load, [])

  return (
    <div className="ri-panel">
      <div className="ri-panel-header">
        <div>
          <h3>Capacity &amp; Performance</h3>
          <p>
            Warehouse-level fleet capacity vs. real MaddenCo load demand, and
            real per-vehicle trip performance from Samsara. No MaddenCo route
            is linked to a specific vehicle/driver anywhere in this schema
            yet, so these are computed at the warehouse and vehicle level -
            the honest grain this data actually supports.
          </p>
        </div>
      </div>
      {error && <div className="ri-error">{error}</div>}

      <div className="ri-inline-form">
        <label>
          From
          <input
            type="date"
            value={dateFrom}
            onChange={(event) => setDateFrom(event.target.value)}
          />
        </label>
        <label>
          To
          <input
            type="date"
            value={dateTo}
            onChange={(event) => setDateTo(event.target.value)}
          />
        </label>
        <button type="button" onClick={load} disabled={isLoading}>
          {isLoading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      <div className="ri-sections">
        <div>
          <h4 className="ri-section-title">Warehouse Workload vs. Capacity</h4>
          <div className="ri-table-wrap">
            {warehouses.length === 0 ? (
              <div className="ri-empty">No warehouses found.</div>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Warehouse</th><th>Vehicles</th><th>Weight Capacity (lb)</th>
                    <th>Weight Demand (lb)</th><th>Routes w/ Activity</th>
                    <th>Utilization</th><th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {warehouses.map((warehouse) => (
                    <tr key={warehouse.warehouse_number}>
                      <td>
                        {warehouse.warehouse_number} - {warehouse.warehouse_location_name}
                      </td>
                      <td>{warehouse.vehicle_count}</td>
                      <td>{formatNumber(warehouse.total_weight_capacity)}</td>
                      <td>{formatNumber(warehouse.total_weight_demand)}</td>
                      <td>{warehouse.route_count_with_activity}</td>
                      <td>
                        {warehouse.weight_utilization_pct == null
                          ? '—'
                          : `${warehouse.weight_utilization_pct.toFixed(1)}%`}
                      </td>
                      <td><WorkloadStatusTag status={warehouse.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        <div>
          <h4 className="ri-section-title">Vehicle Run Performance</h4>
          <div className="ri-table-wrap">
            {vehicles.length === 0 ? (
              <div className="ri-empty">No resolved trips for this range yet.</div>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Unit #</th><th>Home Warehouse</th><th>Runs</th>
                    <th>Total Distance (m)</th><th>Avg. Distance (m)</th>
                  </tr>
                </thead>
                <tbody>
                  {vehicles.map((vehicle) => (
                    <tr key={vehicle.vehicle_id}>
                      <td>{vehicle.unit_number}</td>
                      <td>{vehicle.home_warehouse_number ?? '—'}</td>
                      <td>{vehicle.run_count}</td>
                      <td>{formatNumber(vehicle.total_distance_meters)}</td>
                      <td>{formatNumber(vehicle.average_distance_meters)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// --- Capacity Forecast ---------------------------------------------------

function ForecastStatusTag({ status }: { status: ForecastStatus }) {
  return (
    <span className={`ri-status-tag ri-status-tag--${status}`}>
      {status.replaceAll('_', ' ')}
    </span>
  )
}

function CapacityForecastTab() {
  const [assessments, setAssessments] = useState<CapacityAssessment[]>([])
  const [runStatus, setRunStatus] = useState<{
    status: string; message: string; runAt: string | null
  } | null>(null)
  const [weeksBack, setWeeksBack] = useState('8')
  const [error, setError] = useState('')
  const [isComputing, setIsComputing] = useState(false)
  const [isLoading, setIsLoading] = useState(true)

  const load = () => {
    setIsLoading(true)
    setError('')
    Promise.all([listCapacityForecasts(), getForecastRunStatus()])
      .then(([forecasts, status]) => {
        setAssessments(forecasts.assessments)
        setRunStatus({
          status: status.status, message: status.message, runAt: status.run_at,
        })
      })
      .catch((err) => setError(errorMessage(err, 'Unable to load the capacity forecast.')))
      .finally(() => setIsLoading(false))
  }

  useEffect(load, [])

  const runCompute = () => {
    const weeks = Number(weeksBack) || 8
    setIsComputing(true)
    setError('')
    computeCapacityForecast({ weeks_back: weeks })
      .then(() => load())
      .catch((err) => setError(errorMessage(err, 'Unable to compute the capacity forecast.')))
      .finally(() => setIsComputing(false))
  }

  return (
    <div className="ri-panel">
      <div className="ri-panel-header">
        <div>
          <h3>Capacity Forecast</h3>
          <p>
            Day-of-week demand forecast (real MaddenCo load history) vs.
            fleet weight capacity, per warehouse - a recommendation only,
            not an automatic action. Computing all warehouses takes several
            minutes; results are cached until the next "Compute Now."
          </p>
        </div>
      </div>
      {error && <div className="ri-error">{error}</div>}
      {runStatus && runStatus.status && (
        <div className="ri-note">
          Last run: {runStatus.status} - {runStatus.message}
          {runStatus.runAt ? ` (${runStatus.runAt})` : ''}
        </div>
      )}

      <div className="ri-inline-form">
        <label>
          Weeks of history
          <input
            type="number"
            min={1}
            max={52}
            value={weeksBack}
            onChange={(event) => setWeeksBack(event.target.value)}
          />
        </label>
        <button type="button" onClick={runCompute} disabled={isComputing}>
          {isComputing ? 'Computing… (this can take several minutes)' : 'Compute Now'}
        </button>
        <button type="button" onClick={load} disabled={isLoading}>
          {isLoading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      <div className="ri-table-wrap">
        {assessments.length === 0 ? (
          <div className="ri-empty">
            No forecast computed yet - click "Compute Now."
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Warehouse</th><th>Day</th><th>Samples</th>
                <th>Expected Weight (lb)</th><th>P90 Weight (lb)</th>
                <th>Capacity (lb)</th><th>P90 Utilization</th>
                <th>Status</th><th>Structural Review</th>
              </tr>
            </thead>
            <tbody>
              {assessments.map((assessment) => (
                <tr key={`${assessment.warehouse_number}-${assessment.day_of_week}`}>
                  <td>
                    {assessment.warehouse_number}
                    {assessment.warehouse_location_name
                      ? ` - ${assessment.warehouse_location_name}` : ''}
                  </td>
                  <td>{assessment.day_of_week}</td>
                  <td>{assessment.sample_size}</td>
                  <td>{formatNumber(assessment.expected_weight ?? 0)}</td>
                  <td>{formatNumber(assessment.p90_weight ?? 0)}</td>
                  <td>{formatNumber(assessment.weight_capacity)}</td>
                  <td>
                    {assessment.p90_utilization_pct == null
                      ? '—'
                      : `${assessment.p90_utilization_pct.toFixed(1)}%`}
                  </td>
                  <td><ForecastStatusTag status={assessment.status} /></td>
                  <td>
                    {assessment.structural_review
                      ? <span className="ri-structural-review-flag">⚠ Review</span>
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// --- Route Optimizer ---------------------------------------------------

function OptimizationStatusTag({ status }: { status: string }) {
  const normalized = status || 'unknown'
  return (
    <span className={`ri-status-tag ri-status-tag--${normalized}`}>
      {normalized.replaceAll('_', ' ')}
    </span>
  )
}

function RouteOptimizerTab() {
  const [warehouses, setWarehouses] = useState<WarehouseSummary[]>([])
  const [warehouseNumber, setWarehouseNumber] = useState<number | null>(null)
  const [targetDate, setTargetDate] = useState(daysAgoIsoDate(-1))
  const [readiness, setReadiness] = useState<OptimizationReadiness | null>(null)
  const [locationLat, setLocationLat] = useState('')
  const [locationLon, setLocationLon] = useState('')
  const [runResult, setRunResult] = useState<OptimizationRunStatus | null>(null)
  const [error, setError] = useState('')
  const [isLoadingReadiness, setIsLoadingReadiness] = useState(false)
  const [isSavingLocation, setIsSavingLocation] = useState(false)
  const [isComputing, setIsComputing] = useState(false)
  const [decisionType, setDecisionType] = useState<PlanDecision>('approved_baseline')
  const [decidedBy, setDecidedBy] = useState('')
  const [decisionReason, setDecisionReason] = useState('')
  const [modificationNotes, setModificationNotes] = useState('')
  const [decisionHistory, setDecisionHistory] = useState<RunDecisionRecord[]>([])
  const [decisionError, setDecisionError] = useState('')
  const [isSavingDecision, setIsSavingDecision] = useState(false)

  useEffect(() => {
    listWarehouses()
      .then((response) => {
        setWarehouses(response.warehouses)
        if (response.warehouses.length > 0) {
          setWarehouseNumber(response.warehouses[0].warehouse_number)
        }
      })
      .catch((err) => setError(errorMessage(err, 'Unable to load warehouses.')))
  }, [])

  const loadReadiness = (number: number) => {
    setIsLoadingReadiness(true)
    setError('')
    getOptimizationReadiness(number)
      .then(setReadiness)
      .catch((err) => setError(errorMessage(err, 'Unable to load optimization readiness.')))
      .finally(() => setIsLoadingReadiness(false))
  }

  useEffect(() => {
    if (warehouseNumber != null) {
      setRunResult(null)
      loadReadiness(warehouseNumber)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [warehouseNumber])

  const saveLocation = () => {
    if (warehouseNumber == null || !locationLat.trim() || !locationLon.trim()) return
    setIsSavingLocation(true)
    setError('')
    saveWarehouseLocation(warehouseNumber, {
      latitude: Number(locationLat), longitude: Number(locationLon),
    })
      .then(() => {
        setLocationLat('')
        setLocationLon('')
        loadReadiness(warehouseNumber)
      })
      .catch((err) => setError(errorMessage(err, 'Unable to save the warehouse location.')))
      .finally(() => setIsSavingLocation(false))
  }

  const loadDecisionHistory = (runId: number) => {
    listOptimizationDecisions(runId)
      .then((response) => setDecisionHistory(response.decisions))
      .catch((err) => setDecisionError(errorMessage(err, 'Unable to load decision history.')))
  }

  const runCompute = () => {
    if (warehouseNumber == null) return
    setIsComputing(true)
    setError('')
    setDecisionHistory([])
    setDecisionError('')
    computeRouteOptimization({ warehouse_number: warehouseNumber, target_date: targetDate })
      .then((result) => {
        setRunResult(result)
        if (result.status === 'success' && result.run_id != null) {
          loadDecisionHistory(result.run_id)
        }
      })
      .catch((err) => setError(errorMessage(err, 'Unable to compute route optimization.')))
      .finally(() => setIsComputing(false))
  }

  const submitDecision = () => {
    if (runResult?.run_id == null || !decidedBy.trim() || !decisionReason.trim()) return
    setIsSavingDecision(true)
    setDecisionError('')
    recordOptimizationDecision(runResult.run_id, {
      decision: decisionType,
      decided_by: decidedBy.trim(),
      reason: decisionReason.trim(),
      modification_notes: decisionType === 'modified' ? modificationNotes.trim() : null,
    })
      .then(() => {
        setDecisionReason('')
        setModificationNotes('')
        if (runResult.run_id != null) loadDecisionHistory(runResult.run_id)
      })
      .catch((err) => setDecisionError(errorMessage(err, 'Unable to record this decision.')))
      .finally(() => setIsSavingDecision(false))
  }

  const plansByScenario = (scenario: string): OptimizationPlan[] =>
    (runResult?.plans ?? []).filter((plan) => plan.scenario === scenario)

  return (
    <div className="ri-panel">
      <div className="ri-panel-header">
        <div>
          <h3>Route Optimizer</h3>
          <p>
            Shadow planning only - computes a recommendation, writes nothing
            to Samsara or MaddenCo. Compares a baseline plan (today's active
            vehicles) against a with-backup plan (one extra hypothetical
            vehicle). Requires a warehouse location and real customer/
            vehicle location and capacity data - most warehouses will show
            "insufficient data" until that's entered.
          </p>
        </div>
      </div>
      {error && <div className="ri-error">{error}</div>}

      <div className="ri-inline-form">
        <label>
          Warehouse
          <select
            value={warehouseNumber ?? ''}
            onChange={(event) => setWarehouseNumber(Number(event.target.value))}
          >
            {warehouses.map((warehouse) => (
              <option key={warehouse.warehouse_number} value={warehouse.warehouse_number}>
                {warehouse.warehouse_number} - {warehouse.warehouse_location_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Target date
          <input
            type="date"
            value={targetDate}
            onChange={(event) => setTargetDate(event.target.value)}
          />
        </label>
        <button type="button" onClick={runCompute} disabled={isComputing || !readiness}>
          {isComputing ? 'Computing…' : 'Compute Now'}
        </button>
      </div>

      {isLoadingReadiness ? (
        <div className="ri-empty">Loading readiness…</div>
      ) : readiness && (
        <div className="ri-metrics">
          <div className="ri-metric">
            <strong>{readiness.has_location ? 'Yes' : 'No'}</strong>
            <span>Warehouse Has Location</span>
          </div>
          <div className="ri-metric">
            <strong>{readiness.customers_with_location_count} / {readiness.customer_count}</strong>
            <span>Customers With Coordinates</span>
          </div>
          <div className="ri-metric">
            <strong>{readiness.vehicles_with_capacity_count} / {readiness.vehicle_count}</strong>
            <span>Vehicles With Capacity</span>
          </div>
        </div>
      )}

      {readiness && !readiness.has_location && (
        <div className="ri-inline-form">
          <label>
            Warehouse Latitude
            <input
              type="number" step="0.0001" value={locationLat}
              onChange={(event) => setLocationLat(event.target.value)}
            />
          </label>
          <label>
            Warehouse Longitude
            <input
              type="number" step="0.0001" value={locationLon}
              onChange={(event) => setLocationLon(event.target.value)}
            />
          </label>
          <button type="button" onClick={saveLocation} disabled={isSavingLocation}>
            {isSavingLocation ? 'Saving…' : 'Save Warehouse Location'}
          </button>
        </div>
      )}

      {runResult && (
        <>
          <div className="ri-note">
            <OptimizationStatusTag status={runResult.status} /> {runResult.message}
          </div>

          {(['baseline', 'with_backup'] as const).map((scenario) => {
            const plans = plansByScenario(scenario)
            if (runResult.status !== 'success') return null
            return (
              <div key={scenario}>
                <h4 className="ri-section-title">
                  {scenario === 'baseline' ? 'Baseline (current fleet)' : 'With Backup (+1 vehicle)'}
                </h4>
                <div className="ri-table-wrap">
                  {plans.length === 0 ? (
                    <div className="ri-empty">No vehicle routes in this scenario.</div>
                  ) : (
                    <table>
                      <thead>
                        <tr>
                          <th>Vehicle Slot</th><th>Assigned Vehicle</th><th>Stops</th>
                          <th>Stop Sequence</th><th>Distance (mi)</th><th>Time (min)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {plans.map((plan) => (
                          <tr key={plan.plan_id}>
                            <td>{plan.vehicle_slot}</td>
                            <td>{plan.assigned_vehicle_id ?? 'Hypothetical'}</td>
                            <td>{plan.stop_count}</td>
                            <td>{plan.stop_sequence.join(' -> ') || '—'}</td>
                            <td>{plan.total_distance_miles ?? '—'}</td>
                            <td>{plan.total_time_minutes ?? '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            )
          })}

          {runResult.status === 'success' && (
            <>
              <h4 className="ri-section-title">Record Decision</h4>
              {decisionError && <div className="ri-error">{decisionError}</div>}
              <div className="ri-form-grid">
                <label>
                  Decision
                  <select
                    value={decisionType}
                    onChange={(event) => setDecisionType(event.target.value as PlanDecision)}
                  >
                    <option value="approved_baseline">Approve Baseline</option>
                    <option value="approved_with_backup">Approve With Backup</option>
                    <option value="modified">Modify</option>
                    <option value="rejected">Reject</option>
                  </select>
                </label>
                <label>
                  Decided By
                  <input
                    value={decidedBy}
                    onChange={(event) => setDecidedBy(event.target.value)}
                    placeholder="Person recording this decision"
                  />
                </label>
                <label className="ri-span-2">
                  Reason
                  <textarea
                    value={decisionReason}
                    onChange={(event) => setDecisionReason(event.target.value)}
                    placeholder="Why this decision - evidence considered, gaps, next step"
                  />
                </label>
                {decisionType === 'modified' && (
                  <label className="ri-span-2">
                    Modification Notes
                    <textarea
                      value={modificationNotes}
                      onChange={(event) => setModificationNotes(event.target.value)}
                      placeholder="What should change before this plan is used - no live editor yet, this is a note for whoever adjusts it by hand"
                    />
                  </label>
                )}
                <button type="button" onClick={submitDecision} disabled={isSavingDecision}>
                  {isSavingDecision ? 'Recording…' : 'Record Decision'}
                </button>
              </div>

              <h4 className="ri-section-title">Decision History</h4>
              <div className="ri-table-wrap">
                {decisionHistory.length === 0 ? (
                  <div className="ri-empty">No decisions recorded for this run yet.</div>
                ) : (
                  <table>
                    <thead>
                      <tr>
                        <th>Decision</th><th>Decided By</th><th>When</th>
                        <th>Reason</th><th>Modification Notes</th>
                      </tr>
                    </thead>
                    <tbody>
                      {decisionHistory.map((item) => (
                        <tr key={item.decision_id}>
                          <td>{item.decision.replaceAll('_', ' ')}</td>
                          <td>{item.decided_by}</td>
                          <td>{item.decided_at}</td>
                          <td>{item.reason}</td>
                          <td>{item.modification_notes || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}

// --- Business Rules ---------------------------------------------------

function BusinessRulesTab() {
  const [rules, setRules] = useState<BusinessRule[]>([])
  const [error, setError] = useState('')
  const [ruleKey, setRuleKey] = useState('')
  const [ruleValue, setRuleValue] = useState('')
  const [isSaving, setIsSaving] = useState(false)

  const load = () => {
    listBusinessRules()
      .then((response) => setRules(response.rules))
      .catch((err) => setError(errorMessage(err, 'Unable to load business rules.')))
  }

  useEffect(load, [])

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!ruleKey.trim() || !ruleValue.trim() || isSaving) return
    setIsSaving(true)
    saveBusinessRule(ruleKey.trim(), { rule_value: ruleValue.trim() })
      .then(() => { setRuleKey(''); setRuleValue(''); load() })
      .catch((err) => setError(errorMessage(err, 'Unable to save this rule.')))
      .finally(() => setIsSaving(false))
  }

  return (
    <div className="ri-panel">
      <div className="ri-panel-header">
        <div>
          <h3>Business Rules</h3>
          <p>
            Configuration for capacity-status thresholds and other tunable
            values - a plain key/value store, not a code change to adjust.
          </p>
        </div>
      </div>
      {error && <div className="ri-error">{error}</div>}

      <form className="ri-inline-form" onSubmit={submit}>
        <input
          placeholder="Rule key (e.g. capacity_watch_threshold_pct)"
          value={ruleKey}
          onChange={(event) => setRuleKey(event.target.value)}
        />
        <input
          placeholder="Value"
          value={ruleValue}
          onChange={(event) => setRuleValue(event.target.value)}
        />
        <button type="submit" disabled={isSaving}>Save Rule</button>
      </form>

      <div className="ri-table-wrap">
        {rules.length === 0 ? (
          <div className="ri-empty">No business rules configured yet.</div>
        ) : (
          <table>
            <thead><tr><th>Key</th><th>Value</th><th>Description</th></tr></thead>
            <tbody>
              {rules.map((rule) => (
                <tr key={rule.rule_key}>
                  <td>{rule.rule_key}</td>
                  <td>{rule.rule_value}</td>
                  <td>{rule.description || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// --- Shell ---------------------------------------------------------------

export default function RouteIntelligenceWorkspace() {
  const [tab, setTab] = useState<Tab>('data-quality')

  return (
    <div className="ri-shell">
      <div className="ri-header">
        <span className="ri-kicker">Route Intelligence</span>
        <h2>Delivery Route Capacity Foundation</h2>
        <p>
          Data quality, master data, live Samsara fleet/trip data, and
          warehouse-level capacity &amp; performance reporting for K&amp;M's
          delivery routes.
        </p>
      </div>

      <div className="ri-tabs">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={tab === item.id ? 'ri-tab-active' : ''}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === 'data-quality' && <DataQualityTab />}
      {tab === 'warehouses' && <WarehousesTab />}
      {tab === 'vehicles' && <VehiclesTab />}
      {tab === 'drivers' && <DriversTab />}
      {tab === 'customer-profiles' && <CustomerProfilesTab />}
      {tab === 'trip-history' && <TripHistoryTab />}
      {tab === 'capacity-performance' && <CapacityPerformanceTab />}
      {tab === 'capacity-forecast' && <CapacityForecastTab />}
      {tab === 'route-optimizer' && <RouteOptimizerTab />}
      {tab === 'business-rules' && <BusinessRulesTab />}
    </div>
  )
}
