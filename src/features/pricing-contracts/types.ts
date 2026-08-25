export interface SourceEvidence {
  system: string
  access: 'read_only'
  status: 'available'
  retrieved_at: string
}

export interface DiscountRecord {
  record_key: string
  customer_number: number
  vendor_code: string
  product_class: string
  product_class_label: string
  product_class_item_type: string
  product_class_active: boolean | null
  product_number: string
  product_type: string
  delete_code: string
  active: boolean
  fixed_amount: number
  chain: number
  factor: number
  override_price: number
  price_code: number
  date_added: string | null
  date_changed: string | null
  time_added: string
  time_changed: string
  added_by: string
  changed_by: string
}

export interface PricingEvidenceGap {
  code: string
  label: string
  status: 'unavailable'
  explanation: string
}

export interface PricingContractsGovernance {
  assessment_type: 'evidence_only'
  automatic_score: boolean
  decision_effect: 'none'
  erp_write: boolean
}

export interface DiscountSearchResponse {
  contract_version: string
  source: SourceEvidence
  count: number
  discounts: DiscountRecord[]
  gaps: PricingEvidenceGap[]
  governance: PricingContractsGovernance
}

export interface DiscountEvidenceResponse {
  contract_version: string
  generated_at: string
  source: SourceEvidence
  discount: DiscountRecord
  gaps: PricingEvidenceGap[]
  governance: PricingContractsGovernance
}

export interface CustomerClassRecord {
  id: number
  class_num: string
  class_name: string
  active: boolean
  created_at: string | null
  created_by: string
  changed_at: string | null
  changed_by: string
}

export interface CustomerClassResponse {
  contract_version: string
  source: SourceEvidence
  count: number
  customer_classes: CustomerClassRecord[]
}

export interface PricingNoteRecord {
  note_id: string
  customer_number: number
  vendor_code: string | null
  product_class: string | null
  product_number: string | null
  product_type: string | null
  author_identity: string
  note: string
  created_at: string
  source_as_of: string
  matched_discount_count: number
  decision_effect: 'none'
  erp_write: false
  evidence_snapshot_sha256: string
}

export interface PricingNoteHistoryResponse {
  customer_number: number
  count: number
  notes: PricingNoteRecord[]
}

export interface CreatePricingNoteRequest {
  customer_number: number
  vendor_code?: string | null
  product_class?: string | null
  product_number?: string | null
  product_type?: string | null
  author_identity: string
  note: string
}

export interface DiscountSearchFilters {
  customerNumber?: number
  productNumber?: string
  productClass?: string
  vendorCode?: string
  activeOnly?: boolean
}
