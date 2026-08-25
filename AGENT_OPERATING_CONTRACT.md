# ETOP Agent Operating Contract

Status: Active integration contract  
Owner: Josh Corbit, Founder and Chief Architect  
Applies to: Every agent, developer, and integration pass working on ETOP

ETOP is enterprise software that thinks with people—not instead of them. It is
an enterprise operating platform above systems of record, not a collection of
unrelated screens. Every change must improve a real business capability while
preserving explainability, human authority, and the integrity of existing
workflows.

## 1. Follow the ETOP Blueprint

Use `ETOP-Blueprint/` as the architectural baseline. Preserve the distinction
between facts, approved knowledge, professional judgment, analytical inference,
and AI hypotheses. Implementation evidence does not override an approved
Blueprint rule.

## 2. Begin from one identified baseline

Every assignment must identify its source ZIP version or Git commit. Record the
baseline in the handoff. Do not return a complete replacement project from an
unknown baseline.

## 3. Use one integration owner

Feature agents should make module-local changes and document any shared-shell
changes they require. The integration owner controls shared hotspots,
including:

- `src/App.tsx`
- `backend/main.py`
- platform registries and stores
- shared API clients and types
- navigation and module registration

## 4. Do not create parallel implementations

Search for an existing service, component, API, schema, or business rule before
adding one. Customer resolution, open-invoice retrieval, document storage,
recommendations, workflows, search, and audit history must become reusable
services rather than screen-specific copies.

## 5. No decorative functionality

A visible button, search box, recommendation, filter, report action, or
navigation item must work end to end. Do not use hardcoded customer numbers,
static risk lists, fake results, or inactive controls. Clearly label incomplete
functionality as unavailable.

## 6. Preserve state and evidence

Work must survive leaving and reopening a screen. Processed PDFs, OCR results,
reviews, customer matches, corrections, exports, recommendations, and training
examples must remain retrievable.

## 7. Use real and explainable business logic

Every risk score, recommendation, customer match, or automated action must
retain:

- supporting evidence;
- matched factors;
- confidence;
- warnings or ambiguity;
- rule or model version;
- human decision or override; and
- outcome, when known.

## 8. Keep AI local and controlled

Operational data, customer information, documents, embeddings, and AI
processing remain local. Deterministic rules and verified database
relationships come before AI inference. AI may assist and recommend; it must
not silently invent facts or approve financial actions.

## 9. Respect source authority

ERP data is read-only source data. ETOP may locally own reviews, workflows,
configurations, training corrections, recommendations, and audit records.
Current code is implementation evidence, not authority to contradict an
approved business rule.

## 10. Definition of done means demonstrated

Each completed change must include:

- the complete user workflow;
- a real API connection;
- loading, empty, validation, and failure behavior;
- persistence and reload verification;
- frontend build and lint results;
- relevant backend tests;
- regression checks on existing modules;
- a changed-file list;
- assumptions and unresolved questions; and
- simple verification instructions for Josh.

## 11. Protect the proof of concept

Avoid broad rewrites until equivalent behavior has been verified. Reorganize
incrementally and preserve compatibility throughout the transition.

## 12. Update the Blueprint trace

Material business, data, workflow, service-boundary, or architectural decisions
require an ADR or corresponding Blueprint update. Minor implementation details
do not require excessive documentation.

## Required proof-of-concept workflows

1. **Customer Intelligence:** Search the real customer base and open a connected
   customer workspace.
2. **Priority Review:** Open the review action and receive a ranked list of
   actual high-risk customers with reasons and recommended next actions.
3. **Lockbox:** Upload → Process → Reopen → Review → Resolve Customer → Match
   Open Invoices → Apply Recommendation → Export → Train.
4. **Reporting:** Create → Save → Run → Preview → Export → Schedule a report
   using validated read-only SQL.

## Decisions agents must not invent

- the approved definition, weighting, and tie-breaking rules for “high risk”;
- customer-match confidence thresholds and mandatory human-review points;
- lockbox balancing tolerances and any auto-approval authority;
- approval authority for corrections, overrides, cash application, and learned
  rules; and
- the exact demonstration that constitutes company proof-of-concept approval.

## Required handoff

Every agent must provide:

1. baseline identifier;
2. purpose and completed workflow;
3. changed-file list;
4. shared-file changes requested;
5. tests and results;
6. assumptions and open decisions; and
7. a patch or branch that can be integrated without replacing unrelated files.

Do not assume another agent knows what changed merely because the discussions
are in the same ChatGPT project. Every agent needs the same Blueprint release,
source baseline, operating contract, and current integration manifest.
