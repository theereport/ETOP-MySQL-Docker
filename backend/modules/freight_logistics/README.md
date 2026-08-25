# Freight & Logistics — Increment 1 Backend

Read-only route delivery evidence workspace over MaddenCo (schema `DTA273`):
route schedule/definition (`KMROUTES`, labeled with the existing
warehouse-dashboard application's own `WH_DASHBOARD_LOCATIONS` /
`WH_DASHBOARD_ROUTES` configuration), the route's load manifest with
delivered/undelivered counts and elapsed-time arithmetic (`INWHLOAD`), COD
payment-collection evidence (`WHSIGPAY` joined to its own correction log
`WHSIGPAYC` and detail notes `WHSIGPAYD`), driver-recorded delivery
exceptions/credit requests (`WHSIGNOTE`), driver-recorded quantity
adjustments (`WHSIGADJ`), signature-capture device sessions (`WHSIGRTE`),
and proof-of-delivery signature image metadata (`WHSIGIMG`). ETOP owns one
local append-only record type: professional notes on a route.

This module computes no route profitability, cost-efficiency, on-time
percentage, or COD reconciliation decision, and it never writes to MaddenCo.
Every response is either a direct MaddenCo read or an explicit arithmetic
sum/count/average over that read (stated in each evidence section), never an
inferred judgment.

## Contracts

- `GET /api/v1/freight-logistics/health`
- `GET /api/v1/freight-logistics/routes/search?q=`
- `GET /api/v1/freight-logistics/routes/{route_code}`
- `GET /api/v1/freight-logistics/routes/{route_code}/notes`
- `POST /api/v1/freight-logistics/routes/{route_code}/notes`

## Evidence boundary

- **Identity & schedule** — `KMROUTES`. `schedule` pairs each day's
  `DLVxxx` Y/N delivery flag with that day's `NUMxxx` scheduled-stop count
  (both real columns, no computation). `active` mirrors `RTESTATUS` using
  the same `''`/`'A'` = active convention already established for MaddenCo
  record-status codes elsewhere in this codebase.
- **Warehouse label** — `warehouse_location_name` is an exact numeric join
  of `KMROUTES.RTEWHSE` to `WH_DASHBOARD_LOCATIONS.LOCATION_NUMBER`.
  `directions` lists `WH_DASHBOARD_ROUTES` rows for that same warehouse
  whose `INCLUDED_ROUTES` text field contains this route's code as a
  comma-separated entry (`FIND_IN_SET`, a text-containment match, not a
  foreign key). Both `WH_DASHBOARD_*` tables are an existing separate
  warehouse-dashboard application's own configuration, not MaddenCo
  transactional data, and are presented as reference/config evidence only.
  `WH_DASHBOARD_PASS_THRU` (location-to-location pass-through config) is
  not used by this module — it describes cross-location routing, not a
  single route's own evidence.
- **Load manifest** — `INWHLOAD` rows for the route. A line is "delivered"
  when `DLVSTAMP` holds a real timestamp; MaddenCo represents an
  outstanding line with an absent/zero delivery timestamp, read here as
  null. `elapsed_minutes` is `DLVSTAMP` minus `CRTSTAMP` in minutes,
  computed only when both timestamps are present.
  `average_elapsed_minutes` is the arithmetic mean of `elapsed_minutes`
  across delivered lines only. `delivered_count` / `undelivered_count` /
  `total_weight` / `total_quantity` are direct counts/sums over the same
  rows. None of this is an on-time-delivery percentage.
- **COD payments** — `WHSIGPAY` rows for the route, each enriched with its
  own `WHSIGPAYC` correction history (joined by casting `WHSIGPAY.ID` to
  text against `WHSIGPAYC.PAYMENTID`, since `WHSIGPAYC` stores the payment
  id as `varchar(8)`) and `WHSIGPAYD` detail notes (joined by the matching
  numeric id). `received_count` / `unreceived_count` are direct counts of
  MaddenCo's own `RECEIVED` flag. This module has no COD reconciliation
  authority and performs no ERP write.
- **Delivery exceptions** — `WHSIGNOTE`, MaddenCo's own driver-submitted
  exception/credit-request record. `approved` reflects MaddenCo's own
  `APPROVED` flag; this module does not approve, deny, or write back any
  exception.
- **Delivery adjustments** — `WHSIGADJ`, driver-recorded line-level
  quantity adjustments uploaded from the delivery device.
- **Signature-capture sessions** — `WHSIGRTE`, records of when a handheld
  signature-capture device opened a session for the route. Not a
  proof-of-delivery completeness metric.
- **Signature images** — `WHSIGIMG` has no `ROUTE` column, so it is joined
  to `INWHLOAD` on the shared `CUSTNUM`/`INVNUM` keys to scope it to this
  route's load manifest. Only the signer name and image file name are
  returned; the underlying image file is never retrieved or rendered.
- **Notes** — Local SQLite, append-only (update/delete blocked by
  trigger), each note carries an evidence snapshot and SHA-256 integrity
  marker over the route evidence at the time the note was written,
  following the same pattern as `vendor_intelligence` and `credit_risk`.

### A documented schema assumption

`KMROUTES.RTECODE` and `INWHLOAD.ROUTE` are both `varchar(2)`, so this
module resolves and joins on that two-character route code throughout.
The `WHSIG*` family declares `ROUTE` as `varchar(8)`; without a live
database to inspect actual populated values, this module still filters
those tables by exact string equality against the same route code. If a
`WHSIG*` table actually stores an internal route key rather than the
two-character code, those specific evidence sections will read back empty
for a real route rather than silently substituting a different value —
this is disclosed here and in the `route_code_global_uniqueness` gap
rather than hidden.

## Known performance characteristic

Verified against the live MaddenCo database: `KMROUTES`, `INWHLOAD`, and the
`WHSIG*` family live in schema `KMTDTA`, not `DTA273` — every query here is
schema-qualified accordingly. `INWHLOAD` (~5.3M rows) has no index whose
leading column is `ROUTE`, so filtering by route requires a full scan;
`get_route_evidence` for a single route currently takes on the order of a
minute in practice. This is a MaddenCo indexing constraint ETOP cannot
alter, not a code defect. `get_payment_details` and `get_signature_images`
use `STRAIGHT_JOIN` to force MySQL to drive from the smaller/filtered table
first — without it, both queries exceeded the statement timeout entirely.

## Decisions this module does not invent

- A route profitability, cost-per-stop, or efficiency formula.
- A definition of "on-time" delivery or an on-time percentage.
- COD payment reconciliation authority or any write-back to MaddenCo.
- Retrieval/rendering of the underlying proof-of-delivery signature image
  (only its recorded file name is surfaced).
- Disambiguation of a `RTECODE` that repeats across more than one
  warehouse (the first matching `KMROUTES` row is used).

## Blueprint trace

`ETOP-Blueprint/` does not exist in this repository, so there is no ADR/SRC
baseline to trace into. This module follows the architectural pattern
established by `backend/modules/credit_risk` and
`backend/modules/vendor_intelligence` as its de facto baseline instead.
