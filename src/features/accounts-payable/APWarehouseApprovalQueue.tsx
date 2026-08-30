import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { createAPWarehouseApprovalAction, getAPWarehouseApprovalQueue } from './api'
import { GovernanceBoundary, Message, StatusTag } from './components'
import { errorMessage, formatCurrency, formatDate, formatDateTime, isAbortError } from './format'
import type {
  APWarehouseApprovalItem,
  APWarehouseApprovalQueueResponse,
  WarehouseApprovalStatus,
} from './types'

type AsyncStatus = 'idle' | 'loading' | 'success' | 'error'

const BUCKETS: Array<{
  key: 'needs_approval' | 'approved_by_warehouse' | 'approved_and_entered_by_ap'
  label: string
  next: WarehouseApprovalStatus | null
}> = [
  { key: 'needs_approval', label: 'Needs Approval', next: 'approved_by_warehouse' },
  { key: 'approved_by_warehouse', label: 'Approved by Warehouse', next: 'approved_and_entered_by_ap' },
  { key: 'approved_and_entered_by_ap', label: 'Approved & Entered by A/P', next: null },
]

const STATUS_OPTIONS: Array<{ value: WarehouseApprovalStatus; label: string }> = [
  { value: 'needs_approval', label: 'Needs Approval' },
  { value: 'approved_by_warehouse', label: 'Approved by Warehouse' },
  { value: 'approved_and_entered_by_ap', label: 'Approved & Entered by A/P' },
]

function itemKey(item: APWarehouseApprovalItem): string {
  return `${item.vendor_number}::${item.invoice_number}`
}

export default function APWarehouseApprovalQueue({ refreshKey }: { refreshKey: number }) {
  const [division, setDivision] = useState('')
  const [queue, setQueue] = useState<APWarehouseApprovalQueueResponse | null>(null)
  const [status, setStatus] = useState<AsyncStatus>('loading')
  const [error, setError] = useState('')

  const [activeKey, setActiveKey] = useState<string | null>(null)
  const [targetStatus, setTargetStatus] = useState<WarehouseApprovalStatus>('approved_by_warehouse')
  const [actorIdentity, setActorIdentity] = useState('')
  const [notes, setNotes] = useState('')
  const [actionStatus, setActionStatus] = useState<AsyncStatus>('idle')
  const [actionError, setActionError] = useState('')

  const loadQueue = useCallback(async (signal?: AbortSignal) => {
    setStatus('loading')
    setError('')
    try {
      const response = await getAPWarehouseApprovalQueue(division || null, signal)
      setQueue(response)
      setStatus('success')
    } catch (loadError) {
      if (isAbortError(loadError)) return
      setStatus('error')
      setError(errorMessage(loadError, 'Unable to load the warehouse approval queue.'))
    }
  }, [division])

  useEffect(() => {
    const controller = new AbortController()
    void loadQueue(controller.signal)
    return () => controller.abort()
  }, [loadQueue, refreshKey])

  function openAction(item: APWarehouseApprovalItem, defaultStatus: WarehouseApprovalStatus) {
    setActiveKey(itemKey(item))
    setTargetStatus(defaultStatus)
    setActorIdentity('')
    setNotes('')
    setActionStatus('idle')
    setActionError('')
  }

  function closeAction() {
    setActiveKey(null)
  }

  async function submitAction(event: FormEvent<HTMLFormElement>, item: APWarehouseApprovalItem) {
    event.preventDefault()
    if (!actorIdentity.trim()) {
      setActionStatus('error')
      setActionError('Enter your name to record this action.')
      return
    }
    setActionStatus('loading')
    setActionError('')
    try {
      await createAPWarehouseApprovalAction({
        vendor_number: item.vendor_number,
        invoice_number: item.invoice_number,
        to_status: targetStatus,
        actor_identity: actorIdentity.trim(),
        notes: notes.trim(),
      })
      setActiveKey(null)
      await loadQueue()
    } catch (submitError) {
      setActionStatus('error')
      setActionError(errorMessage(submitError, 'Unable to record the warehouse approval action.'))
    }
  }

  function renderItem(item: APWarehouseApprovalItem, next: WarehouseApprovalStatus | null) {
    const key = itemKey(item)
    const netAmount = item.amount_invoiced - item.amount_discount
    return (
      <article key={key} className="ap-warehouse-card">
        <div className="ap-warehouse-card-heading">
          <strong>{item.invoice_number}</strong>
          {item.on_hold && <StatusTag status="on hold" />}
        </div>
        <span>
          {item.vendor_name ? `${item.vendor_name} · Vendor ${item.vendor_number}` : `Vendor ${item.vendor_number}`}
        </span>
        <span>
          {`Account ${item.gl_account || 'unavailable'} · Division ${item.gl_division || 'unavailable'} · Department ${item.gl_department || 'unavailable'}`}
        </span>
        <div className="ap-warehouse-card-amounts">
          <span>{formatCurrency(netAmount)}</span>
          <span>Invoiced {formatDate(item.invoice_date)} · Due {formatDate(item.due_date)}</span>
        </div>
        {item.last_actor_identity && (
          <small>Last action by {item.last_actor_identity} · {formatDateTime(item.last_action_at)}</small>
        )}
        {item.linked_ap_invoice_id && (
          <small>Linked to Invoice Intelligence · {item.linked_ap_invoice_id}</small>
        )}
        {activeKey === key ? (
          <form className="ap-warehouse-action-form" onSubmit={(event) => void submitAction(event, item)}>
            <label>
              <span>Move to</span>
              <select
                value={targetStatus}
                onChange={(event) => setTargetStatus(event.target.value as WarehouseApprovalStatus)}
              >
                {STATUS_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </label>
            <label>
              <span>Your name</span>
              <input value={actorIdentity} onChange={(event) => setActorIdentity(event.target.value)} maxLength={200} />
            </label>
            <label>
              <span>Notes (optional)</span>
              <input value={notes} onChange={(event) => setNotes(event.target.value)} maxLength={2000} />
            </label>
            {actionError && <Message kind="error">{actionError}</Message>}
            <div className="ap-warehouse-action-buttons">
              <button type="submit" className="ap-primary-button" disabled={actionStatus === 'loading'}>
                {actionStatus === 'loading' ? 'Saving…' : 'Save'}
              </button>
              <button type="button" className="ap-secondary-button" onClick={closeAction}>Cancel</button>
            </div>
          </form>
        ) : (
          <button
            type="button"
            className="ap-secondary-button"
            onClick={() => openAction(item, next ?? item.status)}
          >
            Advance status
          </button>
        )}
      </article>
    )
  }

  return (
    <div className="ap-warehouse-workspace">
      <section className="ap-panel ap-warehouse-boundary">
        <div className="ap-panel-heading">
          <div>
            <span className="ap-kicker">Evidence and documentation only</span>
            <h2>Warehouse approval queue</h2>
          </div>
          <StatusTag status="no execution authority" />
        </div>
        <p>
          Every currently open ERP invoice, so a warehouse manager can review it before A/P keys
          it in. An invoice leaves this queue automatically once MaddenCo shows it paid — there is
          no explicit close step. Recording a status here documents review only: it never approves
          an invoice, blocks A/P's own entry, or authorizes payment.
        </p>
        <label className="ap-warehouse-division-filter">
          <span>Division</span>
          <select value={division} onChange={(event) => setDivision(event.target.value)}>
            <option value="">All divisions</option>
            {(queue?.available_divisions ?? []).map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
        </label>
      </section>

      {status === 'loading' && <p className="ap-empty-inline">Loading the warehouse approval queue…</p>}
      {error && <Message kind="error">{error}</Message>}

      {queue && status === 'success' && (
        <div className="ap-warehouse-columns">
          {BUCKETS.map((bucket) => (
            <section className="ap-panel ap-warehouse-column" key={bucket.key}>
              <div className="ap-panel-heading">
                <div><h3>{bucket.label}</h3></div>
                <span className="ap-count">{queue[bucket.key].length}</span>
              </div>
              {queue[bucket.key].length === 0 && (
                <p className="ap-empty-inline">No invoices in this status.</p>
              )}
              <div className="ap-warehouse-card-list">
                {queue[bucket.key].map((item) => renderItem(item, bucket.next))}
              </div>
            </section>
          ))}
        </div>
      )}

      {queue && <GovernanceBoundary governance={queue.governance} />}
    </div>
  )
}
