import { ApiError, requestJson } from '../../api/client'
import type {
  CreateRouteNoteRequest,
  RouteEvidenceResponse,
  RouteNoteHistoryResponse,
  RouteNoteRecord,
  RouteSearchResponse,
} from './types'

type JsonRecord = Record<string, unknown>

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null
}

async function freightLogisticsRequest<T>(
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

export function searchRoutes(
  search: string,
  signal?: AbortSignal,
): Promise<RouteSearchResponse> {
  const params = new URLSearchParams()
  if (search.trim()) params.set('q', search.trim())
  return freightLogisticsRequest<RouteSearchResponse>(
    `/freight-logistics/routes/search?${params.toString()}`,
    { signal },
  )
}

export function getRouteEvidence(
  routeCode: string,
  signal?: AbortSignal,
): Promise<RouteEvidenceResponse> {
  const route = encodeURIComponent(routeCode)
  return freightLogisticsRequest<RouteEvidenceResponse>(
    `/freight-logistics/routes/${route}`,
    { signal },
  )
}

export function getRouteNotes(
  routeCode: string,
  signal?: AbortSignal,
): Promise<RouteNoteHistoryResponse> {
  const route = encodeURIComponent(routeCode)
  return freightLogisticsRequest<RouteNoteHistoryResponse>(
    `/freight-logistics/routes/${route}/notes`,
    { signal },
  )
}

export function createRouteNote(
  routeCode: string,
  payload: CreateRouteNoteRequest,
  signal?: AbortSignal,
): Promise<RouteNoteRecord> {
  const route = encodeURIComponent(routeCode)
  return freightLogisticsRequest<RouteNoteRecord>(
    `/freight-logistics/routes/${route}/notes`,
    { method: 'POST', body: payload, signal },
  )
}
