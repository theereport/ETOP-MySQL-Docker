# Cash Flow Forecasting — Increment 1 Backend

A 14-week rolling operating cash flow projection, plus a same-week-last-
year backtest and an accuracy history that accumulates as weeks close.
This module reads MaddenCo (schema `DTA273`) and the shared banking
workbook `F:\Accounting\Shared\Banking\Consolidated Daily Bank Balances.xlsx`.
It is evidence-only: it computes a projection and tracks how accurate that
projection turned out to be, but never writes to the ERP and never
adjusts its own future projections based on that history.

## Contracts

- `GET /api/v1/cash-flow-forecasting/health`
- `GET /api/v1/cash-flow-forecasting/current?as_of=`
- `POST /api/v1/cash-flow-forecasting/snapshots?as_of=`
- `GET /api/v1/cash-flow-forecasting/snapshots?limit=`
- `POST /api/v1/cash-flow-forecasting/ap-cache/refresh`
- `POST /api/v1/cash-flow-forecasting/accuracy/record-closed-weeks?as_of=`
- `GET /api/v1/cash-flow-forecasting/accuracy-history?limit=`

## Evidence boundary

- **Starting cash position** — the last business-day row on or before
  the as-of date in the Consolidated Daily Bank Balances workbook.
  `Net Available` (bank balances minus outstanding checks) is reported
  exactly as the workbook computes it; it is not netted against the
  Line of Credit balance, which is reported alongside it separately.
- **Projected AR inflow** — open `TMAROP` invoice rows (`TAROHISTYN` not
  `'Y'`, `TAROAMTOPN <> 0`), bucketed into the Monday-Sunday week
  containing `TARODTEDUE`. This is a due-date baseline: an item is
  projected to convert to cash in the week it's due, not on a
  customer-specific payment-speed model (see Gaps).
- **Projected AP outflow** — `PMHD` open payables, bucketed by
  `PMHDTEDUE`. **`PMHD` has 5M+ rows and its only index is the composite
  primary key (vendor/invoice/payment number) - confirmed live that even
  `COUNT(*)` with a narrow due-date range, and `DISTINCT` on the leading
  PK column, both exceed the platform's 60-second statement timeout.**
  This is the same class of source-side indexing constraint already
  documented for `EOMINV`/`TMPODT` elsewhere in this codebase. Rather
  than fail every live request, this module reads PMHD once via a
  deliberate, extended-timeout batch scan (confirmed to complete in
  ~90-180 seconds) and caches the due-date-bucketed result locally; the
  live forecast endpoint reads that cache. Call
  `POST /ap-cache/refresh` to populate or refresh it - it is not
  refreshed automatically.
- **Projected "other" (non-AR/AP) cash flow** — `GMAD` postings tagged
  `GACDSYS='JE'` against the tracked cash accounts (GL 1010-1013,
  1015-1019; division 1, department 0), with three families excluded
  first: bank-side receipt summaries (redundant with AR), inter-account
  sweeps/transfers (net to zero across the tracked accounts), and Line
  of Credit activity (treasury's own day-to-day plug, not an
  independent driver - see Gaps). What's left (payroll, retirement,
  fuel cards, bank/merchant fees, etc.) is grouped by a normalized
  description family, its historical modal recurrence cadence and
  trailing average amount are computed from a 26-week lookback, and
  that cadence/amount is projected forward into the 14-week horizon.
- **Prior-year comparison** — for each of the 14 weeks, the same
  methodology is re-run as of 364 days earlier (52 weeks, to preserve
  Monday-start alignment), using only GL data dated before that
  historical as-of date (no look-ahead bias). AR uses `TMAROP`'s
  permanent per-invoice due-date/original-amount record regardless of
  current paid status. **AP has no equivalent projected figure**: `PMHD`
  holds only currently-open payables, and the paid-history table
  (`PTHD`) retains only a small rolling window (confirmed live: ~200
  rows platform-wide), not a permanent due-date archive - so a year-ago
  AP projection isn't reliable evidence. The prior-year panel shows
  actual AP cash-out only for that category (from `GMAD`, which is a
  true permanent record back to 2002), with no projected baseline or
  variance for AP specifically.
- **Actuals** (prior-year and, once a week closes, current-year) — AR
  actual = `GMAD` receipt-summary `JE` rows that week; AP actual =
  `GMAD` `GACDSYS='AP'` "CHECK WRITING"/"VOID CHECKS" rows; other actual
  = the same cleaned-`JE` bucket; ending balance = the bank workbook's
  actual last row of that week.
- **Variance** — actual minus projected, reported per category (AR/AP/
  other) and as an ending-balance delta. This is a dollar-amount
  breakdown by category, not a narrative root cause (see Gaps).
- **Snapshots and accuracy history** — local SQLite, append-only
  (update/delete blocked by trigger), following the same pattern as
  `general_ledger`/`vendor_intelligence` notes tables, with a SHA-256
  integrity marker over each stored evidence snapshot. The AP due-date
  cache is the one table in this module that is *not* append-only - it's
  a plain performance cache, replaced wholesale on each refresh.

## Decisions this module does not invent

- A customer- or vendor-specific payment-speed model. MaddenCo does not
  reliably retain a per-invoice paid date (`TMAROP.TARODTECHG` is
  essentially never populated on history rows, confirmed live), so this
  module does not manufacture a "days late" estimate.
- A narrative root cause for a variance ("Customer X paid 12 days
  late"). Only a category-level dollar breakdown is reported.
- Any automatic adjustment of future projections based on tracked
  accuracy history. That history is evidence for a human to review;
  nothing here feeds it back into the model.
- A prediction of future Line of Credit draws or paydowns. Per standard
  treasury-forecasting practice, LOC activity is excluded from the
  "other" bucket and is not treated as an independent driver - a
  projected shortfall is the signal, not a guess at how it gets funded.
- Any interpretation of whether an on-hold payable will actually be paid
  on schedule; it is reported as its own figure, not zeroed or assumed.

## Blueprint trace

`ETOP-Blueprint/` does not exist in this repository, so there is no
ADR/SRC baseline to trace into. This module follows the architectural
pattern established by `backend/modules/general_ledger` and
`backend/modules/vendor_intelligence` as its de facto baseline instead.
