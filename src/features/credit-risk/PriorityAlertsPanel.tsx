import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getCreditRiskPriorityAlerts } from './api'
import type {
  PriorityAlertsResponse,
  PriorityPortfolioFilter,
  PriorityPortfolioItem,
} from './types'

type PriorityStatus = 'loading' | 'success' | 'error'

const moneyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
})

const dateFormatter = new Intl.DateTimeFormat('en-US', {
  dateStyle: 'medium',
})

const dateTimeFormatter = new Intl.DateTimeFormat('en-US', {
  dateStyle: 'medium',
  timeStyle: 'short',
})

function formatMoney(value: number | null): string {
  return value == null ? 'Unavailable' : moneyFormatter.format(value)
}

function formatDate(value: string | null): string {
  if (!value) {
    return 'Unavailable'
  }
  const parsed = new Date(
    /^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00:00` : value,
  )
  return Number.isNaN(parsed.valueOf()) ? value : dateFormatter.format(parsed)
}

function formatDateTime(value: string | null): string {
  if (!value) {
    return 'Unavailable'
  }
  const parsed = new Date(value)
  return Number.isNaN(parsed.valueOf()) ? value : dateTimeFormatter.format(parsed)
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : 'Unable to load the assessed-customer priority projection.'
}

function readable(value: string): string {
  return value.replaceAll('_', ' ')
}

function PriorityItemCard({
  item,
  onOpenCustomer,
}: {
  item: PriorityPortfolioItem
  onOpenCustomer: (customerNumber: number) => void
}) {
  const operationalAlerts = item.alerts.filter(
    (alert) => alert.category !== 'source_gap',
  )

  return (
    <article className="credit-risk-priority-item">
      <div className="credit-risk-priority-rank" aria-label={`Priority position ${item.rank}`}>
        <span>Position</span>
        <strong>{item.rank}</strong>
      </div>

      <div className="credit-risk-priority-main">
        <div className="credit-risk-priority-item-heading">
          <div>
            <span className={`credit-risk-priority-category credit-risk-priority-category--${item.ordering_evidence.review_state}`}>
              {readable(item.priority_category)}
            </span>
            <h3>{item.customer_name}</h3>
            <p>
              Customer {item.customer_number} · Name from{' '}
              {readable(item.customer_name_source)}
            </p>
          </div>
          <div className="credit-risk-priority-rating">
            <span>Manual rating</span>
            <strong>{item.latest_assessment.manual_rating}</strong>
            <small>{item.latest_assessment.band.meaning}</small>
          </div>
        </div>

        {item.draft_band_attention && (
          <div className="credit-risk-draft-attention">
            <strong>Draft high-risk band attention</strong>
            <span>
              Saved Product Owner draft taxonomy {item.latest_assessment.manual_rating} ·{' '}
              {item.latest_assessment.band.meaning}. This is not approved automatic policy.
            </span>
          </div>
        )}

        <div className="credit-risk-priority-facts">
          <div>
            <span>Next review</span>
            <strong>{formatDate(item.ordering_evidence.next_review_date)}</strong>
            <small>{readable(item.ordering_evidence.review_state)}</small>
          </div>
          <div>
            <span>Assessment change</span>
            <strong>{readable(item.ordering_evidence.deterioration_state)}</strong>
            <small>
              {item.ordering_evidence.manual_rating_change == null
                ? 'No prior assessment'
                : `${item.ordering_evidence.manual_rating_change >= 0 ? '+' : ''}${item.ordering_evidence.manual_rating_change} rating change`}
            </small>
          </div>
          <div>
            <span>Current partial exposure</span>
            <strong>{formatMoney(item.live_exposure.partial_exposure)}</strong>
            <small>{readable(item.ordering_evidence.over_line_state)}</small>
          </div>
          <div>
            <span>Live source</span>
            <strong>{readable(item.live_exposure.status)}</strong>
            <small>{formatDateTime(item.live_exposure.retrieved_at)}</small>
          </div>
        </div>

        {item.live_exposure.status !== 'available' && (
          <div className="credit-risk-priority-source-gap" role="status">
            <strong>Live exposure degraded</strong>
            <span>{item.live_exposure.explanation}</span>
          </div>
        )}

        <div className="credit-risk-priority-alerts">
          <div>
            <strong>{operationalAlerts.length} operational signal{operationalAlerts.length === 1 ? '' : 's'}</strong>
            <small>Every signal retains its evidence class and source reference.</small>
          </div>
          {item.alerts.map((alert) => (
            <details key={alert.code} className={`credit-risk-priority-alert credit-risk-priority-alert--${alert.category}`}>
              <summary>{alert.title}</summary>
              <p>{alert.explanation}</p>
              <small>
                Evidence: {readable(alert.evidence_class)}
                {alert.assessment_ids.length > 0
                  ? ` · Assessment ${alert.assessment_ids.join(', ')}`
                  : ''}
              </small>
              {alert.evidence_sha256.map((hash) => (
                <code key={hash}>SHA-256 {hash}</code>
              ))}
            </details>
          ))}
        </div>

        <details className="credit-risk-priority-reasons">
          <summary>Why this operational position?</summary>
          <ol>
            {item.ordering_reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ol>
        </details>

        <div className="credit-risk-priority-actions">
          <span>
            Evidence view only · no recommendation, approval, notification, or ERP action
          </span>
          <button
            type="button"
            className="credit-risk-primary-button"
            onClick={() => onOpenCustomer(item.customer_number)}
          >
            Open Risk 360
          </button>
        </div>
      </div>
    </article>
  )
}

export default function PriorityAlertsPanel({
  onOpenCustomer,
}: {
  onOpenCustomer: (customerNumber: number) => void
}) {
  const [status, setStatus] = useState<PriorityStatus>('loading')
  const [response, setResponse] = useState<PriorityAlertsResponse | null>(null)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState<PriorityPortfolioFilter>('draft_band_attention')
  const requestGeneration = useRef(0)
  const requestAbort = useRef<AbortController | null>(null)

  const runRequest = useCallback((controller: AbortController, generation: number) => {
    getCreditRiskPriorityAlerts(controller.signal)
      .then((result) => {
        if (requestGeneration.current !== generation) {
          return
        }
        setResponse(result)
        setStatus('success')
      })
      .catch((requestError) => {
        if (isAbortError(requestError) || requestGeneration.current !== generation) {
          return
        }
        setResponse(null)
        setStatus('error')
        setError(errorMessage(requestError))
      })
  }, [])

  const retry = useCallback(() => {
    requestAbort.current?.abort()
    const controller = new AbortController()
    requestAbort.current = controller
    const generation = requestGeneration.current + 1
    requestGeneration.current = generation
    setStatus('loading')
    setError('')
    runRequest(controller, generation)
  }, [runRequest])

  useEffect(() => {
    const controller = new AbortController()
    requestAbort.current = controller
    const generation = requestGeneration.current + 1
    requestGeneration.current = generation
    runRequest(controller, generation)
    return () => {
      requestAbort.current?.abort()
      requestGeneration.current += 1
    }
  }, [runRequest])

  const visibleItems = useMemo(() => {
    if (!response) {
      return []
    }
    return filter === 'draft_band_attention'
      ? response.items.filter((item) => item.draft_band_attention)
      : response.items
  }, [filter, response])

  if (status === 'loading') {
    return (
      <div className="credit-risk-loading" role="status">
        <span className="credit-risk-spinner" />
        <div>
          <strong>Building assessed-customer priority and alerts</strong>
          <p>Reading immutable manual assessments and current Customer 360 exposure where available…</p>
        </div>
      </div>
    )
  }

  if (status === 'error') {
    return (
      <div className="credit-risk-message credit-risk-message--error" role="alert">
        <span>{error}</span>
        <button type="button" onClick={retry}>Retry priority and alerts</button>
      </div>
    )
  }

  if (!response) {
    return null
  }

  return (
    <section className="credit-risk-priority-shell">
      <div className="credit-risk-priority-intro">
        <div>
          <span className="credit-risk-kicker">Assessed-customer portfolio</span>
          <h2>Priority &amp; Alerts</h2>
          <p>{response.coverage_statement}</p>
        </div>
        <div>
          <button type="button" onClick={retry}>Refresh current evidence</button>
          <small>As of {formatDate(response.as_of_date)}</small>
        </div>
      </div>

      <div className="credit-risk-priority-boundary">
        <strong>Operational ordering—not an automatic credit decision</strong>
        <p>{response.ordering.explanation}</p>
        <details>
          <summary>Stable ordering conditions</summary>
          <ol>
            {response.ordering.ordered_conditions.map((condition) => (
              <li key={condition}>{condition}</li>
            ))}
          </ol>
          <p>{response.ordering.unavailable_over_line_treatment}</p>
        </details>
      </div>

      <div className="credit-risk-priority-summary">
        <div><span>Assessed customers</span><strong>{response.summary.assessed_customer_count}</strong></div>
        <div><span>Draft-band attention</span><strong>{response.summary.draft_band_attention_count}</strong></div>
        <div><span>Overdue reviews</span><strong>{response.summary.overdue_review_count}</strong></div>
        <div><span>Due today</span><strong>{response.summary.due_today_review_count}</strong></div>
        <div><span>Deteriorated</span><strong>{response.summary.deterioration_count}</strong></div>
        <div><span>Observed over line</span><strong>{response.summary.over_line_count}</strong></div>
        <div><span>Live source degraded</span><strong>{response.summary.live_source_degraded_count}</strong></div>
      </div>

      <div className="credit-risk-priority-filter" aria-label="Priority portfolio filter">
        <div>
          <strong>Portfolio view</strong>
          <small>
            Draft-band attention isolates saved ratings 7–10 using their exact Product Owner draft band snapshots.
          </small>
        </div>
        <div>
          <button
            type="button"
            className={filter === 'draft_band_attention' ? 'is-active' : ''}
            aria-pressed={filter === 'draft_band_attention'}
            onClick={() => setFilter('draft_band_attention')}
          >
            Draft high-risk bands ({response.summary.draft_band_attention_count})
          </button>
          <button
            type="button"
            className={filter === 'all_assessed' ? 'is-active' : ''}
            aria-pressed={filter === 'all_assessed'}
            onClick={() => setFilter('all_assessed')}
          >
            All assessed ({response.summary.assessed_customer_count})
          </button>
        </div>
      </div>

      <div className="credit-risk-priority-unavailable">
        <div>
          <strong>Unavailable alert sources</strong>
          <span>These capabilities emit no alerts until governed sources are connected.</span>
        </div>
        {response.unavailable_capabilities.map((capability) => (
          <article key={capability.code}>
            <strong>{capability.label}</strong>
            <span>{readable(capability.status)}</span>
            <p>{capability.explanation}</p>
          </article>
        ))}
      </div>

      {response.summary.assessed_customer_count === 0 && (
        <div className="credit-risk-empty-workspace">
          <strong>No assessed customers are available for priority ordering.</strong>
          <p>
            Record a manual assessment in Customer Risk 360 to add that customer to this portfolio.
            Unassessed customers are excluded; ETOP does not assign placeholder ratings.
          </p>
        </div>
      )}

      {response.summary.assessed_customer_count > 0 && visibleItems.length === 0 && (
        <div className="credit-risk-empty-workspace">
          <strong>No customers match the draft high-risk band filter.</strong>
          <p>
            The assessed portfolio remains available under All assessed. ETOP did not infer or manufacture a high-risk label.
          </p>
        </div>
      )}

      {visibleItems.length > 0 && (
        <div className="credit-risk-priority-list">
          {visibleItems.map((item) => (
            <PriorityItemCard
              key={item.customer_number}
              item={item}
              onOpenCustomer={onOpenCustomer}
            />
          ))}
        </div>
      )}
    </section>
  )
}
