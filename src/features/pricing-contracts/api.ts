import { ApiError, requestJson } from '../../api/client'
import type {
  CreatePricingNoteRequest,
  CustomerClassResponse,
  DiscountEvidenceResponse,
  DiscountSearchFilters,
  DiscountSearchResponse,
  PricingNoteHistoryResponse,
  PricingNoteRecord,
} from './types'

type JsonRecord = Record<string, unknown>

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null
}

async function pricingContractsRequest<T>(
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

export function searchDiscounts(
  filters: DiscountSearchFilters,
  signal?: AbortSignal,
): Promise<DiscountSearchResponse> {
  const params = new URLSearchParams()
  if (filters.customerNumber != null) {
    params.set('customer_number', String(filters.customerNumber))
  }
  if (filters.productNumber?.trim()) {
    params.set('product_number', filters.productNumber.trim())
  }
  if (filters.productClass?.trim()) {
    params.set('product_class', filters.productClass.trim())
  }
  if (filters.vendorCode?.trim()) {
    params.set('vendor_code', filters.vendorCode.trim())
  }
  if (filters.activeOnly) {
    params.set('active_only', 'true')
  }
  return pricingContractsRequest<DiscountSearchResponse>(
    `/pricing-contracts/discounts/search?${params.toString()}`,
    { signal },
  )
}

export function getDiscount(
  key: {
    customerNumber: number
    vendorCode: string
    productClass: string
    productNumber: string
    productType: string
  },
  signal?: AbortSignal,
): Promise<DiscountEvidenceResponse> {
  const params = new URLSearchParams({
    customer_number: String(key.customerNumber),
    vendor_code: key.vendorCode,
    product_class: key.productClass,
    product_number: key.productNumber,
    product_type: key.productType,
  })
  return pricingContractsRequest<DiscountEvidenceResponse>(
    `/pricing-contracts/discounts/lookup?${params.toString()}`,
    { signal },
  )
}

export function searchCustomerClasses(
  search: string,
  signal?: AbortSignal,
): Promise<CustomerClassResponse> {
  const params = new URLSearchParams()
  if (search.trim()) params.set('q', search.trim())
  return pricingContractsRequest<CustomerClassResponse>(
    `/pricing-contracts/customer-classes/search?${params.toString()}`,
    { signal },
  )
}

export function getPricingNotes(
  customerNumber: number,
  scope: { vendorCode?: string; productClass?: string; productNumber?: string; productType?: string } = {},
  signal?: AbortSignal,
): Promise<PricingNoteHistoryResponse> {
  const params = new URLSearchParams({ customer_number: String(customerNumber) })
  if (scope.vendorCode) params.set('vendor_code', scope.vendorCode)
  if (scope.productClass) params.set('product_class', scope.productClass)
  if (scope.productNumber) params.set('product_number', scope.productNumber)
  if (scope.productType) params.set('product_type', scope.productType)
  return pricingContractsRequest<PricingNoteHistoryResponse>(
    `/pricing-contracts/notes?${params.toString()}`,
    { signal },
  )
}

export function createPricingNote(
  payload: CreatePricingNoteRequest,
  signal?: AbortSignal,
): Promise<PricingNoteRecord> {
  return pricingContractsRequest<PricingNoteRecord>(
    '/pricing-contracts/notes',
    { method: 'POST', body: payload, signal },
  )
}
