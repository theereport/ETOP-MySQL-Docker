import type { WorkflowUser } from '../workflow-foundation'

export type CloseControlState =
  | 'not_started'
  | 'awaiting_review'
  | 'attention_required'
  | 'evidence_sufficient'
  | 'stale'

export type CloseEvidenceStatus =
  | 'not_recorded'
  | 'reference_recorded'
  | 'missing'
  | 'unavailable'

export type CloseReviewCurrency = 'not_reviewed' | 'current' | 'stale'

export type ClosePreparationDisposition = Exclude<
  CloseEvidenceStatus,
  'not_recorded'
>

export type CloseReviewDisposition =
  | 'evidence_sufficient'
  | 'needs_information'
  | 'not_ready'
  | 'deferred'

export type CloseCycleReadiness =
  | 'not_started'
  | 'in_progress'
  | 'attention_required'
  | 'evidence_ready'

export type CloseIdentity = Pick<
  WorkflowUser,
  'person_id' | 'user_id' | 'username' | 'display_name' | 'status'
>

export type FinancialCloseAuthorityBoundary = {
  identity_source: 'workflow_foundation_local_account'
  authority_effect: 'none'
  close_effect: 'none'
  approval_effect: 'none'
  posting_effect: 'none'
  erp_write: false
  statements: string[]
}

export type FinancialCloseGovernance = {
  contract_version: 'financial-close-readiness.v1'
  planning_contract_version: 'financial-close-planning.v1'
  capability_status: 'local_evidence_readiness'
  erp_period_state: 'unavailable'
  books_close_state: 'unavailable'
  template_authority: 'local_user_authored_planning_draft'
  calendar_effect: 'planning_dates_only'
  source_coverage: Array<{
    key: string
    label: string
    status: string
    explanation: string
  }>
  authority: FinancialCloseAuthorityBoundary
  deferred_capabilities: Array<{
    key: string
    label: string
    reason: string
  }>
}

export type CloseControlCounts = {
  total: number
  not_started: number
  awaiting_review: number
  attention_required: number
  evidence_sufficient: number
  stale: number
}

export type CloseCycleSummary = {
  cycle_id: string
  entity_label: string
  period_label: string
  period_start: string
  period_end: string
  target_completion_date: string | null
  description: string
  created_by: CloseIdentity
  created_at: string
  version: number
  control_counts: CloseControlCounts
  readiness: CloseCycleReadiness
  readiness_scope: 'local_evidence_readiness_only'
  erp_period_state: 'unavailable'
  close_effect: 'none'
  template_lineage: CloseCycleTemplateLineage | null
}

export type CloseControlSummary = {
  control_id: string
  cycle_id: string
  title: string
  description: string
  planned_date: string | null
  preparer: CloseIdentity
  reviewer: CloseIdentity
  state: CloseControlState
  evidence_status: CloseEvidenceStatus
  review_currency: CloseReviewCurrency
  version: number
  latest_preparation_at: string | null
  latest_review_at: string | null
  created_by: CloseIdentity
  created_at: string
  updated_at: string
  authority_effect: 'none'
  close_effect: 'none'
  template_lineage: CloseControlTemplateLineage | null
}

export type CloseCycleTemplateLineage = {
  snapshot_id: string
  template_id: string
  template_version: number
  template_title: string
  template_version_sha256: string
  calendar_anchor_date: string
  planning_date_rule: 'calendar_anchor_plus_offset_days'
  instantiated_by: CloseIdentity
  instantiated_at: string
  snapshot_sha256: string
  policy_effect: 'none'
  automation_effect: 'none'
}

export type CloseControlTemplateLineage = {
  snapshot_id: string
  template_id: string
  template_version: number
  template_item_id: string
  template_item_sha256: string
  planned_offset_days: number
  planning_date_rule: 'calendar_anchor_plus_offset_days'
}

export type CloseCycleDetail = CloseCycleSummary & {
  controls: CloseControlSummary[]
  events: CloseEvent[]
  evidence_sha256: string
}

export type CloseEvent = {
  event_id: string
  cycle_id: string
  control_id: string | null
  event_type: string
  actor: CloseIdentity
  occurred_at: string
  details: Record<string, unknown>
  previous_hash: string
  record_hash: string
  authority_effect: 'none'
  close_effect: 'none'
}

export type CloseControlEventList = {
  items: CloseEvent[]
  integrity: {
    valid: boolean
    checked_records: number
    first_invalid_event_id: string | null
    algorithm: 'sha256_hash_chain'
  }
}

export type CloseCycleListResponse = {
  contract_version: 'financial-close-readiness.v1'
  items: CloseCycleSummary[]
  total: number
  governance: FinancialCloseGovernance
}

export type CloseTemplateItem = {
  item_id: string
  template_id: string
  template_version: number
  ordinal: number
  title: string
  description: string
  planned_offset_days: number
  preparer: CloseIdentity
  reviewer: CloseIdentity
  item_sha256: string
}

export type CloseTemplateVersion = {
  template_id: string
  version: number
  title: string
  description: string
  change_note: string
  status: 'local_user_authored_planning_draft'
  created_by: CloseIdentity
  created_at: string
  previous_version_sha256: string
  version_sha256: string
  items: CloseTemplateItem[]
  policy_effect: 'none'
  automation_effect: 'none'
}

export type CloseTemplateEvent = {
  event_id: string
  template_id: string
  event_type:
    | 'template_created'
    | 'template_version_created'
    | 'cycle_instantiated'
  actor: CloseIdentity
  occurred_at: string
  details: Record<string, unknown>
  sequence: number
  previous_hash: string
  record_hash: string
  authority_effect: 'none'
  policy_effect: 'none'
  automation_effect: 'none'
}

export type CloseTemplateSummary = {
  template_id: string
  title: string
  description: string
  latest_version: number
  version_count: number
  item_count: number
  latest_version_sha256: string
  status: 'local_user_authored_planning_draft'
  created_by: CloseIdentity
  created_at: string
  policy_effect: 'none'
  automation_effect: 'none'
}

export type CloseTemplateDetail = CloseTemplateSummary & {
  versions: CloseTemplateVersion[]
  events: CloseTemplateEvent[]
  integrity: {
    valid: boolean
    checked_records: number
    first_invalid_event_id: string | null
    algorithm: 'sha256_hash_chain'
  }
}

export type CloseTemplateListResponse = {
  contract_version: 'financial-close-planning.v1'
  items: CloseTemplateSummary[]
  total: number
  template_authority: 'local_user_authored_planning_draft'
  policy_effect: 'none'
  automation_effect: 'none'
}

export type CreateCloseTemplateItemRequest = {
  title: string
  description: string
  planned_offset_days: number
  preparer_user_id: string
  reviewer_user_id: string
}

export type CreateCloseTemplateRequest = {
  title: string
  description: string
  items: CreateCloseTemplateItemRequest[]
  idempotency_key: string
}

export type CreateCloseTemplateVersionRequest = {
  title: string
  description: string
  change_note: string
  items: CreateCloseTemplateItemRequest[]
  expected_latest_version: number
  idempotency_key: string
}

export type InstantiateCloseTemplateRequest = {
  entity_label: string
  period_label: string
  period_start: string
  period_end: string
  calendar_anchor_date: string
  target_completion_date?: string
  description: string
  idempotency_key: string
}

export type CreateCloseCycleRequest = {
  entity_label: string
  period_label: string
  period_start: string
  period_end: string
  target_completion_date?: string
  description: string
  idempotency_key: string
}

export type CreateCloseControlRequest = {
  title: string
  description: string
  planned_date?: string
  preparer_user_id: string
  reviewer_user_id: string
  idempotency_key: string
}

export type CreateClosePreparationRequest = {
  disposition: ClosePreparationDisposition
  evidence_reference?: string
  note: string
  expected_control_version: number
  idempotency_key: string
}

export type CreateCloseReviewRequest = {
  disposition: CloseReviewDisposition
  note: string
  expected_control_version: number
  idempotency_key: string
}

export type FinancialCloseWorkspaceProps = {
  onOpenWorkManagement?: () => void
}
