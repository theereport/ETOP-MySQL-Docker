import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import {
  generateCustomerAiSummary,
  getCustomerRiskReview,
  getCustomerSummary,
  searchCustomers,
} from './api'
import type {
  CustomerRiskReviewItem,
  CustomerRiskReviewResponse,
  CustomerSearchResult,
  CustomerSummary,
} from './types'
import { buildRecommendations, calculateHealth } from './intelligence'
import './Customer360.css'

type Tab =
  | 'overview'
  | 'financial'
  | 'sales'
  | 'timeline'
  | 'documents'
  | 'notes'
  | 'relationships'
  | 'ai'

type CustomerWorkspaceView = 'search' | 'risk-review'

type Customer360Props = {
  initialView?: CustomerWorkspaceView
  initialCustomerNumber?: string
}

const money = (value: number | null | undefined) =>
  new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(value ?? 0)

const pct = (value: number | null | undefined) =>
  value == null ? 'N/A' : `${value.toFixed(1)}%`

const isRiskCustomer = (
  customer: CustomerSearchResult | CustomerRiskReviewItem,
): customer is CustomerRiskReviewItem => 'risk_priority' in customer

export default function Customer360({
  initialView = 'search',
  initialCustomerNumber,
}: Customer360Props) {
  const parsedInitialCustomer = Number(initialCustomerNumber)
  const hasInitialCustomer =
    Number.isFinite(parsedInitialCustomer) &&
    parsedInitialCustomer > 0

  const [query, setQuery] = useState(
    hasInitialCustomer ? String(parsedInitialCustomer) : '',
  )
  const [viewMode, setViewMode] =
    useState<CustomerWorkspaceView>(initialView)
  const [results, setResults] = useState<
    Array<CustomerSearchResult | CustomerRiskReviewItem>
  >([])
  const [riskReview, setRiskReview] =
    useState<CustomerRiskReviewResponse | null>(null)
  const [selected, setSelected] = useState<number | null>(
    hasInitialCustomer ? parsedInitialCustomer : null,
  )
  const [summary, setSummary] = useState<CustomerSummary | null>(null)
  const [tab, setTab] = useState<Tab>('overview')
  const [listBusy, setListBusy] = useState(
    initialView === 'risk-review',
  )
  const [customerBusy, setCustomerBusy] = useState(hasInitialCustomer)
  const [error, setError] = useState('')
  const [ai, setAi] = useState('')
  const [aiBusy, setAiBusy] = useState(false)

  const health = useMemo(
    () => (summary ? calculateHealth(summary) : null),
    [summary],
  )
  const recommendations = useMemo(
    () =>
      summary && health
        ? buildRecommendations(summary, health)
        : [],
    [summary, health],
  )

  async function loadRiskReview(signal?: AbortSignal) {
    setListBusy(true)
    setError('')
    setViewMode('risk-review')
    setQuery('')
    setSummary(null)
    setSelected(null)
    setCustomerBusy(false)

    try {
      const response = await getCustomerRiskReview(signal)
      setRiskReview(response)
      setResults(response.customers)
      setCustomerBusy(response.customers.length > 0)
      setSelected(response.customers[0]?.customer_number ?? null)
    } catch (requestError) {
      if (
        requestError instanceof DOMException &&
        requestError.name === 'AbortError'
      ) {
        return
      }

      setRiskReview(null)
      setResults([])
      setCustomerBusy(false)
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Unable to load the customer priority queue.',
      )
    } finally {
      if (!signal?.aborted) {
        setListBusy(false)
      }
    }
  }

  useEffect(() => {
    if (initialView !== 'risk-review') {
      return
    }

    const controller = new AbortController()

    getCustomerRiskReview(controller.signal)
      .then((response) => {
        setRiskReview(response)
        setResults(response.customers)
        setCustomerBusy(response.customers.length > 0)
        setSelected(response.customers[0]?.customer_number ?? null)
      })
      .catch((requestError) => {
        if (
          requestError instanceof DOMException &&
          requestError.name === 'AbortError'
        ) {
          return
        }

        setRiskReview(null)
        setResults([])
        setError(
          requestError instanceof Error
            ? requestError.message
            : 'Unable to load the customer priority queue.',
        )
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setListBusy(false)
        }
      })

    return () => controller.abort()
  }, [initialView])

  function selectCustomer(customerNumber: number) {
    if (customerNumber === selected && summary) {
      return
    }

    setCustomerBusy(true)
    setSummary(null)
    setError('')
    setSelected(customerNumber)
  }

  async function search(event?: FormEvent) {
    event?.preventDefault()

    if (!query.trim()) {
      return
    }

    setListBusy(true)
    setError('')
    setViewMode('search')
    setRiskReview(null)
    setSelected(null)
    setSummary(null)
    setCustomerBusy(false)

    try {
      const response = await searchCustomers(query.trim())
      setResults(response.customers)

      if (response.customers.length === 1) {
        selectCustomer(response.customers[0].customer_number)
      }
    } catch (requestError) {
      setResults([])
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Search failed.',
      )
    } finally {
      setListBusy(false)
    }
  }

  useEffect(() => {
    if (selected === null) {
      return
    }

    const controller = new AbortController()

    getCustomerSummary(selected, controller.signal)
      .then((customer) => {
        setSummary(customer)
        setAi('')
        setTab('overview')
      })
      .catch((requestError) => {
        if (
          requestError instanceof DOMException &&
          requestError.name === 'AbortError'
        ) {
          return
        }

        setError(
          requestError instanceof Error
            ? requestError.message
            : 'Unable to load customer.',
        )
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setCustomerBusy(false)
        }
      })

    return () => controller.abort()
  }, [selected])

  async function refreshAi() {
    if (!summary || !health) {
      return
    }

    setAiBusy(true)
    setError('')

    try {
      const response = await generateCustomerAiSummary({
        customer: summary,
        health,
        recommendations,
      })
      setAi(response.summary)
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'AI summary failed.',
      )
    } finally {
      setAiBusy(false)
    }
  }

  const tabs: Tab[] = [
    'overview',
    'financial',
    'sales',
    'timeline',
    'documents',
    'notes',
    'relationships',
    'ai',
  ]

  const emptyListMessage = listBusy
    ? viewMode === 'risk-review'
      ? 'Loading the live priority queue…'
      : 'Searching customers…'
    : viewMode === 'risk-review'
      ? 'No customers currently meet the review thresholds.'
      : 'Search to begin.'

  return (
    <section className="customer360-shell">
      <header className="customer360-header">
        <div>
          <p className="customer360-eyebrow">
            Enterprise Object Workspace
          </p>
          <h1>Customer Intelligence</h1>
          <p>
            Credit, sales, risk, activity, and local AI in one
            explainable workspace.
          </p>
        </div>

        <form className="customer360-search" onSubmit={search}>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Customer number, name, route, phone, email..."
          />
          <button disabled={listBusy}>
            {listBusy && viewMode === 'search' ? 'Working...' : 'Search'}
          </button>
        </form>
      </header>

      {error && <div className="customer360-error">{error}</div>}

      <div className="customer360-layout">
        <aside className="customer360-results">
          <div className="customer360-section-heading">
            <div>
              <h2>
                {viewMode === 'risk-review'
                  ? 'Priority review'
                  : 'Customers'}
              </h2>
              {viewMode === 'risk-review' && (
                <small>Highest risk first</small>
              )}
            </div>
            <span>{results.length}</span>
          </div>

          {viewMode === 'risk-review' && (
            <div className="customer360-review-summary">
              <div>
                <strong>Live credit-risk queue</strong>
                <span>
                  {riskReview
                    ? `${riskReview.threshold_percent}%+ utilization or serious aging`
                    : 'Loading verified account exposure and aging'}
                </span>
              </div>
              <button
                type="button"
                onClick={() => void loadRiskReview()}
                disabled={listBusy}
              >
                {listBusy ? 'Loading…' : 'Refresh'}
              </button>
            </div>
          )}

          {results.length === 0 ? (
            <div className="customer360-empty" aria-live="polite">
              {emptyListMessage}
            </div>
          ) : (
            <div className="customer360-result-list">
              {results.map((customer) => {
                const riskCustomer = isRiskCustomer(customer)
                  ? customer
                  : null

                return (
                  <button
                    key={customer.customer_number}
                    type="button"
                    className={`customer360-result ${
                      selected === customer.customer_number
                        ? 'customer360-result--selected'
                        : ''
                    }`}
                    onClick={() =>
                      selectCustomer(customer.customer_number)
                    }
                  >
                    <div>
                      <strong>{customer.customer_name}</strong>
                      <span>#{customer.customer_number}</span>
                    </div>

                    {riskCustomer ? (
                      <>
                        <div className="customer360-risk-line">
                          <span
                            className={`customer360-risk-priority customer360-risk-priority--${riskCustomer.risk_priority.toLowerCase()}`}
                          >
                            #{riskCustomer.rank}{' '}
                            {riskCustomer.risk_priority}
                          </span>
                          <b>Risk {riskCustomer.risk_score}</b>
                        </div>
                        <p className="customer360-risk-reason">
                          {riskCustomer.risk_reasons[0]}
                        </p>
                      </>
                    ) : (
                      <small>
                        Route {customer.route_code || '—'} · Store{' '}
                        {customer.store_number ?? '—'}
                      </small>
                    )}

                    <div className="customer360-result-status">
                      <span>{money(customer.exposure)} exposure</span>
                      <b
                        className={
                          customer.is_over_limit ? 'danger' : 'good'
                        }
                      >
                        {pct(customer.utilization_percent)}
                      </b>
                    </div>

                    {riskCustomer && (
                      <div className="customer360-past-due">
                        <span>
                          {money(riskCustomer.past_due_amount)} past due
                        </span>
                        <span>
                          {money(riskCustomer.days_60_plus)} at 60+ days
                        </span>
                      </div>
                    )}
                  </button>
                )
              })}
            </div>
          )}
        </aside>

        <main className="customer360-main">
          {!summary || !health ? (
            <div className="customer360-empty customer360-empty--large">
              {customerBusy
                ? 'Loading customer...'
                : viewMode === 'risk-review' && listBusy
                  ? 'Building the customer priority queue...'
                  : 'Select a customer.'}
            </div>
          ) : (
            <>
              <div className="customer360-account-header">
                <div>
                  <div className="customer360-title-line">
                    <h2>{summary.customer_name}</h2>
                    <span
                      className={
                        summary.general.active
                          ? 'status-active'
                          : 'status-inactive'
                      }
                    >
                      {summary.general.active ? 'Active' : 'Inactive'}
                    </span>
                  </div>
                  <p>
                    Customer #{summary.customer_number}
                    {summary.general.dba_name
                      ? ` · ${summary.general.dba_name}`
                      : ''}
                  </p>
                </div>
                <div className="customer360-account-meta">
                  <span>
                    Route{' '}
                    <strong>{summary.general.route_code || '—'}</strong>
                  </span>
                  <span>
                    Store{' '}
                    <strong>
                      {summary.general.store_number ?? '—'}
                    </strong>
                  </span>
                  <span>
                    Salesman{' '}
                    <strong>
                      {summary.general.salesman_number ?? '—'}
                    </strong>
                  </span>
                </div>
              </div>

              <div className="customer360-metrics">
                <article className="customer360-health-hero">
                  <span>Customer Health</span>
                  <strong>{health.score}</strong>
                  <b>{health.status}</b>
                </article>
                <Metric
                  label="Credit Limit"
                  value={money(summary.credit.credit_limit)}
                />
                <Metric
                  label="Exposure"
                  value={money(summary.credit.total_exposure)}
                  detail={pct(summary.credit.utilization_percent)}
                />
                <Metric
                  label="Available"
                  value={money(summary.credit.available_credit)}
                />
                <Metric
                  label="Past Due"
                  value={money(summary.aging.past_due)}
                />
              </div>

              <nav className="customer360-tabs">
                {tabs.map((currentTab) => (
                  <button
                    key={currentTab}
                    className={tab === currentTab ? 'active' : ''}
                    onClick={() => setTab(currentTab)}
                  >
                    {currentTab[0].toUpperCase() + currentTab.slice(1)}
                  </button>
                ))}
              </nav>

              {tab === 'overview' && (
                <div className="customer360-grid">
                  <Panel title="AI Account Summary" wide>
                    <div className="customer360-ai">
                      <p>
                        {ai ||
                          'Generate a concise local-AI summary grounded only in the account data shown here.'}
                      </p>
                      <button onClick={refreshAi} disabled={aiBusy}>
                        {aiBusy
                          ? 'Generating...'
                          : ai
                            ? 'Refresh summary'
                            : 'Generate summary'}
                      </button>
                    </div>
                  </Panel>
                  <Panel title="Health Factors">
                    <div className="customer360-score-list">
                      {health.factors.map((factor) => (
                        <div key={factor.label}>
                          <span>{factor.label}</span>
                          <strong>{factor.score}</strong>
                          <small>{factor.explanation}</small>
                        </div>
                      ))}
                    </div>
                  </Panel>
                  <Panel title="Recommendations">
                    <div className="customer360-recommendations">
                      {recommendations.map((recommendation) => (
                        <div key={recommendation.id}>
                          <b>{recommendation.title}</b>
                          <span
                            className={`impact impact--${recommendation.impact.toLowerCase()}`}
                          >
                            {recommendation.impact}
                          </span>
                          <p>{recommendation.reason}</p>
                          <button>{recommendation.action}</button>
                        </div>
                      ))}
                    </div>
                  </Panel>
                </div>
              )}

              {tab === 'financial' && (
                <div className="customer360-grid">
                  <Panel title="Credit Position">
                    <Fields
                      values={{
                        'Credit Limit': money(
                          summary.credit.credit_limit,
                        ),
                        Balance: money(summary.credit.balance),
                        'On Order': money(summary.credit.credit_on_order),
                        Exposure: money(
                          summary.credit.total_exposure,
                        ),
                        'Available Credit': money(
                          summary.credit.available_credit,
                        ),
                        Terms: summary.credit.terms_description,
                      }}
                    />
                  </Panel>
                  <Panel title="Aging">
                    <Fields
                      values={{
                        Current: money(summary.aging.current),
                        '30 Days': money(summary.aging.days_30),
                        '60 Days': money(summary.aging.days_60),
                        '90 Days': money(summary.aging.days_90),
                        '120 Days': money(summary.aging.days_120),
                        PastDue: money(summary.aging.past_due),
                      }}
                    />
                  </Panel>
                </div>
              )}

              {tab === 'sales' && (
                <div className="customer360-grid">
                  <Panel title="Sales Performance">
                    <Fields
                      values={{
                        'Month to Date': money(
                          summary.sales.month_to_date,
                        ),
                        'Year to Date': money(
                          summary.sales.year_to_date,
                        ),
                        'Last Year': money(summary.sales.last_year),
                        'Annualized Sales': money(
                          summary.sales.annualized_sales,
                        ),
                        'Expected Credit Line': money(
                          summary.sales.expected_credit_line,
                        ),
                      }}
                    />
                  </Panel>
                </div>
              )}

              {tab === 'timeline' && (
                <Panel title="Unified Timeline">
                  <div className="customer360-timeline">
                    {Object.entries(summary.activity).map(
                      ([key, value]) => (
                        <div key={key}>
                          <i />
                          <div>
                            <b>{key.replaceAll('_', ' ')}</b>
                            <span>{String(value ?? '—')}</span>
                          </div>
                        </div>
                      ),
                    )}
                  </div>
                </Panel>
              )}

              {['documents', 'notes', 'relationships'].includes(tab) && (
                <Panel
                  title={`${tab[0].toUpperCase() + tab.slice(1)} Workspace`}
                >
                  <div className="customer360-empty">
                    This workspace shell is ready for its dedicated
                    repository and write-controlled workflow in the next
                    sprint.
                  </div>
                </Panel>
              )}

              {tab === 'ai' && (
                <Panel title="AI Insights">
                  <div className="customer360-ai">
                    <p>{ai || 'No AI summary generated yet.'}</p>
                    <button onClick={refreshAi} disabled={aiBusy}>
                      {aiBusy ? 'Generating...' : 'Generate grounded insight'}
                    </button>
                  </div>
                </Panel>
              )}
            </>
          )}
        </main>
      </div>
    </section>
  )
}

function Metric({
  label,
  value,
  detail,
}: {
  label: string
  value: string
  detail?: string
}) {
  return (
    <article className="customer360-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </article>
  )
}

function Panel({
  title,
  wide,
  children,
}: {
  title: string
  wide?: boolean
  children: React.ReactNode
}) {
  return (
    <article
      className={`customer360-panel ${
        wide ? 'customer360-panel--wide' : ''
      }`}
    >
      <h3>{title}</h3>
      {children}
    </article>
  )
}

function Fields({
  values,
}: {
  values: Record<string, string | number>
}) {
  return (
    <div className="customer360-fields">
      {Object.entries(values).map(([key, value]) => (
        <div className="customer360-field" key={key}>
          <span>{key}</span>
          <strong>{value}</strong>
        </div>
      ))}
    </div>
  )
}
