export interface SourceEvidence {
  system: string
  access: 'read_only'
  status: 'available'
  retrieved_at: string
}

export interface ProductSearchResult {
  product_number: string
  description: string
  search_key: string
  product_class: string
  product_type: string
  brand: string
  unit_of_measure: string
  vendor_code: string
  active: boolean
  non_inventory: boolean
}

export interface ProductSearchResponse {
  contract_version: string
  source: SourceEvidence
  count: number
  products: ProductSearchResult[]
}

export interface ProductIdentityEvidence {
  product_number: string
  search_key: string
  description: string
  product_class: string
  product_type: string
  brand: string
  size: string
  load_index: string
  speed_rating: string
  manufacturer_product_number: string
  barcode: string
  unit_of_measure: string
  vendor_code: string
  store_number: number | null
  warehouse_location: string
  warehouse_alt_location: string
  active: boolean
  non_inventory: boolean
  allow_po_creation: boolean
  date_created: string | null
  date_last_received: string | null
  date_last_sold: string | null
}

export interface ProductCostingEvidence {
  vendor_cost: number | null
  actual_cost: number | null
  replacement_cost: number | null
  last_year_cost: number | null
  price_1: number | null
  price_2: number | null
  price_3: number | null
  price_4: number | null
  price_5: number | null
  price_6: number | null
  source: string
}

export interface ProductInventoryPositionEvidence {
  on_hand: number | null
  on_order: number | null
  allocated: number | null
  configured_minimum: number | null
  configured_maximum: number | null
  inventory_turns: number | null
  ordering_lead_time_days: number | null
  source: string
  explanation: string
}

export interface MonthEndInventoryPeriod {
  store_number: number | null
  month: number | null
  year: number | null
  vendor_number: string
  class_number: string
  units: number
  total_cost: number
  total_fet: number
}

export interface MonthEndInventoryEvidence {
  period_count: number
  periods: MonthEndInventoryPeriod[]
  latest_period_total_units: number | null
  latest_period_total_cost: number | null
  source: string
  explanation: string
}

export interface OpenPurchaseOrderLine {
  po_number: number
  vendor_number: number | null
  po_date: string | null
  date_required: string | null
  status_code: string
  complete: boolean
  ship_via: string
  buyer_number: number | null
  ordered_quantity: number
  received_quantity: number
  backorder_quantity: number
  average_unit_cost: number | null
  line_total_cost: number | null
}

export interface PurchaseExposureEvidence {
  open_order_count: number
  open_order_total_cost: number
  open_orders: OpenPurchaseOrderLine[]
  source: string
  explanation: string
}

export interface ReceivingEvent {
  po_number: number
  vendor_number: number | null
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

export interface ProductEvidenceGap {
  code: string
  label: string
  status: 'unavailable'
  explanation: string
}

export interface ProductEvidenceResponse {
  contract_version: string
  generated_at: string
  source: SourceEvidence
  identity: ProductIdentityEvidence
  costing: ProductCostingEvidence
  inventory_position: ProductInventoryPositionEvidence
  month_end_inventory: MonthEndInventoryEvidence
  purchase_exposure: PurchaseExposureEvidence
  receiving: ReceivingEvidence
  gaps: ProductEvidenceGap[]
  governance: {
    assessment_type: 'evidence_only'
    automatic_score: boolean
    decision_effect: 'none'
    erp_write: boolean
  }
}

export interface InventoryNoteRecord {
  note_id: string
  product_number: string
  product_description: string
  author_identity: string
  note: string
  created_at: string
  source_as_of: string
  decision_effect: 'none'
  erp_write: false
  evidence_snapshot_sha256: string
}

export interface InventoryNoteHistoryResponse {
  product_number: string
  count: number
  notes: InventoryNoteRecord[]
}

export interface CreateInventoryNoteRequest {
  author_identity: string
  note: string
}
