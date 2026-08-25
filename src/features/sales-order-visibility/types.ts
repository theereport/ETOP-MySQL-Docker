export interface SourceEvidence {
  system: string
  access: 'read_only'
  status: 'available'
  retrieved_at: string
}

export interface InvoiceSearchResult {
  invoice_number: number
  customer_number: number
  customer_name: string
  invoice_date: string | null
  type_code: string
  total_amount: number
  void: boolean
  route_code: string
  store_number: number | null
  po_number: string
}

export interface InvoiceSearchResponse {
  contract_version: string
  source: SourceEvidence
  count: number
  invoices: InvoiceSearchResult[]
}

export interface InvoiceHeaderEvidence {
  invoice_number: number
  customer_number: number
  customer_name: string
  invoice_date: string | null
  due_date: string | null
  created_date: string | null
  changed_date: string | null
  type_code: string
  void: boolean
  hold_reason: string
  direct_ship: boolean
  pickup: boolean
  route_code: string
  store_number: number | null
  po_number: string
  reference_number: string
  terms_code: string
  tax_exempt_code: string
  customer_class: string
  customer_type: string
  type_of_sale: string
  ship_to_lines: string[]
  ship_to_zip: string
  tracking_number: string
  total_amount: number
  total_units: number
  total_discount: number
  line_count: number | null
  invoice_count: number | null
  selling_salesman: number | null
  customer_salesman: number | null
  originating_salesman: number | null
  class_salesman: number | null
  status: string
  status_secondary: string
}

export interface InvoiceLineItem {
  line_number: number
  type_code: string
  delete_code: string
  product_number: string
  product_description: string
  product_vendor: string
  brand: string
  product_class: string
  quantity: number
  quantity_ordered: number
  quantity_backorder: number
  unit_price: number
  extended_price: number
  actual_cost: number | null
  replacement_cost: number | null
  fet: number | null
  dot_number: string
  dot_date: string | null
  tire_position: string
  vehicle_make: string
  vehicle_model: string
  vehicle_year: number | null
  mileage: number | null
}

export interface InvoiceLineEvidence {
  line_count: number
  total_extended_price: number
  total_quantity: number
  lines: InvoiceLineItem[]
  source: string
  explanation: string
}

export interface InvoiceMemo {
  line_number: number | null
  type_code: string
  message: string
  created_date: string | null
  created_by: string
  print_on_invoice: boolean
}

export interface InvoiceMemoEvidence {
  memo_count: number
  memos: InvoiceMemo[]
  source: string
}

export interface InvoiceAuthorization {
  authorization_type: string
  type_code: string
  amount_authorized: number | null
  date_requested: string | null
  date_authorized: string | null
  time_requested: string
  time_authorized: string
  salesman_requested: number | null
  salesman_authorized: number | null
  requested_by: string
  authorized_by: string
  text: string
}

export interface InvoiceAuthorizationEvidence {
  authorization_count: number
  authorizations: InvoiceAuthorization[]
  source: string
  explanation: string
}

export interface DeliveryManifestLine {
  store_number: number | null
  route: string
  status: string
  line_number: number | null
  sequence: number | null
  product_number: string
  description: string
  weight: number | null
  quantity: number | null
  created_at: string | null
  delivered_at: string | null
  delivered: boolean
}

export interface DeliveryEvidence {
  manifest_status: 'records_found' | 'no_records_found'
  total_line_count: number
  delivered_line_count: number
  undelivered_line_count: number
  is_fully_delivered: boolean | null
  lines: DeliveryManifestLine[]
  source: string
  explanation: string
}

export interface SalesOrderEvidenceGap {
  code: string
  label: string
  status: 'unavailable'
  explanation: string
}

export interface InvoiceEvidenceResponse {
  contract_version: string
  generated_at: string
  source: SourceEvidence
  header: InvoiceHeaderEvidence
  lines: InvoiceLineEvidence
  memos: InvoiceMemoEvidence
  authorizations: InvoiceAuthorizationEvidence
  delivery: DeliveryEvidence
  gaps: SalesOrderEvidenceGap[]
  governance: {
    assessment_type: 'evidence_only'
    automatic_score: boolean
    decision_effect: 'none'
    erp_write: boolean
  }
}

export interface SalesSummaryRow {
  customer_number: number | null
  product_number: string
  product_class: string
  product_type: string
  customer_class: string
  customer_type: string
  commission_code: string
  vendor_number: string
  store_number: number | null
  year_period: number | null
  sales: number
  units: number
  actual_cost: number | null
  replacement_cost: number | null
  fet: number | null
}

export interface SalesSummaryResponse {
  contract_version: string
  generated_at: string
  source: SourceEvidence
  row_count: number
  total_sales: number
  total_units: number
  total_actual_cost: number
  rows: SalesSummaryRow[]
  source_table: string
  explanation: string
}

export interface OrderNoteRecord {
  note_id: string
  invoice_number: number
  customer_number: number | null
  customer_name: string
  author_identity: string
  note: string
  created_at: string
  source_as_of: string
  decision_effect: 'none'
  erp_write: false
  evidence_snapshot_sha256: string
}

export interface OrderNoteHistoryResponse {
  invoice_number: number
  count: number
  notes: OrderNoteRecord[]
}

export interface CreateOrderNoteRequest {
  author_identity: string
  note: string
}
