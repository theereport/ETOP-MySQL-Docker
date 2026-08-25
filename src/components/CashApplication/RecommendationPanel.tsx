import type {
  CashApplicationRecommendation,
} from './CashApplication'

type RecommendationPanelProps = {
  recommendation: CashApplicationRecommendation
}

function formatCurrency(value: string | number) {
  const parsedValue = Number(value)

  if (Number.isNaN(parsedValue)) {
    return String(value)
  }

  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(parsedValue)
}

function formatDate(value: string) {
  const date = new Date(`${value}T00:00:00`)

  if (Number.isNaN(date.getTime())) {
    return value
  }

  return new Intl.DateTimeFormat('en-US', {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  }).format(date)
}

function getStatusLabel(
  recommendation: CashApplicationRecommendation,
) {
  if (recommendation.auto_apply_allowed) {
    return 'Ready for Approval'
  }

  if (recommendation.status === 'no_match') {
    return 'No Exact Match'
  }

  if (recommendation.review_required) {
    return 'Manual Review Required'
  }

  return recommendation.status.replaceAll('_', ' ')
}

function RecommendationPanel({
  recommendation,
}: RecommendationPanelProps) {
  const confidencePercent = Math.round(
    recommendation.confidence_score * 100 <= 100
      ? recommendation.confidence_score * 100
      : recommendation.confidence_score,
  )

  const statusClass = recommendation.auto_apply_allowed
    ? 'approved'
    : recommendation.status === 'no_match'
      ? 'no-match'
      : 'review'

  return (
    <section className="cash-recommendation-card">
      <div className="cash-recommendation-heading">
        <div>
          <span
            className={`cash-status-badge ${statusClass}`}
          >
            {getStatusLabel(recommendation)}
          </span>

          <h2>
            {recommendation.explanation?.headline ??
              'Cash Application Recommendation'}
          </h2>

          <p>
            {recommendation.explanation?.summary ??
              recommendation.reasons[0] ??
              'The payment evaluation is complete.'}
          </p>
        </div>

        <div className="cash-confidence">
          <span>Confidence</span>
          <strong>{confidencePercent}%</strong>
          <small>
            {recommendation.review_required
              ? 'Review required'
              : 'Decision supported'}
          </small>
        </div>
      </div>

      <div className="cash-summary-grid">
        <div>
          <span>Customer</span>
          <strong>{recommendation.customer_number}</strong>
        </div>

        <div>
          <span>Payment amount</span>
          <strong>
            {formatCurrency(recommendation.payment_amount)}
          </strong>
        </div>

        <div>
          <span>Payment date</span>
          <strong>
            {formatDate(recommendation.payment_date)}
          </strong>
        </div>

        <div>
          <span>Strategy</span>
          <strong>
            {recommendation.strategy.replaceAll('_', ' ')}
          </strong>
        </div>

        <div>
          <span>Recommended invoices</span>
          <strong>
            {
              recommendation.recommended_invoice_numbers
                .length
            }
          </strong>
        </div>

        <div>
          <span>ERP posting</span>
          <strong>Disabled</strong>
        </div>
      </div>

      <div className="cash-reason-list">
        <strong>Decision reasoning</strong>

        {(recommendation.explanation?.reasoning ??
          recommendation.reasons).map((reason, index) => (
          <div key={`${reason}-${index}`}>
            <span>•</span>
            <p>{reason}</p>
          </div>
        ))}
      </div>

      {recommendation.explanation
        ?.confidence_explanation && (
        <div className="cash-confidence-explanation">
          {
            recommendation.explanation
              .confidence_explanation
          }
        </div>
      )}
    </section>
  )
}

export default RecommendationPanel