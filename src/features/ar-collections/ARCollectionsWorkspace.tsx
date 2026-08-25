import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  createCustomerNote,
  getCustomerCollections,
  getCustomerNotes,
} from './api'
import type {
  ARCollectionsNoteHistoryResponse,
  CustomerARCollectionsResponse,
} from './types'
import './ARCollectionsWorkspace.css'

const money = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
})

function formatMoney(value: number | null | undefined): string {
  return value == null ? 'Unavailable' : money.format(value)
}

function formatDate(value: string | null | undefined): string {
  if (!value) return 'Unavailable'
  const date = new Date(`${value}T00:00:00`)
  return Number.isNaN(date.valueOf())
    ? value
    : date.toLocaleDateString('en-US', { dateStyle: 'medium' })
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return 'Unavailable'
  const date = new Date(value)
  return Number.isNaN(date.valueOf())
    ? value
    : date.toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })
}

function formatDaysPastDue(value: number | null | undefined): string {
  if (value == null) return 'Unavailable'
  if (value > 0) return `${value} day${value === 1 ? '' : 's'} past due`
  if (value < 0) return `Due in ${Math.abs(value)} day${Math.abs(value) === 1 ? '' : 's'}`
  return 'Due today'
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

export default function ARCollectionsWorkspace() {
  const [customerInput, setCustomerInput] = useState('')
  const [selectedCustomer, setSelectedCustomer] = useState<number | null>(null)

  const [evidence, setEvidence] = useState<CustomerARCollectionsResponse | null>(null)
  const [notes, setNotes] = useState<ARCollectionsNoteHistoryResponse | null>(null)
  const [detailError, setDetailError] = useState<{ customerNumber: number; message: string } | null>(null)

  const [authorIdentity, setAuthorIdentity] = useState('')
  const [noteText, setNoteText] = useState('')
  const [noteSaveStatus, setNoteSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [noteSaveMessage, setNoteSaveMessage] = useState('')

  // Evidence/errors are tagged with the customer they belong to, so switching
  // the selected customer never needs a synchronous "clear" setState call
  // inside an effect — stale data for a different customer is simply ignored.
  const currentEvidence =
    evidence && evidence.customer.customer_number === selectedCustomer ? evidence : null
  const currentDetailError =
    detailError && detailError.customerNumber === selectedCustomer ? detailError.message : ''
  const isLoadingDetail = selectedCustomer != null && !currentEvidence && !currentDetailError

  useEffect(() => {
    if (selectedCustomer == null) return
    const controller = new AbortController()
    const customerNumber = selectedCustomer
    Promise.all([
      getCustomerCollections(customerNumber, controller.signal),
      getCustomerNotes(customerNumber, controller.signal),
    ])
      .then(([evidenceResponse, notesResponse]) => {
        setEvidence(evidenceResponse)
        setNotes(notesResponse)
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return
        setDetailError({
          customerNumber,
          message: errorMessage(error, 'Unable to load AR collections evidence.'),
        })
      })
    return () => controller.abort()
  }, [selectedCustomer])

  function submitCustomerSearch(event: FormEvent) {
    event.preventDefault()
    const parsed = Number.parseInt(customerInput.trim(), 10)
    if (!Number.isFinite(parsed) || parsed <= 0) return
    setSelectedCustomer(parsed)
  }

  async function submitNote(event: FormEvent) {
    event.preventDefault()
    if (selectedCustomer == null) return
    if (!authorIdentity.trim() || !noteText.trim()) {
      setNoteSaveStatus('error')
      setNoteSaveMessage('Your name and a note are both required.')
      return
    }
    setNoteSaveStatus('saving')
    setNoteSaveMessage('')
    try {
      await createCustomerNote(selectedCustomer, {
        author_identity: authorIdentity.trim(),
        note: noteText.trim(),
      })
      const refreshed = await getCustomerNotes(selectedCustomer)
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
    <section className="arc-shell">
      <header className="arc-header">
        <div>
          <span className="arc-kicker">Read-only MaddenCo evidence</span>
          <h2>AR Collections</h2>
          <p>Itemized open A/R, payment history, GL reference, aging trend, and ERP notes — no priority score, dunning cadence, or ERP write.</p>
        </div>
        <form className="arc-search" onSubmit={submitCustomerSearch}>
          Customer number
          <div className="arc-search-row">
            <input
              type="text"
              inputMode="numeric"
              value={customerInput}
              onChange={(event) => setCustomerInput(event.target.value)}
              placeholder="e.g. 555000"
            />
            <button type="submit">Load</button>
          </div>
        </form>
      </header>

      <div className="arc-layout">
        {selectedCustomer == null && (
          <div className="arc-empty-state">
            <strong>Enter a customer number to view AR collections evidence.</strong>
          </div>
        )}

        {isLoadingDetail && (
          <div className="arc-loading"><span className="arc-spinner" /> Loading AR collections evidence…</div>
        )}

        {selectedCustomer != null && currentDetailError && (
          <div className="arc-message arc-message--error">
            <strong>AR collections evidence is unavailable.</strong>
            <span>{currentDetailError}</span>
          </div>
        )}

        {currentEvidence && (
          <div className="arc-evidence">
            <div className="arc-identity-card">
              <div>
                <h3>{currentEvidence.customer.customer_name}</h3>
                <span>Customer #{currentEvidence.customer.customer_number} · {currentEvidence.customer.active ? 'Active' : 'Inactive'}</span>
              </div>
              <dl>
                <div><dt>Phone</dt><dd>{currentEvidence.customer.phone || 'Unavailable'}</dd></div>
                <div><dt>Email</dt><dd>{currentEvidence.customer.email || 'Unavailable'}</dd></div>
                <div><dt>Address</dt><dd>{currentEvidence.customer.address_lines.join(', ') || 'Unavailable'} {currentEvidence.customer.zip_code}</dd></div>
                <div><dt>Route</dt><dd>{currentEvidence.customer.route_code || 'Unavailable'}</dd></div>
              </dl>
            </div>

            <div className="arc-metric-grid">
              <article><span>Open A/R total</span><strong>{formatMoney(currentEvidence.open_ar.total_open_amount)}</strong><small>{currentEvidence.open_ar.item_count} item(s)</small></article>
              <article><span>GL debit total</span><strong>{formatMoney(currentEvidence.gl_distributions.total_debit_amount)}</strong></article>
              <article><span>GL credit total</span><strong>{formatMoney(currentEvidence.gl_distributions.total_credit_amount)}</strong></article>
              <article><span>Transactions</span><strong>{currentEvidence.transactions.transaction_count}</strong><small>{currentEvidence.transactions.application_count} application(s)</small></article>
            </div>

            <div className="arc-section">
              <h4>Open A/R items</h4>
              <p className="arc-section-note">{currentEvidence.open_ar.explanation}</p>
              {currentEvidence.open_ar.open_items.length === 0 ? (
                <p className="arc-empty">No open A/R items.</p>
              ) : (
                <div className="arc-table-wrap">
                  <table className="arc-table">
                    <thead><tr><th>Invoice</th><th>Type</th><th>D/C</th><th>Original</th><th>Open</th><th>Due date</th><th>Days past due</th><th>Adj. reason</th></tr></thead>
                    <tbody>
                      {currentEvidence.open_ar.open_items.map((item, index) => (
                        <tr key={`${item.invoice_number}-${index}`}>
                          <td>{item.invoice_number}</td>
                          <td>{item.transaction_type || 'Unavailable'}</td>
                          <td>{item.debit_credit || 'Unavailable'}</td>
                          <td>{formatMoney(item.original_amount)}</td>
                          <td>{formatMoney(item.open_amount)}</td>
                          <td>{formatDate(item.due_date)}</td>
                          <td>{formatDaysPastDue(item.days_past_due)}</td>
                          <td>{item.adjustment_reason || 'Unavailable'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="arc-section">
              <h4>Item history (closed/paid)</h4>
              <p className="arc-section-note">{currentEvidence.item_history.explanation}</p>
              {currentEvidence.item_history.items.length === 0 ? (
                <p className="arc-empty">No closed AR item history found.</p>
              ) : (
                <div className="arc-table-wrap">
                  <table className="arc-table">
                    <thead><tr><th>Invoice</th><th>Type</th><th>D/C</th><th>Original</th><th>Transaction date</th><th>Adj. reason</th></tr></thead>
                    <tbody>
                      {currentEvidence.item_history.items.map((item, index) => (
                        <tr key={`${item.invoice_number}-${index}`}>
                          <td>{item.invoice_number}</td>
                          <td>{item.transaction_type || 'Unavailable'}</td>
                          <td>{item.debit_credit || 'Unavailable'}</td>
                          <td>{formatMoney(item.original_amount)}</td>
                          <td>{formatDate(item.transaction_date)}</td>
                          <td>{item.adjustment_reason || 'Unavailable'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="arc-section">
              <h4>AR transaction history</h4>
              <p className="arc-section-note">{currentEvidence.transactions.explanation}</p>
              {currentEvidence.transactions.transactions.length === 0 ? (
                <p className="arc-empty">No AR transaction history found.</p>
              ) : (
                <div className="arc-table-wrap">
                  <table className="arc-table">
                    <thead><tr><th>Invoice</th><th>Date</th><th>Type</th><th>D/C</th><th>Amount</th><th>Status</th><th>Reference</th></tr></thead>
                    <tbody>
                      {currentEvidence.transactions.transactions.map((transaction) => (
                        <tr key={transaction.sequence}>
                          <td>{transaction.invoice_number}</td>
                          <td>{formatDate(transaction.transaction_date)}</td>
                          <td>{transaction.transaction_type || 'Unavailable'}</td>
                          <td>{transaction.debit_credit || 'Unavailable'}</td>
                          <td>{formatMoney(transaction.original_amount)}</td>
                          <td>{transaction.status || 'Unavailable'}</td>
                          <td>{transaction.reference_number || 'Unavailable'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {currentEvidence.transactions.applications.length > 0 && (
                <div className="arc-table-wrap arc-table-wrap--spaced">
                  <table className="arc-table">
                    <thead><tr><th>Applied to invoice</th><th>Amount applied</th><th>Discount applied</th><th>GL account</th><th>Created</th></tr></thead>
                    <tbody>
                      {currentEvidence.transactions.applications.map((application, index) => (
                        <tr key={`${application.header_sequence}-${application.detail_sequence}-${index}`}>
                          <td>{application.applied_invoice_number}</td>
                          <td>{formatMoney(application.amount_applied)}</td>
                          <td>{formatMoney(application.discount_applied)}</td>
                          <td>{application.gl_account ?? 'Unavailable'}</td>
                          <td>{formatDate(application.created_date)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="arc-section">
              <h4>GL distribution lines</h4>
              <p className="arc-section-note">{currentEvidence.gl_distributions.explanation}</p>
              {currentEvidence.gl_distributions.lines.length === 0 ? (
                <p className="arc-empty">No GL distribution lines found.</p>
              ) : (
                <div className="arc-table-wrap">
                  <table className="arc-table">
                    <thead><tr><th>Account</th><th>Division</th><th>Department</th><th>Debit</th><th>Credit</th><th>Description</th><th>Created</th></tr></thead>
                    <tbody>
                      {currentEvidence.gl_distributions.lines.map((line, index) => (
                        <tr key={index}>
                          <td>{line.gl_account ?? 'Unavailable'}</td>
                          <td>{line.gl_division ?? 'Unavailable'}</td>
                          <td>{line.gl_department ?? 'Unavailable'}</td>
                          <td>{formatMoney(line.debit_amount)}</td>
                          <td>{formatMoney(line.credit_amount)}</td>
                          <td>{line.description || 'Unavailable'}</td>
                          <td>{formatDate(line.created_date)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="arc-section">
              <h4>Aging / credit history trend</h4>
              <p className="arc-section-note">{currentEvidence.aging_history.explanation}</p>
              {currentEvidence.aging_history.snapshots.length === 0 ? (
                <p className="arc-empty">No aging snapshots found.</p>
              ) : (
                <div className="arc-table-wrap">
                  <table className="arc-table">
                    <thead><tr><th>Date</th><th>Future</th><th>Current</th><th>30</th><th>60</th><th>90</th><th>120+</th><th>Balance</th><th>Credit limit</th></tr></thead>
                    <tbody>
                      {currentEvidence.aging_history.snapshots.map((snapshot, index) => (
                        <tr key={index}>
                          <td>{formatDate(snapshot.snapshot_date)}</td>
                          <td>{formatMoney(snapshot.aging_future)}</td>
                          <td>{formatMoney(snapshot.aging_current)}</td>
                          <td>{formatMoney(snapshot.aging_30)}</td>
                          <td>{formatMoney(snapshot.aging_60)}</td>
                          <td>{formatMoney(snapshot.aging_90)}</td>
                          <td>{formatMoney(snapshot.aging_120)}</td>
                          <td>{formatMoney(snapshot.balance)}</td>
                          <td>{formatMoney(snapshot.credit_limit)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="arc-section">
              <h4>ERP collection notes</h4>
              <p className="arc-section-note">{currentEvidence.erp_collection_notes.explanation}</p>
              {currentEvidence.erp_collection_notes.notes.length === 0 ? (
                <p className="arc-empty">No ERP collection notes found.</p>
              ) : (
                <ul className="arc-erp-note-list">
                  {currentEvidence.erp_collection_notes.notes.map((note, index) => (
                    <li key={index}>
                      <div><strong>{note.created_by || 'Unknown'}</strong><span>{formatDateTime(note.created_at)}</span></div>
                      <p>{note.note_text}</p>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="arc-section">
              <h4>ERP credit-management notes</h4>
              <p className="arc-section-note">{currentEvidence.erp_credit_management_notes.explanation}</p>
              {currentEvidence.erp_credit_management_notes.notes.length === 0 ? (
                <p className="arc-empty">No ERP credit-management notes found.</p>
              ) : (
                <ul className="arc-erp-note-list">
                  {currentEvidence.erp_credit_management_notes.notes.map((note) => (
                    <li key={note.header_key}>
                      <div><strong>{note.regarding || 'Untitled'}</strong><span>{formatDate(note.created_at)} · to do {formatDate(note.date_to_do)}</span></div>
                      {note.detail_lines.length > 0 && (
                        <ul className="arc-erp-note-detail">
                          {note.detail_lines.map((line, index) => (
                            <li key={index}>{line}</li>
                          ))}
                        </ul>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="arc-gaps">
              <strong>What this evidence does not include</strong>
              <ul>
                {currentEvidence.gaps.map((gap) => (
                  <li key={gap.code}><strong>{gap.label}:</strong> {gap.explanation}</li>
                ))}
              </ul>
            </div>

            <div className="arc-notes">
              <h4>Professional collections notes</h4>
              <p className="arc-section-note">Append-only. A note creates no ERP change, hold, or recommendation.</p>
              <form className="arc-note-form" onSubmit={submitNote}>
                <label>Your name<input value={authorIdentity} onChange={(event) => setAuthorIdentity(event.target.value)} placeholder="Name" /></label>
                <label>Note<textarea rows={3} value={noteText} onChange={(event) => setNoteText(event.target.value)} placeholder="What did you observe or confirm about this customer's collections status?" /></label>
                <button type="submit" disabled={noteSaveStatus === 'saving'}>{noteSaveStatus === 'saving' ? 'Saving…' : 'Save note'}</button>
                {noteSaveMessage && (
                  <p className={noteSaveStatus === 'error' ? 'arc-form-error' : 'arc-form-success'}>{noteSaveMessage}</p>
                )}
              </form>
              {notes && notes.count > 0 && (
                <ul className="arc-note-list">
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
    </section>
  )
}
