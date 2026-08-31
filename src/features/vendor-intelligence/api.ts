import { ApiError, requestJson } from '../../api/client'
import type {
  CreateVendorNoteRequest,
  GLDistributionLine,
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

export function getVendorGLDistributionsBatch(
  vendorNumber: number | string,
  invoiceNumbers: string[],
  signal?: AbortSignal,
): Promise<Record<string, GLDistributionLine[]>> {
  // Lean batched sibling of getVendorInvoiceGLDistributions - one query
  // for a whole vendor's open-payables list instead of one full
  // invoice-evidence assembly (vendor master, PO match, input headers,
  // etc.) per invoice, which was confirmed live to take 10+ seconds
  // across ~9 concurrent invoices for a single vendor.
  const params = new URLSearchParams({
    vendor_number: String(vendorNumber),
    invoice_numbers: invoiceNumbers.join(','),
  })
  return vendorIntelligenceRequest<{ items: Record<string, GLDistributionLine[]> }>(
    `/erp-evidence/accounts-payable/gl-distributions?${params.toString()}`,
    { signal },
  ).then((response) => response.items)
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
