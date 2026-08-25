import type {
  ETOPModuleId,
  WorkflowAuditEvent,
  WorkflowAuditIntegrity,
  WorkflowAuthResponse,
  WorkflowBootstrapStatus,
  WorkflowHealth,
  WorkflowNotification,
  WorkflowNotificationList,
  WorkflowRole,
  WorkflowRoleId,
  WorkflowSession,
  WorkflowTaskCreate,
  WorkflowTaskDetail,
  WorkflowTaskList,
  WorkflowTaskState,
  WorkflowUser,
} from './types'

const API_BASE = 'http://127.0.0.1:8000/api/v1/workflow-foundation'
const TOKEN_KEY = 'etop.workflow.session.v1'
export const WORKFLOW_SESSION_EVENT = 'etop-workflow-session-changed'

export class WorkflowApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'WorkflowApiError'
    this.status = status
  }
}

export function workflowIdempotencyKey(prefix: string): string {
  const id = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`
  return `${prefix}-${id}`
}

export function getWorkflowToken(): string | null {
  return window.sessionStorage.getItem(TOKEN_KEY)
}

export function saveWorkflowToken(token: string): void {
  window.sessionStorage.setItem(TOKEN_KEY, token)
  window.dispatchEvent(new Event(WORKFLOW_SESSION_EVENT))
}

export function clearWorkflowToken(): void {
  window.sessionStorage.removeItem(TOKEN_KEY)
  window.dispatchEvent(new Event(WORKFLOW_SESSION_EVENT))
}

export async function workflowRequest<T>(
  path: string,
  init: RequestInit = {},
  token: string | null = getWorkflowToken(),
): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers })
  if (response.status === 204) {
    return undefined as T
  }
  const body = await response.json().catch(() => null) as {
    detail?: string | { message?: string }
  } | null
  if (!response.ok) {
    if (response.status === 401) {
      clearWorkflowToken()
    }
    const detail = body?.detail
    const message = typeof detail === 'string'
      ? detail
      : detail?.message ?? 'The governed workflow request could not be completed.'
    throw new WorkflowApiError(message, response.status)
  }
  return body as T
}

const request = workflowRequest

export function getBootstrapStatus(signal?: AbortSignal): Promise<WorkflowBootstrapStatus> {
  return request('/bootstrap-status', { signal }, null)
}

export function bootstrapWorkflowAccount(payload: {
  username: string
  display_name: string
  password: string
}): Promise<WorkflowAuthResponse> {
  return request('/bootstrap', { method: 'POST', body: JSON.stringify(payload) }, null)
}

export function loginWorkflow(payload: {
  username: string
  password: string
}): Promise<WorkflowAuthResponse> {
  return request('/sessions', { method: 'POST', body: JSON.stringify(payload) }, null)
}

export function getWorkflowSession(signal?: AbortSignal): Promise<WorkflowSession> {
  return request('/session', { signal })
}

export async function logoutWorkflow(): Promise<void> {
  try {
    await request<void>('/session', { method: 'DELETE' })
  } finally {
    clearWorkflowToken()
  }
}

export function getWorkflowHealth(signal?: AbortSignal): Promise<WorkflowHealth> {
  return request('/health', { signal })
}

export async function getWorkflowUsers(signal?: AbortSignal): Promise<WorkflowUser[]> {
  const result = await request<{ users: WorkflowUser[] }>('/users', { signal })
  return result.users
}

export function createWorkflowUser(payload: {
  username: string
  display_name: string
  password: string
  role_ids: WorkflowRoleId[]
  module_ids?: ETOPModuleId[]
}): Promise<WorkflowUser> {
  return request('/users', { method: 'POST', body: JSON.stringify(payload) })
}

export function getWorkflowRoles(signal?: AbortSignal): Promise<WorkflowRole[]> {
  return request('/roles', { signal })
}

export function getWorkflowTasks(filters: {
  mine?: boolean
  capability?: string
  state?: string
} = {}, signal?: AbortSignal): Promise<WorkflowTaskList> {
  const params = new URLSearchParams()
  if (filters.mine !== undefined) params.set('mine', String(filters.mine))
  if (filters.capability) params.set('capability', filters.capability)
  if (filters.state) params.set('state', filters.state)
  const query = params.size ? `?${params.toString()}` : ''
  return request(`/tasks${query}`, { signal })
}

export function getWorkflowTask(taskId: string, signal?: AbortSignal): Promise<WorkflowTaskDetail> {
  return request(`/tasks/${encodeURIComponent(taskId)}`, { signal })
}

export function createWorkflowTask(payload: WorkflowTaskCreate): Promise<WorkflowTaskDetail> {
  return request('/tasks', { method: 'POST', body: JSON.stringify(payload) })
}

export function assignWorkflowTask(
  taskId: string,
  payload: {
    assignee_user_id: string
    note: string
    expected_version: number
    idempotency_key: string
  },
): Promise<WorkflowTaskDetail> {
  return request(`/tasks/${encodeURIComponent(taskId)}/assignments`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function transitionWorkflowTask(
  taskId: string,
  payload: {
    target_state: WorkflowTaskState
    note: string
    expected_version: number
    idempotency_key: string
  },
): Promise<WorkflowTaskDetail> {
  return request(`/tasks/${encodeURIComponent(taskId)}/transitions`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function getWorkflowNotifications(signal?: AbortSignal): Promise<WorkflowNotificationList> {
  return request('/notifications', { signal })
}

export function markWorkflowNotificationRead(notificationId: string): Promise<WorkflowNotification> {
  return request(`/notifications/${encodeURIComponent(notificationId)}/read`, { method: 'POST' })
}

export async function getWorkflowAudit(signal?: AbortSignal): Promise<WorkflowAuditEvent[]> {
  const result = await request<{ items: WorkflowAuditEvent[] }>('/audit', { signal })
  return result.items
}

export function verifyWorkflowAudit(signal?: AbortSignal): Promise<WorkflowAuditIntegrity> {
  return request('/audit/integrity', { signal })
}
