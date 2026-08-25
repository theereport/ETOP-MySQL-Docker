import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import type { FormEvent } from 'react'
import { SummaryCard } from '../../components/enterprise'
import {
  WORKFLOW_SESSION_EVENT,
  getWorkflowToken,
} from '../workflow-foundation'
import {
  activateRouteReference,
  createItemReview,
  createPaymentNotesRun,
  getPaymentNotesRun,
  getRouteReferenceStatus,
  listPaymentNotesRuns,
  listRouteReferences,
  paymentNotesIdempotencyKey,
  uploadRouteReference,
} from './api'
import {
  DepositList,
  EmptyState,
  ERPProvenancePanel,
  ItemDetail,
  ItemQueue,
  Message,
  RouteReferencePanel,
  RunHistory,
  StatusPill,
} from './components'
import type { QueueView } from './components'
import {
  errorMessage,
  formatCents,
  formatCount,
  isAbortError,
  shortHash,
  calendarWindowSuggestion,
} from './format'
import type {
  AsyncStatus,
  PaymentNotesRunDetail,
  PaymentNotesRunSummary,
  RouteReferenceStatus,
  RouteReferenceSummary,
} from './types'
import './PaymentNotesWorkspace.css'

type WindowStartingPoint = 'same_day' | 'prior_calendar_day'

export default function PaymentNotesWorkspace() {
  const initialWindow = useMemo(() => calendarWindowSuggestion('prior_calendar_day'), [])
  const [signedIn, setSignedIn] = useState(() => Boolean(getWorkflowToken()))
  const [rootStatus, setRootStatus] = useState<AsyncStatus>('loading')
  const [actionStatus, setActionStatus] = useState<AsyncStatus>('idle')
  const [routeActionStatus, setRouteActionStatus] = useState<AsyncStatus>('idle')
  const [error, setError] = useState('')
  const [actionMessage, setActionMessage] = useState('')
  const [routeStatus, setRouteStatus] = useState<RouteReferenceStatus | null>(null)
  const [routeReferences, setRouteReferences] = useState<RouteReferenceSummary[]>([])
  const [runs, setRuns] = useState<PaymentNotesRunSummary[]>([])
  const [selectedRun, setSelectedRun] = useState<PaymentNotesRunDetail | null>(null)
  const [selectedDepositKey, setSelectedDepositKey] = useState<string | null>(null)
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null)
  const [queue, setQueue] = useState<QueueView>('all')
  const [bankFile, setBankFile] = useState<File | null>(null)
  const [windowStartingPoint, setWindowStartingPoint] = useState<WindowStartingPoint>('prior_calendar_day')
  const [dateFrom, setDateFrom] = useState(initialWindow.dateFrom)
  const [dateTo, setDateTo] = useState(initialWindow.dateTo)
  const rootAbort = useRef<AbortController | null>(null)
  const detailAbort = useRef<AbortController | null>(null)
  const actionAbort = useRef<AbortController | null>(null)
  const rootGeneration = useRef(0)
  const detailGeneration = useRef(0)

  const selectedItem = useMemo(
    () => selectedRun?.items.find((item) => item.bank_item_id === selectedItemId) ?? null,
    [selectedItemId, selectedRun],
  )

  const visibleItems = useMemo(() => {
    const items = selectedRun?.items ?? []
    return selectedDepositKey
      ? items.filter((item) => item.deposit_key === selectedDepositKey)
      : items
  }, [selectedDepositKey, selectedRun])

  const selectedDeposit = useMemo(
    () => selectedRun?.deposits.find((deposit) => deposit.deposit_key === selectedDepositKey) ?? null,
    [selectedDepositKey, selectedRun],
  )

  const loadRoot = useCallback(async () => {
    rootAbort.current?.abort()
    const controller = new AbortController()
    rootAbort.current = controller
    const generation = rootGeneration.current + 1
    rootGeneration.current = generation
    const hasToken = Boolean(getWorkflowToken())
    setSignedIn(hasToken)
    setError('')

    if (!hasToken) {
      setRouteStatus(null)
      setRouteReferences([])
      setRuns([])
      setSelectedRun(null)
      setRootStatus('ready')
      return
    }

    setRootStatus('loading')
    try {
      const [nextRouteStatus, nextReferences, nextRuns] = await Promise.all([
        getRouteReferenceStatus(controller.signal),
        listRouteReferences(controller.signal),
        listPaymentNotesRuns({ limit: 50, offset: 0 }, controller.signal),
      ])
      if (controller.signal.aborted || rootGeneration.current !== generation) return
      setRouteStatus(nextRouteStatus)
      setRouteReferences(nextReferences.items)
      setRuns(nextRuns.items)
      setSelectedRun((current) => {
        if (!current) return current
        const summary = nextRuns.items.find((run) => run.run_id === current.run.run_id)
        return summary ? { ...current, run: summary } : null
      })
      setRootStatus('ready')
    } catch (loadError) {
      if (isAbortError(loadError) || rootGeneration.current !== generation) return
      setRootStatus('error')
      setError(errorMessage(loadError, 'Unable to load Payment Notes reconciliation evidence.'))
    }
  }, [])

  const openRun = useCallback(async (runId: string) => {
    detailAbort.current?.abort()
    const controller = new AbortController()
    detailAbort.current = controller
    const generation = detailGeneration.current + 1
    detailGeneration.current = generation
    setActionStatus('loading')
    setError('')
    try {
      const detail = await getPaymentNotesRun(runId, controller.signal)
      if (controller.signal.aborted || detailGeneration.current !== generation) return
      setSelectedRun(detail)
      setSelectedDepositKey(null)
      setSelectedItemId(null)
      setQueue('all')
      setActionStatus('ready')
    } catch (loadError) {
      if (isAbortError(loadError) || detailGeneration.current !== generation) return
      setActionStatus('error')
      setError(errorMessage(loadError, 'Unable to reopen the reconciliation run.'))
    }
  }, [])

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void loadRoot(), 0)
    window.addEventListener(WORKFLOW_SESSION_EVENT, loadRoot)
    return () => {
      window.clearTimeout(timeoutId)
      window.removeEventListener(WORKFLOW_SESSION_EVENT, loadRoot)
      rootAbort.current?.abort()
    }
  }, [loadRoot])

  useEffect(() => () => {
    detailAbort.current?.abort()
    actionAbort.current?.abort()
  }, [])

  useEffect(() => {
    if (!selectedItemId) return
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setSelectedItemId(null)
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [selectedItemId])

  function applyWindowStartingPoint(mode: WindowStartingPoint) {
    setWindowStartingPoint(mode)
    const window = calendarWindowSuggestion(mode)
    setDateFrom(window.dateFrom)
    setDateTo(window.dateTo)
  }

  async function refresh() {
    setActionStatus('loading')
    setError('')
    setActionMessage('')
    try {
      await loadRoot()
      if (selectedRun) await openRun(selectedRun.run.run_id)
      setActionStatus('ready')
      setActionMessage('Current route, bank, and review evidence reloaded.')
    } catch (refreshError) {
      setActionStatus('error')
      setError(errorMessage(refreshError, 'Unable to refresh Payment Notes.'))
    }
  }

  async function uploadReference(file: File, versionLabel: string) {
    actionAbort.current?.abort()
    const controller = new AbortController()
    actionAbort.current = controller
    setRouteActionStatus('loading')
    setError('')
    setActionMessage('')
    try {
      const reference = await uploadRouteReference(file, versionLabel, controller.signal)
      await loadRoot()
      setRouteActionStatus('ready')
      setActionMessage(
        `Route reference ${reference.source_file_name} uploaded as ${reference.version_label}. Review its quality and activate it before reconciling bank files.`,
      )
    } catch (uploadError) {
      if (isAbortError(uploadError)) return
      setRouteActionStatus('error')
      setError(errorMessage(uploadError, 'Unable to upload the route reference.'))
    }
  }

  async function activateReference(referenceId: string) {
    actionAbort.current?.abort()
    const controller = new AbortController()
    actionAbort.current = controller
    setRouteActionStatus('loading')
    setError('')
    setActionMessage('')
    try {
      await activateRouteReference(referenceId, controller.signal)
      await loadRoot()
      setRouteActionStatus('ready')
      setActionMessage('The selected route reference is now active for new reconciliation runs.')
    } catch (activateError) {
      if (isAbortError(activateError)) return
      setRouteActionStatus('error')
      setError(errorMessage(activateError, 'Unable to activate the route reference.'))
    }
  }

  async function importBankFile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    if (!bankFile) {
      setError('Select a PNC remote-capture CSV.')
      return
    }
    if (!routeStatus?.ready) {
      setError('Activate a valid route reference before starting reconciliation.')
      return
    }
    if (!dateFrom || !dateTo || dateFrom > dateTo) {
      setError('Enter a valid inclusive Payment Notes date window.')
      return
    }

    actionAbort.current?.abort()
    const controller = new AbortController()
    actionAbort.current = controller
    setActionStatus('loading')
    setError('')
    setActionMessage('')
    try {
      const detail = await createPaymentNotesRun(bankFile, dateFrom, dateTo, controller.signal)
      setSelectedRun(detail)
      setSelectedDepositKey(null)
      setSelectedItemId(null)
      setQueue('all')
      setBankFile(null)
      await loadRoot()
      setActionStatus('ready')
      setActionMessage('The bank file was preserved and reconciled. Review all unresolved and blocking evidence before recording dispositions.')
      form.reset()
    } catch (importError) {
      if (isAbortError(importError)) return
      setActionStatus('error')
      setError(errorMessage(importError, 'Unable to import and reconcile the bank file.'))
    }
  }

  async function recordReview(payload: {
    decision: 'accept_candidate' | 'leave_unmatched' | 'hold'
    selected_payment_id?: string
    reason: string
  }) {
    if (!selectedRun || !selectedItem) return
    actionAbort.current?.abort()
    const controller = new AbortController()
    actionAbort.current = controller
    setActionStatus('loading')
    setError('')
    setActionMessage('')
    try {
      const response = await createItemReview(
        selectedRun.run.run_id,
        selectedItem.bank_item_id,
        {
          ...payload,
          idempotency_key: paymentNotesIdempotencyKey('payment-notes-review'),
        },
        controller.signal,
      )
      setSelectedRun(response.detail)
      setRuns((current) => current.map((run) => (
        run.run_id === response.run.run_id ? response.run : run
      )))
      setActionStatus('ready')
      setActionMessage('Manual review recorded locally with its reason. No ERP or source-system write occurred.')
    } catch (reviewError) {
      if (isAbortError(reviewError)) return
      setActionStatus('error')
      setError(errorMessage(reviewError, 'Unable to record the manual review.'))
    }
  }

  if (rootStatus === 'loading') {
    return (
      <section className="pn-workspace pn-loading-state" aria-live="polite">
        <span className="pn-spinner" />
        <div><strong>Loading Payment Notes</strong><p>Retrieving current route, bank, and review evidence.</p></div>
      </section>
    )
  }

  if (!signedIn) {
    return (
      <section className="pn-workspace">
        <header className="pn-header">
          <div><span>R73 · PAYMENT NOTES</span><h1>Warehouse Deposit Reconciliation</h1><p>Match deposited checks to expected Payment Notes using exact location, route, date, check, and amount evidence.</p></div>
          <div className="pn-governance-card"><strong>Read-only ERP evidence</strong><span>Recommendation and review only</span><small>No receipt, AR, cash-application, or source-system write authority.</small></div>
        </header>
        <Message kind="notice">
          <div><strong>Authentication required</strong><p>Sign in through Work Management, then return to Payment Notes. Module access is enforced by the backend.</p></div>
        </Message>
      </section>
    )
  }

  const summary = selectedRun?.run.summary

  return (
    <section className="pn-workspace">
      <header className="pn-header">
        <div>
          <span>R73 · PAYMENT NOTES</span>
          <h1>Warehouse Deposit Reconciliation</h1>
          <p>Reconcile PNC remote-capture checks to expected Payment Notes with explainable, one-to-one matching and durable human review.</p>
        </div>
        <div className="pn-governance-card">
          <strong>Read-only ERP evidence</strong>
          <span>Recommendation and review only</span>
          <small>No receipt, AR, cash-application, or source-system write authority.</small>
        </div>
      </header>

      <div className="pn-toolbar">
        <div>
          <span className={`pn-health-dot ${routeStatus?.ready ? 'ready' : 'blocked'}`} />
          <span>{routeStatus?.ready ? 'Route reference ready' : 'Route reference required'}</span>
          {selectedRun && <><i /> <span>Run {shortHash(selectedRun.run.run_id)}</span></>}
        </div>
        <button type="button" className="pn-button pn-button--secondary" onClick={() => void refresh()} disabled={actionStatus === 'loading'}>
          {actionStatus === 'loading' ? 'Working…' : 'Refresh evidence'}
        </button>
      </div>

      {error && <Message kind="error"><strong>Payment Notes request failed</strong><span>{error}</span></Message>}
      {actionMessage && <Message kind="success"><span>{actionMessage}</span></Message>}

      <div className="pn-setup-grid">
        <RouteReferencePanel
          status={routeStatus}
          references={routeReferences}
          busy={routeActionStatus === 'loading'}
          onUpload={uploadReference}
          onActivate={activateReference}
        />

        <section className="pn-panel pn-import-panel" aria-labelledby="pn-import-title">
          <div className="pn-panel-heading">
            <div>
              <span>Bank evidence</span>
              <h2 id="pn-import-title">Start reconciliation</h2>
              <p>Upload one PNC remote-capture CSV and execute an explicit, inclusive Payment Notes creation-date window.</p>
            </div>
            <StatusPill status="RECOMMENDATION_ONLY" />
          </div>
          <form className="pn-import-form" onSubmit={(event) => void importBankFile(event)}>
            <label className="pn-file-field">
              <span>PNC remote-capture CSV</span>
              <input type="file" accept=".csv,text/csv" onChange={(event) => setBankFile(event.target.files?.[0] ?? null)} disabled={actionStatus === 'loading'} />
              <small>{bankFile ? `${bankFile.name} · ${(bankFile.size / 1024).toFixed(1)} KB` : 'No bank file selected'}</small>
            </label>
            <div className="pn-window-presets">
              <span>Calendar starting point</span>
              <div>
                <button type="button" className={windowStartingPoint === 'prior_calendar_day' ? 'active' : ''} onClick={() => applyWindowStartingPoint('prior_calendar_day')}>Prior-day suggestion</button>
                <button type="button" className={windowStartingPoint === 'same_day' ? 'active' : ''} onClick={() => applyWindowStartingPoint('same_day')}>Same-day suggestion</button>
              </div>
              <small>These are calendar suggestions only. Confirm the exact executed dates, including K&amp;M holidays, before importing.</small>
            </div>
            <div className="pn-date-grid">
              <label><span>Date from</span><input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} disabled={actionStatus === 'loading'} /></label>
              <label><span>Date to</span><input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} disabled={actionStatus === 'loading'} /></label>
            </div>
            <div className="pn-import-action">
              <div><strong>Exact cents · one-to-one assignment</strong><span>Virtual Credit balances the deposit but is never treated as a physical check.</span></div>
              <button type="submit" className="pn-button pn-button--primary" disabled={!bankFile || !routeStatus?.ready || actionStatus === 'loading'}>
                {actionStatus === 'loading' ? 'Reconciling…' : 'Import and reconcile'}
              </button>
            </div>
          </form>
        </section>
      </div>

      <div className="pn-work-grid">
        <RunHistory runs={runs} selectedRunId={selectedRun?.run.run_id ?? null} busy={actionStatus === 'loading'} onOpen={(runId) => void openRun(runId)} />

        <main className="pn-run-workspace">
          {!selectedRun ? (
            <section className="pn-panel">
              <EmptyState title="Select or create a reconciliation run" detail="A reopened run restores its immutable source, route version, date range, deposits, candidates, exceptions, and human-review state." />
            </section>
          ) : (
            <>
              <section className="pn-run-heading">
                <div>
                  <span>Current reconciliation</span>
                  <h2>{selectedRun.run.source_file_name}</h2>
                  <p>{selectedRun.run.date_from} through {selectedRun.run.date_to} · route reference v{selectedRun.run.route_reference_version} · rules {selectedRun.run.ruleset_version}</p>
                </div>
                <div><StatusPill status={selectedRun.run.status} /><small>{selectedRun.run.counts_final ? 'Counts final' : 'Counts incomplete'} · source {selectedRun.source_complete ? 'complete' : 'incomplete'}</small></div>
              </section>

              {selectedRun.warnings.length > 0 && (
                <Message kind="notice"><div><strong>Evidence warnings</strong><ul>{selectedRun.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div></Message>
              )}

              <ERPProvenancePanel provenance={selectedRun.erp_provenance} />

              <div className="pn-summary-grid">
                <SummaryCard label="Physical checks" value={formatCount(summary?.physical_item_count)} detail={formatCents(summary?.physical_total_cents)} tone="info" />
                <SummaryCard label="Matched" value={formatCount(summary?.matched_count)} detail={formatCents(summary?.matched_total_cents)} tone="good" />
                <SummaryCard label="Locally recorded unmatched" value={formatCount(summary?.accepted_unmatched_count)} detail={formatCents(summary?.accepted_unmatched_total_cents)} tone="info" />
                <SummaryCard label="Unresolved" value={formatCount(summary?.unresolved_count)} detail={formatCents(summary?.unresolved_total_cents)} tone={summary?.unresolved_count ? 'warning' : 'good'} />
                <SummaryCard label="Blocking exceptions" value={formatCount(summary?.blocking_exception_count)} detail={selectedRun.run.erp_write_performed ? 'Unexpected ERP write flagged' : 'No ERP write performed'} tone={summary?.blocking_exception_count || selectedRun.run.erp_write_performed ? 'danger' : 'neutral'} />
              </div>

              {selectedDeposit && (
                <div className="pn-selected-deposit-bar">
                  <div><span>Filtered to</span><strong>{selectedDeposit.payment_location_key ?? selectedDeposit.bank_location_raw} · deposit {selectedDeposit.deposit_no}</strong></div>
                  <div><span>Bank total</span><strong>{formatCents(selectedDeposit.bank_total_cents)}</strong></div>
                  <div><span>Virtual Credit difference</span><strong>{formatCents(selectedDeposit.virtual_credit_difference_cents)}</strong></div>
                </div>
              )}

              <div className="pn-reconciliation-grid">
                <DepositList deposits={selectedRun.deposits} selectedDepositKey={selectedDepositKey} onSelect={(key) => { setSelectedDepositKey(key); setSelectedItemId(null) }} />
                <ItemQueue items={visibleItems} queue={queue} selectedItemId={selectedItemId} onQueueChange={setQueue} onOpen={setSelectedItemId} />
              </div>
            </>
          )}
        </main>
      </div>

      {selectedItem && (
        <div className="pn-detail-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSelectedItemId(null) }}>
          <ItemDetail key={selectedItem.bank_item_id} item={selectedItem} busy={actionStatus === 'loading'} onClose={() => setSelectedItemId(null)} onReview={recordReview} />
        </div>
      )}
    </section>
  )
}
