# Route Intelligence

A predictive, capacity-aware, human-governed delivery-routing platform,
built incrementally against the "ETOP Route Intelligence" program plan
(RI-0 through RI-9). Built as an RI-0 first slice with no Samsara
dependency; a real Samsara API token became available shortly after
(2026-09-04), so `providers/samsara_provider.py`'s `SamsaraApiProvider`
and a handful of read-only endpoints were added on top without changing
anything else in this module.

## RI-1: fleet import + historical trip sync (added 2026-09-04)

`route_vehicles`/`route_drivers` are now populated by **importing directly
from Samsara** (`POST /samsara/import/vehicles`, `POST /samsara/import/
drivers`), keyed by `samsara_vehicle_id`/`samsara_driver_id` - not by
reconciling against independently-entered data, since those tables were
empty before this and Samsara already has the real fleet. Re-importing
refreshes name/vin/active from Samsara but preserves manually-entered
`notes`/`home_warehouse_number`/`qualifications`.

`POST /samsara/sync-trips` (date range) pulls real trip history via
`list_historical_routes()` and stores it in `route_actual_runs`, resolving
each trip's vehicle via `samsara_vehicle_id`. **Driver is never resolved
on a trip** - confirmed live 2026-09-04 that `/trips/stream` has no driver
field on any trip, not a per-trip gap - so the Data Quality Center's
"unresolved link" check only looks at the vehicle side; checking driver_id
there would flag every trip permanently and mean nothing actionable.

Customer-to-Samsara-address linking (`PUT /customer-profiles/{customer}/
samsara-address`, backed by `GET /samsara/addresses/search`) stays a
manual action, not an import - customers already exist in MaddenCo
independently, and Samsara's address list includes non-customer locations
too (warehouses, depots), so there's no safe bulk-import direction here.

**Live-verified against the real account** (2026-09-04): imported all
1,472 vehicles and 958 drivers with zero errors, then synced 2 days of
real trip history - 13,168 trips ingested, all 13,168 resolved cleanly to
an imported vehicle.

Still explicitly deferred: automatic/scheduled sync (manual trigger only -
`backend/modules/automations/`'s real cron scheduler is the natural next
home for this once manual sync has been used for real), and matching a
trip to a specific MaddenCo route_code (a vehicle isn't tied to one fixed
route_code in this schema - needs more MaddenCo data modeling than should
be guessed at here).

## RI-2: workload & capacity dashboard, read-only (added 2026-09-04)

`GET /workload-summary` and `GET /vehicle-performance` (both take
`date_from`/`date_to`) are computed live, no snapshot - same style as the
Data Quality Center.

The program plan calls this increment "Route performance, workload model
and capacity dashboard." Literally, that implies comparing a route's
workload against the vehicle capacity assigned to it - but **no schema
anywhere links a MaddenCo `route_code` to a specific vehicle or driver**
(the same gap RI-1 already flagged: "a vehicle isn't tied to one fixed
route_code in this schema"). Inventing that link here would mean guessing
at a real operational fact that isn't recorded anywhere, so this slice is
built on the one join key that genuinely exists today: **warehouse
number** (`route_vehicles.home_warehouse_number` /
`route_drivers.home_warehouse_number` vs. freight_logistics's
`warehouse_number`).

- **`/workload-summary`**: per warehouse, sums the *current* capacity
  (weight/cube/tire/max_stops) of active vehicles home-based there against
  real MaddenCo load demand for the date range
  (`freight_logistics_service.get_load_lines_for_warehouse()` - real
  `WEIGHT`/`QUANTITY` off `INWHLOAD`, not previously called from this
  module). Produces a weight-utilization percentage and an
  `ok`/`warning`/`critical`/`unknown` status, classified against
  configurable thresholds (`workload_warning_threshold_pct`,
  `workload_critical_threshold_pct`) read from `route_business_rules`
  (defaulting to 80%/100% - the table has no seed rows). `unknown` (not a
  divide-by-zero) when a warehouse has no vehicles with capacity data.
  "Current" capacity means the vehicle's most-recently-entered capacity
  row - `effective_date` is a free-text column with no enforced format
  today (no rows exist yet to validate a format against), so this is not
  a true point-in-time "as of" lookup.
- **`/vehicle-performance`**: per vehicle, aggregates real ingested
  `route_actual_runs` (Samsara trip data) for the date range - run count,
  total/average distance. This is the honest read-only proxy for "route
  performance," since there's no route_code to report against directly.
  **`distance_meters` is null on every real ingested trip today** -
  confirmed live 2026-09-04 by fetching a raw `/trips/stream` payload: it
  carries no distance field under any name at all (only
  tripStartTime/tripEndTime/startLocation/endLocation/asset/
  completionStatus). This is a permanent Samsara API limitation, not a
  wrong field name in RI-1's mapping - see the comment at `service.py`'s
  `sync_samsara_trips()`. Distance in this view will read 0 until a
  different data source is used (e.g. a straight-line estimate from
  start/end lat-lon via `travel_matrix_provider.py`'s
  `HaversineTravelMatrixProvider` - a real design decision, not made
  here).

Also live-verified 2026-09-04: every warehouse initially reported status
`unknown`, not because of a bug but because **zero** of the 1,472
Samsara-imported vehicles had `home_warehouse_number` or a capacity row
set (`import_samsara_vehicles()` never sets either - matches the
pre-existing `vehicle_missing_capacity` Data Quality Center check).
**Update, same day**: the user supplied K&M's real truck list
spreadsheet, matched by VIN - 902 vehicles got a real
`home_warehouse_number` from the sheet's Location column (the real 51
K&M warehouse numbers, confirmed by the user directly - see the
"freight_logistics warehouse master incomplete" reference for why that's
more than `list_warehouses()` itself returns), and separately 867
vehicles got a real `weight_capacity` from the sheet's GVW (Gross
Vehicle Weight Rating) column. **Known caveat, not a bug**: GVW is the
vehicle's total gross weight rating (truck + cargo combined), not net
payload capacity - the only weight-like column the source spreadsheet
has - so utilization percentages computed against it are systematically
optimistic (real trucks can carry meaningfully less than their GVW).
Most warehouses now report real `ok` status with real (if
GVW-overstated) utilization numbers instead of `unknown`.

Still explicitly deferred: any route_code-to-vehicle/driver assignment
(true per-route performance/capacity stays blocked on this); predictive
"Capacity Forecast" using `forecast_provider.py`'s
`SimpleDayOfWeekForecastProvider` (this slice is current/historical only);
treating `effective_date` as a real point-in-time filter.

## RI-3: forecasting and proactive capacity alerts (added 2026-09-04)

`POST /forecast/compute` (manual trigger, body: `weeks_back`, optional
`warehouse_number`), `GET /forecast/capacity-assessments` (reads stored
results - instant), `GET /forecast/status` (latest run metadata).

Finishes wiring up `forecast_provider.py`'s `SimpleDayOfWeekForecastProvider`
(built in RI-0, confirmed live never called by anything until now) into a
real per-warehouse day-of-week demand forecast vs. fleet weight capacity,
with P50/P80/P90 (added to `DayOfWeekForecast` this slice - it previously
only produced a mean) and a 4-tier status
(`healthy`/`watch`/`backup_likely`/`split_recommended`, plus `unknown`
when a warehouse has no capacity data) using configurable thresholds
from `route_business_rules` (`forecast_watch_threshold_pct` (80),
`forecast_backup_likely_threshold_pct` (90),
`forecast_split_threshold_pct` (100)), same pattern as RI-2's workload
dashboard. Also flags `structural_review` when at least
`forecast_structural_review_min_occurrences` (default 2) of a weekday's
own historical samples already exceeded today's capacity - a real
recurring-overload signal computed from actual past data, not a guess.

**Manual-trigger, stored-result design, not live-computed-per-request**
(unlike RI-2's dashboard): live-verified that `get_load_lines_for_warehouse`
over an 8-12 week lookback takes ~7 seconds per warehouse, so a full
network-wide compute (~53 warehouses) takes several real minutes -
results are cached in two new tables (`route_forecast_runs`,
`route_capacity_assessments`, migration `dffa4a3678d0`) and served
instantly afterward, same shape as RI-1's `sync_samsara_trips`.

**Warehouse-level only, same reasoning as RI-2**: no schema anywhere
links a MaddenCo `route_code` to a vehicle/driver, so per-route or
per-customer forecasting isn't attempted here.

**Real finding, not a design choice**: `INWHLOAD` (MaddenCo's load
manifest, described in its own metadata as a "Load Sheet Hold File")
was assumed to be short-retention - live-verified 2026-09-04 it actually
holds a full 2 years of real data (back to 2024-09-04, 5.37M rows), with
an obvious weekly rhythm already visible in a sample warehouse's daily
counts. This is what made day-of-week forecasting viable at all; it
should be re-verified if this deferred item is ever revisited, since
nothing enforces that MaddenCo won't purge this table's history later.

Still explicitly deferred: customer-level and route-level forecasting
(blocked on the same route_code-to-vehicle gap, or a not-yet-built
`sales_order_visibility_service` function against `TMIHSH`); network-
level (cross-warehouse) rollups; seasonal/trend/promotional adjustments
beyond the day-of-week baseline (per the program plan itself: "more
advanced models only when they materially outperform the baseline in
backtesting"); the full 5-tier alert system's time/HOS-based criteria
(operating buffer minutes, hard time-window violations) - no time-based
capacity dimension or Samsara HOS integration exists in this codebase
yet; automatic/scheduled recomputation (manual trigger only this slice -
`backend/modules/automations/`'s `AutomationScheduler` remains the
natural future home); tire-equivalent-based forecasting (`INWHLOAD`'s
`WEIGHT`/`QUANTITY` columns carry no product-mix/tire-classification
data).

## RI-4: route optimizer and backup split scenarios (added 2026-09-04)

`PUT /warehouse-locations/{warehouse_number}` / `GET /warehouse-locations`
(manual depot coordinates), `GET /optimize/readiness/{warehouse_number}`
(real diagnostic), `POST /optimize/compute` (manual trigger, body:
warehouse_number/target_date), `GET /optimize/runs/{run_id}`.

**This increment hit a fundamentally different blocker than RI-1/2/3.**
Live-checked every real input a route optimizer needs, before writing
any solver code:

- `route_customer_profiles`: 0 rows - no customer has a saved location
  anywhere in ETOP.
- `route_driver_availability`: 0 of 958 real imported drivers have any
  schedule data.
- Stop sequencing: MaddenCo has three columns literally named "Delivery
  Sequence" (`INWHLOAD.SEQ`, `TMCUST.CUDELTRUCK`, `TMIHSH.TIHHDELSEQ`).
  Live-queried all three - **every one is always 0** in real data. None
  are actually populated; there is no real record anywhere of what
  order a route's stops happen in.
- Warehouse depot coordinates: MaddenCo's own warehouse master
  (`WH_DASHBOARD_LOCATIONS`) has only `LOCATION_NAME`/`LOCATION_NUMBER`/
  `ACTIVE` - no lat/lon column at all.
- The optimizer engine itself was a stub (`UnconfiguredRoutingSolverProvider`
  always raised) and OR-Tools wasn't a dependency yet.

Asked the user directly how to proceed given this. **Chosen: build the
real engine now, gate every output on real data completeness rather
than faking inputs or skipping the increment.** Added `ortools` as a
real dependency and a real `OrToolsRoutingSolverProvider` (capacitated
VRP - `providers/routing_solver_provider.py`), wired to the already-real
`HaversineTravelMatrixProvider`. Capacity is **stop-count only** this
slice (`max_stops`, defaulting via a new
`optimizer_default_max_stops_per_vehicle` business rule when a vehicle
has no real value) - real per-customer demand weight isn't cleanly
available from MaddenCo yet. `route_warehouse_locations` fills the
missing depot-coordinate gap the same way `route_customer_profiles`
fills gaps in `TMCUST` - manual entry, ETOP-owned.

`compute_route_optimization(warehouse_number, target_date)` gathers
real customers assigned to the warehouse (`CUSTORENUM` match, same
field the Data Quality Center already validates) with real coordinates,
real active vehicles with a real capacity row, and the warehouse's
saved depot location - if any of the three is missing, it stores a
`status="insufficient_data"` run with the real counts in the message
and returns, rather than fabricating a plan. When all three exist, it
solves twice - `"baseline"` (today's real active vehicles) vs.
`"with_backup"` (one extra hypothetical vehicle, average fleet
`max_stops`) - the literal backup-split comparison the program plan's
section I asks for - and persists both scenarios'
per-vehicle stop sequences, distance, and time.

**Live-verified 2026-09-04**: every real K&M warehouse reports
`insufficient_data` today (0 customer profiles exist anywhere in ETOP -
this is expected and honest, not a bug). Manually setting one real
warehouse's location via the new endpoint confirmed that piece of the
readiness gate flips correctly; a synthetic small-fixture test (not
against real data, since none of the required real data exists yet)
confirms the solver itself produces valid, capacity-respecting,
correctly-comparing baseline/with-backup plans once real inputs exist.

Still explicitly deferred: real per-customer demand weight/cube in the
capacity constraint; time windows, HOS, and driver-availability
constraints (no such data exists anywhere in this codebase); comparing
a recommendation against the *real* existing route structure (an
explicit Definition-of-Done item in the program plan) - not possible
until real stop-sequence data exists from *somewhere* (none of
MaddenCo's three "Delivery Sequence" columns are populated; Samsara's
actual-stops webhook receiver still isn't built); a real
production-grade travel-time matrix (OSRM/Valhalla/a licensed routing
API, per the program plan's section 8) - `HaversineTravelMatrixProvider`
(straight-line × 1.3 fudge factor) remains the only implementation;
customer-level demand forecasting feeding the optimizer.

## RI-5: dispatcher approval workflow (added 2026-09-05)

`POST /optimize/runs/{run_id}/decisions` (body: `decision` -
`"approved_baseline"`/`"approved_with_backup"`/`"modified"`/`"rejected"`,
`decided_by`, `reason`, optional `modification_notes`),
`GET /optimize/runs/{run_id}/decisions` (append-only history).

Adds the missing piece the program plan's Definition of Done requires
on top of RI-4's compute side: a dispatcher approves, modifies, or
rejects a computed optimization run, with every decision traceable.
`decide_optimization_run()` refuses to record a decision against a run
whose `status` isn't `"success"` (a real, worthwhile guard - approving a
run that never produced a plan, e.g. `"insufficient_data"`, would be
meaningless) with a clear 400. `route_plan_decisions` is append-only -
every action inserts a new row rather than mutating a status column, so
a run's decision history is just its rows in order.

**A real, consequential choice made explicitly, not by default**: this
codebase has two competing precedents for "who approved this."
`financial_close` uses real `core.auth`-verified identity
(`Token`/`session_for_token()`) for governed decisions. But the two
closest UI/UX analogs to what RI-5 needed - `credit_risk`'s
`OrderDecisionPreparationPanel` and `accounts_payable`'s
`APWarehouseApprovalQueue` - both deliberately use free-text, unverified
identity, since they're evidence/recommendation logs, not final
external-facing actions; `route_intelligence` itself has no identity
mechanism wired in anywhere (every existing `updated_by` field is unset
from the frontend). Asked the user directly rather than picking silently
- chosen: **free-text `decided_by`**, matching this module's own
existing convention and the credit_risk/accounts_payable precedent.
Real `core.auth`-verified identity is the right call once a decision
here actually triggers an external (Samsara) write - RI-6+, not before.
Given the free-text choice, this slice also skips `financial_close`'s
heavier hash-chained tamper-evidence machinery (that pattern exists
specifically to pair with verified identity) - a plain append-only
table is consistent with this module's existing simplicity level.

Still explicitly deferred: real interactive plan editing (drag-and-drop
stop reassignment) for the "modified" decision - recorded as a free-text
note this slice, not an editor, since nothing real exists yet to edit
against; the full "Route Command Center"/"Daily Planning Workspace"
visual designs (maps, capacity bars, live route progress) - these need
real customer/vehicle location data to render anything meaningful;
publishing an approved plan anywhere (RI-6's job entirely).

## RI-7: live fleet monitoring (added 2026-09-05, RI-6 skipped)

`GET /live-fleet/{warehouse_number}` - real-time vehicle status,
computed fresh every call (no snapshot, same "no staleness" philosophy
as the Data Quality Center).

**The user explicitly skipped RI-6** ("controlled Samsara route
publishing" - a Level-3 change per the program plan's section 9, since
it can affect live delivery operations) and asked to go straight to
RI-7 ("live monitoring and future-stop replanning") with nothing
written externally in this increment either.

Research + live verification reshaped this slice in both directions:
- **"Future-stop replanning" stays fully deferred, not attempted.** It
  needs an approved plan to replan against (still impossible - 0 real
  customer profiles have coordinates, 0 warehouses have a saved
  location, unchanged since RI-4/RI-5) and real stop-level arrival/
  departure data (still blocked on the Samsara webhook receiver +
  public HTTPS endpoint, unchanged since RI-0). Skipping RI-6 also
  removes the other prerequisite - a *published* plan to monitor -
  entirely.
- **"Live monitoring" turned out to be more buildable than expected.**
  `get_live_gps()` (built in RI-0, never actually called against the
  real API until this session) was live-verified for the first time:
  it works, and returns real fields nobody had confirmed before -
  `onTrip` (bool), `latitude`/`longitude`, `location` (human-readable),
  `speed`, `heading`, `time` (epoch ms). `onTrip` is exactly the "which
  vehicles are active right now" signal - a better source than
  `route_actual_runs`, whose `completion_status` can only ever be
  `"completed"` by construction (`list_historical_routes()` hardcodes
  that filter in its own request, so in-progress trips are never even
  requested from Samsara).

`get_live_fleet_status(warehouse_number)` gathers active vehicles home-
based at the warehouse and calls `get_samsara_live_gps()` per vehicle -
there is no bulk "all vehicles' live locations" Samsara endpoint in this
provider today. A single vehicle's failure (no Samsara link, no live
location on file, or a real API error) is caught and reported as
`unavailable_reason` rather than failing the whole response - same
"don't let one bad item sink the whole report" discipline as the Data
Quality Center. `speed`'s real unit is unconfirmed anywhere in Samsara's
docs or this codebase - passed through as-is rather than guessed at.

Checked `backend/modules/automations/`'s `AutomationScheduler` as a way
to make this refresh automatically - real and running, but its finest
schedule granularity is daily (weekly/monthly beyond that); "custom"/
cron scheduling explicitly raises "not enabled yet." So this stays a
manual, on-demand "Refresh," same as every other RI tab - appropriately,
since caching a live GPS snapshot would defeat the point of it being
live.

Still explicitly deferred: future-stop replanning entirely (see above);
RI-6 itself (out of scope per the user's direct instruction);
automatic/scheduled refresh (no sub-daily scheduling infrastructure
exists); a fleet-wide bulk live-location endpoint (Samsara's API this
module uses only exposes per-vehicle lookups).

## RI-8: permanent-route candidate detection (added 2026-09-05)

`POST /network-review/compute` (body: optional `warehouse_number`),
`GET /network-review/runs/{run_id}`.

Section J of the program plan describes a structural review firing on
six trigger conditions, then ETOP simulating six route-redesign
scenarios, producing a recommendation with proposed customers,
territory, expected miles/hours/cost, service-level impact, and a
confidence level. **Re-checked reality before designing**: still 0 real
customer profiles with coordinates and 0 warehouse locations (unchanged
since RI-4) - this still blocks a customer-density heatmap, proposed-
customer/territory lists, and real route-redesign simulation, since
RI-4's optimizer has nothing real to simulate against.

**What's different this time**: RI-3 already computed and *stored* 305
real per-warehouse, per-weekday capacity assessments the last time it
ran. Three of the plan's six structural-review trigger conditions are
directly computable from that already-real, already-stored data, with
zero new external calls:
- "Median utilization exceeds 85% at least three days per week" -
  `p50_weight / weight_capacity` per stored weekday, counted across
  the week.
- "P90 utilization exceeds 100% at least twice per week" - directly
  countable from the already-stored `status == "split_recommended"`
  assessments (RI-3's own classification, reused as-is).
- "Forecast shows a route exceeding capacity within four to eight
  weeks" - a recurring `split_recommended` day-of-week pattern recurs
  every week it holds - a real, honest (if simplified) reading of this
  condition, not a fabricated multi-week projection.

The other three conditions (backup-capacity usage frequency, overtime/
service risk, customer-cluster transfer history) have no real data
source anywhere in this codebase and are **not evaluated** - not
defaulted to "no risk," which would be a worse kind of wrong.
`compute_network_review()` persists a run + one
`PermanentRouteCandidate` row per warehouse that triggers at least one
of the three real conditions, with real `forecasted_weekly_weight_demand`/
`current_weight_capacity`/`capacity_gap` and a `confidence` level
derived from the minimum real `sample_size` seen that week. Every
candidate also carries an explicit `unavailable_fields` list - the
plan's required recommendation fields this slice genuinely can't
compute (`proposed_customers`, `territory`, `expected_miles_hours`,
`expected_cost`, `service_level_impact`) - shown to the user as a
constructive "not yet available" note, not silently omitted.

**Live-verified 2026-09-05** against the real, already-stored 305 RI-3
assessments (see the RI-3 section above for how that data was
generated) - reports real candidate counts and real trigger reasons per
warehouse, with `unavailable_fields` populated on every candidate.

Still explicitly deferred: full route-redesign scenario simulation
(current+flex driver, one additional route, rebalanced adjacent routes,
different vehicle sizes, alternative warehouse assignments) - needs
RI-4's optimizer to have real customer stops to move around, which it
doesn't yet; proposed-customer lists, territory boundaries, a customer-
density heatmap - all need real customer coordinates; the three trigger
conditions with no real data source (reported as not evaluated, not
guessed at); a multi-run historical trend of the trigger evaluation
itself over calendar time (this slice evaluates real 8-week-lookback
data within one run, not a trend across many past runs).

## Samsara integration status (added 2026-09-04)

Real, confirmed against developers.samsara.com the day this was built:

- `GET /samsara/vehicles` - `/assets?type=vehicle`
- `GET /samsara/drivers` - `/fleet/drivers`
- `GET /samsara/driver-vehicle-assignments` - `/fleet/driver-vehicle-assignments`
- `GET /samsara/customer-geofence/{customer_number}` - `/addresses`,
  filtered client-side by `externalIds`. **K&M has not yet established a
  convention for tagging a Samsara address with the ETOP/MaddenCo
  customer number as an externalId** - this returns nothing useful until
  that tagging exists in Samsara itself. Worth a conversation with
  whoever administers the Samsara account.
- `GET /samsara/vehicles/{vehicle_id}/live-gps` - `/v1/fleet/locations`
  (note the different response envelope from every other endpoint here -
  see the method's docstring)

`get_samsara_provider()` switches automatically between the real
`SamsaraApiProvider` and `UnconfiguredSamsaraProvider` based on whether
`SAMSARA_API_TOKEN` is set (see `.env.docker.example`) - no code change
needed once a token exists.

**Not implemented - genuinely can't be, not just deferred**:
`list_actual_stops()` (route-stop arrival/departure). Samsara delivers
this as webhook events (`RouteStopArrival`/`RouteStopDeparture`,
currently Beta), not a pollable REST list - there is no GET endpoint to
call. Reading this needs a webhook receiver in this backend (an endpoint,
signature verification, and somewhere to store incoming events) - real,
separate infrastructure work, not a provider swap. This blocks the
Samsara-based "customer service-time intelligence" (program plan section
D) and historical-route "actual stops" reconstruction (RI-1) until that
receiver exists.

**Blocked on a public HTTPS endpoint, not on code** (confirmed 2026-09-04):
Samsara's cloud has to be able to reach the webhook URL over the public
internet - this backend is currently a local/on-prem Docker deployment
(`https://localhost`, self-signed cert), which Samsara's servers cannot
reach. Deliberately not building the receiver until either a real public
domain exists for ETOP, or a tunnel (ngrok/Cloudflare Tunnel) is stood up
for testing - user's explicit call, not a technical dead end.

Confirmed webhook mechanics for whenever this is picked up (via
`developers.samsara.com/docs/webhooks`):
- **Delivery**: `POST`, `Content-Type: application/json`, from Samsara's
  static IPs. Must return a 2XX promptly; non-2XX retries 5x with
  exponential backoff.
- **Signature verification**: `X-Samsara-Signature: v1=<hex>` header,
  HMAC-SHA256. The webhook's secret (shown once in the Samsara dashboard
  at creation) is base64-encoded and must be decoded before use. Message
  to sign is `v1:<X-Samsara-Timestamp header value>:<raw request body>`.
  **Never skip this check** - an unauthenticated webhook receiver is a
  real attack surface (anyone who finds the URL could inject fake
  RouteStopArrival events).
- **Payload**: `eventId`, `eventMs`, `eventType` (`"Alert"` or `"Ping"`),
  plus event-specific data - RouteStopArrival's fields are
  `data.route.id`, `data.routeStopDetails.id`, `data.vehicle.id`,
  `data.driver.id`, `data.routeStopDetails.actualArrivalTime`,
  coordinates in `data.route.stops[].singleUseLocation`.
- When built, the endpoint should live at
  `/api/v1/route-intelligence/samsara/webhook` and a new
  `samsara_webhook_events` table (append-only, per this codebase's
  established convention for evidence logs) should store every verified
  event before any processing - this is the deferred `samsara_event_log`
  table from the original program plan's section 7.

`list_historical_routes()` maps to `/trips/stream` (GPS-derived actual
trips), not Samsara's "Routes" feature (which is for dispatching planned
routes - the RI-6+ write-back target, not a read source for historical
execution).

## What this slice actually does

- **Data Quality Center** (`GET /data-quality`): live, always-fresh
  cross-check of every K&M customer's MaddenCo route code (`TMCUST.
  CUROUTECD`) and store number (`TMCUST.CUSTORENUM`) against MaddenCo's own
  route (`KMTDTA.KMROUTES`) and warehouse (`KMTDTA.WH_DASHBOARD_LOCATIONS`)
  masters, plus completeness checks on this module's own master data
  (customer coordinates, vehicle capacity profiles, driver availability).
- **Master-data management**: CRUD for `route_vehicles`,
  `route_vehicle_capacities`, `route_drivers`, `route_driver_availability`,
  `route_customer_profiles`, and `route_business_rules` (a generic
  config-key/value store, so the capacity-status thresholds this platform
  will eventually need are configuration, not a code change).
- **Warehouse & route browser** (read-only): passes through to
  `freight_logistics_service`, which already reads MaddenCo's route master,
  warehouse master, and per-route load manifest.

## What this slice deliberately does NOT do yet

Building the full 27-table schema, all 7 UI workspaces, and every increment
in one pass would produce mostly-empty scaffolding with no real logic
behind it - this codebase's own `docs/Architecture/Module Standards.md`
explicitly warns against exactly that. Each of the following gets built
alongside its real backing logic in its own increment, not stubbed out now:

- Route plans, optimization, backup-split scenarios, forecasting beyond the
  `SimpleDayOfWeekForecastProvider` baseline, network-design/permanent-route
  recommendations, and their corresponding UI workspaces (Command Center,
  Daily Planning, Route Detail, Backup Split, Capacity Forecast, Network
  Design).
- Any Samsara write-back (RI-6+). Raw Samsara reads (vehicles, drivers,
  assignments, live GPS, geofences) are now real - see "Samsara
  integration status" above - but geofence-based service-time
  intelligence and historical-route "actual stops" reconstruction are
  still blocked on a webhook receiver that doesn't exist yet (also
  above).
- `providers/routing_solver_provider.py` (planned: OR-Tools) and
  `providers/weather_provider.py` are likewise real interfaces with
  Unconfigured stubs - genuine future engineering work, not something to
  fake today.
- `providers/travel_matrix_provider.py`'s `HaversineTravelMatrixProvider`
  IS real (straight-line distance needs no external vendor), but is an
  explicitly crude placeholder - no road network, no traffic - documented
  in its own module docstring as something to replace once travel-time
  accuracy actually matters for a downstream feature.
- `samsara_sync_state`/`samsara_entity_mappings`/`samsara_event_log` tables
  are not created - they should be designed against the real Samsara API
  shape once access exists, not guessed now.
- `route_locations`/`route_templates` tables are not created - they'd
  duplicate MaddenCo's own `WH_DASHBOARD_LOCATIONS`/`KMROUTES`, which
  `freight_logistics_service` already reads.

## Open question: MaddenCo has no live open-order table

Per `sales_order_visibility/repository.py`'s own docstring and the data
dictionary, MaddenCo has **no `TMORDH`/`TMORDL`-style live open/committed-
order feed**. "Orders" can only come from `TMIHSH`/`TMIHSL` (closed/
invoiced history - good for demand forecasting) or `INWHLOAD` (today's load
manifest, already loaded/dispatched - good for "what's actually on a route
today"). The original program plan's "committed orders / order cutoff"
language assumes a live intraday feed that doesn't exist in the schema this
codebase has confirmed access to. **Worth confirming with the MaddenCo/data
resource contact** whether such a feed exists under a table name not yet
documented in `backend/sql_knowledge/generated/data_dictionary.json` - this
materially affects what "today's committed deliveries" can mean for the
Route Command Center increment later.

## Data-quality scope note

The Data Quality Center's customer population is every `TMCUST` row with
`CUSTORENUM > 0`, since TMCUST has no confirmed active/inactive flag
elsewhere in this codebase. **Confirmed against live MaddenCo data
2026-09-04: 137,515 TMCUST rows match `CUSTORENUM > 0`** - almost
certainly far more than K&M's real active customer count, and the first
live run's route-code match rate (12.7% of a capped 20,000-row sample)
was dominated by what look like legacy/inactive records and internal
inter-warehouse "transfer" pseudo-customers (e.g. "LOCATION 6 TRANSFER"),
not real delivery customers with a stale route code. **This is a real,
documented limitation of the current population filter, not a discovery
that 87% of K&M's routing data is broken** - `CUSTORENUM > 0` is too loose
a definition of "a real, current customer" to use as-is for a meaningful
match-rate metric. Needs a better active-customer definition (e.g. a
last-activity-date cutoff) before the match-rate numbers should be treated
as a real KPI - worth a follow-up conversation with the MaddenCo/data
resource contact rather than guessing at a cutoff here.
