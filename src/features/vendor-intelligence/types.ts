export interface SourceEvidence {
  system: string
  access: 'read_only'
  status: 'available'
  retrieved_at: string
}

export interface VendorSearchResult {
  vendor_number: number
  vendor_name: string
  contact_name: string
  phone: string
  email: string
  zip_code: string
  active: boolean
  po_required: boolean
}

export interface VendorSearchResponse {
  contract_version: string
  source: SourceEvidence
  count: number
  vendors: VendorSearchResult[]
}

export interface VendorIdentityEvidence {
  vendor_number: number
  vendor_name: string
  sort_name: string
  contact_name: string
  address_lines: string[]
  zip_code: string
  country: string
  phone: string
  fax: string
  email: string
  active: boolean
  vendor_type: string
  store_number: number | null
  terms_code: string
  po_required: boolean
  do_not_create_ap_from_receiving: boolean
  is_1099: boolean
  tax_1099_code: string
  tax_1099_manual_amount: number | null
  federal_id_on_file: boolean
  payment_type: string
  bank_account_type: string
  eft_bank_info_on_file: boolean
}

export interface DiscountCaptureMetric {
  value: number | null
  status: 'available' | 'unavailable'
  explanation: string
}

export interface VendorPurchaseVolumeEvidence {
  month_to_date: number
  year_to_date: number
  last_year: number
  discount_month_to_date: number
  discount_year_to_date: number
  discount_lost_month_to_date: number
  discount_lost_year_to_date: number
  discount_capture_rate_month_to_date: DiscountCaptureMetric
  discount_capture_rate_year_to_date: DiscountCaptureMetric
  amount_last_paid: number | null
  date_last_paid: string | null
  check_number_last_paid: number | null
  source: string
  discount_explanation: string
}

export interface OpenPurchaseOrder {
  po_number: number
  po_date: string | null
  date_required: string | null
  status_code: string
  complete: boolean
  total_cost: number
  ship_via: string
  buyer_number: number | null
  ordered_quantity: number
  received_quantity: number
  backorder_quantity: number
  line_count: number
}

export interface PurchaseOrderEvidence {
  open_order_count: number
  open_order_total_cost: number
  open_orders: OpenPurchaseOrder[]
  source: string
  explanation: string
}

export interface ReceivingEvent {
  po_number: number
  product_number: string
  product_description: string
  quantity: number
  actual_cost: number | null
  po_cost: number | null
  cost_variance: number | null
  dot_number: string
  dot_date: string | null
  received_date: string | null
}

export interface ReceivingEvidence {
  receipt_count: number
  total_cost_variance: number | null
  cost_variance_completeness: 'complete' | 'partial' | 'unavailable'
  recent_receipts: ReceivingEvent[]
  source: string
  explanation: string
}

export interface OpenPayableInvoice {
  invoice_number: string
  invoice_amount: number
  discount_amount: number
  invoice_date: string | null
  due_date: string | null
  on_hold: boolean
  period: number | null
  year: number | null
}

export interface PaidPayableInvoice {
  invoice_number: string
  invoice_amount: number
  invoice_date: string | null
  due_date: string | null
  status: string
  amount_paid: number | null
  discount_taken: number | null
}

export interface PayablesEvidence {
  open_invoice_count: number
  open_invoice_total: number
  open_invoices: OpenPayableInvoice[]
  recent_paid_invoices: PaidPayableInvoice[]
  source: string
}

export interface VendorEvidenceGap {
  code: string
  label: string
  status: 'unavailable'
  explanation: string
}

export interface VendorEvidenceResponse {
  contract_version: string
  generated_at: string
  source: SourceEvidence
  identity: VendorIdentityEvidence
  purchase_volume: VendorPurchaseVolumeEvidence
  purchase_orders: PurchaseOrderEvidence
  receiving: ReceivingEvidence
  payables: PayablesEvidence
  gaps: VendorEvidenceGap[]
  governance: {
    assessment_type: 'evidence_only'
    automatic_score: boolean
    decision_effect: 'none'
    erp_write: boolean
  }
}

export interface VendorNoteRecord {
  note_id: string
  vendor_number: number
  vendor_name: string
  author_identity: string
  note: string
  created_at: string
  source_as_of: string
  decision_effect: 'none'
  erp_write: false
  evidence_snapshot_sha256: string
}

export interface VendorNoteHistoryResponse {
  vendor_number: number
  count: number
  notes: VendorNoteRecord[]
}

export interface CreateVendorNoteRequest {
  author_identity: string
  note: string
}
