import { useEffect, useState } from 'react'
import { getCreditERPEvidence } from './api'
import type { CreditERPEvidenceResponse } from './types'

const money = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
const dateTime = new Intl.DateTimeFormat('en-US', { dateStyle: 'medium', timeStyle: 'short' })

function formatDate(value: string | null): string {
  if (!value) return 'Unavailable'
  const parsed = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00:00` : value)
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleDateString()
}

function Status({ value }: { value: string }) {
  return <span className={`credit-erp-status credit-erp-status--${value}`}>{value.replaceAll('_', ' ')}</span>
}

export default function CreditERPEvidencePanel({ customerNumber }: { customerNumber: number }) {
  const [evidence, setEvidence] = useState<CreditERPEvidenceResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => {
      setLoading(true)
      setError('')
      getCreditERPEvidence(customerNumber, controller.signal)
        .then((response) => setEvidence(response))
        .catch((reason: unknown) => {
          if (reason instanceof DOMException && reason.name === 'AbortError') return
          setError(reason instanceof Error ? reason.message : 'Unable to load current ERP credit evidence.')
        })
        .finally(() => setLoading(false))
    }, 0)
    return () => {
      window.clearTimeout(timeoutId)
      controller.abort()
    }
  }, [customerNumber])

  if (loading) {
    return <div className="credit-risk-loading"><strong>Reading current ERP evidence…</strong><span>Bounded TMCUST, TMAROP, and CUNUMENT queries are in progress.</span></div>
  }
  if (error) return <div className="credit-risk-message credit-risk-message--error">{error}</div>
  if (!evidence) return null

  return (
    <section className="credit-erp-panel">
      <header className="credit-erp-header">
        <div><span>Read-only ERP evidence packet</span><h2>{evidence.customer_name}</h2><p>Customer {evidence.customer_number} · retrieved {dateTime.format(new Date(evidence.generated_at))} · SHA-256 {evidence.evidence_sha256.slice(0, 16)}…</p></div>
        <div><Status value={evidence.open_ar.status} /><strong>ERP write disabled</strong></div>
      </header>

      {evidence.warnings.length > 0 && <div className="credit-risk-message credit-risk-message--notice"><ul>{evidence.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div>}

      <div className="credit-erp-metrics">
        <article><span>Current credit line</span><strong>{money.format(evidence.current.credit_limit)}</strong><small>TMCUST</small></article>
        <article><span>Customer balance</span><strong>{money.format(evidence.current.balance)}</strong><small>TMCUST</small></article>
        <article><span>On-order aggregate</span><strong>{money.format(evidence.current.erp_on_order_aggregate)}</strong><small>Not order-level detail</small></article>
        <article><span>Partial exposure</span><strong>{money.format(evidence.current.partial_exposure)}</strong><small>Known components only</small></article>
        <article><span>Partial available</span><strong>{money.format(evidence.current.partial_available_credit)}</strong><small>Not a release decision</small></article>
        <article><span>Last payment fact</span><strong>{evidence.current.last_payment_amount == null ? 'Unavailable' : money.format(evidence.current.last_payment_amount)}</strong><small>{formatDate(evidence.current.last_payment_date)}</small></article>
      </div>

      <section className="credit-erp-section">
        <div className="credit-erp-section-heading"><div><span>TMAROP</span><h3>Current nonzero Open A/R</h3></div><div><Status value={evidence.open_ar.status} /><small>{evidence.open_ar.retrieved_count} row(s) · limit {evidence.open_ar.row_limit}</small></div></div>
        <p>{evidence.open_ar.explanation}</p>
        <div className="credit-erp-table-wrap">
          <table>
            <thead><tr><th>Invoice</th><th>Invoice date</th><th>Due date</th><th>Days past due</th><th>Type</th><th>Reference</th><th>Original</th><th>Signed open</th></tr></thead>
            <tbody>{evidence.open_ar.items.map((item) => <tr key={item.open_item_key}><td><strong>{item.invoice_number}</strong><small>{item.aging_bucket.replaceAll('_', ' ')}</small></td><td>{formatDate(item.invoice_date)}</td><td>{formatDate(item.due_date)}</td><td>{item.days_past_due ?? '—'}</td><td>{item.transaction_type || '—'} / {item.debit_credit || '—'}</td><td>{item.reference_number || '—'}</td><td>{money.format(item.original_amount)}</td><td>{money.format(item.open_amount)}</td></tr>)}</tbody>
          </table>
        </div>
        <footer><span>Retrieved signed open amount <strong>{money.format(evidence.open_ar.retrieved_signed_open_amount)}</strong></span><span>Customer master balance <strong>{money.format(evidence.open_ar.customer_master_balance)}</strong></span><span>Reconciliation difference <strong>{evidence.open_ar.reconciliation_difference == null ? 'Incomplete' : money.format(evidence.open_ar.reconciliation_difference)}</strong></span></footer>
      </section>

      <section className="credit-erp-section">
        <div className="credit-erp-section-heading"><div><span>TMCUST.CUNUMENT</span><h3>Source-linked accounts</h3></div><Status value={evidence.related_accounts.status} /></div>
        <p>{evidence.related_accounts.explanation}</p>
        <div className="credit-erp-related-grid">{evidence.related_accounts.accounts.map((account) => <article key={account.customer_number}><div><strong>{account.customer_name}</strong><Status value={account.relationship} /></div><span>Customer {account.customer_number} · enterprise {account.enterprise_number || 'not recorded'}</span><dl><div><dt>Credit line</dt><dd>{money.format(account.credit_limit)}</dd></div><div><dt>Balance</dt><dd>{money.format(account.balance)}</dd></div><div><dt>On order</dt><dd>{money.format(account.erp_on_order_aggregate)}</dd></div><div><dt>Partial exposure</dt><dd>{money.format(account.partial_exposure)}</dd></div></dl></article>)}</div>
      </section>

      <section className="credit-erp-section">
        <div className="credit-erp-section-heading"><div><span>Coverage contract</span><h3>Available and deliberately unavailable evidence</h3></div></div>
        <div className="credit-erp-coverage">{evidence.coverage.map((item) => <article key={item.key}><div><strong>{item.label}</strong><Status value={item.status} /></div><p>{item.explanation}</p><small>{item.source || 'No source connected'} · {item.record_count ?? 0} row(s)</small></article>)}</div>
      </section>

      <footer className="credit-erp-governance"><div><strong>Evidence only</strong><span>{evidence.governance.source_authority}</span></div><ul>{evidence.governance.statements.map((statement) => <li key={statement}>{statement}</li>)}</ul></footer>
    </section>
  )
}
