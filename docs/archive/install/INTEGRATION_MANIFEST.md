# ETOP Current-Code Agents 1–4 Integration Manifest

## August 22, 2026 — R73 Payment Notes exact-R72 integration candidate

Protected baseline: `ETOP-R72-FULL-SOURCE-20260822T145120Z-9188fe44.zip`,
SHA-256
`b6c85a104d78a8fb72dac91e8adfec3cddd7a0539cac645f04fc87fb5e90181c`,
captured `2026-08-22T14:51:58.1314980Z`. The source capture manifest SHA-256
is `1279cb1de802ebd5f74a137b7d5cdbac2be0f158c21d2396a83519b389cae2e5`.

R73 adds an isolated Payment Notes workspace, authenticated default-deny API,
versioned route-reference intake, PNC remote-capture parsing and exact Virtual
Credit balancing, bounded read-only `KMTDTA.WHSIGPAY` and `WHSIGIMG` evidence,
deterministic leading-zero/check/amount matching, signature enrichment, local
run persistence, and append-only human-review evidence. Shared integration is
limited to the canonical backend router, shell, platform/search registries,
Workflow Foundation module registry/type/access policy, and their tests.

The exact-R72 `backend/main.py` launcher health/readiness behavior is protected.
The isolated R73 file is not an authorized replacement because it lacks R72's
readiness fields/probe and carries a UTF-8 BOM; the integration candidate adds
only the Payment Notes router import and registration to the exact R72 file.
The R72 Credit Application, Lockbox, Automation, security, and launcher paths
remain protected predecessor behavior.

Proposed governance artifacts `SRC-012`, `CAP-PN-001`, and `ADR-018` trace the
supplied SOP, bank sample, route lookup, `WHSIGPAY`, `WHSIGIMG`, matching,
signature, balancing, privacy, authority, and no-write boundaries. They are
**proposed integration-candidate records**, not Product Owner acceptance,
professional-role approval, operational activation, or promotion authority.

Unresolved gates remain: professional owner; route-version steward; reviewer
authority; permanent cross-run reuse policy for `WHSIGPAY.ID`; Corporate `00`; route
`89`; one-digit location aliases; invoice serialization; `RECEIVED` meaning;
source timezone and K&M holiday calendar; sensitive bank-source retention;
approval of the recorded independent bounded-query snapshot mode; authenticated
API/browser/controlled-ERP qualification; and exact-R72 retained regressions.

The hardened candidate records public ERP source/cap/time/completeness/hash
provenance plus private canonical bounded snapshots, redacts bank account and
routing values from persisted working evidence, initializes additive local
schema only on first feature use, exposes amount-candidate population
completeness and blocks acceptance when truncated, serializes route activation
with `BEGIN IMMEDIATE`, and fails closed when a `WHSIGPAY.ID` appears in prior
run evidence. Those controls are implemented and unit-tested but still require
the controlled exact-R72 Windows/API/browser/ERP qualification named above.

This candidate has evidence-and-recommendation effect only. It does not update
Payment Notes, signature images, receipt state, bank records, AR, customers,
invoices, cash application, posting, close, or any ERP source. Module access has
`authority_effect=none` and cannot be interpreted as Decision or financial
authority. R73 must not be marked operationally Ready or promoted until the
named gaps are resolved or explicitly accepted and the complete exact-R72
qualification passes.

## August 13, 2026 — Security & User Access implementation candidate

This isolated implementation candidate extends CAP-WORK-001 and ADR-011 with a
durable local Security & Access module. It uses the existing Workflow Foundation
account/session service; adds hashed, expiring, atomic single-use invitations
with pending-only revocation; versioned default-deny module profiles; account
suspension/reactivation; last-active-security-coordinator protection; append-
only access/invitation evidence; effective frontend permissions; and fail-closed
backend route enforcement. The registry covers every Ready module in the
current `src/App.tsx` plus Security & Access. All current FastAPI routes (174 in
the isolated verification snapshot) are intentionally mapped; future unknown
routes are denied.

The browser attaches credentials only to the configured ETOP backend origin.
Test instances may isolate the application link, cookie, HMAC session hash, and
namespace through `ETOP_APP_URL`, `ETOP_COOKIE_NAME`, `ETOP_COOKIE_DOMAIN`,
`ETOP_SESSION_SIGNING_SECRET`, and `ETOP_SESSION_NAMESPACE`. Module enablement
has authority effect `none` and does not approve, pay, post, apply cash, change
an order, write the ERP, or change accepted Lockbox behavior.

Focused verification passed: 15 pure Workflow Foundation tests, 5 HTTP/CORS/
cookie/enforcement tests, 4 frontend origin/registry tests, changed-file ESLint,
Python compilation, and production TypeScript/Vite build. Full repository
ESLint retains unrelated predecessor failures outside this increment. This is
an integration candidate, not a release acceptance or operational activation.

## Wave 4 Increment 4E-R6 — hard-link fixture identity correction

The exact R5 first full-verification result is a valid stage-local
`technical_candidate_pass`: zero failures, zero pending, unchanged 452-path
runtime/build identity, no activated operational authority, ordinary-file
acceptance, and true hard-link rejection. The sealed lifecycle then rejected
that proof because its consumer retained the R4 fixture hashes while the
candidate correctly emitted the R5 fixture hashes. It failed at
`first_full_verify`, and the outer runner stopped at
`run_disposable_windows_lifecycle`.

The independently inspected returned ZIP contains 92 safe unique files. Its
`partial_failure` global ledger lists 90 exact members, and all 22 internal
sidecars match. This proves the completed first round but not the remaining
rollback, reinstall, final, attestation, evidence-bound, complete-ledger, or
outer-validation stages. The workstation stage root and live fixture are
reported preserved but were not independently re-inspected.

R6 changes only revision-bound governance and release controls. The Windows-
proven R5 fixture-byte definition and derived SHA-256 pair must bind every R6 producer,
inner consumer, outer evidence consumer, and live-fixture consumer; seal-time
verification rejects any mixed revision. It changes no application runtime,
UI, API, schema, dependency, business rule, test, retained verifier, or
authority semantic. R1 through R5 remain immutable rejected evidence. G1
remains open and requires a new R6 Windows lifecycle, independent review, and
Josh Corbit's separate exact-hash acceptance.

## Historical Wave 4 Increment 4E-R5 — returned-timestamp consumer correction

The exact 4E-R4 inner lifecycle completed and produced independently verified
complete evidence. Its lifecycle result records `technical_candidate_pass`,
zero failures and zero pending; the attestation and all three full verification,
command-sandbox, Windows hard-link, 23-test backend, and retained-verifier
rounds passed. All 452 runtime/build paths remained exact, operational authority
was not activated, and G1 remained open.

The sealed R4 outer runner then stopped at `validate_returned_evidence` with
`Returned lifecycle-authorization timestamp is not canonical UTC evidence.`
The raw authorization value is canonical
`2026-08-12T16:05:58.1450429Z`. PowerShell 7.5+ default `ConvertFrom-Json`
date handling converted that JSON string to `DateTime`; the runner's later
`[string]` conversion lost the literal `Z`, so the offset check falsely
rejected the evidence. R4 remains a failed end-to-end lifecycle despite its
complete inner technical proof.

R5 changes only revision-bound governance and the outer returned-timestamp
consumer. It requires PowerShell Core 7.5 or later, parses returned JSON with
`ConvertFrom-Json -DateKind String`, requires `created_utc` to remain a string,
enforces exact ordinal `yyyy-MM-ddTHH:mm:ss.fffffffZ`, and uses invariant
`DateTimeOffset.TryParseExact` with UTC adjustment and a zero-offset check.
Seal-time and lifecycle probes accept the exact producer form and reject
alternate/missing zones, wrong fractional precision, lowercase `z`, an auto-
converted `DateTime`, and malformed input.

R5 changes no application runtime, UI, API, schema, dependency,
authentication, matching, allocation, export, ERP access, authority contract,
or business behavior. All 452 runtime/build paths retain the exact accepted
4D-R9 digest. At R5 sealing time, R1 through R4 were immutable rejected
evidence and a completely new R5 Windows lifecycle was required. That run later
failed at its fixture-consumer boundary and is classified in the R6 section
above.

## Historical Wave 4 Increment 4E-R4 — lifecycle stage-schema correction

The exact 4E-R3 Windows lifecycle is rejected partial-failure evidence. Its
returned ZIP and filename-bound sidecar were supplied and independently
verified. The archive opened without compressed-data errors, and all 184
members listed by its internal `partial_failure` ledger matched their recorded
SHA-256 and byte size. That proves internal evidence integrity; it does not
promote the failed lifecycle.

R3 completed installer validation, governed injected-failure restoration,
install, first full verification, rollback to exact R9, idempotent rollback,
reinstall, final full verification, and all three command-sandbox, Windows
hard-link, 23-test backend, and retained-verifier rounds. The evidence-bound
verifier nevertheless records `technical_candidate_fail` at
`attestation_and_evidence_bound_verify`, one failure, zero pending,
`lifecycle_attestation_validated: false`, unchanged runtime, no activated
operational authority, and G1 open.

The final binder iterated heterogeneous stage records and unconditionally read
`g1_status`. Ordinary lifecycle stage records carry `g1_status: open`;
verifier-result records instead carry `overall_gate_status: G1_OPEN` and
`g1_closed: false`. PowerShell strict mode therefore stopped the binding check.
There is no accepted lifecycle result or complete global evidence ledger.

R4 changed only revision-bound governance and release-control stage binding.
It used schema-aware assertions and added a seal-time property-contract
regression. It changed no application runtime, UI, API, schema, dependency,
authentication, matching, allocation, export, ERP access, authority contract,
or business behavior. All 452 runtime/build paths retain the exact accepted
4D-R9 digest. R1, R2, and R3 remain immutable rejected evidence. G1 remains
open; R4's later inner pass and outer failure are classified above.

## Historical Wave 4 Increment 4E-R3 — Windows sandbox-metadata correction

The exact 4E-R2 Windows lifecycle is rejected evidence. The governed failure
injection restored exact R9 and the actual R2 install passed, but both
command-sandbox `before` validators stopped at `first_full_verify`, before the
governed backend suite or retained Python verifier began. R2 reported
`technical_candidate_fail`, three failures, zero pending, unchanged runtime,
no activated operational authority, and G1 open.

The transcript reports two identical 173-byte before-validator logs with
SHA-256 `61193b730d08074945ee54f322780cf20955d4df41723a58658d2810fe14b8b5`.
The sealed R2 scanner calls `DirEntry.stat(follow_symlinks=False)` and rejects
`st_nlink != 1`. Windows returned the zero link-count field for the scan, and
the first casefold-sorted root file was `.gitignore`. Serializing
`Hard-linked file is forbidden: .gitignore` through the sealed R2 failure JSON
produces the same 173-byte hash. This diagnosis is derived from the supplied
transcript and sealed candidate; the partial returned-evidence ZIP was not
supplied or independently verified.

R3 changes only revision-bound governance and release-control sandbox metadata
proof. It retains link, reparse, hard-link, exact inventory, database isolation,
no-cleanup, and no-copy-back requirements. It changes no application runtime,
UI, API, schema, dependency, authentication, matching, allocation, export, ERP
access, authority contract, or business behavior. All 452 runtime/build paths
retain the exact accepted 4D-R9 digest. G1 remains open and requires a new R3
Windows lifecycle, independent review, and exact-hash Product Owner acceptance.

## Historical Wave 4 Increment 4E-R2 — verifier-isolation correction

The exact 4E-R1 Windows lifecycle is rejected evidence. Its first full
verification passed the governance, privacy, no-write, production-build,
inherited lint, 23-test backend, and retained functional checks, but the final
inventory gate detected an unexpected
`data/modules/document_intelligence/document_intelligence.db` file.

The retained current-review/invoice-search verifier imports through the
top-level Document Intelligence initializer, which initializes the default
relative SQLite database. The governed backend suite has a second inherited
import-time effect that initializes `backend/data/workbench.db`. R2 changes
neither command. It runs each in its own fresh exact command sandbox, records
and hash-binds the exact before/after inventory and expected empty or seeded
SQLite schema, and preserves both sandboxes. Neither database may enter the
source or installed verification project. No byproduct is ignored, allowlisted,
removed, or admitted into the candidate inventory, and the strict
post-command inventory gate remains unchanged.

R2 changed no application runtime, UI, API, schema, dependency, authentication,
matching, allocation, export, ERP access, or authority behavior. All 452
runtime/build paths retained the exact accepted 4D-R9 digest. Its lifecycle
later failed during the first before-command proof, so R2 remains rejected and
cannot close G1.

## Wave 4 Increment 4E — pilot authority and acceptance contract candidate

Protected predecessor: exact accepted 4D-R9, candidate SHA-256
`aee308478767d885fb4e14fbce74c4ab5e03453a679191168b53aa22e30eb025`,
998 package members, G0 closed through the external hash-bound acceptance
package. Historical R9 `G0_OPEN` evidence remains unchanged.

4E is governance-only. Josh Corbit is Business Sponsor, Product Owner,
Escalation Owner, Rule Steward, and final measurement-target authority. Bryan
Benner is Cash Application Professional Owner, Evidence Custodian, File
Control Owner, and Ground-Truth Adjudicator. MAT-LOCKBOX-AUTH-001 and
CON-LOCKBOX-PILOT-AUTH-001 define prospective role types, separation,
freshness, invalidation, retention, measures, escalation, and state semantics.

### 4E protected boundaries

- Individual authenticated assignments remain 4F work; named ownership does
  not activate transaction review, acceptance, export, reconciliation, close,
  reopen, or financial authority.
- Reviewer and Acceptance-for-Export Reviewer differ for every transaction;
  Export Custodian and Reconciler differ for every generation; no amount tier
  or owner-status bypass applies.
- Legacy `approved` is historical `review_accepted_for_export` evidence and
  requires 4F reaffirmation. Unbalanced items hold/escalate; `$0.01` is
  arithmetic equality only.
- Acceptance and later export-generation preflight each require their own
  successful current read-only ERP refresh; a material source/customer/
  allocation/review/rule/service/ERP-state change invalidates readiness.
- Governed evidence is preserved with no deletion until a later policy; legal
  hold overrides disposition; backup/restore implementation and proof remain
  4I work.
- Learning/rule/profile/model promotion is unavailable. Bryan proposes
  measurement targets and Josh approves them before 4J judgment.
- No runtime, UI, API, database, schema, authentication, dependency, build,
  matching, allocation, export, posting, ERP write, financial execution, or
  automatic-approval behavior changes.
- G1 remains open. Successful 4E acceptance can authorize only 4F development.

## 4D-R9 Windows verification-portability correction

Protected predecessor: exact AP5R2Final composite baseline used by the 4D
release envelope. R9 retains the complete R8 source while correcting the two
validation-boundary defects proved by the preserved rejected R8 Windows run.

The Automation runtime connection owner and saved-report lookup remain
byte-identical to R8. The test fixture that creates `workbench.db` now combines
the existing transaction context with an explicit close, eliminating the sole
retained fixture handle before Windows temporary-directory cleanup. The lint
verifier canonicalizes separators after replacing the disposable root and
executes ESLint over active `src` only, so the exact 10-error/0-warning finding
set has the same fingerprint on Windows and POSIX paths.

R9 changes no application runtime behavior, schedule, retry, execution,
SQL-validation, delivery, approval, ERP-access, or operator-authority rule. It
is authorized only for a fresh disposable Windows lifecycle drill. G0,
independent review, Product Owner acceptance, and production authorization
remain open; the rejected R8 package, clone, snapshots, and evidence are not
modified.

## 4D-R8 Windows SQLite connection-lifecycle correction

Protected predecessor: exact AP5R2Final composite baseline used by the 4D
release envelope. R8 retains every accepted 4D governance and privacy change
and corrects the Automation repository resource-lifecycle defect exposed by
the rejected R7 Windows technical verification.

All Automation repository connections now use one bounded owner that preserves
the existing SQLite transaction context and deterministically closes the
operating-system handle on success and failure. The saved-report SQL lookup
uses the same owner. The strict test fixture remains fail-closed and adds an
immediate `workbench.db` deletion regression after representative repository
operations. The verifier also removes the disposable project root from ESLint
message text before hashing, making the sealed ten-error/zero-warning baseline
portable across exact Windows clone paths.

This correction changes no schedule, retry, execution, SQL-validation,
delivery, approval, ERP-access, or operator-authority rule. Runtime databases,
outputs, credentials, and operational evidence remain excluded. R8 remains
limited to an authorized disposable Windows lifecycle drill; G0 and production
authorization remain open.

## Current governance overlay — ETOP 0.7.0 Wave 4 Increment 4D

Protected predecessor: the verified `AP5R2Final` composite source consisting of
971 packaged controlled files from the exact sanitized capture plus the
separately verified protected
`src/components/sqlstudio/SqlEditor.tsx`. The six omitted legacy folder-tree
inventories are retained by path/hash as historical non-runtime evidence and
are not active source or rollback prerequisites.

Increment 4D reconciles source and release governance only. It restores the
exact protected SQL editor, records canonical entrypoints and separate product/
component/schema/Blueprint versions, replaces the stale 0.6.9 release-baseline
reference with `AP5R2Final`, populates Product Roadmap and Release Strategy,
and reconciles Blueprint source/trace records through 4C/AP Increment 5 R2.

### 4D protected boundaries

- Every predecessor runtime TypeScript, JavaScript, Python, schema, and build-
  configuration file other than the exact restored protected editor remains
  byte-identical.
- No Lockbox OCR, customer matching, allocation, review, approval, export,
  posting, or ERP-write behavior changes.
- ERP remains read-only; automatic approval and financial execution remain
  prohibited.
- The current mutable review projection and replaceable reviewed-export
  evidence remain explicit 4F/4G gaps; 4D does not overstate them as immutable.
- The original `_ETOP_BASELINE_EVIDENCE` capture attestation and inventories
  remain unchanged.
- Lockbox feature scope is frozen except a Product Owner-approved, real-file
  pilot blocker with deterministic regression evidence.

### 4D gate state

G0 remains open. On August 10, 2026, the Product Owner authorized deterministic
fictional substitution across the 22-path privacy inventory. Increment 4D-R1
preserves fixture relationships and expected outcomes; 184 affected Python
tests, five retained JavaScript verifiers, the frontend build, and the targeted
flagged-value rescan pass. Privacy is therefore resolved. Windows lifecycle
execution, independent review, sealed evidence, and final Product Owner
acceptance remain open, so no 4D package is yet authoritative or install-
authorized.

## Runtime correction — AP Increment 5 R2 coordinate-aware invoice extraction

Protected predecessor: exact AP Increment 5 R1 final source across the
authoritative 130-path state. R2 is a new application correction, not another
R1 recovery wrapper. It accepts only exact R1 final for installation and exact
R2 final for idempotent verification; every partial, older, or unknown governed
state stops before mutation.

SRC-011 and ADR-016 v0.3 correct a layout defect exposed by Product Owner UAT.
The existing native extractor already preserved readable text and bounding
boxes, but the v1 parser assumed one emitted text object contained both field
label and value and used PDF object order for header inference. R2 adds stable
fragment identity/page geometry, field-specific coordinate pairing, bounded
remittance issuer inference, recipient/customer exclusions, totals-box
semantics, canonical corroboration, explicit ambiguity, and truthful text/
field-readiness status.

The pipeline records extraction v2, parser 2.0.0/rules v2, and processor v3.
Paired evidence retains both label and value fragments, bounding boxes, source
method, pairing method, actual source confidence, rule/authority, and every
corroborating observation. A blank recognized label may remain present without
value. Native geometry never produces invented numeric confidence, and inferred
issuer identity remains analytical evidence requiring review.

The R2 review surface also exposes compact value/page/location/source/confidence
evidence for every distinct ambiguous candidate. A reviewer may explicitly mark
one of the thirteen supported business fields unavailable for the exact current
processing run. That namespaced disposition remains in the existing append-only
review JSON contract without a schema migration, resets on a new run, and makes
the AP projection suppress corrected, machine, and source-text fallback values
through the existing missing-field exception path.

The proprietary UAT document and its identifiers are never included in source,
tests, verification, snapshots, or release payload. A fictional coordinate-
layout PDF is generated only inside the isolated test run.

### AP Increment 5 R2 protected boundaries and lifecycle

- Installation performs no backend import, database connection, upload scan,
  invoice read, OCR call, or automatic reprocess.
- Runtime `data`, `backend/data`, uploads, documents, exports, module-local
  Lockbox results/exports/cash-application output, `.etop-state`, SQLite files
  and sidecars, environment files, credentials, and user evidence are excluded
  from package mutation and fingerprinted for preservation.
- A professional explicitly appends a new processing run after install. The
  prior run remains immutable and retrievable; current review resets to pending
  for the new run, while prior review/corrections remain history.
- Source rollback requires an explicit validated R2 snapshot and returns only
  to exact AP Increment 5 R1 final, preserving the R1 SQLite lifecycle fix. It
  never discovers a latest snapshot or touches earlier recovery snapshots.
- Every extraction remains evidence only. No vendor-master change, PO/receipt/
  GL match, approval, payment, posting, export, external AI transfer, ERP write,
  straight-through threshold, or financial authority is introduced.
- The specialized PNC Lockbox path and all retained AP, spend, ERP Evidence,
  Financial Close, Workflow, and OpenAPI behavior remain unchanged.

## Runtime correction — AP Increment 5 R1 Windows SQLite lifecycle

Protected predecessor: exact AP Increment 5 source installed by the sealed
Step 6 I2 + AP5 sequential release. The original AP5 installed-source verifier
proved that payload and the retained Step 6 sentinels before its focused test
process exposed the Windows handle leak.

R1 preserves the accepted SRC-009 / ADR-016 behavior and changes only
connection ownership in the existing Document Intelligence review and
processing repositories. SQLite transaction contexts still commit or roll
back; an outer deterministic close now releases the operating-system handle on
both success and failure. A cross-platform tracking regression and immediate
database deletion prove the corrected boundary.

The correction introduces no new document type, OCR rule, parser threshold,
review authority, AP synchronization effect, vendor-spend interpretation,
Financial Close behavior, ERP access, or financial action. Runtime databases,
uploads, invoice originals, processing/review evidence, credentials, exports,
and ERP/GL state remain protected operational data and are not source payload.

## Sequential runtime overlay — Step 6 Increment 2 plus AP Increment 5

### Financial Close — Local Close Planning Templates

Protected baseline: exact accepted Step 6 Increment 1 Financial Close
Readiness Foundation payload; its source and payload hashes were independently
verified before this workstream. Increment 2 adds governed reusable local
user-authored planning drafts and an operator-driven path to instantiate one
exact immutable version using a supplied calendar anchor.

Template roots, versions, ordered items, authenticated actors, and events are
immutable/append-only and canonically hash-bound. Manual instantiation
atomically creates the accepted Increment 1 cycle/control records plus an
immutable snapshot of exact template/version/item hashes, identity snapshots,
calculated anchor-plus-offset dates, and generated record IDs. A later template
version cannot rewrite an existing cycle, control, evidence event, review, or
lineage. Direct Increment 1 cycle/control creation and the full retained
preparation/review journey remain available.

### Step 6 Increment 2 protected boundaries

- Every template is labeled `local_user_authored_planning_draft`; it is not an
  approved accounting policy, enterprise control library, audit program, or
  complete close checklist.
- Version creation and manual instantiation require an authenticated Workflow
  Coordinator. Default preparer and reviewer identities must be active and
  distinct; local identity supplies attribution only and no financial
  authority.
- Calendar anchors and calculated dates are planning metadata only, not an
  authoritative fiscal calendar, due date, SLA, or close deadline.
- Instantiation occurs only through an explicit operator command. There is no
  recurrence engine, scheduler, automatic cycle/task creation, escalation, or
  notification.
- ERP/GL sources remain unconnected. There is no ERP/GL read, inference, query,
  mutation, balance, reconciliation, journal, posting, or period-state effect.
- No close, approve, certify, attest, post, reopen, workflow-task, export,
  external communication, AI action, or new role/authority is introduced.

## Parallel AP overlay — Governed Vendor Spend Intelligence

Protected baseline: exact accepted Step 6 Increment 1 Financial Close Readiness
package, outer SHA-256
`DAF678ED665BE3CEFFC66AC74F55FBB477C8639B53CC556FE0566C74C7EF3EAE`.
This AP-local overlay adds deterministic total-spend, one-period
highest-vendor, and twelve-month highest-vendor questions over confirmed
`PMGLDS` posted GL-distribution evidence, with minimized `PMVEND` identity and
no dependency on imported OCR invoices.

### AP Vendor Spend protected boundaries

- The measure is `PMGAMTINV` signed as stored, disclosed as positive, negative,
  and net posted AP GL-distribution amount; it is not cash paid, open AP,
  approval, payment status, or vendor performance.
- Calendar month/year wording uses bounded `PMGDTEINV` ranges. Only explicit ERP
  accounting questions use raw `PMGYR`/`PMGPR`; fiscal interpretation remains
  unavailable without an approved fiscal calendar.
- `account 5050-3` parses as account 5050 and division 3 under the Product Owner
  question convention.
- Only fixed deterministic intents and slots reach parameter-bound,
  selected-column aggregate SQL. Question text and model-generated SQL never
  execute.
- Required runtime fields and the invoice-date storage type are verified before
  financial rows are read. Missing, ambiguous, unsupported, and degraded states
  return no fabricated zero. Native SQL dates are direct; a numeric
  `PMGDTEINV` requires the approved
  `ETOP_AP_PMGDTEINV_NUMERIC_ENCODING=YYYYMMDD|MMDDYYYY` setting because its
  runtime type alone cannot prove the encoding.
- Rankings return at most ten vendors and retain the same rank for equal
  displayed amounts. Ranking and leader-set completeness disclose when the cap
  can hide more rank-1 vendors; capped leader counts are lower bounds. Only
  sources actually queried are listed, alongside as-of time, coverage,
  warnings, and canonical SHA-256.
- A monthly-series question executes twelve fixed, parameterized, per-calendar-
  month rankings inside the same read-only consistent snapshot and returns
  January through December in order. Each month has a ten-vendor cap, explicit
  no-evidence state, and its own tie-completeness disclosure.
- Governed AP mapping readiness explicitly includes `PTDT` input-invoice detail
  alongside the existing `PMVEND`, `PMHD`, `PMDT`, `PMGLDS`, `PTHD`, and
  `PTPY` mappings; this does not authorize arbitrary AP-table browsing.
- No export, recommendation, Decision, approval, payment, posting,
  notification, vendor action, external transfer, or ERP write is introduced.

## Parallel AP overlay — Vendor Invoice Dataset & OCR

Protected baseline: exact accepted Step 6 Increment 1 source. SRC-009 and
ADR-016 make AP vendor-invoice intake usable through the existing PSS-007
Document Intelligence owner. The AP workspace now exposes the visible
`Vendor Invoice Dataset & OCR` journey: upload PDF, preserve exact source/hash,
run native extraction with targeted local Tesseract fallback, inspect versioned
field evidence, review/correct the exact current run, synchronize idempotently
into the existing AP projection, and reopen the evidence.

The extension adds the registered deterministic vendor-invoice parser,
page/field evidence, append-only successful/failed processing runs, a latest-
successful current-result compatibility projection, and processing-run-bound
review history with optimistic concurrency. A failed reprocess retains the last
successful current result. AP ignores corrections/review status from any prior
run. Every review caller supplies the expected current run, and the supported
single-process local runtime serializes processing/review compare-and-save.

### AP Vendor Invoice Capture/OCR protected boundaries

- Intake supports governed PDF content only, up to 50 MB. Empty, oversize,
  non-PDF, encrypted, corrupt, zero-page, unsupported, OCR-failed, missing-field,
  and ambiguous states remain explicit. Every retry attempt appends immutable
  success/failure evidence.
- Native text is first priority. Only pages marked insufficient invoke the
  configured local Tesseract path; no external AI/document service is called.
  Work is offloaded from the async loop and bounded at 500 PDF pages, 25 OCR
  pages, 30 seconds per OCR call, 120 seconds per document, 10,000 raster pixels
  per dimension, and 20,000,000 raster pixels per page.
- Numeric confidence is retained only when an actual source engine supplies it.
  Deterministic native rules and header inference receive no invented value.
- Every new successful extraction resets current review to pending while
  preserving prior review/corrections in history. Stale expected-run saves
  return conflict.
- Extraction review and AP sync do not approve, code, match, pay, post, create
  an ERP payable, establish ERP truth, or write to ERP.
- AP capture synchronizes only the exact selected reviewed job. Dataset
  total/limit/offset plus load-older navigation keeps older jobs reachable.
- Document routes remain a localhost-only proof-of-concept boundary. Managed
  reads are contained under the upload root, public responses omit internal
  stored paths, and authenticated document-access policy remains deferred.
- PNC Lockbox's specialized processing/review/preparation/export path is
  unchanged and its retained regression suite passes.
- Runtime databases, uploads, OCR output, and test artifacts remain excluded
  from the source/release payload.

## Current runtime overlay — Step 6 Increment 1 Financial Close Readiness Foundation

Protected baseline: exact installed Step 5 R1 AP Direct ERP Lookup Correction,
package SHA-256
`2233D3E1580B29CF3B7B96DC9BE7D1AEC095F6A1BF5AC01331AFAD380B8A0529`.
Increment 1 adds a dedicated local Financial Close workspace for immutable
close cycles, control items, verified preparer/reviewer identity, append-only
preparation evidence, professional review dispositions, and derived readiness.

The module reuses authenticated identities from the Workflow Foundation but
keeps close-specific evidence semantics in a capability-owned record. It does
not create financial roles or silently grant existing accounts new authority.

### Step 6 Increment 1 protected boundaries

- Cycle dates, due dates, control priority, and evidence requirements are
  operator supplied; they are not an approved close calendar, SLA, policy, or
  materiality threshold.
- Preparer and reviewer must be different active local users. Authentication
  establishes attribution and segregation only, never close authority.
- `evidence_sufficient_for_close_review` is a snapshot-bound professional
  disposition about the local manifest, not approval, certification, account
  reconciliation, ERP period status, or books closed.
- ERP period state, balances, reconciliations, journals, accruals, allocations,
  intercompany, consolidation, flux analysis, and delegated close/reopen
  authority remain explicit unavailable inputs or deferred capabilities.
- No close, reopen, approval, posting, notification, export, external transfer,
  automation, AI action, or ERP write is introduced.

## Current runtime overlay — Step 5 AP Direct ERP Lookup Correction

Protected baseline: exact installed Step 5 Read-Only ERP Evidence Gateway,
package SHA-256
`A15E31BE3F0257414726A32DD8E78914E9274E405776BFF59DCFF44DB41626EB`.
The correction removes the runtime dependency on an imported OCR invoice by
adding bounded PMVEND vendor discovery, exact PMHD invoice discovery, explicit
human candidate selection, and direct exact vendor/invoice evidence retrieval.
The existing imported-invoice path remains available.

### Correction protected boundaries

- Vendor number and invoice number use exact equality; vendor name returns at
  most 25 candidates and is never auto-selected.
- Invoice discovery returns at most 50 distinct vendor/invoice identities.
- All values are parameter bound; result projections exclude every sensitive
  vendor field already protected by Step 5.
- Missing PTHD/PTDT/PTPY mappings remain visible partial/degraded coverage and
  do not suppress confirmed PMVEND/PMHD/PMDT/PMGLDS evidence.
- No local invoice is fabricated, no OCR evidence is rewritten, and no match,
  approval, payment, posting, export, notification, or ERP write is introduced.

## Current runtime overlay — ETOP 0.7.0 Step 5 Read-Only ERP Evidence Gateway

Protected baseline: exact Platform Foundation Increment 1 source. Step 5 adds a
shared read-only ERP Evidence Gateway and functional Credit/AP evidence views.
Credit reuses `TMCUST`, `TMAROP`, and `TMCUST.CUNUMENT`. AP uses the Product
Owner-supplied DTA273 mapping for `PMVEND`, `PMHD`, `PMDT`, `PMGLDS`, `PTHD`,
`PTDT`, and `PTPY` through exact local invoice identity.

### Step 5 protected boundaries

- Queries are parameterized, selected-column, deterministic, and row capped.
- AP requires numeric vendor number plus invoice number; no broad fallback
  search is performed.
- Undocumented AP codes remain raw. Posted/input/check fields are not promoted
  to open, approved, payable, paid, matched, or executed states.
- Vendor bank account, routing, tax-ID, contact, phone, email, and address fields
  are never selected by the gateway.
- Every packet exposes source time, coverage, completeness, row limit,
  governance, and canonical SHA-256 evidence integrity.
- No recommendation, Decision, approval, payment, posting, order action,
  notification, export, external transfer, or ERP write is introduced.

## Current runtime overlay — ETOP 0.7.0 Platform Foundation Increment 1

Protected baseline: accepted Credit Risk Increment 5 / Accounts Payable
Increment 4 baseline `ETOP-0.7.0-CR5-AP4-Accepted-20260807-111034-216`.
Increment 1 adds local credential identity, operational roles, role queues,
verified assignment, versioned shared tasks, durable in-app notifications, and
a bounded hash-chained audit trace under ADR-011.

Credit Order Decision Preparation may link work to an exact Customer context;
AP Exception Operations may link work to an exact invoice evidence identity.
Existing operator-supplied names and module evidence are never migrated or
rewritten.

### Platform Foundation Increment 1 protected boundaries

- Assignment effect is `work_ownership_only`; authority and execution effects
  are `none`.
- Operational roles do not grant financial Decision or approval authority.
- Task completion changes only workflow state, not the linked business object.
- Due dates are operator supplied, not approved SLA or escalation policy.
- No external notification, approval, payment, posting, order action, cash
  application, export, source correction, or ERP write is introduced.
- The accepted Credit/AP, Lockbox, Document Intelligence, Reporting,
  Automation, Customer 360, SQL, and local operational state remain protected.

## Current runtime overlay — ETOP 0.7.0 Accounts Payable Increment 4

Protected baseline: exact Credit Risk Increment 5 lineage. Increment 4 adds an
Exception Operations Center over the current immutable AP invoice projection,
saved exception/OCR-review evidence, and deterministic duplicate candidates.

The queue exposes every reason and orders current work by source-change/follow-
up state, saved severity, source time, and invoice identity without a hidden
score. Append-only professional actions retain operator-supplied owner/recorder,
notes, optional follow-up, the exact source revision, and a canonical snapshot
hash. A later source revision preserves history and reopens visible review.

### Accounts Payable Increment 4 protected boundaries

- Work metadata does not clear or correct source evidence.
- Operator-supplied owners are not authenticated assignments or authority.
- No approved SLA, escalation, notification, or automatic resolution exists.
- No invoice approval, payment authorization, vendor action, posting, export,
  external transfer, or ERP write is introduced.
- Credit Risk Increments 1–5, AP Increments 1–3, Document Intelligence,
  Lockbox, Reporting, Automation, and every existing authority boundary remain.

## Current runtime overlay — ETOP 0.7.0 Credit Risk Increment 5

Protected baseline: exact Accounts Payable Increment 3 lineage. Increment 5
adds Order Decision Preparation over the existing Credit-Line Intelligence,
manual assessment, proposal, and portfolio-review contracts.

A professional enters a contemplated amount and optional reference. ETOP
recomputes projected partial exposure, partial availability, partial over-line,
and utilization from current read-only Customer 360 evidence. ERP order
identity, full exposure, approved order policy, authentication, and delegated
Decision authority remain explicit gaps. Append-only professional
recommendations preserve exact evidence and canonical hashes.

### Credit Risk Increment 5 protected boundaries

- Entered scenarios are not verified ERP orders or execution instructions.
- Projected partial exposure is not complete true exposure or approved policy.
- A recommendation is not an authorized Decision and has no order effect.
- No hold/release, approval, line/terms/order change, notification, posting,
  export, external transfer, or ERP write is introduced.
- Credit Risk Increments 1–4, AP Increments 1–3, Lockbox, Reporting,
  Automation, Customer 360, and all existing authority boundaries remain.

## Current runtime overlay — ETOP 0.7.0 Accounts Payable Increment 3

Protected baseline: exact Credit Risk Increment 4 lineage. Increment 3 adds
Vendor Intelligence and Cash Planning over the immutable local AP invoice
projection without claiming ERP vendor, payable, payment, or treasury authority.

Vendor evidence groups by saved vendor number, then normalized saved name, and
surfaces volume, known totals, due-date coverage, document review, exception,
duplicate, and OCR patterns. Due windows use saved invoice dates relative to an
operator-selected as-of date. Append-only cash evidence scenarios retain exact
assumptions, included invoice/source hashes, and canonical evidence integrity.

### Accounts Payable Increment 3 protected boundaries

- Vendor aggregates are document evidence, not reconciled vendor-master entities
  or performance scores.
- Cash windows/scenarios do not prove a current unpaid liability and may include
  paid, voided, disputed, credited, or otherwise closed source invoices.
- Scenarios are analytical evidence, not cash forecasts, payment proposals,
  payment batches, approvals, authorizations, releases, or instructions.
- No vendor action, payment, posting, export, external transfer, notification,
  AI action, or ERP write is introduced.
- Credit Risk Increments 1–4, AP Increments 1–2, Document Intelligence,
  Lockbox, Reporting, Automation, and every existing authority boundary remain.

## Current runtime overlay — ETOP 0.7.0 Credit Risk Increment 4

Protected baseline: exact Accounts Payable Increment 2 lineage. Increment 4
adds assessed-customer Portfolio Monitoring over the existing immutable Credit
Risk assessment, Priority & Alerts, and credit-line proposal contracts.

The portfolio inherits the existing stable work order, labels the Product Owner
draft high-risk bands as a working watchlist only, and aggregates partial
exposure only for assessed customers with available current evidence. A
professional may append a source-bound review disposition with optional follow-
up date; database guards and canonical hashes preserve its history.

### Credit Risk Increment 4 protected boundaries

- Unassessed ERP customers are not scored or represented as reviewed.
- Partial assessed-customer concentration is not full, related-account,
  regional, industry, or enterprise exposure.
- Review dispositions are operator-supplied workflow metadata, not Decisions,
  assignments, approvals, alerts, notifications, or credit actions.
- No line/terms/order/hold/release, posting, export, or ERP write is introduced.
- Credit Risk Increments 1–3, AP Increments 1–2, Lockbox, Reporting,
  Automation, Customer 360, and every existing authority boundary are retained.

## Current runtime overlay — ETOP 0.7.0 Accounts Payable Increment 2

Protected baseline: exact Credit Risk Increment 3 lineage. Accounts Payable
Increment 2 adds approval-review and payment-preparation control readiness over
the immutable AP Increment 1 invoice object.

Each local case binds to one source evidence revision and stores requester,
assigned reviewer, optional payment preparer, intended action, notes, exact
evidence snapshot, and canonical hash. Document-field, exception, duplicate,
evidence-currency, and operator-supplied segregation checks are deterministic.
ERP vendor/AP facts, authenticated authority, approval tiers, payment rails,
dual authorization, and posting remain unavailable gates.

The assigned reviewer may append evidence-ready, needs-information, duplicate-
review-required, or not-ready metadata. Evidence-ready is blocked by available
document/segregation failures. Changed source evidence makes an earlier ready
case display not ready without changing its immutable history.

### Accounts Payable Increment 2 protected boundaries

- Operator-supplied names are not authenticated identity, role, delegation, or
  authority evidence.
- Evidence ready is not invoice approval; payment preparation is not payment
  authorization.
- No approval, payment, release, posting, export, notification, vendor action,
  AI action, external transfer, or ERP write is introduced.
- Credit Risk Increments 1–3, AP Increment 1, Document Intelligence, Lockbox,
  Reporting, Automation, and all existing authority boundaries remain unchanged.

## Current runtime overlay — ETOP 0.7.0 Credit Risk Increment 3

Protected baseline: exact joined Credit Risk Increment 2 plus Accounts Payable
Increment 1 lineage. Increment 3 adds customer-level Credit-Line Intelligence
without changing the existing risk assessment or priority contracts.

The service reuses one shared read-only Customer 360 response for sales,
current line, partial exposure, available credit, high balance, monthly high
balance, and average daily balance. It recomputes the existing
`round_to_nearest_500((annualized_sales / 12) * 2)` reference and withholds a
conflicting shared value as invalid. That output is an unapproved analytical
inference, not a system recommendation or policy.

A professional may append a proposed line, review date, operator-supplied
identity, and rationale. ETOP captures the exact live evidence, explicit gaps,
source time, and canonical SHA-256. Database guards prohibit update/delete and
every read verifies integrity. History remains readable during ERP degradation.

### Credit Risk Increment 3 protected boundaries

- Full exposure, seasonality, parent/related accounts, approved line policy,
  authentication, delegation, approval tiers, workflow, and ERP mutation remain
  unavailable.
- A saved proposal is a professional Recommendation, not a Decision or approval;
  it has no notification, line/terms/hold, order, posting, or ERP-write effect.
- Credit Risk Increments 1–2, Customer 360, legacy Priority Review, AP,
  Lockbox, Reporting, Automation, and their authority boundaries remain unchanged.

## Current runtime overlay — ETOP 0.7.0 Accounts Payable Increment 1

Protected baseline: exact verified Credit Risk Increment 2 lineage. Accounts
Payable Increment 1 establishes a dedicated, local invoice-intelligence
workspace over existing saved Document Intelligence evidence without creating
a second document-processing pipeline or a posted ERP payable.

`POST /api/v1/accounts-payable/sync` imports completed `vendor_invoice` jobs
idempotently. Source priority is Document Intelligence review corrections,
structured parsed/header evidence, then versioned candidates derived from the
already-saved extraction text. The AP module never opens the PDF or runs OCR.
Source-text candidates remain analytical inference and require review.

The local projection retains stable source identity, canonical evidence
SHA-256, immutable revisions, immutable timeline events, field authority,
warnings, deterministic exceptions, and conservative duplicate-candidate
evidence. Identical sync is a database no-op. Changed source evidence appends a
revision. Duplicate v1 requires the exact normalized vendor identity and
invoice number; available amount/date conflicts exclude the pair.

The dedicated frontend provides AP health/source readiness, invoice search and
pagination, OCR Review, Exception Review, Duplicate Detection, source-grounded
detail, and sync/refresh. Every metric declares availability, population,
source, and explanation. Document/extraction review—even a source status named
`approved`—is not AP invoice approval or payment authorization.

### Accounts Payable Increment 1 protected boundaries

- Document Intelligence remains authoritative for originals, processing runs,
  extraction results, and document review evidence.
- ERP remains authoritative for vendor master, AP open items, PO, receipts,
  GL, payments, checks/ACH, organizational dimensions, and budgets.
- Current AP balance, due/past-due cash, discounts, payment status, approval
  SLA, PO/receiving match, vendor intelligence, GL coding, payment execution,
  AI, and portal behavior remain unavailable until governed sources and
  authority are connected.
- The provisional 90% OCR-review threshold inherits the existing document
  review UI behavior and grants no straight-through or approval authority.
- No approval, rejection, coding acceptance, route, payment, export, posting,
  notification, vendor communication, AI action, external transfer, or ERP
  write is introduced.
- Existing Credit Risk, Customer 360, Priority Review, Lockbox, Reporting,
  Automation, SQL, and Document Intelligence behavior remains unchanged.

### Accounts Payable Increment 1 deferred work

- Governed ERP source mappings and reconciliation for vendor, payable, PO,
  receiving, price/tax/freight, GL, terms, discounts, payments, organization,
  and budget facts.
- Authentication, approval authority, segregation of duties, workflow/SLA,
  corrections/dispositions, retention, backup, multi-user concurrency, and the
  shared PSS-008 Audit and Provenance Service.
- Three-way matching, touchless coding/routing, cash simulation, payment
  execution, vendor health/portal, mobile approval, AI insight, enterprise
  knowledge, and outcome evaluation.

## Current runtime overlay — ETOP 0.7.0 Credit Risk Increment 2

Protected baseline: exact verified Credit Risk Increment 1 lineage. Increment 2
adds assessed-customer Priority and Alerts without changing manual assessment
records, the legacy 0–100 Priority Review, or Customer Health.

The portfolio begins only with customers that have saved append-only manual
Credit Risk assessments and explicitly excludes unassessed customers. It
compares the latest two immutable assessments for deterioration, evaluates the
latest next-review date, and attempts each customer's current partial over-line
evidence independently through the shared read-only Customer 360 boundary.
Live-source failure degrades only that customer and never converts unavailable
exposure to zero or false evidence.

The default UI filter isolates ratings 7–10 only because their exact saved
Product Owner draft band snapshots say High risk, Very high risk, Default
likely, or Default/legal. This is `draft_band_attention`, not promoted policy.
The full assessed portfolio remains available.

Operational ordering is stable and explainable: overdue review, due today,
scheduled review; higher latest manual rating; deterioration; observed current
partial over-line; earlier next-review date; customer number. It is work
ordering, not a numeric score, Recommendation, Decision, approval, or action.

### Credit Risk Increment 2 protected boundaries

- Broken-promise and NSF alert types are explicitly unavailable and emit no
  alert until governed sources are connected.
- No score/weights, automatic risk policy, recommendation, approval,
  notification, hold/release, credit-line/terms change, order decision, AI,
  export, posting, or ERP write is introduced.
- Alert lifecycle, assignment, acknowledgment, escalation, authentication,
  roles, business timezone, full exposure, related accounts, and source-backed
  promise/NSF signals remain deferred.
- Existing Credit Risk foundation, Customer 360, Priority Review, Lockbox,
  Reporting, Automation, SQL, and Document Intelligence behavior remains
  unchanged.

## Current runtime overlay — ETOP 0.7.0 Credit Risk Increment 1

Protected baseline: exact verified Increment 4C plus Increment 4D-001. Credit
Risk Increment 1 adds a dedicated source-grounded evidence and manual
assessment workspace without changing either legacy 0–100 Priority Review or
Customer Health score.

The capability reuses shared Customer 360 as its only read-only MaddenCo fact
boundary. It recomputes signed aging without consuming Customer 360's legacy
`total_aging` convenience field, preserves raw `CUONORDER + CUONORDAR`, and
labels the available operational exposure as `partial`. The full target
formula remains visible while unbilled shipments, releasable orders,
unapplied cash, valid credits, and secured amounts remain unavailable rather
than numeric zero.

Product Owner-supplied draft 1–10 bands label manual professional judgment.
Each save captures the server-current customer, exposure, signed aging,
payment, and taxonomy evidence; stores its canonical SHA-256; and creates a
new append-only local record. SQLite triggers prohibit update and delete.
Stored history remains readable if the ERP is unavailable, but a new
assessment requires current matching Customer 360 evidence.

### Credit Risk Increment 1 protected boundaries

- No automatic score, priority queue, alert, trend inference, recommendation,
  credit-line/terms change, hold/release, order decision, approval, AI action,
  export, posting, or ERP write is introduced.
- Analyst identity is operator supplied and organizational authority is not
  independently verified; a saved assessment has no approval/action effect.
- Existing Customer 360, Priority Review, Lockbox, Reporting, Automation, SQL,
  and Document Intelligence behavior remains unchanged.
- Operational databases, customer records, documents, exports, credentials,
  logs, caches, and generated build output are excluded from the release.

### Credit Risk Increment 1 deferred work

- Governed sources for the five missing full-exposure components and complete
  payment history.
- Authentication, roles, delegation, retention, backup, multi-user conflict
  handling, and the shared PSS-008 Audit and Provenance Service.
- Portfolio monitoring, alerts, scenarios, credit-line recommendation, order
  decisions, approvals, AI explanations, external data, and predictive risk.

## Current runtime overlay — ETOP 0.7.0 Wave 2 Increment 4C

Protected baseline: exact verified Increment 4B lineage. Increment 4C repairs
the available Reporting workflow and hardens Automation Service without
changing accounting policy, Lockbox decisions, approval authority, posting,
or ERP writes.

Report Builder now persists report definitions through `/api/v1/reports`,
executes previews through the existing read-only `/sql/execute` contract,
downloads controlled CSV output through `/sql/export`, and creates recurring
non-parameterized saved-report schedules through `/api/v1/automations`.
Parameter names, defaults, select options, dates, booleans, numbers, and SQL
placeholder coverage fail explicitly before execution. Quoted/commented
placeholder text is ignored, transient text/select values are encoded as
MySQL UTF-8 expressions, and stale preview results are cleared when SQL or
parameter values change. In-flight previews are abortable and generation-
owned, so an older response cannot repopulate a result after the report or
parameter context changes.

Direct Report Builder XLSX and parameterized schedules are explicitly marked
unavailable because the current backend does not provide those contracts.
Direct CSV remains bounded by the SQL service's configured maximum. Scheduled
CSV/XLSX output continues through Automation Service; delivery configuration
remains owned by Automation Center.

Automation Service now validates active and manually executed definitions,
normalizes supported timezone aliases, maps the browser's Sunday-first weekday
values correctly, compares due times as UTC instants, and requires current
saved-report/script evidence. A durable SQLite running row prevents a second
process from claiming the same automation. Interrupted or failed runs enter an
explicit error state and are not replayed automatically. Invalid legacy active
definitions are quarantined, unsafe mutation during a run returns conflict,
and the health endpoint exposes scheduler/recovery/definition state without
credentials.

The root ESLint configuration now owns only the active frontend project and
excludes archived duplicate/package trees. This removes the 177 duplicate-tree
parser failures while retaining the exact known active-source debt for later
repair. The duplicate trees are not deleted in this increment.

### 4C integration ownership

| Workstream | Integrated result |
| --- | --- |
| Architecture/governance | Exact 4B baseline, module-status audit, source/privacy boundary, release trace and one controlled overlay. |
| Backend/platform | Governed Automation validation, scheduling, durable claims, recovery, quarantine, health, and focused tests. |
| Workflow/UX | Real Report Builder catalog-to-schedule workflow and authoritative Automation activation feedback. |
| Independent verification | Protected Lockbox gate, module audit, focused feature gates, production build, lint comparison, and package/privacy review. |

### 4C protected boundaries

- Lockbox retains the Increment 4B 8/9-digit invoice, invoice-versus-PO,
  current-open customer, distinct service-charge, explicit approval, and
  no-ERP-write contracts.
- Reporting executes only through existing read-only SQL validation and row
  limits. This increment adds no report-specific ERP-write route.
- Automation recovery is fail-closed. ETOP cannot prove that arbitrary scripts
  or delivery adapters are idempotent, so replay/reactivation remains an
  operator decision.
- Operational source documents, Lockbox results/versioned extractions,
  databases, exports, credentials, and runtime caches are excluded from the
  release package.

### 4C deferred governance and engineering gaps

- A complete pinned Python application/test dependency manifest remains
  unresolved; Increment 4C adds only the Windows timezone-data dependency
  required by the new scheduler validation.
- Automation owner/authority, immutable definition-version evidence, adapter
  allowlists, credentials, cancellation/retry, retention/archive, and
  compensating-action contracts require Product Owner/governance decisions.
- PowerShell/Python execution and email/folder delivery are technically present
  but remain governance-blocked unless the Product Owner explicitly delegates
  the owner, scope, adapter, credentials, and permitted actions.
- Priority Review's current thresholds, weights, labels, and tie ordering remain
  technically functional but are not promoted as approved accounting/credit
  policy by this increment.
- Duplicate `backend/src`, `backend/backend`, stale manifest/payload trees, the
  existing 14 active-source lint errors, and the oversized frontend bundle are
  recorded debt; no broad deletion or rewrite is included.

## Current runtime overlay — ETOP 0.7.0 Wave 2 Increment 4B

Protected baseline: exact verified Increment 4A lineage. Increment 4B is a
schema-compatibility correction to the shared Customer 360 search introduced
in 4A.

The production MaddenCo `TMCUST` table has no `CUCITY` column. Customer search
therefore queries the established `CUADDRESS1` through `CUADDRESS4`,
`CUSTATE`, and `CUZIP` fields and returns the address lines for the review
workspace's existing locality parser. Exact currently open 8/9-digit invoice
lookup remains read-only and still returns candidates without selecting one.

This overlay changes no lockbox source, preparation generation, customer
authority, allocation, approval, export, posting, or ERP-write behavior.

## Current runtime overlay — ETOP 0.7.0 Wave 2 Increment 4A

Protected baseline: exact verified Increment 3Z lineage. Increment 4A corrects
the service-charge review evidence handoff and extends customer lookup without
changing allocation or approval authority.

When a reviewer selects or corrects the customer after automatic preparation,
service-charge validation refreshes that selected customer's complete current
ERP Open A/R through the existing read-only provider. Each reviewed `SC` row
must still match a different exact current customer/type/reference/count
`open_item_key`. Closed, missing, duplicated, ambiguous, cross-customer, or
unavailable evidence remains blocked; an older preparation snapshot no longer
vetoes a customer that was resolved during professional review.

The shared Customer 360 search also accepts an exact normalized 8- or 9-digit
invoice number and returns the owning customer candidate only when that invoice
is currently open in ERP. The reviewer still selects the customer. Closed or
invalid invoices do not create candidates, and the lookup creates no customer,
allocation, approval, export, posting, or ERP write.

## Current runtime overlay — ETOP 0.7.0 Wave 2 Increment 3Z

Protected baseline: exact verified Increment 3Y lineage. Increment 3Z corrects
only reviewed service-charge identity validation.

One customer may have several monthly ERP `SC` open items and may pay several
in one check. A reviewer-added short service-charge row is therefore accepted
when its customer/type/reference/count `open_item_key` matches one distinct
`SC` row in that transaction's selected-customer Open-A/R snapshot saved by
the current governed preparation. The validator evaluates the complete saved
Open-A/R set rather than only the smaller automatic recommendation.

The same prepared service charge cannot be used twice. A forged, typed,
duplicated, ambiguous, missing, or later-created short identifier remains
blocked. This correction does not select service charges automatically, alter
the prepared/review counts, approve another transaction, export, post, or
write to ERP.

## Current runtime overlay — ETOP 0.7.0 Wave 2 Increment 3Y

Protected baseline: exact verified Increment 3X lineage. The active
61-transaction source remains protected at the accepted Increment 3W floor of
23 Prepared & Balanced, 38 Needs Review, and zero approved until Increment 3X
is independently verified. Increment 3Y does not reprocess that source or
change its governed customer, allocation, projection, approval, or export
state.

Increment 3Y corrects three operating surfaces:

- PNC transaction headers retain the same `Transaction Information`, `G-`
  identifier, date, and page-boundary contract while admitting the bank's
  three-letter processing-site code instead of requiring `PGH`; Dallas and
  Pittsburgh files therefore enter the same OCR and preparation path without
  deriving authority from the filename suffix;
- after an explicit transaction approval saves successfully, the workspace
  opens the next remaining professional-review transaction in source order,
  wraps to an earlier remaining item when necessary, and closes only when no
  review item remains; no later transaction is approved implicitly; and
- the long batch-level parser-warning stack is no longer rendered above the
  exception queue because each unresolved transaction is reviewed directly.
  The warnings remain stored in parser output and audit evidence.

The new PNC site-header contract is versioned separately so existing saved
Pittsburgh extraction caches are not invalidated or rerun. Invoice admission
remains exactly 8/9 digits, ERP access remains read-only, and no automatic
approval, export, posting, or ERP write is introduced.

## Current runtime overlay — ETOP 0.7.0 Wave 2 Increment 3X

Protected baseline: exact verified Increment 3W lineage and the active
61-transaction projection at 23 Prepared & Balanced, 38 Needs Review, and zero
approved.

The Product Owner confirmed that Increment 3W's unique remaining `$84.00`
open-A/R case passed. The remaining five-row remit failure was not a residual
or 10-digit-invoice problem. Each source row contained both an ordinary K&M
invoice number and the payer's unrelated 8-digit purchase-order number, so the
parser preserved the row as ambiguous instead of selecting either value.

Increment 3X corrects that evidence handoff:

- the governed invoice contract returns to 8- and 9-digit invoices; 7- and
  10-digit values, including `9999999999`, remain source evidence only;
- after one customer is resolved and its complete current open A/R is loaded,
  an ambiguous invoice-versus-PO row may supply one remit invoice only when
  exactly one candidate identifies exactly one ordinary same-customer open
  item and its full signed open amount equals the preserved row payment amount
  exactly to the cent;
- every raw candidate, parser rejection, page, source mode, and OCR attempt is
  retained; the PO is never rewritten as an invoice or deleted;
- all preserved rejected rows must resolve under the same strict rule before
  any recovered set is used; amount mismatch, two ERP-valid candidates,
  duplicate open items, other-customer evidence, service charges, and other
  rejection reasons remain professional review; and
- projection independently validates the complete versioned disambiguation
  envelope before a balanced recommendation may appear.

Increment 3X creates a new append-only preparation generation from saved
source evidence. It does not rerun OCR, overwrite a review draft or human
disposition, approve, export, post, or write to ERP. The 23/38/0 Increment 3W
result is the protected floor.

## Current runtime overlay — ETOP 0.7.0 Wave 2 Increment 3W

Protected baseline: exact verified Increment 3V lineage and the active
61-transaction projection at 22 Prepared & Balanced, 39 Needs Review, and zero
approved.

Increment 3W corrects two source-to-allocation handoffs:

- the shared ERP invoice contract admits 8-, 9-, and 10-digit invoices while
  continuing to exclude the `9999999999` no-remit placeholder;
- a prior rejected source row is re-admitted without OCR only when exactly one
  preserved non-placeholder 10-digit value and its original nonzero amount are
  unambiguous; original rejections and provenance remain intact;
- a stale page-level completeness flag may be superseded for unique-residual
  completion only when every admitted source row exactly reconciles once to
  its full signed current open amount under the same selected ERP customer;
- projection independently verifies equal row sets, source amounts, current
  ownership, boundary closure, zero conflicts/row loss/review edits, exact
  arithmetic, no approval, and no ERP write; and
- ambiguous values, placeholders, duplicate owners/items, amount mismatch,
  cross-customer evidence, partial application, or nonzero results remain
  professional review.

Increment 3W creates a new append-only rule/service generation from saved
source evidence. It does not require a PDF upload or OCR rerun and does not
mutate Increment 3V evidence, human review, approval, export, posting, or ERP
records. The 22/39/0 Increment 3V result remains the protected floor; only
independently qualifying transactions may improve the next projection.

## Current runtime overlay — ETOP 0.7.0 Wave 2 Increment 3V

Protected baseline: exact verified Increment 3U lineage and the active
61-transaction fresh-source projection at 21 Prepared & Balanced, 40 Needs
Review, and zero approved.

Increment 3V completes a remittance-backed residual from current open A/R:

- every admitted remittance invoice must be present exactly once in the
  verified customer's complete current open-A/R set;
- remittance evidence and the next-transaction boundary must be complete;
- after applying the full signed ERP open amount of every remit invoice,
  exactly one remaining ordinary invoice or signed credit under that same
  customer may be added when its full open amount exactly equals the residual;
- a unique residual item may be selected even when another older open item is
  present, because the exact residual amount is the deterministic evidence;
- zero or multiple exact residual items, cross-customer rows, partial
  applications, service-charge reinterpretation, source conflict, or a
  nonzero result remain professional review; and
- the recommendation remains unapproved and performs no ERP write.

Increment 3V creates a new append-only rule/service preparation generation;
it does not rerun OCR or mutate the Increment 3U generation. Existing
complete-balance, aging, due-date, oldest-prefix, and unique-service-charge
paths remain unchanged. The 21/40/0 Increment 3U result is the protected floor;
only independently qualifying residual cases may improve the next projection.

## Current runtime overlay — ETOP 0.7.0 Wave 2 Increment 3U

Protected baseline: exact verified Increment 3T lineage and the active
61-transaction fresh-source projection at 17 Prepared & Balanced, 44 Needs
Review, and zero approved.

Increment 3U corrects customer-evidence precedence during projection:

- `unique_current_open_invoice_owner` is deterministic only when the saved
  resolution and conflict assessment both report `resolved`, select the same
  customer, and use the governed current-open assessment rule;
- every admitted remittance invoice must be present in the saved assessment,
  have exactly one current ERP owner equal to the selected customer, and
  reconcile to the recorded valid-invoice count;
- missing/unavailable lists must be empty and every direct invoice-owner read,
  or its complete current-open-A/R source, must retain source and as-of time;
- only after that proof may stale broad-owner incompleteness, duplicate contact,
  supporting-evidence, and rank-lead flags remain non-decisional; and
- every original broad-owner and contact assertion remains preserved.

Any incomplete, unavailable, mismatched, split, duplicate, payer-directive,
source-conflict, allocation, source-row, boundary, approval, or ERP-write
condition remains review. Increment 3U changes no OCR/parser, customer query,
allocation generation, durable preparation row/event, review draft, approval,
export, posting, or ERP-write behavior. The 17/44/0 active result is the
protected floor; the diagnosed complete candidates may reproject to 21/40/0.

## Current runtime overlay — ETOP 0.7.0 Wave 2 Increment 3T

Protected baseline: exact verified Increment 3S lineage. The first governed
projection for the new 187-transaction source remains 66 Prepared & Balanced,
121 professional-review exceptions, and zero approved.

Increment 3T corrects the fresh-source exception-classification projection:

- an already-terminal `prepared_exception` remains on the required review
  floor with its original terminal error and versioned exception analysis;
- the synthetic fresh-source review floor is used only to assess whether a raw
  `prepared_balanced` candidate passes the retained promotion gates;
- a blocked balanced candidate receives the distinct
  `projection_evidence_gate_blocked` reason rather than a technical failure;
- true recorded `preparation_failure` exceptions remain unchanged and visible;
  and
- final primary-reason totals continue to reconcile exactly to the governed
  exception count.

Increment 3T changes no stored preparation row, OCR/parser, customer matching,
allocation, review draft, approval, export, posting, or ERP-write behavior.
The accepted 78-item controlled source retains the Increment 3R path, and the
new source retains the 66/121/0 governed state while its 121 reasons are
presented accurately.

## Current runtime overlay — ETOP 0.7.0 Wave 2 Increment 3S

Protected baseline: exact verified Increment 3R lineage. The accepted
78-transaction source continues to use its immutable Increment 3E control and
the unchanged Increment 3R projection, with 43 balanced / 35 review / zero
approved as its protected floor.

Increment 3S corrects the new-source preparation bootstrap exposed by a
different processed 187-transaction PDF:

- absence of the old PDF's exact source/rule/service control is recognized as
  a genuinely new immutable source, not as a resumable prior preparation;
- the new source may register its own idempotent current-rule preparation
  generation after OCR has already been saved;
- its first projection starts every non-human transaction in professional
  review and admits Prepared & Balanced only through the existing complete
  deterministic customer, governed allocation, exact arithmetic, source-row,
  transaction-boundary, signed-credit, no-approval, and no-write gates;
- expected, terminal, balanced, exception, and preserved counts are derived
  from that source's own complete transaction set and never borrow the old
  78/30/48 control or its later projected counts; and
- the Lockbox Automation Center distinguishes **Start ERP & Allocations**
  from **Resume ERP & Allocations**, so a processed file with no preparation
  no longer presents a false resume action.

Increment 3S changes no OCR/parser, customer matching, allocation rule,
review draft, approval, export, posting, or ERP-write behavior. Existing
sources with the exact accepted control retain the Increment 3R path
byte-for-byte at runtime; a new source remains unapproved and fail-closed.

## Current runtime overlay — ETOP 0.7.0 Wave 2 Increment 3R

Protected baseline: exact verified Increment 3Q lineage and accepted
projection, 78 transactions, 43 balanced, 35 review, and zero approved.

Increment 3R corrects the last observed false source-conflict classification
without rerunning OCR or creating a new preparation generation:

- one complete bounded candidate read must prove exactly one
  phone-plus-postal ERP owner with no failed selection gate;
- a recorded conflict set limited exactly to `customer_name` and/or
  `customer_city` may then remain nonblocking because neither field supplied
  the ownership proof;
- the recorded conflict count must reconcile exactly to the preserved conflict
  fields; and
- all original values and raw conflict fields remain preserved in evidence.

Any phone, ZIP, state, street, customer-number, invoice-owner, duplicate or
incomplete candidate, mismatched conflict count, allocation, source-row,
boundary, approval, or write conflict continues to fail closed. City remains
blocking for address and every non-phone/postal selection basis. Increment 3R
changes only protected projection interpretation, retains the accepted
43/35/0 floor, and permits a 44/34 result only when the remaining balanced
candidate satisfies every existing deterministic customer and allocation
gate.

## Current runtime overlay — ETOP 0.7.0 Wave 2 Increment 3Q

Protected baseline: exact verified Increment 3P lineage and accepted
projection, 78 transactions, 35 balanced, 43 review, and zero approved.

Increment 3Q corrects the final control-projection contradiction exposed by
balanced review candidates:

- one complete exact phone-plus-ZIP owner is verified from the preserved ERP
  candidate universe and may retain the resolver's intentional 97% display
  confidence when street OCR is absent;
- one complete exact street-plus-ZIP owner remains deterministic without a
  phone only when the bounded address candidate set is complete and unique;
- one stale name-only payer/payee conflict may be bypassed after either
  ownership fact is proven, while the original conflicting assertion remains
  preserved in projection evidence; and
- duplicate/incomplete candidates, invoice-owner, phone, ZIP, street,
  allocation, source-row, boundary, approval, and write conflicts continue to
  fail closed.

Increment 3Q changes only the runtime projection gate. It reuses the completed
Increment 3P candidate and does not rerun OCR or create a new preparation
generation. The accepted 35/43/0 result is the floor; any qualifying exact
candidate remains prepared but unapproved.

## Prior runtime overlay — ETOP 0.7.0 Wave 2 Increment 3P

Protected baseline: verified Increment 3O lineage and accepted projection,
78 transactions, 35 balanced, 43 review, and zero approved.

Increment 3P unifies four repeated exception patterns without adding a score
threshold or transaction-specific outcome:

- one unique payer-authored `Apply/Post to account` or K&M customer-account
  directive may establish the customer only after exact read-only ERP
  verification and only when preserved invoice ownership does not conflict;
- customer resolution and complete ERP open-A/R retrieval always feed one
  final allocation evaluation, and an exact recommendation may populate only
  an untouched review draft—not a dirty, balanced, corrected, or approved one;
- one remittance invoice may be capped at its current ERP open amount and one
  unique same-customer `SC` item may close the exact remainder only when the
  full remittance and every other row reconcile; and
- status, confidence, reason, and allocation are recomputed from the final
  unified decision, preventing stale ambiguity labels after identity resolves.

Generic bank account labels, multiple directives, missing ERP accounts,
invoice conflicts, incomplete evidence, zero/multiple matching service
charges, nonzero differences, and historical cleared-A/R cases remain review.
Increment 3P is a new append-only candidate generation; the accepted 35/43/0
projection is its fail-closed floor, with no automatic approval or ERP write.

## Current runtime overlay — ETOP 0.7.0 Wave 2 Increment 3O

Protected baseline: verified Increment 3N lineage and accepted projection,
78 transactions, 33 balanced, 45 review, and zero approved.

Increment 3O targets the 30 near-success review exceptions without lowering
OCR quality or customer/allocation controls:

- six bounded OCR page workers use worker-local PDF handles and merge evidence
  in original page order; the existing OCR resolution, regions, modes, and
  transaction boundaries remain unchanged;
- durable ERP preparation defaults to six read workers and one serialized
  writer;
- a complete bounded ERP read may resolve exactly one customer from an exact
  normalized street plus first-five ZIP match when invoice and phone evidence
  do not conflict; duplicates and incomplete reads remain review;
- a resolved customer may balance from exactly one signed open-A/R solution:
  complete open balance, one full aging bucket, the existing due-date rule, or
  one chronological oldest-item prefix; invoices, credits, and `SC` items all
  retain their governed identity and sign; and
- multiple possible solutions, any conflict, nonzero difference, approval,
  export, posting, or ERP write remain blocked.

Increment 3O creates a separate append-only candidate generation. The accepted
33/45 result is the fail-closed floor; each of the 8 single-candidate, 17
ranked-candidate, and 5 matched-customer allocation exceptions is reevaluated
under the same generalized rules, but only deterministic exact cases move.

## Current runtime overlay — ETOP 0.7.0 Wave 2 Increment 3N

Protected baseline: verified Increment 3M lineage and accepted projection,
78 transactions, 33 balanced, 45 review, and zero approved.

Increment 3N corrects the live early-stop condition exposed after Increment 3M:

- a primary crop containing phone, ZIP, and a name is not considered a
  complete payer identity when the street address is absent, because the name
  may still be the check payee;
- bounded below-label full-width and left-payer regions from the same
  transaction page continue to be evaluated until a phone/ZIP/street payer
  anchor is found or every bounded region has been compared;
- the original payee assertion, every attempted region, and the selected
  strategy remain preserved;
- if no bounded region supplies a street anchor, the strongest available
  evidence remains a recommendation and cannot invent payer identity;
- complete exact-phone ERP uniqueness, supplied-ZIP conflict, invoice-owner,
  exact allocation, signed-credit, boundary, no-approval, and no-write gates
  remain unchanged.

Increment 3N creates a separate append-only candidate generation. The accepted
33/45 result, every prior generation, human disposition, and source assertion
remain intact.

## Current runtime overlay — ETOP 0.7.0 Wave 2 Increment 3M

Protected baseline: verified Increment 3L projection, 78 transactions,
33 balanced, 45 review, and zero approved.

Increment 3M corrects a check-payer extraction boundary without weakening the
accepted unique-phone customer rule:

- the primary detected check region remains authoritative when it contains a
  complete payer identity;
- only when that region lacks a complete phone-and-ZIP payer block may ETOP
  inspect bounded below-label full-width and left-payer regions on the same
  transaction page;
- the selected identity retains the region strategy and every bounded attempt;
- a stale saved payee name remains preserved but is not a material customer
  conflict when the candidate payer has a high-confidence exact phone, ZIP,
  name, and address; and
- phone, ZIP, address, invoice-owner, incomplete-read, and duplicate-phone
  conflicts remain material and fail closed.

The recovered payer still passes through BR-LOCKBOX-023: one exact normalized
ten-digit phone must have exactly one ERP owner in a complete bounded read, and
the supplied ZIP may not conflict. Allocation remains separate and must
reconcile exactly through BR-LOCKBOX-021. Increment 3M creates a separate
append-only candidate generation; the accepted 33/45 result, every prior
generation, human disposition, and no-approval/no-write boundary remain intact.

## Current runtime overlay — ETOP 0.7.0 Wave 2 Increment 3L

Protected baseline: verified Increment 3K projection, 78 transactions,
32 balanced, 46 review, zero approved, with unique-phone customer resolution
and complete ERP Open-A/R review behavior accepted.

Increment 3L corrects a remittance continuation-page extraction gap without
changing customer, allocation, approval, or ERP-write authority:

- sparse OCR word boxes from one governed attempt may be reconstructed in
  left-to-right order only when they share one visual row;
- words on adjacent rows remain separate and cannot form an invoice/amount
  pair;
- reconstructed rows retain page, OCR mode, visual-row extraction source,
  parser version, raw evidence, and any cross-source conflict;
- the existing monetary-span mask and exactly-one 8/9-digit invoice rule
  remain mandatory;
- recovered invoices still require unique current-open ERP evidence and exact
  zero-difference reconciliation; and
- the accepted 32/46 projection is the fail-closed floor, with no automatic
  approval, export, posting, or ERP write.

Increment 3L creates a separate append-only candidate generation. Every prior
generation, accepted result, customer, source row, and human disposition
remains unchanged.

## Current runtime overlay — ETOP 0.7.0 Wave 2 Increment 3K

Protected baseline: verified Increment 3J review-completeness runtime over the
Increment 3I 31 balanced / 47 review protected projection.

Increment 3K applies the Product Owner's corrected secondary customer-identity
rule without weakening invoice priority, reconciliation, or human authority:

- complete unique current-open invoice ownership remains first priority;
- when invoice evidence supplies no usable owner, one exact normalized
  ten-digit phone owned by exactly one ERP customer in a complete bounded read
  may establish the customer;
- a supplied valid five-digit ZIP that conflicts with the unique phone owner
  blocks selection, while matching ZIP, address, and name remain corroborating
  evidence;
- duplicate exact phones, incomplete candidate reads, partial invoice-owner
  evidence, and invoice-owner conflicts remain review;
- the selected customer triggers the existing read-only complete open-A/R and
  governed allocation pipeline, including signed credits and `SC` items;
- a control review may move to prepared/balanced only when the existing strict
  projection, source-row, boundary, sign, and exact arithmetic gates pass; and
- no customer recommendation approves, exports, posts, or writes to ERP.

Increment 3K creates a separate append-only candidate generation and preserves
the accepted control, Increment 3I projection, Increment 3J review state, and
all human dispositions.

## Current runtime overlay — ETOP 0.7.0 Wave 2 Increment 3J

Protected baseline: verified Increment 3I control-preserving projection,
78 terminal transactions, 31 balanced, 47 review, zero approved, and zero
projected regressions.

Increment 3J completes the review-only ERP Open-A/R boundary without changing
the accepted projection or matching generation:

- every selected ERP customer triggers the existing read-only current-open
  `TMAROP` query using the payment date as the aging date;
- a failed open-A/R request remains a visible error and can no longer be
  silently represented as an empty invoice list;
- the review workspace automatically exposes the complete current ERP open
  item set, signed total, due date, aging, raw type, reference, and count;
- ordinary invoices retain the governed 8/9-digit identity, while `SC` rows
  use the exact ERP customer/type/reference/count open-item key and never enter
  invoice-owner matching;
- signed credits and `SC` rows participate in review totals and exact due-date
  recommendations without overwriting a dirty draft or human disposition;
- recommendations remain editable and distinct from Decision; and
- automatic approval, ERP writes, posting, and a new preparation generation
  remain unavailable.

Increment 3I remains the authoritative runtime projection and its required
31/47 result is unchanged.

## Current runtime overlay — ETOP 0.7.0 Wave 2 Increment 3I

Protected control: restored and verified Increment 3F R1, generation identity
`ADR-001@0.7.0-wave2-increment3e+BR-LOCKBOX-001..013` with saved service
identity `lockbox-preparation@0.7.0-wave2-increment3e`, 78 terminal
transactions, 30 balanced, and 48 review exceptions.

Increment 3I implements the integration model proven by read-only Shadow
Evaluation R4. It does not replace the accepted control engine:

- every accepted control balance and human disposition is immutable;
- candidate parser/matcher behavior runs only as a separate append-only
  generation against control review items;
- a review item may be promoted only when deterministic customer evidence,
  an allowed allocation method, exact reconciliation, complete source-row
  preservation, signed-credit safety, and next-transaction page boundaries
  all pass;
- a blocked or weaker candidate remains an operator recommendation and cannot
  change control status, accepted customer evidence, approval, or export;
- editable review rows never become extraction evidence;
- current-generation reads do not parse the PDF or create data; and
- `can_auto_approve` and `erp_write_performed` remain false.

The rejected 3G and 3H runtime generations remain historical evidence only.
Their useful deterministic behaviors are admitted solely through the 3I
control-preserving gate. The required pilot result is the R4-proven protected
projection of 31 balanced / 47 review with zero projected regressions.

## Current runtime overlay — ETOP 0.7.0 Wave 2 Increment 3F

Protected baseline: verified Wave 2 Increment 3E runtime.

Increment 3F makes the accepted governed preparation the single operational
projection without changing the Increment 3E matching rule:

- the browser starts or reads the durable backend job and cannot derive final
  counts, queue membership, or export readiness from IndexedDB/localStorage;
- a read-only current-generation query binds source job, immutable PDF hash,
  preparation generation, rule version, and service version;
- final metrics require exact count and primary-reason reconciliation;
- the duplicate legacy review GET/PUT routes are removed;
- legacy human reviews migrate idempotently into the canonical review/export
  store, and selected customer identity now round-trips with the disposition;
- governed recommendations remain distinct from corrected/approved human
  dispositions, and reviewed export remains blocked while exceptions exist;
- ranked candidate snapshots and failed evidence gates are preserved for
  professional inspection without changing selection behavior; and
- no new preparation generation, ERP write, automatic approval, matching
  threshold, invoice admission rule, or allocation rule is introduced.

Increment 3F is a presentation/API/persistence integrity overlay on the
accepted Increment 3E result. The Increment 3E section below remains the
matching and evidence-integrity baseline.

## Protected matching baseline — ETOP 0.7.0 Wave 2 Increment 3E

Protected baseline: verified Wave 2 Increment 3D runtime.

Increment 3E converts the preserved evidence diagnostic into two governed
controls without relaxing review authority:

- monetary spans are masked before invoice detection, so an amount cannot be
  admitted as an invoice candidate;
- exactly one distinct shared-rule 8/9-digit candidate is required per row;
  raw rejected candidates, page, embedded/OCR source, OCR mode, and parser
  version remain preserved;
- substantial remittance images receive governed OCR fallback even when long
  embedded report text is present;
- every admitted invoice receives one bounded direct read-only `TMAROP`
  current-owner lookup, even when broad discovery found zero or one owner;
- missing, partial, duplicate, split, truncated, or unavailable current-owner
  evidence remains review and cannot be replaced by contact scoring;
- exact phone/ZIP selection requires a complete candidate set, one normalized
  ten-digit phone, and five ZIP digits; duplicate pairs remain ambiguous;
- a nonzero CUNUMENT read must be complete and contain linked accounts before
  it may broaden verification;
- oversized OCR identity values and more than 100 admitted invoice values do
  not abort customer preparation; invalid supporting inputs are retained as
  structured rejections;
- Increment 3E creates a new append-only preparation generation while every
  Increment 3D and earlier result, event, and human disposition remains
  unchanged; and
- `can_auto_approve` remains false with no ERP write, approval, or posting
  surface.

Increment 3D's protected baseline was the verified Wave 2 Increment 3C Package
R1 runtime, built on
Increment 3B R2 plus the R2A Windows SQLite test cleanup. R2A changed no
runtime code, and 3C Package R1 changed only the guarded handoff classification
from the original 3C payload.

Increment 3D adds the Product Owner's TMCUST relationship and contact-fallback
criteria without adding a confidence threshold or cross-customer authority:

- automated fallback requires exactly one normalized check-phone/`CUPHONE`
  match plus the same first five check-ZIP/`CUZIP` digits;
- phone alone, name, missing ZIP, and duplicate exact phone/ZIP pairs do not
  select a customer;
- a remaining invoice-owner conflict is not overridden by contact evidence
  alone;
- after one customer anchor is supported, nonzero `TMCUST.CUNUMENT` retrieves
  the matched account, enterprise account when present, and every linked
  customer account through read-only ERP queries;
- a split current-owner conflict becomes a group review only when the unique
  phone/ZIP anchor and every current invoice owner belong to one complete
  group and each remittance invoice has exactly one current owner;
- current open AR is loaded for each linked account and exact cross-account
  remittance rows retain their customer numbers for verification;
- the wider group is never used for due-date guessing, and cross-account rows
  are classified `linked_customer_allocation_review` even at zero difference;
- incomplete groups, out-of-group owners, duplicate owners, and unavailable
  linked AR remain explicit exceptions;
- Increment 3D creates preparation generation 4 while generations 1–3,
  results, events, and human dispositions remain unchanged; and
- `can_auto_approve` remains false with no ERP write, approval, or posting
  surface.

Increment 3C applies the measured 19-item `customer_conflict` funnel without
inventing a score or confidence threshold:

- broad read-only ERP invoice-owner candidates remain preserved as evidence;
- current open AR is read for every broad owner candidate;
- one customer is recommended only when every valid remittance invoice is
  currently open under exactly one and the same candidate;
- missing invoices, failed candidate reads, one invoice open under multiple
  candidates, or invoices split across customers remain customer conflicts;
- phone, address, ZIP, name, score, and confidence cannot override a remaining
  invoice-owner conflict;
- the assessment records broad/current owners, source references, as-of times,
  rule version, explanation, and degraded evidence;
- Increment 3C creates preparation generation 3 while generation 2 results,
  events, and human dispositions remain unchanged; and
- the customer result remains a Recommendation input, `can_auto_approve`
  remains false, and no ERP write or posting behavior is introduced.

Increment 3B R2 corrects the durable preparation identity boundary exposed by
live verification of the 8/9-digit rule correction:

- the same source job and PDF hash may have one append-only preparation
  generation per governed rule version;
- a repeated request within the same rule version remains idempotent;
- changed transaction evidence within the same rule version remains a hard
  conflict;
- the version-2 SQLite schema migrates transactionally to version 3;
- existing jobs, transaction results, human dispositions, and events are
  preserved as generation 1;
- a new generation records its generation number, rule version, and prior
  preparation job IDs; and
- no ERP write, approval, posting, or matching-weight change is introduced.

Increment 3B corrects the Product Owner's ERP invoice-number contract from
9/10 digits to exactly 8/9 digits:

- one shared Python rule governs customer resolution, durable preparation,
  allocation policy, and the reusable invoice matcher;
- one shared TypeScript rule governs preparation, recommendation, exact
  due-date evaluation, failure evidence, and review validation;
- 8-digit invoice evidence now enters read-only ERP matching;
- 7- and 10-digit identifiers do not enter ERP matching;
- `9999999999` remains only the explicit no-remittance review placeholder;
- raw OCR evidence is retained even when it fails ERP admission;
- saved 3A results and append-only history are not silently rewritten; and
- matching weights, ambiguity, approval authority, and ERP behavior are
  unchanged.

Increment 3A adds versioned exception-reason intelligence without changing
the 0.6.9 matching/allocation rules or the Increment 2D durability boundary:

- classifies saved Increment 2D `prepared_exception` records from their
  preserved source/result/error envelope;
- does not rerun OCR or ERP reads and does not rewrite historical result or
  event records;
- persists the same versioned reason analysis for new exceptions;
- separates one primary reason from contributing evidence gaps;
- exposes a summary-only API for the exception funnel;
- retains an explicit unclassified fallback rather than inventing meaning;
- keeps `can_auto_approve` false and adds no ERP write surface; and
- records the behavior in ADR-001, CAP-LOCKBOX-001, and the traceability
  matrix.

Further matching increments must use this measured funnel and may not invent
customer-match thresholds, approval authority, or short-pay/deduction meaning.

Release: `ETOP-Integrated-Agent-1-4-Current-20260730-0.6.9`  
Integration date: 2026-07-30  
Runtime baseline:
`ETOP-Integrated-Agent-1-4-Current-20260730-0.6.8.zip`  
Integrated overlay:
editable Lockbox allocation and signed ERP credit control

## Baseline identity

0.6.8 source baseline SHA-256:
`2084304ce34fcda5b242fd3c20a40c1539ad2f661d67b2d05f63cfd73303a7c8`

0.6.7 source baseline SHA-256:
`a642c95e1fdd3d42c2e0b6c45baaa9d60a11bb3bcb261c32195e8369ef467a6a`

0.6.6 source baseline SHA-256:
`6a56e3255b6c83b500d4555fdfd18407c0e359b0ab899692571dbd0c7242cc85`

0.6.5 source baseline SHA-256:
`8d00a134fa149e3a109db8889514b2d34fb224c821cba5006a5802ab84adba88`

0.6.5 preparation source SHA-256:
`480e75e34aa348b37d05b107af7feb452fcb75e69cbadc26bde2046207e3dbcb`

Underlying ERP customer-resolution runtime SHA-256:
`ad07f74ce9c67d6ed4e5dfc8e22b3b3b42125e70dc093c73a668fe003e968e30`

0.6.3 integrated Agent 1–4 overlay SHA-256:
`67740019df66c00dfda22b8d79ae4628bfcd9f402daa235fd94971167a7f4491`

Original common baseline SHA-256:
`464f3405c5f4a3f838cf029c880f18f53f3d17fe9c3b73980657f423c0fabc38`

This package starts from the newest ERP customer-resolution runtime. Agent 1–4
outputs were then merged against the original common baseline, so the later
customer search and invoice-derived ERP hydration are not replaced by earlier
shared files.

## 0.6.9 targeted improvements

- Consolidates the prepared Invoice Allocation Detail and the editable review
  rows into one active human-review draft.
- Allows reviewers to edit apply amounts, remove an incorrect invoice, add a
  remaining verified ERP open invoice, or add a controlled blank row directly
  inside the expanded recommendation workspace.
- Retains original OCR rows separately for evidence and training.
- Derives cash-application business effect from the signed ERP amount. An ERP
  record carried as `Debit` with a negative source amount remains labeled with
  its raw type as evidence but is presented and applied as a Credit.
- Recalculates proposed totals and differences after authoritative credit-sign
  reconciliation.
- Blocks saving an ERP-derived credit with a positive apply amount.
- Corrects the sign of existing prepared but not human-reviewed 0.6.8 drafts
  when authoritative open-invoice detail is loaded.
- Preserves human-corrected and approved records without silent rewriting.
- Runs signed open-invoice reconciliation for every verified customer before
  applying exact due-date priority.
- Adds deterministic regression coverage for the retained negative-debit invoice fixture as a
  `-$916.00` credit despite the raw ERP `Debit` label.
- Amends ADR-001 without changing balance tolerance, approval authority,
  bounded preparation, persistence, or ERP read-only boundaries.

## 0.6.8 targeted improvements

- Adds a read-only bulk invoice-owner endpoint to the existing customer-match
  router. One request accepts up to 500 invoices; the frontend sends bounded
  chunks of 250.
- Collects unique valid remittance invoices once per pending lockbox and
  resolves their complete owner sets through the bulk endpoint.
- Uses a bulk owner only when all returned evidence identifies one unique ERP
  customer. Missing or multiple owners retain the existing transaction-level
  customer-resolution path.
- Runs four read-only transaction-preparation workers by default, with an
  internal hard maximum of eight.
- Keeps local review persistence single-writer and sequential so concurrent
  ERP reads cannot create lost review updates.
- Reuses customer-master reads by ERP customer number.
- Reuses authoritative open-invoice reads by customer number and effective
  aging date.
- Replaces the growing whole-file `localStorage` checkpoint with
  per-transaction IndexedDB records and migrates legacy 0.6.6/0.6.7 cache
  values when available.
- Preserves one terminal checkpoint per transaction, file-level completion
  coverage, transaction-isolated failures, exact due-date priority, review
  gating, human authority, and read-only ERP behavior.
- Adds deterministic bulk-resolution and concurrency regressions while
  retaining the 27-of-125 resume, the retained verified-customer fixture, and six-invoice
  $1,129.36 regressions.
- Amends ADR-001 with performance changes that are permitted without weakening
  evidence, ambiguity, persistence, or approval boundaries.

## 0.6.7 targeted fixes

- Validates preparation coverage against every transaction in the current OCR
  review instead of treating a non-empty cache as complete.
- Resumes only missing transactions after an interrupted batch. Existing
  0.6.6 cache records remain readable and are upgraded on their next save.
- Saves a checkpoint after every attempted transaction.
- Isolates transaction-level preparation and review-persistence failures so
  later checks are still attempted.
- Applies bounded preparation and persistence timeouts; a timed-out
  transaction becomes an explicit review exception rather than blocking the
  file indefinitely.
- Gates the final exception count, transaction review table, and reviewed
  export until preparation reaches the full OCR transaction count.
- Replaces the misleading reprocess path with **Resume ERP & Allocations
  (completed/total)** while a processed lockbox remains incomplete.
- Adds deterministic regression coverage for the reported 27-of-125
  interruption, including a simulated failure on transaction 64 and continued
  processing through transaction 125.
- Routes manual ERP customer selection and recommendation refresh through the
  same customer-aware due-date evaluator used by batch preparation.
- Reads detailed invoice number, due date, and open balance directly from the
  read-only ERP open-invoice endpoint before falling back to the broader
  recommendation endpoint.
- Automatically refreshes the allocation after ERP customer selection so an
  empty generic EOM-aging response cannot remain stale in the review panel.
- Adds customer-aware orchestration regression coverage for the retained verified-customer fixture
  and the six 7/10/26 invoices totaling $1,129.36.
- Amends ADR-001 with the file-level completion, checkpoint, resume, and
  failure-isolation requirements.
- Preserves the authority boundary: failures remain review exceptions,
  preparation is not approval, and no ERP write occurs.

## 0.6.6 targeted fixes

- Makes ERP customer resolution, authoritative customer hydration,
  open-invoice analysis, allocation preparation, and review persistence part
  of **Process PNC Lockbox** for every transaction.
- Calculates the exception queue only after preparation completes.
- Saves prepared customer and allocation fields through the existing local
  lockbox review endpoint.
- Caches the full analytical envelope by lockbox job so leaving and reopening
  the workspace does not rerun completed preparation.
- Upgrades an older saved OCR result through batch ERP/allocation preparation
  when it is first reopened, without rerunning OCR.
- Defaults the automation-center and review-workspace queues to unresolved
  transactions while retaining an all-transactions view.
- Stops invalidating a saved preparation after human correction or approval.
- Evaluates complete exact-due-date invoice groups before generalized EOM or
  aging-bucket combinations.
- Returns actual invoice rows and an exact due-date explanation when the group
  equals the check.
- Adds a visible Due Date column to Invoice Allocation Detail.
- Adds `ADR-001 — Lockbox Preparation and Exact Due-Date Priority`.
- Preserves the authority boundary: prepared/balanced is not approved, no ERP
  write occurs, and `can_auto_approve` remains false.

## 0.6.5 targeted fixes

- Adds a reusable transaction-preparation coordinator that completes
  remittance invoice validation, ERP customer resolution, authoritative
  customer-master hydration, open-invoice retrieval, and allocation analysis
  before the reviewer enters the selected transaction.
- Always reruns the recommendation engine with the resolved ERP customer,
  eliminating the stale first-pass `No Invoice Match` result that could later
  correct itself after a manual refresh.
- Prepares a newly selected transaction before changing the active review
  draft and reuses the result during the current lockbox session.
- Preserves manual review authority: preparation produces a recommendation but
  does not approve, save, post, or silently apply an allocation.
- Expands the invoice-allocation experience with a taller dedicated table,
  sticky headers, visible scrollbars, larger editable rows, and an optional
  near-full-screen detail view.
- Corrects recommendation-panel contrast to match the Lockbox Review dark
  workspace.

## 0.6.4 targeted fixes

- Reopens any saved lockbox result even when the generic document job still
  reports `uploaded`.
- Reuses an existing upload when the selected local PDF has the same name and
  byte size.
- Automatically validates unique 9- or 10-digit remittance invoices against
  the read-only ERP customer-match service.
- Excludes invalid OCR identifiers and the controlled no-remittance placeholder
  from ERP invoice lookups.
- Automatically hydrates the verified ERP customer and loads the connected
  cash-application recommendation.
- Treats the verified ERP customer master as authoritative over OCR identity
  fields.
- Corrects combined locality lines so City, State, and ZIP no longer populate
  Address Line 2.
- Adds persistent, high-contrast scrollbars to the Lockbox Review panes.

## Integrated agent outputs

### Agent 1 — Blueprint

- Full First Concrete Blueprint Package
- 10 Architecture Standards
- 6 Enterprise Reality Models
- 5 Professional Knowledge Models
- 10 Enterprise Objects
- 8 Platform Service Standards
- Package manifest, source record, index, and traceability matrix
- Root Agent Operating Contract and repository agent instructions

Source archive SHA-256:
`4bfe009822360b0aa65393dc82e93c01bc4dab8594b2d34864edb7e8c9d43471`

### Agent 2 — Enterprise search

- Federated local search across modules, customers, reports, and documents
- SOP Search, Document Intelligence, and Project Tracker registry coverage
- Multi-word and plural search matching
- Search result count, stale-request protection, and Enter-to-open behavior
- Direct opening of selected customers, reports, and documents
- Backend search-router registration retained alongside Agent 4 routes

Source archive SHA-256:
`4f0ce6ad806daa93e4b61cdd89f5963dbeaccc4196d4602f7b950cbde58540d0`

### Agent 3 — UI and reporting

- Task-oriented navigation: Overview, Workspaces, Tools, and System
- First-class Lockbox Automation workspace
- Separation of Document Operations from Document AI Studio
- Dashboard and module-purpose guidance
- Restored Report Builder layout and stylesheet
- Working catalog search, category/sort controls, report design, parameters,
  preview, export, and stale-parameter handling

Source archive SHA-256:
`2e7d59aeb6e3791e6c7dbf7552798e6ea0431c890f3b0b07c51f9a1f4402b3bb`

### Agent 4 — Priority review and lockbox recovery

- Live Madden-backed customer priority queue
- Deterministic Critical, High, and Elevated risk ranking
- Risk evidence, utilization, exposure, past-due, and 60+ day balances
- Processed lockbox reopening without rerunning OCR
- Saved review restoration
- Searchable ERP customer selection
- Invoice-first customer matching, followed by phone, street + ZIP, with name
  used only as supporting evidence
- Strong unambiguous match population without hardcoded customer numbers

Source archive SHA-256:
`f87fb12c0a10b08c9dd68af3421979ace2be2d53241f5cccfa7bf5b48d1c8e41`

## Shared-file collision resolutions

| Shared file | Resolution |
| --- | --- |
| `src/App.tsx` | Preserved Agent 3 navigation, Agent 2 search-result routing, and Agent 4 priority-review mode. |
| `backend/main.py` | Registered enterprise search, customer risk, and customer match routers together. |
| `src/features/customer360/Customer360.tsx` | Preserved live risk review and added direct opening by searched customer number. |
| `src/features/enterprise-dashboard/EnterpriseDashboard.tsx` | Retained both high-risk review and PNC lockbox work items. |
| `src/components/ReportBuilder/ReportBuilder.tsx` | Retained Agent 3 repair and Agent 2 direct report-opening support. |
| `src/modules/document-intelligence/DocumentIntelligence.tsx` | Retained workspace separation and Agent 2 direct document-opening support. |
| `src/api/customers.ts` | Retained multi-field customer search and inactive-customer review support while adding the live priority-review API. |
| `src/features/customer360/types.ts` | Combined ERP address/contact fields with risk-review contracts. |
| `src/modules/document-intelligence/components/LockboxReviewWorkspace.tsx` | Kept the newer ERP search, customer-master hydration, invoice-first resolution, and OCR fallback behavior. |
| `src/modules/document-intelligence/components/lockboxRecommendation.ts` | Kept the newer configured-local-API recommendation client. |
| `src/modules/document-intelligence/types.ts` | Combined OCR/customer identity fields with the reusable customer-match request and response contracts. |
| `CHANGELOG.md` | Consolidated the newer ERP customer-resolution work and the 0.5.1, 0.6.1, and 0.6.2 Agent 1–4 history under release 0.6.3. |

Every overlapping file was compared to the common July 29 baseline. A newer
runtime file was retained only after its behavior was reviewed against the
Agent 1–4 change.

Merge accounting:

- 60 Agent 1–4 files were new to the current runtime and were added;
- 23 files contained Agent 1–4 changes while the current runtime still matched
  the common baseline, so those changes were carried forward;
- 5 files had independent changes on both sides and were explicitly merged;
- 1 current-runtime-only file,
  `src/modules/document-intelligence/components/lockboxRecommendation.ts`, was
  retained unchanged; and
- 129 source files were unchanged across all three inputs before the guarded ZIP
  builder was updated for future exports.

## Future export safeguard

`Create-ETOP-Cloud-Zip.ps1` now:

- refuses to archive an incomplete local project;
- requires the Agent Operating Contract, integration manifest, Blueprint,
  `backend/core`, `backend/data/database.py`, and `backend/modules`;
- includes backend source packages and the Blueprint traceability matrix;
- continues to exclude credentials, databases, operational data, uploads,
  documents, OCR results, generated output, and local environment files; and
- verifies that the intentionally excluded `SqlEditor.tsx` exists in the local
  source before packaging, so its absence from the ZIP is an explicit boundary
  instead of an undetected missing dependency.

## Validation record

### 0.6.9 validation

- TypeScript production build: **Passed**
- Vite production bundle: **Passed**, 90 modules transformed
  - validation used a temporary compatibility stub for the intentionally
    excluded `SqlEditor.tsx`; the stub is not present in this release.
- Targeted ESLint for all changed runtime TypeScript/TSX files: **Passed**
- Full repository ESLint: **14 legacy errors, 0 warnings**
  - unchanged from 0.6.8; and
  - none are in 0.6.9 changed files.
- Existing Lockbox workflow regressions: **5 passed**
  - bulk invoice resolution and ambiguity fallback;
  - four-worker preparation and serialized persistence;
  - 27-of-125 resumable completion;
  - customer-aware $1,129.36 allocation; and
  - six-invoice exact July 10 due-date allocation.
- Negative-debit credit/editing regression: **Passed**
  - retained negative-debit invoice fixture;
  - raw ERP transaction type Debit;
  - source and effective amount `-$916.00`;
  - effective business type Credit;
  - proposed total and difference recalculated;
  - row add/edit/remove controls present; and
  - automatic approval remains false.
- No shared application shell, navigation, backend route, `src/App.tsx`,
  `backend/main.py`, balance tolerance, approval authority, ERP write behavior,
  or local `SqlEditor.tsx` change was made.
- Source-difference audit: **12 intentional differences from 0.6.8**
  - 10 modified source/governance/release files; and
  - 2 new handoff/verification files.
- Release source inventory: **233 files**
- Generated dependencies, build output, operational data, symlinks,
  `SqlEditor.tsx`, and merge markers: **not present**

### 0.6.4 validation

- TypeScript production build: **Passed**
- Vite production bundle: **Passed**, 87 modules transformed
  - validation used a temporary compatibility stub for the intentionally
    excluded `SqlEditor.tsx`; the stub is not present in this release.
- Targeted ESLint for all changed Lockbox TypeScript/TSX files: **Passed**
- Python compilation for all included backend Python files: **Passed**
- Pure deterministic backend risk/matching checks: **6 passed**
  - includes valid 9-digit, formatted 9-digit, invalid 8-digit, invalid
    11-digit, and no-remittance-placeholder invoice cases.
- HTTP router tests were not run in the packaging environment because its
  Python runtime did not include FastAPI or pytest.

### 0.6.5 validation

- TypeScript production build: **Passed**
- Vite production bundle: **Passed**, 88 modules transformed
  - validation used a temporary compatibility stub for the intentionally
    excluded `SqlEditor.tsx`; the stub is not present in this release.
- Targeted ESLint for all changed Lockbox TypeScript/TSX files: **Passed**
- No backend route, ERP write behavior, shared application shell, or
  `backend/main.py` changes were made.

### 0.6.8 validation

- TypeScript production build: **Passed**
- Vite production bundle: **Passed**, 90 modules transformed
  - validation used a temporary compatibility stub for the intentionally
    excluded `SqlEditor.tsx`; the stub is not present in this release.
- Targeted ESLint for all changed TypeScript/TSX files: **Passed**
- Full repository ESLint: **14 legacy errors, 0 warnings**
  - unchanged from 0.6.7; and
  - none are in 0.6.8 changed files.
- Python compilation for the updated customer-match router and service:
  **Passed**
- Pure deterministic backend customer-risk/matching checks: **6 passed**
- Bounded-concurrency regression: **Passed**
  - four read-only preparation workers;
  - one shared file-level preparation context; and
  - one serialized review writer.
- Bulk invoice-resolution regression: **Passed**
  - one bulk request for three unique invoices;
  - two unambiguous invoices reused the retained verified-customer fixture;
  - the verified-customer fixture master data loaded once; and
  - one multi-owner invoice used the transaction-level ambiguity fallback.
- Resumable batch regression: **Passed**
  - 27 existing records preserved;
  - only the remaining 98 transactions attempted;
  - simulated transaction 64 failure retained; and
  - final coverage 125 of 125.
- Exact due-date and customer-aware regressions: **Passed**
  - retained verified-customer fixture;
  - six 7/10/26 invoices;
  - suggested total $1,129.36;
  - zero difference;
  - 8/10/26 invoices excluded; and
  - automatic approval remains false.
- No shared application shell, navigation, `src/App.tsx`, `backend/main.py`,
  allocation tolerance, due-date rule, approval behavior, or ERP write
  behavior changed.
- Source-difference audit: **17 intentional differences from 0.6.7**
  - 14 modified source/governance/release files; and
  - 3 new handoff/verification files.
- Release source inventory: **231 files**
- Generated dependencies, build output, operational data, symlinks,
  `SqlEditor.tsx`, and merge markers: **not present**

### 0.6.7 validation

- TypeScript production build: **Passed**
- Vite production bundle: **Passed**, 92 modules transformed
- Targeted ESLint for the changed API and Lockbox TypeScript/TSX files:
  **Passed**
- Full repository ESLint: **14 legacy errors, 0 warnings**
  - unchanged from 0.6.6; and
  - none are in 0.6.7 changed files.
- Resumable batch regression: **Passed**
  - 27 existing preparation records preserved;
  - transactions 28 through 125 attempted exactly once;
  - simulated transaction 64 failure recorded;
  - transactions 65 through 125 still attempted;
  - final coverage 125 of 125; and
  - one explicit preparation failure retained for review.
- Exact due-date regression from 0.6.6: **Passed**
- Customer-aware manual-selection orchestration regression: **Passed**
  - retained verified-customer fixture supplied;
  - generic EOM-aging result received;
  - exact due-date evaluator invoked;
  - six 7/10/26 invoice rows returned; and
  - suggested total $1,129.36 with zero difference.
- ERP open-invoice provider regression: **Passed**
  - direct open-invoice endpoint requested for the retained verified-customer fixture;
  - aging date supplied;
  - actual ERP invoice rows grouped by due date;
  - six 7/10/26 rows selected; and
  - broader recommendation fallback not required for the exact match.
- The shared document API change is backward compatible: it only adds an
  optional abort signal to the existing local review-save request.
- No backend route, ERP write behavior, shared application shell, navigation,
  `src/App.tsx`, or `backend/main.py` changes were made.

### 0.6.6 validation

- TypeScript production build: **Passed**
- Vite production bundle: **Passed**, 90 modules transformed
- Targeted ESLint for all changed Lockbox TypeScript/TSX files: **Passed**
- Full repository ESLint: **14 legacy errors, 0 warnings**
  - unchanged from the documented 0.6.5 baseline;
  - none are in 0.6.6 changed files.
- Exact due-date regression: **Passed**
  - six invoices due July 10, 2026;
  - amounts $83.00, $24.00, $337.36, $162.00, $274.00, and $249.00;
  - total $1,129.36;
  - August 10 invoices excluded;
  - exact due-date explanation returned; and
  - automatic approval remains false.
- No backend route, ERP write behavior, shared application shell, or
  `backend/main.py` changes were made.

### 0.6.3 integration validation

- TypeScript production build: **Passed**
- Vite production bundle: **Passed**, 89 modules transformed
  - validation used a temporary compatibility stub for the intentionally
    excluded `SqlEditor.tsx`; the stub is not present in this release.
- Targeted ESLint for all integration-critical TS/TSX files: **Passed**
- Python compilation for all 23 included backend Python files: **Passed**
- Deterministic backend checks: **8 passed**
  - two risk-ranking checks;
  - three customer-match checks; and
  - three registry-search checks for high-risk customers, lockbox, and SOP.
- Full repository ESLint: **14 legacy errors, 0 warnings**
  - the original supplied baseline had 20 errors and 6 warnings;
  - no new lint errors remain in the integration-critical files;
  - remaining errors are in pre-existing SQL workspace, API utility, grid, and
    document hook/viewer code.

## Intentional exclusions

The release does not contain:

- `src/components/sqlstudio/SqlEditor.tsx`;
- `node_modules`;
- generated `dist` output;
- `.git` history;
- Python bytecode or `__pycache__`;
- `.env` files other than `.env.example`;
- databases, operational data, uploads, OCR documents, spreadsheets, or local
  lockbox working files.

`SqlEditor.tsx` remains intentionally untouched and must stay in Josh's local
project.

## Known source-package boundary

The supplied cloud-development packages intentionally omitted the local
`backend/core`, `backend/data`, and `backend/modules` packages imported by
`backend/main.py`. This integrated ZIP preserves that security boundary. It is
an integration release for Josh's existing full local ETOP project, not a
standalone replacement for omitted local-only packages or data.

## Installation safety

Use `Install-ETOP-Integrated-Release.ps1` from a separately extracted copy of
this release. The installer:

1. verifies the current integrated baseline hashes for every patched target;
2. stops if the local baseline differs;
3. backs up every existing target file under `.etop-backups`;
4. copies only files changed or added by this integration; and
5. verifies copied file hashes.

It does not delete unlisted project files and does not touch
`src/components/sqlstudio/SqlEditor.tsx`.
