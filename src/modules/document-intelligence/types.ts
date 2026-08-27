export type DocumentJobStatus =
  | 'uploaded'
  | 'processing'
  | 'completed'
  | 'failed'

export type DocumentType =
  | 'pnc_lockbox'
  | 'bank_report'
  | 'vendor_invoice'
  | 'statement'
  | 'unknown'

export type DocumentJob = {
  job_id: string
  original_file_name: string
  stored_file_name: string
  content_type: string
  file_size_bytes: number
  source_sha256?: string | null
  intake_document_type?: DocumentType | null
  intake_source?: string | null
  duplicate_of_job_id?: string | null
  document_type: DocumentType
  confidence: number
  status: DocumentJobStatus
  message: string
  created_at: string
  updated_at: string
}

export type DocumentJobListResponse = {
  jobs: DocumentJob[]
  total: number
  limit: number
  offset: number
}

export type DocumentResult = {
  job: DocumentJob
  classifier: string
  classification_evidence: string[]
  extraction: Record<string, unknown>
  parsed: Record<string, unknown>
  processing_run_id?: string | null
  processing_run_number?: number | null
  processor_version?: string | null
  source_sha256?: string | null
}

export type DocumentHealth = {
  status: string
  module: string
  version: string
  database_exists: boolean
  upload_directory_exists: boolean
  job_count: number
  capabilities: Record<string, boolean>
}

export type DocumentParser = {
  name?: string
  key?: string
  document_type?: string
  description?: string
  [key: string]: string | undefined
}

export type TrainingProfile = {
  id: string
  name: string
  documentType: DocumentType
  parserKey: string
  outputTemplate: string
  destination: string
  signals: string[]
  createdAt: string
  updatedAt: string
}


export type DocumentReviewStatus =
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'needs_correction'
  | 'needs_learning'

export type DocumentReview = {
  job_id: string
  processing_run_id: string | null
  status: DocumentReviewStatus
  reviewer: string
  notes: string
  corrected_fields: Record<string, unknown>
  unavailable_fields: string[]
  created_at: string
  updated_at: string
}

export type DocumentReviewHistoryItem = {
  id: number
  job_id: string
  processing_run_id: string | null
  status: DocumentReviewStatus
  reviewer: string
  notes: string
  corrected_fields: Record<string, unknown>
  unavailable_fields: string[]
  created_at: string
}

export type DocumentReviewResponse = {
  review: DocumentReview
  history: DocumentReviewHistoryItem[]
}

export type SaveDocumentReviewRequest = {
  expected_processing_run_id: string
  status: DocumentReviewStatus
  reviewer: string
  notes: string
  corrected_fields: Record<string, unknown>
  unavailable_fields?: string[]
}


export type LearningExample = { id:number; job_id:string; document_type:string; field_name:string; original_value:unknown; corrected_value:unknown; reviewer:string; source_status:DocumentReviewStatus; fingerprint:string; created_at:string }
export type LearningSummary = { total_examples:number; unique_documents:number; unique_fields:number; field_counts:Record<string,number>; document_type_counts:Record<string,number>; recent_examples:LearningExample[] }
export type LearningExampleListResponse = { examples:LearningExample[]; total:number }
export type LearningSummaryResponse = { summary:LearningSummary }
export type GenerateLearningExamplesResponse = { created:number; skipped:number; examples:LearningExample[] }


export type LockboxAllocation = {
  invoice_number: string
  net_invoice_amount: number
  invoice_page: string
  confidence: number
  raw_invoice_candidates?: string[]
  extraction_source?: string
  ocr_psm?: number | null
  allocation_kind?: 'invoice' | 'service_charge'
  erp_transaction_type?: string
  open_item_key?: string
  normalized_invoice_number?: string
  invoice_count?: number | null
  customer_number?: string
}

export type LockboxTransaction = {
  transaction_id: string
  envelope_number: number | null
  lockbox: string
  date: string
  batch: number | null
  batch_item: number | null
  check_number: string
  check_amount: number
  aba_routing: string
  account_number: string
  customer_number?: string
  printed_customer_number?: string
  customer_name: string
  customer_phone?: string
  phone_number?: string
  customer_address_line_1?: string
  customer_address_line_2?: string
  address_line_1?: string
  address_line_2?: string
  customer_city?: string
  city?: string
  customer_state?: string
  state?: string
  customer_postal_code?: string
  customer_zip?: string
  postal_code?: string
  allocations: LockboxAllocation[]
  allocation_total: number
  difference: number
  balanced: boolean
  status: 'balanced' | 'review_required' | 'no_remittance'
  check_page: number | null
  remittance_pages: number[]
  remittance_pages_examined?: number[]
  remittance_candidate_pages?: number[]
  ocr_attempted_pages?: number[]
  ocr_successful_pages?: number[]
  ocr_attempts?: Array<{ page: number; psm: number }>
  rejected_remittance_candidates?: Array<Record<string, unknown>>
  remittance_incomplete_pages?: number[]
  remittance_ocr_errors?: string[]
  remittance_evidence_complete?: boolean
}

export type LockboxProcessingResult = {
  job_id: string
  parser_version?: string
  extraction_version?: string
  pnc_lockbox_header_rule_version?: string
  source_file_name: string
  lockbox: string
  transaction_date: string
  transaction_count: number
  allocation_count: number
  total_check_amount: number
  total_allocation_amount: number
  total_difference: number
  balanced_count: number
  review_count: number
  transactions: LockboxTransaction[]
  warnings: string[]
}

export type DurableLockboxReason = {
  code: string
  category: string
  label: string
  description: string
  review_guidance: string
  count?: number
}

export type DurableLockboxPreparationTransaction = {
  transaction_id: string
  ordinal: number
  state:
    | 'identified'
    | 'customer_resolving'
    | 'customer_resolved'
    | 'open_ar_loading'
    | 'open_ar_loaded'
    | 'allocation_evaluating'
    | 'prepared_balanced'
    | 'prepared_exception'
    | 'preexisting_human_disposition'
  source: Record<string, unknown>
  result: Record<string, unknown> | null
  error: Record<string, unknown> | null
  exception_analysis?: Record<string, unknown>
  retry_eligible: number | boolean
}

export type DurableLockboxPreparation = {
  job_id: string
  source_job_id: string
  source_file_hash: string
  state: string
  expected_count: number
  terminal_count: number
  balanced_count: number
  exception_count: number
  preserved_count: number
  preparation_generation: number
  rule_version: string
  service_version: string
  complete: boolean
  counts_final: boolean
  current_for_rule: boolean | null
  reconciled: boolean
  recommendation_not_decision: boolean
  can_auto_approve: boolean
  erp_write_performed: boolean
  exception_reason_summary?: {
    total_exception_count: number
    by_primary_reason: DurableLockboxReason[]
    retry_eligible_count?: number
  }
  transactions?: DurableLockboxPreparationTransaction[]
}

export type LockboxExportStatus = {
  ready: boolean
  review_count: number
  message: string
}

export type TrainingDifferenceType =
  | 'matched'
  | 'missing'
  | 'extra'
  | 'amount_error'

export type TrainingComparisonRow = {
  transaction_id: string
  difference_type: TrainingDifferenceType
  invoice_number: string
  expected_amount: number | null
  actual_amount: number | null
}

export type TrainingTransactionComparison = {
  transaction_id: string
  expected_check_amount: number
  actual_check_amount: number | null
  expected_row_count: number
  actual_row_count: number
  matched_rows: number
  missing_rows: number
  extra_rows: number
  amount_errors: number
  balanced: boolean
  accuracy: number
  differences: TrainingComparisonRow[]
}

export type TrainingSession = {
  session_id: string
  job_id: string
  dataset_type: string
  source_pdf_name: string
  ground_truth_file_name: string
  status: string
  overall_accuracy: number
  transaction_accuracy: number
  invoice_accuracy: number
  amount_accuracy: number
  expected_transactions: number
  actual_transactions: number
  matched_transactions: number
  expected_rows: number
  actual_rows: number
  matched_rows: number
  missing_rows: number
  extra_rows: number
  amount_errors: number
  created_at: string
  updated_at: string
  transactions: TrainingTransactionComparison[]
}

export type TrainingSummary = {
  total_sessions: number
  total_documents: number
  expected_rows: number
  matched_rows: number
  missing_rows: number
  extra_rows: number
  amount_errors: number
  average_accuracy: number
  latest_session: TrainingSession | null
}

export type LockboxReviewStatus =
  | 'balanced'
  | 'review_required'
  | 'no_remittance'
  | 'corrected'
  | 'held'
  | 'approved'

export type ReviewedLockboxAllocation = LockboxAllocation

export type ReviewedLockboxTransaction = Omit<LockboxTransaction, 'status'> & {
  original_allocations: ReviewedLockboxAllocation[]
  allocations: ReviewedLockboxAllocation[]
  status: LockboxReviewStatus
  reviewer: string
  notes: string
  override_reason: string
  reviewed_at: string | null
}

export type LockboxReviewResult = Omit<
  LockboxProcessingResult,
  'transactions'
> & {
  approved_count: number
  corrected_count: number
  held_count: number
  transactions: ReviewedLockboxTransaction[]
}

export type SaveLockboxTransactionReviewRequest = {
  allocations: ReviewedLockboxAllocation[]
  reviewer: string
  notes: string
  status: LockboxReviewStatus
  override_reason: string
  customer_number?: string
  customer_name?: string
  customer_phone?: string
  customer_address_line_1?: string
  customer_address_line_2?: string
  customer_city?: string
  customer_state?: string
  customer_postal_code?: string
}

export type LockboxCustomerNote = {
  note_id: number
  customer_number: string
  customer_name: string
  body: string
  author: string
  source_job_id: string
  source_transaction_id: string
  source_check_number: string
  created_at: string
}

export type LockboxCustomerNoteList = {
  customer_number: string
  customer_name: string
  notes: LockboxCustomerNote[]
}

export type AppendLockboxCustomerNoteRequest = {
  body: string
  author: string
}

export type CustomerMatchCandidate = {
  customer_number: string
  customer_name: string
  phone: string
  address_line_1: string
  address_line_2: string
  city: string
  state: string
  postal_code: string
  score: number
  confidence: number
  match_type: string
  matched_on: string[]
  matched_invoice_numbers: string[]
}

export type CustomerMatchRequest = {
  invoice_numbers?: string[]
  phone?: string
  address_line_1?: string
  city?: string
  state?: string
  postal_code?: string
  customer_name?: string
  search_text?: string
  limit?: number
}

export type CustomerMatchResponse = {
  recommended_customer: CustomerMatchCandidate | null
  candidates: CustomerMatchCandidate[]
  auto_select: boolean
  message: string
  warnings: string[]
  matching_priority: string[]
}

export type BulkInvoiceOwnerCustomer = {
  customer_number: string
  customer_name: string
  phone: string
  address_line_1: string
  address_line_2: string
  city: string
  state: string
  postal_code: string
}

export type BulkInvoiceOwnerResponse = {
  invoice_owners: Record<string, string[]>
  customers: BulkInvoiceOwnerCustomer[]
  unresolved_invoice_numbers: string[]
  warnings: string[]
  invoice_count: number
  source_query_count: number
  read_only: boolean
}

export type LinkedCustomerAccount = {
  customer_number: string
  customer_name: string
  phone: string
  address_line_1: string
  city: string
  state: string
  postal_code: string
  open_item_count: number
  is_current_customer: boolean
}

export type LinkedCustomerAccountsResponse = {
  is_enterprise: boolean
  enterprise_number: string
  accounts: LinkedCustomerAccount[]
  read_only?: boolean
}
