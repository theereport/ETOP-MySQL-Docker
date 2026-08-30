import { Fragment, useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import {
  createVendorNote,
  getVendorEvidence,
  getVendorInvoiceGLDistributions,
  getVendorNotes,
  searchVendors,
} from './api'
import type {
  GLDistributionLine,
  VendorEvidenceResponse,
  VendorNoteHistoryResponse,
  VendorSearchResult,
} from './types'
import './VendorIntelligenceWorkspace.css'

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

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

type DetailError = { vendorNumber: number; message: string }

export default function VendorIntelligenceWorkspace() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<VendorSearchResult[]>([])
  const [searchError, setSearchError] = useState('')

  const [selectedVendor, setSelectedVendor] = useState<number | null>(null)
  const [evidence, setEvidence] = useState<VendorEvidenceResponse | null>(null)
  const [notes, setNotes] = useState<VendorNoteHistoryResponse | null>(null)
  const [detailError, setDetailError] = useState<DetailError | null>(null)

  const [expandedInvoice, setExpandedInvoice] = useState<string | null>(null)
  const [glDistributions, setGLDistributions] = useState<Record<string, {
    status: 'loading' | 'success' | 'error'
    lines: GLDistributionLine[]
    error: string
  }>>({})

  const [authorIdentity, setAuthorIdentity] = useState('')
  const [noteText, setNoteText] = useState('')
  const [noteSaveStatus, setNoteSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [noteSaveMessage, setNoteSaveMessage] = useState('')

  // Evidence/errors are tagged with the vendor they belong to, so switching
  // the selected vendor never needs a synchronous "clear" setState call
  // inside an effect — stale data for a different vendor is simply ignored.
  const currentEvidence =
    evidence && evidence.identity.vendor_number === selectedVendor ? evidence : null
  const currentDetailError =
    detailError && detailError.vendorNumber === selectedVendor ? detailError.message : ''
  const isLoadingDetail = selectedVendor != null && !currentEvidence && !currentDetailError

  useEffect(() => {
    const controller = new AbortController()
    searchVendors(query, controller.signal)
      .then((response) => {
        setResults(response.vendors)
        setSearchError('')
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return
        setSearchError(errorMessage(error, 'Unable to search vendors.'))
      })
    return () => controller.abort()
  }, [query])

  useEffect(() => {
    if (selectedVendor == null) return
    const controller = new AbortController()
    const vendorNumber = selectedVendor
    Promise.all([
      getVendorEvidence(vendorNumber, controller.signal),
      getVendorNotes(vendorNumber, controller.signal),
    ])
      .then(([evidenceResponse, notesResponse]) => {
        setEvidence(evidenceResponse)
        setNotes(notesResponse)
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return
        setDetailError({
          vendorNumber,
          message: errorMessage(error, 'Unable to load vendor evidence.'),
        })
      })
    return () => controller.abort()
  }, [selectedVendor])

  const sortedReceipts = useMemo(
    () => currentEvidence?.receiving.recent_receipts.slice(0, 10) ?? [],
    [currentEvidence],
  )

  function toggleGLDistributions(invoiceNumber: string) {
    if (expandedInvoice === invoiceNumber) {
      setExpandedInvoice(null)
      return
    }
    setExpandedInvoice(invoiceNumber)
    if (glDistributions[invoiceNumber] || selectedVendor == null) return
    setGLDistributions((current) => ({
      ...current,
      [invoiceNumber]: { status: 'loading', lines: [], error: '' },
    }))
    getVendorInvoiceGLDistributions(selectedVendor, invoiceNumber)
      .then((lines) => {
        setGLDistributions((current) => ({
          ...current,
          [invoiceNumber]: { status: 'success', lines, error: '' },
        }))
      })
      .catch((error: unknown) => {
        setGLDistributions((current) => ({
          ...current,
          [invoiceNumber]: {
            status: 'error',
            lines: [],
            error: errorMessage(error, 'Unable to load GL posting evidence.'),
          },
        }))
      })
  }

  async function submitNote(event: FormEvent) {
    event.preventDefault()
    if (selectedVendor == null) return
    if (!authorIdentity.trim() || !noteText.trim()) {
      setNoteSaveStatus('error')
      setNoteSaveMessage('Your name and a note are both required.')
      return
    }
    setNoteSaveStatus('saving')
    setNoteSaveMessage('')
    try {
      await createVendorNote(selectedVendor, {
        author_identity: authorIdentity.trim(),
        note: noteText.trim(),
      })
      const refreshed = await getVendorNotes(selectedVendor)
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
    <section className="vi-shell">
      <header className="vi-header">
        <div>
          <span className="vi-kicker">Read-only MaddenCo evidence</span>
          <h2>Vendor Intelligence</h2>
          <p>Vendor identity, purchase orders, receiving, and payables — no automatic score, rank, or ERP write.</p>
        </div>
        <label className="vi-search">
          Search vendors
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Vendor name, number, phone, or email"
          />
        </label>
      </header>

      <div className="vi-layout">
        <div className="vi-results">
          {searchError && <p className="vi-error">{searchError}</p>}
          {results.length === 0 ? (
            <p className="vi-empty">No vendors matched.</p>
          ) : (
            <ul className="vi-result-list">
              {results.map((vendor) => (
                <li key={vendor.vendor_number}>
                  <button
                    type="button"
                    className={vendor.vendor_number === selectedVendor ? 'vi-result vi-result--active' : 'vi-result'}
                    onClick={() => setSelectedVendor(vendor.vendor_number)}
                  >
                    <strong>{vendor.vendor_name || 'Unnamed vendor'}</strong>
                    <span>#{vendor.vendor_number}</span>
                    {!vendor.active && <em className="vi-tag vi-tag--inactive">Inactive</em>}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="vi-detail">
          {selectedVendor == null && (
            <div className="vi-empty-state">
              <strong>Select a vendor to view evidence.</strong>
            </div>
          )}

          {isLoadingDetail && (
            <div className="vi-loading"><span className="vi-spinner" /> Loading vendor evidence…</div>
          )}

          {selectedVendor != null && currentDetailError && (
            <div className="vi-message vi-message--error">
              <strong>Vendor evidence is unavailable.</strong>
              <span>{currentDetailError}</span>
            </div>
          )}

          {currentEvidence && (
            <div className="vi-evidence">
              <div className="vi-identity-card">
                <div>
                  <h3>{currentEvidence.identity.vendor_name}</h3>
                  <span>Vendor #{currentEvidence.identity.vendor_number} · {currentEvidence.identity.active ? 'Active' : 'Inactive'}</span>
                </div>
                <dl>
                  <div><dt>Contact</dt><dd>{currentEvidence.identity.contact_name || 'Unavailable'}</dd></div>
                  <div><dt>Phone</dt><dd>{currentEvidence.identity.phone || 'Unavailable'}</dd></div>
                  <div><dt>Email</dt><dd>{currentEvidence.identity.email || 'Unavailable'}</dd></div>
                  <div><dt>Address</dt><dd>{currentEvidence.identity.address_lines.join(', ') || 'Unavailable'} {currentEvidence.identity.zip_code}</dd></div>
                  <div><dt>Terms code</dt><dd>{currentEvidence.identity.terms_code || 'Unavailable'}</dd></div>
                  <div><dt>PO required</dt><dd>{currentEvidence.identity.po_required ? 'Yes' : 'No'}</dd></div>
                  <div><dt>1099 vendor</dt><dd>{currentEvidence.identity.is_1099 ? `Yes (${currentEvidence.identity.tax_1099_code || 'code unavailable'})` : 'No'}</dd></div>
                  <div><dt>Federal ID on file</dt><dd>{currentEvidence.identity.federal_id_on_file ? 'Yes' : 'No'}</dd></div>
                  <div><dt>Payment type</dt><dd>{currentEvidence.identity.payment_type || 'Unavailable'}</dd></div>
                  <div><dt>EFT/bank info on file</dt><dd>{currentEvidence.identity.eft_bank_info_on_file ? 'Yes' : 'No'}</dd></div>
                </dl>
              </div>

              <div className="vi-metric-grid">
                <article><span>YTD purchases</span><strong>{formatMoney(currentEvidence.purchase_volume.year_to_date)}</strong></article>
                <article><span>MTD purchases</span><strong>{formatMoney(currentEvidence.purchase_volume.month_to_date)}</strong></article>
                <article><span>Last year purchases</span><strong>{formatMoney(currentEvidence.purchase_volume.last_year)}</strong></article>
                <article><span>Amount last paid</span><strong>{formatMoney(currentEvidence.purchase_volume.amount_last_paid)}</strong><small>{formatDate(currentEvidence.purchase_volume.date_last_paid)}</small></article>
              </div>

              <div className="vi-section">
                <h4>Discount capture</h4>
                <p className="vi-section-note">{currentEvidence.purchase_volume.discount_explanation}</p>
                <div className="vi-metric-grid">
                  <article>
                    <span>YTD discount taken</span>
                    <strong>{formatMoney(currentEvidence.purchase_volume.discount_year_to_date)}</strong>
                  </article>
                  <article>
                    <span>YTD discount lost</span>
                    <strong>{formatMoney(currentEvidence.purchase_volume.discount_lost_year_to_date)}</strong>
                  </article>
                  <article>
                    <span>YTD capture rate</span>
                    <strong>
                      {currentEvidence.purchase_volume.discount_capture_rate_year_to_date.value == null
                        ? 'Unavailable'
                        : `${currentEvidence.purchase_volume.discount_capture_rate_year_to_date.value}%`}
                    </strong>
                  </article>
                  <article>
                    <span>MTD capture rate</span>
                    <strong>
                      {currentEvidence.purchase_volume.discount_capture_rate_month_to_date.value == null
                        ? 'Unavailable'
                        : `${currentEvidence.purchase_volume.discount_capture_rate_month_to_date.value}%`}
                    </strong>
                  </article>
                </div>
              </div>

              <div className="vi-section">
                <h4>Open purchase orders</h4>
                <p className="vi-section-note">{currentEvidence.purchase_orders.explanation}</p>
                {currentEvidence.purchase_orders.open_orders.length === 0 ? (
                  <p className="vi-empty">No open purchase orders.</p>
                ) : (
                  <div className="vi-table-wrap">
                    <table className="vi-table">
                      <thead><tr><th>PO #</th><th>Date</th><th>Ship via</th><th>Total cost</th><th>Ordered</th><th>Received</th><th>Backorder</th></tr></thead>
                      <tbody>
                        {currentEvidence.purchase_orders.open_orders.map((po) => (
                          <tr key={po.po_number}>
                            <td>{po.po_number}</td>
                            <td>{formatDate(po.po_date)}</td>
                            <td>{po.ship_via || 'Unavailable'}</td>
                            <td>{formatMoney(po.total_cost)}</td>
                            <td>{po.ordered_quantity}</td>
                            <td>{po.received_quantity}</td>
                            <td>{po.backorder_quantity}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <p className="vi-total">Total open cost: {formatMoney(currentEvidence.purchase_orders.open_order_total_cost)} across {currentEvidence.purchase_orders.open_order_count} order(s)</p>
                  </div>
                )}
              </div>

              <div className="vi-section">
                <h4>Recent receiving</h4>
                <p className="vi-section-note">{currentEvidence.receiving.explanation} Cost-variance coverage: {currentEvidence.receiving.cost_variance_completeness}.</p>
                {sortedReceipts.length === 0 ? (
                  <p className="vi-empty">No receiving history found.</p>
                ) : (
                  <div className="vi-table-wrap">
                    <table className="vi-table">
                      <thead><tr><th>PO #</th><th>Product</th><th>Qty</th><th>Actual cost</th><th>PO cost</th><th>Variance</th><th>Received</th></tr></thead>
                      <tbody>
                        {sortedReceipts.map((receipt, index) => (
                          <tr key={`${receipt.po_number}-${receipt.product_number}-${index}`}>
                            <td>{receipt.po_number}</td>
                            <td>{receipt.product_number}<br /><small>{receipt.product_description}</small></td>
                            <td>{receipt.quantity}</td>
                            <td>{formatMoney(receipt.actual_cost)}</td>
                            <td>{formatMoney(receipt.po_cost)}</td>
                            <td>{formatMoney(receipt.cost_variance)}</td>
                            <td>{formatDate(receipt.received_date)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              <div className="vi-section">
                <h4>Payables</h4>
                <p className="vi-section-note">Open total: {formatMoney(currentEvidence.payables.open_invoice_total)} across {currentEvidence.payables.open_invoice_count} invoice(s).</p>
                {currentEvidence.payables.open_invoices.length === 0 ? (
                  <p className="vi-empty">No open payable invoices.</p>
                ) : (
                  <div className="vi-table-wrap">
                    <table className="vi-table">
                      <thead><tr><th /><th>Invoice</th><th>Amount</th><th>Invoice date</th><th>Due date</th><th>Hold</th></tr></thead>
                      <tbody>
                        {currentEvidence.payables.open_invoices.map((invoice) => {
                          const isExpanded = expandedInvoice === invoice.invoice_number
                          const gl = glDistributions[invoice.invoice_number]
                          return (
                            <Fragment key={invoice.invoice_number}>
                              <tr>
                                <td>
                                  <button
                                    type="button"
                                    className="vi-gl-toggle"
                                    aria-expanded={isExpanded}
                                    onClick={() => toggleGLDistributions(invoice.invoice_number)}
                                  >
                                    {isExpanded ? '▾' : '▸'} GL
                                  </button>
                                </td>
                                <td>{invoice.invoice_number}</td>
                                <td>{formatMoney(invoice.invoice_amount)}</td>
                                <td>{formatDate(invoice.invoice_date)}</td>
                                <td>{formatDate(invoice.due_date)}</td>
                                <td>{invoice.on_hold ? 'Yes' : 'No'}</td>
                              </tr>
                              {isExpanded && (
                                <tr className="vi-gl-row">
                                  <td colSpan={6}>
                                    {(!gl || gl.status === 'loading') && (
                                      <p className="vi-empty">Loading GL posting evidence…</p>
                                    )}
                                    {gl?.status === 'error' && <p className="vi-form-error">{gl.error}</p>}
                                    {gl?.status === 'success' && (
                                      gl.lines.length === 0 ? (
                                        <p className="vi-empty">No GL distribution evidence found for this invoice.</p>
                                      ) : (
                                        <table className="vi-table vi-gl-table">
                                          <thead>
                                            <tr>
                                              <th>GL account</th>
                                              <th>Division</th>
                                              <th>Department</th>
                                              <th>Line memo</th>
                                              <th>Quantity</th>
                                              <th>Amount</th>
                                              <th>Period/Year</th>
                                            </tr>
                                          </thead>
                                          <tbody>
                                            {gl.lines.map((line, index) => (
                                              <tr key={`${line.sequence_number ?? index}`}>
                                                <td>
                                                  {line.gl_account ?? 'Unavailable'}
                                                  {line.gl_account_description && (
                                                    <><br /><small>{line.gl_account_description}</small></>
                                                  )}
                                                </td>
                                                <td>{line.gl_division ?? 'Unavailable'}</td>
                                                <td>{line.gl_department ?? 'Unavailable'}</td>
                                                <td>{line.description || '—'}</td>
                                                <td>{line.quantity ?? 'Unavailable'}</td>
                                                <td>{formatMoney(line.invoice_amount)}</td>
                                                <td>{line.accounting_period ?? '—'}/{line.accounting_year ?? '—'}</td>
                                              </tr>
                                            ))}
                                          </tbody>
                                        </table>
                                      )
                                    )}
                                  </td>
                                </tr>
                              )}
                            </Fragment>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              <div className="vi-gaps">
                <strong>What this evidence does not include</strong>
                <ul>
                  {currentEvidence.gaps.map((gap) => (
                    <li key={gap.code}><strong>{gap.label}:</strong> {gap.explanation}</li>
                  ))}
                </ul>
              </div>

              <div className="vi-notes">
                <h4>Professional notes</h4>
                <p className="vi-section-note">Append-only. A note creates no ERP change, approval, or recommendation.</p>
                <form className="vi-note-form" onSubmit={submitNote}>
                  <label>Your name<input value={authorIdentity} onChange={(event) => setAuthorIdentity(event.target.value)} placeholder="Name" /></label>
                  <label>Note<textarea rows={3} value={noteText} onChange={(event) => setNoteText(event.target.value)} placeholder="What did you observe or confirm about this vendor?" /></label>
                  <button type="submit" disabled={noteSaveStatus === 'saving'}>{noteSaveStatus === 'saving' ? 'Saving…' : 'Save note'}</button>
                  {noteSaveMessage && (
                    <p className={noteSaveStatus === 'error' ? 'vi-form-error' : 'vi-form-success'}>{noteSaveMessage}</p>
                  )}
                </form>
                {notes && notes.count > 0 && (
                  <ul className="vi-note-list">
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
