import { API_BASE, ApiError, requestJson } from '../../api/client'
import {
  searchCustomers as searchSharedCustomers,
} from '../customer360/api'
import type { CustomerSearchResponse } from '../customer360/types'
import type {
  AssessmentHistoryResponse,
  CreateAssessmentRequest,
  CreateCreditLineProposalRequest,
  CreatePortfolioReviewRequest,
  CreateOrderRecommendationRequest,
  CreditLineIntelligenceResponse,
  CreditLineProposal,
  CreditLineProposalHistoryResponse,
  CreditRiskAssessment,
  CustomerRiskSnapshot,
  PriorityAlertsResponse,
  PortfolioMonitoringResponse,
  PortfolioReview,
  OrderDecisionPreparationResponse,
  OrderRecommendation,
  OrderRecommendationHistoryResponse,
  RiskBandResponse,
  CreditERPEvidenceResponse,
} from './types'

type JsonRecord = Record<string, unknown>

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null
}

async function creditRiskRequest<T>(
  path: string,
  options: Parameters<typeof requestJson<T>>[1] = {},
): Promise<T> {
  try {
    return await requestJson<T>(path, options)
  } catch (error) {
    if (error instanceof ApiError && isRecord(error.details)) {
      const detail = error.details.detail

      if (isRecord(detail) && typeof detail.message === 'string') {
        throw new ApiError(detail.message, error.status, detail)
      }
    }

    throw error
  }
}

export function searchCreditRiskCustomers(
  search: string,
  signal?: AbortSignal,
): Promise<CustomerSearchResponse> {
  return searchSharedCustomers(search, signal, true)
}

export function getRiskBands(
  signal?: AbortSignal,
): Promise<RiskBandResponse> {
  return creditRiskRequest<RiskBandResponse>('/credit-risk/bands', { signal })
}

export function getCreditRiskPriorityAlerts(
  signal?: AbortSignal,
): Promise<PriorityAlertsResponse> {
  return creditRiskRequest<PriorityAlertsResponse>('/credit-risk/priority-alerts', {
    signal,
  })
}

export function getCustomerRiskSnapshot(
  customerNumber: number | string,
  signal?: AbortSignal,
): Promise<CustomerRiskSnapshot> {
  const customer = encodeURIComponent(String(customerNumber))
  return creditRiskRequest<CustomerRiskSnapshot>(`/credit-risk/customers/${customer}`, {
    signal,
  })
}

export function getCreditERPEvidence(
  customerNumber: number | string,
  signal?: AbortSignal,
): Promise<CreditERPEvidenceResponse> {
  const customer = encodeURIComponent(String(customerNumber))
  return creditRiskRequest<CreditERPEvidenceResponse>(
    `/erp-evidence/credit/customers/${customer}?open_item_limit=200`,
    { signal },
  )
}

export function getCustomerRiskAssessments(
  customerNumber: number | string,
  signal?: AbortSignal,
): Promise<AssessmentHistoryResponse> {
  const customer = encodeURIComponent(String(customerNumber))
  return creditRiskRequest<AssessmentHistoryResponse>(
    `/credit-risk/customers/${customer}/assessments`,
    { signal },
  )
}

export function createCustomerRiskAssessment(
  customerNumber: number | string,
  assessment: CreateAssessmentRequest,
  signal?: AbortSignal,
): Promise<CreditRiskAssessment> {
  const customer = encodeURIComponent(String(customerNumber))
  return creditRiskRequest<CreditRiskAssessment>(
    `/credit-risk/customers/${customer}/assessments`,
    {
      method: 'POST',
      body: assessment,
      signal,
    },
  )
}

export function getCreditLineIntelligence(
  customerNumber: number | string,
  signal?: AbortSignal,
): Promise<CreditLineIntelligenceResponse> {
  const customer = encodeURIComponent(String(customerNumber))
  return creditRiskRequest<CreditLineIntelligenceResponse>(
    `/credit-risk/customers/${customer}/credit-line-intelligence`,
    { signal },
  )
}

export function getCreditLineProposals(
  customerNumber: number | string,
  signal?: AbortSignal,
): Promise<CreditLineProposalHistoryResponse> {
  const customer = encodeURIComponent(String(customerNumber))
  return creditRiskRequest<CreditLineProposalHistoryResponse>(
    `/credit-risk/customers/${customer}/credit-line-proposals`,
    { signal },
  )
}

export function createCreditLineProposal(
  customerNumber: number | string,
  proposal: CreateCreditLineProposalRequest,
  signal?: AbortSignal,
): Promise<CreditLineProposal> {
  const customer = encodeURIComponent(String(customerNumber))
  return creditRiskRequest<CreditLineProposal>(
    `/credit-risk/customers/${customer}/credit-line-proposals`,
    {
      method: 'POST',
      body: proposal,
      signal,
    },
  )
}

export function getCreditPortfolioMonitoring(
  signal?: AbortSignal,
): Promise<PortfolioMonitoringResponse> {
  return creditRiskRequest<PortfolioMonitoringResponse>(
    '/credit-risk/portfolio-monitoring',
    { signal },
  )
}

export function createCreditPortfolioReview(
  customerNumber: number | string,
  review: CreatePortfolioReviewRequest,
  signal?: AbortSignal,
): Promise<PortfolioReview> {
  const customer = encodeURIComponent(String(customerNumber))
  return creditRiskRequest<PortfolioReview>(
    `/credit-risk/customers/${customer}/portfolio-reviews`,
    {
      method: 'POST',
      body: review,
      signal,
    },
  )
}

export function getOrderDecisionPreparation(
  customerNumber: number | string,
  contemplatedOrderAmount: number,
  orderReference?: string,
  signal?: AbortSignal,
): Promise<OrderDecisionPreparationResponse> {
  const customer = encodeURIComponent(String(customerNumber))
  const parameters = new URLSearchParams({
    contemplated_order_amount: String(contemplatedOrderAmount),
  })
  if (orderReference?.trim()) {
    parameters.set('order_reference', orderReference.trim())
  }
  return creditRiskRequest<OrderDecisionPreparationResponse>(
    `/credit-risk/customers/${customer}/order-decision-preparation?${parameters.toString()}`,
    { signal },
  )
}

export function getOrderRecommendations(
  customerNumber: number | string,
  signal?: AbortSignal,
): Promise<OrderRecommendationHistoryResponse> {
  const customer = encodeURIComponent(String(customerNumber))
  return creditRiskRequest<OrderRecommendationHistoryResponse>(
    `/credit-risk/customers/${customer}/order-recommendations`,
    { signal },
  )
}

export function createOrderRecommendation(
  customerNumber: number | string,
  payload: CreateOrderRecommendationRequest,
  signal?: AbortSignal,
): Promise<OrderRecommendation> {
  const customer = encodeURIComponent(String(customerNumber))
  return creditRiskRequest<OrderRecommendation>(
    `/credit-risk/customers/${customer}/order-recommendations`,
    {
      method: 'POST',
      body: payload,
      signal,
    },
  )
}

export async function getPotentialCustomers(
  signal?: AbortSignal,
): Promise<import('./types').PotentialCustomerListResponse> {
  return creditRiskRequest<import('./types').PotentialCustomerListResponse>(
    '/credit-risk/potential-customers',
    { signal },
  )
}

export async function uploadPotentialCustomerApplication(
  file: File,
  signal?: AbortSignal,
): Promise<import('./types').PotentialCustomerRecord> {
  const form = new FormData()
  form.append('file', file)
  const response = await fetch(
    `${API_BASE}/credit-risk/potential-customers/upload`,
    { method: 'POST', body: form, signal, headers: { Accept: 'application/json' } },
  )
  if (!response.ok) {
    let message = `Upload failed with status ${response.status}.`
    try {
      const details = await response.json() as { detail?: { message?: string } }
      message = details.detail?.message || message
    } catch {
      // Keep the HTTP status fallback when the backend returned no JSON.
    }
    throw new ApiError(message, response.status)
  }
  return await response.json() as import('./types').PotentialCustomerRecord
}

export function updatePotentialCustomerReview(
  potentialCustomerId: string,
  payload: { status: string; km_setup?: Record<string, unknown>; review_notes?: string; field_updates?: Record<string, unknown> },
  signal?: AbortSignal,
): Promise<import('./types').PotentialCustomerRecord> {
  const id = encodeURIComponent(potentialCustomerId)
  return creditRiskRequest<import('./types').PotentialCustomerRecord>(
    `/credit-risk/potential-customers/${id}/review`,
    { method: 'PUT', body: payload, signal },
  )
}
