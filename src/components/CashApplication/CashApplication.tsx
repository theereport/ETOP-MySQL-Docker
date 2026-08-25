import {
  type FormEvent,
  useMemo,
  useState,
} from 'react'

import './CashApplication.css'
import PaymentSearch from './PaymentSearch'
import RecommendationPanel from './RecommendationPanel'
import BusinessRulesPanel from './BusinessRulesPanel'
import DecisionTrace from './DecisionTrace'
import ScoreBreakdown from './ScoreBreakdown'
import InvoiceGrid from './InvoiceGrid'

const API_BASE = 'http://127.0.0.1:8000'

export type ScoreComponent = {
  rule_code: string
  rule_name: string
  score_adjustment: number
  passed: boolean
  explanation: string
}

export type CombinationMatch = {
  invoice_numbers?: string[]
  total_amount?: string | number
  invoice_count?: number
  score?: number
  due_dates?: string[]
}

export type CombinationResult = {
  customer_number: string
  payment_amount: string
  status: string
  confidence_score: number
  matches: CombinationMatch[]
  recommended_invoice_numbers: string[]
  reasons: string[]
  searched_invoice_count: number
  truncated: boolean
  anchor_due_date: string | null
  matched_through_due_date: string | null
  searched_due_date_buckets: string[]
}

export type HistoricalBehavior = {
  customer_number: string
  sample_size: number
  confidence_level: string
  multiple_payment_ratio: number
  average_invoice_group_size: number
  commonly_combines_invoices: boolean
  single_invoice_group_count: number
  multi_invoice_group_count: number
  largest_invoice_group_size: number
  notes: string[]
}

export type BusinessRuleResult = {
  base_score: number
  final_score: number
  auto_apply_allowed: boolean
  review_required: boolean
  selected_strategy: string
  passed_rules: string[]
  warnings: string[]
  decision_trace: string[]
  score_components: ScoreComponent[]
}

export type RecommendationExplanation = {
  headline: string
  summary: string
  reasoning: string[]
  warnings: string[]
  confidence_explanation: string
  decision_trace: string[]
}

export type CashApplicationRecommendation = {
  customer_number: string
  payment_amount: string
  payment_date: string
  status: string
  confidence_score: number
  review_required: boolean
  auto_apply_allowed: boolean
  recommended_invoice_numbers: string[]
  strategy: string
  reasons: string[]
  single_invoice_result?: {
    customer_number: string
    payment_amount: string
    supplied_invoice_numbers: string[]
    status: string
    confidence_score: number
    recommended_invoice_numbers: string[]
    candidates: unknown[]
    reasons: string[]
  }
  combination_result?: CombinationResult
  historical_behavior?: HistoricalBehavior
  business_rule_result?: BusinessRuleResult
  explanation?: RecommendationExplanation
}

type RecommendationResponse = {
  recommendation: CashApplicationRecommendation
  explanation?: string
}

function CashApplication() {
  const [customerNumber, setCustomerNumber] = useState('')
  const [paymentAmount, setPaymentAmount] = useState('')
  const [paymentDate, setPaymentDate] = useState(() => {
    return new Date().toISOString().slice(0, 10)
  })

  const [suppliedInvoiceNumbers, setSuppliedInvoiceNumbers] =
    useState('')

  const [recommendation, setRecommendation] =
    useState<CashApplicationRecommendation | null>(null)

  const [plainTextExplanation, setPlainTextExplanation] =
    useState('')

  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')

  const normalizedInvoiceNumbers = useMemo(() => {
    return suppliedInvoiceNumbers
      .split(/[\s,;]+/)
      .map((invoiceNumber) => invoiceNumber.trim())
      .filter(Boolean)
  }, [suppliedInvoiceNumbers])

  async function findRecommendation(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault()

    const normalizedCustomer = customerNumber.trim()
    const normalizedAmount = paymentAmount.trim()

    if (!normalizedCustomer) {
      setError('Enter a customer number.')
      return
    }

    if (
      !normalizedAmount ||
      Number.isNaN(Number(normalizedAmount)) ||
      Number(normalizedAmount) <= 0
    ) {
      setError('Enter a valid payment amount greater than $0.00.')
      return
    }

    if (!paymentDate) {
      setError('Select the payment received date.')
      return
    }

    setIsLoading(true)
    setError('')
    setRecommendation(null)
    setPlainTextExplanation('')

    try {
      const searchParameters = new URLSearchParams({
        payment_amount: Number(normalizedAmount).toFixed(2),
        payment_date: paymentDate,
      })

      normalizedInvoiceNumbers.forEach((invoiceNumber) => {
        searchParameters.append(
          'invoice_numbers',
          invoiceNumber,
        )
      })

      /*
       * Change only this path if your FastAPI route uses a
       * different endpoint name.
       */
      const endpoint =
        `${API_BASE}/api/test/` +
        `cash-application-recommendation/` +
        `${encodeURIComponent(normalizedCustomer)}` +
        `?${searchParameters.toString()}`

      const response = await fetch(endpoint)

      const responseBody =
        (await response.json().catch(() => null)) as
          | RecommendationResponse
          | { detail?: string }
          | null

      if (!response.ok) {
        const detail =
          responseBody &&
          'detail' in responseBody &&
          responseBody.detail

        throw new Error(
          detail ||
            `Recommendation request failed with status ${response.status}.`,
        )
      }

      if (
        !responseBody ||
        !('recommendation' in responseBody)
      ) {
        throw new Error(
          'The backend returned an unexpected response.',
        )
      }

      setRecommendation(responseBody.recommendation)
      setPlainTextExplanation(
        responseBody.explanation ?? '',
      )
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Unable to reach the cash application endpoint.',
      )
    } finally {
      setIsLoading(false)
    }
  }

  function resetReview() {
    setRecommendation(null)
    setPlainTextExplanation('')
    setError('')
  }

  return (
    <section className="cash-application-page">
      <div className="page-section-header">
        <div>
          <span className="workspace-label">
            CASH APPLICATION DECISION ENGINE
          </span>

          <h1>Cash Application</h1>

          <p>
            Evaluate open customer invoices using exact payment
            matching, due-date priority, historical behavior,
            and centralized business rules.
          </p>
        </div>

        {recommendation && (
          <button
            type="button"
            className="desktop-secondary-button"
            onClick={resetReview}
          >
            Start New Review
          </button>
        )}
      </div>

      <PaymentSearch
        customerNumber={customerNumber}
        paymentAmount={paymentAmount}
        paymentDate={paymentDate}
        suppliedInvoiceNumbers={suppliedInvoiceNumbers}
        isLoading={isLoading}
        onCustomerNumberChange={setCustomerNumber}
        onPaymentAmountChange={setPaymentAmount}
        onPaymentDateChange={setPaymentDate}
        onSuppliedInvoiceNumbersChange={
          setSuppliedInvoiceNumbers
        }
        onSubmit={findRecommendation}
      />

      {error && (
        <div className="desktop-error-banner">{error}</div>
      )}

      {isLoading && (
        <div className="cash-loading-panel">
          <span className="cash-loading-spinner" />

          <div>
            <strong>Evaluating open invoices</strong>
            <p>
              Applying invoice matching, due-date priority,
              history, and business rules.
            </p>
          </div>
        </div>
      )}

      {recommendation && !isLoading && (
        <div className="cash-review-layout">
          <RecommendationPanel
            recommendation={recommendation}
          />

          <InvoiceGrid
            recommendedInvoiceNumbers={
              recommendation.recommended_invoice_numbers
            }
            combinationResult={
              recommendation.combination_result
            }
          />

          <div className="cash-detail-grid">
            <BusinessRulesPanel
              businessRuleResult={
                recommendation.business_rule_result
              }
              historicalBehavior={
                recommendation.historical_behavior
              }
            />

            <ScoreBreakdown
              scoreComponents={
                recommendation.business_rule_result
                  ?.score_components ?? []
              }
              finalScore={
                recommendation.business_rule_result
                  ?.final_score ??
                recommendation.confidence_score
              }
            />
          </div>

          <DecisionTrace
            trace={
              recommendation.explanation?.decision_trace ??
              recommendation.business_rule_result
                ?.decision_trace ??
              []
            }
          />

          {plainTextExplanation && (
            <details className="cash-raw-explanation">
              <summary>
                View backend recommendation summary
              </summary>

              <pre>{plainTextExplanation}</pre>
            </details>
          )}
        </div>
      )}
    </section>
  )
}

export default CashApplication