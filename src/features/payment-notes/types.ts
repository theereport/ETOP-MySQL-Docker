export type AsyncStatus = 'idle' | 'loading' | 'ready' | 'error'

export type RouteReferenceState = 'active' | 'inactive' | 'invalid'

export interface RouteReferenceQuality {
  row_count: number
  unique_mapping_count: number
  unique_route_count: number | null
  duplicate_mapping_count: number
  conflicting_route_count: number
  unresolved_store_count: number | null
  warnings: string[]
}

export interface RouteReferenceSummary {
  reference_id: string
  source_file_name: string
  source_sha256: string
  version_label: string
  created_at: string
  activated_at: string | null
  state: RouteReferenceState | string
  quality: RouteReferenceQuality
}

export interface RouteReferenceStatus {
  ready: boolean
  active_reference: RouteReferenceSummary | null
  blocking_reasons: string[]
}

export interface RouteReferenceListResponse {
  items: RouteReferenceSummary[]
  total: number
}

export type PaymentNotesRunState =
  | 'INGESTED'
  | 'BALANCE_FAILED'
  | 'REVIEW_REQUIRED'
  | 'ARITHMETICALLY_BALANCED'
  | 'LOCAL_REVIEW_COMPLETE'
  | string

export type MatchClassification =
  | 'AUTO_MATCHED'
  | 'LOCAL_REVIEW_ACCEPTED_MATCH'
  | 'CHECK_MATCH_AMOUNT_MISMATCH'
  | 'SUGGESTED_REVIEW'
  | 'AMBIGUOUS_MATCH'
  | 'NO_MATCH'
  | 'LOCALLY_RECORDED_UNMATCHED'
  | string

export type SignatureState =
  | 'SIGNED_EVIDENCE'
  | 'SIGNATURE_ROW_NO_FILE'
  | 'NO_SIGNATURE_EVIDENCE'
  | 'SIGNATURE_UNDETERMINED'
  | string

export interface PaymentNotesCountSummary {
  physical_item_count: number | null
  physical_total_cents: number | null
  matched_count: number | null
  matched_total_cents: number | null
  accepted_unmatched_count: number | null
  accepted_unmatched_total_cents: number | null
  unresolved_count: number | null
  unresolved_total_cents: number | null
  blocking_exception_count: number | null
}

export interface PaymentNotesRunSummary {
  run_id: string
  source_file_name: string
  source_sha256: string
  created_at: string
  date_from: string
  date_to: string
  business_timezone: string
  status: PaymentNotesRunState
  counts_final: boolean
  recommendation_only: boolean
  erp_write_performed: boolean
  route_reference_id: string
  route_reference_version: string
  route_reference_sha256: string
  ruleset_version: string
  summary: PaymentNotesCountSummary
}

export interface PaymentNotesRunListResponse {
  items: PaymentNotesRunSummary[]
  total: number
  limit: number
  offset: number
}

export interface DepositSummary {
  deposit_key: string
  deposit_no: string
  bank_location_raw: string
  canonical_location_code: string | null
  payment_location_key: string | null
  create_date: string
  physical_item_count: number
  bank_total_cents: number
  virtual_credit_count: number
  virtual_credit_amount_cents: number
  virtual_credit_difference_cents: number
  matched_count: number
  matched_total_cents: number
  accepted_unmatched_count: number
  accepted_unmatched_total_cents: number
  unresolved_count: number
  unresolved_total_cents: number
  blocking_exception_count: number
  balance_status: 'ARITHMETICALLY_BALANCED' | 'BALANCE_FAILED'
  status: PaymentNotesRunState
  exception_codes: string[]
}

export interface MatchFeature {
  code: string
  label: string
  matched: boolean
  points: number
  explanation: string
}

export interface SignatureEvidence {
  rrn: string
  invoice_number: string
  signer_name: string | null
  file_name: string | null
  created_at: string | null
  uploaded_at: string | null
  state: SignatureState
}

export interface PaymentNoteCandidate {
  payment_id: string
  customer_number: string | null
  route: string
  payment_type: string
  raw_check_number: string | null
  normalized_check_number: string | null
  amount_cents: number
  invoices: string[]
  raw_invoices: string | null
  received: string | null
  received_at: string | null
  created_at: string | null
  score: number | null
  tier: string
  eligible_for_automatic_match: boolean
  matched_factors: MatchFeature[]
  conflicts: string[]
  rejection_reasons: string[]
  signature_state: SignatureState
  signatures: SignatureEvidence[]
}

export interface CrossRunReuseEvidence {
  payment_id: string
  prior_run_ids: string[]
  prior_item_ids: string[]
  source_types: string[]
}

export type ReviewDecision = 'accept_candidate' | 'leave_unmatched' | 'hold'

export interface ItemReview {
  review_id: string
  decision: ReviewDecision
  selected_payment_id: string | null
  reason: string
  actor_name: string
  created_at: string
  version: number
  active: boolean
}

export interface BankItem {
  bank_item_id: string
  fingerprint: string
  source_line: number
  deposit_key: string
  deposit_no: string
  item_type: string
  bank_location_raw: string
  canonical_location_code: string | null
  payment_location_key: string | null
  raw_check_number: string | null
  normalized_check_number: string | null
  amount_cents: number
  candidate_count: number
  candidate_total_count: number
  candidate_display_cap: number
  candidate_population_complete: boolean
  candidate_population_truncated: boolean
  classification: MatchClassification
  selected_payment_id: string | null
  recommendation_score: number | null
  recommendation_tier: string | null
  strongest_mismatch: string | null
  exception_codes: string[]
  explanation: string[]
  route_scope: string[]
  signature_state: SignatureState
  signature_count: number
  current_review: ItemReview | null
  candidates: PaymentNoteCandidate[]
  cross_run_reuse_evidence: CrossRunReuseEvidence[]
}

export interface ExpectedPaymentQueryProvenance {
  source_object: 'KMTDTA.WHSIGPAY'
  store_number: string
  routes: string[]
  date_from: string
  date_to: string
  retrieved_at: string
  row_limit: number
  returned_count: number
  complete: boolean
  canonical_evidence_sha256: string
  error: string | null
}

export interface SignatureQueryProvenance {
  source_object: 'KMTDTA.WHSIGIMG'
  retrieved_at: string
  row_limit: number
  pair_count: number
  returned_count: number
  complete: boolean
  canonical_evidence_sha256: string
  error: string | null
}

export interface PaymentNotesERPProvenance {
  contract_version: string
  snapshot_mode: 'independent_bounded_read_only_queries'
  expected_payment_queries: ExpectedPaymentQueryProvenance[]
  signature_queries: SignatureQueryProvenance[]
  expected_payment_query_count: number
  signature_query_count: number
  complete: boolean
}

export interface PaymentNotesRunDetail {
  run: PaymentNotesRunSummary
  deposits: DepositSummary[]
  items: BankItem[]
  warnings: string[]
  source_complete: boolean
  route_reference_ready: boolean
  erp_provenance: PaymentNotesERPProvenance
}

export interface CreateItemReviewRequest {
  decision: ReviewDecision
  selected_payment_id?: string
  reason: string
  idempotency_key: string
}

export interface ReviewResponse {
  item: BankItem
  run: PaymentNotesRunSummary
  detail: PaymentNotesRunDetail
}
