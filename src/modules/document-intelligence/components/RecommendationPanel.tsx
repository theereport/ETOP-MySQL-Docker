import type { LockboxRecommendation } from './lockboxRecommendation'

type Props = {
  recommendation: LockboxRecommendation | null
  loading: boolean
  errorMessage: string
  onLoad: () => void
  onApply: () => void
  onUseFallback: () => void
}

function money(value: string | number) {
  return Number(value || 0).toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
  })
}

function percent(value: number) {
  return `${Math.round(Number(value || 0) * 100)}%`
}

export default function RecommendationPanel({
  recommendation,
  loading,
  errorMessage,
  onLoad,
  onApply,
  onUseFallback,
}: Props) {
  if (!recommendation) {
    return (
      <section className="lockbox-recommendation-panel">
        <div>
          <span>AI CASH APPLICATION</span>
          <h3>Find the best invoice application</h3>
          <p>
            Resolve the ERP customer, load open invoices, and run the
            existing cash-application engine.
          </p>
        </div>

        <button type="button" onClick={onLoad} disabled={loading}>
          {loading ? 'Building recommendation…' : 'Build Recommendation'}
        </button>

        {errorMessage && (
          <p className="lockbox-recommendation-error">
            {errorMessage}
          </p>
        )}
      </section>
    )
  }

  const customer = recommendation.customer_match
  const decision = recommendation.decision

  return (
    <section className="lockbox-recommendation-panel">
      <header>
        <div>
          <span>AI CASH APPLICATION</span>
          <h3>{customer?.customer_name || 'Customer review required'}</h3>
          {customer && (
            <p>
              Customer #{customer.customer_number}
              {' · '}
              {percent(customer.confidence)} customer confidence
            </p>
          )}
        </div>

        <strong>
          {recommendation.status.replaceAll('_', ' ')}
        </strong>
      </header>

      {customer && (
        <div className="lockbox-match-reasons">
          {customer.matched_on.map((item) => (
            <span key={item}>✓ {item}</span>
          ))}
        </div>
      )}

      {decision && (
        <div className="lockbox-intent-summary">
          <div>
            <span>Payment Intent</span>
            <strong>
              {decision.payment_intent.intent_type.replaceAll('_', ' ')}
            </strong>
          </div>
          <div>
            <span>Overall Confidence</span>
            <strong>{percent(decision.overall_confidence)}</strong>
          </div>
        </div>
      )}

      <div className="lockbox-suggestion-table">
        <div className="lockbox-suggestion-row lockbox-suggestion-head">
          <span>Invoice</span>
          <span>Open</span>
          <span>Suggested</span>
        </div>

        {recommendation.suggested_allocations.map((allocation) => (
          <div
            className="lockbox-suggestion-row"
            key={allocation.invoice_number}
          >
            <span>{allocation.invoice_number}</span>
            <span>{money(allocation.open_amount)}</span>
            <span>{money(allocation.suggested_apply_amount)}</span>
          </div>
        ))}
      </div>

      <div className="lockbox-recommendation-totals">
        <span>
          Check <strong>{money(recommendation.check_amount)}</strong>
        </span>
        <span>
          Suggested <strong>{money(recommendation.suggested_total)}</strong>
        </span>
        <span>
          Difference <strong>{money(recommendation.difference)}</strong>
        </span>
      </div>

      <div className="lockbox-recommendation-actions">
        <button
          type="button"
          onClick={onApply}
          disabled={!recommendation.suggested_allocations.length}
        >
          Apply Recommendation
        </button>

        <button type="button" onClick={onUseFallback}>
          Use 9999999999 Fallback
        </button>
      </div>

      {recommendation.decision_reasons.length > 0 && (
        <details>
          <summary>Why ETOP selected this application</summary>
          <ul>
            {recommendation.decision_reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}
