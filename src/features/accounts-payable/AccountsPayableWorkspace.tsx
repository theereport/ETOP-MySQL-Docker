import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import type { FormEvent } from 'react'
import {
  getAccountsPayableInvoice,
  getAccountsPayableInvoices,
  getAccountsPayableOverview,
  syncAccountsPayableInvoices,
} from './api'
import {
  DeferredCapabilities,
  ExecutiveOverview,
  GovernanceBoundary,
  InvoiceDetail,
  InvoiceTable,
  Message,
  SourceCoverage,
} from './components'
import { errorMessage, formatDateTime, isAbortError } from './format'
import type {
  AccountsPayableWorkspaceProps,
  APInvoiceDetailResponse,
  APInvoiceListResponse,
  APInvoiceSummary,
  APOverviewResponse,
  APSyncResponse,
  APWorkspaceView,
} from './types'
import { AP_PAGE_SIZE, filtersForAPView } from './query'
import APControlCenter from './APControlCenter'
import APVendorCashIntelligence from './APVendorCashIntelligence'
import APExceptionOperationsCenter from './APExceptionOperationsCenter'
import APERPEvidenceWorkspace from './APERPEvidenceWorkspace'
import APVendorSpendIntelligence from './APVendorSpendIntelligence'
import APVendorInvoiceCapture from './APVendorInvoiceCapture'
import './AccountsPayableWorkspace.css'

type AsyncStatus = 'idle' | 'loading' | 'success' | 'error'

const workspaceViews: Array<{
  id: APWorkspaceView
  label: string
  description: string
}> = [
  { id: 'overview', label: 'Executive Dashboard', description: 'AP health and source readiness' },
  { id: 'vendor_invoice_capture', label: 'Vendor Invoice Dataset & OCR', description: 'Upload, extract, review, sync, and reopen vendor invoice evidence' },
  { id: 'invoices', label: 'Invoice Intelligence', description: 'Search imported invoice evidence' },
  { id: 'ocr', label: 'OCR Processing', description: 'Invoices flagged by the source for OCR review' },
  { id: 'exceptions', label: 'Exception Review', description: 'Imported invoices with recorded exceptions' },
  { id: 'exception_operations', label: 'Exception Operations', description: 'Deterministic queue and append-only follow-up' },
  { id: 'duplicates', label: 'Duplicate Detection', description: 'Invoices with duplicate candidate evidence' },
  { id: 'approvals', label: 'Approval Center', description: 'Evidence readiness and professional review dispositions' },
  { id: 'payment_controls', label: 'Payment Controls', description: 'Segregation and payment-preparation readiness' },
  { id: 'vendor_intelligence', label: 'Vendor Intelligence', description: 'Document-evidence volume, quality, and exception patterns' },
  { id: 'cash_planning', label: 'Cash Planning', description: 'Due-window evidence and immutable analytical scenarios' },
  { id: 'spend_intelligence', label: 'Vendor Spend Q&A', description: 'Ask governed questions over signed posted AP GL distributions' },
  { id: 'erp_evidence', label: 'ERP Evidence', description: 'Exact, bounded DTA273 vendor and invoice facts' },
]

function viewHeading(view: APWorkspaceView): { title: string; description: string } {
  const selected = workspaceViews.find((item) => item.id === view)
  return {
    title: selected?.label ?? 'Accounts Payable',
    description: selected?.description ?? '',
  }
}

export default function AccountsPayableWorkspace({
  initialQuery = '',
}: AccountsPayableWorkspaceProps) {
  const [view, setView] = useState<APWorkspaceView>('overview')
  const [queryDraft, setQueryDraft] = useState(initialQuery)
  const [appliedQuery, setAppliedQuery] = useState(initialQuery.trim())
  const [statusFilter, setStatusFilter] = useState('')
  const [offset, setOffset] = useState(0)
  const [overview, setOverview] = useState<APOverviewResponse | null>(null)
  const [overviewStatus, setOverviewStatus] = useState<AsyncStatus>('loading')
  const [overviewError, setOverviewError] = useState('')
  const [invoiceList, setInvoiceList] = useState<APInvoiceListResponse | null>(null)
  const [listStatus, setListStatus] = useState<AsyncStatus>('idle')
  const [listError, setListError] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [invoiceDetail, setInvoiceDetail] = useState<APInvoiceDetailResponse | null>(null)
  const [detailStatus, setDetailStatus] = useState<AsyncStatus>('idle')
  const [detailError, setDetailError] = useState('')
  const [syncStatus, setSyncStatus] = useState<AsyncStatus>('idle')
  const [syncResult, setSyncResult] = useState<APSyncResponse | null>(null)
  const [syncError, setSyncError] = useState('')
  const [controlRefreshKey, setControlRefreshKey] = useState(0)
  const overviewGeneration = useRef(0)
  const listGeneration = useRef(0)
  const detailGeneration = useRef(0)
  const overviewAbort = useRef<AbortController | null>(null)
  const listAbort = useRef<AbortController | null>(null)
  const detailAbort = useRef<AbortController | null>(null)
  const syncAbort = useRef<AbortController | null>(null)

  const heading = viewHeading(view)
  const isInvoiceListView = ['invoices', 'ocr', 'exceptions', 'duplicates'].includes(view)

  const displayedInvoices = useMemo(() => {
    const items = invoiceList?.items ?? []
    return view === 'ocr'
      ? items.filter((invoice) => invoice.ocr_review_required)
      : items
  }, [invoiceList, view])

  const loadOverview = useCallback(async () => {
    overviewAbort.current?.abort()
    const controller = new AbortController()
    const generation = overviewGeneration.current + 1
    overviewGeneration.current = generation
    overviewAbort.current = controller
    setOverviewStatus('loading')
    setOverviewError('')

    try {
      const response = await getAccountsPayableOverview(controller.signal)
      if (overviewGeneration.current !== generation) {
        return
      }
      setOverview(response)
      setOverviewStatus('success')
    } catch (error) {
      if (isAbortError(error) || overviewGeneration.current !== generation) {
        return
      }
      setOverviewStatus('error')
      setOverviewError(errorMessage(error, 'Unable to load Accounts Payable health.'))
    }
  }, [])

  const loadInvoices = useCallback(async (
    nextView: APWorkspaceView,
    nextQuery: string,
    nextStatus: string,
    nextOffset: number,
  ) => {
    if (!['invoices', 'ocr', 'exceptions', 'duplicates'].includes(nextView)) {
      return
    }
    listAbort.current?.abort()
    const controller = new AbortController()
    const generation = listGeneration.current + 1
    listGeneration.current = generation
    listAbort.current = controller
    setListStatus('loading')
    setListError('')

    try {
      const response = await getAccountsPayableInvoices(
        filtersForAPView(nextView, nextQuery, nextStatus, nextOffset),
        controller.signal,
      )
      if (listGeneration.current !== generation) {
        return
      }
      setInvoiceList(response)
      setListStatus('success')
    } catch (error) {
      if (isAbortError(error) || listGeneration.current !== generation) {
        return
      }
      setInvoiceList(null)
      setListStatus('error')
      setListError(errorMessage(error, 'Unable to load imported invoices.'))
    }
  }, [])

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadOverview()
    }, 0)
    return () => {
      window.clearTimeout(timeoutId)
      overviewAbort.current?.abort()
    }
  }, [loadOverview])

  useEffect(() => {
    if (!isInvoiceListView) {
      return
    }
    const timeoutId = window.setTimeout(() => {
      void loadInvoices(view, appliedQuery, statusFilter, offset)
    }, 0)
    return () => {
      window.clearTimeout(timeoutId)
      listAbort.current?.abort()
    }
  }, [appliedQuery, isInvoiceListView, loadInvoices, offset, statusFilter, view])

  useEffect(() => {
    if (!selectedId) {
      return
    }
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setSelectedId(null)
        setInvoiceDetail(null)
        detailAbort.current?.abort()
      }
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [selectedId])

  useEffect(() => () => {
    overviewAbort.current?.abort()
    listAbort.current?.abort()
    detailAbort.current?.abort()
    syncAbort.current?.abort()
  }, [])

  function changeView(nextView: APWorkspaceView) {
    if (nextView === view) {
      return
    }
    setView(nextView)
    setOffset(0)
    setStatusFilter('')
    setSelectedId(null)
    setInvoiceDetail(null)
    setDetailStatus('idle')
    setDetailError('')
    detailAbort.current?.abort()
  }

  function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const search = queryDraft.trim()
    setAppliedQuery(search)
    setOffset(0)
    if (view === 'overview') {
      setView('invoices')
    }
  }

  function clearSearch() {
    setQueryDraft('')
    setAppliedQuery('')
    setOffset(0)
  }

  const openInvoice = useCallback(async (invoice: APInvoiceSummary) => {
    detailAbort.current?.abort()
    const controller = new AbortController()
    const generation = detailGeneration.current + 1
    detailGeneration.current = generation
    detailAbort.current = controller
    setSelectedId(invoice.ap_invoice_id)
    setInvoiceDetail(null)
    setDetailStatus('loading')
    setDetailError('')

    try {
      const response = await getAccountsPayableInvoice(invoice.ap_invoice_id, controller.signal)
      if (detailGeneration.current !== generation) {
        return
      }
      setInvoiceDetail(response)
      setDetailStatus('success')
    } catch (error) {
      if (isAbortError(error) || detailGeneration.current !== generation) {
        return
      }
      setDetailStatus('error')
      setDetailError(errorMessage(error, 'Unable to load this invoice evidence.'))
    }
  }, [])

  function closeDetail() {
    detailAbort.current?.abort()
    detailGeneration.current += 1
    setSelectedId(null)
    setInvoiceDetail(null)
    setDetailStatus('idle')
    setDetailError('')
  }

  async function runSync() {
    if (syncStatus === 'loading') {
      return
    }
    syncAbort.current?.abort()
    const controller = new AbortController()
    syncAbort.current = controller
    setSyncStatus('loading')
    setSyncError('')
    setSyncResult(null)

    try {
      const result = await syncAccountsPayableInvoices(controller.signal)
      setSyncResult(result)
      setSyncStatus('success')
      if (selectedId) {
        closeDetail()
      }
      await Promise.all([
        loadOverview(),
        isInvoiceListView
          ? loadInvoices(view, appliedQuery, statusFilter, offset)
          : Promise.resolve(),
      ])
      if (!isInvoiceListView && view !== 'overview') {
        setControlRefreshKey((current) => current + 1)
      }
    } catch (error) {
      if (isAbortError(error)) {
        return
      }
      setSyncStatus('error')
      setSyncError(errorMessage(error, 'Unable to synchronize Accounts Payable invoices.'))
    }
  }

  function refreshCurrentView() {
    if (selectedId) {
      closeDetail()
    }
    if (view === 'overview') {
      void loadOverview()
    } else if (isInvoiceListView) {
      void loadInvoices(view, appliedQuery, statusFilter, offset)
    } else {
      setControlRefreshKey((current) => current + 1)
    }
  }

  function openImportedVendorInvoice(jobId: string) {
    setQueryDraft(jobId)
    setAppliedQuery(jobId)
    setStatusFilter('')
    setOffset(0)
    setSelectedId(null)
    setInvoiceDetail(null)
    setView('invoices')
  }

  const hasPreviousPage = offset > 0
  const hasNextPage = invoiceList ? offset + invoiceList.items.length < invoiceList.total : false

  return (
    <section className="ap-shell">
      <header className="ap-header">
        <div>
          <span className="ap-eyebrow">ACCOUNTS PAYABLE INTELLIGENCE · GOVERNED EVIDENCE</span>
          <h1>Accounts Payable</h1>
          <p>
            Turn imported invoices into source-grounded review evidence and durable control
            packets. Readiness dispositions never approve invoices or authorize payments.
          </p>
        </div>
        <div className="ap-header-actions">
          <button
            type="button"
            className="ap-secondary-button"
            onClick={refreshCurrentView}
            disabled={overviewStatus === 'loading' || listStatus === 'loading'}
          >
            {overviewStatus === 'loading' || listStatus === 'loading' ? 'Refreshing…' : 'Refresh'}
          </button>
          <button
            type="button"
            className="ap-primary-button"
            onClick={() => void runSync()}
            disabled={syncStatus === 'loading'}
          >
            {syncStatus === 'loading' ? 'Synchronizing…' : 'Sync imported invoices'}
          </button>
        </div>
      </header>

      <div className="ap-governance-strip">
        <span><i /> Local invoice intelligence</span>
        <span>ERP read only</span>
        <span>No approval or payment effect</span>
      </div>

      {syncResult && (
        <Message kind="success">
          <div>
            <strong>{syncResult.message || 'Invoice synchronization completed.'}</strong>
            <span>
              Eligible jobs {syncResult.eligible_job_count}; imported {syncResult.imported_count}; updated {syncResult.updated_count};
              unchanged {syncResult.unchanged_count}; skipped {syncResult.skipped_count}; duplicate candidates {syncResult.duplicate_candidate_count}
              {syncResult.completed_at ? ` · ${formatDateTime(syncResult.completed_at)}` : ''}
            </span>
          </div>
        </Message>
      )}
      {syncError && <Message kind="error">{syncError}</Message>}

      {(view === 'overview' || isInvoiceListView) && <form className="ap-search" onSubmit={submitSearch}>
        <label htmlFor="ap-enterprise-search">Search available invoice evidence</label>
        <div>
          <input
            id="ap-enterprise-search"
            type="search"
            value={queryDraft}
            onChange={(event) => setQueryDraft(event.target.value)}
            placeholder="Invoice, vendor, PO, document job ID, or filename"
            disabled={listStatus === 'loading'}
          />
          {queryDraft && (
            <button type="button" className="ap-clear-button" onClick={clearSearch}>Clear</button>
          )}
          <button type="submit" className="ap-primary-button" disabled={listStatus === 'loading'}>
            {listStatus === 'loading' ? 'Searching…' : 'Search invoices'}
          </button>
        </div>
        <small>
          Searches imported invoice/vendor identifiers, PO number, source job ID, and filename. Amount/date and document full-text search are deferred.
        </small>
      </form>}

      <nav className="ap-view-navigation" aria-label="Accounts Payable workspace views">
        {workspaceViews.map((item) => (
          <button
            type="button"
            key={item.id}
            className={view === item.id ? 'is-active' : ''}
            onClick={() => changeView(item.id)}
            aria-current={view === item.id ? 'page' : undefined}
          >
            <strong>{item.label}</strong>
            <small>{item.description}</small>
          </button>
        ))}
      </nav>

      <main className="ap-workspace">
        <div className="ap-workspace-heading">
          <div>
            <span className="ap-kicker">Current workspace</span>
            <h2>{heading.title}</h2>
            <p>{heading.description}</p>
          </div>
          {isInvoiceListView && invoiceList && (
            <div className="ap-result-count">
              <strong>{invoiceList.total}</strong>
              <span>matching invoice{invoiceList.total === 1 ? '' : 's'}</span>
            </div>
          )}
        </div>

        {view === 'overview' && overviewStatus === 'loading' && (
          <div className="ap-loading" role="status"><span className="ap-spinner" /><div><strong>Loading AP health</strong><p>Reading current imported invoice evidence and source coverage…</p></div></div>
        )}
        {view === 'overview' && overviewStatus === 'error' && (
          <Message kind="error">
            <span>{overviewError}</span>
            <button type="button" onClick={() => void loadOverview()}>Retry dashboard</button>
          </Message>
        )}
        {view === 'overview' && overview && overviewStatus === 'success' && (
          <ExecutiveOverview overview={overview} />
        )}

        {view === 'vendor_invoice_capture' && (
          <APVendorInvoiceCapture
            onOpenImportedEvidence={openImportedVendorInvoice}
            onProjectionChanged={async () => {
              await loadOverview()
              setControlRefreshKey((current) => current + 1)
            }}
          />
        )}

        {isInvoiceListView && (
          <section className="ap-list-panel">
            <div className="ap-list-toolbar">
              <div>
                <strong>{heading.title}</strong>
                <span>
                  {appliedQuery ? `Search: “${appliedQuery}”` : 'All available imported invoice evidence'}
                </span>
              </div>
              {view === 'invoices' && (
                <label>
                  <span>Status</span>
                  <select
                    value={statusFilter}
                    onChange={(event) => {
                      setStatusFilter(event.target.value)
                      setOffset(0)
                    }}
                    disabled={listStatus === 'loading'}
                  >
                    <option value="">All statuses</option>
                    {(invoiceList?.filter_options.statuses ?? []).map((status) => (
                      <option value={status} key={status}>{status.replaceAll('_', ' ')}</option>
                    ))}
                  </select>
                </label>
              )}
            </div>

            {listStatus === 'loading' && (
              <div className="ap-loading ap-loading--compact" role="status"><span className="ap-spinner" /><div><strong>Loading invoices</strong><p>Applying server-side search and review filters…</p></div></div>
            )}
            {listStatus === 'error' && (
              <Message kind="error">
                <span>{listError}</span>
                <button type="button" onClick={() => void loadInvoices(view, appliedQuery, statusFilter, offset)}>Retry invoice list</button>
              </Message>
            )}
            {listStatus === 'success' && displayedInvoices.length === 0 && (
              <div className="ap-empty-state">
                <strong>No invoices matched this view.</strong>
                <p>
                  ETOP did not create placeholder results. Adjust the search or choose another evidence view.
                </p>
              </div>
            )}
            {listStatus === 'success' && displayedInvoices.length > 0 && (
              <>
                <InvoiceTable
                  invoices={displayedInvoices}
                  busy={detailStatus === 'loading'}
                  selectedId={selectedId}
                  onOpen={(invoice) => void openInvoice(invoice)}
                />
                <div className="ap-pagination">
                  <button
                    type="button"
                    onClick={() => setOffset((current) => Math.max(0, current - AP_PAGE_SIZE))}
                    disabled={!hasPreviousPage}
                  >
                    Previous
                  </button>
                  <span>
                    {invoiceList && invoiceList.total > 0
                      ? `${offset + 1}–${Math.min(offset + invoiceList.items.length, invoiceList.total)} of ${invoiceList.total}`
                      : '0 results'}
                  </span>
                  <button
                    type="button"
                    onClick={() => setOffset((current) => current + AP_PAGE_SIZE)}
                    disabled={!hasNextPage}
                  >
                    Next
                  </button>
                </div>
              </>
            )}

            {invoiceList && listStatus === 'success' && (
              <div className="ap-list-evidence">
                {invoiceList.warnings.length > 0 && (
                  <Message kind="notice"><ul>{invoiceList.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></Message>
                )}
                <div className="ap-two-column">
                  <SourceCoverage items={invoiceList.source_coverage} />
                  <GovernanceBoundary governance={invoiceList.governance} />
                </div>
                <DeferredCapabilities capabilities={invoiceList.deferred_capabilities} />
              </div>
            )}
          </section>
        )}

        {view === 'approvals' && (
          <APControlCenter key={`approval-${controlRefreshKey}`} mode="approval_review" />
        )}
        {view === 'payment_controls' && (
          <APControlCenter key={`payment-${controlRefreshKey}`} mode="payment_preparation" />
        )}
        {view === 'exception_operations' && (
          <APExceptionOperationsCenter refreshKey={controlRefreshKey} />
        )}
        {view === 'vendor_intelligence' && (
          <APVendorCashIntelligence mode="vendor" refreshKey={controlRefreshKey} />
        )}
        {view === 'cash_planning' && (
          <APVendorCashIntelligence mode="cash" refreshKey={controlRefreshKey} />
        )}
        {view === 'spend_intelligence' && (
          <APVendorSpendIntelligence refreshKey={controlRefreshKey} />
        )}
        {view === 'erp_evidence' && (
          <APERPEvidenceWorkspace refreshKey={controlRefreshKey} />
        )}
      </main>

      {selectedId && (
        <div className="ap-detail-layer">
          <button type="button" className="ap-detail-backdrop" onClick={closeDetail} aria-label="Close invoice detail" />
          <InvoiceDetail
            invoice={invoiceDetail}
            busy={detailStatus === 'loading'}
            error={detailError}
            onClose={closeDetail}
            onRetry={() => {
              const summary = invoiceList?.items.find((item) => item.ap_invoice_id === selectedId)
              if (summary) {
                void openInvoice(summary)
              }
            }}
          />
        </div>
      )}
    </section>
  )
}
