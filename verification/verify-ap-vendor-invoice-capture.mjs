import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import ts from 'typescript'

const root = process.cwd()
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8')

const paths = {
  service: 'backend/modules/document_intelligence/service.py',
  settings: 'backend/modules/document_intelligence/settings.py',
  repository: 'backend/modules/document_intelligence/repository.py',
  router: 'backend/modules/document_intelligence/router.py',
  schemas: 'backend/modules/document_intelligence/schemas.py',
  reviewSchemas: 'backend/modules/document_intelligence/review_schemas.py',
  reviewStore: 'backend/modules/document_intelligence/review_store.py',
  ocr: 'backend/modules/document_intelligence/ocr_engine.py',
  extractor: 'backend/modules/document_intelligence/extractors/vendor_invoice.py',
  parser: 'backend/modules/document_intelligence/parsers/vendor_invoice.py',
  registry: 'backend/modules/document_intelligence/parsers/registry.py',
  apSource: 'backend/modules/accounts_payable/source.py',
  apService: 'backend/modules/accounts_payable/service.py',
  apRouter: 'backend/modules/accounts_payable/api.py',
  apExtraction: 'backend/modules/accounts_payable/extraction.py',
  capture: 'src/features/accounts-payable/APVendorInvoiceCapture.tsx',
  workspace: 'src/features/accounts-payable/AccountsPayableWorkspace.tsx',
  api: 'src/features/accounts-payable/api.ts',
  types: 'src/features/accounts-payable/types.ts',
  styles: 'src/features/accounts-payable/AccountsPayableWorkspace.css',
  documentApi: 'src/modules/document-intelligence/api.ts',
  documentTypes: 'src/modules/document-intelligence/types.ts',
  documentViewer: 'src/modules/document-intelligence/components/DocumentViewer.tsx',
  documentResultView: 'src/modules/document-intelligence/components/DocumentResultView.tsx',
  aiStudio: 'src/modules/document-intelligence/components/AIStudio.tsx',
  tests: 'backend/test_vendor_invoice_capture.py',
  reviewUnavailableTests: 'backend/test_document_review_unavailable.py',
  apFoundationTests: 'backend/test_accounts_payable_foundation.py',
  lockboxTests: 'backend/test_pnc_lockbox_parser.py',
  sourceRecord: 'ETOP-Blueprint/12_Governance/Source_Records/SRC-009_AP_Vendor_Invoice_Capture_OCR_Source.md',
  correctionSource: 'ETOP-Blueprint/12_Governance/Source_Records/SRC-011_AP_Vendor_Invoice_Coordinate_Extraction_Correction.md',
  decision: 'ETOP-Blueprint/10_Architecture_Decision_Records/ADR-016_AP_Vendor_Invoice_Capture_and_OCR_Evidence.md',
  capability: 'ETOP-Blueprint/04_Capabilities/CAP-AP-001_Accounts_Payable_Invoice_Intelligence.md',
  pss007: 'ETOP-Blueprint/06_Platform_Service_Standards/PSS-007_Document_Intelligence_Service.md',
  pss008: 'ETOP-Blueprint/06_Platform_Service_Standards/PSS-008_Audit_and_Provenance_Service.md',
  matrixCsv: 'ETOP-Blueprint/12_Governance/BLUEPRINT_TRACEABILITY_MATRIX.csv',
  matrixMd: 'ETOP-Blueprint/12_Governance/BLUEPRINT_TRACEABILITY_MATRIX.md',
  r2Handoff: 'AP_INCREMENT5_R2_COORDINATE_EXTRACTION_HANDOFF.md',
}

for (const relativePath of Object.values(paths)) {
  assert.ok(fs.existsSync(path.join(root, relativePath)), `Missing required file: ${relativePath}`)
}

for (const key of ['capture', 'workspace', 'api', 'types', 'documentApi', 'documentTypes', 'documentViewer', 'documentResultView', 'aiStudio']) {
  const relativePath = paths[key]
  const result = ts.transpileModule(read(relativePath), {
    compilerOptions: {
      jsx: ts.JsxEmit.ReactJSX,
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
    reportDiagnostics: true,
    fileName: relativePath,
  })
  assert.equal(
    result.diagnostics?.length ?? 0,
    0,
    `${relativePath} has TypeScript syntax diagnostics`,
  )
}

const service = read(paths.service)
const settings = read(paths.settings)
const repository = read(paths.repository)
const router = read(paths.router)
const reviewSchemas = read(paths.reviewSchemas)
const reviewStore = read(paths.reviewStore)
const ocr = read(paths.ocr)
const extractor = read(paths.extractor)
const parser = read(paths.parser)
const registry = read(paths.registry)
const apSource = read(paths.apSource)
const apService = read(paths.apService)
const apRouter = read(paths.apRouter)
const apExtraction = read(paths.apExtraction)
const capture = read(paths.capture)
const workspace = read(paths.workspace)
const api = read(paths.api)
const types = read(paths.types)
const styles = read(paths.styles)
const documentApi = read(paths.documentApi)
const documentTypes = read(paths.documentTypes)
const documentViewer = read(paths.documentViewer)
const documentResultView = read(paths.documentResultView)
const aiStudio = read(paths.aiStudio)
const tests = read(paths.tests)
const reviewUnavailableTests = read(paths.reviewUnavailableTests)
const apFoundationTests = read(paths.apFoundationTests)

// One existing PSS-007 owner: no AP-owned original/document store.
assert.match(router, /"\/vendor-invoices\/upload"/)
assert.match(router, /"\/vendor-invoices\/jobs"/)
assert.match(router, /"\/jobs\/\{job_id\}\/runs"/)
assert.match(router, /"\/jobs\/\{job_id\}\/runs\/\{processing_run_id\}"/)
assert.match(router, /"\/jobs\/\{job_id\}\/result"/)
assert.match(router, /"\/jobs\/\{job_id\}\/file"/)
assert.match(service, /create_vendor_invoice_intake/)
assert.match(service, /settings\.upload_root/)
assert.match(service, /hashlib\.sha256/)
assert.match(service, /first_bytes\.startswith\(b"%PDF"\)/)
assert.match(service, /settings\.max_upload_bytes/)
assert.match(service, /settings\.max_pdf_pages/)
assert.match(service, /asyncio\.to_thread\(process_job/)
assert.match(service, /_PROCESSING_REVIEW_LOCK/)
assert.match(service, /_managed_pdf_path/)
assert.match(service, /could not be opened \(\{type\(exc\)\.__name__\}\)/)
assert.match(service, /intake_document_type="vendor_invoice"/)
assert.doesNotMatch(read(paths.schemas), /\bstored_path\s*:/)
assert.doesNotMatch(documentTypes, /\bstored_path\s*:/)
assert.doesNotMatch(types, /\bstored_path\s*:/)
assert.doesNotMatch(documentResultView, /job\.stored_path/)
assert.match(documentResultView, /job\.stored_file_name/)

// Native-first, page-targeted local OCR with actual engine evidence.
assert.match(extractor, /if requires_ocr:/)
assert.match(extractor, /_ocr_lines\([\s\S]*timeout_seconds=page_timeout/)
assert.match(extractor, /ocr_attempted_pages/)
assert.match(extractor, /ocr_failed_pages/)
assert.match(extractor, /ocr_engine_version/)
assert.match(extractor, /ocr_skipped_pages/)
assert.match(extractor, /max_ocr_pages/)
assert.match(extractor, /ocr_total_timeout_seconds/)
assert.match(settings, /max_ocr_render_dimension_pixels/)
assert.match(settings, /max_ocr_render_pixels/)
assert.match(ocr, /OCR raster safety limit exceeded before page rendering/)
assert.match(ocr, /timeout=timeout_seconds/)
assert.match(ocr, /def tesseract_available/)
assert.doesNotMatch(service, /tesseract_identity/)
assert.match(extractor, /source_method": "native_pdf_text"/)
assert.match(extractor, /source_method": "local_tesseract_ocr"/)
assert.match(extractor, /vendor-invoice-extraction\.v2/)
assert.match(extractor, /fragment_id/)
assert.match(extractor, /page_width/)
assert.match(extractor, /native_text_pages/)
assert.match(extractor, /text_source_summary/)
assert.match(ocr, /shutil\.which\("tesseract"\)/)
assert.match(ocr, /subprocess\.run/)
assert.match(ocr, /import pytesseract/)
assert.doesNotMatch(service, /openai|anthropic|azure\.ai|google\.cloud/i)

// Registered deterministic parser, provenance, ambiguity, and no fake confidence.
assert.match(registry, /parser_registry\.register\(VendorInvoiceParser\(\)\)/)
assert.match(parser, /document_type = "vendor_invoice"/)
assert.match(parser, /VENDOR_INVOICE_FIELD_RULE_VERSION/)
assert.match(parser, /vendor-invoice-field-rules\.v2/)
assert.match(parser, /parser_version = "2\.0\.0"/)
assert.match(parser, /LABEL_PATTERNS/)
assert.match(parser, /same_row_right/)
assert.match(parser, /below_label/)
assert.match(parser, /remittance_issuer_candidate/)
assert.match(parser, /evidence_fragments/)
assert.match(parser, /observation_count/)
assert.match(parser, /present_without_value/)
assert.match(parser, /shipped/)
assert.match(parser, /Customer|customer/)
assert.match(parser, /field_summary/)
assert.match(parser, /key_field_readiness/)
assert.match(parser, /ambiguous_fields/)
assert.match(parser, /"location": location/)
assert.match(parser, /"authority": authority/)
assert.match(parser, /def _line_confidence[\s\S]*if value is None(?: or [^:]+)?:[\s\S]*return None/)
assert.doesNotMatch(parser, /\b0\.98\b|\b0\.55\b|\b0\.45\b/)
assert.match(settings, /document-intelligence-processor\.v3/)
assert.match(settings, /module_version: str = "0\.5\.0"/)
assert.match(service, /_vendor_invoice_review_message/)
assert.match(service, /field_summary/)
assert.match(service, /OCR was not needed/)

// Append-only runs, latest-success compatibility, and retained current result.
assert.match(repository, /CREATE TABLE IF NOT EXISTS doc_processing_runs/)
assert.match(repository, /doc_processing_runs_no_update/)
assert.match(repository, /doc_processing_runs_no_delete/)
assert.match(repository, /processing_run_number/)
assert.match(repository, /ON CONFLICT\(job_id\) DO UPDATE SET/)
assert.match(service, /make_current=True/)
assert.match(service, /make_current=False/)
assert.match(service, /status="completed" if retained_current else "failed"/)
assert.match(service, /successful current result remains available/)

// Run-bound review, invalidation, optimistic concurrency, and AP consumption.
assert.match(reviewSchemas, /expected_processing_run_id/)
assert.match(reviewSchemas, /SUPPORTED_UNAVAILABLE_FIELDS/)
assert.match(reviewSchemas, /unavailable_fields: list\[str\] \| None/)
assert.doesNotMatch(reviewSchemas, /expected_processing_run_id:\s*str\s*\|\s*None/)
assert.match(reviewStore, /processing_run_id TEXT/)
assert.match(reviewStore, /begin_review_for_processing_run/)
assert.match(reviewStore, /status="pending"/)
assert.match(reviewStore, /corrected_fields=\{\}/)
assert.match(reviewStore, /__etop_document_review_unavailable_fields_v1__/)
assert.match(reviewStore, /def pack_review_fields/)
assert.match(reviewStore, /"unavailable_fields": unavailable_fields/)
assert.match(reviewStore, /from contextlib import closing/)
assert.match(reviewStore, /with closing\(connect\(\)\) as connection, connection:/)
assert.doesNotMatch(reviewStore, /with connect\(\) as connection:/)
assert.match(repository, /from contextlib import closing/)
assert.match(repository, /with closing\(sqlite3\.connect\(settings\.database_path\)\) as connection, connection:/)
assert.doesNotMatch(repository, /with sqlite3\.connect\(settings\.database_path\) as connection:/)
assert.match(service, /expected_processing_run_id != current_processing_run_id/)
assert.match(service, /status_code=409/)
assert.match(router, /pack_review_fields\(/)
assert.match(router, /payload\.unavailable_fields/)
assert.match(documentViewer, /expected_processing_run_id:[\s\S]*result\.processing_run_id/)
assert.match(documentTypes, /expected_processing_run_id: string/)
assert.match(service, /begin_review_for_processing_run\(job_id, run\["processing_run_id"\]\)/)
assert.match(apSource, /review_matches_current_run/)
assert.match(apSource, /document_extraction_review_pending/)
assert.match(apSource, /processing_run_id/)
assert.match(apSource, /ocr_profile_version/)
assert.match(apExtraction, /field_evidence/)
assert.match(apExtraction, /ap-review-unavailable\.v1/)
assert.match(apExtraction, /human_reviewed_unavailable/)
assert.match(apSource, /unavailable_fields=unavailable_fields/)
assert.match(apSource, /"unavailable_fields_used": bool\(unavailable_fields\)/)

// Usable AP-facing workflow and honest states.
assert.match(workspace, /Vendor Invoice Dataset & OCR/)
assert.match(workspace, /APVendorInvoiceCapture/)
assert.match(capture, /Upload vendor invoice/)
assert.match(capture, /Loading vendor invoice dataset/)
assert.match(capture, /No vendor invoice documents are registered/)
assert.match(capture, /Retry processing/)
assert.match(capture, /Append reprocess run/)
assert.match(capture, /Field-level provenance/)
assert.match(capture, /Review or correct extraction/)
assert.match(capture, /Processing run history/)
assert.match(capture, /Sync reviewed extraction/)
assert.match(capture, /Reopen in Invoice Intelligence/)
assert.match(capture, /review\.review\.processing_run_id === result\.processing_run_id/)
assert.match(capture, /expected_processing_run_id: result\.processing_run_id/)
assert.match(capture, /detailGeneration/)
assert.match(capture, /selectedJobIdRef\.current !== job\.job_id/)
assert.match(capture, /Load older invoices/)
assert.match(capture, /jobs\.length < datasetTotal/)
assert.match(capture, /never approves an invoice, authorizes payment/)
assert.match(capture, /No external AI service receives the document/)
assert.match(capture, /Native PDF text/)
assert.match(capture, /OCR not needed/)
assert.match(capture, /Field coverage/)
assert.match(capture, /Key fields recognized/)
assert.match(capture, /pairing_method/)
assert.match(capture, /corroborating observations retained/)
assert.match(capture, /Mark unavailable/)
assert.match(capture, /Restore extracted value/)
assert.match(capture, /unavailable_fields:/)
assert.match(capture, /distinctEvidenceCandidates/)
assert.match(capture, /Review \{candidates\.length\} distinct retained candidate/)
assert.match(capture, /candidate\.location/)
assert.match(capture, /candidate\.source/)
assert.match(capture, /confidence\(candidate\.confidence\)/)
assert.doesNotMatch(capture, /candidate\.raw_line|extraction\.full_text/)
assert.doesNotMatch(capture, /straight.?through|auto.?approv/i)
assert.match(api, /documents\/vendor-invoices\/upload/)
assert.match(api, /documents\/vendor-invoices\/jobs/)
assert.match(api, /offset=\$\{encodeURIComponent\(offset\)\}/)
assert.match(api, /accounts-payable\/sync\/document-jobs/)
assert.match(api, /expected_processing_run_id/)
assert.match(types, /processing_run_id: string \| null/)
assert.match(types, /text_source_summary/)
assert.match(types, /evidence_fragments/)
assert.match(types, /observation_count/)
assert.match(types, /field_summary/)
assert.match(types, /APVendorInvoiceEvidenceCandidate/)
assert.match(types, /unavailable_fields: string\[\]/)
assert.match(styles, /\.ap-vendor-capture/)
assert.match(styles, /\.ap-capture-layout/)
assert.match(styles, /@media \(max-width: 820px\)/)
assert.match(apRouter, /"\/sync\/document-jobs\/\{job_id\}"/)
assert.match(apService, /def sync_document_job/)
assert.match(apService, /get_vendor_invoice_evidence\(job_id\)/)
assert.match(apService, /review\.get\("processing_run_id"\) != current_run_id/)
assert.match(documentApi, /getVendorInvoiceJobs\([\s\S]*offset = 0/)
assert.match(aiStudio, /Promise\.allSettled/)
assert.match(aiStudio, /vendorDatasetAvailable/)

// Explicitly retain the specialized Lockbox branch.
assert.match(router, /"\/jobs\/\{job_id\}\/lockbox\/process"/)
assert.match(router, /process_lockbox\(job_id, path\)/)
assert.match(read(paths.lockboxTests), /test_governed_embedded_row_avoids_unnecessary_ocr/)
assert.match(read(paths.lockboxTests), /test_invalid_embedded_row_uses_psm6_then_psm11/)

// Focused executable regressions cover every critical state transition.
for (const requiredTest of [
  'test_upload_preserves_exact_pdf_bytes_and_sha256',
  'test_native_only_document_never_invokes_ocr',
  'test_ocr_runs_only_for_pages_native_extraction_marks_insufficient',
  'test_vendor_parser_is_registered_and_ambiguity_is_preserved',
  'test_prior_runs_remain_retrievable_when_current_advances',
  'test_failed_reprocess_keeps_last_successful_current_result',
  'test_new_run_resets_current_review_and_preserves_prior_history',
  'test_review_and_repository_connections_close_deterministically',
  'test_stale_review_put_is_rejected_with_conflict',
  'test_ap_projection_does_not_apply_review_from_prior_run',
  'test_review_request_requires_expected_processing_run_id',
  'test_invalid_retry_appends_failed_run_instead_of_short_circuiting',
  'test_targeted_ocr_page_limit_is_explicit_review_evidence',
  'test_ocr_identity_work_cannot_overrun_document_time_limit',
  'test_oversized_ocr_raster_is_rejected_before_pixmap_allocation',
  'test_vendor_intake_offloads_processing_from_async_event_loop',
  'test_vendor_jobs_are_counted_and_retrievable_across_offsets',
  'test_exact_job_sync_uses_only_reviewed_current_job',
  'test_exact_job_sync_rejects_prior_run_review',
  'test_public_job_response_does_not_disclose_stored_path',
  'test_pdf_validation_error_does_not_reflect_local_path',
  'test_fictional_coordinate_invoice_exercises_native_layout_pairing',
  'test_recipient_and_customer_sections_do_not_become_vendor_identity',
  'test_blank_purchase_order_does_not_steal_nearby_service_values',
  'test_corroborating_totals_collapse_but_conflicting_totals_fail_closed',
  'test_ocr_coordinate_pair_uses_value_confidence_and_retains_fragments',
  'test_malformed_bbox_falls_back_to_inline_labeled_parser',
  'test_service_quality_message_distinguishes_native_text_from_ocr',
]) {
  assert.match(tests, new RegExp(requiredTest))
}

for (const requiredTest of [
  'test_unknown_or_conflicting_unavailable_field_is_rejected',
  'test_save_reload_history_and_new_run_reset_without_migration',
]) {
  assert.match(reviewUnavailableTests, new RegExp(requiredTest))
}

for (const requiredTest of [
  'test_reviewer_unavailable_suppresses_machine_and_text_fallback',
  'test_prior_run_unavailable_does_not_suppress_current_machine_value',
]) {
  assert.match(apFoundationTests, new RegExp(requiredTest))
}

// Governance and bidirectional trace.
assert.match(read(paths.sourceRecord), /SRC-009/)
assert.match(read(paths.sourceRecord), /Vendor Invoice Dataset & OCR/)
assert.match(read(paths.correctionSource), /SRC-011/)
assert.match(read(paths.correctionSource), /Coordinate Extraction Correction/)
assert.match(read(paths.correctionSource), /marked unavailable/i)
assert.match(read(paths.decision), /ADR-016/)
assert.match(read(paths.decision), /Version:\*\* 0\.3\.0/)
assert.match(read(paths.decision), /failed reprocess never advances or removes the current result/i)
assert.match(read(paths.decision), /machine and source-text fallback/i)
assert.match(read(paths.capability), /Step 6 controlled extension — Vendor Invoice Dataset & OCR/)
assert.match(read(paths.pss007), /Step 6 AP Vendor Invoice Capture\/OCR mapping/)
assert.match(read(paths.pss008), /AP Vendor Invoice Capture\/OCR Mapping/)
assert.match(read(paths.matrixCsv), /"SRC-009"/)
assert.match(read(paths.matrixCsv), /"ADR-016"/)
assert.match(read(paths.matrixCsv), /"SRC-011"/)
assert.match(read(paths.matrixCsv), /test_document_review_unavailable\.py/)
assert.match(read(paths.matrixCsv), /verify-ap-vendor-invoice-capture\.mjs/)
assert.match(read(paths.matrixMd), /fifteen Step 6 AP Vendor Invoice Capture\/OCR links/)
assert.match(read(paths.matrixMd), /sixteen AP Increment 5 R2 links/)
assert.match(read(paths.matrixMd), /SRC-011\/ADR-016 v0\.3 payload \| 638/)
assert.match(read(paths.r2Handoff), /exact `R1Final` only/)
assert.match(read(paths.r2Handoff), /Append reprocess run/)

console.log(
  'AP Vendor Invoice Dataset & OCR R2 verification passed: governed PDF preservation/hash, native-first targeted local OCR, stable coordinate fragments, field-specific label/value pairing, remittance and recipient/customer semantics, reviewable candidate provenance, corroboration and ambiguity, actual-confidence evidence, truthful field readiness, reviewer unavailable suppression, append-only run/review boundaries, idempotent AP projection, retained Lockbox separation, and SRC-009/SRC-011/ADR-016 trace are present.',
)
