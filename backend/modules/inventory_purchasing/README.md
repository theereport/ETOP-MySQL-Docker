# Inventory & Purchasing — Increment 1 Backend

Read-only product evidence workspace over MaddenCo (schema `DTA273`): item
identity and costing (`TMPROD`), month-end inventory valuation trend by
store/vendor/class (`EOMINV`), open purchase-order exposure for the item
across every vendor (`TMPOHD`/`TMPODT`), and receiving history (`TTRCVD`
joined to `TMPOHD`). This is the product-centric counterpart to Vendor
Intelligence, which reads the same PO/receiving tables from the vendor
angle; this module reads them by product number instead. ETOP owns one
local append-only record type: professional notes on a product.

This module computes no reorder point, safety-stock level, demand forecast,
turnover rate, or ERP write. Every response is either a direct MaddenCo
read or an explicit arithmetic sum/count/average over that read (stated in
each evidence section), never an inferred judgment.

## Contracts

- `GET /api/v1/inventory-purchasing/health`
- `GET /api/v1/inventory-purchasing/products/search?q=`
- `GET /api/v1/inventory-purchasing/products/{product_number}`
- `GET /api/v1/inventory-purchasing/products/{product_number}/notes`
- `POST /api/v1/inventory-purchasing/products/{product_number}/notes`

## Evidence boundary

- **Identity** — `TMPROD`. A product may have one row per store
  (`PDSTORE`); the identity/costing/inventory-position read picks the
  first store row by `PDSTORE` order, and search collapses multi-store
  rows to one entry per `PDNUMBER` with `MAX()` (a plain aggregate, not a
  business calculation) so the same item does not appear once per store.
  `active` follows the same convention as Vendor Intelligence: the delete
  code (`PDDELETE`) is treated as active when blank or `A`.
- **Costing** — `TMPROD`'s own vendor/actual/replacement/last-year cost
  fields and its six price levels. No margin, markup, or pricing
  recommendation is computed.
- **Inventory position** — `TMPROD`'s own last-committed on-hand, on-order,
  allocated, configured min/max, inventory-turns, and lead-time fields.
  These are the product/store master row's own stored values, not a
  verified live, real-time, per-warehouse feed — see the gaps below.
- **Month-end inventory** — `EOMINV` rows for this product's `PARTNUM`,
  most recent periods first. These are periodic month-end snapshots keyed
  by store/month/year/vendor/class, never presented as current stock.
  "Latest period" totals are a plain sum of `UNITS`/`TOTALCOST` across
  every store row sharing the most recent year/month present.
- **Purchase exposure** — Open orders are `TMPOHD` rows carrying at least
  one `TMPODT` line for this product (`TPDPRD`) where the header complete
  flag is not `Y`, across every vendor with an open order for the item.
  Ordered/received/backorder quantities are summed from this product's own
  `TMPODT` lines per PO; line total cost is `SUM(TPDQTYORD * TPDUNTCST)`
  and average unit cost is the mean of `TPDUNTCST` across those lines.
- **Receiving** — `TTRCVD` filtered by product number (`TRCDNUMPRD`), left
  joined to `TMPOHD` on PO number to read the vendor number (`TPHNBVND`),
  since receiving does not carry the AP vendor number directly. Cost
  variance is MaddenCo's own recorded `TRCDCOSDIF` value per line.
- **Notes** — Local SQLite, append-only (update/delete blocked by
  trigger), each note carries an evidence snapshot and SHA-256 integrity
  marker over the product evidence at the time the note was written,
  following the same pattern as `vendor_intelligence` and `credit_risk`.

## Known performance characteristic

Verified against the live MaddenCo database: `EOMINV` lives in schema
`KMTDTA` (queries are schema-qualified accordingly) and has ~48M rows with
`PARTNUM` as the last column of its composite primary key, so a
`PARTNUM`-only filter cannot use an index. `TMPODT` (~6.2M rows) has the
same problem for `TPDPRD`. Both are real MaddenCo indexing constraints ETOP
cannot alter. `month_end_inventory` and `purchase_exposure` each catch the
resulting statement-timeout failure and report
`status: "unavailable_source_capability"` with an explanation instead of
failing the whole product-evidence request — this reflects a source-side
limit, not an absence of inventory or purchase-order data.

## Decisions this module does not invent

- A reorder-point or safety-stock formula. MaddenCo's own configured
  order-generation thresholds (`TMPROD.PDMIN` / `PDMAX`), when populated,
  are shown as-is; ETOP computes no reorder point of its own.
- A real-time, on-hand-by-warehouse quantity. Only the periodic month-end
  snapshot (`EOMINV`/`INEOMINV`) is available in the current schema for
  inventory-position trending.
- A demand-forecasting or turnover-rate calculation. `TMPROD.PDINVTURNS`,
  when populated, is shown as MaddenCo's own stored value, not an
  ETOP-derived figure.
- A cross-reference between `TMPROD.PDVENDOR` (a short product-master
  vendor code) and `PMVEND`'s numeric vendor number used by Vendor
  Intelligence; no verified mapping is joined here.
- Price history (`TMPDHS`) and extended product attributes such as
  warranty/UTQG (`TMPDIF`) exist in the schema but are out of scope for
  this increment.

## Blueprint trace

`ETOP-Blueprint/` does not exist in this repository, so there is no ADR/SRC
baseline to trace into. This module follows the architectural pattern
established by `backend/modules/credit_risk` and
`backend/modules/vendor_intelligence` as its de facto baseline instead.
