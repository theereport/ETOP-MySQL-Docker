import { ApiError, requestJson } from '../../api/client'
import type {
  ApCacheRefreshResult,
  CashFlowAccuracyHistoryResponse,
  CashFlowForecastResponse,
  CashFlowSnapshotHistoryResponse,
  RecordClosedWeeksResult,
} from './types'

type JsonRecord = Record<string, unknown>

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null
}

async function cashFlowRequest<T>(
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

export function getCurrentForecast(
  asOf?: string,
  signal?: AbortSignal,
): Promise<CashFlowForecastResponse> {
  const params = new URLSearchParams()
  if (asOf) params.set('as_of', asOf)
  const query = params.toString()
  return cashFlowRequest<CashFlowForecastResponse>(
    `/cash-flow-forecasting/current${query ? `?${query}` : ''}`,
    { signal },
  )
}

export function createSnapshot(asOf?: string): Promise<{ snapshot_id: string }> {
  const params = new URLSearchParams()
  if (asOf) params.set('as_of', asOf)
  const query = params.toString()
  return cashFlowRequest<{ snapshot_id: string }>(
    `/cash-flow-forecasting/snapshots${query ? `?${query}` : ''}`,
    { method: 'POST' },
  )
}

export function listSnapshots(signal?: AbortSignal): Promise<CashFlowSnapshotHistoryResponse> {
  return cashFlowRequest<CashFlowSnapshotHistoryResponse>('/cash-flow-forecasting/snapshots', {
    signal,
  })
}

export function refreshApCache(): Promise<ApCacheRefreshResult> {
  return cashFlowRequest<ApCacheRefreshResult>('/cash-flow-forecasting/ap-cache/refresh', {
    method: 'POST',
  })
}

export function recordClosedWeeks(asOf?: string): Promise<RecordClosedWeeksResult> {
  const params = new URLSearchParams()
  if (asOf) params.set('as_of', asOf)
  const query = params.toString()
  return cashFlowRequest<RecordClosedWeeksResult>(
    `/cash-flow-forecasting/accuracy/record-closed-weeks${query ? `?${query}` : ''}`,
    { method: 'POST' },
  )
}

export function getAccuracyHistory(
  signal?: AbortSignal,
): Promise<CashFlowAccuracyHistoryResponse> {
  return cashFlowRequest<CashFlowAccuracyHistoryResponse>(
    '/cash-flow-forecasting/accuracy-history',
    { signal },
  )
}
