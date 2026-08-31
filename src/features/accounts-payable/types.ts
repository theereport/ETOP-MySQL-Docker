export type SourceStatus =
  | 'available'
  | 'partial'
  | 'unavailable'
  | 'not_connected'
  | 'degraded'
  | 'unknown'
  | string

export interface SourceCoverageItem {
  key: string
  label: string
  status: SourceStatus
  source: string | null
  as_of: string | null
  record_count: number | null
  explanation: string
}

export interface APMetric<T = number> {
  value: T | null
  status: SourceStatus
  source: string | null
  as_of: string | null
  explanation: string
}

export interface AccountsPayableMetrics {
  imported_invoice_count: APMetric
  review_required_count: APMetric
  exception_count: APMetric
  duplicate_candidate_count: APMetric
  ocr_processed_count: APMetric
  ocr_average_confidence: APMetric
  extracted_invoice_total: APMetric
  current_ap_balance: APMetric
  due_today_count: APMetric
  due_today_amount: APMetric
  past_due_count: APMetric
  past_due_amount: APMetric
  due_within_7_days_amount: APMetric
  discounts_available: APMetric
  average_approval_time: APMetric
}

export interface APGovernance {
  erp_access: string
  erp_write: boolean
  approval_effect: string
  payment_effect: string
  automatic_approval: boolean
  source_authority: string
  statements: string[]
}

export interface DeferredCapability {
  key: string
  label: string
  status: string
  reason: string
  missing_sources: string[]
}

export interface APOverviewResponse {
  contract_version: string
  generated_at: string
  metrics: AccountsPayableMetrics
  source_coverage: SourceCoverageItem[]
  governance: APGovernance
  deferred_capabilities: DeferredCapability[]
  warnings: string[]
}

export interface APInvoiceSummary {
  ap_invoice_id: string
  document_job_id: string
  document_result_id: string
  source_record_index: number | null
  source_file_name: string
  vendor_number: string | null
  vendor_name: string | null
  invoice_number: string | null
  invoice_date: string | null
  received_at: string | null
  due_date: string | null
  purchase_order_number: string | null
  subtotal: number | null
  tax: number | null
  freight: number | null
  discount: number | null
  total_amount: number | null
  currency: string | null
  terms: string | null
  status: string
  review_required: boolean
  ocr_review_required: boolean
  classification_confidence: number | null
  ocr_confidence: number | null
  exception_count: number
  duplicate_candidate_count: number
  warnings: string[]
  processed_at: string | null
  source_as_of: string
  last_synced_at: string
}

export interface APInvoiceFilters {
  statuses: string[]
}

export interface APInvoiceListResponse {
  contract_version: string
  items: APInvoiceSummary[]
  total: number
  limit: number
  offset: number
  filter_options: APInvoiceFilters
  source_coverage: SourceCoverageItem[]
  governance: APGovernance
  deferred_capabilities: DeferredCapability[]
  warnings: string[]
}

export interface APExtractedField {
  field_name: string
  label: string
  value: string | number | boolean | null
  normalized_value: string | number | boolean | null
  confidence: number | null
  source: string
  page: number | null
  location: string | null
  validation_status: string
  explanation: string
  authority: string
  rule_version: string | null
}

export interface APExceptionEvidence {
  code: string
  label: string
  severity: string
  explanation: string
  evidence: string[]
  source: string | null
}

export interface APDuplicateEvidence {
  candidate_id: string
  candidate_ap_invoice_id: string
  candidate_invoice_number: string | null
  candidate_vendor_name: string | null
  candidate_amount: number | null
  confidence: number | null
  match_factors: string[]
  amount_corroboration: string
  date_corroboration: string
  explanation: string
}

export interface APTimelineEvent {
  event_id: string
  event_type: string
  label: string
  occurred_at: string | null
  recorded_at: string
  source: string
  actor: string | null
  details: string
  source_evidence_sha256: string | null
}

export interface APSourceDocument {
  job_id: string
  result_id: string
  file_name: string
  file_endpoint: string
  content_type: string | null
  document_type: string
  status: string
  classifier: string | null
  parser_name: string | null
  parser_version: string | null
  classification_confidence: number | null
  classification_evidence: string[]
  created_at: string | null
  updated_at: string | null
  result_created_at: string | null
  result_updated_at: string | null
}

export interface APInvoiceDetailResponse extends APInvoiceSummary {
  contract_version: string
  source_document: APSourceDocument
  extracted_fields: APExtractedField[]
  exceptions: APExceptionEvidence[]
  duplicate_evidence: APDuplicateEvidence[]
  timeline: APTimelineEvent[]
  source_coverage: SourceCoverageItem[]
  governance: APGovernance
  deferred_capabilities: DeferredCapability[]
  provenance: string[]
  source_evidence_sha256: string
  evidence_revision_count: number
}

export interface APErpLedgerRefreshResponse {
  job_id: string
  status: 'queued' | 'completed'
}

export interface APSyncResponse {
  contract_version: string
  status: string
  imported_count: number
  updated_count: number
  unchanged_count: number
  skipped_count: number
  eligible_job_count: number
  duplicate_candidate_count: number
  imported_event_count: number
  sync_id: string
  started_at: string
  completed_at: string
  message: string
  source_coverage: SourceCoverageItem[]
  governance: APGovernance
  deferred_capabilities: DeferredCapability[]
  warnings: string[]
}

export type APVendorInvoiceDocumentStatus =
  | 'uploaded'
  | 'processing'
  | 'completed'
  | 'failed'

export interface APVendorInvoiceDocumentJob {
  job_id: string
  original_file_name: string
  stored_file_name: string
  content_type: string
  file_size_bytes: number
  source_sha256: string | null
  intake_document_type: string | null
  intake_source: string | null
  duplicate_of_job_id: string | null
  document_type: string
  confidence: number
  status: APVendorInvoiceDocumentStatus
  message: string
  created_at: string
  updated_at: string
}

export interface APVendorInvoiceDatasetPage {
  jobs: APVendorInvoiceDocumentJob[]
  total: number
  limit: number
  offset: number
}

export interface APVendorInvoiceEvidenceCandidate {
  field_name?: string
  value?: unknown
  source?: string | null
  page?: number | null
  location?: string | null
  confidence?: number | null
  source_method?: string | null
  pairing_method?: string | null
}

export interface APVendorInvoiceFieldEvidence {
  field_name: string
  value: string | number | null
  source: string
  page: number | null
  location: string | null
  confidence: number | null
  authority: string
  rule_version: string | null
  validation_status: string
  candidate_count?: number
  observation_count?: number
  pairing_method?: string
  evidence_fragments?: Array<{
    role: string
    fragment_id: string | null
    text: string | null
    bbox: number[] | null
    source_method: string | null
    confidence: number | null
  }>
  observations?: APVendorInvoiceEvidenceCandidate[]
  candidates?: APVendorInvoiceEvidenceCandidate[]
}

export interface APVendorInvoiceDocumentResult {
  job: APVendorInvoiceDocumentJob
  classifier: string
  classification_evidence: string[]
  extraction: {
    extraction_version?: string
    ocr_profile_version?: string
    ocr_engine?: string | null
    ocr_engine_version?: string | null
    ocr_attempted_pages?: number[]
    ocr_completed_pages?: number[]
    ocr_failed_pages?: number[]
    ocr_average_confidence?: number | null
    pages?: Array<{
      page_number?: number
      text_source?: string
      ocr_status?: string
      [key: string]: unknown
    }>
    native_text_pages?: number[]
    ocr_text_pages?: number[]
    text_source_summary?: 'native_pdf_text' | 'local_tesseract_ocr' | 'mixed_native_and_ocr' | 'unavailable'
    warnings?: string[]
    [key: string]: unknown
  }
  parsed: {
    parser?: string
    parser_version?: string
    field_rule_version?: string
    fields?: Record<string, unknown>
    field_evidence?: Record<string, APVendorInvoiceFieldEvidence>
    ambiguous_fields?: Record<string, Array<Record<string, unknown>>>
    review_required?: boolean
    key_field_readiness?: {
      status?: 'key_fields_recognized' | 'key_fields_need_review' | string
      text_source?: string
      required_fields?: string[]
      missing_or_ambiguous_fields?: string[]
      message?: string
    }
    field_summary?: {
      quality?: string
      text_source?: string
      business_field_count?: number
      available_count?: number
      available_fields?: string[]
      ambiguous_fields?: string[]
      present_without_value_fields?: string[]
      unavailable_fields?: string[]
      key_fields?: Record<string, string>
      message?: string
    }
    validation?: { status?: string; errors?: string[]; warnings?: string[] }
    [key: string]: unknown
  }
  processing_run_id: string | null
  processing_run_number: number | null
  processor_version: string | null
  source_sha256: string | null
}

export interface APVendorInvoiceIntakeResponse {
  intake_status: 'processed' | 'failed'
  job: APVendorInvoiceDocumentJob
  result: APVendorInvoiceDocumentResult | null
  review_required: boolean
  message: string
}

export interface APVendorInvoiceProcessingRun {
  processing_run_id: string
  job_id: string
  run_number: number
  processor_version: string
  source_sha256: string | null
  status: 'completed' | 'failed'
  classifier: string | null
  parser: string | null
  parser_version: string | null
  ocr_engine: string | null
  ocr_engine_version: string | null
  message: string
  created_at: string
  completed_at: string
}

export interface APVendorInvoiceReview {
  review: {
    job_id: string
    processing_run_id: string | null
    status: string
    reviewer: string
    notes: string
    corrected_fields: Record<string, unknown>
    unavailable_fields: string[]
    created_at: string
    updated_at: string
  }
  history: Array<{
    id: number
    job_id: string
    processing_run_id: string | null
    status: string
    reviewer: string
    notes: string
    corrected_fields: Record<string, unknown>
    unavailable_fields: string[]
    created_at: string
  }>
}

export interface APControlGate {
  code: string
  label: string
  status: 'passed' | 'blocked' | 'unavailable'
  source: string | null
  explanation: string
}

export interface APSegregationCheck {
  code: string
  label: string
  status: 'passed' | 'blocked' | 'not_applicable'
  identities: string[]
  explanation: string
}

export interface APControlReview {
  review_id: string
  control_case_id: string
  reviewer_identity: string
  disposition: 'evidence_ready' | 'needs_information' | 'duplicate_review_required' | 'not_ready'
  notes: string
  created_at: string
  actor_identity_source: 'operator_supplied'
  actor_authority_status: 'not_independently_verified'
  approval_effect: 'none'
  payment_effect: 'none'
}

export interface APControlCaseSummary {
  control_case_id: string
  ap_invoice_id: string
  intended_action: 'approval_review' | 'payment_preparation'
  requested_by: string
  assigned_reviewer: string
  payment_preparer: string | null
  notes: string
  created_at: string
  invoice: APInvoiceSummary
  control_status: 'control_review_pending' | 'evidence_ready' | 'needs_information' | 'duplicate_review_required' | 'not_ready'
  latest_review: APControlReview | null
  document_evidence_ready: boolean
  evidence_current: boolean
  evidence_gates: APControlGate[]
  segregation_checks: APSegregationCheck[]
  approval_authority_status: 'unavailable'
  payment_authorization_status: 'unavailable'
  can_enter_governed_approval: false
  can_authorize_payment: false
}

export interface APControlCaseDetail extends APControlCaseSummary {
  contract_version: string
  reviews: APControlReview[]
  source_evidence_sha256: string
  evidence_snapshot: Record<string, unknown>
  evidence_snapshot_sha256: string
  source_coverage: SourceCoverageItem[]
  governance: APGovernance
  deferred_capabilities: DeferredCapability[]
  warnings: string[]
}

export interface APControlCaseListResponse {
  contract_version: string
  items: APControlCaseSummary[]
  total: number
  limit: number
  offset: number
  source_coverage: SourceCoverageItem[]
  governance: APGovernance
  deferred_capabilities: DeferredCapability[]
  warnings: string[]
}

export interface APVendorTermsReferenceRecord {
  terms_code: string
  discount_percent: number
  num_periods: number | null
  num_months: number | null
  num_days: number | null
  second_period: number | null
  third_period: number | null
  next_period: number | null
  day_of_month: number | null
  cutoff_day: number | null
  description: string
  updated_at: string
}

export interface APVendorTermsReferenceListResponse {
  items: APVendorTermsReferenceRecord[]
}

export interface APVendorTermsReferenceUpsert {
  discount_percent: number
  num_periods: number | null
  num_months: number | null
  num_days: number | null
  second_period: number | null
  third_period: number | null
  next_period: number | null
  day_of_month: number | null
  cutoff_day: number | null
  description: string
}

export type WarehouseApprovalStatus =
  | 'needs_approval'
  | 'approved_by_warehouse'
  | 'approved_and_entered_by_ap'

export interface APWarehouseApprovalItem {
  vendor_number: string
  vendor_name: string | null
  invoice_number: string
  invoice_date: string | null
  due_date: string | null
  amount_invoiced: number
  amount_discount: number
  on_hold: boolean
  gl_account: string | null
  gl_division: string | null
  gl_department: string | null
  status: WarehouseApprovalStatus
  last_actor_identity: string | null
  last_action_at: string | null
  linked_ap_invoice_id: string | null
}

export interface APWarehouseApprovalQueueResponse {
  contract_version: string
  division: string | null
  available_divisions: string[]
  needs_approval: APWarehouseApprovalItem[]
  approved_by_warehouse: APWarehouseApprovalItem[]
  approved_and_entered_by_ap: APWarehouseApprovalItem[]
  governance: APGovernance
}

export interface APWarehouseApprovalActionCreate {
  vendor_number: string
  invoice_number: string
  to_status: WarehouseApprovalStatus
  actor_identity: string
  notes?: string
}

export interface APGLCodingSuggestion {
  gl_division: string
  gl_account: string
  gl_department: string | null
  gl_account_description: string | null
  invoice_count: number
  match_percent: number
}

export interface APGLCodingSuggestionsResponse {
  contract_version: string
  generated_at: string
  vendor_number: string
  coded_year: number | null
  total_coded_invoice_count: number
  suggestions: APGLCodingSuggestion[]
  excluded_structural_accounts: string[]
  governance: {
    source_authority: string
    erp_access: string
    erp_write: boolean
    recommendation_effect: string
    decision_effect: string
    execution_effect: string
    automatic_selection: boolean
    statements: string[]
  }
  warnings: string[]
}

export interface APWarehouseApprovalActionRecord {
  action_id: string
  vendor_number: string
  invoice_number: string
  from_status: WarehouseApprovalStatus
  to_status: WarehouseApprovalStatus
  actor_identity: string
  actor_identity_source: 'operator_supplied' | 'sso'
  notes: string
  created_at: string
}

export interface APVendorInsight {
  vendor_key: string
  identity_basis: 'vendor_number' | 'vendor_name' | 'unidentified'
  vendor_number: string | null
  vendor_name: string | null
  invoice_count: number
  known_total_count: number
  extracted_total_amount: number
  due_date_count: number
  review_required_count: number
  exception_invoice_count: number
  duplicate_candidate_invoice_count: number
  ocr_average_confidence: number | null
  evidence_alerts: string[]
}

export interface APCashWindow {
  code: 'past_due' | 'due_today' | 'next_7_days' | 'days_8_to_14' | 'days_15_to_30' | 'beyond_30_days' | 'due_date_unavailable'
  label: string
  invoice_count: number
  known_amount_count: number
  extracted_amount: number
  explanation: string
}

export interface APVendorCashCoverage {
  imported_invoice_count: number
  identified_vendor_invoice_count: number
  due_date_invoice_count: number
  known_amount_invoice_count: number
  review_required_invoice_count: number
  source_as_of: string | null
}

export interface APVendorCashGovernance {
  classification: 'document_evidence_analytics'
  current_payable_status_known: false
  cash_requirement_authority: 'not_authoritative'
  vendor_performance_score: false
  payment_proposal: false
  payment_authorization: false
  erp_write: false
  statements: string[]
}

export interface APVendorCashIntelligenceResponse {
  contract_version: string
  generated_at: string
  as_of_date: string
  coverage: APVendorCashCoverage
  vendors: APVendorInsight[]
  cash_windows: APCashWindow[]
  governance: APVendorCashGovernance
  source_coverage: SourceCoverageItem[]
  deferred_capabilities: DeferredCapability[]
  warnings: string[]
}

export interface APCashScenario {
  cash_scenario_id: string
  as_of_date: string
  horizon_days: number
  horizon_end_date: string
  include_review_required: boolean
  prepared_by: string
  rationale: string
  created_at: string
  included_invoice_count: number
  included_known_amount_count: number
  extracted_amount: number
  excluded_review_required_count: number
  excluded_missing_due_date_count: number
  excluded_missing_amount_count: number
  actor_identity_source: 'operator_supplied'
  actor_authority_status: 'not_independently_verified'
  scenario_classification: 'analytical_scenario'
  current_payable_status_known: false
  approval_effect: 'none'
  payment_effect: 'none'
  erp_write: false
  evidence_snapshot: Record<string, unknown>
  evidence_snapshot_sha256: string
}

export interface APCashScenarioHistoryResponse {
  contract_version: string
  count: number
  scenarios: APCashScenario[]
  governance: APVendorCashGovernance
  warnings: string[]
}

export interface CreateAPCashScenarioRequest {
  as_of_date: string
  horizon_days: 7 | 14 | 30 | 60 | 90
  include_review_required: boolean
  prepared_by: string
  rationale: string
}

export type APExceptionActionDisposition =
  | 'investigating'
  | 'information_requested'
  | 'document_correction_needed'
  | 'duplicate_review_complete'
  | 'ready_for_control_case'

export type APExceptionWorkState =
  | 'unworked'
  | 'follow_up_scheduled'
  | 'follow_up_overdue'
  | 'source_changed'
  | 'documented_for_next_step'
  | 'documented'

export interface APExceptionReason {
  code: string
  label: string
  severity: 'high' | 'medium' | 'low' | 'review'
  source: 'saved_exception' | 'duplicate_candidate' | 'ocr_review' | 'source_review_flag'
  explanation: string
}

export interface APExceptionAction {
  action_id: string
  ap_invoice_id: string
  disposition: APExceptionActionDisposition
  owner_identity: string
  actor_identity: string
  notes: string
  follow_up_date: string | null
  created_at: string
  source_evidence_sha256: string
  actor_identity_source: 'operator_supplied'
  owner_identity_source: 'operator_supplied'
  authority_status: 'not_independently_verified'
  action_classification: 'professional_workflow_metadata'
  approval_effect: 'none'
  payment_effect: 'none'
  erp_write: false
  evidence_snapshot: Record<string, unknown>
  evidence_snapshot_sha256: string
}

export interface APExceptionQueueItem {
  queue_rank: number
  ap_invoice_id: string
  vendor_number: string | null
  vendor_name: string | null
  invoice_number: string | null
  invoice_date: string | null
  due_date: string | null
  total_amount: number | null
  source_file_name: string
  source_as_of: string
  source_evidence_sha256: string
  exception_count: number
  duplicate_candidate_count: number
  ocr_review_required: boolean
  reasons: APExceptionReason[]
  work_state: APExceptionWorkState
  latest_action: APExceptionAction | null
}

export interface APExceptionOperationsSummary {
  queue_count: number
  unworked_count: number
  follow_up_scheduled_count: number
  follow_up_overdue_count: number
  source_changed_count: number
  documented_count: number
  duplicate_review_count: number
  ocr_review_count: number
  known_amount_count: number
  extracted_amount: number
}

export interface APExceptionOperationsGovernance {
  classification: 'professional_exception_work_management'
  queue_ordering: 'deterministic_evidence_and_follow_up_state'
  approved_sla: false
  authenticated_assignment: false
  automatic_resolution: false
  approval_effect: 'none'
  payment_effect: 'none'
  erp_write: false
  statements: string[]
}

export interface APExceptionOperationsResponse {
  contract_version: string
  generated_at: string
  as_of_date: string
  summary: APExceptionOperationsSummary
  items: APExceptionQueueItem[]
  source_coverage: SourceCoverageItem[]
  governance: APExceptionOperationsGovernance
  deferred_capabilities: DeferredCapability[]
  warnings: string[]
}

export interface APExceptionActionHistoryResponse {
  contract_version: string
  ap_invoice_id: string
  count: number
  actions: APExceptionAction[]
  governance: APExceptionOperationsGovernance
}

export interface CreateAPExceptionActionRequest {
  disposition: APExceptionActionDisposition
  owner_identity: string
  actor_identity: string
  notes: string
  follow_up_date?: string | null
}

export interface CreateAPControlCaseRequest {
  intended_action: 'approval_review' | 'payment_preparation'
  requested_by: string
  assigned_reviewer: string
  payment_preparer?: string | null
  notes: string
}

export interface CreateAPControlReviewRequest {
  reviewer_identity: string
  disposition: 'evidence_ready' | 'needs_information' | 'duplicate_review_required' | 'not_ready'
  notes: string
}

export interface APInvoiceQuery {
  query?: string
  status?: string
  exception?: boolean
  duplicate?: boolean
  limit?: number
  offset?: number
}

export type APWorkspaceView =
  | 'overview'
  | 'vendor_invoice_capture'
  | 'invoices'
  | 'ocr'
  | 'exceptions'
  | 'exception_operations'
  | 'duplicates'
  | 'approvals'
  | 'warehouse_approval'
  | 'payment_controls'
  | 'vendor_intelligence'
  | 'cash_planning'
  | 'spend_intelligence'
  | 'erp_evidence'

export interface ERPEvidenceCoverageItem {
  key: string
  label: string
  status: string
  source: string | null
  as_of: string | null
  record_count: number | null
  complete: boolean | null
  explanation: string
}

export interface ERPEvidenceGovernance {
  source_authority: string
  erp_access: 'read_only'
  erp_write: false
  recommendation_effect: 'none'
  decision_effect: 'none'
  execution_effect: 'none'
  automatic_selection: false
  statements: string[]
}

export interface APMappingCandidate {
  category: string
  table_name: string
  required_fields_matched: string[]
  missing_fields: string[]
  evidence_columns: string[]
  selection_state: string
  source_rows_read: false
}

export interface APMappingReadinessResponse {
  contract_version: string
  generated_at: string
  source_schema: string
  schema_catalog_status: string
  catalog_complete: boolean
  inspected_column_count: number
  categories: Array<{
    key: string
    label: string
    status: string
    required_fields: string[]
    candidates: APMappingCandidate[]
    explanation: string
  }>
  governance: ERPEvidenceGovernance
  next_required_action: string
  warnings: string[]
}

export interface APBoundedEvidenceCollection {
  status: string
  retrieved_count: number
  row_limit: number
  complete: boolean
  explanation: string
}

export interface APERPInvoiceSearchResponse {
  contract_version: string
  generated_at: string
  query: {
    vendor_query: string | null
    invoice_number: string | null
    row_limit: number
  }
  vendor_candidates: Array<{
    vendor_number: string
    vendor_name: string | null
    sort_name: string | null
    match_basis: Array<'exact_vendor_number' | 'vendor_name_contains'>
  }>
  invoice_candidates: Array<{
    vendor_number: string
    vendor_name: string | null
    invoice_number: string
    posted_header_row_count: number
    latest_invoice_date: string | null
    latest_due_date: string | null
  }>
  vendor_candidate_complete: boolean
  invoice_candidate_complete: boolean
  source_references: Array<{
    source_system: string
    source_schema: string
    source_object: string
    access: 'read_only'
    retrieved_at: string
    contract_version: string
  }>
  governance: ERPEvidenceGovernance
  sensitive_fields_excluded: string[]
  evidence_sha256: string
  warnings: string[]
}

export interface APERPEvidenceResponse {
  contract_version: string
  generated_at: string
  lookup_identity: {
    lookup_origin: 'local_imported_invoice' | 'direct_erp_search'
    vendor_number: string
    invoice_number: string
    local_ap_invoice_id: string | null
  }
  local_invoice: {
    ap_invoice_id: string
    vendor_number: string | null
    vendor_name: string | null
    invoice_number: string | null
    invoice_date: string | null
    due_date: string | null
    purchase_order_number: string | null
    total_amount: number | null
    source_evidence_sha256: string
  } | null
  vendor_master: {
    status: string
    vendor_number: string
    vendor_name: string | null
    sort_name: string | null
    vendor_type_code: string | null
    delete_code: string | null
    terms_code: string | null
    po_required_code: string | null
    no_ap_from_receipt_code: string | null
    default_gl_division: string | null
    default_gl_department: string | null
    default_gl_account: string | null
    last_paid_date: string | null
    last_paid_amount: number | null
    explanation: string
  }
  posted_headers: Array<Record<string, string | number | null>>
  posted_header_collection: APBoundedEvidenceCollection
  posted_details: Array<Record<string, string | number | null>>
  posted_detail_collection: APBoundedEvidenceCollection
  gl_distributions: Array<Record<string, string | number | null>>
  gl_distribution_collection: APBoundedEvidenceCollection
  po_receiving_match: Array<Record<string, string | number | null>>
  po_receiving_match_collection: APBoundedEvidenceCollection
  input_headers: Array<Record<string, string | number | null>>
  input_header_collection: APBoundedEvidenceCollection
  input_details: Array<Record<string, string | number | null>>
  input_detail_collection: APBoundedEvidenceCollection
  input_payment_splits: Array<Record<string, string | number | null>>
  input_payment_collection: APBoundedEvidenceCollection
  coverage: ERPEvidenceCoverageItem[]
  source_references: Array<{
    source_system: string
    source_schema: string
    source_object: string
    access: 'read_only'
    retrieved_at: string
    contract_version: string
  }>
  governance: ERPEvidenceGovernance
  sensitive_fields_excluded: string[]
  evidence_sha256: string
  warnings: string[]
}

export type APSpendReadinessStatus = 'available' | 'partial' | 'unavailable' | 'degraded'
export type APSpendQuestionStatus =
  | 'answered'
  | 'needs_clarification'
  | 'unavailable'
  | 'no_evidence'
  | 'degraded'

export interface APSpendMappingCheck {
  key: string
  label: string
  status: APSpendReadinessStatus
  source: string
  required_fields: string[]
  missing_fields: string[]
  incompatible_fields: string[]
  runtime_data_type: string | null
  explanation: string
}

export interface APSpendDateBasisReadiness {
  key: string
  label: string
  status: APSpendReadinessStatus
  source_fields: string[]
  explanation: string
}

export interface APSpendReadinessResponse {
  contract_version: string
  generated_at: string
  status: APSpendReadinessStatus
  source_schema: string
  mapping_checks: APSpendMappingCheck[]
  date_bases: APSpendDateBasisReadiness[]
  measure: {
    key: 'signed_posted_ap_gl_distribution_amount'
    label: 'Signed posted AP GL-distribution amount'
    source_table: 'PMGLDS'
    amount_field: 'PMGAMTINV'
    sign_treatment: 'signed_as_stored'
    ranking_basis: 'net_signed_amount_descending'
    interpretation: string
    excluded_meanings: string[]
  }
  local_data_dictionary_status: APSpendReadinessStatus
  local_data_dictionary_path: string | null
  product_owner_mappings_needed: string[]
  governance: ERPEvidenceGovernance
  warnings: string[]
}

export interface APSpendParsedQuestion {
  parser_version: string
  original_question: string
  normalized_question: string
  intent: 'total_spend' | 'top_vendor' | 'top_vendor_by_month' | null
  division: string | null
  account: string | null
  time_basis: 'erp_accounting_year' | 'erp_accounting_period' | 'calendar_invoice_date' | null
  year: number | null
  month: number | null
  accounting_period: number | null
  range_start: string | null
  range_end_exclusive: string | null
  interpretation_notes: string[]
  missing_slots: string[]
  ambiguous_slots: string[]
  unavailable_slots: string[]
}

export interface APSpendAmountSummary {
  distribution_row_count: number
  amount_available_row_count: number
  missing_amount_row_count: number
  invoice_identity_count: number
  vendor_count: number
  positive_distribution_amount: number
  negative_distribution_amount: number
  net_signed_amount: number
}

export interface APSpendVendorRank {
  rank: number
  vendor_number: string
  vendor_name: string | null
  distribution_row_count: number
  amount_available_row_count: number
  missing_amount_row_count: number
  invoice_identity_count: number
  positive_distribution_amount: number
  negative_distribution_amount: number
  net_signed_amount: number
}

export interface APSpendMonthlyPeriod {
  calendar_year: number
  calendar_month: number
  range_start: string
  range_end_exclusive: string
  status: 'available' | 'no_evidence'
  leaders: APSpendVendorRank[]
  ranking_complete: boolean
  leader_set_complete: boolean
  explanation: string
}

export interface APSpendQuestionResponse {
  contract_version: string
  generated_at: string
  evidence_as_of: string | null
  status: APSpendQuestionStatus
  answer_text: string
  parsed: APSpendParsedQuestion
  readiness: APSpendReadinessResponse
  total: APSpendAmountSummary | null
  ranking: APSpendVendorRank[]
  leaders: APSpendVendorRank[]
  monthly_periods: APSpendMonthlyPeriod[]
  ranking_row_limit: number
  monthly_period_limit: number
  monthly_leader_limit: number
  ranking_complete: boolean | null
  leader_set_complete: boolean | null
  evidence_consistency:
    | 'single_read_only_consistent_snapshot'
    | 'no_financial_query'
    | 'consistent_snapshot_query_failed'
  coverage: ERPEvidenceCoverageItem[]
  source_references: Array<{
    source_system: string
    source_schema: string
    source_object: string
    access: 'read_only'
    retrieved_at: string
    contract_version: string
  }>
  governance: ERPEvidenceGovernance
  evidence_sha256: string
  warnings: string[]
  suggested_questions: string[]
}

export interface AccountsPayableWorkspaceProps {
  initialQuery?: string
}
