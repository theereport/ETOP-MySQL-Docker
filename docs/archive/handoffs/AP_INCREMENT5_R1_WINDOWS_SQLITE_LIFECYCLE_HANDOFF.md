# AP Increment 5 R1 Windows SQLite Lifecycle Handoff

## Baseline and purpose

- Predecessor: exact AP Increment 5 source from the sealed Step 6 I2 + AP5
  sequential release dated August 8, 2026.
- Trigger: Windows installed-source verification exposed open SQLite handles in
  the vendor-invoice review and processing repositories.
- Scope: deterministic database-connection closure and recovery-script state
  classification only. No AP, OCR, spend, close, ERP, or authority semantics
  change.

## Root cause corrected

Python's `sqlite3.Connection` context manager commits or rolls back a
transaction but does not close the connection. The original review store and
document repository relied on that context alone. Linux permitted removal of
the still-open temporary database, while Windows correctly returned
`WinError 32` during the next test setup.

R1 wraps each existing transaction context in deterministic connection
closure. It also closes the focused test's direct SQLite probe. The correction
retains transaction semantics on success and exception and releases the
operating-system handle immediately.

## Changed source paths

- `backend/modules/document_intelligence/review_store.py`
- `backend/modules/document_intelligence/repository.py`
- `backend/test_vendor_invoice_capture.py`
- `verification/verify-ap-vendor-invoice-capture.mjs`
- `AP_VENDOR_INVOICE_CAPTURE_OCR_HANDOFF.md`
- `CHANGELOG.md`
- `INTEGRATION_MANIFEST.md`
- `AP_INCREMENT5_R1_WINDOWS_SQLITE_LIFECYCLE_HANDOFF.md`

The separate recovery release also corrects the sequential PowerShell
final-state classifier, whose original implementation passed a parsed hash
table where a manifest pathname was required. That release wrapper change does
not alter ETOP application source.

## Validation contract

- Run the 27 focused vendor-invoice capture tests twice consecutively.
- Treat SQLite `ResourceWarning` as an error.
- Prove every tracked review/repository connection is explicitly closed.
- Prove the temporary review and repository database files can be removed
  immediately after use.
- Retain Lockbox, AP, spend, ERP Evidence, Financial Close, Workflow, OpenAPI,
  JavaScript, TypeScript, lint, build, package-integrity, state-preservation,
  idempotency, and rollback checks.

## Protected boundaries

No runtime database, upload, invoice PDF, OCR result, processing run, review,
AP projection, workflow/close evidence, credential, export, or ERP/GL state is
packaged, replaced, deleted, or reinterpreted. Extraction review still is not
invoice approval, coding acceptance, posting, payment authorization, or ERP
truth.
