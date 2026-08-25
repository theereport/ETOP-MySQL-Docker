import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import {
  createProductNote,
  getProductEvidence,
  getProductNotes,
  searchProducts,
} from './api'
import type {
  InventoryNoteHistoryResponse,
  ProductEvidenceResponse,
  ProductSearchResult,
} from './types'
import './InventoryPurchasingWorkspace.css'

const money = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
})

function formatMoney(value: number | null | undefined): string {
  return value == null ? 'Unavailable' : money.format(value)
}

function formatNumber(value: number | null | undefined): string {
  return value == null ? 'Unavailable' : value.toLocaleString('en-US')
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

function formatPeriod(month: number | null, year: number | null): string {
  if (!month || !year) return 'Unavailable'
  return `${String(month).padStart(2, '0')}/${year}`
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

type DetailError = { productNumber: string; message: string }

export default function InventoryPurchasingWorkspace() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<ProductSearchResult[]>([])
  const [searchError, setSearchError] = useState('')

  const [selectedProduct, setSelectedProduct] = useState<string | null>(null)
  const [evidence, setEvidence] = useState<ProductEvidenceResponse | null>(null)
  const [notes, setNotes] = useState<InventoryNoteHistoryResponse | null>(null)
  const [detailError, setDetailError] = useState<DetailError | null>(null)

  const [authorIdentity, setAuthorIdentity] = useState('')
  const [noteText, setNoteText] = useState('')
  const [noteSaveStatus, setNoteSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [noteSaveMessage, setNoteSaveMessage] = useState('')

  // Evidence/errors are tagged with the product they belong to, so switching
  // the selected product never needs a synchronous "clear" setState call
  // inside an effect — stale data for a different product is simply ignored.
  const currentEvidence =
    evidence && evidence.identity.product_number === selectedProduct ? evidence : null
  const currentDetailError =
    detailError && detailError.productNumber === selectedProduct ? detailError.message : ''
  const isLoadingDetail = selectedProduct != null && !currentEvidence && !currentDetailError

  useEffect(() => {
    const controller = new AbortController()
    searchProducts(query, controller.signal)
      .then((response) => {
        setResults(response.products)
        setSearchError('')
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return
        setSearchError(errorMessage(error, 'Unable to search products.'))
      })
    return () => controller.abort()
  }, [query])

  useEffect(() => {
    if (selectedProduct == null) return
    const controller = new AbortController()
    const productNumber = selectedProduct
    Promise.all([
      getProductEvidence(productNumber, controller.signal),
      getProductNotes(productNumber, controller.signal),
    ])
      .then(([evidenceResponse, notesResponse]) => {
        setEvidence(evidenceResponse)
        setNotes(notesResponse)
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return
        setDetailError({
          productNumber,
          message: errorMessage(error, 'Unable to load product evidence.'),
        })
      })
    return () => controller.abort()
  }, [selectedProduct])

  const recentPeriods = useMemo(
    () => currentEvidence?.month_end_inventory.periods.slice(0, 12) ?? [],
    [currentEvidence],
  )

  const recentReceipts = useMemo(
    () => currentEvidence?.receiving.recent_receipts.slice(0, 10) ?? [],
    [currentEvidence],
  )

  async function submitNote(event: FormEvent) {
    event.preventDefault()
    if (selectedProduct == null) return
    if (!authorIdentity.trim() || !noteText.trim()) {
      setNoteSaveStatus('error')
      setNoteSaveMessage('Your name and a note are both required.')
      return
    }
    setNoteSaveStatus('saving')
    setNoteSaveMessage('')
    try {
      await createProductNote(selectedProduct, {
        author_identity: authorIdentity.trim(),
        note: noteText.trim(),
      })
      const refreshed = await getProductNotes(selectedProduct)
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
    <section className="ip-shell">
      <header className="ip-header">
        <div>
          <span className="ip-kicker">Read-only MaddenCo evidence</span>
          <h2>Inventory &amp; Purchasing</h2>
          <p>Item identity, month-end inventory valuation, open purchase-order exposure, and receiving — no reorder point, forecast, or ERP write.</p>
        </div>
        <label className="ip-search">
          Search products
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Product number, search key, description, or barcode"
          />
        </label>
      </header>

      <div className="ip-layout">
        <div className="ip-results">
          {searchError && <p className="ip-error">{searchError}</p>}
          {results.length === 0 ? (
            <p className="ip-empty">No products matched.</p>
          ) : (
            <ul className="ip-result-list">
              {results.map((product) => (
                <li key={product.product_number}>
                  <button
                    type="button"
                    className={product.product_number === selectedProduct ? 'ip-result ip-result--active' : 'ip-result'}
                    onClick={() => setSelectedProduct(product.product_number)}
                  >
                    <strong>{product.description || 'Unnamed product'}</strong>
                    <span>#{product.product_number}</span>
                    {!product.active && <em className="ip-tag ip-tag--inactive">Inactive</em>}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="ip-detail">
          {selectedProduct == null && (
            <div className="ip-empty-state">
              <strong>Select a product to view evidence.</strong>
            </div>
          )}

          {isLoadingDetail && (
            <div className="ip-loading"><span className="ip-spinner" /> Loading product evidence…</div>
          )}

          {selectedProduct != null && currentDetailError && (
            <div className="ip-message ip-message--error">
              <strong>Product evidence is unavailable.</strong>
              <span>{currentDetailError}</span>
            </div>
          )}

          {currentEvidence && (
            <div className="ip-evidence">
              <div className="ip-identity-card">
                <div>
                  <h3>{currentEvidence.identity.description || 'Unnamed product'}</h3>
                  <span>Product #{currentEvidence.identity.product_number} · {currentEvidence.identity.active ? 'Active' : 'Inactive'}</span>
                </div>
                <dl>
                  <div><dt>Class / type</dt><dd>{currentEvidence.identity.product_class || 'Unavailable'} / {currentEvidence.identity.product_type || 'Unavailable'}</dd></div>
                  <div><dt>Brand</dt><dd>{currentEvidence.identity.brand || 'Unavailable'}</dd></div>
                  <div><dt>Size</dt><dd>{currentEvidence.identity.size || 'Unavailable'}</dd></div>
                  <div><dt>Load / speed</dt><dd>{currentEvidence.identity.load_index || 'Unavailable'} / {currentEvidence.identity.speed_rating || 'Unavailable'}</dd></div>
                  <div><dt>Unit of measure</dt><dd>{currentEvidence.identity.unit_of_measure || 'Unavailable'}</dd></div>
                  <div><dt>Vendor code</dt><dd>{currentEvidence.identity.vendor_code || 'Unavailable'}</dd></div>
                  <div><dt>Warehouse</dt><dd>{currentEvidence.identity.warehouse_location || 'Unavailable'}</dd></div>
                  <div><dt>PO allowed</dt><dd>{currentEvidence.identity.allow_po_creation ? 'Yes' : 'No'}</dd></div>
                  <div><dt>Last received</dt><dd>{formatDate(currentEvidence.identity.date_last_received)}</dd></div>
                  <div><dt>Last sold</dt><dd>{formatDate(currentEvidence.identity.date_last_sold)}</dd></div>
                </dl>
              </div>

              <div className="ip-metric-grid">
                <article><span>Vendor cost</span><strong>{formatMoney(currentEvidence.costing.vendor_cost)}</strong></article>
                <article><span>Replacement cost</span><strong>{formatMoney(currentEvidence.costing.replacement_cost)}</strong></article>
                <article><span>Price level 1</span><strong>{formatMoney(currentEvidence.costing.price_1)}</strong></article>
                <article><span>Last year's cost</span><strong>{formatMoney(currentEvidence.costing.last_year_cost)}</strong></article>
              </div>

              <div className="ip-section">
                <h4>Inventory position</h4>
                <p className="ip-section-note">{currentEvidence.inventory_position.explanation}</p>
                <div className="ip-metric-grid">
                  <article><span>On hand</span><strong>{formatNumber(currentEvidence.inventory_position.on_hand)}</strong></article>
                  <article><span>On order</span><strong>{formatNumber(currentEvidence.inventory_position.on_order)}</strong></article>
                  <article><span>Allocated</span><strong>{formatNumber(currentEvidence.inventory_position.allocated)}</strong></article>
                  <article><span>Configured min / max</span><strong>{formatNumber(currentEvidence.inventory_position.configured_minimum)} / {formatNumber(currentEvidence.inventory_position.configured_maximum)}</strong></article>
                </div>
              </div>

              <div className="ip-section">
                <h4>Month-end inventory (periodic snapshot)</h4>
                <p className="ip-section-note">{currentEvidence.month_end_inventory.explanation}</p>
                {currentEvidence.month_end_inventory.latest_period_total_units != null && (
                  <p className="ip-total">Most recent period total: {formatNumber(currentEvidence.month_end_inventory.latest_period_total_units)} units, {formatMoney(currentEvidence.month_end_inventory.latest_period_total_cost)}</p>
                )}
                {recentPeriods.length === 0 ? (
                  <p className="ip-empty">No month-end inventory snapshots found for this product.</p>
                ) : (
                  <div className="ip-table-wrap">
                    <table className="ip-table">
                      <thead><tr><th>Period</th><th>Store</th><th>Vendor</th><th>Class</th><th>Units</th><th>Total cost</th></tr></thead>
                      <tbody>
                        {recentPeriods.map((period, index) => (
                          <tr key={`${period.store_number}-${period.year}-${period.month}-${index}`}>
                            <td>{formatPeriod(period.month, period.year)}</td>
                            <td>{period.store_number ?? 'Unavailable'}</td>
                            <td>{period.vendor_number || 'Unavailable'}</td>
                            <td>{period.class_number || 'Unavailable'}</td>
                            <td>{formatNumber(period.units)}</td>
                            <td>{formatMoney(period.total_cost)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              <div className="ip-section">
                <h4>Open purchase-order exposure</h4>
                <p className="ip-section-note">{currentEvidence.purchase_exposure.explanation}</p>
                {currentEvidence.purchase_exposure.open_orders.length === 0 ? (
                  <p className="ip-empty">No open purchase orders reference this item.</p>
                ) : (
                  <div className="ip-table-wrap">
                    <table className="ip-table">
                      <thead><tr><th>PO #</th><th>Vendor</th><th>Date</th><th>Ordered</th><th>Received</th><th>Backorder</th><th>Avg unit cost</th><th>Line total</th></tr></thead>
                      <tbody>
                        {currentEvidence.purchase_exposure.open_orders.map((po) => (
                          <tr key={po.po_number}>
                            <td>{po.po_number}</td>
                            <td>{po.vendor_number ?? 'Unavailable'}</td>
                            <td>{formatDate(po.po_date)}</td>
                            <td>{po.ordered_quantity}</td>
                            <td>{po.received_quantity}</td>
                            <td>{po.backorder_quantity}</td>
                            <td>{formatMoney(po.average_unit_cost)}</td>
                            <td>{formatMoney(po.line_total_cost)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <p className="ip-total">Total open cost: {formatMoney(currentEvidence.purchase_exposure.open_order_total_cost)} across {currentEvidence.purchase_exposure.open_order_count} order(s)</p>
                  </div>
                )}
              </div>

              <div className="ip-section">
                <h4>Recent receiving</h4>
                <p className="ip-section-note">{currentEvidence.receiving.explanation} Cost-variance coverage: {currentEvidence.receiving.cost_variance_completeness}.</p>
                {recentReceipts.length === 0 ? (
                  <p className="ip-empty">No receiving history found.</p>
                ) : (
                  <div className="ip-table-wrap">
                    <table className="ip-table">
                      <thead><tr><th>PO #</th><th>Vendor</th><th>Qty</th><th>Actual cost</th><th>PO cost</th><th>Variance</th><th>Received</th></tr></thead>
                      <tbody>
                        {recentReceipts.map((receipt, index) => (
                          <tr key={`${receipt.po_number}-${index}`}>
                            <td>{receipt.po_number}</td>
                            <td>{receipt.vendor_number ?? 'Unavailable'}</td>
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

              <div className="ip-gaps">
                <strong>What this evidence does not include</strong>
                <ul>
                  {currentEvidence.gaps.map((gap) => (
                    <li key={gap.code}><strong>{gap.label}:</strong> {gap.explanation}</li>
                  ))}
                </ul>
              </div>

              <div className="ip-notes">
                <h4>Professional notes</h4>
                <p className="ip-section-note">Append-only. A note creates no ERP change, approval, or recommendation.</p>
                <form className="ip-note-form" onSubmit={submitNote}>
                  <label>Your name<input value={authorIdentity} onChange={(event) => setAuthorIdentity(event.target.value)} placeholder="Name" /></label>
                  <label>Note<textarea rows={3} value={noteText} onChange={(event) => setNoteText(event.target.value)} placeholder="What did you observe or confirm about this item?" /></label>
                  <button type="submit" disabled={noteSaveStatus === 'saving'}>{noteSaveStatus === 'saving' ? 'Saving…' : 'Save note'}</button>
                  {noteSaveMessage && (
                    <p className={noteSaveStatus === 'error' ? 'ip-form-error' : 'ip-form-success'}>{noteSaveMessage}</p>
                  )}
                </form>
                {notes && notes.count > 0 && (
                  <ul className="ip-note-list">
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
