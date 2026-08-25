import { findPlatformModules } from './registry'
import type { SearchResult } from './types'

const API_BASE =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ??
  'http://127.0.0.1:8000/api/v1'

const SOURCE_TIMEOUT_MS = 2200
const MAX_RESULTS = 50

type JsonRecord = Record<string, unknown>

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === 'object' && value !== null
}

function readString(
  record: JsonRecord,
  key: string,
): string {
  const value = record[key]

  if (typeof value === 'string') {
    return value
  }

  if (typeof value === 'number') {
    return String(value)
  }

  return ''
}

function readNumber(
  record: JsonRecord,
  key: string,
): number | null {
  const value = record[key]

  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }

  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }

  return null
}

function readArray(
  payload: unknown,
  key: string,
): unknown[] {
  if (!isRecord(payload)) {
    return []
  }

  const value = payload[key]
  return Array.isArray(value) ? value : []
}

function matchesQuery(
  query: string,
  values: Array<string | number | null>,
): boolean {
  const haystack = values
    .filter((value) => value !== null)
    .join(' ')
    .toLowerCase()

  return query
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((token) => {
      if (haystack.includes(token)) {
        return true
      }

      if (token.endsWith('ies') && token.length > 4) {
        return haystack.includes(`${token.slice(0, -3)}y`)
      }

      if (token.endsWith('s') && token.length > 3) {
        return haystack.includes(token.slice(0, -1))
      }

      return false
    })
}

function resultScore(
  query: string,
  title: string,
  searchable: string,
  base: number,
): number {
  const normalized = query.toLowerCase()
  const normalizedTitle = title.toLowerCase()

  if (normalizedTitle === normalized) {
    return Math.min(base + 0.08, 1)
  }

  if (normalizedTitle.startsWith(normalized)) {
    return Math.min(base + 0.05, 1)
  }

  if (searchable.toLowerCase().includes(normalized)) {
    return Math.min(base + 0.02, 1)
  }

  return base
}

function localSearch(query: string): SearchResult[] {
  return findPlatformModules(query).map((module, index) => ({
    id: `module-${module.id}`,
    type: 'Module',
    title: module.shortTitle,
    subtitle: module.description,
    module: module.title,
    score: Math.max(0.72, 0.92 - index * 0.01),
    action: module.title,
    metadata: {
      source: 'ETOP module registry',
      version: module.version,
      status: module.status,
    },
  }))
}

async function fetchJson(
  url: string,
  signal?: AbortSignal,
): Promise<unknown | null> {
  const controller = new AbortController()
  const abort = () => controller.abort()

  if (signal?.aborted) {
    controller.abort()
  } else {
    signal?.addEventListener('abort', abort, { once: true })
  }

  const timeoutId = window.setTimeout(
    abort,
    SOURCE_TIMEOUT_MS,
  )

  try {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
      },
    })

    if (!response.ok) {
      return null
    }

    return await response.json()
  } catch {
    return null
  } finally {
    window.clearTimeout(timeoutId)
    signal?.removeEventListener('abort', abort)
  }
}

async function searchPlatformApi(
  query: string,
  signal?: AbortSignal,
): Promise<SearchResult[]> {
  const payload = await fetchJson(
    `${API_BASE}/platform/search?q=${encodeURIComponent(query)}`,
    signal,
  )

  if (!isRecord(payload)) {
    return []
  }

  const data = isRecord(payload.data) ? payload.data : payload

  return readArray(data, 'results')
    .filter(isRecord)
    .map((item): SearchResult | null => {
      const id = readString(item, 'id')
      const title = readString(item, 'title')
      const moduleName = readString(item, 'module')

      if (!id || !title || !moduleName) {
        return null
      }

      const score = readNumber(item, 'score')

      return {
        id,
        type: readString(item, 'type') || 'Enterprise',
        title,
        subtitle: readString(item, 'subtitle'),
        module: moduleName,
        score: score ?? 0.75,
        action: readString(item, 'action') || moduleName,
        metadata: {
          source: 'ETOP platform API',
        },
      } satisfies SearchResult
    })
    .filter(
      (result): result is SearchResult =>
        result !== null,
    )
}

async function searchCustomers(
  query: string,
  signal?: AbortSignal,
): Promise<SearchResult[]> {
  const params = new URLSearchParams({
    search: query,
    limit: '20',
    active_only: 'true',
  })
  const payload = await fetchJson(
    `${API_BASE}/customers?${params.toString()}`,
    signal,
  )

  return readArray(payload, 'customers')
    .filter(isRecord)
    .map((customer): SearchResult | null => {
      const number = readString(customer, 'customer_number')
      const name =
        readString(customer, 'customer_name') ||
        readString(customer, 'dba_name')

      if (!number || !name) {
        return null
      }

      const route = readString(customer, 'route_code')
      const store = readString(customer, 'store_number')
      const phone = readString(customer, 'phone')
      const email = readString(customer, 'email')
      const utilization = readNumber(
        customer,
        'utilization_percent',
      )
      const searchable = [
        number,
        name,
        readString(customer, 'dba_name'),
        route,
        store,
        phone,
        email,
      ].join(' ')
      const details = [
        `Customer #${number}`,
        route ? `Route ${route}` : '',
        store ? `Store ${store}` : '',
        utilization !== null
          ? `${utilization.toFixed(1)}% credit utilization`
          : '',
      ].filter(Boolean)

      return {
        id: `customer-${number}`,
        type: 'Customer',
        title: name,
        subtitle: details.join(' · '),
        module: 'Customer 360',
        score: resultScore(
          query,
          `${name} ${number}`,
          searchable,
          0.88,
        ),
        action: 'Customer 360',
        metadata: {
          source: 'Customer 360',
          customerNumber: number,
          route: route || null,
          store: store || null,
        },
      } satisfies SearchResult
    })
    .filter(
      (result): result is SearchResult =>
        result !== null,
    )
}

async function searchReports(
  query: string,
  signal?: AbortSignal,
): Promise<SearchResult[]> {
  const payload = await fetchJson(
    `${API_BASE}/reports`,
    signal,
  )

  return readArray(payload, 'items')
    .filter(isRecord)
    .filter((report) =>
      matchesQuery(query, [
        readString(report, 'name'),
        readString(report, 'description'),
        readString(report, 'category'),
        readString(report, 'database'),
        readString(report, 'outputFormat'),
      ]),
    )
    .map((report): SearchResult | null => {
      const id = readString(report, 'id')
      const name = readString(report, 'name')

      if (!id || !name) {
        return null
      }

      const category =
        readString(report, 'category') || 'General'
      const description = readString(report, 'description')

      return {
        id: `report-${id}`,
        type: 'Report',
        title: name,
        subtitle: [category, description]
          .filter(Boolean)
          .join(' · '),
        module: 'Report Builder',
        score: resultScore(
          query,
          name,
          `${name} ${category} ${description}`,
          0.82,
        ),
        action: 'Report Builder',
        metadata: {
          source: 'Report catalog',
          reportId: id,
          category,
        },
      } satisfies SearchResult
    })
    .filter(
      (result): result is SearchResult =>
        result !== null,
    )
}

async function searchDocuments(
  query: string,
  signal?: AbortSignal,
): Promise<SearchResult[]> {
  const payload = await fetchJson(
    `${API_BASE}/documents/jobs?limit=100`,
    signal,
  )

  return readArray(payload, 'jobs')
    .filter(isRecord)
    .filter((job) =>
      matchesQuery(query, [
        readString(job, 'job_id'),
        readString(job, 'original_file_name'),
        readString(job, 'document_type'),
        readString(job, 'status'),
        readString(job, 'message'),
      ]),
    )
    .map((job): SearchResult | null => {
      const id = readString(job, 'job_id')
      const fileName = readString(
        job,
        'original_file_name',
      )

      if (!id || !fileName) {
        return null
      }

      const documentType =
        readString(job, 'document_type') || 'unknown'
      const status = readString(job, 'status') || 'unknown'

      return {
        id: `document-${id}`,
        type: 'Document',
        title: fileName,
        subtitle: `${documentType.replaceAll('_', ' ')} · ${status}`,
        module: 'Document Intelligence',
        score: resultScore(
          query,
          fileName,
          `${fileName} ${documentType} ${status}`,
          0.8,
        ),
        action: 'Document Intelligence',
        metadata: {
          source: 'Document Intelligence',
          jobId: id,
          documentType,
          status,
        },
      } satisfies SearchResult
    })
    .filter(
      (result): result is SearchResult =>
        result !== null,
    )
}

function mergeResults(
  resultGroups: SearchResult[][],
): SearchResult[] {
  const unique = new Map<string, SearchResult>()

  for (const result of resultGroups.flat()) {
    const existing = unique.get(result.id)

    if (
      !existing ||
      (result.score ?? 0) > (existing.score ?? 0)
    ) {
      unique.set(result.id, result)
    }
  }

  return [...unique.values()]
    .sort(
      (left, right) =>
        (right.score ?? 0) - (left.score ?? 0) ||
        left.title.localeCompare(right.title),
    )
    .slice(0, MAX_RESULTS)
}

export async function searchEnterprise(
  query: string,
  signal?: AbortSignal,
): Promise<SearchResult[]> {
  const normalized = query.trim()

  if (!normalized) {
    return []
  }

  const localResults = localSearch(normalized)
  const remoteGroups = await Promise.all([
    searchPlatformApi(normalized, signal),
    searchCustomers(normalized, signal),
    searchReports(normalized, signal),
    searchDocuments(normalized, signal),
  ])

  return mergeResults([
    localResults,
    ...remoteGroups,
  ])
}
