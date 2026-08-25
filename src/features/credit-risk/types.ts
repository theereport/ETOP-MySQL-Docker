import type { CustomerSearchResult } from '../customer360/types'

export interface CreditERPEvidenceResponse {
  contract_version: string
  generated_at: string
  customer_number: number
  customer_name: string
  current: {
    credit_limit: number
    balance: number
    erp_on_order_aggregate: number
    partial_exposure: number
    partial_available_credit: number
    terms_code: string
    terms_description: string
    last_payment_amount: number | null
    last_payment_date: string | null
  }
  open_ar: {
    status: string
    items: Array<{
      open_item_key: string
      customer_number: string
      invoice_number: string
      invoice_count: number | null
      invoice_date: string | null
      due_date: string | null
      original_amount: number
      open_amount: number
      raw_open_amount: number
      debit_credit: string
      transaction_type: string
      reference_number: string
      selling_store: string | null
      days_past_due: number | null
      aging_bucket: string
    }>
    retrieved_count: number
    row_limit: number
    complete: boolean
    retrieved_signed_open_amount: number
    customer_master_balance: number
    reconciliation_difference: number | null
    explanation: string
  }
  related_accounts: {
    status: string
    relationship_basis: string
    group_scope: string
    enterprise_number: string | null
    accounts: Array<{
      customer_number: string
      customer_name: string
      enterprise_number: string | null
      relationship: string
      credit_limit: number
      balance: number
      erp_on_order_aggregate: number
      partial_exposure: number
    }>
    retrieved_count: number
    complete: boolean
    partial_group_credit_limit: number | null
    partial_group_exposure: number | null
    explanation: string
  }
  coverage: Array<{
    key: string
    label: string
    status: string
    source: string | null
    as_of: string | null
    record_count: number | null
    complete: boolean | null
    explanation: string
  }>
  governance: {
    source_authority: string
    erp_access: 'read_only'
    erp_write: false
    recommendation_effect: 'none'
    decision_effect: 'none'
    execution_effect: 'none'
    automatic_selection: false
    statements: string[]
  }
  evidence_sha256: string
  warnings: string[]
}

export interface RiskBand {
  sequence: number
  rating_min: number
  rating_max: number
  meaning: string
  typical_response: string
}

export interface RiskBandSet {
  band_set_id: string
  version: string
  title: string
  status: string
  source_record: string
  seeded_at: string
  automated_policy: boolean
  promotion_authority: string
}

export interface RiskBandResponse {
  contract_version: string
  band_set: RiskBandSet
  bands: RiskBand[]
}

export interface RiskSourceEvidence {
  system: string
  access: string
  status: string
  retrieved_at: string
  source_transaction_as_of: string | null
}

export interface RiskCustomerIdentity {
  customer_number: number
  customer_name: string
  dba_name: string
  address_lines: string[]
  state_code: number | null
  zip_code: string
  phone: string
  email: string
  route_code: string
  store_number: number | null
  salesman_number: number | null
  customer_type: string
  customer_class: string
  active: boolean
}

export interface CreditEvidence {
  credit_line: number
  open_ar: number
  erp_on_order_aggregate: number
  customer_360_exposure: number
  customer_360_available_credit: number
  amount_over_limit: number
  utilization_percent: number | null
  terms_code: string
  terms_description: string
}

export interface ExposureComponent {
  key: string
  label: string
  operation: 'add' | 'subtract' | 'informational'
  value: number | null
  calculation_value: number | null
  status: string
  required_for_full_exposure: boolean
  included_in_partial_calculation: boolean
  source: string | null
  explanation: string
}

export interface ExposureEvidence {
  full_formula: string
  full_exposure: number | null
  completeness: string
  known_component_subtotal: number
  operational_reference_formula: string
  partial_exposure: number
  partial_available_credit: number
  missing_required_components: string[]
  components: ExposureComponent[]
  warnings: string[]
}

export interface AgingEvidence {
  future: number
  current: number
  days_30: number
  days_60: number
  days_90: number
  days_120: number
  past_due: number
  bucket_total: number
  open_ar_reconciliation_difference: number
  source: string
  status: string
}

export interface EvidenceMetric<T = number> {
  value: T | null
  status: string
  source: string | null
  explanation: string
}

export interface PaymentEvidence {
  last_payment_amount: number | null
  last_payment_date: string | null
  last_payment_status: string
  last_payment_explanation: string
  average_days_to_pay: EvidenceMetric
  weighted_average_days_to_pay: EvidenceMetric
  days_beyond_terms: EvidenceMetric
  on_time_percentage: EvidenceMetric
  late_payment_frequency: EvidenceMetric
  largest_historical_delinquency: EvidenceMetric
}

export interface AssessmentGovernance {
  assessment_type: string
  automatic_score: boolean
  decision_effect: string
  erp_write: boolean
}

export interface CustomerRiskEvidenceSnapshot {
  contract_version: string
  source: RiskSourceEvidence
  customer: RiskCustomerIdentity
  credit: CreditEvidence
  exposure: ExposureEvidence
  aging: AgingEvidence
  payment: PaymentEvidence
  governance?: AssessmentGovernance
  risk_band_configuration?: RiskBandResponse
}

export type AssessmentBandSnapshot = RiskBand

export interface CreditRiskAssessment {
  assessment_id: string
  customer_number: number
  customer_name: string
  manual_rating: number
  band_set_id: string
  band_set_version: string
  band_set_status: string
  band: AssessmentBandSnapshot
  review_date: string
  next_review_date: string
  analyst_identity: string
  rationale: string
  created_at: string
  source_as_of: string
  completeness_state: string
  actor_identity_source: string
  actor_authority_status: string
  assessment_classification: string
  decision_effect: string
  evidence_snapshot: CustomerRiskEvidenceSnapshot
  evidence_snapshot_sha256: string
}

export interface CustomerRiskSnapshot extends CustomerRiskEvidenceSnapshot {
  latest_assessment: CreditRiskAssessment | null
  governance: AssessmentGovernance
}

export interface AssessmentHistoryResponse {
  customer_number: number
  assessments: CreditRiskAssessment[]
  count: number
}

export interface PriorityAssessmentReference {
  assessment_id: string
  customer_number: number
  customer_name: string
  manual_rating: number
  band: AssessmentBandSnapshot
  review_date: string
  next_review_date: string
  created_at: string
  source_as_of: string
  evidence_snapshot_sha256: string
}

export interface PriorityOrderingEvidence {
  review_state: 'overdue' | 'due_today' | 'scheduled'
  latest_manual_rating: number
  deterioration_state: 'deteriorated' | 'not_deteriorated' | 'insufficient_history'
  manual_rating_change: number | null
  over_line_state: 'over_line' | 'not_over_line' | 'unavailable'
  next_review_date: string
}

export interface PriorityLiveExposureEvidence {
  status: 'available' | 'source_unavailable' | 'customer_not_found' | 'source_integrity_error'
  source: string
  retrieved_at: string | null
  exposure_completeness: 'partial' | null
  credit_line: number | null
  partial_exposure: number | null
  partial_available_credit: number | null
  amount_over_limit: number | null
  is_over_line: boolean | null
  explanation: string
}

export interface PriorityAlert {
  code:
    | 'review_overdue'
    | 'review_due_today'
    | 'manual_rating_deteriorated'
    | 'draft_band_attention'
    | 'current_partial_exposure_over_line'
    | 'live_source_degraded'
  category:
    | 'review_schedule'
    | 'assessment_change'
    | 'draft_taxonomy'
    | 'live_exposure'
    | 'source_gap'
  evidence_class:
    | 'professional_judgment'
    | 'deterministic_comparison'
    | 'observed_current'
    | 'source_limitation'
  title: string
  explanation: string
  assessment_ids: string[]
  evidence_sha256: string[]
  source_as_of: string | null
}

export interface PriorityPortfolioItem {
  rank: number
  priority_category: 'review_overdue' | 'review_due_today' | 'scheduled_review'
  customer_number: number
  customer_name: string
  customer_name_source: 'live_customer_360' | 'saved_assessment'
  latest_assessment: PriorityAssessmentReference
  previous_assessment: PriorityAssessmentReference | null
  draft_band_attention: boolean
  ordering_evidence: PriorityOrderingEvidence
  live_exposure: PriorityLiveExposureEvidence
  alerts: PriorityAlert[]
  ordering_reasons: string[]
}

export interface PriorityPortfolioSummary {
  assessed_customer_count: number
  operational_alert_count: number
  overdue_review_count: number
  due_today_review_count: number
  deterioration_count: number
  draft_band_attention_count: number
  over_line_count: number
  live_source_degraded_count: number
}

export interface UnavailablePriorityCapability {
  code: 'broken_promise_alerts' | 'nsf_alerts'
  label: string
  status: 'unavailable_source_capability'
  emitted_alerts: false
  explanation: string
}

export interface PriorityOrderingGovernance {
  rule_version: 'credit-risk-priority-ordering.v1'
  classification: 'operational_ordering'
  ordered_conditions: string[]
  numeric_risk_score: false
  automatic_credit_decision: false
  recommendation: false
  notification: false
  erp_write: false
  unavailable_over_line_treatment: string
  explanation: string
}

export interface PriorityAlertsResponse {
  contract_version: string
  generated_at: string
  as_of_date: string
  coverage_statement: string
  unassessed_customers_excluded: true
  summary: PriorityPortfolioSummary
  ordering: PriorityOrderingGovernance
  unavailable_capabilities: UnavailablePriorityCapability[]
  items: PriorityPortfolioItem[]
}

export type PriorityPortfolioFilter = 'draft_band_attention' | 'all_assessed'

export interface CreateAssessmentRequest {
  manual_rating: number
  review_date: string
  next_review_date: string
  analyst_identity: string
  rationale: string
}

export interface AssessmentDraft {
  rating: string
  reviewDate: string
  nextReviewDate: string
  analystIdentity: string
  rationale: string
}

export type AssessmentField = keyof AssessmentDraft
export type AssessmentErrors = Partial<Record<AssessmentField, string>>

export interface CreditRiskWorkspaceProps {
  initialCustomerNumber?: number | string
}

export type CreditRiskCustomerSearchResult = CustomerSearchResult

export interface CreditLineMetric {
  value: number | null
  status: 'available' | 'unavailable' | 'invalid'
  source: string | null
  as_of: string | null
  explanation: string
}

export interface CreditLineSalesEvidence {
  month_to_date: CreditLineMetric
  year_to_date: CreditLineMetric
  last_year: CreditLineMetric
  annualized_sales: CreditLineMetric
}

export interface CreditLineCapacityEvidence {
  current_credit_line: CreditLineMetric
  partial_exposure: CreditLineMetric
  available_credit: CreditLineMetric
  high_balance: CreditLineMetric
  monthly_high_balance: CreditLineMetric
  average_daily_balance: CreditLineMetric
}

export interface CreditLineAnalyticalReference {
  amount: number | null
  status: 'available' | 'unavailable' | 'invalid'
  formula: string
  rounding_increment: number
  rule_version: string
  knowledge_class: string
  policy_status: string
  automatic_recommendation: false
  explanation: string
}

export interface CreditLineGap {
  code: string
  label: string
  status: 'unavailable'
  explanation: string
}

export interface CreditLineGovernance {
  classification: string
  reference_is_recommendation: false
  proposal_is_decision: false
  proposal_approval_effect: 'none'
  erp_write: false
  actor_identity_source: string
  actor_authority_status: string
  statements: string[]
}

export interface CreditLineProposal {
  proposal_id: string
  customer_number: number
  customer_name: string
  proposed_credit_line: number
  current_credit_line: number
  analytical_reference_line: number | null
  review_date: string
  analyst_identity: string
  rationale: string
  created_at: string
  source_as_of: string
  actor_identity_source: string
  actor_authority_status: string
  proposal_classification: string
  approval_status: string
  decision_effect: 'none'
  erp_write: false
  evidence_snapshot: Record<string, unknown>
  evidence_snapshot_sha256: string
}

export interface CreditLineProposalHistoryResponse {
  customer_number: number
  count: number
  proposals: CreditLineProposal[]
}

export interface CreditLineIntelligenceResponse {
  contract_version: string
  generated_at: string
  source: RiskSourceEvidence
  customer: RiskCustomerIdentity
  sales: CreditLineSalesEvidence
  capacity: CreditLineCapacityEvidence
  analytical_reference: CreditLineAnalyticalReference
  current_manual_assessment: CreditRiskAssessment | null
  latest_professional_proposal: CreditLineProposal | null
  gaps: CreditLineGap[]
  governance: CreditLineGovernance
}

export interface CreateCreditLineProposalRequest {
  proposed_credit_line: number
  review_date: string
  analyst_identity: string
  rationale: string
}

export type PortfolioReviewDisposition =
  | 'reviewed_no_change'
  | 'reassessment_needed'
  | 'credit_line_analysis_needed'
  | 'information_requested'

export interface PortfolioReview {
  portfolio_review_id: string
  customer_number: number
  customer_name: string
  disposition: PortfolioReviewDisposition
  reviewer_identity: string
  notes: string
  follow_up_date: string | null
  created_at: string
  assessment_id: string
  proposal_id: string | null
  actor_identity_source: 'operator_supplied'
  actor_authority_status: 'not_independently_verified'
  review_classification: 'professional_workflow_metadata'
  decision_effect: 'none'
  erp_write: false
  evidence_snapshot: Record<string, unknown>
  evidence_snapshot_sha256: string
}

export interface PortfolioBandConcentration {
  band_meaning: string
  customer_count: number
  partial_exposure: number
  exposure_share_percent: number | null
  exposure_customer_count: number
}

export interface PortfolioMonitoringSummary {
  assessed_customer_count: number
  watchlist_customer_count: number
  overdue_review_count: number
  due_today_review_count: number
  degraded_live_source_count: number
  customers_with_proposals: number
  customers_with_recorded_reviews: number
  partial_exposure_customer_count: number
  partial_exposure_total: number
}

export interface PortfolioMonitoringItem {
  rank: number
  customer_number: number
  customer_name: string
  assessment_id: string
  watchlist: boolean
  review_state: 'overdue' | 'due_today' | 'scheduled'
  next_review_date: string
  days_to_review: number
  latest_manual_rating: number
  band_meaning: string
  partial_exposure: number | null
  partial_exposure_share_percent: number | null
  latest_professional_proposal: CreditLineProposal | null
  latest_portfolio_review: PortfolioReview | null
  alerts: PriorityAlert[]
  ordering_reasons: string[]
}

export interface PortfolioMonitoringGovernance {
  classification: 'professional_work_management'
  concentration_scope: 'assessed_customers_with_available_partial_exposure'
  approved_portfolio_policy: false
  automatic_decision: false
  notification: false
  erp_write: false
  statements: string[]
}

export interface PortfolioMonitoringResponse {
  contract_version: string
  generated_at: string
  as_of_date: string
  summary: PortfolioMonitoringSummary
  band_concentration: PortfolioBandConcentration[]
  items: PortfolioMonitoringItem[]
  governance: PortfolioMonitoringGovernance
  warnings: string[]
}

export interface CreatePortfolioReviewRequest {
  disposition: PortfolioReviewDisposition
  reviewer_identity: string
  notes: string
  follow_up_date?: string | null
}

export interface OrderDecisionEvidence {
  contemplated_order_amount: number
  current_credit_line: number
  current_partial_exposure: number
  projected_partial_exposure: number
  projected_partial_available_credit: number
  projected_partial_over_line_amount: number
  projected_partial_utilization_percent: number | null
  order_source: 'operator_entered_scenario_not_erp_order'
  exposure_scope: 'partial_customer_360_evidence'
}

export interface OrderDecisionGate {
  code:
    | 'current_customer_evidence'
    | 'current_manual_assessment'
    | 'erp_order_identity'
    | 'full_exposure'
    | 'approved_order_policy'
    | 'authenticated_decision_authority'
  status: 'available' | 'unavailable' | 'operator_entered'
  explanation: string
}

export interface OrderDecisionGovernance {
  classification: 'professional_decision_preparation'
  automatic_recommendation: false
  automatic_decision: false
  order_hold_effect: 'none'
  order_release_effect: 'none'
  approval_effect: 'none'
  erp_write: false
  actor_identity_source: 'operator_supplied'
  actor_authority_status: 'not_independently_verified'
  statements: string[]
}

export interface OrderDecisionPreparationResponse {
  contract_version: string
  generated_at: string
  source: RiskSourceEvidence
  customer: RiskCustomerIdentity
  order_reference: string | null
  evidence: OrderDecisionEvidence
  latest_manual_assessment: CreditRiskAssessment | null
  latest_professional_proposal: CreditLineProposal | null
  latest_portfolio_review: PortfolioReview | null
  gates: OrderDecisionGate[]
  professional_review_required: true
  governance: OrderDecisionGovernance
  warnings: string[]
}

export type OrderRecommendationDisposition =
  | 'advance_to_authorized_review'
  | 'request_additional_information'
  | 'escalate_for_credit_authority'
  | 'do_not_advance'

export interface OrderRecommendation {
  order_recommendation_id: string
  customer_number: number
  customer_name: string
  contemplated_order_amount: number
  order_reference: string | null
  disposition: OrderRecommendationDisposition
  analyst_identity: string
  rationale: string
  created_at: string
  source_as_of: string
  assessment_id: string | null
  proposal_id: string | null
  current_credit_line: number
  current_partial_exposure: number
  projected_partial_exposure: number
  projected_partial_available_credit: number
  projected_partial_over_line_amount: number
  actor_identity_source: 'operator_supplied'
  actor_authority_status: 'not_independently_verified'
  recommendation_classification: 'professional_recommendation'
  decision_status: 'not_submitted_to_governed_decision'
  decision_effect: 'none'
  order_effect: 'none'
  erp_write: false
  evidence_snapshot: Record<string, unknown>
  evidence_snapshot_sha256: string
}

export interface OrderRecommendationHistoryResponse {
  customer_number: number
  count: number
  recommendations: OrderRecommendation[]
  governance: OrderDecisionGovernance
}

export interface CreateOrderRecommendationRequest {
  contemplated_order_amount: number
  order_reference?: string | null
  disposition: OrderRecommendationDisposition
  analyst_identity: string
  rationale: string
}

export interface PotentialCustomerAddress {
  street: string
  city: string
  state: string
  zip: string
}

export type PotentialCustomerFieldStatus = 'parsed' | 'blank' | 'unreadable' | 'not_detected' | 'human_verified'

export interface PotentialCustomerFieldEvidence {
  value: unknown
  status: PotentialCustomerFieldStatus
  source_present?: boolean
  confidence: number
  source: string
  parser: string
  parser_version: string
}

export interface PotentialCustomerFields {
  legal_business_name: string
  trade_name: string
  type_of_business: string
  shipping_address: PotentialCustomerAddress
  billing_address: PotentialCustomerAddress
  business_phone: string
  primary_language: string
  cell_phone: string
  county: string
  email_address: string
  federal_tax_id: string
  manager_name: string
  year_started_business: string
  accounts_payable_contact: string
  purchase_order_required: boolean | null
  owners: Array<{ name: string; raw_line: string; dob: string }>
  trade_references: Array<{ raw_line: string; phone: string; zip: string }>
  previous_km_relationship: boolean | null
  previous_business_name: string
  sales_tax_exempt: boolean | null
  sales_tax_exemption_reason: string
  sales_tax_id: string
  application_signed_date: string
  weblink_signup: boolean | null
  weblink_email: string
  statement_email_signup: boolean | null
  statement_email: string
  salesperson_name: string
  salesperson_date: string
  number_of_locations: number | null
  estimated_annual_purchases: number | null
  terms_signer_name: string
  terms_signed_date: string
  personal_guarantor_name: string
  terms_signature_present: boolean
  personal_guarantee_signature_present: boolean
}

export interface PotentialCustomerTmcustMapping {
  field: string
  tmcust_column: string
  source: 'application' | 'km_setup'
  application_or_proposed_value: unknown
  status: 'ready' | 'missing' | 'unassigned' | 'needs_km_value' | 'translation_required'
  warning: string
  max_length: number | null
}

export interface PotentialCustomerMatch {
  customer_number: number
  customer_name: string
  route_code: string
  matched_factors: string[]
  confidence: number
  automatic_decision: false
}

export interface PotentialCustomerRecord {
  contract_version: string
  potential_customer_id: string
  status: string
  source_file_name: string
  source_sha256: string
  parser_name: string
  parser_version: string
  classifier_confidence: number
  received_at: string
  updated_at: string
  fields: PotentialCustomerFields
  evidence: Record<string, PotentialCustomerFieldEvidence>
  km_setup: Record<string, unknown>
  review_notes: string
  erp_write: false
  tmcust_mapping: PotentialCustomerTmcustMapping[]
  madden_setup: {
    ready_count: number
    total_count: number
    erp_write: false
    status: 'preparation_only'
  }
  existing_customer_matches: PotentialCustomerMatch[]
  governance: {
    source_authority: string
    erp_access: 'read_only'
    erp_write: false
    automatic_customer_creation: false
    human_review_required: true
  }
}

export interface PotentialCustomerListResponse {
  contract_version: string
  count: number
  potential_customers: PotentialCustomerRecord[]
}
