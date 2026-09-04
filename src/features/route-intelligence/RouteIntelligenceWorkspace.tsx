import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  addVehicleCapacity,
  createDriver,
  createVehicle,
  getCustomerProfile,
  getDataQualityReport,
  getVehiclePerformance,
  getWorkloadSummary,
  importSamsaraDrivers,
  importSamsaraVehicles,
  linkCustomerSamsaraAddress,
  listActualRuns,
  listBusinessRules,
  listCustomerProfiles,
  listDrivers,
  listRoutesForWarehouse,
  listVehicles,
  listWarehouses,
  saveBusinessRule,
  saveCustomerProfile,
  searchSamsaraAddresses,
  setDriverAvailability,
  syncSamsaraTrips,
} from './api'
import type {
  ActualRun,
  BusinessRule,
  CustomerProfile,
  DataQualityReport,
  Driver,
  RouteSummary,
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
  | 'business-rules'

const TABS: { id: Tab; label: string }[] = [
  { id: 'data-quality', label: 'Data Quality' },
  { id: 'warehouses', label: 'Warehouses & Routes' },
  { id: 'vehicles', label: 'Vehicles' },
  { id: 'drivers', label: 'Drivers' },
  { id: 'customer-profiles', label: 'Customer Profiles' },
  { id: 'trip-history', label: 'Trip History' },
  { id: 'capacity-performance', label: 'Capacity & Performance' },
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
      {tab === 'business-rules' && <BusinessRulesTab />}
    </div>
  )
}
