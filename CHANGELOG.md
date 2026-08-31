# Changelog

## [0.7.0 Vendor Intelligence] - GL Posting Detail Inline; Batched GL Endpoint

### Changed
- Each open payable invoice's GL posting evidence (GL account with
  description, division, department) moved from a "▸ GL" click-to-expand
  toggle into three columns appended directly to the invoice row, after
  Hold - no click required to see it. An invoice with multiple GL lines
  stacks them within the same three cells. Department now reads `0`
  instead of "Unavailable" when MaddenCo has no department value for
  that line, matching the department-zero convention already applied
  elsewhere in AP (see AP Increment 10).

### Added
- New batched endpoint,
  `GET /erp-evidence/accounts-payable/gl-distributions`, returning GL
  distribution lines for a whole list of invoice numbers in one indexed
  `PMGLDS` query (`WHERE PMGNBVND = ? AND PMGNBINV IN (...)`). Needed
  because showing every open invoice's GL detail immediately (rather
  than lazily on click) would otherwise mean firing the existing
  per-invoice `invoice-evidence` endpoint once per invoice - confirmed
  live that endpoint also assembles vendor master, posted headers/
  details, PO/receiving match, and input headers/details/payment splits
  per call, so 9 concurrent calls for one vendor's open payables took
  10-15+ seconds. The new endpoint does only the GL lookup plus the
  existing `GMGM` description join, cutting 9 heavy requests down to 1
  lean one.

### Preserved
- The original per-invoice `invoice-evidence` endpoint and its GL
  distribution field are unchanged and still used elsewhere (e.g.
  Accounts Payable's ERP Evidence tab); the new batched endpoint is
  additive, not a replacement.

## [0.7.0 Workflow Foundation] - Admin Password Reset

### Added
- Security & Access administrators can now reset a user's password two
  ways: generate a one-time reset link (mirrors the existing invitation-
  link mechanism exactly - random token, only its SHA-256 hash stored,
  displayed once, 24-hour fixed expiry) that the user activates by
  setting their own new password, or set a new password directly as a
  fallback. Both paths reuse the existing scrypt password hashing, the
  `expected_version` optimistic-concurrency pattern (a new
  `credential_version` column, kept independent of `status_version` and
  `access_version` the same way those two are already kept independent
  of each other), and revoke all of the target account's active sessions
  on completion, forcing re-authentication with the new password.
- New `wf_password_reset_tokens`/`wf_password_reset_events` tables
  (structurally identical to the existing invitation tables) and three
  new audit event types (`identity.password_reset_requested`,
  `identity.password_reset_completed`, `identity.password_set_by_admin`)
  append to the existing hash-chained audit log.
- Unlike the two closest existing precedents (suspending a user,
  changing module access - both of which forbid an admin from acting on
  their own account), an admin may reset or set a new password for their
  own account: there is currently no other way to recover from a
  forgotten admin password, so blocking self-service here would create a
  real lockout risk with no recovery path.
- Verified live end-to-end: generated a reset link for a test account,
  activated it in a separate session (new password worked, prior session
  revoked, old password rejected), then used the direct-set fallback
  (new password worked, prior session revoked again) - all three new
  audit event types confirmed recorded with the hash chain still valid.

## [0.7.0 AP Increment 12] - Vendor Performance Timeout Fix; MTD Purchase/Discount Hidden

### Corrected
- The new PO fill-rate query (`TMPOHD` joined to `TMPODT`, both large
  tables with no index on the date column used) was unstable for the
  handful of highest-volume vendors - live timing on the same vendor and
  query ranged from ~1s to ~59.7s, and it occasionally exceeded the
  shared 60s MySQL statement timeout entirely, throwing an error that
  crashed the vendor's *entire* evidence page (Payables, Purchase
  Orders, Receiving included), not just the Performance section. Fixed
  two ways: the query now carries a `MAX_EXECUTION_TIME(8000)` optimizer
  hint so its own worst case is a fast, predictable failure well under
  the shared ceiling (confirmed live this also made timing far more
  consistent, ~10s versus the prior 1-59s spread), and
  `_build_performance_summary` now catches a failure and reports "PO fill
  rate unavailable" instead of taking the rest of the page down with it -
  matching the bounded-query pattern already used everywhere else in
  this codebase for exactly this class of MaddenCo-table-too-large risk.

### Changed
- Vendor Intelligence's "MTD purchases" tile and "MTD capture rate" tile
  are hidden. Confirmed live that MaddenCo's `PVPURMTD`/`PVDISCMTD`
  (month-to-date) are identical to `PVPURYTD`/`PVDISCYTD` (year-to-date)
  for essentially every vendor sampled (10 of 10) - a stalled or
  misconfigured month-end rollover on the MaddenCo/AS400 side (the
  vendor's own period-change date field is years stale), not an ETOP
  computation bug. Showing it read as a duplicate of YTD rather than a
  real, distinct figure, so it's hidden rather than displayed
  misleadingly; the underlying MaddenCo data issue itself is unchanged
  and worth raising with whoever administers that instance.

## [0.7.0 AP Increment 11] - PO/Receiving Match, GL Coding Shortlist, Vendor Performance

### Added
- **Purchase Order and Receiving Match**: the ERP Evidence tab now shows a
  real 3-way match (quantities only - see Corrected below) for any AP
  invoice line carrying a nonzero PO/receiver reference
  (`PMDT.PMDNBPORV`), joining `TTRCVD` and `TMPOHD`/`TMPODT`. Confirmed
  live this only applies to ~9-10% of currently open invoices (most AP
  activity - rebates, AR-offset, differential clearing - has no PO trail
  at all); the rest show a plain "not applicable," never an error. The
  matching "Purchase Order and Receiving Match" deferred-capability entry
  is removed - the coverage limitation is disclosed per-invoice instead.
- **GL Coding Recommendation**: the Vendor Invoice Dataset & OCR review
  screen now shows a ranked top-3 historical GL coding shortlist once a
  vendor is confirmed (e.g. "Account 5050 (TRUCK EXPENSE - REPAIRS) -
  97.9%"), scoped to that vendor's most recent accounting year. Reference
  only - ETOP does not perform GL coding entry itself. Confirmed live
  that a single "most likely account" guess is unreliable, but a top-3
  shortlist is highly reliable, once genuine double-entry control/
  clearing legs (cash, AP control, AR-vendor, vendor cash discounts -
  confirmed identical across every vendor and division sampled) are
  excluded by account number; excluded accounts are always disclosed in
  the response, never silently dropped. The "GL Coding Recommendation"
  deferred-capability entry is removed.
- **Vendor Performance**: Vendor Intelligence's vendor evidence page now
  shows a real PO fill-rate (quantity received / ordered, trailing 12
  months) alongside the vendor's existing purchase volume and discount
  capture rate. On-time delivery and quality/chargeback performance are
  shown as permanently unavailable, not "pending connection" - confirmed
  live that no promised-delivery-date field or returns/chargeback/
  quality table exists anywhere in the connected MaddenCo instance. The
  AP dashboard's "Authoritative Vendor Performance" deferred-capability
  entry is narrowed to reflect exactly this split.

### Corrected
- The PO/receiving match join initially used `TTRCVD.TRCHNUMRPT` alone as
  if it uniquely identified one receiving-report line; confirmed live
  against a real 20-line invoice that `TRCHNUMRPT`'s real primary key is
  composite with `TRCDNUMSEQ`, and a single receiving report commonly has
  dozens of lines. The join now also requires
  `TRCDNUMSEQ = PMDT.PMDSEQ - 1` (confirmed live, in order and quantity,
  across the same 20-line invoice) - without it, a match would have
  silently returned a different product's quantities entirely.
- `vendor_intelligence`'s receiving-evidence cost variance
  (`TRCDCOSDIF`) was reported "complete, $0.00 variance" whenever
  receipts existed; confirmed live that field is exactly 0 across all
  450,925 rows this instance has ever recorded (never a real
  observation) and `TRCDCOS` always just copies `TRCDCOSPO` when set.
  Now always disclosed as unavailable rather than reporting a data void
  as a clean match.

## [0.7.0 Automation] - Test-Data Leak Cleanup, Connection Leak Fix, Quarantine Reactivation

### Corrected
- `test_automation_service_governance.py`'s database sandbox used
  `sys.modules.setdefault("data.database", ...)` *before* importing
  `modules.automations.repository`, which only isolates the test if
  `data.database` had never been imported yet in that interpreter. Once
  any other test file (or the real backend) had already imported it in
  the same pytest process, the guard was a silent no-op and the test's
  fixture automation ("Governed Automation", `SELECT 1`, daily 8:30am)
  was written straight into the real `workbench.db` - and the live
  scheduler thread then actually ran it on schedule, producing real
  executions and real exported files on disk. Fixed by rebinding
  `modules.automations.repository.get_connection` directly (an
  import-order-independent approach) in `setUp`/`tearDown` instead.
  The two contaminated `automation-1`/`automation-2` rows and their
  execution history were deleted via the real `DELETE /automations/{id}`
  endpoint (which was itself unaffected and working correctly).
- Every `with get_connection() as connection:` in
  `modules/automations/repository.py` (16 sites) and `service.py` (1
  site) leaked the connection - `sqlite3.Connection`'s context-manager
  protocol only commits/rolls back on exit, it never closes. On Windows
  this is why the governance test suite's `tearDown` failed with
  `WinError 32` even after fixing the isolation bug; on Linux the leak is
  silent until the process runs out of file descriptors. Fixed with a
  `_connection()` wrapper that guarantees `close()`; the test file had
  the identical bug in its own two connection helpers and got the same
  fix. `modules/reports/service.py` has 6 sites with this same pattern -
  flagged, not fixed here.
- Two real automations were quarantined (`status: "error"`) and had
  simply never been manually reactivated - `status` is a one-way latch
  that nothing clears automatically, even after a later successful run,
  which is why the catalog showed ERROR badges with SUCCESS runs listed
  underneath. "Prior Day Missing Credit Card Auth" failed once on
  2026-08-12 and sat quarantined since. "Sold Stock Transfer Report" was
  retroactively quarantined on 2026-08-25, the day a stricter
  `next_run_at` format check shipped, and its legacy definition didn't
  satisfy it. Both re-validate clean today and were reactivated through
  the same `POST /automations` path the UI's "Activate" button uses
  (fetch current definition, flip `status` to `active`, resubmit) - both
  now show real, freshly-computed `next_run_at` values.

## [0.7.0 AP Increment 10] - Multi-File Drag-and-Drop Upload; GL Department Zero Fix

### Added
- Vendor Invoice Dataset & OCR now has a drag-and-drop zone next to the
  upload button that accepts multiple PDF files at once (the file picker
  also now allows multi-select) - each is preserved and processed
  sequentially, with a combined result message (e.g. "2 of 2 vendor
  invoices preserved and processed.") and per-file failure detail when
  some are rejected. Confirmed live: a real duplicate two-file drop
  processed both to completion, and a corrupt two-file drop correctly
  preserved both while reporting per-file "could not be opened" reasons.

### Corrected
- The Warehouse Approval Queue's GL account/division/department all come
  from NOT NULL decimal columns in `PMGLDS`, so a genuine value of `0`
  (department 0 is common) arrives as `Decimal(0)` from the MySQL driver -
  falsy in Python. The prior `x or None` pattern wrongly discarded it as
  "missing" and showed "Department unavailable" instead of the real `0`.
  Fixed with an explicit `is not None` check; will show correctly on the
  next ERP ledger refresh.

## [0.7.0 AP Increment 9] - Voided PMHD Entries Excluded from Open Ledger

### Corrected
- `accounts_payable`, `cash_flow_forecasting`, and `vendor_intelligence` all
  scan `PMHD` filtered to `PMHNBCHK = 0 OR NULL` ("unpaid"), but a voided
  entry never gets a check number either, so it stayed "unpaid" forever.
  `PMHCODSEL = 'V'` marks these - confirmed live that 12,166 of 12,289 such
  rows carry a non-zero `PMHGLREFVD` (void GL reference) versus zero of the
  genuinely open rows, and the `'V'` rows carried nonsense dates spanning
  1950-2034 (surfaced by real decades-old "invoices" in the new Warehouse
  Approval Queue) versus the real open rows' 2024-2026 range. Excluding
  them moves the real open balance from $90.9M/40,725 invoices to
  $93.0M/28,814 invoices (voided entries net negative, so removing them
  raises the balance) - confirmed live via a full refresh after the fix.
- The GL-division scan behind the Warehouse Approval Queue now also
  captures the GL account and department from the same winning
  distribution line (largest `PMGAMTINV`), shown on each queue card as
  "Account · Division · Department".

## [0.7.0 AP Increment 8] - Warehouse Approval Queue

### Added
- A new "Warehouse Approval" tab pulls in every currently-open ERP
  invoice from the same open-ledger cache the Executive Dashboard uses,
  filterable by GL division, bucketed into Needs Approval / Approved by
  Warehouse / Approved & Entered by A/P. A warehouse manager can review
  and advance an invoice's status before A/P ever keys it in from OCR
  capture; an invoice leaves the queue automatically once MaddenCo shows
  it paid (it simply stops appearing in the open-ledger cache), with no
  explicit "closed" step. This is evidence/documentation only, matching
  the existing Approval Center's governance posture - it never blocks,
  gates, or replaces A/P's own entry of an invoice.
- New append-only `ap_warehouse_approval_actions` table (mirrors
  `ap_control_reviews`'s append-only trigger pattern) records each status
  change with an operator-supplied actor identity; an
  `actor_identity_source` column is ready for real Microsoft/Outlook SSO
  identity later without a schema change, though only
  `operator_supplied` is used today. An invoice's current status is
  always derived from its latest action, never stored redundantly.
- The ERP ledger refresh job (triggered by the existing "Refresh ERP
  ledger" button) now also scopes and runs a targeted `PMGLDS` scan
  (vendor + accounting year, using the table's only secondary index) to
  populate a per-invoice GL division - confirmed live: vendor 6245's
  invoices matched division "59" (one exception matched "21", a
  different account on that specific invoice), and a full-scale refresh
  against the real ~41K open invoices matched 40,692 of them to a
  division in one job run. When an invoice has more than one GL line,
  the line with the largest `PMGAMTINV` is used - a disclosed
  simplification, not a guarantee of the "true" distribution line.

## [0.7.0 Vendor Intelligence] - GL Posting Detail on Open Payables

### Added
- Each open payable invoice on a vendor's page now has a "▸ GL" toggle
  that fetches and shows exactly what the invoice posts to (GL account,
  division, department, quantity, amount, period/year) - reuses the
  existing `erp_evidence` per-invoice evidence endpoint (also used by
  Accounts Payable's ERP Evidence tab), so no new backend route was
  needed for the toggle itself.
- `erp_evidence`'s GL distribution evidence now also carries
  `gl_account_description` (from `GMGM`, the chart-of-accounts master),
  e.g. "TRUCK EXPENSE - REPAIRS" for account 5050 - confirmed live
  against the same MaddenCo screen this was requested from. `PMGLDS`'s
  own per-line memo field is usually blank; this is a new, separate
  field alongside it, not a replacement - never fabricated when the
  account master has no matching row.

## [0.7.0 AP Increment 7] - Vendor Number Search on Extraction Review

### Added
- The "Vendor number" field in Vendor Invoice Dataset & OCR's extraction
  review now searches MaddenCo live as you type (by vendor number or
  name/sort-name substring, reusing the existing
  `erp_evidence` vendor search already built for the ERP Evidence tab -
  no new backend endpoint needed) and lets you pick the real vendor,
  auto-filling both vendor number and vendor name from the authoritative
  record instead of trusting the OCR guess. Confirmed live: replaced an
  OCR misread ("osile Motors Inc.") with the real match (6245, JINKS
  MOBILE REPAIR) in one search.

## [0.7.0 Vendor Intelligence] - Open Payables Excluded Paid Invoices

### Corrected
- `vendor_intelligence`'s per-vendor open-payables query
  (`get_open_payable_invoices`) had the same `PMHNBCHK` gap already found
  and fixed twice today in `accounts_payable` and `cash_flow_forecasting`:
  no filter for whether an invoice had been paid. A real vendor lookup
  live (vendor #6245) showed 100 invoices / $60,332.46 "open" before this
  fix; filtered to genuinely unpaid, the real figure is 12 invoices /
  $3,496.18 - confirmed both by a direct query and live in the Vendors
  workspace.

### Preserved
- Changes only the `WHERE` clause; `get_paid_payable_invoices` (which
  queries the separate `PTHD` payment-history table) is unaffected.

## [0.7.0 AP Increment 6] - ERP Open-Ledger, Discount Eligibility, and Approval-Time Metrics

### Added
- `accounts_payable` now has real, live ERP connectivity for the first time
  - a new invoice-level cache of MaddenCo's open AP ledger (`PMHD`),
  refreshed by a background job (via the platform job queue, not a blocking
  request) that unlocks five previously-permanent "Unavailable" Executive
  Dashboard tiles: Current AP Balance, Invoices/Amount Due Today, Past-Due
  count/amount, and Cash Required in 7 Days. On-hold invoices are broken
  out separately rather than hidden inside or excluded from these figures.
- Average Approval Time is now real, computed from existing local
  `ap_control_cases`/`ap_control_reviews` timestamps (average hours from
  case creation to first recorded review disposition) - no new
  infrastructure was needed for this one.
- Discounts Available is now real once a vendor terms code carries a flat
  "N days from invoice date" discount rule. A local, user-editable Vendor
  Terms Reference table (new section under Vendor Intelligence) replaces
  the nonexistent MaddenCo terms-code decode table; a discount-bearing
  code that instead relies on day-of-month/cutoff ("proximo") logic is
  disclosed and excluded rather than silently counted as zero.
- Invoice Intelligence's invoice detail view now automatically surfaces
  the existing `erp_evidence` per-invoice ERP lookup as a compact "ERP
  match" panel (matched / amount or due-date mismatch / not found in ERP),
  instead of requiring a manual trip to the separate ERP Evidence tab.

### Corrected
- Live verification caught two real defects before they reached the
  dashboard: (1) `PMHD`'s real key includes a payment-split number
  (`PMHNBPMT`) not originally selected, causing invoices with multiple
  payment splits to collide on the new cache's key - fixed by aggregating
  split rows per invoice; (2) the initial live scan showed $7.26B across
  5.39M "open" invoices - `PMHD` retains full AP history, not just open
  items, and `PMHNBCHK` (check number) is the real paid/unpaid signal.
  Filtered to unpaid, the real balance is $90.9M across ~41K invoices,
  verified against an independent direct query.
- The same `PMHNBCHK` gap was found in `cash_flow_forecasting`'s existing
  AP cash-flow projection (`ap_due_date_cache_source.py`), which had no
  such filter either - every AP forecast produced before this fix
  materially overstated projected AP outflow. Fixed alongside this work;
  see the Cash Application Increment 1 R3 entry below for detail.

### Preserved
- Changes no invoice approval, payment authorization, or ERP-write
  behavior - every new metric and the ERP match panel are read-only
  evidence, matching this module's existing governance statements.
- The five newly-real dashboard tiles report `unavailable` with an
  action-oriented reason (run the refresh) rather than a vague "not
  connected" message until the cache has been refreshed at least once.

## [0.7.0 Cash Application Increment 1 R3] - AP Cash Flow Forecast Excluded Paid Invoices

### Corrected
- `cash_flow_forecasting`'s open-AP due-date scan (`PMHD`) had no filter for
  whether an invoice had already been paid. Confirmed live: `PMHD` retains
  full AP history, not just open items, and `PMHNBCHK` (check number) is
  populated once an invoice is paid - ~5.39M of ~5.44M rows already carried
  one. The unfiltered scan was projecting $7.26B across 5.39M rows as future
  AP cash outflow; filtered to genuinely unpaid (`PMHNBCHK = 0` or `NULL`),
  the real figure is $90.9M across ~41K invoices - verified against an
  independent direct query of the same live data. Every AP cash-flow
  forecast produced before this fix materially overstated projected AP
  outflow.

### Preserved
- Changes only the `WHERE` clause of the existing PMHD scan
  (`ap_due_date_cache_source.py`); the cache schema, refresh trigger, and
  weekly-bucketing logic are unchanged. No AR, GL, bank-balance, or "other"
  cash-flow category is affected.

## [0.7.0 Platform Core Increment 1] - Background Job Queue and Completion Notifications

### Added
- `job_queue` module: a generic, durable job-tracking table
  (`queued`/`running`/`completed`/`failed`) any module can report
  background-job progress into, exposed at `/api/v1/platform/job-queue`
  under the baseline `dashboard` access grant every signed-in user
  already has - the same grant `platform_search` already piggybacks on,
  so no access-control wiring was needed. Fail-closed restart recovery
  marks any job still queued/running at startup as interrupted rather
  than silently resuming or replaying it, matching `automations`'
  existing recovery convention.
- Lockbox preparation's existing background executor now reports into
  the job queue through two optional coordinator hooks
  (`on_job_queued`/`on_job_complete`), so a batch already running in the
  background (started from `DurableLockboxPreparationCoordinator`) is now
  tracked end to end without touching its execution or promotion logic.
- A real, durable notification path for background work: the header
  notification bell and panel now reflect actual job completions (title,
  balanced/exception counts) alongside Work Management's existing
  durable notifications, and a new toast appears at the top of the
  screen the instant a background job finishes - with a "View" action
  that opens the module the job belongs to - so a job started in one
  module surfaces the moment it completes no matter which module is open.

### Preserved
- Changes no Lockbox extraction, customer resolution, allocation,
  preparation, approval, export, posting, or ERP-write behavior; the two
  new coordinator hooks default to `None` and are no-ops unless supplied.
- Adds no new access-control module and no changes to
  `workflow_foundation`'s module grants or route policy.

## [0.7.0 Wave 2 Increment 4E] - Structurally-Tolerable Remittance-Row Ambiguity

### Corrected
- Admits a `prepared_balanced` candidate whose remittance-row OCR
  reconstruction still has an unresolved row when that row's rejection is
  `no_governed_invoice_candidate` or `multiple_governed_invoice_candidates`
  (an ambiguous or absent OCR candidate, with no active disagreement) and
  the recommendation method is `exact_remittance_invoices` with an
  otherwise fully clean current-open completion assessment: matching
  invoice sets, one source amount and one current-open item per admitted
  invoice, every item owned by the selected customer, the closed
  next-transaction-information boundary intact, and zero allocation,
  removal, or customer conflicts.
- Leaves `conflicting_cross_source_amount` rows fail-closed under every
  method; an unresolved row disagreeing with another source about the
  dollar amount is never treated as structurally tolerable, regardless of
  how clean the rest of the completion assessment is.
- Business decision, made under active parallel-testing observation:
  every promoted transaction is still reviewed by a person before any ERP
  write, so this widens what promotes to Prepared & Balanced without
  widening what can auto-approve or post.

### Preserved
- Changes only the row-disambiguation leg of `promotion_assessment`; the
  Increment 4D customer-evidence override, every other promotion
  blocker, and the read-only ERP boundary are unchanged.
- Protects the active PGH-640045 source: after Increment 4D left 3
  `prepared_balanced` transactions blocked by the evidence gate, this
  change clears exactly the one (G-7032002) whose only unresolved rows
  carry a tolerable rejection reason and a clean completion assessment,
  leaving G-7157006 (an active `conflicting_cross_source_amount` row) and
  G-7157001 (an unrelated duplicate-phone conflict) blocked.

## [0.7.0 Wave 2 Increment 4D] - Strong-Identity Override of Partial Invoice Evidence

### Corrected
- Extends the existing `unique_current_open_invoice_owner` override of the
  `partial_invoice_owner_evidence` stop-gate to three more strong
  customer-identity bases: `payer_supplied_customer_number`,
  `km_statement_customer_number`, `learned_payer_bank_account_mapping`,
  and `unique_open_ar_bucket_match`. When the customer was confidently
  resolved via one of these four bases, an admitted invoice with only
  partial current-open ownership evidence no longer blocks promotion to
  Prepared & Balanced by itself.
- Fixes both places the stop-gate could fire: the direct
  `partial_invoice_owner_evidence` evidence flag and the
  `failed_selection_gates` list carrying the same string.
- Leaves `check_for_customer_number` and `check_phone_number_match` out of
  the tolerant set; a check-only or phone-only resolution still fails
  closed on partial invoice evidence, matching the rationale that this
  override belongs only to bases strong enough to stand on their own.
- Business decision, made under active parallel-testing observation: every
  promoted transaction is still reviewed by a person before any ERP
  write, so this widens what promotes to Prepared & Balanced without
  widening what can auto-approve or post.

### Preserved
- Keeps every other customer-evidence stop gate (invoice-owner conflict,
  duplicate exact phone, duplicate exact phone/ZIP, payer-account
  directive conflict, and the per-basis verified-flag checks) fully
  enforced for all nine selection-basis tiers, including the four newly
  tolerant ones.
- Protects the active PGH-640045 source: clears exactly the four
  transactions (G-7032005, G-7032010, G-7107004, G-7197002) whose only
  blocker was partial invoice evidence under one of the four tolerant
  bases, moving the evidence-gate-blocked count from 7 to 3, while
  leaving G-7032002 blocked (its actual blocker is a separate
  row-disambiguation gate, addressed in Increment 4E) and G-7157001/
  G-7157006 blocked under unrelated, unaffected gates.

## [0.7.0 Cash Application Increment 1 R2] - Enterprise Linking, Statement Summary, and Misc G/L Entry

### Added
- Manually-linked (non-ERP) enterprise customer grouping, merged with any
  existing ERP `CUNUMENT` group rather than replacing it. The
  linked-customers response discloses which evidence contributed via
  `source: "erp" | "manual" | "mixed"`. A reviewer can link two customers
  with no CUNUMENT relationship, or extend an already ERP-linked group
  with a further manually-linked account; unlinking only ever removes
  that one customer's own manual-group membership.
- A statement/aging summary mini table (statement date, future, current,
  01-30, 31-60, over-61, due-now) in the review header, sourced from the
  existing `customer_360` TMCUST aging evidence once a customer resolves.
- Misc G/L Entry: a bounded write-off (reason `Service Charge ADJ`, GL
  `3880`, server-validated) with reviewer-entered location, department,
  and amount. The amount participates in `difference`/`balanced` without
  becoming an allocation row, round-trips on save/reload, and exports to
  its own `misc_gl` workbook tab (Check #, Customer #, GL Code, Location,
  Department, Amount).
- `Customer Number` column on the reviewed PNC lockbox export's detail
  sheet.

### Fixed
- Allocation rows added from a linked enterprise account's open items no
  longer show a blank Open Amount, Invoice Date, Due Date, and Aging —
  the allocation table's evidence lookup now spans every linked account
  whose open items have been fetched, not only the primary customer's.
- The editable allocation table now visibly groups rows by owning
  customer number (with a divider row) whenever a transaction's draft
  spans more than one enterprise account.

## [0.7.0 Cash Application Increment 1 R1] - Lockbox Review Workflow Tweaks

### Added
- A Clear button for the editable ERP open-item allocation draft.
- An Invoice Date column between Apply Amount and Due Date.
- A left/right toggle through ERP-enterprise-linked accounts, showing
  each account's open-item count and letting a reviewer add open
  invoices from any linked account into the same check's allocation.

### Changed
- Reviewer action buttons (Customer Notes, Email Customer, Back, Next,
  Hold, Save Correction, Approve Transaction) reordered into a single
  uniformly-sized column.

## [0.7.0 Cash Application Increment 1] - Lockbox Preparation Reliability and Cash Flow Forecasting Foundation

### Added
- `cash_flow_forecasting` module: a 14-week rolling AR/AP/other cash
  flow projection with a same-week-last-year backtest and an accuracy
  history that accumulates as weeks close. Evidence-only — it never
  writes to the ERP and never feeds tracked accuracy back into its own
  future projections. See `backend/modules/cash_flow_forecasting/README.md`.
- Standalone ETOP Launcher desktop application for starting and
  monitoring the local backend/frontend development environment.
- A phone/bank-account-independent allocation tie-break that trusts an
  exact dollar match against a candidate customer's own open A/R.
- Recognition of "MEMO" as a customer-number label alongside "FOR" on
  checks.

### Fixed
- Lockbox preparation was leaving checks in manual review far more often
  than necessary. Root-caused and corrected: an unindexed live `TMAROP`
  query that timed out under batch load (replaced with a local cache), a
  customer-conflict gate that discarded independently-verified
  resolutions over merely-incomplete (not conflicting) invoice evidence,
  and missing multi-bucket due-date combination matching in two
  allocation code paths.
- Payment-notes location-number handling during remote capture.

## [0.7.0 AP Increment 5 R2] - Coordinate-Aware Vendor Invoice Extraction

### Fixed
- Native-text invoice labels and values emitted as separate positioned PDF
  fragments are now paired through deterministic, field-specific geometry.
- Remittance/payee issuer candidates are distinguished from Sold To, Bill To,
  Ship To, Shipped To, Customer, Buyer, Recipient, delivery, and service
  sections. Customer account identifiers are never treated as vendor numbers.
- Totals boxes recognize subtotal, tax, Total, and Total Due while excluding
  unrelated table headings; blank purchase-order labels remain present without
  a fabricated value.
- Native-text success, OCR use, thirteen-field coverage, and three-key-field
  readiness are reported independently so readable text cannot masquerade as
  resolved fields.
- Reviewers can explicitly mark an unsupported extracted field unavailable;
  AP synchronization suppresses machine and text fallback for that current-run
  disposition instead of silently restoring the rejected value.

### Added
- Extraction v2 stable fragment identity/page geometry and parser 2.0.0/rules
  v2 two-fragment provenance, pairing method, canonical corroboration, and
  fail-closed conflicting-value ambiguity.
- Fictional coordinate-layout PDF regressions covering remittance and recipient
  semantics, blank PO, totals, OCR confidence provenance, malformed geometry,
  and truthful review status.
- Compact review provenance for every distinct ambiguous candidate plus
  reversible **Mark unavailable** evidence stored in the existing append-only
  review JSON contract without a database migration.
- A governed source-only exact-state installer, explicit R1-final rollback,
  short-path isolated verifier, and AP Increment 5 R2 handoff.

### Scope boundary
- Installation never opens or changes runtime databases, uploads, invoices,
  extraction/review evidence, credentials, exports, or ERP/GL state and never
  reprocesses a document automatically.
- Every new extraction remains human-review-required. The correction creates no
  vendor master, match, approval, payment, posting, external AI transfer, ERP
  write, straight-through threshold, or financial authority.

## [0.7.0 AP Increment 5 R1] - Windows SQLite Lifecycle Correction

### Fixed
- Document Intelligence review and processing repositories now preserve
  SQLite transaction commit/rollback behavior while deterministically closing
  every connection, including exception paths.
- Windows can immediately reuse, move, back up, or remove a completed test
  database without `WinError 32` from a leaked ETOP handle.
- The focused AP capture suite now proves repository/review connection closure
  cross-platform and closes its own direct append-only-ledger probe.

### Scope boundary
- This is a source/runtime lifecycle correction only. It changes no parser,
  OCR, review, AP synchronization, vendor-spend, Financial Close, ERP, or
  financial-authority behavior.
- Runtime databases, invoice originals, OCR evidence, reviews, uploads,
  credentials, and ERP/GL state remain outside the source payload.

## [0.7.0 AP Increment 5] - Vendor Invoice Capture/OCR and Vendor Spend Q&A

### Added
- AP-facing governed PDF upload backed by the existing Document Intelligence
  job/file store, with exact byte preservation, SHA-256, validation, and
  exact-byte duplicate evidence.
- Registered deterministic vendor-invoice parser with field-level source,
  page/location, rule/authority, ambiguity, and actual OCR confidence when
  available.
- Native-first extraction with local Tesseract fallback only on insufficient
  pages, including page-local OCR engine/version/confidence/failure evidence.
- Append-only successful and failed processing runs while keeping the existing
  result endpoint as a latest-success compatibility projection.
- Processing-run-bound review/correction history, new-run review invalidation,
  stale-review conflict, and AP adapter run matching.
- `Vendor Invoice Dataset & OCR` workspace for upload, dataset retrieval,
  original/hash inspection, field evidence, correction/review, run history,
  controlled idempotent AP sync, and reopen in Invoice Intelligence.
- Paginated vendor-invoice retrieval with total/load-older navigation and an
  exact-selected-job AP synchronization endpoint.
- Deterministic total-spend and highest-vendor questions over signed posted AP
  GL-distribution evidence, including division, `account 5050-3`, calendar
  month/year, and explicit ERP accounting year/period filters.
- Fixed parameter-bound aggregates, runtime mapping validation, read-only
  consistent-snapshot evidence, bounded ranking/tie disclosure, source coverage,
  and canonical evidence hashes.

### Fixed
- Failed reprocessing no longer hides or replaces the last successful current
  result.
- The Document Intelligence AP summary no longer equates a classifier
  confidence threshold with “Ready” extraction.
- AI Studio no longer presents the registered vendor-invoice evidence dataset
  and parser as merely planned.
- Review saves now require the expected current run across every caller;
  processing/review/AP synchronization are serialized in the local runtime.
- Failed validation retries append immutable failed runs. PDF/OCR processing is
  offloaded and bounded by governed page, time, and raster limits with explicit
  review evidence.
- Public document-job responses no longer expose internal storage paths;
  managed file reads are contained under the configured upload root.
- Null-only, ambiguous, unsupported, conflicting, or incompatible vendor-spend
  questions now fail closed without a fabricated zero or semantically different
  financial query.

### Explicit limits
- PDF-only, local proof-of-concept parsing is not a calibrated production
  parser or approved straight-through threshold.
- Extraction review is not invoice approval, coding acceptance, payment
  authorization, posting, ERP verification, or financial authority.
- No external AI/OCR transmission, ERP write, automatic approval, payment,
  destructive overwrite, or change to the specialized PNC Lockbox path is
  introduced.
- Vendor-spend results are posted AP GL-distribution evidence, not cash paid,
  invoice approval, vendor performance, payment status, or financial authority.

## [0.7.0 Step 6 Increment 2] - Local Close Planning Templates

### Added
- Immutable, numbered local user-authored planning-template versions with
  ordered control definitions, active/distinct default preparer/reviewer
  identities, authenticated attribution, idempotency, and tamper-evident event
  lineage.
- Explicit operator-driven instantiation of one exact version using a supplied
  calendar anchor, deterministic anchor-plus-offset planning dates, and an
  atomic immutable cycle/control snapshot.
- A usable Financial Close Planning Templates workspace for loading/empty/error
  states, template authoring, version history/revision, date preview, manual
  instantiation, and template-to-cycle lineage.
- Focused backend and static verification for immutability, later-version
  isolation, atomic failure, route bounds, and retained Increment 1 behavior.

### Explicit limits
- Templates are local planning drafts, not approved accounting policy, an
  enterprise control library, an authoritative calendar, or financial
  authority.
- Dates have planning effect only. No recurrence, scheduled/automatic cycle or
  task creation, notification, escalation, or shared workflow task is added.
- No ERP/GL read or write and no close, approve, certify, post, reopen, export,
  external communication, or AI action is introduced.

## [0.7.0 Step 6 Increment 1] - Financial Close Readiness Foundation

### Added
- Immutable local close cycles and close-control items with operator-supplied
  calendar dates, verified preparer/reviewer identities, and segregation.
- Append-only preparation evidence and professional review dispositions with
  optimistic concurrency, idempotency, canonical hashes, and reload durability.
- Derived close-control readiness counts, work queue, and evidence timeline in
  a dedicated Financial Close workspace.

### Explicit limits
- Readiness describes the completeness of this local evidence manifest only;
  ERP period state, books-closed status, balances, reconciliations, materiality,
  policy, delegated authority, and actual close execution remain unavailable.
- No close, reopen, certify, approval, journal posting, consolidation,
  notification, export, external transfer, or ERP write is introduced.

## [0.7.0 Step 5 R1] - AP Direct ERP Lookup Correction

### Fixed
- AP ERP evidence no longer requires an existing imported OCR invoice.
- Added bounded PMVEND vendor-name/number discovery, exact PMHD invoice-number
  discovery, explicit candidate selection, and direct exact evidence retrieval.
- Zero imported invoices is now an honest optional-path state rather than a
  blocker for confirmed ERP evidence.

### Explicit limits
- Vendor-name results are candidates only and are never auto-selected.
- Partial PTHD/PTDT/PTPY mappings remain visible and uninterpreted.
- No local invoice fabrication, OCR rewrite, match, recommendation, Decision,
  approval, payment, posting, export, notification, or ERP write is introduced.

## [0.7.0 Step 5] - Read-Only ERP Evidence Gateway

### Added
- Shared, row-capped, parameterized ERP evidence contracts for Credit and AP.
- Current Credit customer, Open A/R, and CUNUMENT relationship evidence with
  explicit incomplete-order/payment/exposure coverage.
- Exact-identity AP vendor, posted invoice/detail, GL distribution, invoice
  input, and input payment-split evidence from the confirmed DTA273 mapping.
- Credit and AP ERP Evidence views with timestamped, hash-bound packets.

### Explicit limits
- AP raw codes are not interpreted as open, approved, payable, paid, matched,
  or executed without authoritative code semantics.
- Sensitive vendor bank, routing, tax-ID, contact, phone, email, and address
  fields are never selected.
- No recommendation, Decision, approval, payment, posting, order action,
  notification, export, external transfer, or ERP write is introduced.

## [0.7.0 Accounts Payable Increment 4] - Exception Operations

### Added
- A deterministic current exception queue over saved document-review,
  exception, OCR-review, and duplicate-candidate evidence.
- Visible source-change, overdue/scheduled follow-up, unworked, and documented
  states with every ordering reason exposed and no hidden priority score.
- Append-only professional actions with operator-supplied owner/recorder,
  optional follow-up, exact source snapshot, and canonical evidence integrity.

### Explicit limits
- Work owners are not authenticated assignments; no approved SLA, escalation,
  notification, automatic resolution, or source correction is implied.
- Dispositions do not clear exceptions, approve invoices, authorize payments,
  communicate externally, post, export, or write to ERP.

## [0.7.0 Credit Risk Increment 5] - Order Decision Preparation

### Added
- Operator-entered contemplated-order scenarios over current read-only customer,
  line, partial-exposure, assessment, proposal, and portfolio-review evidence.
- Exact projected partial exposure, availability, over-line, and utilization
  calculations with explicit missing order/full-exposure/policy/authority gates.
- Append-only professional order recommendations with reconstructable source
  evidence and canonical integrity hashes.

### Explicit limits
- Scenario inputs are not verified ERP orders and projected amounts are not full
  exposure or approved policy results.
- No automatic recommendation, Decision, approval, hold/release, line/terms
  change, notification, posting, export, or ERP write is introduced.

## [0.7.0 Accounts Payable Increment 3] - Vendor and Cash Evidence

### Added
- Vendor document-evidence rollups for volume, extracted totals, due-date
  coverage, review, exception, duplicate, and OCR patterns.
- Due-date cash windows relative to a selected as-of date with measured missing
  due-date and amount coverage.
- Append-only cash evidence scenarios with explicit horizon/review assumptions,
  included invoice/source hashes, and canonical evidence integrity.

### Explicit limits
- Vendor groups are not reconciled ERP vendor-master entities and receive no
  performance score.
- Cash windows/scenarios do not know current payable/payment status and create
  no cash forecast, payment proposal, approval, authorization, posting, or ERP write.

## [0.7.0 Credit Risk Increment 4] - Portfolio Monitoring

### Added
- Assessed-customer portfolio monitoring with inherited Priority & Alerts order,
  review cadence, draft-band watchlist, and current source-degradation evidence.
- Explicit partial-exposure concentration by saved draft band, including the
  measured population and unavailable-source coverage.
- Append-only professional portfolio-review dispositions bound to the current
  assessment, optional proposal, exact evidence snapshot, and canonical hash.

### Explicit limits
- The draft watchlist is not approved policy, and the monitored population is
  not the full ERP customer universe.
- Reviews are workflow metadata only; no assignment, notification, escalation,
  credit decision, line/terms/order action, or ERP write is introduced.

## [0.7.0 Accounts Payable Increment 2] - Control Readiness

### Added
- Approval Center and Payment Controls views over real imported invoice evidence.
- Immutable evidence-bound cases with document, exception, duplicate,
  source-revision, and operator-supplied segregation checks.
- Append-only assigned-reviewer readiness dispositions and reconstructable history.

### Explicit limits
- Evidence ready is not invoice approval. Payment preparation is not payment
  authorization. Operator names are not authenticated identities or authority.
- ERP vendor/AP verification, approval tiers, payment rails, dual authorization,
  posting, workflow execution, and notifications remain unavailable.

### Preserved
- No approval, payment, funds release, posting, export, vendor communication,
  AI action, external transfer, or ERP write.
- Credit Risk Increments 1–3, AP Increment 1 invoice evidence, Document
  Intelligence, Lockbox, Reporting, Automation, and existing authority boundaries.

## [0.7.0 Credit Risk Increment 3] - Credit-Line Intelligence

### Added
- Customer-level sales, current-line, partial-exposure, available-credit,
  high-balance, monthly-high-balance, and average-daily-balance evidence.
- Exact server-verified two-month annualized-sales reference with its formula,
  knowledge class, policy status, and unavailable/invalid states.
- Append-only professional credit-line proposals with review date, analyst,
  rationale, exact evidence snapshot, integrity hash, and reloadable history.

### Explicit limits
- The analytical reference is not approved policy or an automatic
  recommendation. Full exposure, seasonality, related accounts, approval
  authority, and workflow remain unavailable.
- A saved proposal is a professional recommendation only; it does not approve,
  execute, notify, change a line/terms/hold, release an order, or write to ERP.

### Preserved
- Credit Risk Increments 1–2, Customer 360, legacy Priority Review, AP,
  Lockbox, Reporting, Automation, and all existing authority boundaries.

## [0.7.0 Accounts Payable Increment 1] - Invoice Intelligence Foundation

### Added
- Dedicated Accounts Payable workspace with source-grounded Executive,
  Invoice Intelligence, OCR Review, Exception Review, and Duplicate Detection
  views.
- Idempotent import of completed vendor-invoice evidence already saved by
  Document Intelligence; the AP module never opens source PDFs or reruns OCR.
- Field-level source authority, immutable evidence revisions and timeline
  events, explicit review/exception reasons, and conservative exact-identity
  duplicate candidates.
- Search, filtering, pagination, source refresh, invoice detail, provenance,
  source-coverage disclosure, and responsive operational states.

### Explicit limits
- Document/extraction review is not AP invoice approval, payment authority, or
  evidence that an ERP payable exists.
- ERP vendor/AP, PO/receiving, payment, GL, workflow, budget, cash, discount,
  and organizational sources remain unavailable until governed mappings are
  connected.
- Three-way match, touchless coding/routing, cash simulation, payment center,
  vendor health/portal, mobile approval, AI insight, and knowledge-graph
  capabilities remain later increments.

### Preserved
- No approval, coding acceptance, routing, payment, export, posting,
  notification, external communication, AI action, or ERP write is added.
- Existing Credit Risk, Customer 360, Priority Review, Lockbox, Reporting,
  Automation, SQL, and Document Intelligence behavior remains unchanged.

## [0.7.0 Credit Risk Increment 2] - Priority and Alerts

### Added
- Assessed-customer-only Priority and Alerts workspace with explicit disclosure
  that customers without a saved manual assessment are excluded.
- Deterministic work ordering by review timing, latest saved manual rating,
  deterioration, available current partial over-line evidence, next-review
  date, and customer number.
- Latest/prior immutable assessment references and hashes, explainable alert
  reasons, degraded per-customer live evidence, and drill-through to Customer
  Risk 360.
- A default `draft_band_attention` filter for ratings 7–10 only when their
  exact saved Product Owner draft band snapshot carries the corresponding
  high-risk draft meaning.

### Explicit limits
- The draft-band filter is contextual work organization, not approved policy,
  a score, recommendation, decision, or action.
- Broken-promise and NSF sources are explicitly unavailable and emit no alerts.
- Alert lifecycle, assignment, acknowledgment, escalation, roles, business
  timezone, full exposure, related accounts, and notifications remain later
  increments.

### Preserved
- No automatic score, credit recommendation, approval, hold/release,
  line/terms change, order decision, AI action, export, posting, or ERP write.
- The legacy 0–100 Customer Health/Priority Review remains separate and
  unchanged.

## [0.7.0 Credit Risk Increment 1] - Credit Risk Foundation

### Added
- Dedicated Credit Risk workspace using the existing real Customer 360 search
  and read-only ERP customer facts.
- Source-grounded Risk 360 context for credit line, open A/R, ERP on-order
  aggregate, current observed exposure, aging, last-payment evidence, and
  explicit missing-data status.
- Versioned Product Owner-supplied draft 1–10 risk bands.
- Local append-only manual assessments with review date, next-review date,
  analyst, rationale, exact band snapshot, evidence snapshot, and integrity
  hash.
- Reloadable assessment history and deterministic backend/workflow coverage.
- Fail-closed required numeric source validation and honest available,
  partial, degraded, or absent last-payment evidence states.

### Explicit limits
- Current observed exposure is partial until the required shipment, releasable
  order, unapplied cash, valid credit, and secured-amount sources are governed.
- Actor identity is operator-supplied and authority is not independently
  verified; an assessment does not approve or execute a credit action.
- Priority/alerts, automatic scoring, credit-line recommendation, order
  decisioning, approvals, AI analysis, and predictive/portfolio intelligence
  remain later increments.

### Preserved
- MaddenCo/ERP remains read-only.
- Existing Customer 360, Priority Review, Lockbox, Reporting, Automation, SQL,
  approval, posting, and export-authority behavior remains unchanged.
- The release package contains no operational database, customer record,
  document, export, credential, log, or cache.

## [0.7.0 Wave 2 Increment 4C] - Reporting Workflow and Governed Automation

### Corrected
- Replaces Report Builder's nonexistent report-execute/report-export calls
  with the existing read-only `/sql/execute` preview and `/sql/export` CSV
  contracts, including the live server row cap and connection state.
- Completes persisted report catalog, design, validation, save, preview, CSV
  export, and non-parameterized recurring schedule workflows with explicit
  loading, empty, degraded, failure, retry, busy, and stale-result states.
- Aligns Report Builder weekly schedules with Automation Service's governed
  Sunday-first `0..6` weekday contract.
- Aborts and invalidates an in-flight preview when SQL, parameters, report, or
  workspace context changes, preventing an older response from repopulating a
  stale result under a newer definition.
- Prevents Automation Center from showing an activation as successful until
  the backend accepts and returns the governed definition.
- Restores the active-source ESLint boundary so archived duplicate frontend
  trees do not create parser failures; the known active-source debt remains
  visible instead of being hidden.

### Added
- Automation definition validation for schedule time, timezone, weekdays,
  monthly dates, script path/type, saved-report identity, and required email
  recipient presence before activation or execution.
- Timezone-aware next-run calculation, durable cross-process execution claims,
  fail-closed restart recovery, invalid-definition quarantine, scheduler
  diagnostics, and `/api/v1/automations/health`.
- Deterministic Report Builder and Automation Service regression coverage.

### Explicit limits
- Direct Report Builder export remains CSV-only and capped by the existing SQL
  service. Direct XLSX is unavailable; XLSX remains available through a saved
  scheduled automation.
- Parameterized report schedules remain unavailable because the current
  Automation Service does not bind persisted report parameter values.
- Custom cron, automatic replay after interruption, cancellation, adapter
  allowlists, retention policy, and compensating actions remain unavailable or
  ungoverned.
- PowerShell/Python execution and email/folder delivery remain governance-
  blocked unless the Product Owner explicitly delegates their owner, scope,
  adapter, credential, and action authority.

### Preserved
- Changes no Lockbox extraction, customer resolution, allocation, preparation,
  approval, export, posting, or ERP-write behavior.
- Keeps report execution inside the existing read-only SQL boundary and keeps
  interrupted automation replay under explicit operator control.
- Includes no operational PDF, extraction/result JSON, database, export,
  credential, cache, or customer/check evidence.

## [0.7.0 Wave 2 Increment 4B] - Madden Customer Schema Compatibility

### Corrected
- Removes the invalid `TMCUST.CUCITY` dependency from Customer Identity
  search because the production MaddenCo customer table has no standalone
  city column.
- Preserves address and locality context through `CUADDRESS1` through
  `CUADDRESS4`, `CUSTATE`, and `CUZIP`; the review workspace continues to
  parse city/state/ZIP from the returned address lines.
- Keeps exact currently open 8- or 9-digit invoice lookup and customer-owner
  ranking from Increment 4A intact.

### Preserved
- Changes no customer selection authority, allocation, approval, export,
  posting, database-write, or ERP-write behavior.
- Adds a regression that fails if hardcoded `CUCITY` SQL returns to the shared
  Customer 360 search.

## [0.7.0 Wave 2 Increment 4A] - Current Review Evidence and Invoice Search

### Corrected
- Refreshes the reviewer-selected customer's complete current ERP Open A/R
  before saving or approving short service-charge rows, so a customer selected
  during professional review is not rejected by an empty earlier preparation
  snapshot.
- Allows the customer-search field to find customer candidates by an exact
  normalized currently open 8- or 9-digit ERP invoice number.
- Returns customer address context with search results so invoice-based
  selections hydrate the review form consistently.

### Preserved
- Requires every service-charge row to match a different exact current ERP
  `SC` open-item key and blocks closed, missing, ambiguous, duplicated,
  cross-customer, or unavailable evidence.
- Keeps customer selection explicit and changes no automatic allocation,
  approval authority, export, posting, or ERP-write behavior.

## [0.7.0 Wave 2 Increment 3Z] - Multiple Service-Charge Review Validation

### Corrected
- Allows one reviewed transaction to contain multiple monthly ERP `SC` open
  items when every row maps to a different exact service-charge identity in
  the selected customer's saved current Open-A/R preparation snapshot.
- Validates reviewer-added service charges against the complete prepared
  Open-A/R set rather than only the smaller automatic recommendation.
- Replaces the singular internal approval error with operator language that
  explicitly permits multiple service charges.

### Preserved
- Blocks reuse of the same `SC` open-item key, forged or typed short
  identifiers, duplicate prepared identities, and service charges absent from
  the governed preparation snapshot.
- Changes no extraction, customer resolution, automatic allocation,
  preparation count, approval authority, export, posting, or ERP-write rule.

## [0.7.0 Wave 2 Increment 3Y] - Review Flow and PNC Site Compatibility

### Corrected
- Advances to the next remaining professional-review transaction in source
  order after an explicit approval is saved successfully; wraps to the first
  remaining exception and closes the workspace when the queue is complete.
- Admits PNC transaction headers with a governed three-letter processing-site
  code, allowing Dallas and Pittsburgh lockboxes to use the same OCR,
  transaction-boundary, and preparation workflow.
- Removes the repeated batch-level parser-warning stack from the transaction
  queue because unresolved items are reviewed individually.

### Preserved
- Keeps every parser warning in saved result/evidence even though the redundant
  queue-level presentation is hidden.
- Does not infer lockbox identity from a `P` or `D` filename suffix; the PDF's
  PNC transaction header remains source evidence.
- Keeps the 8/9-digit invoice contract, current 3X customer/allocation rules,
  explicit human approval, read-only ERP boundary, and protected 23/38/0 floor
  unchanged.

## [0.7.0 Wave 2 Increment 3X] - ERP-Backed Remittance-Row Disambiguation

### Corrected
- Restores the governed ERP invoice contract to 8- and 9-digit numbers after
  Product Owner validation confirmed there are no 10-digit ERP invoices.
- Resolves an ambiguous remittance row containing both a K&M invoice and a
  payer purchase-order number only when the selected customer's complete
  current open A/R proves exactly one candidate and the full signed ERP amount
  equals the preserved row payment amount exactly to the cent.
- Feeds only the fully resolved row set into allocation and records a versioned
  assessment that protected projection independently verifies.

### Preserved
- Keeps every raw candidate, purchase order, parser rejection, page, OCR mode,
  and prior preparation generation unchanged and auditable.
- Keeps amount mismatches, multiple ERP-valid candidates, duplicate open items,
  cross-customer evidence, service charges, other rejection reasons, partial
  recovered sets, approval, export, posting, and ERP writes blocked.
- Protects the verified Increment 3W baseline at 23 Prepared & Balanced / 38
  Needs Review / 0 Approved and creates a new append-only generation without
  rerunning OCR.

## [0.7.0 Wave 2 Increment 3V] - Remaining Open-A/R Residual Completion

### Corrected
- Continues allocation after complete remit-invoice matching by evaluating the
  verified customer's remaining current open A/R.
- Adds one remaining ordinary invoice or signed credit only when exactly one
  same-customer item's full ERP open amount equals the residual.
- Allows the unique exact residual item to close the check even when another
  older open item exists, correcting the premature oldest-first stop shown by
  the reported exact remaining difference.

### Preserved
- Incomplete remit evidence, zero or multiple residual matches,
  cross-customer rows, partial applications, source conflicts, nonzero
  results, approval, and ERP writes remain blocked.
- Existing service-charge, full-balance, aging, due-date, oldest-prefix,
  signed-credit, immutable-source, and human-review rules remain intact.
- Creates a new append-only preparation generation and does not rewrite the
  accepted Increment 3U result or any human disposition.

## [0.7.0 Wave 2 Increment 3U] - Current-Open Owner Evidence Precedence

### Corrected
- Recognizes a complete saved `current_open_invoice_owner` assessment as the
  authoritative customer proof when it reconciles every admitted remittance
  invoice to exactly one same selected ERP customer.
- Prevents stale broad invoice-owner incompleteness and contact-ranking flags
  from vetoing that stronger current-open proof while preserving every lower-
  authority flag and warning for audit.

### Preserved
- Keeps missing, unavailable, mismatched, split, or duplicate current-open
  ownership; incomplete source timestamps; payer directives; source conflicts;
  nonzero allocations; approval signals; and ERP writes fail-closed.
- Changes only read-time projection interpretation. No OCR, ERP query,
  preparation generation, stored result, review draft, approval, export,
  posting, or ERP-write path changes.
- Protects the active 61-item source at 17 Prepared & Balanced / 44 Needs
  Review / zero approved and permits 21/40/0 only when the four diagnosed
  candidates satisfy the complete saved current-open evidence envelope.

## [0.7.0 Wave 2 Increment 3T] - Fresh-Source Exception Classification

### Corrected
- Preserves each fresh source's already-classified professional-review
  exception instead of rebuilding it from an empty synthetic review floor.
- Keeps blocked balanced candidates distinct as `projection_evidence_gate_blocked`.
- Prevents ordinary customer, evidence, and allocation exceptions from being
  mislabeled as technical preparation failures.

### Preserved
- Keeps the new source at 66 Prepared & Balanced, 121 Needs Review, and zero
  approved while retaining its raw 76 balanced / 111 exception candidate.
- Changes no OCR, customer resolution, allocation, stored preparation,
  review-draft, approval, export, posting, or ERP-write behavior.

## [0.7.0 Wave 2 Increment 3S] - Fresh-Source Preparation Bootstrap

### Corrected
- Allows a processed Lockbox PDF with no historical preparation to register
  and run its own current-rule ERP/allocation generation instead of requiring
  the prior 78-transaction PDF's exact Increment 3E control identity.
- Gives a new source its own fail-closed first projection: every non-human
  transaction begins in review, and only the existing deterministic customer,
  governed allocation, exact arithmetic, source, boundary, sign, no-approval,
  and no-write gates may promote it to Prepared & Balanced.
- Labels a processed source with no generation as **Start ERP & Allocations**;
  **Resume** is reserved for an actual saved preparation generation.

### Preserved
- Existing sources that have the accepted Increment 3E control continue to use
  the unchanged Increment 3R protected projection and 43/35/0 floor.
- New-source counts come only from that source's complete terminal transaction
  set; the old 78/30/48 control and later projected counts are never borrowed.
- OCR, parser, matching, allocation, review drafts, approval, export, posting,
  and ERP read-only behavior remain unchanged.

## [0.7.0 Wave 2 Increment 3R] - Corroborating-Field Conflict Gate

### Corrected
- Recognizes that payer/payee name and city are corroborating fields—not
  ownership anchors—after a complete bounded read proves exactly one
  phone-plus-postal ERP owner.
- Allows only a name/city-only recorded conflict set to remain nonblocking for
  the `exact_phone_and_zip` basis; the recorded conflict count must reconcile
  exactly to the preserved conflict-field set.

### Preserved
- Original OCR values, raw conflict fields, and the final nonmaterial-field
  classification remain auditable in the control-projection envelope.
- Every phone, ZIP, street, state, customer-number, invoice-owner,
  candidate-completeness, allocation, boundary, approval, and ERP-write
  conflict remains review. A city conflict also remains blocking for every
  selection basis other than complete unique `exact_phone_and_zip`.
- The accepted 43 balanced / 35 review / 0 approved Increment 3Q projection is
  the protected floor; the completed candidate is reprojected without OCR.

## [0.7.0 Wave 2 Increment 3Q] - Deterministic Promotion Evidence

### Corrected
- Replaces the blanket 99% control-projection threshold with basis-specific
  verification of the preserved complete ERP candidate universe.
- Allows the resolver's intentional 97% exact phone-plus-ZIP result to promote
  only when exactly one owner is proven by a complete bounded read.
- Treats one preserved name-only payer/payee conflict as nonblocking only after
  complete exact phone-plus-ZIP or street-plus-ZIP ownership is independently
  established; the original assertion remains auditable.

### Preserved
- Duplicate/incomplete candidate sets, invoice-owner, phone, ZIP, street,
  allocation, source-row, and transaction-boundary conflicts remain review.
- The existing Increment 3P candidate is reprojected without OCR, a new ERP
  write, automatic approval, posting, export, or reviewer-state overwrite.
- The accepted 35 balanced / 43 review / 0 approved projection remains the
  protected floor.

## [0.7.0 Wave 2 Increment 3P] - Unified Lockbox Decision

### Improved
- Recognizes a payer-authored `Apply/Post to account` or K&M customer-account
  directive only when one unique 4–12 digit account is printed and the exact
  ERP customer exists; generic bank-account labels never enter this rule.
- Reruns and projects the final governed allocation after customer resolution
  and complete ERP retrieval while preserving any dirty, balanced, corrected,
  or approved reviewer draft.
- Caps one overstated remittance invoice at its current ERP open amount and
  uses one unique same-customer `SC` item only when it exactly closes the
  remittance remainder.
- Recomputes final status, confidence, and exception reason from one unified
  customer/allocation/projection decision rather than retaining stale
  ambiguity text.

### Preserved
- The accepted 35 balanced / 43 review / 0 approved Increment 3O result is the
  protected floor. Historical, incomplete, conflicting, cleared-A/R, and
  multiply satisfiable cases remain review.
- Six-worker OCR/read concurrency, immutable source evidence, signed credits,
  human authority, and the read-only ERP/no-posting boundary remain unchanged.

## [0.7.0 Wave 2 Increment 3O] - Six-Worker Exception Funnel

### Improved
- Raises bounded OCR and durable preparation read concurrency to six workers
  while preserving OCR quality, source regions, page order, and a single
  serialized result writer.
- Resolves a customer from one complete exact street-plus-ZIP ERP owner when
  invoice and phone evidence do not conflict; duplicate or incomplete
  candidate universes remain ambiguous.
- Adds exact signed allocation fallbacks for the complete open balance, one
  full aging bucket, and one chronological oldest-item prefix, retaining the
  existing exact due-date and remittance rules.

### Preserved
- Re-evaluates all 30 near-success exception cases through generalized rules;
  no customer, allocation, or count is hardcoded.
- The accepted 33 balanced / 45 review / 0 approved result is the protected
  floor, and multiple solutions, nonzero balances, automatic approval,
  export, posting, and ERP writes remain blocked.

### Verified
- 156 governed backend tests, four privacy-safe Python increment verifiers,
  ten Lockbox runtime regressions, targeted frontend lint, and the production
  build pass.

## [0.7.0 Wave 2 Increment 3N] - Payer Completeness Gate Correction

### Corrected
- Keeps bounded same-page payer OCR open when the primary crop contains an
  exact phone, ZIP, and stale payee name but no street address.
- Requires a street contact anchor before the primary check crop may terminate
  payer-region evaluation; if no region contains one, all bounded regions are
  still compared and the strongest evidence remains reviewable.
- Invalidates the Increment 3M extraction cache through a new parser/rule/
  service generation while preserving the accepted 33 balanced / 45 review /
  0 approved floor.
- Adds the live-shaped privacy-safe regression omitted by the Increment 3M
  verifier and retains every invoice, conflict, arithmetic, approval, export,
  posting, and ERP-write gate.

## [0.7.0 Wave 2 Increment 3M] - Bounded Check-Payer Resolution

### Corrected
- Adds bounded same-page payer-region OCR when the primary detected check crop
  lacks a complete phone-and-ZIP payer identity.
- Preserves a stale payee name as source evidence without allowing that
  name-only disagreement to block a high-confidence phone, ZIP, name, and
  address payer block.

### Preserved
- Complete invoice ownership remains first priority; exact-phone uniqueness,
  complete ERP reads, supplied-ZIP conflict, duplicate-phone ambiguity, exact
  allocation, source preservation, and human authority remain unchanged.
- The accepted 33 balanced / 45 review / 0 approved Increment 3L projection is
  the fail-closed floor; no automatic approval, export, posting, or ERP write
  is added.

### Verified
- Privacy-safe primary-crop, bounded-fallback, stale-payee, ZIP-conflict,
  duplicate-phone, incomplete-read, projection-floor, and end-to-end customer
  resolution regressions pass.

## [0.7.0 Wave 2 Increment 3L] - Spatial Remittance-Row Recovery

### Corrected
- Reconstructs invoice/date/amount table rows when governed sparse OCR splits
  their columns into different logical lines but preserves them on one visual
  row.
- Routes recovered 8/9-digit invoices through the unchanged current-open ERP
  and exact-reconciliation pipeline.

### Preserved
- Adjacent visual rows never join; monetary masking, invoice admission,
  cross-source conflict handling, next-transaction boundaries, signed credits,
  and source provenance remain fail-closed.
- The accepted 32 balanced / 46 review / 0 approved Increment 3K projection,
  every prior generation, human disposition, and no-ERP-write boundary remain
  protected.

### Verified
- Synthetic split-column rows reconstruct exactly, adjacent rows remain
  separate, current ERP amounts reconcile, and a qualifying review promotion
  can improve the projection to 33/45 with zero regression.

## [0.7.0 Wave 2 Increment 3K] - Unique-Phone Customer Resolution

### Corrected
- Resolves one ERP customer from an exact normalized ten-digit check phone
  when a complete bounded read proves exactly one phone owner and invoice
  evidence supplies no usable owner.
- Treats a supplied valid five-digit ZIP mismatch as a hard conflict while
  preserving ZIP, address, city/state, and name as corroborating evidence.
- Sends the supported customer through the existing complete read-only open-
  A/R and allocation pipeline, allowing a balanced control review to promote
  only through the existing strict projection gates.

### Preserved
- Complete invoice ownership remains first priority; invoice conflicts,
  partial owner evidence, duplicate phones, and incomplete phone reads remain
  review.
- Increment 3I control state, Increment 3J review completeness, all human
  dispositions, no automatic approval, and no ERP writes remain protected.

### Verified
- Deterministic privacy-safe reported-case coverage plus unique-phone,
  duplicate-phone, conflicting-ZIP, invoice-priority, provider, and strict-
  projection regressions pass.

## [0.7.0 Wave 2 Increment 3J] - ERP Open-A/R Review Completeness

### Corrected
- Makes a failed ERP open-A/R request visible instead of silently converting
  it into an empty invoice list.
- Automatically exposes the selected customer's current ERP open items and
  signed open balance in the review workspace.
- Preserves `SC` service-charge rows by governed open-item key instead of
  discarding them for not satisfying the 8/9-digit invoice-number contract.
- Includes `SC`, signed credits, references, counts, due dates, and aging in
  manual selection and exact due-date review recommendations.

### Preserved
- Increment 3I remains the authoritative 31 balanced / 47 review projection.
- No preparation generation, control count, automatic approval, ERP write,
  posting behavior, or human disposition is changed.

### Verified
- 126 backend tests, ten Lockbox regression scripts, targeted frontend lint,
  and the production build pass.

## [0.7.0 Wave 2 Increment 3I] - Control-Preserving Lockbox Projection

### Added
- Binds every Increment 3I candidate generation to the exact accepted 3F R1
  78/30/48 control identity before any candidate work is created.
- Preserves every accepted balanced transaction and human disposition while
  evaluating new deterministic logic only for control review items.
- Admits a promotion only when customer evidence, allocation method, exact
  arithmetic, signed credits, source-row preservation, and transaction
  boundary evidence all pass the R4 gate.
- Keeps blocked improvements and weaker customer/allocation evidence as
  operator recommendations without automatic allocation or approval.
- Adds immutable saved-evidence merging, versioned parser output, and the
  next `Transaction Information` boundary; displayed `Num Pages` is not used
  to truncate a transaction.

### Verified
- Synthetic runtime projection reproduces 31 balanced / 47 review, one
  admitted promotion, one blocked promotion, 22 raw regressions contained,
  three operator assists, and zero projected regressions.
- 126 targeted backend tests, frontend production build, and targeted lint
  pass. Recommendation remains distinct from Decision; ERP access is read
  only and no approval, export, posting, or ERP write is added.

### Lineage
- Increment 3F R1 remains the authoritative control.
- Rejected 3G and 3H generations are preserved as history and are never
  selected as control. Their candidate rules cannot replace accepted state.

## [0.7.0 Wave 2 Increment 3F] - Governed Preparation UI and Review Integrity

### Corrected
- Replaces browser-owned Lockbox preparation counts and queue membership with
  one current-rule durable backend projection. The observed raw 19/59 screen
  now projects the governed 30/48 result from the same saved generation.
- Removes duplicate GET/PUT review routes that caused all 78 browser review
  writes to fail schema validation while appearing as preparation errors.
- Consolidates review and reviewed-export persistence through one canonical
  store and migrates legacy human reviews idempotently without deleting the
  legacy database.
- Persists the selected ERP customer number and identity with the human review.
- Preserves parser/extraction versions and remittance/OCR diagnostics through
  FastAPI response models.

### Added
- Adds a read-only current-generation query bound to source job, immutable PDF
  hash, and the unchanged Increment 3E matching rule.
- Reconciles expected, terminal, balanced, exception, preserved, and primary-
  reason counts before final UI metrics or reviewed export are available.
- Shows governed exception reason totals and preserves versioned ranked-
  candidate snapshots, match factors, score, and bounded-query completeness
  for professional review without changing selection behavior.
- Blocks reviewed export until the current governed generation is final and
  every professional-review exception has a human disposition.

### Preserved
- Increment 3F changes presentation, persistence, and evidence visibility only;
  it does not create a new matching-rule generation or change any 3E outcome.
- The 8/9-digit invoice, unique phone+ZIP, complete current-owner/CUNUMENT,
  exact allocation, no-auto-approval, and no-ERP-write controls are unchanged.

### Governance
- Adds BR-LOCKBOX-014 and BR-LOCKBOX-015 across ADR-001, DEC-CASHAPP-001,
  CAP-LOCKBOX-001, the release charter, Platform Service mappings, and the
  Blueprint traceability matrix.
- Adds deterministic duplicate-route, migration, API-evidence, count-
  reconciliation, export-gate, and exact 19/59-to-30/48 UI parity tests.

## [0.7.0 Wave 2 Increment 3E] - Evidence Integrity and Direct Current Owner

### Added
- Masks monetary spans before invoice detection and admits only one distinct
  governed 8/9-digit candidate per remittance row.
- Preserves rejected raw candidates, page, embedded/OCR source, OCR mode, and
  explicit parser version; substantial remittance images receive PSM 6 then
  PSM 11 fallback when embedded evidence is insufficient.
- Reads current `TMAROP` ownership once for every admitted invoice through a
  bounded, chunked, read-only query independent of broad candidate count.
- Adds structured exception reasons for incomplete owner evidence, duplicate
  or truncated contact candidate sets, unconfirmed candidates, and rank-only
  ambiguity.

### Corrected
- Prevents the integer portion of an amount such as `12345.67` from becoming
  a false invoice candidate.
- Prevents long embedded header text from suppressing OCR of a substantial
  remittance image.
- Removes Pydantic request-size failure from internal preparation so more than
  100 admitted invoices or oversized OCR identity fields do not abort a
  transaction.
- Requires complete exact phone/ZIP and nonzero CUNUMENT candidate universes;
  duplicate or bounded/truncated reads remain review evidence.

### Preserved
- The shared ERP admission rule remains exactly 8 or 9 digits; rejected
  identifiers are never padded, truncated, guessed, or passed to ERP matching.
- No automatic approval, cross-customer authority, ERP write, or posting
  surface was added.
- Increment 3D and every earlier result, event, generation, and human
  disposition remain unchanged.

### Governance
- Added BR-LOCKBOX-012 and BR-LOCKBOX-013 across ADR-001, DEC-CASHAPP-001,
  CAP-LOCKBOX-001, the release charter, source-authority matrix, and Blueprint
  traceability matrix.
- Added deterministic remittance, parser, current-owner, high-cardinality,
  validation, generation, and safety counterexamples.

## [0.7.0 Wave 2 Increment 3D] - Enterprise Customer Group Verification

### Added
- Resolves Lockbox contact fallback only when normalized check phone and the
  first five ZIP digits uniquely match one ERP customer; phone alone and
  duplicate phone/ZIP pairs remain ambiguous.
- Reads `TMCUST.CUNUMENT` after a customer is supported and retrieves the
  matched account, enterprise account, and every linked customer account.
- Retrieves current read-only open AR for each linked account and preserves
  account/customer numbers on every proposed allocation row.
- Permits a split invoice-owner conflict to become an enterprise-group review
  only when the phone/ZIP anchor is unique, every current invoice has one
  owner, and every owner is inside the same complete CUNUMENT group.
- Classifies exact remittance invoices spanning linked accounts as
  `linked_customer_allocation_review` rather than balanced or approved.

### Preserved
- CUNUMENT expands verification evidence; it does not prove payment intent or
  authorize cross-customer application.
- Missing group members, owners outside the group, duplicate current owners,
  incomplete bounded reads, and unavailable linked open AR remain exceptions.
- Name remains supporting evidence only, `can_auto_approve` remains false,
  and no ERP write or posting surface was added.
- Increment 3C generation 3 and every prior result, event, and human
  disposition remain unchanged; Increment 3D runs as generation 4.

### Governance
- Added BR-LOCKBOX-010 and BR-LOCKBOX-011 to `ADR-001`,
  `DEC-CASHAPP-001`, `CAP-LOCKBOX-001`, the release charter,
  source-authority matrix, and Blueprint traceability matrix.
- Added deterministic regressions for phone/ZIP uniqueness, nonzero
  CUNUMENT expansion, cross-account exact remittance review, out-of-group
  owners, degraded linked-account reads, generation 4, no approval, and no
  ERP write.

## [0.7.0 Wave 2 Increment 3C] - Current-Open Customer Conflict Resolution

### Added
- Reconciles broad ERP invoice-owner conflicts against current read-only open
  AR for every candidate customer.
- Recommends one customer only when every valid remittance invoice is
  currently open under exactly one and the same candidate.
- Persists a versioned assessment containing the broad owners, current-open
  owners, missing invoices, unavailable reads, source references, as-of times,
  explanation, and safety flags.
- Appends a `customer_conflict_assessed` event for each evaluated conflict.

### Preserved
- Missing, unavailable, split, and still-multiple current-open evidence remains
  a `customer_conflict` exception; failed candidate reads remain retryable.
- Phone, address, ZIP, name, score, or confidence cannot override a remaining
  invoice-owner conflict.
- Increment 3B generation 2 results, human dispositions, and events remain
  unchanged; Increment 3C runs as generation 3.
- The result remains a Recommendation input requiring professional review.
  `can_auto_approve` is false, ERP access is read-only, and no posting surface
  was added.

### Governance
- Added BR-LOCKBOX-009 to `ADR-001`, `DEC-CASHAPP-001`,
  `CAP-LOCKBOX-001`, the release charter, source-authority matrix, and
  Blueprint traceability matrix.
- Added deterministic regressions for unique, split, missing, unavailable,
  append-only generation, no-auto-approval, and no-ERP-write behavior.

## [0.7.0 Wave 2 Increment 3B R2] - Versioned Preparation Identity

### Fixed
- Corrected durable preparation identity so the same preserved Lockbox PDF may
  receive a new preparation generation when the governed rule version changes.
- Increment 3A results created under the former invoice-admission rule no
  longer block Increment 3B evaluation with a transaction/source fingerprint
  conflict.
- Upgrades the local preparation schema transactionally from version 2 to 3,
  replacing the one-generation-per-source constraint with one generation per
  source and rule version.

### Preserved
- Earlier preparation jobs, transaction results, human dispositions, and
  append-only events remain intact and readable as generation 1.
- Repeating the same source under the same rule remains idempotent.
- Changed transaction evidence within one rule version still raises a durable
  identity conflict instead of overwriting history.
- ERP access remains read-only; no approval, posting, or automatic disposition
  behavior was added.

### Governance
- Amended `ADR-001`, `CAP-LOCKBOX-001`, the 0.7.0 release charter, and the
  traceability matrix with the versioned re-preparation identity contract.
- Added migration and rule-generation regressions, including preservation of a
  prior human disposition and foreign-key integrity validation.

## [0.7.0 Wave 2 Increment 3B] - ERP Invoice Number Contract Correction

### Fixed
- Corrected the authoritative ERP invoice-number rule from the mistaken
  9/10-digit assumption to exactly 8 or 9 digits.
- Centralized backend and frontend normalization so customer resolution,
  durable preparation, allocation evaluation, failed-transaction evidence,
  review validation, and shared invoice matching use the same boundary.
- Eight-digit remittance invoices now enter read-only ERP invoice-owner and
  allocation matching. Seven- and 10-digit values are rejected as ERP invoice
  evidence.
- `9999999999` remains available only as the controlled no-remittance review
  placeholder and is never submitted to ERP matching.

### Preserved
- Raw OCR candidates remain preserved even when they are invalid ERP invoice
  evidence.
- Existing saved preparation results and append-only history are not silently
  rewritten; the corrected rule applies to new evaluation and current review
  validation.
- Customer-ranking weights, ambiguity behavior, allocation tolerance, human
  authority, read-only ERP access, and no-auto-approval controls are unchanged.

### Governance
- Amended BR-LOCKBOX-001 in `ADR-001`, `DEC-CASHAPP-001`, the Lockbox release
  charter, capability specification, and traceability matrix.
- Added Python and TypeScript boundary regressions proving 8/9 accepted and
  7/10 plus the no-remittance placeholder rejected.

## [0.7.0 Wave 2 Increment 3A] - Matching Recommendation Intelligence: Exception Reasons

### Added
- Versioned deterministic primary and contributing reason codes for every
  durable `prepared_exception`.
- Backward classification of saved Increment 2D exceptions from preserved
  source/result/error evidence, without OCR, ERP reads, or stored-history
  mutation.
- A job-level exception funnel with primary-reason, contributing-reason,
  category, retry-eligible, classified, and unclassified counts.
- A summary-only durable preparation endpoint for measuring the current
  exception population without returning the full transaction payload.

### Preserved
- Customer ranking, matching priority, exact due-date allocation, the
  one-cent arithmetic equality, retry eligibility, and existing dispositions
  are unchanged.
- `prepared` and `balanced` remain recommendations, not approvals.
- ERP access remains read-only; no ERP write or automatic approval was added.

### Governance
- Amended `ADR-001` and `CAP-LOCKBOX-001` with the versioned exception-reason
  contract and backward-classification boundary.
- Added trace links and deterministic regressions for reason distinctions,
  legacy-record classification, summary reconciliation, and safety controls.

## [0.6.9] - Editable Lockbox Allocation and Credit Sign Control

### Fixed
- The prepared invoice allocation is now the editable review draft instead of
  a separate read-only table above disconnected correction controls.
- Reviewers can edit apply amounts, remove an incorrect invoice, add another
  verified ERP open invoice, or add a blank allocation row directly within
  the expanded recommendation workspace.
- ERP entries carried as `Debit` with a negative source amount are interpreted
  as credits for cash-application arithmetic. The raw ERP type remains visible
  as evidence while open and apply amounts use the negative credit sign.
- Recommendation totals and differences are recalculated after authoritative
  ERP credit-sign reconciliation.
- A positive apply amount for an ERP-derived credit is highlighted and blocked
  from save.
- Existing 0.6.8 prepared transactions receive the corrected sign when opened,
  unless a human correction or approval already exists.

### Preserved
- Original OCR allocations remain unchanged for provenance and training.
- Review changes remain local until Save Correction or Approve Transaction.
- Human approval, the one-cent balance tolerance, 125/125 preparation
  coverage, bounded concurrency, and read-only ERP behavior are unchanged.
- No ERP posting or automatic approval was added.

### Governance
- Amended ADR-001 with editable-recommendation and signed-transaction-effect
  requirements.
- Added regression coverage for the retained negative-debit invoice fixture as a `-$916.00` credit
  despite the raw ERP `Debit` label.

## [0.6.8] - High-Throughput Governed Lockbox Preparation

### Improved
- File-level preparation now resolves all unique 9- or 10-digit remittance
  invoices through bounded bulk ERP requests. Invoice-source discovery and
  ownership queries are performed once per bulk chunk instead of once for
  every check.
- Four read-only preparation workers run concurrently by default. ERP customer
  matching, customer hydration, recommendation analysis, and open-invoice
  evaluation can overlap without increasing concurrency beyond the controlled
  limit.
- Customer-master responses are reused by customer number during the file.
  Open-invoice responses are reused by customer number and effective aging
  date, eliminating repeated reads when one customer has multiple checks.
- Review writes remain serialized. Faster ERP reads cannot create concurrent
  read-modify-write races in the local lockbox review record.
- Preparation checkpoints are stored as individual IndexedDB records rather
  than rewriting one growing `localStorage` payload after every transaction.
  This removes the largest browser-side serialization and quota risk for large
  lockboxes.

### Preserved
- Bulk resolution auto-selects only when the supplied invoices identify one
  unique ERP owner. Missing or multi-customer evidence uses the existing
  transaction-level resolver and remains a review exception when ambiguous.
- Every transaction still requires a saved prepared result, explicit failure,
  or durable prior human decision before ETOP exposes the exception count,
  review table, or reviewed export.
- The six invoices due 7/10/26 still total $1,129.36 and exclude the 8/10/26
  invoices.
- Preparation remains read-only, explainable, resumable, separate from human
  approval, and incapable of ERP posting.
- Existing 0.6.6 and 0.6.7 browser caches remain readable and migrate forward
  when the per-transaction checkpoint store is available.

### Governance
- Amended `ADR-001` with the bulk-resolution, bounded-read-concurrency,
  single-writer, shared-cache, degradation, and checkpoint-store rules.
- Added deterministic regressions for four-worker preparation, serialized
  persistence, one bulk invoice-owner read, shared customer hydration,
  ambiguity fallback, 27-of-125 resume, and exact due-date allocation.

## [0.6.7] - Complete and Resumable Lockbox Preparation

### Fixed
- A partial preparation cache is no longer treated as a completed lockbox.
  ETOP compares saved preparation records to every transaction in the current
  OCR result before calculating or displaying the exception queue.
- Reopening a partially prepared lockbox resumes only the missing
  transactions. A 27-of-125 run resumes at transaction 28 without rerunning
  OCR or recalculating the first 27 prepared checks.
- One ERP lookup, allocation, timeout, or local review-save failure no longer
  aborts the remaining file. The failure is recorded on that transaction,
  remains in review, and processing continues with the next transaction.
- Preparation checkpoints are saved after every transaction so leaving,
  refreshing, or restarting can resume from the last completed check.
- Manual ERP customer selection and the recommendation-panel Refresh action
  now use the same customer-aware due-date allocation pipeline as batch
  preparation. They no longer stop at an empty generic EOM-aging result.
- Selecting the retained verified-customer fixture automatically reevaluates the $1,129.36 payment
  against open invoices and returns the six invoices due 7/10/26 when the ERP
  open-invoice response contains that exact group.
- Exact due-date grouping now reads the authoritative ERP open-invoice rows
  directly. It no longer depends on the broader recommendation response to
  embed invoice due dates and open balances that response may omit.

### Changed
- Lockbox Review, its exception count, and reviewed export remain unavailable
  until preparation coverage reaches the full OCR transaction count.
- An incomplete processed lockbox presents **Resume ERP & Allocations
  (completed/total)** instead of directing the reviewer to rerun OCR.
- Legacy 0.6.6 preparation caches remain readable and are upgraded when they
  are next saved.
- ERP customer selection automatically refreshes the customer-aware allocation
  recommendation; a second manual Refresh click is not required.

### Governance
- Amended `ADR-001` to require file-level preparation coverage,
  checkpoint/resume behavior, transaction-isolated failures, and an explicit
  completion gate before review.
- Preparation errors remain exceptions; they are not approval, ERP posting,
  or evidence that customer/allocation resolution succeeded.

## [0.6.6] - Integrated Lockbox Preparation and Due-Date Allocation

### Changed
- **Process PNC Lockbox** now completes OCR, ERP customer resolution,
  customer-master hydration, open-invoice analysis, allocation preparation,
  and local review persistence before presenting the review queue.
- Every transaction is prepared once during processing instead of waiting for
  the reviewer to select checks individually.
- The default Lockbox Automation and Lockbox Review queues now show unresolved
  exceptions. Prepared and balanced transactions remain available through the
  all-transactions view.
- Prepared customer identity and allocation rows are saved through the
  existing local lockbox review store. The complete analytical envelope is
  cached by job so leaving and reopening the workspace does not rerun the
  recommendation process.
- Opening an older saved OCR result prepares and persists its transactions
  without rerunning OCR, then reuses that upgraded result thereafter.
- Saving or approving a transaction now preserves a saved preparation marker
  instead of invalidating the result and forcing another calculation.

### Fixed
- Exact groups of open invoices sharing one due date are evaluated before
  generalized EOM or aging-bucket combinations.
- When a same-due-date group equals the check, ETOP returns the actual invoice
  rows and explains the exact due date instead of reporting an empty
  aging-bucket match.
- The regression case of six invoices due July 10, 2026 now returns six rows
  totaling $1,129.36 and excludes later August 10 invoices.

### Governance
- Added `ADR-001 — Lockbox Preparation and Exact Due-Date Priority`.
- Prepared/balanced remains distinct from approved; ERP posting remains
  disabled and no straight-through approval authority was added.

## [0.6.5] - Pre-Review ERP and Allocation Preparation

### Changed
- **Prepare & Open Review Workspace** now completes invoice validation, ERP
  customer resolution, customer-master hydration, open-invoice retrieval, and
  allocation analysis before displaying the selected transaction.
- The cash-application decision engine always runs a final second pass after
  the ERP customer is resolved. An early customer-discovery response can no
  longer leave a stale `No Invoice Match` result in the review workspace.
- Switching transactions inside Lockbox Review prepares the selected
  transaction before replacing the visible review draft.
- The prepared result is reused during the active lockbox session and is
  invalidated after the transaction is saved.

### Improved
- Invoice Allocation Detail now has a dedicated high-contrast view with a
  taller scrollable table, sticky column headers, and larger row spacing.
- Reviewers can expand Invoice Allocation Detail to a near-full-screen view
  without changing browser zoom.
- Editable invoice rows now appear in their own larger panel with a stable
  minimum height and visible scrollbars.
- The recommendation panel now uses the Lockbox Review dark theme instead of
  the low-contrast white panel shown in 0.6.4.
- Review entry and transaction switching show explicit ERP-preparation status.

## [0.6.4] - Lockbox Recovery and ERP Invoice Authority

### Fixed
- Previously processed lockboxes are reopened by checking for their durable
  lockbox result instead of relying on the generic document job status.
- Selecting or re-uploading the same PDF name and file size reuses the existing
  job instead of creating another duplicate upload.
- Remittance invoices are validated against ERP automatically when a review
  transaction opens or its invoice evidence changes.
- Only unique 9- or 10-digit invoice values are sent to ERP matching; the
  no-remittance placeholder and invalid OCR values are excluded.
- A verified invoice-owned ERP customer now loads its open-invoice
  recommendation without requiring a separate customer-number search.
- Verified ERP customer-master values fully replace OCR identity fields.
- ERP address lines containing `City, State ZIP` are mapped into the correct
  City, State, and ZIP fields instead of Address Line 2.
- Trailing punctuation is removed from incomplete ZIP values such as `46788-`.
- Lockbox queue, editor, validation, allocation, and customer-result scrollbars
  are wider and use a visible high-contrast thumb.

## [0.6.3] - Current Runtime Consolidation

### Added
- ERP customer search in Lockbox Review across customer number, name, phone,
  and address-oriented search text.
- Explicit ERP customer selection with customer-master hydration for name,
  phone, and address fields.
- The full First Concrete Blueprint Package and Agent Operating Contract.
- Federated enterprise search across modules, customers, reports, documents,
  and SOPs.
- A live customer priority-review queue and explainable risk evidence.
- A restored Report Builder workflow and task-oriented application navigation.
- Processed lockbox reopening and saved-review restoration.
- A guarded development-ZIP builder that requires the Blueprint, operating
  contract, and imported backend source packages before creating an archive.

### Changed
- Cash-application recommendations can resolve a customer from remittance
  invoice numbers without requiring a known customer number first.
- Invoice-derived ERP customer data takes precedence over OCR identity fields;
  OCR values remain only when the ERP record has no replacement value.
- Recommendation calls now reuse the configured local API base.
- Agent 1–4 capabilities were re-merged onto the ERP customer-resolution
  runtime instead of replacing its newer files with the earlier integration.
- Future sanitized exports now carry `ETOP-Blueprint/`, backend source packages,
  and the Agent Operating Contract while continuing to exclude credentials,
  operational data, documents, OCR files, and `SqlEditor.tsx`.

## [0.6.2] - Lockbox Recovery and ERP Customer Matching

### Added
- Reopening saved lockbox OCR results and review edits after leaving the screen.
- An explicit **Open Processed Lockbox** action that does not rerun OCR.
- Live ERP customer search inside the lockbox review workspace.
- Ranked customer recommendations with confidence and match evidence.
- Invoice-first, then phone, address/ZIP, and name-supporting-only match rules.

### Changed
- The last completed lockbox is restored when the user returns to the module.
- Strong, unambiguous customer matches populate the ERP customer number.
- Cash-application recommendations can resolve a customer without a hardcoded
  customer number.

## [0.6.1] - Customer Risk Review

### Added
- Live customer credit-risk review endpoint backed by read-only Madden data.
- Deterministic Critical, High, and Elevated priority scoring.
- Ranked risk reasons, exposure, utilization, past-due, and 60+ day balances
  in the Customer Intelligence side panel.
- Automatic loading of the highest-priority customer from the dashboard work
  queue.

### Changed
- The **Review customers above credit thresholds** dashboard action now
  launches a working priority queue instead of an empty customer search.

## [0.5.1] - Task-Oriented Navigation

### Changed
- Reorganized the application sidebar into Overview, Workspaces, Tools, and
  System.
- Promoted Lockbox Automation to a first-class operational workspace.
- Limited Document Operations to intake, processing, review, and AP work.
- Moved parser quality, learning, profiles, templates, and parser management
  into Document AI Studio.
- Reworked dashboard shortcuts around the business task a user wants to
  complete.
- Added module purpose hints and current-workspace guidance to the shell.

### Fixed
- Coming-soon content now renders only for modules that are actually marked
  Coming Soon.

## [0.5.0] - Enterprise Foundation

### Added
- Global ETOP search and Ctrl+K command palette.
- Shared notification center with read/unread state.
- Universal task panel with local persistence.
- Enterprise timeline panel.
- Frontend platform types, registry, services, and reusable overlay component.
- Platform registry and health API endpoints.

### Changed
- The application title bar now exposes platform-level timeline, task, and notification controls.

### Notes
- Sprint 3 uses browser local storage for tasks and notifications. The service boundaries are ready for a later FastAPI persistence migration.
## 0.7.0 Wave 2 Increment 3W — 2026-08-05

- Admitted governed 10-digit ERP invoice numbers while retaining the
  `9999999999` no-remit exclusion.
- Recovered only preserved, unambiguous prior 10-digit rejected remit rows and
  retained every original rejection and source field.
- Added current-ERP remittance reconciliation so exact full-open, same-customer
  source rows may supersede a stale page-level completeness flag for one unique
  residual item.
- Kept ambiguity, amount/owner mismatch, source conflict/loss, review edits,
  partial applications, nonzero results, approval, export, posting, and ERP
  writes blocked.
- Added source-loader, allocation, coordinator, projection, shared-contract,
  and privacy-safe verifier coverage.
