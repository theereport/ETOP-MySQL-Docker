import { useCallback, useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import {
  createOrderRecommendation,
  getOrderDecisionPreparation,
  getOrderRecommendations,
} from './api'
import type {
  OrderDecisionPreparationResponse,
  OrderRecommendationHistoryResponse,
  OrderRecommendationDisposition,
} from './types'
import { ContextWorkPanel } from '../workflow-foundation'

const money = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
})

const dispositions: Array<{
  value: OrderRecommendationDisposition
  label: string
}> = [
  { value: 'advance_to_authorized_review', label: 'Advance to authorized review' },
  { value: 'request_additional_information', label: 'Request additional information' },
  { value: 'escalate_for_credit_authority', label: 'Escalate for credit authority' },
  { value: 'do_not_advance', label: 'Do not advance this scenario' },
]

function message(error: unknown): string {
  return error instanceof Error ? error.message : 'Unable to prepare this order scenario.'
}

function label(value: string): string {
  return value.replaceAll('_', ' ')
}

export default function OrderDecisionPreparationPanel({
  customerNumber,
}: {
  customerNumber: number
}) {
  const [amount, setAmount] = useState('')
  const [orderReference, setOrderReference] = useState('')
  const [preparation, setPreparation] = useState<OrderDecisionPreparationResponse | null>(null)
  const [history, setHistory] = useState<OrderRecommendationHistoryResponse | null>(null)
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle')
  const [error, setError] = useState('')
  const [historyError, setHistoryError] = useState('')
  const [disposition, setDisposition] = useState<OrderRecommendationDisposition>('advance_to_authorized_review')
  const [analyst, setAnalyst] = useState('')
  const [rationale, setRationale] = useState('')
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [saveMessage, setSaveMessage] = useState('')

  const loadHistory = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await getOrderRecommendations(customerNumber, signal)
      setHistory(response)
      setHistoryError('')
    } catch (loadError) {
      if (signal?.aborted) return
      setHistoryError(message(loadError))
    }
  }, [customerNumber])

  useEffect(() => {
    const controller = new AbortController()
    void getOrderRecommendations(customerNumber, controller.signal)
      .then((response) => {
        setHistory(response)
        setHistoryError('')
      })
      .catch((loadError: unknown) => {
        if (controller.signal.aborted) return
        setHistoryError(message(loadError))
      })
    return () => controller.abort()
  }, [customerNumber])

  async function buildPreparation(event: FormEvent) {
    event.preventDefault()
    const numericAmount = Number(amount)
    if (!Number.isFinite(numericAmount) || numericAmount <= 0) {
      setStatus('error')
      setError('Enter a contemplated order amount greater than zero.')
      return
    }
    setStatus('loading')
    setError('')
    setSaveStatus('idle')
    setSaveMessage('')
    try {
      const response = await getOrderDecisionPreparation(
        customerNumber,
        numericAmount,
        orderReference,
      )
      setPreparation(response)
      setStatus('success')
    } catch (loadError) {
      setPreparation(null)
      setStatus('error')
      setError(message(loadError))
    }
  }

  async function saveRecommendation(event: FormEvent) {
    event.preventDefault()
    if (!preparation) return
    if (!analyst.trim() || !rationale.trim()) {
      setSaveStatus('error')
      setSaveMessage('Analyst and rationale are required.')
      return
    }
    setSaveStatus('saving')
    setSaveMessage('')
    try {
      await createOrderRecommendation(customerNumber, {
        contemplated_order_amount: preparation.evidence.contemplated_order_amount,
        order_reference: preparation.order_reference,
        disposition,
        analyst_identity: analyst.trim(),
        rationale: rationale.trim(),
      })
      setRationale('')
      await loadHistory()
      setSaveStatus('success')
      setSaveMessage('Append-only professional recommendation recorded. No order, approval, or ERP action was performed.')
    } catch (saveError) {
      setSaveStatus('error')
      setSaveMessage(message(saveError))
    }
  }

  return (
    <div className="credit-order-decision">
      <section className="credit-risk-panel credit-order-heading">
        <div>
          <span className="credit-risk-kicker">Credit Risk Increment 5</span>
          <h2>Order Decision Preparation</h2>
          <p>
            Examine a contemplated amount against current partial customer exposure and
            preserve professional recommendation evidence for an authorized decision.
          </p>
        </div>
        <span className="credit-order-boundary-badge">Preparation only · no hold or release</span>
      </section>

      <form className="credit-risk-panel credit-order-input" onSubmit={buildPreparation}>
        <label>
          Contemplated order amount
          <input type="number" min="0.01" step="0.01" value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="0.00" />
        </label>
        <label>
          Order/reference (optional)
          <input value={orderReference} maxLength={100} onChange={(event) => setOrderReference(event.target.value)} placeholder="Operator-entered reference" />
        </label>
        <button type="submit" className="credit-risk-primary-button" disabled={status === 'loading'}>
          {status === 'loading' ? 'Preparing…' : 'Build decision preparation'}
        </button>
        <small>No ERP order is loaded or changed. This amount is a professional scenario input.</small>
      </form>

      {error && <p className="credit-risk-error-text">{error}</p>}

      {preparation && (
        <>
          <section className="credit-order-metrics" aria-label="Order preparation evidence">
            <article><span>Current line</span><strong>{money.format(preparation.evidence.current_credit_line)}</strong></article>
            <article><span>Current partial exposure</span><strong>{money.format(preparation.evidence.current_partial_exposure)}</strong></article>
            <article><span>Scenario amount</span><strong>{money.format(preparation.evidence.contemplated_order_amount)}</strong></article>
            <article><span>Projected partial exposure</span><strong>{money.format(preparation.evidence.projected_partial_exposure)}</strong></article>
            <article className={preparation.evidence.projected_partial_available_credit < 0 ? 'is-negative' : ''}><span>Projected partial availability</span><strong>{money.format(preparation.evidence.projected_partial_available_credit)}</strong></article>
          </section>

          <div className="credit-order-grid">
            <section className="credit-risk-panel credit-order-gates">
              <div className="credit-risk-panel-heading">
                <div><span className="credit-risk-kicker">Evidence and authority</span><h3>Decision gates</h3></div>
                <small>Professional review required</small>
              </div>
              {preparation.gates.map((gate) => (
                <article key={gate.code}>
                  <span className={`credit-order-gate-status is-${gate.status}`}>{label(gate.status)}</span>
                  <div><strong>{label(gate.code)}</strong><p>{gate.explanation}</p></div>
                </article>
              ))}
              {preparation.warnings.map((warning) => <p className="credit-risk-decision-boundary" key={warning}>{warning}</p>)}
            </section>

            <form className="credit-risk-panel credit-order-recommendation" onSubmit={saveRecommendation}>
              <div className="credit-risk-panel-heading">
                <div><span className="credit-risk-kicker">Professional recommendation</span><h3>Record the next step</h3></div>
              </div>
              <label>Recommendation<select value={disposition} onChange={(event) => setDisposition(event.target.value as OrderRecommendationDisposition)}>{dispositions.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
              <label>Analyst<input value={analyst} onChange={(event) => setAnalyst(event.target.value)} placeholder="Person recording the recommendation" /></label>
              <label>Rationale<textarea rows={5} value={rationale} onChange={(event) => setRationale(event.target.value)} placeholder="Evidence considered, gaps, and recommended next step" /></label>
              <p className="credit-risk-decision-boundary">Recommendation only · decision effect none · order effect none · ERP write false</p>
              <button type="submit" className="credit-risk-primary-button" disabled={saveStatus === 'saving'}>{saveStatus === 'saving' ? 'Recording…' : 'Record recommendation'}</button>
              {saveMessage && <p className={saveStatus === 'error' ? 'credit-risk-error-text' : 'credit-risk-success-text'}>{saveMessage}</p>}
            </form>
          </div>
        </>
      )}

      <section className="credit-risk-panel credit-order-history">
        <div className="credit-risk-panel-heading"><div><span className="credit-risk-kicker">Append-only history</span><h3>Order recommendations</h3></div><small>{history?.count ?? 0} recorded</small></div>
        {historyError && <p className="credit-risk-error-text">{historyError}</p>}
        {history && history.recommendations.length === 0 && <p className="credit-risk-empty">No order recommendation history exists for this customer.</p>}
        {history?.recommendations.map((item) => (
          <article key={item.order_recommendation_id}>
            <div><strong>{label(item.disposition)}</strong><small>{item.created_at} · {item.analyst_identity}</small></div>
            <span>{money.format(item.contemplated_order_amount)}{item.order_reference ? ` · ${item.order_reference}` : ''}</span>
            <p>{item.rationale}</p>
          </article>
        ))}
      </section>

      <ContextWorkPanel
        capability="credit_risk"
        contextType="credit_customer"
        contextId={String(customerNumber)}
        contextLabel={`Customer ${customerNumber} credit review`}
        defaultTitle={`Follow up on customer ${customerNumber} credit evidence`}
      />
    </div>
  )
}
