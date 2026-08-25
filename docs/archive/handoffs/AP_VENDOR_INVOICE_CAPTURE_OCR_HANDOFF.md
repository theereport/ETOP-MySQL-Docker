# AP Vendor Invoice Capture/OCR Handoff

## Baseline and scope

- Baseline: exact accepted Step 6 Increment 1 source.
- Governance: SRC-009 and ADR-016; CAP-AP-001, PSS-007, PSS-008, trace matrix,
  manifest, and changelog updated.
- Bounded scope: AP Vendor Invoice Dataset & OCR only. Division/account vendor-
  spend questions are intentionally outside this workstream.
- Packaging: not performed. Runtime databases, uploads, OCR files, build output,
  and test artifacts are not deliverables.

## Completed user journey

`Accounts Payable → Vendor Invoice Dataset & OCR → upload governed PDF → exact
local preserve/hash → native extraction → targeted local Tesseract only where
required → registered vendor_invoice parser → inspect field evidence/ambiguity
→ save correction/review against exact run → idempotent AP evidence sync →
reopen in Invoice Intelligence`

Existing processed vendor invoices remain a retrievable dataset. Failed jobs
remain visible. Prior successful and failed processing runs remain queryable,
and paginated total/load-older navigation keeps jobs beyond the newest page
reachable.

## Backend result

### Existing Document Intelligence ownership retained

- No AP-owned document/original/OCR/parser store was introduced.
- `/api/v1/documents/vendor-invoices/upload` uses the existing upload root,
  job table, file endpoint, parser registry, review store, and result contract.
- Intake accepts supported PDF types only, requires `.pdf`, non-empty content,
  PDF signature, at most the configured 50 MB, and no more than 500 pages.
- Exact bytes and SHA-256 are saved. Exact-byte prior job identity is disclosed
  without collapsing or deleting the new job.
- Readable/non-encrypted/non-zero-page validation is explicit. Post-signature
  invalid PDFs remain preserved as failed jobs for review.
- Registered source reads are contained under the configured upload root.
  Public job responses omit the internal repository path and expose only the
  managed file name plus the registered file endpoint.

### Native-first targeted OCR and parser evidence

- Native PyMuPDF extraction runs first.
- Only pages already marked `requires_ocr` invoke local Tesseract.
- Processing runs outside the async request event loop. Targeted OCR is bounded
  to 25 pages, 30 seconds per call, 120 seconds per document, 10,000 rendered
  pixels per dimension, and 20,000,000 rendered pixels per page. Limit,
  timeout, and pre-raster rejection remain explicit failed/skipped page
  evidence.
- Tesseract version identity is deferred until a page actually requires OCR.
- The OCR wrapper now works with the optional `pytesseract` module or directly
  with a configured/local Tesseract executable; no external service exists.
- Page/line text, method, bbox, actual Tesseract confidence, engine/version,
  attempted/completed/failed pages, and page-local errors remain available.
- `vendor_invoice` is registered in the existing parser registry.
- Labeled invoice/vendor/date/PO/terms/amount/currency candidates retain raw
  source, page/location, rule, authority, and validation state.
- Multiple distinct values are retained as ambiguity and left unselected.
- Native deterministic matches and header issuer inference use confidence
  `None`; only actual OCR confidence is retained.

### Non-destructive processing and review

- `doc_processing_runs` is append-only with no-update/no-delete triggers.
- Existing legacy current results migrate once into a `legacy-unversioned`
  immutable run.
- `/jobs/{job_id}/result` remains the latest-success compatibility endpoint.
- `/jobs/{job_id}/runs` and run detail expose prior successful/failed evidence.
- Every retry attempt, including corrupt, encrypted, and over-limit validation
  failure, appends a failed run without advancing current result. When a
  prior successful result exists, job state remains `completed` with a visible
  latest-run failure message.
- Current review and review history now retain `processing_run_id`.
- A new successful run resets current review to pending and clears inherited
  current corrections while preserving prior history/corrections.
- Every review PUT caller sends required `expected_processing_run_id`; stale
  saves return 409. Processing, review compare-and-save, and exact-job AP sync
  share a local per-process serialization boundary.
- AP source corrections/status apply only when review and current run match.

## Frontend result

- Accounts Payable has a dedicated `Vendor Invoice Dataset & OCR` view.
- Working states include initial loading, empty dataset, upload/processing,
  invalid input, failed job, retry, dataset reload, result/run/review loading,
  field evidence, corrections, stale review warning, sync, and reopen.
- Dataset retrieval uses total/limit/offset with load-older navigation. Job and
  selection-generation guards prevent stale detail requests from replacing a
  newer user selection.
- Original PDF, SHA-256, job/classification state, parser/OCR provenance,
  validation messages, field source/confidence/location, ambiguity, and all run
  summaries are visible.
- “Extraction evidence reviewed” is explicitly not approval, coding acceptance,
  posting, or payment authorization.
- Sync is enabled only for an approved review bound to the displayed current
  run. It calls the exact selected-job endpoint, cannot import unrelated jobs,
  and remains evidence-only and idempotent.
- The older Document Intelligence AP summary no longer calls high classifier
  confidence “Ready.” AI Studio now shows the actual registered vendor-invoice
  evidence dataset/parser state rather than `PLANNED`; an AP dataset request
  failure degrades that row independently and does not suppress core training
  sessions/summary.

## API additions

- `POST /api/v1/documents/vendor-invoices/upload`
- `GET /api/v1/documents/vendor-invoices/jobs`
- `GET /api/v1/documents/jobs/{job_id}/runs`
- `GET /api/v1/documents/jobs/{job_id}/runs/{processing_run_id}`
- `POST /api/v1/accounts-payable/sync/document-jobs/{job_id}`

Existing upload/job/file/result/review routes and specialized Lockbox routes are
retained.

## Verification completed

- `python backend/test_vendor_invoice_capture.py` — original AP5: 26 passed;
  Windows SQLite Lifecycle R1: 27 passed twice consecutively with
  `ResourceWarning` treated as an error.
- `python -m unittest -v backend/test_pnc_lockbox_parser.py` — 25 passed.
- `PYTHONPATH=backend python -m unittest -v` for AP foundation, controls, vendor/
  cash, and exception operations — 25 passed.
- `node verification/verify-ap-vendor-invoice-capture.mjs` — passed.
- Focused ESLint for AP capture/workspace/API/types and Document Intelligence
  Document Viewer/Result View/AP Dashboard/AI Studio/API/types — passed.
- `npm run build` — passed; existing Vite chunk-size advisory remains.
- `python -m compileall -q backend/modules/document_intelligence
  backend/modules/accounts_payable` — passed.

## Shared-hotspot requests

None. The existing Accounts Payable and Document Intelligence routers were
already registered by the accepted baseline. No `main.py`, `App.tsx`, platform
registry, shared database, or installer edit is requested from integration.

## Open gaps and deferred work

- Evaluate representative vendor layouts and establish calibrated field
  accuracy; current deterministic rules are a bounded foundation.
- Approve additional image/email/office/package formats if required.
- Establish authenticated extraction-review roles and access policy.
- The present document API is explicitly a localhost-only proof-of-concept
  deployment boundary; authenticated document-access policy remains deferred.
- Establish retention, backup, legal hold, secure export, independent audit
  storage, and multi-machine synchronization.
- Govern authoritative ERP vendor/PO/receipt/GL/payable/payment mappings and
  codes separately.
- Define any future straight-through threshold, approval/payment authority, or
  ERP mutation only through separate source, Decision, Workflow, Automation,
  and security governance. None exists here.
