import type { APInvoiceQuery, APWorkspaceView } from './types'

export const AP_PAGE_SIZE = 50

export function filtersForAPView(
  view: APWorkspaceView,
  query: string,
  status: string,
  offset: number,
): APInvoiceQuery {
  return {
    query: query.trim() || undefined,
    status: view === 'invoices' ? status.trim() || undefined : view === 'ocr' ? 'ocr_review' : undefined,
    exception: view === 'exceptions' ? true : undefined,
    duplicate: view === 'duplicates' ? true : undefined,
    limit: AP_PAGE_SIZE,
    offset,
  }
}

export function buildAccountsPayableInvoiceQuery(filters: APInvoiceQuery): string {
  const parameters = new URLSearchParams()

  if (filters.query?.trim()) {
    parameters.set('query', filters.query.trim())
  }
  if (filters.status?.trim()) {
    parameters.set('status', filters.status.trim())
  }
  if (filters.exception !== undefined) {
    parameters.set('exception', String(filters.exception))
  }
  if (filters.duplicate !== undefined) {
    parameters.set('duplicate', String(filters.duplicate))
  }
  if (filters.limit !== undefined) {
    parameters.set('limit', String(filters.limit))
  }
  if (filters.offset !== undefined) {
    parameters.set('offset', String(filters.offset))
  }

  const query = parameters.toString()
  return query ? `?${query}` : ''
}
