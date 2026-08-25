import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  createCreditLineProposal,
  getCreditLineIntelligence,
  getCreditLineProposals,
} from './api'
import type {
  CreditLineIntelligenceResponse,
  CreditLineMetric,
  CreditLineProposal,
} from './types'

type LoadState = 'loading' | 'success' | 'error'

const money = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
})

const dateTime = new Intl.DateTimeFormat('en-US', {
  dateStyle: 'medium',
  timeStyle: 'short',
})

function formatMoney(value: number | null): string {
  return value == null ? 'Unavailable' : money.format(value)
}

function formatDateTime(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.valueOf()) ? value : dateTime.format(parsed)
}

function message(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function Metric({ label, metric }: { label: string; metric: CreditLineMetric }) {
  return (
    <article className={`credit-line-metric credit-line-metric--${metric.status}`}>
      <div>
        <span>{label}</span>
        <small>{metric.status}</small>
      </div>
      <strong>{formatMoney(metric.value)}</strong>
      <p>{metric.explanation}</p>
      <small>{metric.source || 'No governed source'}{metric.as_of ? ` · ${formatDateTime(metric.as_of)}` : ''}</small>
    </article>
  )
}

function ProposalHistory({ proposals }: { proposals: CreditLineProposal[] }) {
  return (
    <section className="credit-risk-panel credit-line-history">
      <div className="credit-risk-panel-heading">
        <div>
          <span className="credit-risk-kicker">Append-only professional record</span>
          <h2>Credit-line proposal history</h2>
        </div>
        <span className="credit-risk-count">{proposals.length}</span>
      </div>
      {proposals.length === 0 ? (
        <p className="credit-risk-empty">No professional credit-line proposals have been recorded.</p>
      ) : (
        <div className="credit-line-history-list">
          {proposals.map((proposal) => (
            <article key={proposal.proposal_id}>
              <div>
                <strong>{formatMoney(proposal.proposed_credit_line)}</strong>
                <span>Proposed by {proposal.analyst_identity}</span>
                <small>Recorded {formatDateTime(proposal.created_at)} · Review {proposal.review_date}</small>
              </div>
              <p>{proposal.rationale}</p>
              <dl className="credit-risk-definition-list">
                <div><dt>Current line at capture</dt><dd>{formatMoney(proposal.current_credit_line)}</dd></div>
                <div><dt>Analytical reference</dt><dd>{formatMoney(proposal.analytical_reference_line)}</dd></div>
                <div><dt>Classification</dt><dd>{proposal.proposal_classification.replaceAll('_', ' ')}</dd></div>
                <div><dt>Approval status</dt><dd>{proposal.approval_status.replaceAll('_', ' ')}</dd></div>
              </dl>
              <p className="credit-risk-decision-boundary">
                Decision effect: {proposal.decision_effect}. ERP write: {proposal.erp_write ? 'enabled' : 'not permitted'}.
              </p>
              <small className="credit-line-hash">Evidence SHA-256 <code>{proposal.evidence_snapshot_sha256}</code></small>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

export default function CreditLineIntelligencePanel({
  customerNumber,
}: {
  customerNumber: number
}) {
  const [intelligence, setIntelligence] = useState<CreditLineIntelligenceResponse | null>(null)
  const [proposals, setProposals] = useState<CreditLineProposal[]>([])
  const [loadState, setLoadState] = useState<LoadState>('loading')
  const [loadError, setLoadError] = useState('')
  const [saveState, setSaveState] = useState<'idle' | 'loading' | 'success' | 'error'>('idle')
  const [saveMessage, setSaveMessage] = useState('')
  const [amount, setAmount] = useState('')
  const [reviewDate, setReviewDate] = useState('')
  const [analyst, setAnalyst] = useState('')
  const [rationale, setRationale] = useState('')

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoadState('loading')
    setLoadError('')
    try {
      const [current, history] = await Promise.all([
        getCreditLineIntelligence(customerNumber, signal),
        getCreditLineProposals(customerNumber, signal),
      ])
      setIntelligence(current)
      setProposals(history.proposals)
      setLoadState('success')
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return
      setLoadState('error')
      setLoadError(message(error, 'Unable to load credit-line intelligence.'))
    }
  }, [customerNumber])

  useEffect(() => {
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => {
      void load(controller.signal)
    }, 0)
    return () => {
      window.clearTimeout(timeoutId)
      controller.abort()
    }
  }, [load])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const proposed = Number(amount)
    if (!Number.isFinite(proposed) || proposed < 0 || !reviewDate || !analyst.trim() || !rationale.trim()) {
      setSaveState('error')
      setSaveMessage('Enter a non-negative proposed amount, review date, analyst identity, and professional rationale.')
      return
    }
    setSaveState('loading')
    setSaveMessage('')
    try {
      await createCreditLineProposal(customerNumber, {
        proposed_credit_line: proposed,
        review_date: reviewDate,
        analyst_identity: analyst.trim(),
        rationale: rationale.trim(),
      })
      const [current, history] = await Promise.all([
        getCreditLineIntelligence(customerNumber),
        getCreditLineProposals(customerNumber),
      ])
      setIntelligence(current)
      setProposals(history.proposals)
      setAmount('')
      setReviewDate('')
      setAnalyst('')
      setRationale('')
      setSaveState('success')
      setSaveMessage('Professional proposal saved. It did not approve or change the customer credit line.')
    } catch (error) {
      setSaveState('error')
      setSaveMessage(message(error, 'Unable to save the credit-line proposal.'))
    }
  }

  if (loadState === 'loading') {
    return <div className="credit-risk-loading" role="status"><span className="credit-risk-spinner" /><div><strong>Loading credit-line evidence</strong><p>Reading live sales, balance, and local proposal history…</p></div></div>
  }
  if (loadState === 'error' || !intelligence) {
    return <div className="credit-risk-message credit-risk-message--error" role="alert"><span>{loadError}</span><button type="button" onClick={() => void load()}>Retry</button></div>
  }

  const { sales, capacity, analytical_reference: reference } = intelligence
  return (
    <div className="credit-line-workspace">
      <section className="credit-line-metric-grid" aria-label="Credit-line evidence">
        <Metric label="Current credit line" metric={capacity.current_credit_line} />
        <Metric label="Partial exposure" metric={capacity.partial_exposure} />
        <Metric label="Partial available credit" metric={capacity.available_credit} />
        <Metric label="High balance" metric={capacity.high_balance} />
        <Metric label="Monthly high balance" metric={capacity.monthly_high_balance} />
        <Metric label="Average daily balance" metric={capacity.average_daily_balance} />
        <Metric label="Month-to-date sales" metric={sales.month_to_date} />
        <Metric label="Year-to-date sales" metric={sales.year_to_date} />
        <Metric label="Last-year sales" metric={sales.last_year} />
        <Metric label="Annualized sales" metric={sales.annualized_sales} />
      </section>

      <section className="credit-risk-panel credit-line-reference">
        <div className="credit-risk-panel-heading"><div><span className="credit-risk-kicker">Existing analytical inference</span><h2>Two-month line reference</h2></div><span className={`credit-risk-source-tag credit-risk-source-tag--${reference.status}`}>{reference.status}</span></div>
        <strong>{formatMoney(reference.amount)}</strong>
        <code>{reference.formula}</code>
        <p>{reference.explanation}</p>
        <div className="credit-risk-authority-warning"><strong>Policy boundary</strong><p>This reference is not an automatic recommendation or approved policy. It cannot change a customer line or write to ERP.</p></div>
      </section>

      <section className="credit-risk-panel credit-line-gaps">
        <div className="credit-risk-panel-heading"><div><span className="credit-risk-kicker">Decision-quality limits</span><h2>Unavailable governed inputs</h2></div><span className="credit-risk-count">{intelligence.gaps.length}</span></div>
        <div>{intelligence.gaps.map((gap) => <article key={gap.code}><strong>{gap.label}</strong><span>{gap.status}</span><p>{gap.explanation}</p></article>)}</div>
      </section>

      <section className="credit-risk-panel credit-line-proposal-form">
        <div className="credit-risk-panel-heading"><div><span className="credit-risk-kicker">Professional judgment</span><h2>Record a credit-line proposal</h2></div></div>
        <form onSubmit={submit} noValidate>
          <div className="credit-line-form-grid">
            <label><span>Proposed credit line</span><input type="number" min="0" step="0.01" value={amount} onChange={(event) => setAmount(event.target.value)} disabled={saveState === 'loading'} /></label>
            <label><span>Review date</span><input type="date" value={reviewDate} onChange={(event) => setReviewDate(event.target.value)} disabled={saveState === 'loading'} /></label>
            <label><span>Analyst identity</span><input type="text" maxLength={200} value={analyst} onChange={(event) => setAnalyst(event.target.value)} disabled={saveState === 'loading'} /></label>
          </div>
          <label><span>Professional rationale</span><textarea rows={5} maxLength={5000} value={rationale} onChange={(event) => setRationale(event.target.value)} disabled={saveState === 'loading'} /></label>
          <div className="credit-risk-authority-warning"><strong>Recommendation, not execution</strong><p>The identity is operator supplied and authority is not independently verified. Saving creates an append-only professional recommendation only—no decision, approval, notification, credit hold, order release, line change, or ERP write.</p></div>
          {saveMessage && <div className={`credit-risk-message credit-risk-message--${saveState === 'error' ? 'error' : 'success'}`} role={saveState === 'error' ? 'alert' : 'status'}>{saveMessage}</div>}
          <button className="credit-risk-primary-button" type="submit" disabled={saveState === 'loading'}>{saveState === 'loading' ? 'Saving proposal…' : 'Save append-only proposal'}</button>
        </form>
      </section>

      <ProposalHistory proposals={proposals} />
      <footer className="credit-risk-workspace-footer"><strong>Governance boundary</strong><span>{intelligence.governance.statements.join(' ')}</span></footer>
    </div>
  )
}
