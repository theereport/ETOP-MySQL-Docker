# AR Collections — Increment 1 Backend

Read-only AR collections evidence workspace over MaddenCo (schema `DTA273`):
itemized open A/R items (`TMAROP`), AR transaction/payment history
(`TTNARH`/`TTNARD`), read-only GL distribution reference lines (`TTNGL`),
the ERP's own existing collection and credit-management notes
(`CCROLNOTE`, `TMCRMH`/`TMCRMD`), and the periodic aging/credit snapshot
trend (`TMCCH`). ETOP owns one local append-only record type: professional
collections notes on a customer.

This module computes no collections priority score, rank, dunning
recommendation, hold, or ERP write. Every response field is either a direct
MaddenCo read or an explicit arithmetic sum/count/day-difference over that
read (stated in each evidence section), never an inferred judgment.

Customer identity (name/address) is obtained from the existing
`modules.customer_360.service.customer_service` singleton rather than a
second read of `TMCUST`, the same dependency pattern `credit_risk` uses.

## Contracts

- `GET /api/v1/ar-collections/health`
- `GET /api/v1/ar-collections/customers/{customer_number}`
- `GET /api/v1/ar-collections/customers/{customer_number}/notes`
- `POST /api/v1/ar-collections/customers/{customer_number}/notes`

## Evidence boundary

- **Customer identity** — Retrieved through Customer 360's `summary()` over
  `TMCUST`; this module does not query `TMCUST` directly. Used only for a
  name/address header.
- **Open A/R** — `TMAROP` rows filtered to the customer and to
  `TAROHISTYN <> 'Y'`, one row per currently open invoice/debit/credit.
  `total_open_amount` is the arithmetic sum of `TAROAMTOPN` across the
  returned rows. `days_past_due` is today's date minus `TARODTEDUE`, in
  days (positive = past due, negative = not yet due); it is arithmetic,
  not a policy determination, and is `null` when no due date is present.
- **Item history** — Verified against live data: MaddenCo does not purge
  `TMAROP` once an item closes — it keeps the row and sets
  `TAROHISTYN='Y'`. This section is `TMAROP` filtered to that flag, most
  recent first, and is the customer's real closed/paid item history — the
  same columns as Open A/R, just on the closed side of the same table.
- **AR transaction history** — Headers are `TTNARH` rows for the customer
  (`TNARNUMCUS`). Applications are `TTNARD` rows joined to `TTNARH` on the
  shared `TNARSEQ` transaction sequence, showing which invoice(s)
  (`TNARINVAPL`) each payment or credit was applied against, with the GL
  account/division/department carried on the detail line. Verified against
  live data: `TTNARH`/`TTNARD` are scoped to a narrow adjustment workflow
  (`TNARTYPTRN`) and are commonly sparse or entirely empty in production —
  they are not this customer's primary transaction ledger; Item History
  above is. This is not a cash-application recommendation.
- **GL distributions** — `TTNGL` rows filtered directly on `TNGLNBCST`
  (customer number). `total_debit_amount`/`total_credit_amount` are
  arithmetic sums of `TNGLAMTDB`/`TNGLAMTCR`. Read-only reference only; no
  GL posting logic is performed or implied.
- **ERP collection notes** — `CCROLNOTE` rows for the customer
  (`CUSTNUM`), MaddenCo's own free-text collection notes, surfaced
  read-only.
- **ERP credit-management notes** — `TMCRMH` header rows for the customer
  joined to their `TMCRMD` detail lines (ordered by `TCMODNBSEQ`),
  MaddenCo's own existing credit-management to-do/notes records, surfaced
  read-only.
- **Aging/credit history** — `TMCCH` rows for the customer, most recent
  `TCCHDTE` first. This is a periodic snapshot table (one row per
  customer per period), not a real-time balance; it is presented as a
  trend, separate from the current `TMAROP` open-item list above.
- **Notes** — Local SQLite, append-only (update/delete blocked by
  trigger), each note carries an evidence snapshot and SHA-256 integrity
  marker over the AR collections evidence at the time the note was
  written, following the same pattern as `vendor_intelligence` and
  `credit_risk`'s assessments.

## Decisions this module does not invent

- The approved definition, weighting, or tie-breaking rule for
  "collections priority" — no ranking or scoring of customers is computed.
- A dunning schedule or statement cadence policy — ETOP does not compute
  or suggest contact timing.
- Write-back of a collection disposition, hold, or promise-to-pay into
  MaddenCo — out of scope; this module is read-only against the ERP.

## Blueprint trace

`ETOP-Blueprint/` does not exist in this repository, so there is no ADR/SRC
baseline to trace into. This module follows the architectural pattern
established by `backend/modules/credit_risk` and
`backend/modules/vendor_intelligence` as its de facto baseline instead.
