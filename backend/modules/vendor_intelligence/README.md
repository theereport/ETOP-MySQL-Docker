# Vendor Intelligence — Increment 1 Backend

Read-only vendor evidence workspace over MaddenCo (schema `DTA273`): vendor
identity and purchase volume (`PMVEND`), open purchase orders
(`TMPOHD`/`TMPODT`), receiving history and recorded cost variance (`TTRCVD`
joined to `TMPOHD`), and current/paid accounts-payable evidence
(`PMHD`, `PTHD`/`PTPY`). ETOP owns one local append-only record type:
professional notes on a vendor.

This module computes no vendor score, rating, rank, approval, hold, PO
action, or ERP write. Every response is either a direct MaddenCo read or an
explicit arithmetic sum/count over that read (stated in each evidence
section), never an inferred judgment.

## Contracts

- `GET /api/v1/vendor-intelligence/health`
- `GET /api/v1/vendor-intelligence/vendors/search?q=`
- `GET /api/v1/vendor-intelligence/vendors/{vendor_number}`
- `GET /api/v1/vendor-intelligence/vendors/{vendor_number}/notes`
- `POST /api/v1/vendor-intelligence/vendors/{vendor_number}/notes`

## Evidence boundary

- **Identity** — `PMVEND`. Only free-text address lines are available; the
  current schema has no discrete city/state columns for vendors (unlike
  `TMCUST`). The federal ID is reported as a boolean "on file" flag only —
  the raw value is never returned, to avoid exposing a sole-proprietor
  vendor's SSN/EIN through this API. Bank account and routing numbers
  (`PVACCBNK`/`PVROUBNK`) are likewise reported only as a boolean
  `eft_bank_info_on_file` flag — the raw values are never returned. The
  1099 code (`PVCOD1099`) and manual 1099 amount (`PVAMT1099`) are exposed
  since they carry no equivalent sensitivity.
- **Purchase volume** — `PMVEND`'s own MTD/YTD/last-year purchase and
  discount fields, plus last-paid amount/date/check number. Discount
  capture rate is discount taken divided by (discount taken + discount
  lost) for the same period, a stated arithmetic ratio over `PMVEND`'s own
  `PVDISCMTD`/`PVDISCYTD`/`PVDISCLMTD`/`PVDISCLYTD` fields — not a vendor
  performance score.
- **Purchase orders** — Open orders are `TMPOHD` rows for the vendor where
  the complete flag is not `Y`. Ordered/received/backorder quantities are
  summed from `TMPODT` lines per PO. This is not an on-time or fill-rate
  score.
- **Receiving** — `TTRCVD` joined to `TMPOHD` on PO number (receiving does
  not carry the AP vendor number directly; it is derived through the PO).
  Cost variance is MaddenCo's own recorded `TRCDCOSDIF` value per line.
- **Payables** — Open invoices from `PMHD`; paid history from `PTHD` left
  joined to `PTPY`. These are the vendor's AP records, not a cash
  disbursement schedule.
- **Notes** — Local SQLite, append-only (update/delete blocked by trigger),
  each note carries an evidence snapshot and SHA-256 integrity marker over
  the vendor evidence at the time the note was written, following the same
  pattern as `credit_risk`'s assessments.

## Decisions this module does not invent

- Vendor scorecard weighting or a composite vendor rating.
- A definition of "on-time" delivery or receiving performance.
- Payment-terms code-to-description mapping (no lookup table is connected).
- Vendor rebate accrual (no rebate table exists in the current MaddenCo
  schema; out of scope for this increment).

## Blueprint trace

`ETOP-Blueprint/` does not exist in this repository, so there is no ADR/SRC
baseline to trace into. This module follows the architectural pattern
established by `backend/modules/credit_risk` and
`backend/modules/accounts_payable` as its de facto baseline instead.
