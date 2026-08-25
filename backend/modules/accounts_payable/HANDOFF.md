# Accounts Payable Increment 1 Backend Handoff

## Baseline

- Branch: `ap-intelligence-backend`
- Required baseline commit: `d37d3dd0ebd7c6ab787946e6a2bd76a0273408fc`
- Change type: additive module-local backend foundation

## Completed workflow

`saved completed vendor-invoice job/result → explicit sync → source-grounded
normalization → immutable evidence revision → deterministic exceptions and
duplicate candidates → overview/list/detail queries`

No Lockbox file or behavior was changed.

## Shared-file integration request

`backend/main.py` only:

```python
from modules.accounts_payable.manifest import manifest as accounts_payable_manifest
```

and after the other module router registrations:

```python
app.include_router(accounts_payable_router)
```

Do not add another prefix. Do not change `backend/data/database.py`; the module
initializes its own additive tables lazily through the existing shared local
connection factory.

## Source mapping assumptions

- One saved Document Intelligence record becomes one AP invoice object.
- A result with a nonempty structured `records` array creates one stable AP
  object per record index.
- A generic/empty-record result creates one document-level AP object.
- `doc_results.job_id` is the existing result primary key and is exposed as
  `document_result_id`.
- Document review corrections take precedence over structured extraction.
- Saved text candidates are permitted only for a single document-level record,
  are anchored/labeled inference, and always require review.
- `doc_jobs.confidence` is classification confidence, not OCR confidence.

## Open source/governance mappings

- Canonical ERP vendor identity and vendor-master aliases.
- ERP AP open-item/payment sources and status semantics.
- Purchase-order, receipt, item-price, tax, freight, and GL sources.
- Approval identity, authority matrix, workflow, SLA, and escalation rules.
- Approved OCR review/straight-through thresholds.
- Retention, backup, multi-user conflict, and shared PSS-008 audit service.
- Policy for a source job later reclassified away from `vendor_invoice` or a
  structured result whose record count is reduced. Increment 1 preserves prior
  local evidence and does not destructively delete it.

## Verification

Focused tests cover source priority, unavailable facts, deterministic saved-text
candidates, provisional OCR review, exact duplicate rules, contradictory
corroboration, exception mapping, overview disclosure, query/filter/pagination,
multi-record identity, idempotent sync, immutable revision reconstruction,
append-only triggers, missing result handling, source failure, and Windows-safe
SQLite cleanup.
