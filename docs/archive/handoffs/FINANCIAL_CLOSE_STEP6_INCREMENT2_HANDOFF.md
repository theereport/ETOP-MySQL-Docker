# ETOP 0.7.0 Step 6 Increment 2 — Local Close Planning Templates

## Outcome

Step 6 Increment 2 adds a usable, governed Financial Close planning surface
for immutable, numbered **local user-authored planning drafts** and explicit
manual creation of a Close Cycle from one exact selected version plus an
operator-supplied calendar anchor.

Instantiation atomically preserves an immutable template-to-cycle snapshot,
creates ordinary Increment 1 cycle/control records, and then uses the retained
preparer-evidence/reviewer-readiness journey unchanged. Later template versions
cannot rewrite the earlier cycle, controls, dates, evidence, reviews, or
lineage.

This increment cannot read or write ERP/GL data and cannot close, approve,
certify, attest, post, reopen, schedule, notify, create a shared task, or grant
financial authority.

## Protected baseline

Implementation used the isolated `step6_i2` workstream copied from the exact
accepted Step 6 Increment 1 payload. The parent integration workstream had
already independently verified its payload hashes. No historical archive or
pre-Increment 1 source was used.

## Governed identities

- Source: SRC-008
- Capability: CAP-FC-001 version 0.2.0
- Decision model: DEC-FC-001 version 0.2.0
- Architecture decision: ADR-015
- Existing readiness contract: `financial-close-readiness.v1` (unchanged)
- Additive planning contract: `financial-close-planning.v1`
- Template authority: `local_user_authored_planning_draft`
- Calendar effect: `planning_dates_only`

## Implemented professional flow

1. An authenticated Workflow Coordinator opens **Planning templates** in the
   Financial Close workspace.
2. The coordinator authors version 1 with one or more ordered controls, integer
   anchor offsets, and different active local preparer/reviewer accounts.
3. ETOP preserves immutable root/version/item records plus a hash-chained
   authenticated `template_created` event.
4. A coordinator may append, never overwrite, a new immutable version using an
   exact expected-latest-version guard and change note.
5. The coordinator chooses one exact version, supplies entity/period labels and
   dates plus a planning anchor, and sees proposed anchor-plus-offset dates.
6. One explicit POST atomically creates the cycle, its controls, the exact
   template/version/item/identity/date/record-ID snapshot, and both cycle and
   template history.
7. The cycle appears in the retained Close Work Plan. Its controls proceed
   through existing Increment 1 preparation and distinct reviewer evaluation.
8. Cycle/control screens display immutable snapshot/version/item hashes and
   offsets. A later template version does not affect them.

No timer, recurrence engine, background process, automatic cycle/task creation,
notification, or external communication participates in this flow.

## Additive routes

All routes remain under `/api/v1/financial-close`, use the existing Workflow
Foundation bearer session, and expose strict response/request models.

- `GET /templates`
- `POST /templates`
- `GET /templates/{template_id}`
- `POST /templates/{template_id}/versions`
- `POST /templates/{template_id}/versions/{template_version}/instantiate`

The eight accepted Increment 1 operations remain present, including direct
cycle/control creation and preparation/review history. There are no PUT, PATCH,
DELETE, close, approval, certification, posting, reopen, notification,
automation, ERP, or ledger routes.

## Persistence and integrity

The module adds only source-initialized, module-local tables:

- `fc_control_templates`
- `fc_template_versions`
- `fc_template_items`
- `fc_template_events`
- `fc_cycle_template_snapshots`

Database triggers prohibit update/delete of template roots, versions, items,
events, and snapshots. Each definition/event/snapshot has canonical SHA-256
evidence; template events maintain a per-template predecessor-hash chain. Reads
verify root, item, version, chain, snapshot, cycle, control, and lineage
integrity before returning current-good projections.

Manual instantiation uses one `BEGIN IMMEDIATE` transaction. Any inactive or
identical identity, stale/hash mismatch, idempotency conflict, or database
failure rolls back cycle, controls, snapshot, and event together. Identical
retries return the original cycle without duplication.

The transaction revalidates every configured preparer/reviewer account after
acquiring its write lock, closing the status-change race between request
validation and persistence. Reads cross-check every snapshot item, identity,
ordinal, offset, anchor-derived date, generated control binding, immutable
version hash, and version/snapshot event so a rehashed mismapping or deleted
valid chain tail is withheld as an integrity failure.

Runtime databases and local operational content are not release artifacts.
Source rollback must preserve these tables and records.

## UI behavior

`ClosePlanningTemplates.tsx` is a working capability surface, not a decorative
card. It provides:

- template-list loading, empty, error, retry, and detail-integrity states;
- dynamic multi-control version-1 authoring;
- active/distinct default preparer/reviewer selection and client validation;
- exact immutable version selection, SHA-256, author, items, and event history;
- prefilled append-only next-version authoring with required change note;
- operator entity/period/calendar-anchor/target/description entry;
- proposed planning-date preview with server-side recomputation disclosure;
- explicit exact-version manual instantiation; and
- persistent local-draft, no-policy, no-automation/notification, and no-ERP/GL
  labels.

Create-template and instantiate forms retain one idempotency key across an
ambiguous failed attempt and replace it only after success or an intentional
form/source change. Changing the selected template clears any open revision;
the submit path also rejects a revision whose originating template no longer
matches the current selection.

The existing workspace continues to provide direct cycles/controls, evidence
submission, review, staleness, queues, event history, and governance views.

## Validation evidence

| Gate | Command | Result |
|---|---|---|
| Financial Close backend | `cd backend && python -m unittest test_financial_close_readiness` | PASS — 16 tests |
| Python syntax | `python -m py_compile backend/modules/financial_close/{schemas,repository,service,api}.py backend/test_financial_close_readiness.py` | PASS |
| Focused verifier | `node verification/verify-financial-close-readiness.mjs` | PASS |
| Focused frontend lint | `npx eslint src/features/financial-close/FinancialCloseWorkspace.tsx src/features/financial-close/ClosePlanningTemplates.tsx src/features/financial-close/api.ts src/features/financial-close/types.ts --max-warnings=0` | PASS |
| Frontend production build | `npm run build` | PASS; existing bundle-size advisory only |
| Retained Workflow Foundation | `cd backend && python -m unittest test_workflow_foundation` | PASS |
| Retained ERP Evidence Gateway | `cd backend && python -m unittest test_erp_evidence_gateway` | ENVIRONMENT BLOCKED — this Python runtime does not include `fastapi`; failure occurs while importing the unchanged ERP package API before tests run |

Focused tests cover coordinator/identity permissions, no automatic cycle
creation, immutable versions, optimistic expected-version conflict,
idempotency, exact anchor-plus-offset dates, exact-version snapshot lineage,
later-version isolation, retained Increment 1 preparation/review behavior,
update/delete guards, rehashed cross-binding tamper detection, deleted valid
chain-tail detection, under-lock inactive-user race failure, atomic rollback,
and the exact bounded 13-operation router set. The focused verifier additionally
guards retained logical-submit idempotency keys and template-switch revision
reset/submit checks in the planning UI.

## Exact changed files

New files:

- `ETOP-Blueprint/10_Architecture_Decision_Records/ADR-015_Local_Close_Planning_Template_Version_and_Cycle_Snapshot.md`
- `ETOP-Blueprint/12_Governance/Source_Records/SRC-008_Financial_Close_Planning_Templates_Source.md`
- `src/features/financial-close/ClosePlanningTemplates.tsx`
- `src/features/financial-close/ClosePlanningTemplates.css`
- `FINANCIAL_CLOSE_STEP6_INCREMENT2_HANDOFF.md`

Existing shared/governance hotspots changed:

- `CHANGELOG.md`
- `INTEGRATION_MANIFEST.md`
- `ETOP-Blueprint/CHANGELOG.md`
- `ETOP-Blueprint/PACKAGE_INDEX.md`
- `ETOP-Blueprint/04_Capabilities/CAP-FC-001_Financial_Close_and_Controller_Intelligence.md`
- `ETOP-Blueprint/09_Decision_Models/DEC-FC-001_Close_Control_Evidence_Readiness.md`
- `ETOP-Blueprint/12_Governance/BLUEPRINT_TRACEABILITY_MATRIX.csv`
- `ETOP-Blueprint/12_Governance/BLUEPRINT_TRACEABILITY_MATRIX.md`
- `backend/modules/financial_close/schemas.py`
- `backend/modules/financial_close/repository.py`
- `backend/modules/financial_close/service.py`
- `backend/modules/financial_close/api.py`
- `backend/test_financial_close_readiness.py`
- `src/features/financial-close/types.ts`
- `src/features/financial-close/api.ts`
- `src/features/financial-close/FinancialCloseWorkspace.tsx`
- `verification/verify-financial-close-readiness.mjs`

No shared App/main router-registration file, Workflow Foundation source,
installer, package script, ERP module, Accounts Payable module, runtime
database, generated `dist` output, or other workstream file belongs in this
increment's integration set.

## Integration notes for shared hotspots

- Merge the new Integration Manifest overlay above Increment 1; retain any
  overlays added by parallel workstreams.
- Append only this workstream's eleven CSV trace rows and corresponding
  Markdown migration/bullet content; recalculate the final combined matrix row
  count/hash after all parallel trace rows are merged.
- Preserve parallel changelog and Package Index additions while inserting the
  Step 6 Increment 2 entries.
- Financial Close backend/frontend/test files were isolated from the AP OCR and
  AP spend-intelligence workstreams and can be taken as complete-file changes
  unless parent integration has independently edited those same paths.
- Do not copy `backend/data/workbench.db`, any other `.db`, `dist/`,
  `__pycache__/`, or test-generated operational data.

## Assumptions

- The existing `workflow_coordinator` permission is reused strictly for local
  planning configuration; it confers no accounting or financial authority.
- Planning offsets are integer calendar days, technically bounded to ±3,660;
  each version is non-empty and limited to 100 controls.
- The operator chooses the appropriate exact version and supplies unverified
  entity/period/calendar context for every cycle.
- Default identities are snapshots from version authorship and are revalidated
  as active/distinct at instantiation; ETOP does not silently substitute users.
- Direct Increment 1 cycle/control creation remains supported for compatibility.
- Recurrence is not implemented. Any future recurrence proposal requires new
  governance and may calculate candidate dates only; it cannot auto-create
  cycles/tasks or notify users under this contract.

## Blockers

Implementation blocker: none. One retained regression gate is environment
blocked: `test_erp_evidence_gateway` cannot import the unchanged ERP package
because this workstream's Python runtime does not include `fastapi`; no ERP test
body ran and this increment changes no ERP file. Final parent integration still
needs to merge shared governance hotspots with the two parallel AP workstreams,
run that retained test in the normal backend environment, and recalculate
combined trace/package hashes without taking any runtime database or generated
output.
