import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import {
  createCreditPortfolioReview,
  getCreditPortfolioMonitoring,
} from './api'
import type {
  PortfolioMonitoringItem,
  PortfolioMonitoringResponse,
  PortfolioReviewDisposition,
} from './types'

const money = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
})

const dispositions: Array<{
  value: PortfolioReviewDisposition
  label: string
}> = [
  { value: 'reviewed_no_change', label: 'Reviewed — no change' },
  { value: 'reassessment_needed', label: 'Reassessment needed' },
  { value: 'credit_line_analysis_needed', label: 'Credit-line analysis needed' },
  { value: 'information_requested', label: 'Information requested' },
]

function message(error: unknown): string {
  return error instanceof Error ? error.message : 'Unable to load portfolio monitoring.'
}

function reviewLabel(value: string): string {
  return value.replaceAll('_', ' ')
}

export default function PortfolioMonitoringPanel({
  onOpenCustomer,
}: {
  onOpenCustomer: (customerNumber: number) => void
}) {
  const [data, setData] = useState<PortfolioMonitoringResponse | null>(null)
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [error, setError] = useState('')
  const [filter, setFilter] = useState<'watchlist' | 'all'>('watchlist')
  const [selectedNumber, setSelectedNumber] = useState<number | null>(null)
  const [disposition, setDisposition] = useState<PortfolioReviewDisposition>('reviewed_no_change')
  const [reviewer, setReviewer] = useState('')
  const [notes, setNotes] = useState('')
  const [followUpDate, setFollowUpDate] = useState('')
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [saveMessage, setSaveMessage] = useState('')

  async function load(signal?: AbortSignal) {
    setStatus('loading')
    setError('')
    try {
      const response = await getCreditPortfolioMonitoring(signal)
      setData(response)
      setSelectedNumber((current) => (
        current != null && response.items.some((item) => item.customer_number === current)
          ? current
          : response.items[0]?.customer_number ?? null
      ))
      setStatus('success')
    } catch (loadError) {
      if (signal?.aborted) return
      setError(message(loadError))
      setStatus('error')
    }
  }

  useEffect(() => {
    const controller = new AbortController()
    void getCreditPortfolioMonitoring(controller.signal)
      .then((response) => {
        setData(response)
        setSelectedNumber(response.items[0]?.customer_number ?? null)
        setStatus('success')
      })
      .catch((loadError: unknown) => {
        if (controller.signal.aborted) return
        setError(message(loadError))
        setStatus('error')
      })
    return () => controller.abort()
  }, [])

  const visibleItems = useMemo(
    () => (data?.items ?? []).filter((item) => filter === 'all' || item.watchlist),
    [data, filter],
  )
  const selected = (data?.items ?? []).find(
    (item) => item.customer_number === selectedNumber,
  ) ?? null

  function selectItem(item: PortfolioMonitoringItem) {
    setSelectedNumber(item.customer_number)
    setSaveStatus('idle')
    setSaveMessage('')
  }

  async function submitReview(event: FormEvent) {
    event.preventDefault()
    if (!selected) return
    if (!reviewer.trim() || !notes.trim()) {
      setSaveStatus('error')
      setSaveMessage('Reviewer and notes are required.')
      return
    }
    setSaveStatus('saving')
    setSaveMessage('')
    try {
      await createCreditPortfolioReview(selected.customer_number, {
        disposition,
        reviewer_identity: reviewer.trim(),
        notes: notes.trim(),
        follow_up_date: followUpDate || null,
      })
      setNotes('')
      setFollowUpDate('')
      await load()
      setSaveStatus('success')
      setSaveMessage('Append-only portfolio review recorded. No credit decision or ERP change was made.')
    } catch (saveError) {
      setSaveStatus('error')
      setSaveMessage(message(saveError))
    }
  }

  if (status === 'loading' && !data) {
    return <section className="credit-risk-panel"><p>Building the assessed-customer portfolio…</p></section>
  }
  if (status === 'error' && !data) {
    return (
      <section className="credit-risk-panel credit-risk-error-banner">
        <strong>Portfolio monitoring is unavailable.</strong>
        <p>{error}</p>
        <button type="button" onClick={() => void load()}>Retry</button>
      </section>
    )
  }

  return (
    <div className="credit-portfolio-monitoring">
      <section className="credit-risk-panel credit-portfolio-heading">
        <div>
          <span className="credit-risk-kicker">Credit Risk Increment 4</span>
          <h2>Portfolio Monitoring &amp; Review Cadence</h2>
          <p>
            Organize saved assessments, current partial exposure, proposals, and professional
            follow-up evidence without turning draft bands into automatic policy.
          </p>
        </div>
        <button type="button" onClick={() => void load()} disabled={status === 'loading'}>
          {status === 'loading' ? 'Refreshing…' : 'Refresh portfolio'}
        </button>
      </section>

      {data && (
        <>
          <section className="credit-portfolio-metrics" aria-label="Portfolio summary">
            <article><span>Assessed customers</span><strong>{data.summary.assessed_customer_count}</strong></article>
            <article><span>Draft watchlist</span><strong>{data.summary.watchlist_customer_count}</strong></article>
            <article><span>Overdue reviews</span><strong>{data.summary.overdue_review_count}</strong></article>
            <article><span>Partial exposure</span><strong>{money.format(data.summary.partial_exposure_total)}</strong></article>
            <article><span>Live-source gaps</span><strong>{data.summary.degraded_live_source_count}</strong></article>
          </section>

          <section className="credit-risk-panel credit-portfolio-concentration">
            <div className="credit-risk-panel-heading">
              <div>
                <span className="credit-risk-kicker">Available evidence only</span>
                <h3>Draft-band concentration</h3>
              </div>
              <small>{data.summary.partial_exposure_customer_count} customers with partial exposure</small>
            </div>
            <div className="credit-portfolio-band-grid">
              {data.band_concentration.map((band) => (
                <article key={band.band_meaning}>
                  <strong>{band.band_meaning}</strong>
                  <span>{band.customer_count} customer{band.customer_count === 1 ? '' : 's'}</span>
                  <span>{money.format(band.partial_exposure)}</span>
                  <small>{band.exposure_share_percent == null ? 'Share unavailable' : `${band.exposure_share_percent}% of available partial exposure`}</small>
                </article>
              ))}
            </div>
          </section>

          <div className="credit-portfolio-grid">
            <section className="credit-risk-panel credit-portfolio-queue">
              <div className="credit-risk-panel-heading">
                <div><span className="credit-risk-kicker">Professional work queue</span><h3>Review cadence</h3></div>
                <div className="credit-portfolio-filter" role="group" aria-label="Portfolio filter">
                  <button type="button" className={filter === 'watchlist' ? 'is-active' : ''} onClick={() => setFilter('watchlist')}>Draft watchlist</button>
                  <button type="button" className={filter === 'all' ? 'is-active' : ''} onClick={() => setFilter('all')}>All assessed</button>
                </div>
              </div>
              {visibleItems.length === 0 ? (
                <p className="credit-risk-empty">No customers meet this view.</p>
              ) : (
                <div className="credit-portfolio-list">
                  {visibleItems.map((item) => (
                    <button
                      type="button"
                      key={item.customer_number}
                      className={item.customer_number === selectedNumber ? 'is-selected' : ''}
                      onClick={() => selectItem(item)}
                    >
                      <span className="credit-portfolio-rank">#{item.rank}</span>
                      <span><strong>{item.customer_name}</strong><small>{item.customer_number} · {item.band_meaning}</small></span>
                      <span><strong>{item.latest_manual_rating}/10</strong><small>{reviewLabel(item.review_state)}</small></span>
                      <span><strong>{item.partial_exposure == null ? 'Unavailable' : money.format(item.partial_exposure)}</strong><small>{item.days_to_review < 0 ? `${Math.abs(item.days_to_review)} days overdue` : `${item.days_to_review} days to review`}</small></span>
                    </button>
                  ))}
                </div>
              )}
            </section>

            <section className="credit-risk-panel credit-portfolio-review">
              {!selected ? <p className="credit-risk-empty">Select a customer to review.</p> : (
                <>
                  <div className="credit-risk-panel-heading">
                    <div><span className="credit-risk-kicker">Selected assessed customer</span><h3>{selected.customer_name}</h3><small>{selected.customer_number}</small></div>
                    <button type="button" onClick={() => onOpenCustomer(selected.customer_number)}>Open Risk 360</button>
                  </div>
                  <dl className="credit-portfolio-detail-grid">
                    <div><dt>Next assessment review</dt><dd>{selected.next_review_date}</dd></div>
                    <div><dt>Latest proposal</dt><dd>{selected.latest_professional_proposal ? money.format(selected.latest_professional_proposal.proposed_credit_line) : 'None recorded'}</dd></div>
                    <div><dt>Latest portfolio review</dt><dd>{selected.latest_portfolio_review ? reviewLabel(selected.latest_portfolio_review.disposition) : 'None recorded'}</dd></div>
                    <div><dt>Exposure share</dt><dd>{selected.partial_exposure_share_percent == null ? 'Unavailable' : `${selected.partial_exposure_share_percent}%`}</dd></div>
                  </dl>
                  <form className="credit-portfolio-review-form" onSubmit={submitReview}>
                    <label>Review outcome<select value={disposition} onChange={(event) => setDisposition(event.target.value as PortfolioReviewDisposition)}>{dispositions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
                    <label>Reviewer<input value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder="Person recording the review" /></label>
                    <label>Follow-up date (optional)<input type="date" value={followUpDate} onChange={(event) => setFollowUpDate(event.target.value)} /></label>
                    <label className="credit-portfolio-notes">Notes<textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={4} placeholder="Evidence reviewed, gaps, and the professional next step" /></label>
                    <p className="credit-risk-decision-boundary">Operator-supplied workflow evidence only · no decision, notification, or ERP write</p>
                    <button className="credit-risk-primary-button" type="submit" disabled={saveStatus === 'saving'}>{saveStatus === 'saving' ? 'Recording…' : 'Record portfolio review'}</button>
                    {saveMessage && <p className={saveStatus === 'error' ? 'credit-risk-error-text' : 'credit-risk-success-text'}>{saveMessage}</p>}
                  </form>
                </>
              )}
            </section>
          </div>

          <section className="credit-risk-panel credit-portfolio-boundary">
            <strong>Coverage and authority boundary</strong>
            {data.warnings.map((warning) => <p key={warning}>{warning}</p>)}
          </section>
        </>
      )}
    </div>
  )
}
