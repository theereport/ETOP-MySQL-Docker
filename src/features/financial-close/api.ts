import { ApiError, requestJson } from '../../api/client'
import {
  clearWorkflowToken,
  getWorkflowToken,
} from '../workflow-foundation'
import type {
  CloseControlEventList,
  CloseControlSummary,
  CloseCycleDetail,
  CloseCycleListResponse,
  CloseTemplateDetail,
  CloseTemplateListResponse,
  CreateCloseControlRequest,
  CreateCloseCycleRequest,
  CreateClosePreparationRequest,
  CreateCloseReviewRequest,
  CreateCloseTemplateRequest,
  CreateCloseTemplateVersionRequest,
  FinancialCloseGovernance,
  InstantiateCloseTemplateRequest,
} from './types'

type RequestOptions = Parameters<typeof requestJson<unknown>>[1]

async function financialCloseRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const token = getWorkflowToken()
  if (!token) {
    throw new ApiError(
      'Sign in through Work Management before using Financial Close.',
      401,
    )
  }

  const headers = new Headers(options.headers)
  headers.set('Authorization', `Bearer ${token}`)

  try {
    return await requestJson<T>(`/financial-close${path}`, {
      ...options,
      headers,
    })
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      clearWorkflowToken()
    }
    if (error instanceof ApiError) {
      const details = error.details as {
        detail?: string | { message?: string }
      } | undefined
      const detail = details?.detail
      const message = typeof detail === 'string'
        ? detail
        : detail?.message
      if (message) {
        throw new ApiError(message, error.status, error.details)
      }
    }
    throw error
  }
}

export function getFinancialCloseGovernance(
  signal?: AbortSignal,
): Promise<FinancialCloseGovernance> {
  return financialCloseRequest('/governance', { signal })
}

export function getCloseCycles(
  signal?: AbortSignal,
): Promise<CloseCycleListResponse> {
  return financialCloseRequest('/cycles', { signal })
}

export function getCloseTemplates(
  signal?: AbortSignal,
): Promise<CloseTemplateListResponse> {
  return financialCloseRequest('/templates', { signal })
}

export function createCloseTemplate(
  payload: CreateCloseTemplateRequest,
  signal?: AbortSignal,
): Promise<CloseTemplateDetail> {
  return financialCloseRequest('/templates', {
    method: 'POST',
    body: payload,
    signal,
  })
}

export function getCloseTemplate(
  templateId: string,
  signal?: AbortSignal,
): Promise<CloseTemplateDetail> {
  return financialCloseRequest(
    `/templates/${encodeURIComponent(templateId)}`,
    { signal },
  )
}

export function createCloseTemplateVersion(
  templateId: string,
  payload: CreateCloseTemplateVersionRequest,
  signal?: AbortSignal,
): Promise<CloseTemplateDetail> {
  return financialCloseRequest(
    `/templates/${encodeURIComponent(templateId)}/versions`,
    {
      method: 'POST',
      body: payload,
      signal,
    },
  )
}

export function instantiateCloseTemplate(
  templateId: string,
  templateVersion: number,
  payload: InstantiateCloseTemplateRequest,
  signal?: AbortSignal,
): Promise<CloseCycleDetail> {
  return financialCloseRequest(
    `/templates/${encodeURIComponent(templateId)}/versions/${templateVersion}/instantiate`,
    {
      method: 'POST',
      body: payload,
      signal,
    },
  )
}

export function createCloseCycle(
  payload: CreateCloseCycleRequest,
  signal?: AbortSignal,
): Promise<CloseCycleDetail> {
  return financialCloseRequest('/cycles', {
    method: 'POST',
    body: payload,
    signal,
  })
}

export function getCloseCycle(
  cycleId: string,
  signal?: AbortSignal,
): Promise<CloseCycleDetail> {
  return financialCloseRequest(
    `/cycles/${encodeURIComponent(cycleId)}`,
    { signal },
  )
}

export function createCloseControl(
  cycleId: string,
  payload: CreateCloseControlRequest,
  signal?: AbortSignal,
): Promise<CloseControlSummary> {
  return financialCloseRequest(
    `/cycles/${encodeURIComponent(cycleId)}/controls`,
    {
      method: 'POST',
      body: payload,
      signal,
    },
  )
}

export function createClosePreparation(
  cycleId: string,
  controlId: string,
  payload: CreateClosePreparationRequest,
  signal?: AbortSignal,
): Promise<CloseControlSummary> {
  return financialCloseRequest(
    `/cycles/${encodeURIComponent(cycleId)}/controls/${encodeURIComponent(controlId)}/preparations`,
    {
      method: 'POST',
      body: payload,
      signal,
    },
  )
}

export function createCloseReview(
  cycleId: string,
  controlId: string,
  payload: CreateCloseReviewRequest,
  signal?: AbortSignal,
): Promise<CloseControlSummary> {
  return financialCloseRequest(
    `/cycles/${encodeURIComponent(cycleId)}/controls/${encodeURIComponent(controlId)}/reviews`,
    {
      method: 'POST',
      body: payload,
      signal,
    },
  )
}

export function getCloseControlEvents(
  cycleId: string,
  controlId: string,
  signal?: AbortSignal,
): Promise<CloseControlEventList> {
  return financialCloseRequest(
    `/cycles/${encodeURIComponent(cycleId)}/controls/${encodeURIComponent(controlId)}/events`,
    { signal },
  )
}
