import { ApiError, requestJson } from '../../api/client'
import type {
  CreateInventoryNoteRequest,
  InventoryNoteHistoryResponse,
  InventoryNoteRecord,
  ProductEvidenceResponse,
  ProductSearchResponse,
} from './types'

type JsonRecord = Record<string, unknown>

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null
}

async function inventoryPurchasingRequest<T>(
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

export function searchProducts(
  search: string,
  signal?: AbortSignal,
): Promise<ProductSearchResponse> {
  const params = new URLSearchParams()
  if (search.trim()) params.set('q', search.trim())
  return inventoryPurchasingRequest<ProductSearchResponse>(
    `/inventory-purchasing/products/search?${params.toString()}`,
    { signal },
  )
}

export function getProductEvidence(
  productNumber: string,
  signal?: AbortSignal,
): Promise<ProductEvidenceResponse> {
  const product = encodeURIComponent(productNumber)
  return inventoryPurchasingRequest<ProductEvidenceResponse>(
    `/inventory-purchasing/products/${product}`,
    { signal },
  )
}

export function getProductNotes(
  productNumber: string,
  signal?: AbortSignal,
): Promise<InventoryNoteHistoryResponse> {
  const product = encodeURIComponent(productNumber)
  return inventoryPurchasingRequest<InventoryNoteHistoryResponse>(
    `/inventory-purchasing/products/${product}/notes`,
    { signal },
  )
}

export function createProductNote(
  productNumber: string,
  payload: CreateInventoryNoteRequest,
  signal?: AbortSignal,
): Promise<InventoryNoteRecord> {
  const product = encodeURIComponent(productNumber)
  return inventoryPurchasingRequest<InventoryNoteRecord>(
    `/inventory-purchasing/products/${product}/notes`,
    { method: 'POST', body: payload, signal },
  )
}
