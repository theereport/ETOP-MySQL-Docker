# ETOP 0.7.0 Step 6 Increment 1 — Financial Close Readiness Foundation

## Outcome

Step 6 Increment 1 establishes the first bounded Financial Close and Controller
Intelligence slice: an authenticated, persistent local Close Cycle and Close
Control evidence register with distinct preparer/reviewer identities,
append-only evidence and review events, deterministic staleness, and explicit
source/authority gaps.

It does not determine whether the books are ready to close and cannot close,
approve, certify, post, or reopen a financial period.

## Protected baseline

Implementation must begin from the exact installed ETOP 0.7.0 Step 5 R1
baseline accepted by the Product Owner. The release package must record and
verify that baseline's exact source manifest/hash before applying changes. The
historical July archive and pre-R1 Step 5 package are not valid implementation
baselines.

## Governed package identity

- Package: `ETOP-0.7.0-Step6-Increment1-Financial-Close-Readiness-Foundation`
- Runtime contract: `financial-close-readiness.v1`
- Source: SRC-007
- Capability: CAP-FC-001
- Decision model: DEC-FC-001
- Architecture decision: ADR-014

## Increment 1 professional flow

1. Sign in through the existing Workflow Foundation.
2. Create a local Close Cycle for an explicitly labeled entity and period.
3. Add a locally defined Close Control Item.
4. Select two different active local accounts as preparer and reviewer.
5. The configured preparer records a source reference, missing evidence, or
   unavailable evidence.
6. The configured reviewer evaluates the exact current evidence and records
   `evidence_sufficient`, `needs_information`, `not_ready`, or `deferred` with
   rationale.
7. ETOP derives local control and cycle evidence readiness.
8. Later preparer evidence leaves the old review intact and marks it stale.

## State contract

The UI and API must keep these state dimensions separate:

| Dimension | Values | Effect |
|---|---|---|
| ERP/GL period state | `unavailable` | No source and no close/reopen authority. |
| Evidence | `not_recorded`, `reference_recorded`, `missing`, `unavailable` | Local preparer evidence metadata only. |
| Review currency | `not_reviewed`, `current`, `stale` | Exact binding to latest evidence. |
| Control readiness | `not_started`, `awaiting_review`, `attention_required`, `evidence_sufficient`, `stale` | Local evidence-review projection. |
| Cycle readiness | `not_started`, `in_progress`, `attention_required`, `evidence_ready` | Aggregate of all locally recorded controls. |

`evidence_ready` means only that all locally recorded controls have
current sufficient evidence reviews. It does not mean `ready_to_close`.

## Identity and authority contract

- All writes require an existing valid Workflow Foundation bearer session.
- Preparer and reviewer must be active, distinct local user IDs.
- The evidence actor must be the configured preparer; the review actor must be
  the configured reviewer.
- No new role, shared task, queue, assignment, notification, SLA, or escalation
  is added in Increment 1.
- Local authentication does not establish accounting role, Controller
  delegation, approval limit, or financial-close authority.
- Review effect is `professional_evidence_metadata`.
- Authority, approval, close, period, posting, export, notification, and ERP
  effects are all `none`.

## Expected runtime routes

All routes are under `/api/v1/financial-close` and use strict request/response
models.

- `GET /governance`
- `GET /cycles`
- `POST /cycles`
- `GET /cycles/{cycle_id}`
- `POST /cycles/{cycle_id}/controls`
- `POST /cycles/{cycle_id}/controls/{control_id}/preparations`
- `POST /cycles/{cycle_id}/controls/{control_id}/reviews`
- `GET /cycles/{cycle_id}/controls/{control_id}/events`

There are no PUT, PATCH, DELETE, close, approve, certify, post, reopen, export,
or ERP routes.

Every POST requires an idempotency key. Preparation and review POSTs also bind
an `expected_control_version`; the service binds review evidence to the latest
server-verified preparation hash, and changed evidence returns conflict rather
than recording a review over stale support.

## Persistence and evidence

The module owns only local Close Cycle/control/evidence/review records. It must:

- preserve cycle and control definition identity;
- append, never overwrite, evidence and review events;
- use database guards against update/delete of historical evidence;
- retain actor, recorded time, evidence status/reference, rationale, current
  control version, idempotency request hash, and canonical SHA-256;
- maintain and verify a domain event hash chain;
- avoid copying Workflow credentials/session tokens into domain evidence;
- avoid copying referenced sensitive files or payloads; and
- leave the local database outside install and release archives.

This is domain evidence and PSS-008-compatible provenance, not the completed
enterprise Audit and Provenance Service.

## Source authority and coverage

The workspace must show:

- local user identity/session: available with local-credential assurance;
- cycle/control definitions: available as operator-authored local records;
- evidence reference/reviewer rationale: available as authenticated local
  professional records;
- referenced evidence content: unverified unless explicitly proven by a later
  governed connector;
- legal entity/fiscal calendar: operator-supplied and unverified;
- GL period state, balances, journals, reconciliations, consolidations, and
  close authority: unavailable/not connected; and
- ERP access by this module: none.

Missing and unavailable values cannot be rendered as zero, passed, approved,
reconciled, or closed.

## Minimum UI behavior

- navigation entry: **Financial Close**;
- source/authority boundary banner visible on every cycle;
- empty, loading, partial, error, and integrity-failure states;
- cycle create/list/select experience;
- control register with local planning date, preparer/reviewer, evidence,
  review, staleness, and attention state;
- evidence form available only to the configured signed-in preparer;
- review form available only to the configured signed-in reviewer;
- disabled `evidence_sufficient` when deterministic evidence gates fail;
- cycle measures limited to the visible local population and labeled as such;
- event history with evidence/review hashes and source references; and
- no mock balances, unexplained close percentage, AI conclusion, or financial
  action button.

## Acceptance criteria

### Contract and domain

- cycle/control creation persists across backend restart;
- strict models reject unknown fields and invalid identifiers/dates;
- actual ERP/GL period state always remains `unavailable`;
- no UI or API state is named closed, certified, approved, reconciled, posted,
  or reopened;
- aggregates use every locally recorded control and disclose that population;
- no fake cycle, control, evidence, balance, or metric is seeded.

### Identity and separation

- unauthenticated or expired sessions cannot write;
- missing, inactive, identical, or actor-mismatched preparer/reviewer identities
  are rejected;
- local identities retain authority status `not_configured` and financial
  effects `none`;
- existing Workflow roles/tasks and accepted module behavior remain unchanged.

### Evidence and review

- evidence/review events are append-only and update/delete attempts fail;
- repeated identical idempotent requests append no duplicate event and return
  the current control projection;
- reused keys with different payloads return conflict;
- `evidence_sufficient` is rejected without current valid evidence or when
  required evidence is missing/unavailable;
- review binds exact evidence ID/hash;
- new evidence makes the earlier review stale without mutation;
- canonical record and event-chain verification detects tampering; and
- source references, gaps, limitations, and no-effect statements survive
  round-trip persistence.

### Safety and integration

- the module imports no ERP database dependency and emits no ERP query;
- no source-system mutation, close, approval, posting, export, notification, or
  AI action exists;
- frontend type-check, focused lint, and production build pass;
- backend financial-close and retained Workflow/ERP/AP/Credit/Lockbox tests
  pass;
- the verifier checks OpenAPI for the bounded route/method set and forbidden
  financial-action routes;
- install preflight binds the exact accepted Step 5 R1 source;
- source rollback preserves local financial-close data; and
- archives contain no database, evidence payload, credentials, session token,
  or operational source row.

## Explicitly deferred

- approved close calendar/templates, recurring cycle generation, shared tasks,
  assignment, SLA, escalation, and notifications;
- account reconciliations, balances, tie-outs, certification, and approved
  segregation-of-duties policy;
- journal entries, accruals, allocations, recurring entries, reversals,
  approvals, and posting;
- intercompany, eliminations, consolidation, multi-entity and currency close;
- flux/variance analysis, materiality, anomaly detection, Controller narrative,
  and AI;
- authoritative entity/fiscal-period/GL status, Controller delegation,
  close/reopen/certification authority, and execution;
- evidence-file ingestion/validation, retention, legal hold, auditor access,
  secure export, and audit-ready close package;
- enterprise SSO, network synchronization, external communication; and
- every ERP/GL read or write.
