// From workflow-foundation's own api.ts, not its barrel - that barrel also
// statically re-exports WorkflowFoundationWorkspace, and this module is
// reachable from App.tsx's always-eager job-queue import.
import { getWorkflowToken } from '../workflow-foundation/api'
import type { JobQueueJob, JobQueueSummary } from './types'

const API_BASE = 'http://127.0.0.1:8000/api/v1/platform/job-queue'

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getWorkflowToken()
  const headers = new Headers(init.headers)
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers })
  if (!response.ok) {
    throw new Error(`Job queue request failed: ${response.status}`)
  }
  const body = (await response.json()) as { data: T }
  return body.data
}

export function getJobQueueSummary(signal?: AbortSignal): Promise<JobQueueSummary> {
  return request('/summary', { signal })
}

export function getJobQueueJobs(signal?: AbortSignal): Promise<JobQueueJob[]> {
  return request('/jobs', { signal })
}

export function acknowledgeJobQueueItem(jobId: string): Promise<void> {
  return request(`/jobs/${encodeURIComponent(jobId)}/acknowledge`, {
    method: 'POST',
  })
}
