import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import {
  createRouteNote,
  getRouteEvidence,
  getRouteNotes,
  searchRoutes,
} from './api'
import type {
  RouteEvidenceResponse,
  RouteNoteHistoryResponse,
  RouteSearchResult,
} from './types'
import './FreightLogisticsWorkspace.css'

function formatNumber(value: number | null | undefined): string {
  return value == null ? 'Unavailable' : value.toLocaleString('en-US')
}

function formatWeight(value: number | null | undefined): string {
  return value == null ? 'Unavailable' : `${value.toLocaleString('en-US')} lb`
}

function formatMoney(value: number | null | undefined): string {
  if (value == null) return 'Unavailable'
  return value.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
}

function formatMinutes(value: number | null | undefined): string {
  return value == null ? 'Unavailable' : `${value.toLocaleString('en-US')} min`
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return 'Unavailable'
  const date = new Date(value)
  return Number.isNaN(date.valueOf())
    ? value
    : date.toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

type DetailError = { routeCode: string; message: string }

export default function FreightLogisticsWorkspace() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<RouteSearchResult[]>([])
  const [searchError, setSearchError] = useState('')

  const [selectedRoute, setSelectedRoute] = useState<string | null>(null)
  const [evidence, setEvidence] = useState<RouteEvidenceResponse | null>(null)
  const [notes, setNotes] = useState<RouteNoteHistoryResponse | null>(null)
  const [detailError, setDetailError] = useState<DetailError | null>(null)

  const [authorIdentity, setAuthorIdentity] = useState('')
  const [noteText, setNoteText] = useState('')
  const [noteSaveStatus, setNoteSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [noteSaveMessage, setNoteSaveMessage] = useState('')

  // Evidence/errors are tagged with the route they belong to, so switching
  // the selected route never needs a synchronous "clear" setState call
  // inside an effect — stale data for a different route is simply ignored.
  const currentEvidence =
    evidence && evidence.identity.route_code === selectedRoute ? evidence : null
  const currentDetailError =
    detailError && detailError.routeCode === selectedRoute ? detailError.message : ''
  const isLoadingDetail = selectedRoute != null && !currentEvidence && !currentDetailError

  useEffect(() => {
    const controller = new AbortController()
    searchRoutes(query, controller.signal)
      .then((response) => {
        setResults(response.routes)
        setSearchError('')
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return
        setSearchError(errorMessage(error, 'Unable to search routes.'))
      })
    return () => controller.abort()
  }, [query])

  useEffect(() => {
    if (selectedRoute == null) return
    const controller = new AbortController()
    const routeCode = selectedRoute
    Promise.all([
      getRouteEvidence(routeCode, controller.signal),
      getRouteNotes(routeCode, controller.signal),
    ])
      .then(([evidenceResponse, notesResponse]) => {
        setEvidence(evidenceResponse)
        setNotes(notesResponse)
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return
        setDetailError({
          routeCode,
          message: errorMessage(error, 'Unable to load route evidence.'),
        })
      })
    return () => controller.abort()
  }, [selectedRoute])

  const recentLoadLines = useMemo(
    () => currentEvidence?.load.lines.slice(0, 15) ?? [],
    [currentEvidence],
  )
  const recentPayments = useMemo(
    () => currentEvidence?.payments.payments.slice(0, 10) ?? [],
    [currentEvidence],
  )
  const recentExceptions = useMemo(
    () => currentEvidence?.exceptions.exceptions.slice(0, 10) ?? [],
    [currentEvidence],
  )

  async function submitNote(event: FormEvent) {
    event.preventDefault()
    if (selectedRoute == null) return
    if (!authorIdentity.trim() || !noteText.trim()) {
      setNoteSaveStatus('error')
      setNoteSaveMessage('Your name and a note are both required.')
      return
    }
    setNoteSaveStatus('saving')
    setNoteSaveMessage('')
    try {
      await createRouteNote(selectedRoute, {
        author_identity: authorIdentity.trim(),
        note: noteText.trim(),
      })
      const refreshed = await getRouteNotes(selectedRoute)
      setNotes(refreshed)
      setNoteText('')
      setNoteSaveStatus('success')
      setNoteSaveMessage('Note saved. It is append-only and creates no ERP change.')
    } catch (error) {
      setNoteSaveStatus('error')
      setNoteSaveMessage(errorMessage(error, 'Unable to save the note.'))
    }
  }

  return (
    <section className="fl-shell">
      <header className="fl-header">
        <div>
          <span className="fl-kicker">Read-only MaddenCo evidence</span>
          <h2>Freight &amp; Logistics</h2>
          <p>Route schedule, load manifest, COD payments, and delivery exceptions — no automatic score, on-time rate, or ERP write.</p>
        </div>
        <label className="fl-search">
          Search routes
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Route code, key, or warehouse"
          />
        </label>
      </header>

      <div className="fl-layout">
        <div className="fl-results">
          {searchError && <p className="fl-error">{searchError}</p>}
          {results.length === 0 ? (
            <p className="fl-empty">No routes matched.</p>
          ) : (
            <ul className="fl-result-list">
              {results.map((route) => (
                <li key={route.route_key}>
                  <button
                    type="button"
                    className={route.route_code === selectedRoute ? 'fl-result fl-result--active' : 'fl-result'}
                    onClick={() => setSelectedRoute(route.route_code)}
                  >
                    <strong>Route {route.route_code || 'Unknown'}</strong>
                    <span>
                      {route.warehouse_location_name || (route.warehouse_number != null ? `Whse #${route.warehouse_number}` : 'Warehouse unavailable')}
                    </span>
                    {!route.active && <em className="fl-tag fl-tag--inactive">Inactive</em>}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="fl-detail">
          {selectedRoute == null && (
            <div className="fl-empty-state">
              <strong>Select a route to view evidence.</strong>
            </div>
          )}

          {isLoadingDetail && (
            <div className="fl-loading"><span className="fl-spinner" /> Loading route evidence…</div>
          )}

          {selectedRoute != null && currentDetailError && (
            <div className="fl-message fl-message--error">
              <strong>Route evidence is unavailable.</strong>
              <span>{currentDetailError}</span>
            </div>
          )}

          {currentEvidence && (
            <div className="fl-evidence">
              <div className="fl-identity-card">
                <div>
                  <h3>Route {currentEvidence.identity.route_code}</h3>
                  <span>
                    Key {currentEvidence.identity.route_key} · {currentEvidence.identity.active ? 'Active' : 'Inactive'} ·{' '}
                    {currentEvidence.warehouse_label.warehouse_location_name || 'Warehouse unavailable'}
                  </span>
                </div>
                <dl>
                  <div><dt>Warehouse #</dt><dd>{formatNumber(currentEvidence.identity.warehouse_number)}</dd></div>
                  <div><dt>Status code</dt><dd>{currentEvidence.identity.status_code || 'Unavailable'}</dd></div>
                  <div><dt>Created</dt><dd>{formatDateTime(currentEvidence.identity.created_at)} by {currentEvidence.identity.created_by || 'Unavailable'}</dd></div>
                  <div><dt>Last changed</dt><dd>{formatDateTime(currentEvidence.identity.changed_at)} by {currentEvidence.identity.changed_by || 'Unavailable'}</dd></div>
                </dl>
                <div className="fl-schedule">
                  {currentEvidence.identity.schedule.map((day) => (
                    <div key={day.day} className={day.scheduled ? 'fl-schedule-day fl-schedule-day--on' : 'fl-schedule-day'}>
                      <span>{day.day.slice(0, 3)}</span>
                      <strong>{day.scheduled ? day.scheduled_stop_count : '—'}</strong>
                    </div>
                  ))}
                </div>
                {currentEvidence.warehouse_label.directions.length > 0 && (
                  <p className="fl-section-note">
                    Dashboard direction(s): {currentEvidence.warehouse_label.directions.map((d) => d.direction_name || 'Unnamed').join(', ')}
                  </p>
                )}
              </div>

              <div className="fl-metric-grid">
                <article><span>Load lines</span><strong>{currentEvidence.load.line_count}</strong></article>
                <article><span>Delivered</span><strong>{currentEvidence.load.delivered_count}</strong></article>
                <article><span>Undelivered</span><strong>{currentEvidence.load.undelivered_count}</strong></article>
                <article><span>Total weight</span><strong>{formatWeight(currentEvidence.load.total_weight)}</strong></article>
                <article><span>Avg elapsed (delivered)</span><strong>{formatMinutes(currentEvidence.load.average_elapsed_minutes)}</strong></article>
              </div>

              <div className="fl-section">
                <h4>Load manifest</h4>
                <p className="fl-section-note">{currentEvidence.load.explanation}</p>
                {recentLoadLines.length === 0 ? (
                  <p className="fl-empty">No load manifest lines found.</p>
                ) : (
                  <div className="fl-table-wrap">
                    <table className="fl-table">
                      <thead><tr><th>Invoice</th><th>Customer</th><th>Product</th><th>Qty</th><th>Weight</th><th>Created</th><th>Delivered</th><th>Elapsed</th></tr></thead>
                      <tbody>
                        {recentLoadLines.map((line, index) => (
                          <tr key={`${line.invoice_number}-${line.line_number}-${index}`}>
                            <td>{line.invoice_number ?? 'Unavailable'}</td>
                            <td>{line.customer_number ?? 'Unavailable'}</td>
                            <td>{line.product_number}<br /><small>{line.description}</small></td>
                            <td>{formatNumber(line.quantity)}</td>
                            <td>{formatWeight(line.weight)}</td>
                            <td>{formatDateTime(line.created_at)}</td>
                            <td>{line.delivered ? formatDateTime(line.delivered_at) : 'Not yet delivered'}</td>
                            <td>{formatMinutes(line.elapsed_minutes)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              <div className="fl-section">
                <h4>COD payments</h4>
                <p className="fl-section-note">{currentEvidence.payments.explanation} Total collected: {formatMoney(currentEvidence.payments.total_amount)} across {currentEvidence.payments.payment_count} payment(s), {currentEvidence.payments.received_count} received / {currentEvidence.payments.unreceived_count} not yet received.</p>
                {recentPayments.length === 0 ? (
                  <p className="fl-empty">No COD payments recorded.</p>
                ) : (
                  <div className="fl-table-wrap">
                    <table className="fl-table">
                      <thead><tr><th>Payment #</th><th>Customer</th><th>Type</th><th>Amount</th><th>Received</th><th>Corrections</th><th>Notes</th></tr></thead>
                      <tbody>
                        {recentPayments.map((payment) => (
                          <tr key={payment.payment_id}>
                            <td>{payment.payment_id}</td>
                            <td>{payment.customer_number ?? 'Unavailable'}</td>
                            <td>{payment.payment_type || 'Unavailable'}</td>
                            <td>{formatMoney(payment.amount)}</td>
                            <td>{payment.received ? formatDateTime(payment.received_at) : 'Not received'}</td>
                            <td>{payment.corrections.length}</td>
                            <td>{payment.notes || '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              <div className="fl-section">
                <h4>Delivery exceptions</h4>
                <p className="fl-section-note">{currentEvidence.exceptions.explanation} {currentEvidence.exceptions.approved_count} approved / {currentEvidence.exceptions.unapproved_count} unapproved of {currentEvidence.exceptions.exception_count}.</p>
                {recentExceptions.length === 0 ? (
                  <p className="fl-empty">No delivery exceptions recorded.</p>
                ) : (
                  <div className="fl-table-wrap">
                    <table className="fl-table">
                      <thead><tr><th>Invoice</th><th>Customer</th><th>Notes</th><th>Approved</th><th>Credit invoice</th></tr></thead>
                      <tbody>
                        {recentExceptions.map((exception, index) => (
                          <tr key={`${exception.invoice_number}-${exception.line_number}-${index}`}>
                            <td>{exception.invoice_number ?? 'Unavailable'}</td>
                            <td>{exception.customer_number ?? 'Unavailable'}</td>
                            <td>{exception.notes || '—'}</td>
                            <td>{exception.approved ? `Yes (${exception.approved_by || 'Unavailable'})` : 'No'}</td>
                            <td>{exception.credit_invoice_number ?? '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              <div className="fl-section-grid">
                <div className="fl-section">
                  <h4>Delivery adjustments</h4>
                  <p className="fl-section-note">{currentEvidence.adjustments.explanation}</p>
                  <p className="fl-total">{currentEvidence.adjustments.adjustment_count} adjustment(s) recorded.</p>
                </div>
                <div className="fl-section">
                  <h4>Signature-capture sessions</h4>
                  <p className="fl-section-note">{currentEvidence.signature_sessions.explanation}</p>
                  <p className="fl-total">{currentEvidence.signature_sessions.session_count} session(s) recorded.</p>
                </div>
                <div className="fl-section">
                  <h4>Proof-of-delivery images</h4>
                  <p className="fl-section-note">{currentEvidence.images.explanation}</p>
                  <p className="fl-total">{currentEvidence.images.image_count} image reference(s) recorded.</p>
                </div>
              </div>

              <div className="fl-gaps">
                <strong>What this evidence does not include</strong>
                <ul>
                  {currentEvidence.gaps.map((gap) => (
                    <li key={gap.code}><strong>{gap.label}:</strong> {gap.explanation}</li>
                  ))}
                </ul>
              </div>

              <div className="fl-notes">
                <h4>Logistics notes</h4>
                <p className="fl-section-note">Append-only. A note creates no ERP change, approval, or recommendation.</p>
                <form className="fl-note-form" onSubmit={submitNote}>
                  <label>Your name<input value={authorIdentity} onChange={(event) => setAuthorIdentity(event.target.value)} placeholder="Name" /></label>
                  <label>Note<textarea rows={3} value={noteText} onChange={(event) => setNoteText(event.target.value)} placeholder="What did you observe or confirm about this route?" /></label>
                  <button type="submit" disabled={noteSaveStatus === 'saving'}>{noteSaveStatus === 'saving' ? 'Saving…' : 'Save note'}</button>
                  {noteSaveMessage && (
                    <p className={noteSaveStatus === 'error' ? 'fl-form-error' : 'fl-form-success'}>{noteSaveMessage}</p>
                  )}
                </form>
                {notes && notes.count > 0 && (
                  <ul className="fl-note-list">
                    {notes.notes.map((note) => (
                      <li key={note.note_id}>
                        <div><strong>{note.author_identity}</strong><span>{formatDateTime(note.created_at)}</span></div>
                        <p>{note.note}</p>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
