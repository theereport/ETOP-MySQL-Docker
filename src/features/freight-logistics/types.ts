export interface SourceEvidence {
  system: string
  access: 'read_only'
  status: 'available'
  retrieved_at: string
}

export interface RouteSearchResult {
  route_key: string
  route_code: string
  warehouse_number: number | null
  warehouse_location_name: string
  status_code: string
  active: boolean
}

export interface RouteSearchResponse {
  contract_version: string
  source: SourceEvidence
  count: number
  routes: RouteSearchResult[]
}

export type WeekdayName =
  | 'Sunday'
  | 'Monday'
  | 'Tuesday'
  | 'Wednesday'
  | 'Thursday'
  | 'Friday'
  | 'Saturday'

export interface RouteScheduleDay {
  day: WeekdayName
  scheduled: boolean
  scheduled_stop_count: number
}

export interface WarehouseDirectionLabel {
  direction_name: string
  minimum_weight: number | null
  maximum_weight: number | null
  quantity_limit: number | null
  limit_by: string
  active: boolean
}

export interface WarehouseLabelEvidence {
  warehouse_number: number | null
  warehouse_location_name: string
  directions: WarehouseDirectionLabel[]
  source: string
  explanation: string
}

export interface RouteIdentityEvidence {
  route_key: string
  route_code: string
  warehouse_number: number | null
  status_code: string
  active: boolean
  schedule: RouteScheduleDay[]
  created_at: string | null
  created_by: string
  changed_at: string | null
  changed_by: string
}

export interface RouteLoadLine {
  store_number: number | null
  route: string
  status_code: string
  invoice_number: number | null
  customer_number: number | null
  line_number: number | null
  seq: number | null
  product_number: string
  description: string
  weight: number | null
  quantity: number | null
  created_at: string | null
  delivered_at: string | null
  delivered: boolean
  elapsed_minutes: number | null
}

export interface RouteLoadEvidence {
  line_count: number
  delivered_count: number
  undelivered_count: number
  total_weight: number
  total_quantity: number
  average_elapsed_minutes: number | null
  lines: RouteLoadLine[]
  source: string
  explanation: string
}

export interface CodPaymentCorrection {
  field: string
  before_value: string
  after_value: string
  reason: string
  changed_by: string
  changed_at: string | null
}

export interface CodPaymentDetailNote {
  notes: string
  created_at: string | null
  created_by: string
}

export interface CodPayment {
  payment_id: number
  customer_number: number | null
  route: string
  payment_type: string
  check_number: string
  auth_number: string
  amount: number
  notes: string
  invoices: string
  received: boolean
  received_at: string | null
  created_at: string | null
  corrections: CodPaymentCorrection[]
  detail_notes: CodPaymentDetailNote[]
}

export interface PaymentEvidence {
  payment_count: number
  total_amount: number
  received_count: number
  unreceived_count: number
  payments: CodPayment[]
  source: string
  explanation: string
}

export interface DeliveryException {
  customer_number: number | null
  route: string
  invoice_number: number | null
  line_number: number | null
  quantity: number | null
  option_code: string
  notes: string
  approved: boolean
  credit_invoice_number: number | null
  approval_notes: string
  approved_by: string
  created_at: string | null
  approved_at: string | null
}

export interface ExceptionEvidence {
  exception_count: number
  approved_count: number
  unapproved_count: number
  exceptions: DeliveryException[]
  source: string
  explanation: string
}

export interface DeliveryAdjustment {
  route: string
  invoice_number: number | null
  customer_number: number | null
  line_number: number | null
  seq: number | null
  line_type: string
  product_number: string
  description: string
  quantity: number | null
  created_at: string | null
  uploaded_at: string | null
}

export interface AdjustmentEvidence {
  adjustment_count: number
  adjustments: DeliveryAdjustment[]
  source: string
  explanation: string
}

export interface SignatureCaptureSession {
  serial_number: string
  route: string
  session_type: string
  created_at: string | null
  created_by: string
}

export interface SignatureCaptureEvidence {
  session_count: number
  sessions: SignatureCaptureSession[]
  source: string
  explanation: string
}

export interface SignatureImage {
  customer_number: number | null
  invoice_number: number | null
  signer_name: string
  file_name: string
  created_at: string | null
  uploaded_at: string | null
}

export interface ImageEvidence {
  image_count: number
  images: SignatureImage[]
  source: string
  explanation: string
}

export interface RouteEvidenceGap {
  code: string
  label: string
  status: 'unavailable'
  explanation: string
}

export interface RouteEvidenceResponse {
  contract_version: string
  generated_at: string
  source: SourceEvidence
  identity: RouteIdentityEvidence
  warehouse_label: WarehouseLabelEvidence
  load: RouteLoadEvidence
  payments: PaymentEvidence
  exceptions: ExceptionEvidence
  adjustments: AdjustmentEvidence
  signature_sessions: SignatureCaptureEvidence
  images: ImageEvidence
  gaps: RouteEvidenceGap[]
  governance: {
    assessment_type: 'evidence_only'
    automatic_score: boolean
    decision_effect: 'none'
    erp_write: boolean
  }
}

export interface RouteNoteRecord {
  note_id: string
  route_code: string
  warehouse_number: number | null
  author_identity: string
  note: string
  created_at: string
  source_as_of: string
  decision_effect: 'none'
  erp_write: false
  evidence_snapshot_sha256: string
}

export interface RouteNoteHistoryResponse {
  route_code: string
  count: number
  notes: RouteNoteRecord[]
}

export interface CreateRouteNoteRequest {
  author_identity: string
  note: string
}
