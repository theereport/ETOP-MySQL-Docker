export type WorkflowRoleId =
  | 'workflow_coordinator'
  | 'credit_professional'
  | 'ap_professional'
  | 'workflow_observer'

export type ETOPModuleId =
  | 'dashboard'
  | 'customer_360'
  | 'credit_risk'
  | 'accounts_payable'
  | 'financial_close'
  | 'cash_application'
  | 'payment_notes'
  | 'lockbox'
  | 'carryover_dashboard'
  | 'document_intelligence'
  | 'automation_center'
  | 'work_management'
  | 'report_builder'
  | 'sql_workspace'
  | 'knowledge_base'
  | 'ai_assistant'
  | 'document_ai_studio'
  | 'security_administration'
  | 'vendor_intelligence'
  | 'ar_collections'
  | 'freight_logistics'
  | 'inventory_purchasing'
  | 'tax_compliance'
  | 'sales_order_visibility'
  | 'pricing_contracts'
  | 'general_ledger'
  | 'cash_flow_forecasting'

export type EffectivePermissions = {
  module_ids: ETOPModuleId[]
  access_version: number
  default_behavior: 'deny'
  authority_effect: 'none'
  decision_authority: false
}

export type WorkflowRole = {
  role_id: WorkflowRoleId
  name: string
  description: string
  queue_scope: string
  authority_effect: 'none'
  decision_authority: false
}

export type WorkflowUser = {
  person_id: string
  user_id: string
  username: string
  display_name: string
  status: 'active' | 'inactive'
  roles: WorkflowRole[]
  authentication_assurance: 'local_credential'
  authority_status: 'not_configured'
  created_at: string
}

export type WorkflowSession = {
  expires_at: string
  user: WorkflowUser
  permissions: EffectivePermissions
  authority_boundary: string
}

export type WorkflowAuthResponse = WorkflowSession & {
  token: string
}

export type WorkflowBootstrapStatus = {
  bootstrap_required: boolean
  account_count: number
  authentication_boundary: string
  authority_boundary: string
}

export type WorkflowCapability =
  | 'credit_risk'
  | 'accounts_payable'
  | 'lockbox'
  | 'reporting'
  | 'platform'

export type WorkflowTaskState =
  | 'open'
  | 'in_progress'
  | 'deferred'
  | 'completed'
  | 'cancelled'
  | 'reopened'

export type WorkflowTask = {
  task_id: string
  definition_id: string
  definition_version: string
  title: string
  description: string
  capability: WorkflowCapability
  context_type: string
  context_id: string
  context_label: string
  queue_role: WorkflowRole
  assignee: WorkflowUser | null
  priority: 'low' | 'medium' | 'high' | 'critical'
  state: WorkflowTaskState
  due_date: string | null
  created_by: WorkflowUser
  created_at: string
  updated_at: string
  version: number
  permitted_actions: string[]
  assignment_effect: 'work_ownership_only'
  authority_effect: 'none'
  execution_effect: 'none'
}

export type WorkflowAssignment = {
  assignment_event_id: string
  task_id: string
  assignee: WorkflowUser
  prior_assignee_user_id: string | null
  assigned_by: WorkflowUser
  assignment_type: 'initial' | 'claim' | 'reassign'
  note: string
  task_version: number
  created_at: string
  authority_effect: 'none'
}

export type WorkflowTaskEvent = {
  event_id: string
  task_id: string
  event_type: 'task_created' | 'task_state_changed'
  from_state: WorkflowTaskState | null
  to_state: WorkflowTaskState
  actor: WorkflowUser
  note: string
  task_version: number
  created_at: string
}

export type WorkflowTaskDetail = WorkflowTask & {
  assignments: WorkflowAssignment[]
  events: WorkflowTaskEvent[]
}

export type WorkflowTaskList = {
  items: WorkflowTask[]
  total: number
  queue_scope: 'personal_and_role' | 'coordinator_all'
  authority_boundary: string
}

export type WorkflowNotification = {
  notification_id: string
  task_id: string | null
  notification_type: string
  title: string
  message: string
  severity: 'info' | 'success' | 'warning' | 'critical'
  created_at: string
  read_at: string | null
}

export type WorkflowNotificationList = {
  items: WorkflowNotification[]
  unread_count: number
  delivery_scope: 'in_app_local'
}

export type WorkflowAuditEvent = {
  audit_id: string
  event_type: string
  actor_user_id: string | null
  subject_type: string
  subject_id: string
  correlation_id: string
  occurred_at: string
  details: Record<string, unknown>
  previous_hash: string
  record_hash: string
  schema_version: '1.0'
}

export type WorkflowAuditIntegrity = {
  valid: boolean
  checked_records: number
  first_invalid_audit_id: string | null
  algorithm: 'sha256_hash_chain'
}

export type WorkflowHealth = {
  status: 'ready'
  users: number
  open_tasks: number
  unread_notifications: number
  audit_records: number
  audit_integrity: WorkflowAuditIntegrity
  authority_boundary: string
  erp_access: 'none'
}

export type WorkflowTaskCreate = {
  title: string
  description: string
  capability: WorkflowCapability
  context_type: string
  context_id: string
  context_label: string
  queue_role_id: WorkflowRoleId
  assignee_user_id?: string
  priority: WorkflowTask['priority']
  due_date?: string
  idempotency_key: string
}
