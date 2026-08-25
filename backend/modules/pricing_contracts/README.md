# Pricing & Contracts — Increment 1 Backend

Read-only pricing-override browser over MaddenCo (schema `DTA273`):
customer/vendor/product-specific discount and price-override records
(`TMDISC`), joined to a readable product-class label (`CLASSES`), plus a
readable customer-class reference (`CUCLASSES`). ETOP owns one local
append-only record type: pricing/contract notes scoped to a customer and,
optionally, a vendor code and/or product — the practical way to track
vendor rebate program commitments, since no rebate-accrual table exists in
this schema.

This module computes no final price, no contract-compliance score, and no
automatic recommendation. Every response is either a direct MaddenCo read
or an explicit literal pass-through of a stored column (stated in each
evidence section), never an inferred judgment.

## Contracts

- `GET /api/v1/pricing-contracts/health`
- `GET /api/v1/pricing-contracts/discounts/search?customer_number=&product_number=&product_class=&vendor_code=&active_only=&limit=&offset=`
- `GET /api/v1/pricing-contracts/discounts/lookup?customer_number=&vendor_code=&product_class=&product_number=&product_type=`
- `GET /api/v1/pricing-contracts/customer-classes/search?q=&active_only=`
- `GET /api/v1/pricing-contracts/notes?customer_number=&vendor_code=&product_class=&product_number=&product_type=`
- `POST /api/v1/pricing-contracts/notes`

## Evidence boundary

- **Discount / price-override records** — `TMDISC`. `DCPRICE` (override
  price), `DCAMTFIX` (fixed discount amount), `DCFACTOR`, and `DCPRICECD`
  (price code) are all returned as literal stored values side by side. No
  "effective price" or "final price" is computed: MaddenCo's own pricing
  engine resolves which mechanic applies using inputs this module does not
  have visibility into. `DCDELETE` (delete code) is surfaced as-is and also
  reduced to an `active` boolean (`true` when the delete code is blank).
- **Product class label** — `TMDISC.DCPRODCLAS` is left-joined to
  `CLASSES.CLASSNUM` for a readable `product_class_label`
  (`CLASSES.CLASSNAME`), plus `CLASSES.ITEMTYPE` and `CLASSES.ACTIVE`. Per
  the MYSQL Dictionary extract, `CLASSES` lives in schema `KMTDTA`, a
  different schema than `TMDISC`'s `DTA273`, on the same MySQL server. The
  join is written as a fully-qualified `KMTDTA.CLASSES` reference. **This
  assumes the read-only application login has a SELECT grant on `KMTDTA` in
  addition to `DTA273` — that has not been independently verified against
  the live server.** If the grant is missing, the join fails with an
  access-denied error surfaced as an HTTP 400 (via the shared
  `madden_database` error handling), not a silently wrong label.
- **Customer class reference** — `CUCLASSES` (also schema `KMTDTA`, same
  cross-schema caveat as above), exposed as its own read-only reference
  list. It is not joined to `TMDISC`: `TMDISC.DCCUSTNO` is a customer
  number, not a customer class code, so there is no direct FK path from a
  discount row to a customer class in this schema.
- **Vendor code identity** — `TMDISC.DCVENDOR` is a 3-character
  product-vendor code. It is a different numbering system than the 7-digit
  AP vendor number (`PMVEND.PVNUMVEN`) used by Vendor Intelligence. This
  module does not assume or join the two; `DCVENDOR` is always shown as its
  own literal code, and the gap is named explicitly below.
- **Notes** — Local SQLite, append-only (update/delete blocked by trigger).
  Each note is scoped to a `customer_number` and optionally narrowed by
  `vendor_code` / `product_class` / `product_number` / `product_type`. Each
  note carries an evidence snapshot (the TMDISC rows matching that scope at
  write time, which may be zero) and a SHA-256 integrity marker over that
  snapshot, following the same pattern as `vendor_intelligence`'s notes.
  Unlike `vendor_intelligence`, note creation does **not** require an
  existing MaddenCo row to already match the scope: a rebate program
  commitment is frequently made before (or entirely independent of) a
  matching `TMDISC` override row, and there is no other place in this
  schema to record it.

## Decisions this module does not invent

- A vendor rebate accrual balance or ledger — no such table exists in the
  current MaddenCo schema; tracking is local-notes-only.
- A contract-compliance score, rank, or automatic flag.
- A resolved mapping from `TMDISC.DCVENDOR` (3-character product-vendor
  code) to the 7-digit AP vendor number (`PMVEND.PVNUMVEN`) — stated as an
  open identity-resolution gap rather than guessed.
- Which of `DCPRICE` / `DCAMTFIX` / `DCFACTOR` a given `DCPRICECD` actually
  triggers at sale time — no governed code-to-mechanism mapping is
  connected, so all four fields are shown as literal values, not resolved
  into one "final price."

## Blueprint trace

`ETOP-Blueprint/` does not exist in this repository, so there is no ADR/SRC
baseline to trace into. This module follows the architectural pattern
established by `backend/modules/credit_risk` and
`backend/modules/vendor_intelligence` as its de facto baseline instead.
