import { API_BASE, ApiError, requestJson } from '../../api/client'
import type {
  APErpLedgerRefreshResponse,
  APInvoiceDetailResponse,
  APInvoiceListResponse,
  APInvoiceQuery,
  APOverviewResponse,
  APSyncResponse,
  APVendorTermsReferenceListResponse,
  APVendorTermsReferenceUpsert,
  APGLCodingSuggestionsResponse,
  APWarehouseApprovalActionCreate,
  APWarehouseApprovalActionRecord,
  APWarehouseApprovalQueueResponse,
  APControlCaseDetail,
  APControlCaseListResponse,
  CreateAPControlCaseRequest,
  CreateAPControlReviewRequest,
  APVendorCashIntelligenceResponse,
  APCashScenario,
  APCashScenarioHistoryResponse,
  CreateAPCashScenarioRequest,
  APExceptionAction,
  APExceptionActionHistoryResponse,
  APExceptionOperationsResponse,
  CreateAPExceptionActionRequest,
  APERPEvidenceResponse,
  APERPInvoiceSearchResponse,
  APMappingReadinessResponse,
  APSpendQuestionResponse,
  APSpendReadinessResponse,
  APVendorInvoiceDocumentJob,
  APVendorInvoiceDatasetPage,
  APVendorInvoiceDocumentResult,
  APVendorInvoiceIntakeResponse,
  APVendorInvoiceProcessingRun,
  APVendorInvoiceReview,
} from './types'
import { buildAccountsPayableInvoiceQuery } from './query'

type JsonRecord = Record<string, unknown>

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function invalidContract(context: string, field: string): never {
  throw new Error(`Accounts Payable ${context} response is missing valid ${field} evidence.`)
}

function requireRecord(value: unknown, context: string, field: string): JsonRecord {
  return isRecord(value) ? value : invalidContract(context, field)
}

function requireString(value: unknown, context: string, field: string): string {
  return typeof value === 'string' ? value : invalidContract(context, field)
}

function requireArray(value: unknown, context: string, field: string): unknown[] {
  return Array.isArray(value) ? value : invalidContract(context, field)
}

function validateSourceCoverageAndDeferred(payload: JsonRecord, context: string): void {
  const coverage = requireArray(payload.source_coverage, context, 'source_coverage')
  coverage.forEach((value) => {
    const source = requireRecord(value, context, 'source coverage item')
    requireString(source.key, context, 'source coverage key')
    requireString(source.label, context, 'source coverage label')
    requireString(source.status, context, 'source coverage status')
    requireString(source.explanation, context, 'source coverage explanation')
  })
  const deferred = requireArray(payload.deferred_capabilities, context, 'deferred_capabilities')
  deferred.forEach((value) => {
    const capability = requireRecord(value, context, 'deferred capability')
    requireString(capability.key, context, 'deferred capability key')
    requireString(capability.label, context, 'deferred capability label')
    requireString(capability.status, context, 'deferred capability status')
    requireString(capability.reason, context, 'deferred capability reason')
    requireArray(capability.missing_sources, context, 'deferred capability missing_sources')
  })
}

// Used by endpoints backed by the full APGovernance contract (overview,
// invoices, sync, control cases). Vendor/cash and exception-operations
// responses carry their own narrower, bespoke governance shapes
// (APVendorCashGovernance / APExceptionOperationsGovernance on the
// backend) and are validated separately - they were never meant to
// satisfy this fuller contract.
function validateSharedEnvelope(payload: JsonRecord, context: string): void {
  requireString(payload.contract_version, context, 'contract_version')
  validateSourceCoverageAndDeferred(payload, context)
  const governance = requireRecord(payload.governance, context, 'governance')
  requireString(governance.erp_access, context, 'governance.erp_access')
  requireString(governance.approval_effect, context, 'governance.approval_effect')
  requireString(governance.payment_effect, context, 'governance.payment_effect')
  requireString(governance.source_authority, context, 'governance.source_authority')
  requireArray(governance.statements, context, 'governance.statements')
  if (typeof governance.erp_write !== 'boolean' || typeof governance.automatic_approval !== 'boolean') {
    invalidContract(context, 'governance authority flags')
  }
}

function validateVendorCashGovernance(payload: JsonRecord, context: string): void {
  requireString(payload.contract_version, context, 'contract_version')
  validateSourceCoverageAndDeferred(payload, context)
  const governance = requireRecord(payload.governance, context, 'governance')
  requireString(governance.classification, context, 'governance.classification')
  requireString(governance.cash_requirement_authority, context, 'governance.cash_requirement_authority')
  requireArray(governance.statements, context, 'governance.statements')
  if (
    typeof governance.current_payable_status_known !== 'boolean' ||
    typeof governance.vendor_performance_score !== 'boolean' ||
    typeof governance.payment_proposal !== 'boolean' ||
    typeof governance.payment_authorization !== 'boolean' ||
    typeof governance.erp_write !== 'boolean'
  ) {
    invalidContract(context, 'governance authority flags')
  }
}

const overviewMetricKeys = [
  'imported_invoice_count',
  'review_required_count',
  'exception_count',
  'duplicate_candidate_count',
  'ocr_processed_count',
  'ocr_average_confidence',
  'extracted_invoice_total',
  'current_ap_balance',
  'due_today_count',
  'due_today_amount',
  'past_due_count',
  'past_due_amount',
  'due_within_7_days_amount',
  'discounts_available',
  'average_approval_time',
] as const

function validateOverview(payload: unknown): APOverviewResponse {
  const record = requireRecord(payload, 'overview', 'root object')
  validateSharedEnvelope(record, 'overview')
  requireString(record.generated_at, 'overview', 'generated_at')
  const metrics = requireRecord(record.metrics, 'overview', 'metrics')
  overviewMetricKeys.forEach((key) => {
    const metric = requireRecord(metrics[key], 'overview', `metrics.${key}`)
    if (metric.value !== null && typeof metric.value !== 'number') {
      invalidContract('overview', `metrics.${key}.value`)
    }
    requireString(metric.status, 'overview', `metrics.${key}.status`)
  })
  requireArray(record.warnings, 'overview', 'warnings')
  return record as unknown as APOverviewResponse
}

function validateInvoiceSummary(value: unknown, context: string): void {
  const invoice = requireRecord(value, context, 'invoice item')
  requireString(invoice.ap_invoice_id, context, 'invoice item ap_invoice_id')
  requireString(invoice.document_job_id, context, 'invoice item document_job_id')
  requireString(invoice.source_file_name, context, 'invoice item source_file_name')
  requireString(invoice.status, context, 'invoice item status')
  requireArray(invoice.warnings, context, 'invoice item warnings')
  if (
    typeof invoice.review_required !== 'boolean' ||
    typeof invoice.ocr_review_required !== 'boolean' ||
    typeof invoice.exception_count !== 'number' ||
    typeof invoice.duplicate_candidate_count !== 'number'
  ) {
    invalidContract(context, 'invoice item review evidence')
  }
}

function validateInvoiceList(payload: unknown): APInvoiceListResponse {
  const record = requireRecord(payload, 'invoice list', 'root object')
  validateSharedEnvelope(record, 'invoice list')
  const items = requireArray(record.items, 'invoice list', 'items')
  items.forEach((item) => validateInvoiceSummary(item, 'invoice list'))
  if (typeof record.total !== 'number' || typeof record.limit !== 'number' || typeof record.offset !== 'number') {
    invalidContract('invoice list', 'pagination')
  }
  const filterOptions = requireRecord(record.filter_options, 'invoice list', 'filter_options')
  const statuses = requireArray(filterOptions.statuses, 'invoice list', 'filter_options.statuses')
  if (!statuses.every((status) => typeof status === 'string')) {
    invalidContract('invoice list', 'filter_options.statuses')
  }
  requireArray(record.warnings, 'invoice list', 'warnings')
  return record as unknown as APInvoiceListResponse
}

function validateInvoiceDetail(payload: unknown): APInvoiceDetailResponse {
  const record = requireRecord(payload, 'invoice detail', 'root object')
  validateSharedEnvelope(record, 'invoice detail')
  validateInvoiceSummary(record, 'invoice detail')
  const sourceDocument = requireRecord(record.source_document, 'invoice detail', 'source_document')
  requireString(sourceDocument.job_id, 'invoice detail', 'source_document.job_id')
  requireString(sourceDocument.file_name, 'invoice detail', 'source_document.file_name')
  requireString(sourceDocument.status, 'invoice detail', 'source_document.status')
  const extractedFields = requireArray(record.extracted_fields, 'invoice detail', 'extracted_fields')
  extractedFields.forEach((value) => {
    const field = requireRecord(value, 'invoice detail', 'extracted field')
    requireString(field.field_name, 'invoice detail', 'extracted field field_name')
    requireString(field.authority, 'invoice detail', 'extracted field authority')
    requireString(field.validation_status, 'invoice detail', 'extracted field validation_status')
    requireString(field.source, 'invoice detail', 'extracted field source')
  })
  const exceptions = requireArray(record.exceptions, 'invoice detail', 'exceptions')
  exceptions.forEach((value) => {
    const exception = requireRecord(value, 'invoice detail', 'exception')
    requireString(exception.code, 'invoice detail', 'exception code')
    requireString(exception.severity, 'invoice detail', 'exception severity')
    requireArray(exception.evidence, 'invoice detail', 'exception evidence')
  })
  const duplicateEvidence = requireArray(record.duplicate_evidence, 'invoice detail', 'duplicate_evidence')
  duplicateEvidence.forEach((value) => {
    const candidate = requireRecord(value, 'invoice detail', 'duplicate candidate')
    requireString(candidate.candidate_ap_invoice_id, 'invoice detail', 'duplicate candidate id')
    requireString(candidate.amount_corroboration, 'invoice detail', 'duplicate amount corroboration')
    requireString(candidate.date_corroboration, 'invoice detail', 'duplicate date corroboration')
    requireArray(candidate.match_factors, 'invoice detail', 'duplicate match_factors')
  })
  const timeline = requireArray(record.timeline, 'invoice detail', 'timeline')
  timeline.forEach((value) => {
    const event = requireRecord(value, 'invoice detail', 'timeline event')
    requireString(event.event_id, 'invoice detail', 'timeline event id')
    requireString(event.label, 'invoice detail', 'timeline event label')
    requireString(event.source, 'invoice detail', 'timeline event source')
  })
  requireArray(record.provenance, 'invoice detail', 'provenance')
  requireString(record.source_evidence_sha256, 'invoice detail', 'source_evidence_sha256')
  if (typeof record.evidence_revision_count !== 'number') {
    invalidContract('invoice detail', 'evidence_revision_count')
  }
  return record as unknown as APInvoiceDetailResponse
}

function validateVendorInvoiceJob(value: unknown): APVendorInvoiceDocumentJob {
  const job = requireRecord(value, 'vendor invoice job', 'root object')
  requireString(job.job_id, 'vendor invoice job', 'job_id')
  requireString(job.original_file_name, 'vendor invoice job', 'original_file_name')
  requireString(job.document_type, 'vendor invoice job', 'document_type')
  requireString(job.status, 'vendor invoice job', 'status')
  requireString(job.message, 'vendor invoice job', 'message')
  if (typeof job.file_size_bytes !== 'number' || typeof job.confidence !== 'number') {
    invalidContract('vendor invoice job', 'size/confidence')
  }
  return job as unknown as APVendorInvoiceDocumentJob
}

function validateVendorInvoiceResult(value: unknown): APVendorInvoiceDocumentResult {
  const result = requireRecord(value, 'vendor invoice result', 'root object')
  validateVendorInvoiceJob(result.job)
  requireString(result.classifier, 'vendor invoice result', 'classifier')
  requireArray(result.classification_evidence, 'vendor invoice result', 'classification_evidence')
  requireRecord(result.extraction, 'vendor invoice result', 'extraction')
  const parsed = requireRecord(result.parsed, 'vendor invoice result', 'parsed')
  if (parsed.field_evidence !== undefined) {
    requireRecord(parsed.field_evidence, 'vendor invoice result', 'parsed.field_evidence')
  }
  return result as unknown as APVendorInvoiceDocumentResult
}

function validateVendorInvoiceIntake(value: unknown): APVendorInvoiceIntakeResponse {
  const intake = requireRecord(value, 'vendor invoice intake', 'root object')
  requireString(intake.intake_status, 'vendor invoice intake', 'intake_status')
  validateVendorInvoiceJob(intake.job)
  if (intake.result !== null) validateVendorInvoiceResult(intake.result)
  if (typeof intake.review_required !== 'boolean') {
    invalidContract('vendor invoice intake', 'review_required')
  }
  requireString(intake.message, 'vendor invoice intake', 'message')
  return intake as unknown as APVendorInvoiceIntakeResponse
}

function validateSync(payload: unknown): APSyncResponse {
  const record = requireRecord(payload, 'sync', 'root object')
  validateSharedEnvelope(record, 'sync')
  requireString(record.status, 'sync', 'status')
  requireString(record.message, 'sync', 'message')
  requireString(record.completed_at, 'sync', 'completed_at')
  requireArray(record.warnings, 'sync', 'warnings')
  for (const field of [
    'imported_count',
    'updated_count',
    'unchanged_count',
    'skipped_count',
    'eligible_job_count',
    'duplicate_candidate_count',
  ] as const) {
    if (typeof record[field] !== 'number') {
      invalidContract('sync', field)
    }
  }
  return record as unknown as APSyncResponse
}

function validateControlCaseSummary(value: unknown, context: string): void {
  const control = requireRecord(value, context, 'control case')
  requireString(control.control_case_id, context, 'control_case_id')
  requireString(control.ap_invoice_id, context, 'ap_invoice_id')
  requireString(control.intended_action, context, 'intended_action')
  requireString(control.control_status, context, 'control_status')
  requireString(control.requested_by, context, 'requested_by')
  requireString(control.assigned_reviewer, context, 'assigned_reviewer')
  validateInvoiceSummary(control.invoice, context)
  requireArray(control.evidence_gates, context, 'evidence_gates')
  requireArray(control.segregation_checks, context, 'segregation_checks')
  if (
    typeof control.document_evidence_ready !== 'boolean' ||
    typeof control.evidence_current !== 'boolean' ||
    typeof control.can_enter_governed_approval !== 'boolean' ||
    typeof control.can_authorize_payment !== 'boolean'
  ) {
    invalidContract(context, 'control authority flags')
  }
}

function validateControlCaseList(payload: unknown): APControlCaseListResponse {
  const record = requireRecord(payload, 'control case list', 'root object')
  validateSharedEnvelope(record, 'control case list')
  const items = requireArray(record.items, 'control case list', 'items')
  items.forEach((item) => validateControlCaseSummary(item, 'control case list'))
  if (typeof record.total !== 'number') invalidContract('control case list', 'total')
  requireArray(record.warnings, 'control case list', 'warnings')
  return record as unknown as APControlCaseListResponse
}

function validateControlCaseDetail(payload: unknown): APControlCaseDetail {
  const record = requireRecord(payload, 'control case detail', 'root object')
  validateSharedEnvelope(record, 'control case detail')
  validateControlCaseSummary(record, 'control case detail')
  requireString(record.source_evidence_sha256, 'control case detail', 'source_evidence_sha256')
  requireString(record.evidence_snapshot_sha256, 'control case detail', 'evidence_snapshot_sha256')
  requireArray(record.reviews, 'control case detail', 'reviews')
  requireArray(record.warnings, 'control case detail', 'warnings')
  return record as unknown as APControlCaseDetail
}

function validateVendorCashIntelligence(payload: unknown): APVendorCashIntelligenceResponse {
  const record = requireRecord(payload, 'vendor and cash intelligence', 'root object')
  validateVendorCashGovernance(record, 'vendor and cash intelligence')
  requireString(record.generated_at, 'vendor and cash intelligence', 'generated_at')
  requireString(record.as_of_date, 'vendor and cash intelligence', 'as_of_date')
  const coverage = requireRecord(record.coverage, 'vendor and cash intelligence', 'coverage')
  for (const key of [
    'imported_invoice_count',
    'identified_vendor_invoice_count',
    'due_date_invoice_count',
    'known_amount_invoice_count',
    'review_required_invoice_count',
  ] as const) {
    if (typeof coverage[key] !== 'number') invalidContract('vendor and cash intelligence', `coverage.${key}`)
  }
  const vendors = requireArray(record.vendors, 'vendor and cash intelligence', 'vendors')
  vendors.forEach((value) => {
    const vendor = requireRecord(value, 'vendor and cash intelligence', 'vendor')
    requireString(vendor.vendor_key, 'vendor and cash intelligence', 'vendor_key')
    requireString(vendor.identity_basis, 'vendor and cash intelligence', 'identity_basis')
    requireArray(vendor.evidence_alerts, 'vendor and cash intelligence', 'evidence_alerts')
    if (typeof vendor.invoice_count !== 'number' || typeof vendor.extracted_total_amount !== 'number') {
      invalidContract('vendor and cash intelligence', 'vendor metrics')
    }
  })
  const windows = requireArray(record.cash_windows, 'vendor and cash intelligence', 'cash_windows')
  windows.forEach((value) => {
    const window = requireRecord(value, 'vendor and cash intelligence', 'cash window')
    requireString(window.code, 'vendor and cash intelligence', 'cash window code')
    requireString(window.label, 'vendor and cash intelligence', 'cash window label')
    requireString(window.explanation, 'vendor and cash intelligence', 'cash window explanation')
    if (typeof window.invoice_count !== 'number' || typeof window.extracted_amount !== 'number') {
      invalidContract('vendor and cash intelligence', 'cash window metrics')
    }
  })
  requireArray(record.warnings, 'vendor and cash intelligence', 'warnings')
  return record as unknown as APVendorCashIntelligenceResponse
}

function validateCashScenario(value: unknown, context: string): void {
  const scenario = requireRecord(value, context, 'cash scenario')
  requireString(scenario.cash_scenario_id, context, 'cash_scenario_id')
  requireString(scenario.as_of_date, context, 'as_of_date')
  requireString(scenario.horizon_end_date, context, 'horizon_end_date')
  requireString(scenario.prepared_by, context, 'prepared_by')
  requireString(scenario.rationale, context, 'rationale')
  requireString(scenario.evidence_snapshot_sha256, context, 'evidence_snapshot_sha256')
  if (
    typeof scenario.horizon_days !== 'number' ||
    typeof scenario.included_invoice_count !== 'number' ||
    typeof scenario.extracted_amount !== 'number' ||
    typeof scenario.include_review_required !== 'boolean' ||
    typeof scenario.current_payable_status_known !== 'boolean' ||
    typeof scenario.erp_write !== 'boolean'
  ) {
    invalidContract(context, 'scenario metrics and authority flags')
  }
}

function validateCashScenarioRecord(payload: unknown): APCashScenario {
  validateCashScenario(payload, 'cash scenario')
  return payload as APCashScenario
}

function validateCashScenarioHistory(payload: unknown): APCashScenarioHistoryResponse {
  const record = requireRecord(payload, 'cash scenario history', 'root object')
  requireString(record.contract_version, 'cash scenario history', 'contract_version')
  const scenarios = requireArray(record.scenarios, 'cash scenario history', 'scenarios')
  scenarios.forEach((scenario) => validateCashScenario(scenario, 'cash scenario history'))
  if (typeof record.count !== 'number') invalidContract('cash scenario history', 'count')
  requireRecord(record.governance, 'cash scenario history', 'governance')
  requireArray(record.warnings, 'cash scenario history', 'warnings')
  return record as unknown as APCashScenarioHistoryResponse
}

function validateExceptionAction(value: unknown, context: string): void {
  const action = requireRecord(value, context, 'exception action')
  for (const field of [
    'action_id',
    'ap_invoice_id',
    'disposition',
    'owner_identity',
    'actor_identity',
    'notes',
    'created_at',
    'source_evidence_sha256',
    'evidence_snapshot_sha256',
    'authority_status',
  ] as const) {
    requireString(action[field], context, field)
  }
  requireRecord(action.evidence_snapshot, context, 'evidence_snapshot')
  if (action.approval_effect !== 'none' || action.payment_effect !== 'none' || action.erp_write !== false) {
    invalidContract(context, 'non-authoritative action boundary')
  }
}

function validateExceptionGovernance(value: unknown, context: string): void {
  const governance = requireRecord(value, context, 'governance')
  requireString(governance.classification, context, 'governance.classification')
  requireString(governance.queue_ordering, context, 'governance.queue_ordering')
  requireArray(governance.statements, context, 'governance.statements')
  if (
    governance.approved_sla !== false ||
    governance.authenticated_assignment !== false ||
    governance.automatic_resolution !== false ||
    governance.approval_effect !== 'none' ||
    governance.payment_effect !== 'none' ||
    governance.erp_write !== false
  ) {
    invalidContract(context, 'governance authority flags')
  }
}

function validateExceptionOperations(payload: unknown): APExceptionOperationsResponse {
  const record = requireRecord(payload, 'exception operations', 'root object')
  requireString(record.contract_version, 'exception operations', 'contract_version')
  requireString(record.generated_at, 'exception operations', 'generated_at')
  requireString(record.as_of_date, 'exception operations', 'as_of_date')
  const summary = requireRecord(record.summary, 'exception operations', 'summary')
  for (const field of [
    'queue_count',
    'unworked_count',
    'follow_up_scheduled_count',
    'follow_up_overdue_count',
    'source_changed_count',
    'documented_count',
    'duplicate_review_count',
    'ocr_review_count',
    'known_amount_count',
    'extracted_amount',
  ] as const) {
    if (typeof summary[field] !== 'number') invalidContract('exception operations', `summary.${field}`)
  }
  const items = requireArray(record.items, 'exception operations', 'items')
  items.forEach((value) => {
    const item = requireRecord(value, 'exception operations', 'queue item')
    requireString(item.ap_invoice_id, 'exception operations', 'queue item ap_invoice_id')
    requireString(item.source_file_name, 'exception operations', 'queue item source_file_name')
    requireString(item.source_evidence_sha256, 'exception operations', 'queue item source_evidence_sha256')
    requireString(item.work_state, 'exception operations', 'queue item work_state')
    if (typeof item.queue_rank !== 'number') invalidContract('exception operations', 'queue item queue_rank')
    const reasons = requireArray(item.reasons, 'exception operations', 'queue item reasons')
    reasons.forEach((reasonValue) => {
      const reason = requireRecord(reasonValue, 'exception operations', 'queue item reason')
      requireString(reason.code, 'exception operations', 'reason code')
      requireString(reason.label, 'exception operations', 'reason label')
      requireString(reason.severity, 'exception operations', 'reason severity')
      requireString(reason.source, 'exception operations', 'reason source')
      requireString(reason.explanation, 'exception operations', 'reason explanation')
    })
    if (item.latest_action !== null) validateExceptionAction(item.latest_action, 'exception operations')
  })
  requireArray(record.source_coverage, 'exception operations', 'source_coverage')
  requireArray(record.deferred_capabilities, 'exception operations', 'deferred_capabilities')
  requireArray(record.warnings, 'exception operations', 'warnings')
  validateExceptionGovernance(record.governance, 'exception operations')
  return record as unknown as APExceptionOperationsResponse
}

function validateExceptionActionRecord(payload: unknown): APExceptionAction {
  validateExceptionAction(payload, 'exception action')
  return payload as APExceptionAction
}

function validateExceptionActionHistory(payload: unknown): APExceptionActionHistoryResponse {
  const record = requireRecord(payload, 'exception action history', 'root object')
  requireString(record.contract_version, 'exception action history', 'contract_version')
  requireString(record.ap_invoice_id, 'exception action history', 'ap_invoice_id')
  if (typeof record.count !== 'number') invalidContract('exception action history', 'count')
  const actions = requireArray(record.actions, 'exception action history', 'actions')
  actions.forEach((action) => validateExceptionAction(action, 'exception action history'))
  validateExceptionGovernance(record.governance, 'exception action history')
  return record as unknown as APExceptionActionHistoryResponse
}

export function getAccountsPayableOverview(
  signal?: AbortSignal,
): Promise<APOverviewResponse> {
  return requestJson<unknown>('/accounts-payable/overview', { signal }).then(validateOverview)
}

export function getAccountsPayableInvoices(
  filters: APInvoiceQuery,
  signal?: AbortSignal,
): Promise<APInvoiceListResponse> {
  return requestJson<unknown>(
    `/accounts-payable/invoices${buildAccountsPayableInvoiceQuery(filters)}`,
    { signal },
  ).then(validateInvoiceList)
}

export function getAccountsPayableInvoice(
  apInvoiceId: string,
  signal?: AbortSignal,
): Promise<APInvoiceDetailResponse> {
  return requestJson<unknown>(
    `/accounts-payable/invoices/${encodeURIComponent(apInvoiceId)}`,
    { signal },
  ).then(validateInvoiceDetail)
}

function validateAPMappingReadiness(payload: unknown): APMappingReadinessResponse {
  const record = requireRecord(payload, 'ERP mapping readiness', 'root object')
  requireString(record.contract_version, 'ERP mapping readiness', 'contract_version')
  requireString(record.generated_at, 'ERP mapping readiness', 'generated_at')
  requireString(record.source_schema, 'ERP mapping readiness', 'source_schema')
  requireString(record.schema_catalog_status, 'ERP mapping readiness', 'schema_catalog_status')
  requireArray(record.categories, 'ERP mapping readiness', 'categories')
  requireArray(record.warnings, 'ERP mapping readiness', 'warnings')
  return record as unknown as APMappingReadinessResponse
}

function validateAPErpEvidence(payload: unknown): APERPEvidenceResponse {
  const record = requireRecord(payload, 'ERP invoice evidence', 'root object')
  requireString(record.contract_version, 'ERP invoice evidence', 'contract_version')
  requireString(record.generated_at, 'ERP invoice evidence', 'generated_at')
  requireString(record.evidence_sha256, 'ERP invoice evidence', 'evidence_sha256')
  requireRecord(record.lookup_identity, 'ERP invoice evidence', 'lookup_identity')
  if (record.local_invoice !== null) {
    requireRecord(record.local_invoice, 'ERP invoice evidence', 'local_invoice')
  }
  requireRecord(record.vendor_master, 'ERP invoice evidence', 'vendor_master')
  requireArray(record.posted_headers, 'ERP invoice evidence', 'posted_headers')
  requireArray(record.posted_details, 'ERP invoice evidence', 'posted_details')
  requireArray(record.gl_distributions, 'ERP invoice evidence', 'gl_distributions')
  requireArray(record.po_receiving_match, 'ERP invoice evidence', 'po_receiving_match')
  requireArray(record.input_headers, 'ERP invoice evidence', 'input_headers')
  requireArray(record.input_details, 'ERP invoice evidence', 'input_details')
  requireArray(record.input_payment_splits, 'ERP invoice evidence', 'input_payment_splits')
  requireArray(record.coverage, 'ERP invoice evidence', 'coverage')
  requireArray(record.sensitive_fields_excluded, 'ERP invoice evidence', 'sensitive_fields_excluded')
  requireArray(record.warnings, 'ERP invoice evidence', 'warnings')
  return record as unknown as APERPEvidenceResponse
}

function validateAPErpInvoiceSearch(payload: unknown): APERPInvoiceSearchResponse {
  const record = requireRecord(payload, 'ERP invoice search', 'root object')
  requireString(record.contract_version, 'ERP invoice search', 'contract_version')
  requireString(record.generated_at, 'ERP invoice search', 'generated_at')
  requireString(record.evidence_sha256, 'ERP invoice search', 'evidence_sha256')
  requireRecord(record.query, 'ERP invoice search', 'query')
  requireArray(record.vendor_candidates, 'ERP invoice search', 'vendor_candidates')
  requireArray(record.invoice_candidates, 'ERP invoice search', 'invoice_candidates')
  requireArray(record.source_references, 'ERP invoice search', 'source_references')
  requireRecord(record.governance, 'ERP invoice search', 'governance')
  requireArray(record.sensitive_fields_excluded, 'ERP invoice search', 'sensitive_fields_excluded')
  requireArray(record.warnings, 'ERP invoice search', 'warnings')
  if (
    typeof record.vendor_candidate_complete !== 'boolean'
    || typeof record.invoice_candidate_complete !== 'boolean'
  ) {
    invalidContract('ERP invoice search', 'bounded completeness flags')
  }
  return record as unknown as APERPInvoiceSearchResponse
}

function validateAPSpendReadiness(payload: unknown): APSpendReadinessResponse {
  const record = requireRecord(payload, 'vendor spend readiness', 'root object')
  requireString(record.contract_version, 'vendor spend readiness', 'contract_version')
  requireString(record.generated_at, 'vendor spend readiness', 'generated_at')
  requireString(record.status, 'vendor spend readiness', 'status')
  requireString(record.source_schema, 'vendor spend readiness', 'source_schema')
  const mappingChecks = requireArray(record.mapping_checks, 'vendor spend readiness', 'mapping_checks')
  mappingChecks.forEach((item, index) => {
    const check = requireRecord(item, 'vendor spend readiness', `mapping_checks[${index}]`)
    requireArray(check.missing_fields, 'vendor spend readiness', `mapping_checks[${index}].missing_fields`)
    requireArray(check.incompatible_fields, 'vendor spend readiness', `mapping_checks[${index}].incompatible_fields`)
  })
  requireArray(record.date_bases, 'vendor spend readiness', 'date_bases')
  requireRecord(record.measure, 'vendor spend readiness', 'measure')
  requireRecord(record.governance, 'vendor spend readiness', 'governance')
  requireArray(record.product_owner_mappings_needed, 'vendor spend readiness', 'product_owner_mappings_needed')
  requireArray(record.warnings, 'vendor spend readiness', 'warnings')
  return record as unknown as APSpendReadinessResponse
}

function validateAPSpendQuestion(payload: unknown): APSpendQuestionResponse {
  const record = requireRecord(payload, 'vendor spend question', 'root object')
  requireString(record.contract_version, 'vendor spend question', 'contract_version')
  requireString(record.generated_at, 'vendor spend question', 'generated_at')
  if (record.evidence_as_of !== null && typeof record.evidence_as_of !== 'string') {
    invalidContract('vendor spend question', 'evidence_as_of')
  }
  requireString(record.status, 'vendor spend question', 'status')
  requireString(record.answer_text, 'vendor spend question', 'answer_text')
  requireString(record.evidence_sha256, 'vendor spend question', 'evidence_sha256')
  const parsed = requireRecord(record.parsed, 'vendor spend question', 'parsed')
  requireString(parsed.parser_version, 'vendor spend question', 'parsed.parser_version')
  requireString(parsed.original_question, 'vendor spend question', 'parsed.original_question')
  requireArray(parsed.interpretation_notes, 'vendor spend question', 'parsed.interpretation_notes')
  requireArray(parsed.missing_slots, 'vendor spend question', 'parsed.missing_slots')
  requireArray(parsed.ambiguous_slots, 'vendor spend question', 'parsed.ambiguous_slots')
  requireArray(parsed.unavailable_slots, 'vendor spend question', 'parsed.unavailable_slots')
  validateAPSpendReadiness(record.readiness)
  if (record.total !== null) {
    const total = requireRecord(record.total, 'vendor spend question', 'total')
    for (const field of [
      'distribution_row_count',
      'amount_available_row_count',
      'missing_amount_row_count',
      'invoice_identity_count',
      'vendor_count',
      'positive_distribution_amount',
      'negative_distribution_amount',
      'net_signed_amount',
    ] as const) {
      if (typeof total[field] !== 'number') invalidContract('vendor spend question', `total.${field}`)
    }
  }
  requireArray(record.ranking, 'vendor spend question', 'ranking')
  requireArray(record.leaders, 'vendor spend question', 'leaders')
  const monthlyPeriods = requireArray(record.monthly_periods, 'vendor spend question', 'monthly_periods')
  monthlyPeriods.forEach((value, index) => {
    const period = requireRecord(value, 'vendor spend question', `monthly_periods[${index}]`)
    if (
      typeof period.calendar_year !== 'number'
      || typeof period.calendar_month !== 'number'
      || typeof period.ranking_complete !== 'boolean'
      || typeof period.leader_set_complete !== 'boolean'
    ) {
      invalidContract('vendor spend question', `monthly_periods[${index}] numeric/completeness evidence`)
    }
    requireString(period.range_start, 'vendor spend question', `monthly_periods[${index}].range_start`)
    requireString(period.range_end_exclusive, 'vendor spend question', `monthly_periods[${index}].range_end_exclusive`)
    requireString(period.status, 'vendor spend question', `monthly_periods[${index}].status`)
    requireString(period.explanation, 'vendor spend question', `monthly_periods[${index}].explanation`)
    requireArray(period.leaders, 'vendor spend question', `monthly_periods[${index}].leaders`)
  })
  requireArray(record.coverage, 'vendor spend question', 'coverage')
  requireArray(record.source_references, 'vendor spend question', 'source_references')
  requireRecord(record.governance, 'vendor spend question', 'governance')
  requireArray(record.warnings, 'vendor spend question', 'warnings')
  requireArray(record.suggested_questions, 'vendor spend question', 'suggested_questions')
  if (
    typeof record.ranking_row_limit !== 'number'
    || typeof record.monthly_period_limit !== 'number'
    || typeof record.monthly_leader_limit !== 'number'
  ) {
    invalidContract('vendor spend question', 'ranking/monthly row limits')
  }
  if (record.ranking_complete !== null && typeof record.ranking_complete !== 'boolean') {
    invalidContract('vendor spend question', 'ranking_complete')
  }
  if (record.leader_set_complete !== null && typeof record.leader_set_complete !== 'boolean') {
    invalidContract('vendor spend question', 'leader_set_complete')
  }
  requireString(record.evidence_consistency, 'vendor spend question', 'evidence_consistency')
  if (
    record.evidence_consistency !== 'single_read_only_consistent_snapshot'
    && record.evidence_consistency !== 'no_financial_query'
    && record.evidence_consistency !== 'consistent_snapshot_query_failed'
  ) {
    invalidContract('vendor spend question', 'evidence_consistency')
  }
  return record as unknown as APSpendQuestionResponse
}

export function getAPErpMappingReadiness(
  signal?: AbortSignal,
): Promise<APMappingReadinessResponse> {
  return requestJson<unknown>('/erp-evidence/accounts-payable/mapping-readiness', {
    signal,
  }).then(validateAPMappingReadiness)
}

export function getAPVendorSpendReadiness(
  signal?: AbortSignal,
): Promise<APSpendReadinessResponse> {
  return requestJson<unknown>(
    '/erp-evidence/accounts-payable/vendor-spend-readiness',
    { signal },
  ).then(validateAPSpendReadiness)
}

export function askAPVendorSpendQuestion(
  question: string,
  signal?: AbortSignal,
): Promise<APSpendQuestionResponse> {
  const params = new URLSearchParams({ question: question.trim() })
  return requestJson<unknown>(
    `/erp-evidence/accounts-payable/vendor-spend-question?${params.toString()}`,
    { signal },
  ).then(validateAPSpendQuestion)
}

export function getAPErpInvoiceEvidence(
  apInvoiceId: string,
  signal?: AbortSignal,
): Promise<APERPEvidenceResponse> {
  return requestJson<unknown>(
    `/erp-evidence/accounts-payable/invoices/${encodeURIComponent(apInvoiceId)}`,
    { signal },
  ).then(validateAPErpEvidence)
}

function validateAPGLCodingSuggestions(payload: unknown): APGLCodingSuggestionsResponse {
  const record = requireRecord(payload, 'GL coding suggestions', 'root object')
  requireString(record.contract_version, 'GL coding suggestions', 'contract_version')
  requireString(record.vendor_number, 'GL coding suggestions', 'vendor_number')
  if (typeof record.total_coded_invoice_count !== 'number') {
    invalidContract('GL coding suggestions', 'total_coded_invoice_count')
  }
  const suggestions = requireArray(record.suggestions, 'GL coding suggestions', 'suggestions')
  suggestions.forEach((value) => {
    const suggestion = requireRecord(value, 'GL coding suggestions', 'suggestion')
    requireString(suggestion.gl_division, 'GL coding suggestions', 'suggestion gl_division')
    requireString(suggestion.gl_account, 'GL coding suggestions', 'suggestion gl_account')
    if (typeof suggestion.invoice_count !== 'number' || typeof suggestion.match_percent !== 'number') {
      invalidContract('GL coding suggestions', 'suggestion metrics')
    }
  })
  requireArray(record.excluded_structural_accounts, 'GL coding suggestions', 'excluded_structural_accounts')
  requireRecord(record.governance, 'GL coding suggestions', 'governance')
  requireArray(record.warnings, 'GL coding suggestions', 'warnings')
  return record as unknown as APGLCodingSuggestionsResponse
}

export function getAPGLCodingSuggestions(
  vendorNumber: string,
  signal?: AbortSignal,
): Promise<APGLCodingSuggestionsResponse> {
  const params = new URLSearchParams({ vendor_number: vendorNumber, limit: '3' })
  return requestJson<unknown>(
    `/erp-evidence/accounts-payable/gl-coding-suggestions?${params.toString()}`,
    { signal },
  ).then(validateAPGLCodingSuggestions)
}

export function searchAPErpInvoices(
  vendorQuery: string,
  invoiceNumber: string,
  signal?: AbortSignal,
): Promise<APERPInvoiceSearchResponse> {
  const params = new URLSearchParams()
  if (vendorQuery.trim()) params.set('vendor_query', vendorQuery.trim())
  if (invoiceNumber.trim()) params.set('invoice_number', invoiceNumber.trim())
  params.set('limit', '50')
  return requestJson<unknown>(
    `/erp-evidence/accounts-payable/invoice-search?${params.toString()}`,
    { signal },
  ).then(validateAPErpInvoiceSearch)
}

export function getAPErpDirectInvoiceEvidence(
  vendorNumber: string,
  invoiceNumber: string,
  signal?: AbortSignal,
): Promise<APERPEvidenceResponse> {
  const params = new URLSearchParams({
    vendor_number: vendorNumber,
    invoice_number: invoiceNumber,
  })
  return requestJson<unknown>(
    `/erp-evidence/accounts-payable/invoice-evidence?${params.toString()}`,
    { signal },
  ).then(validateAPErpEvidence)
}

export function syncAccountsPayableInvoices(
  signal?: AbortSignal,
): Promise<APSyncResponse> {
  return requestJson<unknown>('/accounts-payable/sync', {
    method: 'POST',
    signal,
  }).then(validateSync)
}

function validateErpLedgerRefresh(payload: unknown): APErpLedgerRefreshResponse {
  const record = requireRecord(payload, 'erp-ledger-refresh', 'root object')
  const jobId = requireString(record.job_id, 'erp-ledger-refresh', 'job_id')
  const status = requireString(record.status, 'erp-ledger-refresh', 'status')
  if (status !== 'queued' && status !== 'completed') {
    invalidContract('erp-ledger-refresh', 'status')
  }
  return { job_id: jobId, status: status as 'queued' | 'completed' }
}

export function refreshAccountsPayableErpLedger(
  signal?: AbortSignal,
): Promise<APErpLedgerRefreshResponse> {
  return requestJson<unknown>('/accounts-payable/erp-ledger/refresh', {
    method: 'POST',
    signal,
  }).then(validateErpLedgerRefresh)
}

function validateVendorTermsReference(
  payload: unknown,
): APVendorTermsReferenceListResponse {
  const record = requireRecord(payload, 'vendor-terms-reference', 'root object')
  const items = requireArray(record.items, 'vendor-terms-reference', 'items')
  return { items: items as APVendorTermsReferenceListResponse['items'] }
}

export function getAPVendorTermsReference(
  signal?: AbortSignal,
): Promise<APVendorTermsReferenceListResponse> {
  return requestJson<unknown>('/accounts-payable/vendor-terms-reference', {
    signal,
  }).then(validateVendorTermsReference)
}

export function upsertAPVendorTermsReference(
  termsCode: string,
  payload: APVendorTermsReferenceUpsert,
): Promise<void> {
  return requestJson<void>(
    `/accounts-payable/vendor-terms-reference/${encodeURIComponent(termsCode)}`,
    { method: 'PUT', body: JSON.stringify(payload) },
  )
}

function validateWarehouseApprovalGovernance(value: unknown, context: string): void {
  const governance = requireRecord(value, context, 'governance')
  requireString(governance.erp_access, context, 'governance.erp_access')
  requireString(governance.approval_effect, context, 'governance.approval_effect')
  requireString(governance.payment_effect, context, 'governance.payment_effect')
  requireString(governance.source_authority, context, 'governance.source_authority')
  requireArray(governance.statements, context, 'governance.statements')
  if (typeof governance.erp_write !== 'boolean' || typeof governance.automatic_approval !== 'boolean') {
    invalidContract(context, 'governance authority flags')
  }
}

function validateWarehouseApprovalItem(value: unknown, context: string): void {
  const item = requireRecord(value, context, 'warehouse approval item')
  requireString(item.vendor_number, context, 'vendor_number')
  requireString(item.invoice_number, context, 'invoice_number')
  requireString(item.status, context, 'status')
  if (typeof item.amount_invoiced !== 'number' || typeof item.amount_discount !== 'number') {
    invalidContract(context, 'amount fields')
  }
  if (typeof item.on_hold !== 'boolean') {
    invalidContract(context, 'on_hold')
  }
}

function validateWarehouseApprovalQueue(payload: unknown): APWarehouseApprovalQueueResponse {
  const record = requireRecord(payload, 'warehouse approval queue', 'root object')
  requireString(record.contract_version, 'warehouse approval queue', 'contract_version')
  requireArray(record.available_divisions, 'warehouse approval queue', 'available_divisions')
  const buckets = ['needs_approval', 'approved_by_warehouse', 'approved_and_entered_by_ap'] as const
  buckets.forEach((bucket) => {
    const items = requireArray(record[bucket], 'warehouse approval queue', bucket)
    items.forEach((item) => validateWarehouseApprovalItem(item, 'warehouse approval queue'))
  })
  validateWarehouseApprovalGovernance(record.governance, 'warehouse approval queue')
  return record as unknown as APWarehouseApprovalQueueResponse
}

function validateWarehouseApprovalAction(payload: unknown): APWarehouseApprovalActionRecord {
  const record = requireRecord(payload, 'warehouse approval action', 'root object')
  requireString(record.action_id, 'warehouse approval action', 'action_id')
  requireString(record.vendor_number, 'warehouse approval action', 'vendor_number')
  requireString(record.invoice_number, 'warehouse approval action', 'invoice_number')
  requireString(record.from_status, 'warehouse approval action', 'from_status')
  requireString(record.to_status, 'warehouse approval action', 'to_status')
  requireString(record.actor_identity, 'warehouse approval action', 'actor_identity')
  requireString(record.actor_identity_source, 'warehouse approval action', 'actor_identity_source')
  requireString(record.created_at, 'warehouse approval action', 'created_at')
  return record as unknown as APWarehouseApprovalActionRecord
}

export function getAPWarehouseApprovalQueue(
  division: string | null,
  signal?: AbortSignal,
): Promise<APWarehouseApprovalQueueResponse> {
  const params = division ? `?division=${encodeURIComponent(division)}` : ''
  return requestJson<unknown>(
    `/accounts-payable/warehouse-approval-queue${params}`,
    { signal },
  ).then(validateWarehouseApprovalQueue)
}

export function createAPWarehouseApprovalAction(
  payload: APWarehouseApprovalActionCreate,
  signal?: AbortSignal,
): Promise<APWarehouseApprovalActionRecord> {
  return requestJson<unknown>('/accounts-payable/warehouse-approval-queue/actions', {
    method: 'POST',
    body: payload,
    signal,
  }).then(validateWarehouseApprovalAction)
}

export function syncAccountsPayableInvoiceJob(
  jobId: string,
  signal?: AbortSignal,
): Promise<APSyncResponse> {
  return requestJson<unknown>(
    `/accounts-payable/sync/document-jobs/${encodeURIComponent(jobId)}`,
    { method: 'POST', signal },
  ).then(validateSync)
}

export async function uploadAPVendorInvoice(
  file: File,
  signal?: AbortSignal,
): Promise<APVendorInvoiceIntakeResponse> {
  const formData = new FormData()
  formData.append('file', file)
  const response = await fetch(`${API_BASE}/documents/vendor-invoices/upload`, {
    method: 'POST',
    body: formData,
    signal,
    headers: { Accept: 'application/json' },
  })
  if (!response.ok) {
    let message = `Vendor invoice upload failed with status ${response.status}.`
    let details: unknown
    try {
      details = await response.json()
      if (isRecord(details) && typeof details.detail === 'string') {
        message = details.detail
      }
    } catch {
      // The status remains the fail-closed evidence when the body is unreadable.
    }
    throw new ApiError(message, response.status, details)
  }
  return validateVendorInvoiceIntake(await response.json())
}

export function getAPVendorInvoiceJobs(
  limit = 50,
  offset = 0,
  signal?: AbortSignal,
): Promise<APVendorInvoiceDatasetPage> {
  return requestJson<unknown>(`/documents/vendor-invoices/jobs?limit=${encodeURIComponent(limit)}&offset=${encodeURIComponent(offset)}`, {
    signal,
  }).then((value) => {
    const envelope = requireRecord(value, 'vendor invoice dataset', 'root object')
    const jobs = requireArray(envelope.jobs, 'vendor invoice dataset', 'jobs').map(
      validateVendorInvoiceJob,
    )
    if (
      typeof envelope.total !== 'number'
      || typeof envelope.limit !== 'number'
      || typeof envelope.offset !== 'number'
    ) {
      invalidContract('vendor invoice dataset', 'pagination')
    }
    return {
      jobs,
      total: envelope.total,
      limit: envelope.limit,
      offset: envelope.offset,
    }
  })
}

export function getAPVendorInvoiceJob(
  jobId: string,
  signal?: AbortSignal,
): Promise<APVendorInvoiceDocumentJob> {
  return requestJson<unknown>(
    `/documents/jobs/${encodeURIComponent(jobId)}`,
    { signal },
  ).then(validateVendorInvoiceJob)
}

export function getAPVendorInvoiceResult(
  jobId: string,
  signal?: AbortSignal,
): Promise<APVendorInvoiceDocumentResult> {
  return requestJson<unknown>(
    `/documents/jobs/${encodeURIComponent(jobId)}/result`,
    { signal },
  ).then(validateVendorInvoiceResult)
}

export function reprocessAPVendorInvoice(
  jobId: string,
  signal?: AbortSignal,
): Promise<APVendorInvoiceDocumentResult> {
  return requestJson<unknown>(
    `/documents/jobs/${encodeURIComponent(jobId)}/process`,
    { method: 'POST', signal },
  ).then(validateVendorInvoiceResult)
}

export function getAPVendorInvoiceRuns(
  jobId: string,
  signal?: AbortSignal,
): Promise<APVendorInvoiceProcessingRun[]> {
  return requestJson<unknown>(
    `/documents/jobs/${encodeURIComponent(jobId)}/runs`,
    { signal },
  ).then((value) => {
    const envelope = requireRecord(value, 'vendor invoice runs', 'root object')
    return requireArray(envelope.runs, 'vendor invoice runs', 'runs').map((item) => {
      const run = requireRecord(item, 'vendor invoice runs', 'run')
      requireString(run.processing_run_id, 'vendor invoice runs', 'processing_run_id')
      requireString(run.processor_version, 'vendor invoice runs', 'processor_version')
      requireString(run.status, 'vendor invoice runs', 'status')
      if (typeof run.run_number !== 'number') invalidContract('vendor invoice runs', 'run_number')
      return run as unknown as APVendorInvoiceProcessingRun
    })
  })
}

export function getAPVendorInvoiceReview(
  jobId: string,
  signal?: AbortSignal,
): Promise<APVendorInvoiceReview> {
  return requestJson<unknown>(
    `/documents/jobs/${encodeURIComponent(jobId)}/review`,
    { signal },
  ).then((value) => {
    const envelope = requireRecord(value, 'vendor invoice review', 'root object')
    requireRecord(envelope.review, 'vendor invoice review', 'review')
    requireArray(envelope.history, 'vendor invoice review', 'history')
    return envelope as unknown as APVendorInvoiceReview
  })
}

export function saveAPVendorInvoiceReview(
  jobId: string,
  payload: {
    expected_processing_run_id: string
    status: 'approved' | 'needs_correction' | 'needs_learning' | 'pending'
    reviewer: string
    notes: string
    corrected_fields: Record<string, unknown>
    unavailable_fields: string[]
  },
  signal?: AbortSignal,
): Promise<APVendorInvoiceReview> {
  return requestJson<unknown>(
    `/documents/jobs/${encodeURIComponent(jobId)}/review`,
    { method: 'PUT', body: payload, signal },
  ).then((value) => {
    const envelope = requireRecord(value, 'vendor invoice review', 'root object')
    requireRecord(envelope.review, 'vendor invoice review', 'review')
    requireArray(envelope.history, 'vendor invoice review', 'history')
    return envelope as unknown as APVendorInvoiceReview
  })
}

export function getAPVendorInvoiceFileUrl(jobId: string): string {
  return `${API_BASE}/documents/jobs/${encodeURIComponent(jobId)}/file`
}

export function getAPControlCases(
  action: 'approval_review' | 'payment_preparation',
  signal?: AbortSignal,
): Promise<APControlCaseListResponse> {
  return requestJson<unknown>(
    `/accounts-payable/control-cases?intended_action=${encodeURIComponent(action)}`,
    { signal },
  ).then(validateControlCaseList)
}

export function getAPControlCase(
  controlCaseId: string,
  signal?: AbortSignal,
): Promise<APControlCaseDetail> {
  return requestJson<unknown>(
    `/accounts-payable/control-cases/${encodeURIComponent(controlCaseId)}`,
    { signal },
  ).then(validateControlCaseDetail)
}

export function createAPControlCase(
  apInvoiceId: string,
  payload: CreateAPControlCaseRequest,
  signal?: AbortSignal,
): Promise<APControlCaseDetail> {
  return requestJson<unknown>(
    `/accounts-payable/invoices/${encodeURIComponent(apInvoiceId)}/control-cases`,
    { method: 'POST', body: payload, signal },
  ).then(validateControlCaseDetail)
}

export function createAPControlReview(
  controlCaseId: string,
  payload: CreateAPControlReviewRequest,
  signal?: AbortSignal,
): Promise<APControlCaseDetail> {
  return requestJson<unknown>(
    `/accounts-payable/control-cases/${encodeURIComponent(controlCaseId)}/reviews`,
    { method: 'POST', body: payload, signal },
  ).then(validateControlCaseDetail)
}

export function getAPVendorCashIntelligence(
  asOfDate: string,
  signal?: AbortSignal,
): Promise<APVendorCashIntelligenceResponse> {
  return requestJson<unknown>(
    `/accounts-payable/vendor-cash-intelligence?as_of_date=${encodeURIComponent(asOfDate)}`,
    { signal },
  ).then(validateVendorCashIntelligence)
}

export function getAPCashScenarios(
  signal?: AbortSignal,
): Promise<APCashScenarioHistoryResponse> {
  return requestJson<unknown>('/accounts-payable/cash-scenarios', { signal })
    .then(validateCashScenarioHistory)
}

export function createAPCashScenario(
  payload: CreateAPCashScenarioRequest,
  signal?: AbortSignal,
): Promise<APCashScenario> {
  return requestJson<unknown>('/accounts-payable/cash-scenarios', {
    method: 'POST',
    body: payload,
    signal,
  }).then(validateCashScenarioRecord)
}

export function getAPExceptionOperations(
  asOfDate: string,
  signal?: AbortSignal,
): Promise<APExceptionOperationsResponse> {
  return requestJson<unknown>(
    `/accounts-payable/exception-operations?as_of_date=${encodeURIComponent(asOfDate)}`,
    { signal },
  ).then(validateExceptionOperations)
}

export function getAPExceptionActions(
  apInvoiceId: string,
  signal?: AbortSignal,
): Promise<APExceptionActionHistoryResponse> {
  return requestJson<unknown>(
    `/accounts-payable/invoices/${encodeURIComponent(apInvoiceId)}/exception-actions`,
    { signal },
  ).then(validateExceptionActionHistory)
}

export function createAPExceptionAction(
  apInvoiceId: string,
  payload: CreateAPExceptionActionRequest,
  signal?: AbortSignal,
): Promise<APExceptionAction> {
  return requestJson<unknown>(
    `/accounts-payable/invoices/${encodeURIComponent(apInvoiceId)}/exception-actions`,
    { method: 'POST', body: payload, signal },
  ).then(validateExceptionActionRecord)
}
