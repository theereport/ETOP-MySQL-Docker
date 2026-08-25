export interface SourceEvidence {
  system: string
  access: 'read_only'
  status: 'available'
  retrieved_at: string
}

export interface TaxAuthorityRecord {
  tax_authority: number
  state_code: number
  state_abbreviation: string
  description: string
  tax_type_code: string
  rate_percent: number | null
  max_tax_amount: number | null
  fet_applicable: boolean
  selectable_from_prompt: boolean
  next_tax_authority: number | null
  next_state_code: number | null
  active: boolean
  date_created: string | null
  date_changed: string | null
  created_by: string
  changed_by: string
}

export interface TaxAuthoritySearchResponse {
  contract_version: string
  source: SourceEvidence
  count: number
  authorities: TaxAuthorityRecord[]
  explanation: string
}

export interface TaxExemptionCodeRecord {
  exempt_code: string
  state_code: number
  description: string
  tax_type_code: string
  override_or_percent_code: string
  percent_taxable: number | null
  rate_percent: number | null
  max_taxable_per_line: number | null
  active: boolean
  date_created: string | null
  date_changed: string | null
  created_by: string
  changed_by: string
}

export interface TaxExemptionCodeSearchResponse {
  contract_version: string
  source: SourceEvidence
  count: number
  exemption_codes: TaxExemptionCodeRecord[]
  explanation: string
}

export interface TaxComplianceGap {
  code: string
  label: string
  status: 'unavailable'
  explanation: string
}

export interface TaxComplianceGovernance {
  assessment_type: 'evidence_only'
  automatic_score: boolean
  decision_effect: 'none'
  erp_write: boolean
}

export type ExemptionMatchStatus =
  | 'matched'
  | 'no_matching_exemption_code_found'
  | 'no_exemption_code_on_customer'

export type ExemptionExpirationStatus =
  | 'current'
  | 'expired'
  | 'no_expiration_date_on_file'

export interface CustomerExemptionCheckResult {
  customer_number: number
  customer_name: string
  state_code: number | null
  exemption_code_on_file: string
  fet_exempt: boolean
  exemption_certificate_expiration_date: string | null
  expiration_status: ExemptionExpirationStatus
  match_status: ExemptionMatchStatus
  matched_exemption_codes: TaxExemptionCodeRecord[]
}

export interface CustomerExemptionCheckResponse {
  contract_version: string
  generated_at: string
  source: SourceEvidence
  result: CustomerExemptionCheckResult
  gaps: TaxComplianceGap[]
  governance: TaxComplianceGovernance
}

export interface CustomerExemptionCheckBatchResponse {
  contract_version: string
  generated_at: string
  source: SourceEvidence
  checked_count: number
  not_found_customer_numbers: number[]
  results: CustomerExemptionCheckResult[]
  gaps: TaxComplianceGap[]
  governance: TaxComplianceGovernance
}

export interface TaxComplianceNoteRecord {
  note_id: string
  customer_number: number
  customer_name: string
  author_identity: string
  note: string
  created_at: string
  source_as_of: string
  decision_effect: 'none'
  erp_write: false
  evidence_snapshot_sha256: string
}

export interface TaxComplianceNoteHistoryResponse {
  customer_number: number
  count: number
  notes: TaxComplianceNoteRecord[]
}

export interface CreateTaxComplianceNoteRequest {
  author_identity: string
  note: string
}
