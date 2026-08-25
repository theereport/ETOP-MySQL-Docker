export interface SourceEvidence {
  system: string
  access: 'read_only'
  status: 'available'
  retrieved_at: string
}

export interface CustomerIdentityEvidence {
  customer_number: number
  customer_name: string
  dba_name: string
  address_lines: string[]
  zip_code: string
  country: string
  phone: string
  email: string
  route_code: string
  store_number: number | null
  salesman_number: number | null
  customer_type: string
  customer_class: string
  active: boolean
  source: string
}

export interface OpenARItem {
  invoice_number: number
  transaction_type: string
  entry_type: string
  debit_credit: string
  original_amount: number
  open_amount: number
  discountable_amount: number
  cash_discount: number
  terms_code: string
  adjustment_reason: string
  reference_number: string
  transaction_date: string | null
  due_date: string | null
  days_past_due: number | null
  purged_to_history: boolean
}

export interface OpenAREvidence {
  item_count: number
  total_open_amount: number
  open_items: OpenARItem[]
  source: string
  explanation: string
}

export interface AROpenItemHistoryEvidence {
  item_count: number
  items: OpenARItem[]
  source: string
  explanation: string
}

export interface ARTransaction {
  sequence: number
  invoice_number: number
  transaction_date: string | null
  due_date: string | null
  original_amount: number
  debit_credit: string
  entry_type: string
  transaction_type: string
  reference_number: string
  status: string
  period: number | null
  year: number | null
  cash_discount: number
}

export interface ARTransactionApplication {
  header_sequence: number
  detail_sequence: number
  header_invoice_number: number
  header_reference_number: string
  header_transaction_date: string | null
  applied_invoice_number: number
  amount_applied: number
  discount_applied: number
  gl_account: number | null
  gl_division: number | null
  gl_department: number | null
  created_date: string | null
}

export interface ARTransactionHistoryEvidence {
  transaction_count: number
  application_count: number
  transactions: ARTransaction[]
  applications: ARTransactionApplication[]
  source: string
  explanation: string
}

export interface GLDistributionLine {
  gl_account: number | null
  gl_division: number | null
  gl_department: number | null
  debit_amount: number
  credit_amount: number
  quantity: number
  description: string
  created_date: string | null
}

export interface GLDistributionEvidence {
  line_count: number
  total_debit_amount: number
  total_credit_amount: number
  lines: GLDistributionLine[]
  source: string
  explanation: string
}

export interface ERPCollectionNote {
  note_text: string
  created_at: string | null
  created_by: string
  changed_at: string | null
  changed_by: string
}

export interface ERPCollectionNotesEvidence {
  count: number
  notes: ERPCollectionNote[]
  source: string
  explanation: string
}

export interface ERPCreditManagementNote {
  header_key: number
  regarding: string
  date_to_do: string | null
  date_done: string | null
  created_at: string | null
  created_by: string
  changed_at: string | null
  changed_by: string
  detail_lines: string[]
}

export interface ERPCreditManagementNotesEvidence {
  count: number
  notes: ERPCreditManagementNote[]
  source: string
  explanation: string
}

export interface AgingSnapshot {
  snapshot_date: string | null
  aging_future: number
  aging_current: number
  aging_30: number
  aging_60: number
  aging_90: number
  aging_120: number
  balance: number
  balance_high: number
  discount_month_to_date: number
  credit_limit: number
  date_last_paid: string | null
  date_last_statement: string | null
  amount_last_paid: number
  salesman_number: number | null
  sales_month_to_date: number
}

export interface AgingHistoryEvidence {
  snapshot_count: number
  snapshots: AgingSnapshot[]
  source: string
  explanation: string
}

export interface ARCollectionsEvidenceGap {
  code: string
  label: string
  status: 'unavailable'
  explanation: string
}

export interface CustomerARCollectionsResponse {
  contract_version: string
  generated_at: string
  source: SourceEvidence
  customer: CustomerIdentityEvidence
  open_ar: OpenAREvidence
  item_history: AROpenItemHistoryEvidence
  transactions: ARTransactionHistoryEvidence
  gl_distributions: GLDistributionEvidence
  erp_collection_notes: ERPCollectionNotesEvidence
  erp_credit_management_notes: ERPCreditManagementNotesEvidence
  aging_history: AgingHistoryEvidence
  gaps: ARCollectionsEvidenceGap[]
  governance: {
    assessment_type: 'evidence_only'
    automatic_score: boolean
    decision_effect: 'none'
    erp_write: boolean
  }
}

export interface ARCollectionsNoteRecord {
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

export interface ARCollectionsNoteHistoryResponse {
  customer_number: number
  count: number
  notes: ARCollectionsNoteRecord[]
}

export interface CreateARCollectionsNoteRequest {
  author_identity: string
  note: string
}
