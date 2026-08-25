import { ApiError, requestJson } from '../../api/client'
import type {
  CreateVendorNoteRequest,
  VendorEvidenceResponse,
  VendorNoteHistoryResponse,
  VendorNoteRecord,
  VendorSearchResponse,
} from './types'

type JsonRecord = Record<string, unknown>

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null
}

async function vendorIntelligenceRequest<T>(
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

export function searchVendors(
  search: string,
  signal?: AbortSignal,
): Promise<VendorSearchResponse> {
  const params = new URLSearchParams()
  if (search.trim()) params.set('q', search.trim())
  return vendorIntelligenceRequest<VendorSearchResponse>(
    `/vendor-intelligence/vendors/search?${params.toString()}`,
    { signal },
  )
}

export function getVendorEvidence(
  vendorNumber: number | string,
  signal?: AbortSignal,
): Promise<VendorEvidenceResponse> {
  const vendor = encodeURIComponent(String(vendorNumber))
  return vendorIntelligenceRequest<VendorEvidenceResponse>(
    `/vendor-intelligence/vendors/${vendor}`,
    { signal },
  )
}

export function getVendorNotes(
  vendorNumber: number | string,
  signal?: AbortSignal,
): Promise<VendorNoteHistoryResponse> {
  const vendor = encodeURIComponent(String(vendorNumber))
  return vendorIntelligenceRequest<VendorNoteHistoryResponse>(
    `/vendor-intelligence/vendors/${vendor}/notes`,
    { signal },
  )
}

export function createVendorNote(
  vendorNumber: number | string,
  payload: CreateVendorNoteRequest,
  signal?: AbortSignal,
): Promise<VendorNoteRecord> {
  const vendor = encodeURIComponent(String(vendorNumber))
  return vendorIntelligenceRequest<VendorNoteRecord>(
    `/vendor-intelligence/vendors/${vendor}/notes`,
    { method: 'POST', body: payload, signal },
  )
}
