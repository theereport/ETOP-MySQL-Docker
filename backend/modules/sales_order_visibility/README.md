# Sales Order Visibility — Increment 1 Backend

Read-only invoice-forward visibility workspace over MaddenCo (schema
`DTA273`): invoice header search and detail (`TMIHSH`), line items
(`TMIHSL`) enriched with vehicle-fit detail (`TMIHSI`), invoice memos
(`TMIHSM`), credit-authorization history (`TMIHSA`), delivery cross-
reference (`INWHLOAD`), and a customer/product sales-summary view
(`TMSALE`). ETOP owns one local append-only record type: professional
notes on an invoice.

## SCOPE BOUNDARY — read this first

**MaddenCo (DTA273) has no open/pre-invoice order-entry table.** A full
scan of the schema's 87 tables found nothing resembling an "OEHDR"/open-
order-header table — only invoice-**history** tables (`TMIHS*`) and the
`TMSALE` sales-summary fact table. Those represent completed or in-process
**invoices**, not a live pending-order queue. This module is therefore
scoped as **invoice-forward visibility only**: it shows what has already
been invoiced (and that invoice's line/memo/authorization/delivery
detail), never a queue of orders awaiting fulfillment. Nothing in this
module's name, endpoints, or UI should be read as live order-entry or
pipeline tracking.

This module computes no fulfillment score, SLA judgment, on-time-ship
determination, ERP write, approval, or hold action. Every response is
either a direct MaddenCo read or an explicit arithmetic sum/count/product
over that read (stated in each evidence section).

## Contracts

- `GET /api/v1/sales-order-visibility/health`
- `GET /api/v1/sales-order-visibility/invoices/search?q=&customer_number=`
- `GET /api/v1/sales-order-visibility/invoices/{invoice_number}`
- `GET /api/v1/sales-order-visibility/invoices/{invoice_number}/notes`
- `POST /api/v1/sales-order-visibility/invoices/{invoice_number}/notes`
- `GET /api/v1/sales-order-visibility/sales-summary?customer_number=&product_number=`

## Evidence boundary

- **No open-order queue** — see the scope boundary above. This is the
  single most important boundary of this module and is repeated in the
  `gaps` array of every invoice-evidence response (`open_order_queue`).
- **Invoice header** — `TMIHSH`, left-joined to `TMCUST` (`CUNUMBER`/
  `CUNAME`) for the customer name only. Dates (`TIHHDTEINV`, `TIHHDTEDUE`,
  `TIHHDTECRT`, `TIHHDTECHG`) are MaddenCo's own stored `YYYYMMDD`
  strings. Void/direct-ship/pickup are `TIHHVOIDYN`/`TIHHDIRSHP`/
  `TIHHPICKUP` flags read verbatim.
- **Line items** — `TMIHSL` per invoice/line number, left-joined in
  application code to `TMIHSI` (vehicle make/model/year/mileage) on
  matching invoice + line number. `TMIHSL` has no stored extended-amount
  column, so each line's `extended_price` is the arithmetic product of
  `TIHLQTY` × `TIHLPRC` — stated explicitly in the response
  (`extended_price_not_stored` gap).
- **Memos** — `TMIHSM` message lines for the invoice, in line-number
  order.
- **Authorizations** — `TMIHSA` credit-authorization request/grant rows
  for the invoice. This is MaddenCo's own authorization log, not a
  computed credit-risk judgment.
- **Delivery** — `INWHLOAD` rows for the invoice number. A line is
  `delivered` only when `DLVSTAMP` is not null. When an invoice has zero
  `INWHLOAD` rows the response reports `manifest_status:
  "no_records_found"` — explicitly not evidence of a missed delivery,
  since will-call/pickup invoices are never routed to a delivery load
  (`delivery_manifest_optional` gap).
- **Sales summary** — `TMSALE`, a pre-aggregated fact table by customer,
  product, class, type, and year-period. Totals are plain sums over the
  rows returned for the requested filter; this is explicitly labeled as a
  summary fact, not an invoice-level list.
- **Notes** — Local SQLite, append-only (update/delete blocked by
  trigger), each note carries an evidence snapshot and SHA-256 integrity
  marker over the invoice evidence at the time the note was written,
  following the same pattern as `vendor_intelligence`/`credit_risk`.

## Decisions this module does not invent

- **No open/pre-invoice order queue** exists in the current MaddenCo
  schema. This module is invoice-forward history only — completed or
  in-process invoices — never a live pending-order pipeline. Do not read
  any endpoint or UI element here as order-entry tracking.
- No fulfillment SLA or on-time-ship definition is computed. Delivery
  status is INWHLOAD's own recorded delivered/not-delivered state, never
  a performance judgment.
- No vendor/customer rating, rank, or automatic recommendation.
- No terms-code or type-of-sale-code-to-description mapping (no governed
  lookup table is connected in this increment).

## Blueprint trace

`ETOP-Blueprint/` does not exist in this repository, so there is no
ADR/SRC baseline to trace into. This module follows the architectural
pattern established by `backend/modules/credit_risk` and
`backend/modules/vendor_intelligence` as its de facto baseline instead.
