# Document Intelligence — Current Local Foundation

## Capabilities

- PDF upload and validation
- Local file storage
- Exact source SHA-256 and exact-byte duplicate evidence
- SQLite job tracking
- Native PDF text extraction with PyMuPDF
- Targeted local Tesseract OCR for vendor-invoice pages with insufficient
  native text
- Rule-based document classification
- Parser registry
- Specialized PNC Lockbox processing and manual review workspace,
  including ERP-and-manually-linked enterprise customer allocation
  across accounts and a Misc G/L write-off entry — see
  `lockbox_review/README.md`
- Deterministic vendor-invoice parser with field source/page/location,
  ambiguity, actual OCR confidence, and explicit validation evidence
- Structured JSON results
- Latest-success result compatibility plus append-only successful/failed
  processing-run retrieval
- Processing-run-bound review/correction history with stale-write conflict
- Paginated vendor-invoice dataset retrieval with an exact total
- Local processing/review serialization and async request-loop offload

## Endpoints

- `GET /api/v1/documents/health`
- `GET /api/v1/documents/parsers`
- `POST /api/v1/documents/upload`
- `POST /api/v1/documents/vendor-invoices/upload`
- `POST /api/v1/documents/jobs/{job_id}/process`
- `GET /api/v1/documents/jobs/{job_id}`
- `GET /api/v1/documents/jobs/{job_id}/result`
- `GET /api/v1/documents/jobs/{job_id}/runs`
- `GET /api/v1/documents/jobs/{job_id}/runs/{processing_run_id}`
- `GET /api/v1/documents/jobs/{job_id}/review`
- `PUT /api/v1/documents/jobs/{job_id}/review`
- `GET /api/v1/documents/vendor-invoices/jobs`
- `GET /api/v1/documents/jobs`

List responses include `total`, `limit`, and `offset`. Public job payloads omit
the repository's internal `stored_path`; clients use `stored_file_name` and the
registered `/jobs/{job_id}/file` route.

## Vendor-invoice boundary

The AP-facing intake accepts readable, non-encrypted PDFs up to 50 MB. It
preserves the original and hash, uses native text first, and invokes only the
configured local Tesseract runtime for pages marked `requires_ocr`. Native
deterministic rules have no numeric confidence unless the source engine
actually supplied one.

Technical resource guards reject PDFs over 1000 pages and bound targeted OCR to
25 pages, 30 seconds per OCR call, 120 seconds per document, 10,000 rendered
pixels per dimension, and 20,000,000 rendered pixels per page. Skipped,
timed-out, or oversized-raster pages remain explicit review evidence.

Every extraction remains review evidence. It cannot approve an invoice,
authorize payment, post, write to ERP, or call an external AI service. A new
successful run resets current extraction review to pending and preserves prior
review/corrections in history. A failed reprocess leaves the last successful
current result available, and every retry attempt appends an immutable run.
Every review write requires `expected_processing_run_id`.

The current routes are a localhost-only proof-of-concept boundary. Managed file
reads are contained under the configured upload root. Authenticated document
access roles, enterprise retention, and multi-user policy remain deferred.
