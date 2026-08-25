import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  getAPErpDirectInvoiceEvidence,
  getAPErpInvoiceEvidence,
  getAPErpMappingReadiness,
  getAccountsPayableInvoices,
  searchAPErpInvoices,
} from './api'
import {
  errorMessage,
  formatCurrency,
  formatDate,
  formatDateTime,
  isAbortError,
  titleCase,
} from './format'
import type {
  APERPEvidenceResponse,
  APERPInvoiceSearchResponse,
  APInvoiceSummary,
  APMappingReadinessResponse,
} from './types'

type Status = 'idle' | 'loading' | 'success' | 'error'
type InvoiceCandidate = APERPInvoiceSearchResponse['invoice_candidates'][number]

function StatusPill({ value }: { value: string }) {
  return <span className={`ap-erp-status ap-erp-status--${value}`}>{value.replaceAll('_', ' ')}</span>
}

function ValueTable({
  title,
  rows,
}: {
  title: string
  rows: Array<Record<string, string | number | null>>
}) {
  const columns = rows.length > 0 ? Object.keys(rows[0]) : []
  return (
    <section className="ap-panel ap-erp-table-panel">
      <div className="ap-section-heading">
        <h3>{title}</h3>
        <span>{rows.length}</span>
      </div>
      {rows.length === 0 ? (
        <p className="ap-erp-empty">The exact vendor/invoice query returned no rows.</p>
      ) : (
        <div className="ap-table-wrap">
          <table className="ap-invoice-table">
            <thead><tr>{columns.map((column) => <th key={column}>{titleCase(column)}</th>)}</tr></thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={`${title}-${index}`}>
                  {columns.map((column) => <td key={column}>{row[column] ?? '—'}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

export default function APERPEvidenceWorkspace({ refreshKey }: { refreshKey: number }) {
  const [mapping, setMapping] = useState<APMappingReadinessResponse | null>(null)
  const [mappingStatus, setMappingStatus] = useState<Status>('loading')
  const [mappingError, setMappingError] = useState('')
  const [vendorQuery, setVendorQuery] = useState('')
  const [invoiceQuery, setInvoiceQuery] = useState('')
  const [searchResult, setSearchResult] = useState<APERPInvoiceSearchResponse | null>(null)
  const [searchStatus, setSearchStatus] = useState<Status>('idle')
  const [searchError, setSearchError] = useState('')
  const [localQuery, setLocalQuery] = useState('')
  const [invoices, setInvoices] = useState<APInvoiceSummary[]>([])
  const [invoiceStatus, setInvoiceStatus] = useState<Status>('loading')
  const [invoiceError, setInvoiceError] = useState('')
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  const [evidence, setEvidence] = useState<APERPEvidenceResponse | null>(null)
  const [evidenceStatus, setEvidenceStatus] = useState<Status>('idle')
  const [evidenceError, setEvidenceError] = useState('')
  const searchAbortRef = useRef<AbortController | null>(null)
  const evidenceAbortRef = useRef<AbortController | null>(null)

  const loadMapping = useCallback(async () => {
    const controller = new AbortController()
    setMappingStatus('loading')
    setMappingError('')
    try {
      setMapping(await getAPErpMappingReadiness(controller.signal))
      setMappingStatus('success')
    } catch (error) {
      if (isAbortError(error)) return
      setMappingStatus('error')
      setMappingError(errorMessage(error, 'Unable to validate the AP ERP source map.'))
    }
  }, [])

  const loadInvoices = useCallback(async (search: string) => {
    setInvoiceStatus('loading')
    setInvoiceError('')
    try {
      const response = await getAccountsPayableInvoices({
        query: search.trim() || undefined,
        limit: 25,
        offset: 0,
      })
      setInvoices(response.items)
      setInvoiceStatus('success')
    } catch (error) {
      if (isAbortError(error)) return
      setInvoiceStatus('error')
      setInvoiceError(errorMessage(error, 'Unable to load imported invoice identities.'))
    }
  }, [])

  const runDirectSearch = useCallback(async (vendor: string, invoice: string) => {
    searchAbortRef.current?.abort()
    const controller = new AbortController()
    searchAbortRef.current = controller
    setSearchResult(null)
    setSearchStatus('loading')
    setSearchError('')
    try {
      const result = await searchAPErpInvoices(vendor, invoice, controller.signal)
      setSearchResult(result)
      setSearchStatus('success')
    } catch (error) {
      if (isAbortError(error)) return
      setSearchStatus('error')
      setSearchError(errorMessage(error, 'Unable to search current ERP AP evidence.'))
    }
  }, [])

  const loadLocalEvidence = useCallback(async (apInvoiceId: string) => {
    evidenceAbortRef.current?.abort()
    const controller = new AbortController()
    evidenceAbortRef.current = controller
    setSelectedKey(`local:${apInvoiceId}`)
    setEvidence(null)
    setEvidenceStatus('loading')
    setEvidenceError('')
    try {
      setEvidence(await getAPErpInvoiceEvidence(apInvoiceId, controller.signal))
      setEvidenceStatus('success')
    } catch (error) {
      if (isAbortError(error)) return
      setEvidenceStatus('error')
      setEvidenceError(errorMessage(error, 'Unable to load bounded ERP invoice evidence.'))
    }
  }, [])

  const loadDirectEvidence = useCallback(async (candidate: InvoiceCandidate) => {
    evidenceAbortRef.current?.abort()
    const controller = new AbortController()
    evidenceAbortRef.current = controller
    setSelectedKey(`erp:${candidate.vendor_number}:${candidate.invoice_number}`)
    setEvidence(null)
    setEvidenceStatus('loading')
    setEvidenceError('')
    try {
      setEvidence(await getAPErpDirectInvoiceEvidence(
        candidate.vendor_number,
        candidate.invoice_number,
        controller.signal,
      ))
      setEvidenceStatus('success')
    } catch (error) {
      if (isAbortError(error)) return
      setEvidenceStatus('error')
      setEvidenceError(errorMessage(error, 'Unable to load the selected ERP invoice evidence.'))
    }
  }, [])

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadMapping()
      void loadInvoices('')
    }, 0)
    return () => {
      window.clearTimeout(timeoutId)
      searchAbortRef.current?.abort()
      evidenceAbortRef.current?.abort()
    }
  }, [loadInvoices, loadMapping, refreshKey])

  function submitDirectSearch(event: FormEvent) {
    event.preventDefault()
    if (!vendorQuery.trim() && !invoiceQuery.trim()) {
      setSearchStatus('error')
      setSearchError('Enter a vendor name/number, an exact invoice number, or both.')
      return
    }
    void runDirectSearch(vendorQuery, invoiceQuery)
  }

  function submitLocalSearch(event: FormEvent) {
    event.preventDefault()
    void loadInvoices(localQuery)
  }

  return (
    <div className="ap-erp-workspace">
      <section className="ap-panel">
        <div className="ap-panel-heading">
          <div><span className="ap-kicker">Confirmed source record</span><h2>DTA273 AP mapping</h2></div>
          {mapping && <StatusPill value={mapping.schema_catalog_status} />}
        </div>
        {mappingStatus === 'loading' && <p>Checking the supplied table and column map against the configured ERP schema…</p>}
        {mappingStatus === 'error' && <div className="ap-message ap-message--error">{mappingError}</div>}
        {mapping && (
          <>
            <div className="ap-erp-mapping-grid">
              {mapping.categories.map((category) => (
                <article key={category.key}>
                  <div><strong>{category.label}</strong><StatusPill value={category.status} /></div>
                  <span>{category.candidates.map((candidate) => candidate.table_name).join(', ')}</span>
                  <p>{category.explanation}</p>
                </article>
              ))}
            </div>
            <p className="ap-erp-boundary">{mapping.next_required_action}</p>
          </>
        )}
      </section>

      <section className="ap-panel">
        <div className="ap-panel-heading">
          <div><span className="ap-kicker">Live ERP discovery</span><h2>Find a Madden vendor or posted invoice</h2><p>This path reads PMVEND and PMHD directly and does not require an imported OCR invoice.</p></div>
        </div>
        <form className="ap-erp-search ap-erp-search--direct" onSubmit={submitDirectSearch}>
          <label>
            <span>Vendor name or number</span>
            <input value={vendorQuery} onChange={(event) => setVendorQuery(event.target.value)} placeholder="Example: Michelin or 101" />
          </label>
          <label>
            <span>Exact invoice number</span>
            <input value={invoiceQuery} onChange={(event) => setInvoiceQuery(event.target.value)} placeholder="Optional when vendor is entered" />
          </label>
          <button type="submit" className="ap-primary-button" disabled={searchStatus === 'loading'}>{searchStatus === 'loading' ? 'Searching ERP…' : 'Search ERP'}</button>
        </form>
        <p className="ap-erp-boundary">Enter at least one field. Vendor-name matches are candidates for you to select; invoice-number matching is exact.</p>
        {searchError && <div className="ap-message ap-message--error">{searchError}</div>}
        {searchResult?.warnings.length ? <div className="ap-message ap-message--notice"><ul>{searchResult.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div> : null}

        {searchResult && searchStatus === 'success' && (
          <>
            {searchResult.vendor_candidates.length > 0 && (
              <div className="ap-erp-discovery-group">
                <div className="ap-section-heading"><h3>Vendor candidates</h3><span>{searchResult.vendor_candidates.length}</span></div>
                <div className="ap-erp-invoice-list">
                  {searchResult.vendor_candidates.map((vendor) => (
                    <button key={vendor.vendor_number} type="button" onClick={() => {
                      setVendorQuery(vendor.vendor_number)
                      void runDirectSearch(vendor.vendor_number, invoiceQuery)
                    }}>
                      <span><strong>{vendor.vendor_name || 'Vendor name unavailable'}</strong><small>{vendor.match_basis.map(titleCase).join(', ')}</small></span>
                      <span><strong>#{vendor.vendor_number}</strong><small>{vendor.sort_name || 'No sort name'}</small></span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="ap-erp-discovery-group">
              <div className="ap-section-heading"><h3>Posted invoice identities</h3><span>{searchResult.invoice_candidates.length}</span></div>
              {searchResult.invoice_candidates.length === 0 ? (
                <p className="ap-erp-empty">No PMHD vendor/invoice identity matched the supplied fields.</p>
              ) : (
                <div className="ap-erp-invoice-list">
                  {searchResult.invoice_candidates.map((candidate) => {
                    const candidateKey = `erp:${candidate.vendor_number}:${candidate.invoice_number}`
                    return (
                      <button key={candidateKey} type="button" className={selectedKey === candidateKey ? 'is-active' : ''} onClick={() => void loadDirectEvidence(candidate)}>
                        <span><strong>{candidate.invoice_number}</strong><small>{candidate.vendor_name || 'Vendor name unavailable'} · vendor {candidate.vendor_number}</small></span>
                        <span><strong>{candidate.posted_header_row_count} header row{candidate.posted_header_row_count === 1 ? '' : 's'}</strong><small>Invoice {formatDate(candidate.latest_invoice_date)} · due {formatDate(candidate.latest_due_date)}</small></span>
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          </>
        )}
      </section>

      <section className="ap-panel">
        <div className="ap-panel-heading"><div><span className="ap-kicker">Optional OCR-linked lookup</span><h2>Select an imported ETOP invoice</h2><p>Use this path when Document Intelligence has already created local vendor-invoice evidence.</p></div></div>
        <form className="ap-erp-search" onSubmit={submitLocalSearch}>
          <input value={localQuery} onChange={(event) => setLocalQuery(event.target.value)} placeholder="Invoice, vendor, PO, job ID, or filename" />
          <button type="submit" className="ap-primary-button" disabled={invoiceStatus === 'loading'}>Search imports</button>
        </form>
        {invoiceError && <div className="ap-message ap-message--error">{invoiceError}</div>}
        <div className="ap-erp-invoice-list">
          {invoiceStatus === 'success' && invoices.length === 0 && <p>No imported OCR invoice evidence exists yet. Direct ERP search above remains available.</p>}
          {invoices.map((invoice) => (
            <button key={invoice.ap_invoice_id} type="button" className={selectedKey === `local:${invoice.ap_invoice_id}` ? 'is-active' : ''} onClick={() => void loadLocalEvidence(invoice.ap_invoice_id)}>
              <span><strong>{invoice.invoice_number || 'Invoice number unavailable'}</strong><small>{invoice.vendor_name || 'Vendor unavailable'} · vendor {invoice.vendor_number || 'unmapped'}</small></span>
              <span><strong>{formatCurrency(invoice.total_amount)}</strong><small>{formatDate(invoice.invoice_date)}</small></span>
            </button>
          ))}
        </div>
      </section>

      {selectedKey && evidenceStatus === 'loading' && <div className="ap-loading"><span className="ap-spinner" /><div><strong>Reading ERP evidence</strong><p>Executing exact, bounded, read-only vendor and invoice queries…</p></div></div>}
      {evidenceError && <div className="ap-message ap-message--error">{evidenceError}</div>}

      {evidence && evidenceStatus === 'success' && (
        <>
          {evidence.warnings.length > 0 && <div className="ap-message ap-message--notice"><ul>{evidence.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div>}
          <section className="ap-panel">
            <div className="ap-panel-heading"><div><span className="ap-kicker">ERP evidence packet</span><h2>{evidence.lookup_identity.invoice_number}</h2><p>Retrieved {formatDateTime(evidence.generated_at)} · SHA-256 {evidence.evidence_sha256.slice(0, 16)}…</p></div><StatusPill value={evidence.lookup_identity.lookup_origin} /></div>
            <div className="ap-erp-summary-grid">
              <article><span>Vendor</span><strong>{evidence.vendor_master.vendor_name || evidence.local_invoice?.vendor_name || 'Unavailable'}</strong><small>#{evidence.vendor_master.vendor_number || evidence.lookup_identity.vendor_number || '—'}</small></article>
              <article><span>ETOP local invoice total</span><strong>{formatCurrency(evidence.local_invoice?.total_amount)}</strong><small>{evidence.local_invoice ? 'Linked imported evidence' : 'Direct ERP lookup; no local import required'}</small></article>
              <article><span>ERP last-paid fact</span><strong>{formatCurrency(evidence.vendor_master.last_paid_amount)}</strong><small>{formatDate(evidence.vendor_master.last_paid_date)}</small></article>
              <article><span>Default GL</span><strong>{[evidence.vendor_master.default_gl_division, evidence.vendor_master.default_gl_department, evidence.vendor_master.default_gl_account].filter(Boolean).join('-') || 'Unavailable'}</strong><small>PMVEND raw fields</small></article>
            </div>
          </section>

          <section className="ap-panel">
            <div className="ap-section-heading"><h3>Source coverage</h3><span>{evidence.coverage.length}</span></div>
            <div className="ap-erp-coverage-grid">
              {evidence.coverage.map((item) => <article key={item.key}><div><strong>{item.label}</strong><StatusPill value={item.status} /></div><p>{item.explanation}</p><small>{item.source || 'No source mapped'} · {item.record_count ?? 0} row(s)</small></article>)}
            </div>
          </section>

          <ValueTable title="Posted invoice headers · PMHD" rows={evidence.posted_headers} />
          <ValueTable title="Posted invoice detail · PMDT" rows={evidence.posted_details} />
          <ValueTable title="GL distributions · PMGLDS" rows={evidence.gl_distributions} />
          <ValueTable title="Invoice input headers · PTHD" rows={evidence.input_headers} />
          <ValueTable title="Invoice input detail · PTDT" rows={evidence.input_details} />
          <ValueTable title="Input payment splits · PTPY" rows={evidence.input_payment_splits} />

          <section className="ap-panel ap-erp-governance">
            <div><span className="ap-kicker">Governance boundary</span><h2>Evidence only; no financial action</h2><p>{evidence.governance.source_authority}</p></div>
            <ul>{evidence.governance.statements.map((statement) => <li key={statement}>{statement}</li>)}</ul>
            <details><summary>Sensitive fields deliberately excluded</summary><ul>{evidence.sensitive_fields_excluded.map((field) => <li key={field}>{field}</li>)}</ul></details>
          </section>
        </>
      )}
    </div>
  )
}
