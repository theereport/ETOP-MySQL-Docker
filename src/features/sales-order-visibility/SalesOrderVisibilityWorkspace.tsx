import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import {
  createInvoiceNote,
  getInvoiceEvidence,
  getInvoiceNotes,
  getSalesSummary,
  searchInvoices,
} from './api'
import type {
  InvoiceEvidenceResponse,
  InvoiceSearchResult,
  OrderNoteHistoryResponse,
  SalesSummaryResponse,
} from './types'
import './SalesOrderVisibilityWorkspace.css'

const money = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
})

const number0 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 })

function formatMoney(value: number | null | undefined): string {
  return value == null ? 'Unavailable' : money.format(value)
}

function formatNumber(value: number | null | undefined): string {
  return value == null ? 'Unavailable' : number0.format(value)
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

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

type DetailError = { invoiceNumber: number; message: string }
type WorkspaceTab = 'invoices' | 'sales-summary'

export default function SalesOrderVisibilityWorkspace() {
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('invoices')

  const [query, setQuery] = useState('')
  const [customerFilter, setCustomerFilter] = useState('')
  const [results, setResults] = useState<InvoiceSearchResult[]>([])
  const [searchError, setSearchError] = useState('')

  const [selectedInvoice, setSelectedInvoice] = useState<number | null>(null)
  const [evidence, setEvidence] = useState<InvoiceEvidenceResponse | null>(null)
  const [notes, setNotes] = useState<OrderNoteHistoryResponse | null>(null)
  const [detailError, setDetailError] = useState<DetailError | null>(null)

  const [authorIdentity, setAuthorIdentity] = useState('')
  const [noteText, setNoteText] = useState('')
  const [noteSaveStatus, setNoteSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [noteSaveMessage, setNoteSaveMessage] = useState('')

  const [summaryCustomer, setSummaryCustomer] = useState('')
  const [summaryProduct, setSummaryProduct] = useState('')
  const [summary, setSummary] = useState<SalesSummaryResponse | null>(null)
  const [summaryError, setSummaryError] = useState('')
  const [summaryLoading, setSummaryLoading] = useState(false)

  const currentEvidence =
    evidence && evidence.header.invoice_number === selectedInvoice ? evidence : null
  const currentDetailError =
    detailError && detailError.invoiceNumber === selectedInvoice ? detailError.message : ''
  const isLoadingDetail = selectedInvoice != null && !currentEvidence && !currentDetailError

  useEffect(() => {
    if (activeTab !== 'invoices') return
    const controller = new AbortController()
    searchInvoices(query, { customerNumber: customerFilter, signal: controller.signal })
      .then((response) => {
        setResults(response.invoices)
        setSearchError('')
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return
        setSearchError(errorMessage(error, 'Unable to search invoices.'))
      })
    return () => controller.abort()
  }, [query, customerFilter, activeTab])

  useEffect(() => {
    if (selectedInvoice == null) return
    const controller = new AbortController()
    const invoiceNumber = selectedInvoice
    Promise.all([
      getInvoiceEvidence(invoiceNumber, controller.signal),
      getInvoiceNotes(invoiceNumber, controller.signal),
    ])
      .then(([evidenceResponse, notesResponse]) => {
        setEvidence(evidenceResponse)
        setNotes(notesResponse)
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return
        setDetailError({
          invoiceNumber,
          message: errorMessage(error, 'Unable to load invoice evidence.'),
        })
      })
    return () => controller.abort()
  }, [selectedInvoice])

  const sortedDeliveryLines = useMemo(
    () => currentEvidence?.delivery.lines ?? [],
    [currentEvidence],
  )

  async function submitNote(event: FormEvent) {
    event.preventDefault()
    if (selectedInvoice == null) return
    if (!authorIdentity.trim() || !noteText.trim()) {
      setNoteSaveStatus('error')
      setNoteSaveMessage('Your name and a note are both required.')
      return
    }
    setNoteSaveStatus('saving')
    setNoteSaveMessage('')
    try {
      await createInvoiceNote(selectedInvoice, {
        author_identity: authorIdentity.trim(),
        note: noteText.trim(),
      })
      const refreshed = await getInvoiceNotes(selectedInvoice)
      setNotes(refreshed)
      setNoteText('')
      setNoteSaveStatus('success')
      setNoteSaveMessage('Note saved. It is append-only and creates no ERP change.')
    } catch (error) {
      setNoteSaveStatus('error')
      setNoteSaveMessage(errorMessage(error, 'Unable to save the note.'))
    }
  }

  async function runSalesSummary(event: FormEvent) {
    event.preventDefault()
    setSummaryLoading(true)
    setSummaryError('')
    try {
      const response = await getSalesSummary({
        customerNumber: summaryCustomer.trim() || undefined,
        productNumber: summaryProduct.trim() || undefined,
      })
      setSummary(response)
    } catch (error) {
      setSummaryError(errorMessage(error, 'Unable to load the sales summary.'))
    } finally {
      setSummaryLoading(false)
    }
  }

  return (
    <section className="sov-shell">
      <header className="sov-header">
        <div>
          <span className="sov-kicker">Read-only MaddenCo evidence · invoice-forward only</span>
          <h2>Sales Order Visibility</h2>
          <p>
            Invoice history, line items, memos, credit authorizations, and delivery cross-reference.
            MaddenCo has no open/pre-invoice order queue — this workspace never shows a live pending-order pipeline.
          </p>
        </div>
        <div className="sov-tabs">
          <button
            type="button"
            className={activeTab === 'invoices' ? 'sov-tab sov-tab--active' : 'sov-tab'}
            onClick={() => setActiveTab('invoices')}
          >
            Invoices
          </button>
          <button
            type="button"
            className={activeTab === 'sales-summary' ? 'sov-tab sov-tab--active' : 'sov-tab'}
            onClick={() => setActiveTab('sales-summary')}
          >
            Sales summary
          </button>
        </div>
      </header>

      {activeTab === 'invoices' && (
        <div className="sov-layout">
          <div className="sov-results">
            <div className="sov-search-controls">
              <label>
                Search
                <input
                  type="search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Invoice #, customer #, name, or PO"
                />
              </label>
              <label>
                Customer #
                <input
                  type="text"
                  value={customerFilter}
                  onChange={(event) => setCustomerFilter(event.target.value)}
                  placeholder="Filter by customer"
                />
              </label>
            </div>
            {searchError && <p className="sov-error">{searchError}</p>}
            {results.length === 0 ? (
              <p className="sov-empty">No invoices matched.</p>
            ) : (
              <ul className="sov-result-list">
                {results.map((invoice) => (
                  <li key={invoice.invoice_number}>
                    <button
                      type="button"
                      className={
                        invoice.invoice_number === selectedInvoice
                          ? 'sov-result sov-result--active'
                          : 'sov-result'
                      }
                      onClick={() => setSelectedInvoice(invoice.invoice_number)}
                    >
                      <strong>Invoice #{invoice.invoice_number}</strong>
                      <span>{invoice.customer_name || `Customer #${invoice.customer_number}`}</span>
                      <span>{formatDate(invoice.invoice_date)} · {formatMoney(invoice.total_amount)}</span>
                      {invoice.void && <em className="sov-tag sov-tag--void">Void</em>}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="sov-detail">
            {selectedInvoice == null && (
              <div className="sov-empty-state">
                <strong>Select an invoice to view evidence.</strong>
              </div>
            )}

            {isLoadingDetail && (
              <div className="sov-loading"><span className="sov-spinner" /> Loading invoice evidence…</div>
            )}

            {selectedInvoice != null && currentDetailError && (
              <div className="sov-message sov-message--error">
                <strong>Invoice evidence is unavailable.</strong>
                <span>{currentDetailError}</span>
              </div>
            )}

            {currentEvidence && (
              <div className="sov-evidence">
                <div className="sov-identity-card">
                  <div>
                    <h3>Invoice #{currentEvidence.header.invoice_number}</h3>
                    <span>
                      {currentEvidence.header.customer_name || `Customer #${currentEvidence.header.customer_number}`}
                      {' · '}
                      {currentEvidence.header.type_code === 'C' ? 'Credit' : 'Invoice'}
                      {currentEvidence.header.void ? ' · Void' : ''}
                    </span>
                  </div>
                  <dl>
                    <div><dt>Invoice date</dt><dd>{formatDate(currentEvidence.header.invoice_date)}</dd></div>
                    <div><dt>Due date</dt><dd>{formatDate(currentEvidence.header.due_date)}</dd></div>
                    <div><dt>PO number</dt><dd>{currentEvidence.header.po_number || 'Unavailable'}</dd></div>
                    <div><dt>Route</dt><dd>{currentEvidence.header.route_code || 'Unavailable'}</dd></div>
                    <div><dt>Store</dt><dd>{currentEvidence.header.store_number ?? 'Unavailable'}</dd></div>
                    <div><dt>Terms code</dt><dd>{currentEvidence.header.terms_code || 'Unavailable'}</dd></div>
                    <div><dt>Direct ship</dt><dd>{currentEvidence.header.direct_ship ? 'Yes' : 'No'}</dd></div>
                    <div><dt>Pickup</dt><dd>{currentEvidence.header.pickup ? 'Yes' : 'No'}</dd></div>
                    <div><dt>Ship to</dt><dd>{currentEvidence.header.ship_to_lines.join(', ') || 'Unavailable'} {currentEvidence.header.ship_to_zip}</dd></div>
                    <div><dt>Tracking #</dt><dd>{currentEvidence.header.tracking_number || 'Unavailable'}</dd></div>
                    {currentEvidence.header.hold_reason && (
                      <div><dt>Hold reason</dt><dd>{currentEvidence.header.hold_reason}</dd></div>
                    )}
                  </dl>
                </div>

                <div className="sov-metric-grid">
                  <article><span>Total amount</span><strong>{formatMoney(currentEvidence.header.total_amount)}</strong></article>
                  <article><span>Total units</span><strong>{formatNumber(currentEvidence.header.total_units)}</strong></article>
                  <article><span>Total discount</span><strong>{formatMoney(currentEvidence.header.total_discount)}</strong></article>
                  <article><span>Line count</span><strong>{currentEvidence.header.line_count ?? 'Unavailable'}</strong></article>
                </div>

                <div className="sov-section">
                  <h4>Line items</h4>
                  <p className="sov-section-note">{currentEvidence.lines.explanation}</p>
                  {currentEvidence.lines.lines.length === 0 ? (
                    <p className="sov-empty">No line items found.</p>
                  ) : (
                    <div className="sov-table-wrap">
                      <table className="sov-table">
                        <thead>
                          <tr>
                            <th>Line</th><th>Product</th><th>Qty</th><th>Unit price</th>
                            <th>Extended</th><th>Brand</th><th>Vehicle fit</th>
                          </tr>
                        </thead>
                        <tbody>
                          {currentEvidence.lines.lines.map((line) => (
                            <tr key={line.line_number}>
                              <td>{line.line_number}</td>
                              <td>{line.product_number}<br /><small>{line.product_description}</small></td>
                              <td>{formatNumber(line.quantity)}</td>
                              <td>{formatMoney(line.unit_price)}</td>
                              <td>{formatMoney(line.extended_price)}</td>
                              <td>{line.brand || 'Unavailable'}</td>
                              <td>
                                {line.vehicle_make || line.vehicle_model || line.vehicle_year
                                  ? `${line.vehicle_year ?? ''} ${line.vehicle_make} ${line.vehicle_model}`.trim()
                                  : 'Unavailable'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      <p className="sov-total">
                        Total extended: {formatMoney(currentEvidence.lines.total_extended_price)} across {currentEvidence.lines.line_count} line(s)
                      </p>
                    </div>
                  )}
                </div>

                <div className="sov-section">
                  <h4>Memos</h4>
                  {currentEvidence.memos.memos.length === 0 ? (
                    <p className="sov-empty">No memo lines found.</p>
                  ) : (
                    <ul className="sov-memo-list">
                      {currentEvidence.memos.memos.map((memo, index) => (
                        <li key={`${memo.line_number ?? 'h'}-${index}`}>
                          <div><strong>{memo.created_by || 'Unknown user'}</strong><span>{formatDate(memo.created_date)}</span></div>
                          <p>{memo.message}</p>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>

                <div className="sov-section">
                  <h4>Credit authorizations</h4>
                  <p className="sov-section-note">{currentEvidence.authorizations.explanation}</p>
                  {currentEvidence.authorizations.authorizations.length === 0 ? (
                    <p className="sov-empty">No authorization history found.</p>
                  ) : (
                    <div className="sov-table-wrap">
                      <table className="sov-table">
                        <thead><tr><th>Type</th><th>Amount</th><th>Requested</th><th>Authorized</th><th>Requested by</th><th>Authorized by</th></tr></thead>
                        <tbody>
                          {currentEvidence.authorizations.authorizations.map((auth, index) => (
                            <tr key={index}>
                              <td>{auth.authorization_type || 'Unavailable'}</td>
                              <td>{formatMoney(auth.amount_authorized)}</td>
                              <td>{formatDate(auth.date_requested)}</td>
                              <td>{formatDate(auth.date_authorized)}</td>
                              <td>{auth.requested_by || 'Unavailable'}</td>
                              <td>{auth.authorized_by || 'Unavailable'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>

                <div className="sov-section">
                  <h4>Delivery cross-reference</h4>
                  <p className="sov-section-note">{currentEvidence.delivery.explanation}</p>
                  {currentEvidence.delivery.manifest_status === 'no_records_found' ? (
                    <p className="sov-empty">No warehouse-load manifest rows found for this invoice.</p>
                  ) : (
                    <div className="sov-table-wrap">
                      <table className="sov-table">
                        <thead><tr><th>Route</th><th>Product</th><th>Qty</th><th>Created</th><th>Delivered</th></tr></thead>
                        <tbody>
                          {sortedDeliveryLines.map((line, index) => (
                            <tr key={index}>
                              <td>{line.route || 'Unavailable'}</td>
                              <td>{line.product_number}<br /><small>{line.description}</small></td>
                              <td>{formatNumber(line.quantity)}</td>
                              <td>{formatDateTime(line.created_at)}</td>
                              <td>{line.delivered ? formatDateTime(line.delivered_at) : 'Not yet delivered'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      <p className="sov-total">
                        {currentEvidence.delivery.delivered_line_count} of {currentEvidence.delivery.total_line_count} line(s) delivered
                      </p>
                    </div>
                  )}
                </div>

                <div className="sov-gaps">
                  <strong>What this evidence does not include</strong>
                  <ul>
                    {currentEvidence.gaps.map((gap) => (
                      <li key={gap.code}><strong>{gap.label}:</strong> {gap.explanation}</li>
                    ))}
                  </ul>
                </div>

                <div className="sov-notes">
                  <h4>Professional notes</h4>
                  <p className="sov-section-note">Append-only. A note creates no ERP change, approval, or recommendation.</p>
                  <form className="sov-note-form" onSubmit={submitNote}>
                    <label>Your name<input value={authorIdentity} onChange={(event) => setAuthorIdentity(event.target.value)} placeholder="Name" /></label>
                    <label>Note<textarea rows={3} value={noteText} onChange={(event) => setNoteText(event.target.value)} placeholder="What did you observe or confirm about this invoice?" /></label>
                    <button type="submit" disabled={noteSaveStatus === 'saving'}>{noteSaveStatus === 'saving' ? 'Saving…' : 'Save note'}</button>
                    {noteSaveMessage && (
                      <p className={noteSaveStatus === 'error' ? 'sov-form-error' : 'sov-form-success'}>{noteSaveMessage}</p>
                    )}
                  </form>
                  {notes && notes.count > 0 && (
                    <ul className="sov-note-list">
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
      )}

      {activeTab === 'sales-summary' && (
        <div className="sov-summary">
          <form className="sov-summary-form" onSubmit={runSalesSummary}>
            <label>
              Customer #
              <input
                value={summaryCustomer}
                onChange={(event) => setSummaryCustomer(event.target.value)}
                placeholder="Customer number"
              />
            </label>
            <label>
              Product #
              <input
                value={summaryProduct}
                onChange={(event) => setSummaryProduct(event.target.value)}
                placeholder="Product number"
              />
            </label>
            <button type="submit" disabled={summaryLoading}>
              {summaryLoading ? 'Loading…' : 'Run summary'}
            </button>
          </form>

          {summaryError && <p className="sov-error">{summaryError}</p>}

          {summary && (
            <div className="sov-section">
              <p className="sov-section-note">{summary.explanation}</p>
              <div className="sov-metric-grid">
                <article><span>Total sales</span><strong>{formatMoney(summary.total_sales)}</strong></article>
                <article><span>Total units</span><strong>{formatNumber(summary.total_units)}</strong></article>
                <article><span>Total actual cost</span><strong>{formatMoney(summary.total_actual_cost)}</strong></article>
                <article><span>Rows</span><strong>{summary.row_count}</strong></article>
              </div>
              {summary.rows.length === 0 ? (
                <p className="sov-empty">No sales-summary rows matched.</p>
              ) : (
                <div className="sov-table-wrap">
                  <table className="sov-table">
                    <thead>
                      <tr>
                        <th>Customer</th><th>Product</th><th>Class</th><th>Type</th>
                        <th>Sales</th><th>Units</th><th>Actual cost</th><th>Period</th>
                      </tr>
                    </thead>
                    <tbody>
                      {summary.rows.map((row, index) => (
                        <tr key={index}>
                          <td>{row.customer_number ?? 'Unavailable'}</td>
                          <td>{row.product_number || 'Unavailable'}</td>
                          <td>{row.product_class || 'Unavailable'}</td>
                          <td>{row.product_type || 'Unavailable'}</td>
                          <td>{formatMoney(row.sales)}</td>
                          <td>{formatNumber(row.units)}</td>
                          <td>{formatMoney(row.actual_cost)}</td>
                          <td>{row.year_period ?? 'Unavailable'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </section>
  )
}
