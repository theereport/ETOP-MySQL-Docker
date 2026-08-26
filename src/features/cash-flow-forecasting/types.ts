export interface SourceEvidence {
  system: string
  access: 'read_only'
  status: 'available' | 'unavailable_source_capability'
  retrieved_at: string
}

export interface StartingCashPosition {
  business_day: string | null
  net_available: number | null
  line_of_credit_balance: number | null
  line_of_credit_available: number | null
  line_of_credit_withholding: number | null
  status: 'available' | 'unavailable_source_capability'
  source: string
  explanation: string
}

export interface WeeklyProjection {
  week_index: number
  week_start: string
  week_end: string
  projected_ar: number
  projected_ap: number | null
  projected_ap_on_hold: number | null
  projected_other: number
  projected_net_change: number | null
  projected_ending_balance: number | null
}

export interface PriorYearWeekComparison {
  week_index: number
  week_start: string
  week_end: string
  prior_year_week_start: string
  prior_year_week_end: string

  prior_year_projected_ar: number
  prior_year_projected_ap: number | null
  prior_year_projected_other: number
  prior_year_projected_ending_balance: number | null

  prior_year_actual_ar: number | null
  prior_year_actual_ap: number | null
  prior_year_actual_other: number | null
  prior_year_actual_ending_balance: number | null

  prior_year_variance_ar: number | null
  prior_year_variance_ap: number | null
  prior_year_variance_other: number | null
  prior_year_variance_ending_balance: number | null

  current_year_week_closed: boolean
  current_year_actual_ar: number | null
  current_year_actual_ap: number | null
  current_year_actual_other: number | null
  current_year_actual_ending_balance: number | null
}

export interface CashFlowForecastGap {
  code: string
  label: string
  status: 'unavailable'
  explanation: string
}

export interface CashFlowForecastResponse {
  contract_version: string
  generated_at: string
  as_of: string
  horizon_weeks: number
  source: SourceEvidence
  starting_position: StartingCashPosition
  weeks: WeeklyProjection[]
  prior_year_comparison: PriorYearWeekComparison[]
  gaps: CashFlowForecastGap[]
  governance: {
    assessment_type: 'evidence_only'
    automatic_score: boolean
    decision_effect: 'none'
    erp_write: boolean
  }
}

export interface CashFlowSnapshotSummary {
  snapshot_id: string
  as_of: string
  generated_at: string
  horizon_weeks: number
}

export interface CashFlowSnapshotHistoryResponse {
  count: number
  snapshots: CashFlowSnapshotSummary[]
}

export interface CashFlowAccuracyWeek {
  week_start: string
  week_end: string
  projected_ar: number
  projected_ap: number
  projected_other: number
  projected_ending_balance: number | null
  actual_ar: number
  actual_ap: number
  actual_other: number
  actual_ending_balance: number | null
  variance_ar: number
  variance_ap: number
  variance_other: number
  variance_ending_balance: number | null
  recorded_at: string
}

export interface CashFlowAccuracyHistoryResponse {
  count: number
  weeks: CashFlowAccuracyWeek[]
  explanation: string
}

export interface ApCacheRefreshResult {
  status: string
  weeks_cached?: number
  source_rows?: number
  refreshed_at?: string
  message?: string
}

export interface RecordClosedWeeksResult {
  recorded: number
  already_recorded: number
}
