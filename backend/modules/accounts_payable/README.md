# Accounts Payable Intelligence — Increments 1–2 Backend

This module creates a durable, local, read-only Accounts Payable evidence
projection from **saved** Document Intelligence jobs and results whose
document type is `vendor_invoice` and whose job status is `completed`.

It does not open PDFs, invoke a parser, rerun OCR, query or write ERP, approve
an invoice, schedule a payment, post a transaction, export data, call AI, or
transfer evidence externally.

Increment 2 adds immutable approval-review and payment-preparation readiness
cases. These records evaluate available evidence and operator-supplied role
separation only; they never approve an invoice or authorize payment.

## API contract

The module-local router owns these routes:

- `POST /api/v1/accounts-payable/sync`
- `POST /api/v1/accounts-payable/sync/document-jobs/{job_id}`
- `GET /api/v1/accounts-payable/overview`
- `GET /api/v1/accounts-payable/invoices`
- `GET /api/v1/accounts-payable/invoices/{ap_invoice_id}`
- `POST /api/v1/accounts-payable/invoices/{ap_invoice_id}/control-cases`
- `GET /api/v1/accounts-payable/control-cases`
- `GET /api/v1/accounts-payable/control-cases/{control_case_id}`
- `POST /api/v1/accounts-payable/control-cases/{control_case_id}/reviews`

Invoice list queries support:

- `query` — vendor number/name, invoice number, PO, source job, or file name;
- `status` — `review_required`, `evidence_available`, or the virtual
  `ocr_review` filter;
- `exception` and `duplicate` optional booleans;
- `exception_code` for one deterministic exception code;
- `limit`/`offset`; and
- governed sort fields and direction.

Every response includes a versioned contract plus `source_coverage`,
`governance`, and `deferred_capabilities`. Unknown facts are `null` and
unavailable; they are never converted to zero.

## Source order and authority

Field candidates are considered in this order:

1. Document Intelligence review `corrected_fields`;
2. structured saved parser field evidence/fields/records; and
3. explicitly labeled candidates derived by deterministic anchored rules from
   the already-saved `extraction.full_text`.

The registered deterministic vendor-invoice parser now provides source-
grounded field evidence. The third path remains only as compatibility for
legacy saved generic results; it never reads the PDF and never runs OCR. Every
value from that path is labeled
`analytical_inference`, carries rule version `ap-source-text-candidate.v1`, and
forces professional review.

An `approved` Document Intelligence review means only that document extraction
was reviewed. It is never represented as AP invoice approval, posting
authority, or payment authorization.

For versioned results, review/correction evidence is consumed only when its
`processing_run_id` matches the current result. A review from a prior run is
retained as history, ignored for current fields, and surfaced as pending review.

Classifier confidence remains separate from OCR confidence. Only an explicit
saved OCR-confidence field populates `ocr_confidence`. The 90% low-OCR review
threshold is explicitly `provisional`, traces to the currently observed
Document Intelligence review UI, and grants no straight-through authority.

## Persistence and reconstruction

The module initializes these additive tables in ETOP's local `workbench.db`:

- `ap_invoices` — current AP evidence projection;
- `ap_invoice_revisions` — immutable source-evidence snapshots;
- `ap_invoice_events` — immutable source/import timeline; and
- `ap_duplicate_candidates` — current deterministic duplicate-pair evidence.

Every normalized source snapshot has canonical JSON SHA-256. A changed saved
result or correction appends a new immutable revision and refresh event before
the current projection advances. Repeated identical sync is a database no-op:
no update, revision, event, or duplicate rewrite occurs.

The module does not duplicate preserved PDF text in AP storage. It retains
normalized evidence, field source paths, parser/classifier identities,
warnings, exceptions, timestamps, and the source-evidence hash. The original
text and file remain owned by Document Intelligence.

For AP Vendor Invoice Capture, `POST
/api/v1/accounts-payable/sync/document-jobs/{job_id}` imports only the exact
selected Document Intelligence job after its review is approved and bound to
the current processing run. It never expands into the legacy all-eligible-job
sync. Repeated identical evidence is idempotent. The operation remains
source-only: it creates no ERP invoice and performs no ERP write.

## Exceptions and duplicate rule

Increment 1 deterministically identifies:

- missing vendor identity, invoice number, invoice date, due date, or total;
- invalid source-present values that cannot be normalized;
- due date before invoice date;
- exact-cent total reconciliation mismatch when subtotal, tax, freight,
  discount, and total are all present;
- explicit saved amount, PO, receiving, tax, price, or freight mismatch facts;
- provisional low OCR confidence; and
- source-text candidates requiring review.

Duplicate Detection v1 requires exact normalized vendor identity plus exact
normalized invoice number. When both records provide amount or invoice date,
those values must also match; contradictory pairs are excluded. Missing
corroborators remain visible as `unavailable`. No score is invented, and the
candidate has review-only effect.

## Metrics boundary

The overview can report local import, exception, duplicate, and explicit OCR
coverage metrics. `extracted_invoice_total` is deliberately `partial`: it is a
sum of source-present document totals, not current AP balance.

Current balance, due/past-due amounts, seven-day cash need, discount
eligibility, payment status, and approval time are `unavailable` until their
governed ERP/workflow sources are connected. PO/receiving match, vendor master,
GL coding, payment, posting, export, AI recommendations, and image similarity
remain deferred.

## Control-readiness boundary

Cases retain the exact invoice source revision/hash and a canonical case
evidence hash. SQLite triggers block case/review update and delete. A later
invoice revision makes a previously ready case display `not_ready`; history is
not overwritten.

Available gates cover required document fields, deterministic exceptions,
duplicate candidates, evidence currency, requester/reviewer separation, and—for
payment preparation—reviewer/preparer separation. ERP vendor master, AP open
item/payment state, authenticated approval authority, payment execution, and
posting remain unavailable.

Only the immutable assigned-reviewer text may append a disposition, but that
operator-supplied match does not authenticate identity or prove authority.
Every case reports `can_enter_governed_approval: false` and
`can_authorize_payment: false`; every review has approval/payment effect `none`.

## Focused verification

From the project root:

```powershell
$env:PYTHONPATH = "backend"
python -m unittest -v backend.test_accounts_payable_foundation
```

The tests use synthetic fixtures only and explicitly close every SQLite
connection so temporary databases are removable on Windows.

## Shared integration required

The integration owner should make only these two additions to
`backend/main.py`:

```python
from modules.accounts_payable.manifest import manifest as accounts_payable_manifest
```

```python
app.include_router(accounts_payable_router)
```

The router already owns `/api/v1/accounts-payable`; do not add a second prefix.
Schema initialization is lazy and idempotent, so no shared database startup
edit is required.

## Blueprint alignment

The implementation follows ERM-006 Document Reality, ERM-003 Financial
Reality, OBJ-004 Document, ARCH-003 Enterprise Object Standard, ARCH-010
Architecture Boundary Rules, PSS-007 Document Intelligence Service, and
PSS-008 Audit and Provenance Service, DEC-AP-001, and ADR-006. It is a local
proof-of-concept foundation, not a claim that the complete shared Object, Decision, Workflow,
or tamper-aware Audit services are finished.
