import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import {
  createPricingNote,
  getPricingNotes,
  searchCustomerClasses,
  searchDiscounts,
} from './api'
import type {
  CustomerClassRecord,
  DiscountRecord,
  DiscountSearchFilters,
  PricingNoteHistoryResponse,
} from './types'
import './PricingContractsWorkspace.css'

const money = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
})

function formatMoney(value: number): string {
  return money.format(value)
}

function formatNumber(value: number): string {
  return value.toLocaleString('en-US', { maximumFractionDigits: 4 })
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

type ViewMode = 'discounts' | 'customer-classes'
type NoteSaveStatus = 'idle' | 'saving' | 'success' | 'error'

export default function PricingContractsWorkspace() {
  const [viewMode, setViewMode] = useState<ViewMode>('discounts')

  const [customerNumberInput, setCustomerNumberInput] = useState('')
  const [productNumberInput, setProductNumberInput] = useState('')
  const [productClassInput, setProductClassInput] = useState('')
  const [vendorCodeInput, setVendorCodeInput] = useState('')
  const [activeOnly, setActiveOnly] = useState(false)

  const [discounts, setDiscounts] = useState<DiscountRecord[]>([])
  const [discountGaps, setDiscountGaps] = useState<
    { code: string; label: string; explanation: string }[]
  >([])
  const [searchError, setSearchError] = useState('')
  const [hasSearched, setHasSearched] = useState(false)

  const [selectedRecordKey, setSelectedRecordKey] = useState<string | null>(null)
  const selectedDiscount = useMemo(
    () => discounts.find((d) => d.record_key === selectedRecordKey) ?? null,
    [discounts, selectedRecordKey],
  )

  const [notes, setNotes] = useState<PricingNoteHistoryResponse | null>(null)
  const [notesError, setNotesError] = useState('')
  const [authorIdentity, setAuthorIdentity] = useState('')
  const [noteText, setNoteText] = useState('')
  const [noteScopeVendor, setNoteScopeVendor] = useState('')
  const [noteScopeClass, setNoteScopeClass] = useState('')
  const [noteScopeProduct, setNoteScopeProduct] = useState('')
  const [noteScopeType, setNoteScopeType] = useState('')
  const [noteSaveStatus, setNoteSaveStatus] = useState<NoteSaveStatus>('idle')
  const [noteSaveMessage, setNoteSaveMessage] = useState('')

  const [customerClasses, setCustomerClasses] = useState<CustomerClassRecord[]>([])
  const [classSearch, setClassSearch] = useState('')
  const [classError, setClassError] = useState('')

  const parsedCustomerNumber = customerNumberInput.trim()
    ? Number.parseInt(customerNumberInput.trim(), 10)
    : undefined
  const customerNumberIsValid =
    parsedCustomerNumber === undefined || Number.isFinite(parsedCustomerNumber)

  function runSearch(event?: FormEvent) {
    event?.preventDefault()
    setHasSearched(true)
  }

  useEffect(() => {
    if (!hasSearched || viewMode !== 'discounts') return
    if (!customerNumberIsValid) return
    const controller = new AbortController()
    const filters: DiscountSearchFilters = {
      customerNumber: parsedCustomerNumber,
      productNumber: productNumberInput,
      productClass: productClassInput,
      vendorCode: vendorCodeInput,
      activeOnly,
    }
    searchDiscounts(filters, controller.signal)
      .then((response) => {
        setDiscounts(response.discounts)
        setDiscountGaps(response.gaps)
        setSearchError('')
        setSelectedRecordKey(null)
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return
        setSearchError(errorMessage(error, 'Unable to search pricing records.'))
      })
    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasSearched, viewMode])

  useEffect(() => {
    if (viewMode !== 'customer-classes') return
    const controller = new AbortController()
    searchCustomerClasses(classSearch, controller.signal)
      .then((response) => {
        setCustomerClasses(response.customer_classes)
        setClassError('')
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return
        setClassError(errorMessage(error, 'Unable to load customer classes.'))
      })
    return () => controller.abort()
  }, [viewMode, classSearch])

  useEffect(() => {
    if (selectedDiscount) {
      setNoteScopeVendor(selectedDiscount.vendor_code)
      setNoteScopeClass(selectedDiscount.product_class)
      setNoteScopeProduct(selectedDiscount.product_number)
      setNoteScopeType(selectedDiscount.product_type)
    } else {
      setNoteScopeVendor('')
      setNoteScopeClass('')
      setNoteScopeProduct('')
      setNoteScopeType('')
    }
  }, [selectedDiscount])

  const noteScopeCustomerNumber = selectedDiscount
    ? selectedDiscount.customer_number
    : parsedCustomerNumber

  useEffect(() => {
    if (noteScopeCustomerNumber === undefined || !Number.isFinite(noteScopeCustomerNumber)) {
      setNotes(null)
      return
    }
    const controller = new AbortController()
    const scope = selectedDiscount
      ? {
          vendorCode: selectedDiscount.vendor_code,
          productClass: selectedDiscount.product_class,
          productNumber: selectedDiscount.product_number,
          productType: selectedDiscount.product_type,
        }
      : {}
    getPricingNotes(noteScopeCustomerNumber, scope, controller.signal)
      .then((response) => {
        setNotes(response)
        setNotesError('')
      })
      .catch((error: unknown) => {
        if (isAbortError(error)) return
        setNotesError(errorMessage(error, 'Unable to load pricing notes.'))
      })
    return () => controller.abort()
  }, [noteScopeCustomerNumber, selectedDiscount])

  async function submitNote(event: FormEvent) {
    event.preventDefault()
    if (noteScopeCustomerNumber === undefined || !Number.isFinite(noteScopeCustomerNumber)) {
      setNoteSaveStatus('error')
      setNoteSaveMessage('Enter a customer number before saving a note.')
      return
    }
    if (!authorIdentity.trim() || !noteText.trim()) {
      setNoteSaveStatus('error')
      setNoteSaveMessage('Your name and a note are both required.')
      return
    }
    setNoteSaveStatus('saving')
    setNoteSaveMessage('')
    try {
      await createPricingNote({
        customer_number: noteScopeCustomerNumber,
        vendor_code: noteScopeVendor.trim() || null,
        product_class: noteScopeClass.trim() || null,
        product_number: noteScopeProduct.trim() || null,
        product_type: noteScopeType.trim() || null,
        author_identity: authorIdentity.trim(),
        note: noteText.trim(),
      })
      const scope = selectedDiscount
        ? {
            vendorCode: selectedDiscount.vendor_code,
            productClass: selectedDiscount.product_class,
            productNumber: selectedDiscount.product_number,
            productType: selectedDiscount.product_type,
          }
        : {}
      const refreshed = await getPricingNotes(noteScopeCustomerNumber, scope)
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
    <section className="pc-shell">
      <header className="pc-header">
        <div>
          <span className="pc-kicker">Read-only MaddenCo evidence</span>
          <h2>Pricing &amp; Contracts</h2>
          <p>
            Customer/vendor/product pricing overrides from TMDISC, shown as literal stored
            values — no computed final price, no compliance score.
          </p>
        </div>
        <div className="pc-view-toggle">
          <button
            type="button"
            className={viewMode === 'discounts' ? 'pc-toggle pc-toggle--active' : 'pc-toggle'}
            onClick={() => setViewMode('discounts')}
          >
            Pricing overrides
          </button>
          <button
            type="button"
            className={
              viewMode === 'customer-classes' ? 'pc-toggle pc-toggle--active' : 'pc-toggle'
            }
            onClick={() => setViewMode('customer-classes')}
          >
            Customer classes
          </button>
        </div>
      </header>

      {viewMode === 'discounts' ? (
        <>
          <form className="pc-filters" onSubmit={runSearch}>
            <label>
              Customer number
              <input
                type="text"
                inputMode="numeric"
                value={customerNumberInput}
                onChange={(event) => setCustomerNumberInput(event.target.value)}
                placeholder="e.g. 1234567"
              />
            </label>
            <label>
              Product number
              <input
                type="text"
                value={productNumberInput}
                onChange={(event) => setProductNumberInput(event.target.value)}
                placeholder="Contains..."
              />
            </label>
            <label>
              Product class
              <input
                type="text"
                maxLength={2}
                value={productClassInput}
                onChange={(event) => setProductClassInput(event.target.value)}
                placeholder="2-char code"
              />
            </label>
            <label>
              Vendor code
              <input
                type="text"
                maxLength={3}
                value={vendorCodeInput}
                onChange={(event) => setVendorCodeInput(event.target.value)}
                placeholder="3-char DCVENDOR code"
              />
            </label>
            <label className="pc-checkbox">
              <input
                type="checkbox"
                checked={activeOnly}
                onChange={(event) => setActiveOnly(event.target.checked)}
              />
              Active only
            </label>
            <button type="submit" disabled={!customerNumberIsValid}>
              Search
            </button>
          </form>
          {!customerNumberIsValid && (
            <p className="pc-error">Customer number must be numeric.</p>
          )}

          <div className="pc-layout">
            <div className="pc-results">
              {!hasSearched && <p className="pc-empty">Enter filters and search to see pricing overrides.</p>}
              {searchError && <p className="pc-error">{searchError}</p>}
              {hasSearched && !searchError && discounts.length === 0 && (
                <p className="pc-empty">No TMDISC rows matched these filters.</p>
              )}
              {discounts.length > 0 && (
                <ul className="pc-result-list">
                  {discounts.map((discount) => (
                    <li key={discount.record_key}>
                      <button
                        type="button"
                        className={
                          discount.record_key === selectedRecordKey
                            ? 'pc-result pc-result--active'
                            : 'pc-result'
                        }
                        onClick={() => setSelectedRecordKey(discount.record_key)}
                      >
                        <strong>
                          Customer #{discount.customer_number} · Vendor {discount.vendor_code}
                        </strong>
                        <span>
                          {discount.product_number} ({discount.product_type}) ·{' '}
                          {discount.product_class_label || `Class ${discount.product_class}`}
                        </span>
                        {!discount.active && <em className="pc-tag pc-tag--inactive">Inactive</em>}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="pc-detail">
              {selectedDiscount ? (
                <div className="pc-evidence">
                  <div className="pc-identity-card">
                    <div>
                      <h3>
                        Customer #{selectedDiscount.customer_number} · Vendor {selectedDiscount.vendor_code}
                      </h3>
                      <span>
                        {selectedDiscount.product_number} ({selectedDiscount.product_type}) ·{' '}
                        {selectedDiscount.active ? 'Active' : 'Inactive'}
                      </span>
                    </div>
                    <dl>
                      <div>
                        <dt>Product class</dt>
                        <dd>
                          {selectedDiscount.product_class_label ||
                            'Unavailable'}{' '}
                          ({selectedDiscount.product_class})
                        </dd>
                      </div>
                      <div>
                        <dt>Delete code</dt>
                        <dd>{selectedDiscount.delete_code || 'Blank (active)'}</dd>
                      </div>
                      <div>
                        <dt>Date added</dt>
                        <dd>{formatDate(selectedDiscount.date_added)}</dd>
                      </div>
                      <div>
                        <dt>Date changed</dt>
                        <dd>{formatDate(selectedDiscount.date_changed)}</dd>
                      </div>
                      <div>
                        <dt>Added by</dt>
                        <dd>{selectedDiscount.added_by || 'Unavailable'}</dd>
                      </div>
                      <div>
                        <dt>Changed by</dt>
                        <dd>{selectedDiscount.changed_by || 'Unavailable'}</dd>
                      </div>
                    </dl>
                  </div>

                  <div className="pc-metric-grid">
                    <article>
                      <span>Override price (DCPRICE)</span>
                      <strong>{formatMoney(selectedDiscount.override_price)}</strong>
                    </article>
                    <article>
                      <span>Fixed amount (DCAMTFIX)</span>
                      <strong>{formatMoney(selectedDiscount.fixed_amount)}</strong>
                    </article>
                    <article>
                      <span>Factor (DCFACTOR)</span>
                      <strong>{formatNumber(selectedDiscount.factor)}</strong>
                    </article>
                    <article>
                      <span>Price code (DCPRICECD)</span>
                      <strong>{selectedDiscount.price_code}</strong>
                    </article>
                  </div>
                  <p className="pc-section-note">
                    These four values are shown as literal TMDISC columns, not resolved into one
                    "final price" — MaddenCo's pricing engine decides which mechanic applies using
                    inputs this module cannot see.
                  </p>

                  <div className="pc-gaps">
                    <strong>What this evidence does not include</strong>
                    <ul>
                      {discountGaps.map((gap) => (
                        <li key={gap.code}>
                          <strong>{gap.label}:</strong> {gap.explanation}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              ) : (
                <div className="pc-empty-state">
                  <strong>
                    {hasSearched && discounts.length > 0
                      ? 'Select a pricing override to view its full evidence.'
                      : parsedCustomerNumber !== undefined
                        ? 'No override selected — notes below are scoped to the customer number only.'
                        : 'Search for a customer to begin.'}
                  </strong>
                </div>
              )}

              {noteScopeCustomerNumber !== undefined && Number.isFinite(noteScopeCustomerNumber) && (
                <div className="pc-notes">
                  <h4>Pricing / contract notes</h4>
                  <p className="pc-section-note">
                    Append-only. Used to track vendor rebate program commitments — there is no
                    rebate-accrual table in this schema. A note creates no ERP change.
                  </p>
                  {notesError && <p className="pc-error">{notesError}</p>}
                  <form className="pc-note-form" onSubmit={submitNote}>
                    <div className="pc-note-scope-grid">
                      <label>
                        Customer #
                        <input value={noteScopeCustomerNumber} disabled />
                      </label>
                      <label>
                        Vendor code
                        <input
                          value={noteScopeVendor}
                          onChange={(event) => setNoteScopeVendor(event.target.value)}
                          disabled={Boolean(selectedDiscount)}
                          maxLength={3}
                          placeholder="Optional"
                        />
                      </label>
                      <label>
                        Product class
                        <input
                          value={noteScopeClass}
                          onChange={(event) => setNoteScopeClass(event.target.value)}
                          disabled={Boolean(selectedDiscount)}
                          maxLength={2}
                          placeholder="Optional"
                        />
                      </label>
                      <label>
                        Product number
                        <input
                          value={noteScopeProduct}
                          onChange={(event) => setNoteScopeProduct(event.target.value)}
                          disabled={Boolean(selectedDiscount)}
                          placeholder="Optional"
                        />
                      </label>
                      <label>
                        Product type
                        <input
                          value={noteScopeType}
                          onChange={(event) => setNoteScopeType(event.target.value)}
                          disabled={Boolean(selectedDiscount)}
                          maxLength={3}
                          placeholder="Optional"
                        />
                      </label>
                    </div>
                    <label>
                      Your name
                      <input
                        value={authorIdentity}
                        onChange={(event) => setAuthorIdentity(event.target.value)}
                        placeholder="Name"
                      />
                    </label>
                    <label>
                      Note
                      <textarea
                        rows={3}
                        value={noteText}
                        onChange={(event) => setNoteText(event.target.value)}
                        placeholder="What commitment, rebate term, or pricing context did you confirm?"
                      />
                    </label>
                    <button type="submit" disabled={noteSaveStatus === 'saving'}>
                      {noteSaveStatus === 'saving' ? 'Saving…' : 'Save note'}
                    </button>
                    {noteSaveMessage && (
                      <p className={noteSaveStatus === 'error' ? 'pc-form-error' : 'pc-form-success'}>
                        {noteSaveMessage}
                      </p>
                    )}
                  </form>
                  {notes && notes.count > 0 && (
                    <ul className="pc-note-list">
                      {notes.notes.map((note) => (
                        <li key={note.note_id}>
                          <div>
                            <strong>{note.author_identity}</strong>
                            <span>{formatDateTime(note.created_at)}</span>
                          </div>
                          <div className="pc-note-scope-tags">
                            {note.vendor_code && <em>Vendor {note.vendor_code}</em>}
                            {note.product_class && <em>Class {note.product_class}</em>}
                            {note.product_number && <em>{note.product_number}</em>}
                            <em>{note.matched_discount_count} matching TMDISC row(s) at write time</em>
                          </div>
                          <p>{note.note}</p>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          </div>
        </>
      ) : (
        <div className="pc-layout pc-layout--single">
          <div className="pc-detail">
            <label className="pc-search-classes">
              Search customer classes
              <input
                type="search"
                value={classSearch}
                onChange={(event) => setClassSearch(event.target.value)}
                placeholder="Class number or name"
              />
            </label>
            {classError && <p className="pc-error">{classError}</p>}
            {customerClasses.length === 0 ? (
              <p className="pc-empty">No customer classes matched.</p>
            ) : (
              <div className="pc-table-wrap">
                <table className="pc-table">
                  <thead>
                    <tr>
                      <th>Class #</th>
                      <th>Class name</th>
                      <th>Active</th>
                      <th>Created</th>
                      <th>Changed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {customerClasses.map((entry) => (
                      <tr key={entry.id}>
                        <td>{entry.class_num}</td>
                        <td>{entry.class_name}</td>
                        <td>{entry.active ? 'Yes' : 'No'}</td>
                        <td>{formatDateTime(entry.created_at)}</td>
                        <td>{formatDateTime(entry.changed_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="pc-section-note">
              CUCLASSES is a customer-class reference only; TMDISC discount rows are keyed by
              customer number, not by customer class, so this list is not joined to the pricing
              overrides above.
            </p>
          </div>
        </div>
      )}
    </section>
  )
}
