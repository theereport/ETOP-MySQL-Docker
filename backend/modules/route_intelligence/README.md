# Route Intelligence

A predictive, capacity-aware, human-governed delivery-routing platform,
built incrementally against the "ETOP Route Intelligence" program plan
(RI-0 through RI-9). This module is the **first slice**: the correct
structural foundation plus one genuinely working feature, built entirely
against live MaddenCo data with no Samsara dependency (Samsara API access
does not exist yet, but the provider architecture below is built so that
access can be dropped in later with no changes to any caller).

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
- Everything Samsara-dependent: vehicle/driver/GPS reads, geofence-based
  service-time intelligence, historical-route reconstruction, and any
  Samsara write-back. `providers/samsara_provider.py` defines the exact
  interface (`SamsaraProvider`) this module will call once access exists;
  today it's wired to `UnconfiguredSamsaraProvider`, which raises a clear
  error instead of silently returning empty data.
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
