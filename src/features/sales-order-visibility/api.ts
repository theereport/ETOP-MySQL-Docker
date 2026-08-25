import { ApiError, requestJson } from '../../api/client'
import type {
  CreateOrderNoteRequest,
  InvoiceEvidenceResponse,
  InvoiceSearchResponse,
  OrderNoteHistoryResponse,
  OrderNoteRecord,
  SalesSummaryResponse,
} from './types'

type JsonRecord = Record<string, unknown>

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null
}

async function salesOrderVisibilityRequest<T>(
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

export function searchInvoices(
  search: string,
  options?: { customerNumber?: number | string; signal?: AbortSignal },
): Promise<InvoiceSearchResponse> {
  const params = new URLSearchParams()
  if (search.trim()) params.set('q', search.trim())
  if (options?.customerNumber != null && options.customerNumber !== '') {
    params.set('customer_number', String(options.customerNumber))
  }
  return salesOrderVisibilityRequest<InvoiceSearchResponse>(
    `/sales-order-visibility/invoices/search?${params.toString()}`,
    { signal: options?.signal },
  )
}

export function getInvoiceEvidence(
  invoiceNumber: number | string,
  signal?: AbortSignal,
): Promise<InvoiceEvidenceResponse> {
  const invoice = encodeURIComponent(String(invoiceNumber))
  return salesOrderVisibilityRequest<InvoiceEvidenceResponse>(
    `/sales-order-visibility/invoices/${invoice}`,
    { signal },
  )
}

export function getInvoiceNotes(
  invoiceNumber: number | string,
  signal?: AbortSignal,
): Promise<OrderNoteHistoryResponse> {
  const invoice = encodeURIComponent(String(invoiceNumber))
  return salesOrderVisibilityRequest<OrderNoteHistoryResponse>(
    `/sales-order-visibility/invoices/${invoice}/notes`,
    { signal },
  )
}

export function createInvoiceNote(
  invoiceNumber: number | string,
  payload: CreateOrderNoteRequest,
  signal?: AbortSignal,
): Promise<OrderNoteRecord> {
  const invoice = encodeURIComponent(String(invoiceNumber))
  return salesOrderVisibilityRequest<OrderNoteRecord>(
    `/sales-order-visibility/invoices/${invoice}/notes`,
    { method: 'POST', body: payload, signal },
  )
}

export function getSalesSummary(
  options?: {
    customerNumber?: number | string
    productNumber?: string
    signal?: AbortSignal
  },
): Promise<SalesSummaryResponse> {
  const params = new URLSearchParams()
  if (options?.customerNumber != null && options.customerNumber !== '') {
    params.set('customer_number', String(options.customerNumber))
  }
  if (options?.productNumber?.trim()) {
    params.set('product_number', options.productNumber.trim())
  }
  return salesOrderVisibilityRequest<SalesSummaryResponse>(
    `/sales-order-visibility/sales-summary?${params.toString()}`,
    { signal: options?.signal },
  )
}
