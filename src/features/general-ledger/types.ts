export interface SourceEvidence {
  system: string
  access: 'read_only'
  status: 'available'
  retrieved_at: string
}

export interface AccountSearchResult {
  account_number: number
  division: number
  department: number
  description: string
  short_name: string
  debit_or_credit: string
  account_type: string
  active: boolean
}

export interface AccountSearchResponse {
  contract_version: string
  source: SourceEvidence
  count: number
  accounts: AccountSearchResult[]
}

export interface AccountIdentityEvidence {
  account_number: number
  division: number
  department: number
  company_number: number | null
  description: string
  short_name: string
  debit_or_credit: string
  account_type: string
  active: boolean
  requires_customer: boolean
  requires_employee: boolean
  requires_job: boolean
  requires_po: boolean
  date_created: string | null
  date_changed: string | null
  created_by: string
  changed_by: string
}

export interface AccountEvidenceGap {
  code: string
  label: string
  status: 'unavailable'
  explanation: string
}

export interface AccountEvidenceResponse {
  contract_version: string
  generated_at: string
  source: SourceEvidence
  identity: AccountIdentityEvidence
  gaps: AccountEvidenceGap[]
  governance: {
    assessment_type: 'evidence_only'
    automatic_score: boolean
    decision_effect: 'none'
    erp_write: boolean
  }
}

export interface AccountPeriodBalance {
  year: number
  period: number
  net_balance: number
}

export interface AccountBalanceEvidence {
  account_number: number
  division: number
  department: number
  balances: AccountPeriodBalance[]
  source: string
  explanation: string
}

export interface JournalEntryHeaderReference {
  reference_number: number
  period: number
  year: number
  company_number: number | null
  total_debit: number
  total_credit: number
  flag: string
}

export interface PostedTransaction {
  sequence: number
  year: number
  period: number
  amount: number
  debit_or_credit: string
  description: string
  system_source: string
  date_created: string | null
  date_posted: string | null
  je_created_date: string | null
  je_created_time: string
  je_created_by: string
  je_created_workstation: string
  customer_number: number | null
  employee_number: number | null
  job_number: number | null
  po_number: number | null
  reference_number: number | null
  reconcile_reference_number: number | null
  memo_id: number | null
  matched_journal_entry: JournalEntryHeaderReference | null
}

export interface UnpostedJournalEntryLine {
  reference_number: number
  sequence: number
  account_number: number
  division: number
  department: number
  debit_amount: number
  credit_amount: number
  description: string
  customer_number: number | null
  employee_number: number | null
  job_number: number | null
  po_number: number | null
}

export interface ReconciliationCheck {
  year: number
  period: number
  posted_debit_total: number
  posted_credit_total: number
  posted_net_total: number
  period_balance: number | null
  difference: number | null
  formula: string
}

export interface TransactionEvidence {
  account_number: number
  division: number
  department: number
  year: number
  period: number
  count: number
  transactions: PostedTransaction[]
  reconciliation: ReconciliationCheck
  unposted_journal_entry_lines: UnpostedJournalEntryLine[]
  unposted_explanation: string
  source: string
}

export interface StandardJournalEntryTemplateSummary {
  name: string
  description: string
  je_description: string
  status_code: string
}

export interface StandardJournalEntryTemplateResponse {
  contract_version: string
  source: SourceEvidence
  count: number
  templates: StandardJournalEntryTemplateSummary[]
  explanation: string
}

export interface StandardJournalEntryTemplateLine {
  sequence: number
  account_number: number
  division: number
  department: number
  debit_amount: number
  credit_amount: number
  description: string
  customer_number: number | null
  employee_number: number | null
  job_number: number | null
  po_number: number | null
}

export interface StandardJournalEntryTemplateDetail {
  name: string
  description: string
  je_description: string
  status_code: string
  next_sequence_number: number | null
  created_by: string
  last_changed_by: string
  lines: StandardJournalEntryTemplateLine[]
  line_debit_total: number
  line_credit_total: number
  source: string
  explanation: string
}

export interface GLNoteRecord {
  note_id: string
  account_number: number
  division: number
  department: number
  period: number | null
  year: number | null
  account_description: string
  author_identity: string
  note: string
  created_at: string
  source_as_of: string
  decision_effect: 'none'
  erp_write: false
  evidence_snapshot_sha256: string
}

export interface GLNoteHistoryResponse {
  account_number: number
  count: number
  notes: GLNoteRecord[]
}

export interface CreateGLNoteRequest {
  author_identity: string
  note: string
  division?: number
  department?: number
  period?: number | null
  year?: number | null
}
