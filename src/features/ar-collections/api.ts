import { ApiError, requestJson } from '../../api/client'
import type {
  ARCollectionsNoteHistoryResponse,
  ARCollectionsNoteRecord,
  CreateARCollectionsNoteRequest,
  CustomerARCollectionsResponse,
} from './types'

type JsonRecord = Record<string, unknown>

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null
}

async function arCollectionsRequest<T>(
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

export function getCustomerCollections(
  customerNumber: number | string,
  signal?: AbortSignal,
): Promise<CustomerARCollectionsResponse> {
  const customer = encodeURIComponent(String(customerNumber))
  return arCollectionsRequest<CustomerARCollectionsResponse>(
    `/ar-collections/customers/${customer}`,
    { signal },
  )
}

export function getCustomerNotes(
  customerNumber: number | string,
  signal?: AbortSignal,
): Promise<ARCollectionsNoteHistoryResponse> {
  const customer = encodeURIComponent(String(customerNumber))
  return arCollectionsRequest<ARCollectionsNoteHistoryResponse>(
    `/ar-collections/customers/${customer}/notes`,
    { signal },
  )
}

export function createCustomerNote(
  customerNumber: number | string,
  payload: CreateARCollectionsNoteRequest,
  signal?: AbortSignal,
): Promise<ARCollectionsNoteRecord> {
  const customer = encodeURIComponent(String(customerNumber))
  return arCollectionsRequest<ARCollectionsNoteRecord>(
    `/ar-collections/customers/${customer}/notes`,
    { method: 'POST', body: payload, signal },
  )
}
