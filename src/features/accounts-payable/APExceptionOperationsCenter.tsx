import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import {
  createAPExceptionAction,
  getAPExceptionActions,
  getAPExceptionOperations,
} from './api'
import { errorMessage, formatDateTime } from './format'
import type {
  APExceptionActionDisposition,
  APExceptionActionHistoryResponse,
  APExceptionOperationsResponse,
  APExceptionQueueItem,
  APExceptionWorkState,
  CreateAPExceptionActionRequest,
} from './types'
import { ContextWorkPanel } from '../workflow-foundation'

type QueueFilter = 'all' | 'unworked' | 'follow_up' | 'source_changed' | 'documented'

const dispositionOptions: Array<{ value: APExceptionActionDisposition; label: string }> = [
  { value: 'investigating', label: 'Investigating' },
  { value: 'information_requested', label: 'Information requested' },
  { value: 'document_correction_needed', label: 'Document correction needed' },
  { value: 'duplicate_review_complete', label: 'Duplicate review complete' },
  { value: 'ready_for_control_case', label: 'Documented for control-case preparation' },
]

const stateLabels: Record<APExceptionWorkState, string> = {
  unworked: 'Unworked',
  follow_up_scheduled: 'Follow-up scheduled',
  follow_up_overdue: 'Follow-up overdue',
  source_changed: 'Source changed',
  documented_for_next_step: 'Documented for next step',
  documented: 'Documented',
}

function todayInput(): string {
  const now = new Date()
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
  return local.toISOString().slice(0, 10)
}

function extractedAmount(value: number | null): string {
  if (value === null) return 'Unavailable'
  return value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function matchesFilter(item: APExceptionQueueItem, filter: QueueFilter): boolean {
  if (filter === 'all') return true
  if (filter === 'follow_up') return item.work_state === 'follow_up_scheduled' || item.work_state === 'follow_up_overdue'
  if (filter === 'documented') return item.work_state === 'documented' || item.work_state === 'documented_for_next_step'
  return item.work_state === filter
}

export default function APExceptionOperationsCenter({ refreshKey }: { refreshKey: number }) {
  const [asOfDate, setAsOfDate] = useState(todayInput)
  const [retryKey, setRetryKey] = useState(0)
  const [data, setData] = useState<APExceptionOperationsResponse | null>(null)
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [loadError, setLoadError] = useState('')
  const [filter, setFilter] = useState<QueueFilter>('all')
  const [query, setQuery] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [history, setHistory] = useState<APExceptionActionHistoryResponse | null>(null)
  const [historyStatus, setHistoryStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle')
  const [historyError, setHistoryError] = useState('')
  const [disposition, setDisposition] = useState<APExceptionActionDisposition>('investigating')
  const [ownerIdentity, setOwnerIdentity] = useState('')
  const [actorIdentity, setActorIdentity] = useState('')
  const [followUpDate, setFollowUpDate] = useState('')
  const [notes, setNotes] = useState('')
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [saveMessage, setSaveMessage] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => {
      setStatus('loading')
      setLoadError('')
      void getAPExceptionOperations(asOfDate, controller.signal)
        .then((response) => {
          setData(response)
          setStatus('success')
          setSelectedId((current) => (
            current && response.items.some((item) => item.ap_invoice_id === current)
              ? current
              : response.items[0]?.ap_invoice_id ?? null
          ))
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) return
          setStatus('error')
          setLoadError(errorMessage(error, 'Unable to load AP exception operations.'))
        })
    }, 0)
    return () => {
      window.clearTimeout(timeoutId)
      controller.abort()
    }
  }, [asOfDate, refreshKey, retryKey])

  useEffect(() => {
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => {
      if (!selectedId) {
        setHistory(null)
        setHistoryStatus('idle')
        return
      }
      setHistoryStatus('loading')
      setHistoryError('')
      void getAPExceptionActions(selectedId, controller.signal)
        .then((response) => {
          setHistory(response)
          setHistoryStatus('success')
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) return
          setHistoryStatus('error')
          setHistoryError(errorMessage(error, 'Unable to load exception action history.'))
        })
    }, 0)
    return () => {
      window.clearTimeout(timeoutId)
      controller.abort()
    }
  }, [selectedId])

  const visibleItems = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase()
    return (data?.items ?? []).filter((item) => {
      if (!matchesFilter(item, filter)) return false
      if (!normalized) return true
      return [
        item.vendor_name,
        item.vendor_number,
        item.invoice_number,
        item.source_file_name,
        ...item.reasons.flatMap((reason) => [reason.label, reason.code]),
      ].filter(Boolean).some((value) => String(value).toLocaleLowerCase().includes(normalized))
    })
  }, [data, filter, query])

  const selected = data?.items.find((item) => item.ap_invoice_id === selectedId) ?? null

  async function reloadOperations(): Promise<APExceptionOperationsResponse> {
    const response = await getAPExceptionOperations(asOfDate)
    setData(response)
    return response
  }

  async function submitAction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selected) return
    if (!ownerIdentity.trim() || !actorIdentity.trim() || !notes.trim()) {
      setSaveStatus('error')
      setSaveMessage('Owner, recorded by, and notes are required professional context.')
      return
    }
    const payload: CreateAPExceptionActionRequest = {
      disposition,
      owner_identity: ownerIdentity.trim(),
      actor_identity: actorIdentity.trim(),
      notes: notes.trim(),
      follow_up_date: followUpDate || null,
    }
    setSaveStatus('saving')
    setSaveMessage('')
    try {
      const saved = await createAPExceptionAction(selected.ap_invoice_id, payload)
      const [, nextHistory] = await Promise.all([
        reloadOperations(),
        getAPExceptionActions(selected.ap_invoice_id),
      ])
      setHistory(nextHistory)
      setHistoryStatus('success')
      setNotes('')
      setFollowUpDate('')
      setSaveStatus('success')
      setSaveMessage(
        `Action ${saved.action_id} was appended as professional workflow metadata. No invoice approval, payment effect, or ERP write occurred.`,
      )
    } catch (error) {
      setSaveStatus('error')
      setSaveMessage(errorMessage(error, 'Unable to append the exception action.'))
    }
  }

  if (status === 'loading' && !data) {
    return <div className="ap-loading"><span className="ap-spinner" /><div><strong>Building exception operations</strong><p>Ordering current saved review evidence and append-only follow-up state…</p></div></div>
  }
  if (status === 'error' && !data) {
    return <div className="ap-message ap-message--error"><div><strong>Exception operations are unavailable.</strong><span>{loadError}</span></div><button type="button" onClick={() => setRetryKey((value) => value + 1)}>Retry</button></div>
  }
  if (!data) return null

  return (
    <section className="ap-exception-operations">
      <div className="ap-exception-summary" aria-label="Exception queue summary">
        <article><span>Current queue</span><strong>{data.summary.queue_count}</strong></article>
        <article><span>Unworked</span><strong>{data.summary.unworked_count}</strong></article>
        <article className={data.summary.follow_up_overdue_count ? 'is-attention' : ''}><span>Follow-up overdue</span><strong>{data.summary.follow_up_overdue_count}</strong></article>
        <article className={data.summary.source_changed_count ? 'is-attention' : ''}><span>Source changed</span><strong>{data.summary.source_changed_count}</strong></article>
        <article><span>Documented</span><strong>{data.summary.documented_count}</strong></article>
        <article><span>Known extracted amount</span><strong>{extractedAmount(data.summary.extracted_amount)}</strong><small>{data.summary.known_amount_count}/{data.summary.queue_count} amounts known</small></article>
      </div>

      <div className="ap-evidence-boundary">
        <strong>Professional work queue · evidence state, not an approved SLA or authority assignment</strong>
        <p>Queue order is deterministic. Operator-entered owners are not authenticated assignments, and dispositions do not resolve source exceptions, approve invoices, or authorize payment.</p>
      </div>

      <div className="ap-exception-toolbar">
        <label>Filter queue<input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Vendor, invoice, file, or reason" /></label>
        <label>Work state<select value={filter} onChange={(event) => setFilter(event.target.value as QueueFilter)}><option value="all">All current exceptions</option><option value="unworked">Unworked</option><option value="follow_up">Follow-up</option><option value="source_changed">Source changed</option><option value="documented">Documented</option></select></label>
        <label>Follow-up as of<input type="date" value={asOfDate} onChange={(event) => setAsOfDate(event.target.value)} /></label>
      </div>

      {status === 'error' && <div className="ap-message ap-message--error"><span>{loadError}</span><button type="button" onClick={() => setRetryKey((value) => value + 1)}>Retry current queue</button></div>}
      <div className="ap-exception-layout">
        <div className="ap-exception-queue" aria-label="Current AP exception queue">
          <div className="ap-exception-queue-heading"><div><span className="ap-kicker">Deterministic ordering</span><h3>Current exception work</h3></div><strong>{visibleItems.length}</strong></div>
          {visibleItems.length === 0 ? (
            <div className="ap-empty-state"><strong>No current exceptions matched.</strong><p>No placeholder work items were created.</p></div>
          ) : visibleItems.map((item) => (
            <button type="button" key={item.ap_invoice_id} className={selectedId === item.ap_invoice_id ? 'ap-exception-item is-selected' : 'ap-exception-item'} onClick={() => { setSelectedId(item.ap_invoice_id); setSaveStatus('idle'); setSaveMessage('') }}>
              <span className="ap-exception-rank">{item.queue_rank}</span>
              <span className="ap-exception-item-main"><strong>{item.vendor_name || 'Vendor unavailable'}</strong><small>{item.invoice_number || 'Invoice number unavailable'} · {item.source_file_name}</small><span>{item.reasons.map((reason) => reason.label).join(' · ')}</span></span>
              <span className={`ap-work-state ap-work-state--${item.work_state.replaceAll('_', '-')}`}>{stateLabels[item.work_state]}</span>
              <span className="ap-exception-amount">{extractedAmount(item.total_amount)}<small>extracted</small></span>
            </button>
          ))}
        </div>

        <div className="ap-exception-detail">
          {!selected ? <div className="ap-empty-state"><strong>Select a current exception.</strong><p>The selected evidence and append-only action history will appear here.</p></div> : (
            <>
              <div className="ap-exception-detail-header"><div><span className="ap-kicker">Queue #{selected.queue_rank} · {stateLabels[selected.work_state]}</span><h3>{selected.vendor_name || 'Vendor unavailable'}</h3><p>{selected.invoice_number || 'Invoice number unavailable'} · source as of {formatDateTime(selected.source_as_of)}</p></div><strong>{extractedAmount(selected.total_amount)}</strong></div>
              <div className="ap-exception-reasons">{selected.reasons.map((reason) => <article key={`${reason.source}-${reason.code}`}><div><strong>{reason.label}</strong><span className={`ap-status-tag ap-status-tag--${reason.severity}`}>{reason.severity}</span></div><p>{reason.explanation}</p><small>{reason.source.replaceAll('_', ' ')} · {reason.code}</small></article>)}</div>

              <form className="ap-exception-action-form" onSubmit={submitAction}>
                <span className="ap-kicker">Append-only professional action</span><h3>Record follow-up context</h3>
                <label>Disposition<select value={disposition} onChange={(event) => setDisposition(event.target.value as APExceptionActionDisposition)}>{dispositionOptions.map((option) => <option value={option.value} key={option.value}>{option.label}</option>)}</select></label>
                <div className="ap-exception-form-row"><label>Owner<input value={ownerIdentity} onChange={(event) => setOwnerIdentity(event.target.value)} placeholder="Operator-supplied work owner" /></label><label>Recorded by<input value={actorIdentity} onChange={(event) => setActorIdentity(event.target.value)} placeholder="Person recording this action" /></label></div>
                <label>Follow-up date (optional)<input type="date" value={followUpDate} onChange={(event) => setFollowUpDate(event.target.value)} /></label>
                <label>Notes<textarea rows={4} value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Evidence reviewed, information requested, and next professional step" /></label>
                <p className="ap-control-boundary">Owner identity is operator supplied and authority is not independently verified · no automatic resolution · no approval, payment, or ERP effect</p>
                <button type="submit" className="ap-primary-button" disabled={saveStatus === 'saving'}>{saveStatus === 'saving' ? 'Appending action…' : 'Append exception action'}</button>
                {saveMessage && <p className={saveStatus === 'error' ? 'ap-form-error' : 'ap-form-success'}>{saveMessage}</p>}
              </form>

              <div className="ap-exception-history"><span className="ap-kicker">Immutable history</span><h3>Recorded actions</h3>{historyStatus === 'loading' && <p>Loading action history…</p>}{historyStatus === 'error' && <p className="ap-form-error">{historyError}</p>}{historyStatus === 'success' && !history?.actions.length && <p>No professional actions have been recorded for this invoice.</p>}{history?.actions.map((action) => <article key={action.action_id}><div><strong>{dispositionOptions.find((option) => option.value === action.disposition)?.label ?? action.disposition.replaceAll('_', ' ')}</strong><small>{formatDateTime(action.created_at)}</small></div><span>Owner: {action.owner_identity} · recorded by {action.actor_identity}</span>{action.follow_up_date && <span>Follow-up: {action.follow_up_date}</span>}<p>{action.notes}</p><small>Evidence SHA-256 {action.source_evidence_sha256}</small></article>)}</div>
              <ContextWorkPanel
                capability="accounts_payable"
                contextType="ap_invoice"
                contextId={selected.ap_invoice_id}
                contextLabel={`${selected.vendor_name || 'Vendor unavailable'} · ${selected.invoice_number || selected.ap_invoice_id}`}
                defaultTitle={`Follow up on AP exception ${selected.invoice_number || selected.ap_invoice_id}`}
              />
            </>
          )}
        </div>
      </div>

      <div className="ap-two-column">
        <div className="ap-evidence-boundary"><strong>Source and workflow limits</strong>{data.warnings.map((warning) => <p key={warning}>{warning}</p>)}</div>
        <div className="ap-evidence-boundary"><strong>Authority limits</strong>{data.governance.statements.map((statement) => <p key={statement}>{statement}</p>)}</div>
      </div>
    </section>
  )
}
