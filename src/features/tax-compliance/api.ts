import { ApiError, requestJson } from '../../api/client'
import type {
  CreateTaxComplianceNoteRequest,
  CustomerExemptionCheckBatchResponse,
  CustomerExemptionCheckResponse,
  TaxAuthoritySearchResponse,
  TaxComplianceNoteHistoryResponse,
  TaxComplianceNoteRecord,
  TaxExemptionCodeRecord,
  TaxExemptionCodeSearchResponse,
} from './types'

type JsonRecord = Record<string, unknown>

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null
}

async function taxComplianceRequest<T>(
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

export function searchTaxAuthorities(
  params: { state?: string; taxType?: string; activeOnly?: boolean } = {},
  signal?: AbortSignal,
): Promise<TaxAuthoritySearchResponse> {
  const search = new URLSearchParams()
  if (params.state?.trim()) search.set('state', params.state.trim())
  if (params.taxType?.trim()) search.set('tax_type', params.taxType.trim())
  if (params.activeOnly !== undefined) {
    search.set('active_only', String(params.activeOnly))
  }
  return taxComplianceRequest<TaxAuthoritySearchResponse>(
    `/tax-compliance/tax-authorities?${search.toString()}`,
    { signal },
  )
}

export function searchExemptionCodes(
  params: { stateCode?: number; taxType?: string; activeOnly?: boolean } = {},
  signal?: AbortSignal,
): Promise<TaxExemptionCodeSearchResponse> {
  const search = new URLSearchParams()
  if (params.stateCode != null) search.set('state_code', String(params.stateCode))
  if (params.taxType?.trim()) search.set('tax_type', params.taxType.trim())
  if (params.activeOnly !== undefined) {
    search.set('active_only', String(params.activeOnly))
  }
  return taxComplianceRequest<TaxExemptionCodeSearchResponse>(
    `/tax-compliance/exemption-codes?${search.toString()}`,
    { signal },
  )
}

export function getExemptionCode(
  exemptCode: string,
  signal?: AbortSignal,
): Promise<TaxExemptionCodeRecord[]> {
  const code = encodeURIComponent(exemptCode)
  return taxComplianceRequest<TaxExemptionCodeRecord[]>(
    `/tax-compliance/exemption-codes/${code}`,
    { signal },
  )
}

export function checkCustomerExemption(
  customerNumber: number | string,
  signal?: AbortSignal,
): Promise<CustomerExemptionCheckResponse> {
  const customer = encodeURIComponent(String(customerNumber))
  return taxComplianceRequest<CustomerExemptionCheckResponse>(
    `/tax-compliance/customers/${customer}/exemption-check`,
    { signal },
  )
}

export function checkCustomersExemptionBatch(
  customerNumbers: number[],
  signal?: AbortSignal,
): Promise<CustomerExemptionCheckBatchResponse> {
  return taxComplianceRequest<CustomerExemptionCheckBatchResponse>(
    `/tax-compliance/customers/exemption-check/batch`,
    { method: 'POST', body: { customer_numbers: customerNumbers }, signal },
  )
}

export function getCustomerNotes(
  customerNumber: number | string,
  signal?: AbortSignal,
): Promise<TaxComplianceNoteHistoryResponse> {
  const customer = encodeURIComponent(String(customerNumber))
  return taxComplianceRequest<TaxComplianceNoteHistoryResponse>(
    `/tax-compliance/customers/${customer}/notes`,
    { signal },
  )
}

export function createCustomerNote(
  customerNumber: number | string,
  payload: CreateTaxComplianceNoteRequest,
  signal?: AbortSignal,
): Promise<TaxComplianceNoteRecord> {
  const customer = encodeURIComponent(String(customerNumber))
  return taxComplianceRequest<TaxComplianceNoteRecord>(
    `/tax-compliance/customers/${customer}/notes`,
    { method: 'POST', body: payload, signal },
  )
}
