import {
  useEffect,
  useCallback,
  useMemo,
  useRef,
  useState,
} from 'react'
import type { FormEvent, ReactNode } from 'react'
import {
  createCustomerRiskAssessment,
  getCustomerRiskAssessments,
  getCustomerRiskSnapshot,
  getRiskBands,
  searchCreditRiskCustomers,
} from './api'
import type {
  AgingEvidence,
  AssessmentDraft,
  AssessmentErrors,
  CreditRiskAssessment,
  CreditRiskCustomerSearchResult,
  CreditRiskWorkspaceProps,
  CustomerRiskSnapshot,
  EvidenceMetric,
  ExposureComponent,
  PaymentEvidence,
  RiskBand,
  RiskBandResponse,
} from './types'
import {
  findBandForRating,
  ratingOptions,
  toCreateAssessmentRequest,
  validateAssessmentDraft,
} from './validation'
import PriorityAlertsPanel from './PriorityAlertsPanel'
import CreditLineIntelligencePanel from './CreditLineIntelligencePanel'
import PortfolioMonitoringPanel from './PortfolioMonitoringPanel'
import OrderDecisionPreparationPanel from './OrderDecisionPreparationPanel'
import CreditERPEvidencePanel from './CreditERPEvidencePanel'
import PotentialCustomersPanel from './PotentialCustomersPanel'
import './CreditRiskWorkspace.css'

type AsyncStatus = 'idle' | 'loading' | 'success' | 'error'
type WorkspaceView = 'priority' | 'portfolio' | 'customer' | 'potential_customers' | 'credit_line' | 'order_decision' | 'erp_evidence'

const moneyFormatter = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
})

const numberFormatter = new Intl.NumberFormat('en-US', {
  maximumFractionDigits: 2,
})

const dateTimeFormatter = new Intl.DateTimeFormat('en-US', {
  dateStyle: 'medium',
  timeStyle: 'short',
})

const dateFormatter = new Intl.DateTimeFormat('en-US', {
  dateStyle: 'medium',
})

function formatMoney(value: number | null | undefined): string {
  return value == null ? 'Unavailable' : moneyFormatter.format(value)
}

function formatPercent(value: number | null | undefined): string {
  return value == null ? 'Unavailable' : `${numberFormatter.format(value)}%`
}

function formatDate(value: string | null | undefined): string {
  if (!value) {
    return 'Unavailable'
  }

  const date = new Date(
    /^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00:00` : value,
  )
  return Number.isNaN(date.valueOf()) ? value : dateFormatter.format(date)
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return 'Unavailable'
  }

  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? value : dateTimeFormatter.format(date)
}

function todayLocal(): string {
  const now = new Date()
  const offset = now.getTimezoneOffset() * 60_000
  return new Date(now.valueOf() - offset).toISOString().slice(0, 10)
}

function emptyDraft(): AssessmentDraft {
  return {
    rating: '',
    reviewDate: todayLocal(),
    nextReviewDate: '',
    analystIdentity: '',
    rationale: '',
  }
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

function StatusMessage({
  kind,
  children,
}: {
  kind: 'error' | 'success' | 'notice'
  children: ReactNode
}) {
  return (
    <div
      className={`credit-risk-message credit-risk-message--${kind}`}
      role={kind === 'error' ? 'alert' : 'status'}
    >
      {children}
    </div>
  )
}

function SourceTag({ status }: { status: string }) {
  const normalized = status.toLowerCase().replace(/[^a-z0-9]+/g, '-')
  return (
    <span className={`credit-risk-source-tag credit-risk-source-tag--${normalized}`}>
      {status.replaceAll('_', ' ')}
    </span>
  )
}

function CustomerSearchList({
  results,
  selectedCustomerNumber,
  disabled,
  onSelect,
}: {
  results: CreditRiskCustomerSearchResult[]
  selectedCustomerNumber: number | null
  disabled: boolean
  onSelect: (customerNumber: number) => void
}) {
  return (
    <div className="credit-risk-customer-list" aria-label="Customer search results">
      {results.map((customer) => (
        <button
          key={customer.customer_number}
          type="button"
          className={
            customer.customer_number === selectedCustomerNumber
              ? 'credit-risk-customer credit-risk-customer--selected'
              : 'credit-risk-customer'
          }
          onClick={() => onSelect(customer.customer_number)}
          disabled={disabled}
        >
          <span className="credit-risk-customer-name">
            <strong>{customer.customer_name || customer.dba_name}</strong>
            <small>Customer {customer.customer_number}</small>
          </span>
          <span className="credit-risk-customer-facts">
            <small>{customer.route_code ? `Route ${customer.route_code}` : 'Route unavailable'}</small>
            <small>{customer.phone || 'Phone unavailable'}</small>
          </span>
        </button>
      ))}
    </div>
  )
}

function ExposureComponentRow({ component }: { component: ExposureComponent }) {
  const operationSymbol =
    component.operation === 'subtract'
      ? '−'
      : component.operation === 'add'
        ? '+'
        : 'i'

  return (
    <tr>
      <td>
        <span className="credit-risk-operation" aria-label={component.operation}>
          {operationSymbol}
        </span>
        <div>
          <strong>{component.label}</strong>
          <small>{component.explanation}</small>
        </div>
      </td>
      <td>{formatMoney(component.value)}</td>
      <td>
        <SourceTag status={component.status} />
        <small>{component.source || 'No governed source connected'}</small>
      </td>
      <td>
        {component.included_in_partial_calculation
          ? `Included in partial exposure${
              component.calculation_value !== component.value
                ? ` at ${formatMoney(component.calculation_value)}`
                : ''
            }`
          : component.required_for_full_exposure
            ? 'Required; not included'
            : component.operation === 'informational'
              ? 'Informational; not a separate full-formula term'
              : 'Reference only'}
      </td>
    </tr>
  )
}

function ExposurePanel({ snapshot }: { snapshot: CustomerRiskSnapshot }) {
  const { credit, exposure } = snapshot

  return (
    <section className="credit-risk-panel credit-risk-panel--wide">
      <div className="credit-risk-panel-heading">
        <div>
          <span className="credit-risk-kicker">Source-grounded exposure</span>
          <h2>Exposure composition</h2>
        </div>
        <SourceTag status={exposure.completeness} />
      </div>

      <div className="credit-risk-formula">
        <strong>Required full formula</strong>
        <code>{exposure.full_formula}</code>
        <p>
          The current ERP source does not prove every required component. The partial
          figure below is an operational reference, not a complete true-exposure result.
        </p>
      </div>

      <div className="credit-risk-metric-grid credit-risk-metric-grid--four">
        <div>
          <span>Open A/R</span>
          <strong>{formatMoney(credit.open_ar)}</strong>
          <small>Observed from ERP</small>
        </div>
        <div>
          <span>ERP on-order aggregate</span>
          <strong>{formatMoney(credit.erp_on_order_aggregate)}</strong>
          <small>Not separated into required formula components</small>
        </div>
        <div className="credit-risk-metric--partial">
          <span>Partial exposure</span>
          <strong>{formatMoney(exposure.partial_exposure)}</strong>
          <small>{exposure.operational_reference_formula}</small>
        </div>
        <div className="credit-risk-metric--partial">
          <span>Partial available credit</span>
          <strong>{formatMoney(exposure.partial_available_credit)}</strong>
          <small>Credit line less partial exposure</small>
        </div>
      </div>

      <div className="credit-risk-table-wrap">
        <table className="credit-risk-evidence-table">
          <thead>
            <tr>
              <th>Formula component</th>
              <th>Amount</th>
              <th>Evidence status</th>
              <th>Calculation treatment</th>
            </tr>
          </thead>
          <tbody>
            {exposure.components.map((component) => (
              <ExposureComponentRow key={component.key} component={component} />
            ))}
          </tbody>
        </table>
      </div>

      {exposure.missing_required_components.length > 0 && (
        <div className="credit-risk-gap-box">
          <strong>Required components currently unavailable</strong>
          <ul>
            {exposure.missing_required_components.map((component) => (
              <li key={component}>{component.replaceAll('_', ' ')}</li>
            ))}
          </ul>
        </div>
      )}

      {exposure.warnings.map((warning) => (
        <p className="credit-risk-warning" key={warning}>{warning}</p>
      ))}
    </section>
  )
}

const agingBuckets: Array<[keyof AgingEvidence, string]> = [
  ['future', 'Future'],
  ['current', 'Current'],
  ['days_30', '30 days'],
  ['days_60', '60 days'],
  ['days_90', '90 days'],
  ['days_120', '120+ days'],
]

function AgingPanel({ aging }: { aging: AgingEvidence }) {
  return (
    <section className="credit-risk-panel">
      <div className="credit-risk-panel-heading">
        <div>
          <span className="credit-risk-kicker">Signed ERP balances</span>
          <h2>Aging evidence</h2>
        </div>
        <SourceTag status={aging.status} />
      </div>
      <div className="credit-risk-aging-grid">
        {agingBuckets.map(([key, label]) => (
          <div key={key}>
            <span>{label}</span>
            <strong>{formatMoney(aging[key] as number)}</strong>
          </div>
        ))}
      </div>
      <dl className="credit-risk-definition-list">
        <div>
          <dt>Past due</dt>
          <dd>{formatMoney(aging.past_due)}</dd>
        </div>
        <div>
          <dt>Recomputed bucket total</dt>
          <dd>{formatMoney(aging.bucket_total)}</dd>
        </div>
        <div>
          <dt>Open A/R reconciliation difference</dt>
          <dd>{formatMoney(aging.open_ar_reconciliation_difference)}</dd>
        </div>
      </dl>
      <p className="credit-risk-source-note">Source: {aging.source}</p>
    </section>
  )
}

const paymentMetricDefinitions: Array<[
  keyof Omit<
    PaymentEvidence,
    | 'last_payment_amount'
    | 'last_payment_date'
    | 'last_payment_status'
    | 'last_payment_explanation'
  >,
  string,
  'number' | 'percent' | 'currency',
]> = [
  ['average_days_to_pay', 'Average days to pay', 'number'],
  ['weighted_average_days_to_pay', 'Weighted average days to pay', 'number'],
  ['days_beyond_terms', 'Days beyond terms', 'number'],
  ['on_time_percentage', 'On-time percentage', 'percent'],
  ['late_payment_frequency', 'Late-payment frequency', 'number'],
  ['largest_historical_delinquency', 'Largest historical delinquency', 'currency'],
]

function metricValue(
  metric: EvidenceMetric,
  format: 'number' | 'percent' | 'currency',
): string {
  if (metric.value == null) {
    return 'Unavailable'
  }

  if (format === 'currency') {
    return formatMoney(metric.value)
  }

  if (format === 'percent') {
    return formatPercent(metric.value)
  }

  return numberFormatter.format(metric.value)
}

function PaymentPanel({ payment }: { payment: PaymentEvidence }) {
  return (
    <section className="credit-risk-panel">
      <div className="credit-risk-panel-heading">
        <div>
          <span className="credit-risk-kicker">Available and missing evidence</span>
          <h2>Payment behavior</h2>
        </div>
      </div>
      <div className="credit-risk-last-payment">
        <div>
          <span>Last payment amount</span>
          <strong>{formatMoney(payment.last_payment_amount)}</strong>
        </div>
        <div>
          <span>Last payment date</span>
          <strong>{formatDate(payment.last_payment_date)}</strong>
        </div>
        <SourceTag status={payment.last_payment_status} />
      </div>
      <p className="credit-risk-source-note">
        {payment.last_payment_explanation}
      </p>
      <div className="credit-risk-payment-list">
        {paymentMetricDefinitions.map(([key, label, format]) => {
          const metric = payment[key]
          return (
            <div key={key}>
              <div>
                <span>{label}</span>
                <small>{metric.explanation}</small>
              </div>
              <div>
                <strong>{metricValue(metric, format)}</strong>
                <SourceTag status={metric.status} />
              </div>
            </div>
          )
        })}
      </div>
      <p className="credit-risk-source-note">
        Unavailable metrics remain blank until a governed payment-history source is connected.
      </p>
    </section>
  )
}

function BandReference({ response }: { response: RiskBandResponse }) {
  return (
    <section className="credit-risk-panel credit-risk-panel--bands">
      <div className="credit-risk-panel-heading">
        <div>
          <span className="credit-risk-kicker">Manual assessment taxonomy</span>
          <h2>{response.band_set.title}</h2>
        </div>
        <SourceTag status={response.band_set.status} />
      </div>
      <p>
        Version <strong>{response.band_set.version}</strong> · Source{' '}
        <strong>{response.band_set.source_record}</strong>
      </p>
      <div className="credit-risk-band-list">
        {response.bands.map((band) => (
          <div key={band.sequence}>
            <strong>
              {band.rating_min === band.rating_max
                ? band.rating_min
                : `${band.rating_min}–${band.rating_max}`}
            </strong>
            <span>{band.meaning}</span>
            <small>{band.typical_response}</small>
          </div>
        ))}
      </div>
      <p className="credit-risk-governance-note">
        This is a product-owner-supplied draft used only to label professional judgment.
        It is not an automated scoring or action policy. Promotion authority:{' '}
        {response.band_set.promotion_authority}.
      </p>
    </section>
  )
}

function AssessmentForm({
  bands,
  draft,
  errors,
  busy,
  disabled,
  onChange,
  onSubmit,
}: {
  bands: RiskBand[]
  draft: AssessmentDraft
  errors: AssessmentErrors
  busy: boolean
  disabled: boolean
  onChange: (field: keyof AssessmentDraft, value: string) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
}) {
  const selectedBand = findBandForRating(bands, Number(draft.rating))

  return (
    <section className="credit-risk-panel credit-risk-panel--assessment">
      <div className="credit-risk-panel-heading">
        <div>
          <span className="credit-risk-kicker">Professional judgment</span>
          <h2>Record a manual risk assessment</h2>
        </div>
      </div>
      <form onSubmit={onSubmit} noValidate>
        <div className="credit-risk-form-row credit-risk-form-row--three">
          <label>
            <span>Manual rating</span>
            <select
              value={draft.rating}
              onChange={(event) => onChange('rating', event.target.value)}
              aria-invalid={Boolean(errors.rating)}
              disabled={disabled}
            >
              <option value="">Select rating</option>
              {ratingOptions(bands).map((rating) => (
                <option value={rating} key={rating}>
                  {rating}
                </option>
              ))}
            </select>
            {errors.rating && <small className="credit-risk-field-error">{errors.rating}</small>}
          </label>
          <label>
            <span>Review date</span>
            <input
              type="date"
              value={draft.reviewDate}
              onChange={(event) => onChange('reviewDate', event.target.value)}
              aria-invalid={Boolean(errors.reviewDate)}
              disabled={disabled}
            />
            {errors.reviewDate && <small className="credit-risk-field-error">{errors.reviewDate}</small>}
          </label>
          <label>
            <span>Next review date</span>
            <input
              type="date"
              value={draft.nextReviewDate}
              min={draft.reviewDate || undefined}
              onChange={(event) => onChange('nextReviewDate', event.target.value)}
              aria-invalid={Boolean(errors.nextReviewDate)}
              disabled={disabled}
            />
            {errors.nextReviewDate && <small className="credit-risk-field-error">{errors.nextReviewDate}</small>}
          </label>
        </div>

        {selectedBand && (
          <div className="credit-risk-selected-band">
            <strong>{selectedBand.meaning}</strong>
            <span>{selectedBand.typical_response}</span>
          </div>
        )}

        <label>
          <span>Analyst identity</span>
          <input
            type="text"
            value={draft.analystIdentity}
            maxLength={200}
            autoComplete="name"
            placeholder="Enter the person recording this assessment"
            onChange={(event) => onChange('analystIdentity', event.target.value)}
            aria-invalid={Boolean(errors.analystIdentity)}
            disabled={disabled}
          />
          {errors.analystIdentity && (
            <small className="credit-risk-field-error">{errors.analystIdentity}</small>
          )}
        </label>

        <label>
          <span>Professional rationale</span>
          <textarea
            value={draft.rationale}
            rows={5}
            maxLength={5000}
            placeholder="Explain the evidence considered, uncertainty, and professional judgment behind this rating."
            onChange={(event) => onChange('rationale', event.target.value)}
            aria-invalid={Boolean(errors.rationale)}
            disabled={disabled}
          />
          {errors.rationale && <small className="credit-risk-field-error">{errors.rationale}</small>}
        </label>

        <div className="credit-risk-authority-warning">
          <strong>Identity and authority boundary</strong>
          <p>
            The analyst name is operator supplied. ETOP does not independently verify
            identity or authority in this increment. Saving records an assessment only;
            it does not approve a review, change a credit line, place or release a hold,
            release an order, or write to ERP.
          </p>
        </div>

        <button
          type="submit"
          className="credit-risk-primary-button"
          disabled={disabled || busy}
        >
          {busy ? 'Saving assessment…' : 'Save append-only assessment'}
        </button>
      </form>
    </section>
  )
}

function SnapshotDetails({ assessment }: { assessment: CreditRiskAssessment }) {
  const { evidence_snapshot: snapshot } = assessment
  return (
    <details className="credit-risk-snapshot">
      <summary>Reconstruct saved evidence snapshot</summary>
      <div className="credit-risk-snapshot-grid">
        <div>
          <span>Snapshot source</span>
          <strong>{snapshot.source.system}</strong>
          <small>{snapshot.source.access} · {snapshot.source.status}</small>
        </div>
        <div>
          <span>Snapshot captured</span>
          <strong>{formatDateTime(snapshot.source.retrieved_at)}</strong>
          <small>Contract {snapshot.contract_version}</small>
        </div>
        <div>
          <span>Credit line</span>
          <strong>{formatMoney(snapshot.credit.credit_line)}</strong>
        </div>
        <div>
          <span>Open A/R</span>
          <strong>{formatMoney(snapshot.credit.open_ar)}</strong>
        </div>
        <div>
          <span>ERP on-order aggregate</span>
          <strong>{formatMoney(snapshot.credit.erp_on_order_aggregate)}</strong>
        </div>
        <div>
          <span>Partial exposure</span>
          <strong>{formatMoney(snapshot.exposure.partial_exposure)}</strong>
          <small>{snapshot.exposure.completeness}</small>
        </div>
        <div>
          <span>Past due</span>
          <strong>{formatMoney(snapshot.aging.past_due)}</strong>
        </div>
        <div>
          <span>Last payment</span>
          <strong>{formatMoney(snapshot.payment.last_payment_amount)}</strong>
          <small>{formatDate(snapshot.payment.last_payment_date)}</small>
        </div>
      </div>
      <div className="credit-risk-snapshot-components">
        {snapshot.exposure.components.map((component) => (
          <div key={component.key}>
            <span>{component.label}</span>
            <strong>{formatMoney(component.value)}</strong>
            <small>
              Partial calculation: {formatMoney(component.calculation_value)} ·{' '}
              {component.included_in_partial_calculation ? 'included' : 'not included'}
            </small>
            <small>{component.status} · {component.source || 'No governed source'}</small>
          </div>
        ))}
      </div>
      <div className="credit-risk-snapshot-section">
        <strong>Saved full-exposure formula</strong>
        <code>{snapshot.exposure.full_formula}</code>
      </div>
      <div className="credit-risk-snapshot-section">
        <strong>Saved signed aging buckets</strong>
        <div className="credit-risk-snapshot-grid credit-risk-snapshot-grid--aging">
          {agingBuckets.map(([key, label]) => (
            <div key={key}>
              <span>{label}</span>
              <strong>{formatMoney(snapshot.aging[key] as number)}</strong>
            </div>
          ))}
          <div>
            <span>Bucket total</span>
            <strong>{formatMoney(snapshot.aging.bucket_total)}</strong>
          </div>
          <div>
            <span>Open A/R difference</span>
            <strong>{formatMoney(snapshot.aging.open_ar_reconciliation_difference)}</strong>
          </div>
        </div>
      </div>
      <div className="credit-risk-snapshot-section">
        <strong>Saved payment evidence and gaps</strong>
        <div className="credit-risk-snapshot-payment">
          {paymentMetricDefinitions.map(([key, label, format]) => {
            const metric = snapshot.payment[key]
            return (
              <div key={key}>
                <span>{label}</span>
                <strong>{metricValue(metric, format)}</strong>
                <small>{metric.status} · {metric.explanation}</small>
              </div>
            )
          })}
        </div>
      </div>
      {snapshot.exposure.warnings.length > 0 && (
        <div className="credit-risk-snapshot-section">
          <strong>Saved limitations</strong>
          <ul>
            {snapshot.exposure.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}
      {snapshot.risk_band_configuration && (
        <p className="credit-risk-snapshot-config">
          Saved taxonomy {snapshot.risk_band_configuration.band_set.version} ·{' '}
          {snapshot.risk_band_configuration.band_set.source_record}
        </p>
      )}
      <p className="credit-risk-snapshot-hash">
        Evidence SHA-256 <code>{assessment.evidence_snapshot_sha256}</code>
      </p>
    </details>
  )
}

function AssessmentHistory({
  assessments,
  status,
}: {
  assessments: CreditRiskAssessment[]
  status: AsyncStatus
}) {
  return (
    <section className="credit-risk-panel credit-risk-panel--history">
      <div className="credit-risk-panel-heading">
        <div>
          <span className="credit-risk-kicker">Append-only local record</span>
          <h2>Assessment history</h2>
        </div>
        <span className="credit-risk-count">{assessments.length}</span>
      </div>
      {status === 'loading' && <p className="credit-risk-empty">Reloading assessment history…</p>}
      {status !== 'loading' && assessments.length === 0 && (
        <p className="credit-risk-empty">No manual assessments have been recorded for this customer.</p>
      )}
      <div className="credit-risk-history-list">
        {assessments.map((assessment) => (
          <article key={assessment.assessment_id}>
            <div className="credit-risk-history-heading">
              <div className="credit-risk-rating-badge">
                <strong>{assessment.manual_rating}</strong>
                <span>{assessment.band.meaning}</span>
              </div>
              <div>
                <strong>{formatDate(assessment.review_date)}</strong>
                <small>Recorded {formatDateTime(assessment.created_at)}</small>
              </div>
            </div>
            <p>{assessment.rationale}</p>
            <dl className="credit-risk-definition-list">
              <div>
                <dt>Analyst</dt>
                <dd>{assessment.analyst_identity}</dd>
              </div>
              <div>
                <dt>Next review</dt>
                <dd>{formatDate(assessment.next_review_date)}</dd>
              </div>
              <div>
                <dt>Band configuration</dt>
                <dd>{assessment.band_set_version} · {assessment.band_set_status}</dd>
              </div>
              <div>
                <dt>Exposure completeness</dt>
                <dd>{assessment.completeness_state}</dd>
              </div>
              <div>
                <dt>Actor identity</dt>
                <dd>{assessment.actor_identity_source.replaceAll('_', ' ')}</dd>
              </div>
              <div>
                <dt>Authority</dt>
                <dd>{assessment.actor_authority_status.replaceAll('_', ' ')}</dd>
              </div>
            </dl>
            <p className="credit-risk-decision-boundary">{assessment.decision_effect}</p>
            <SnapshotDetails assessment={assessment} />
          </article>
        ))}
      </div>
    </section>
  )
}

export default function CreditRiskWorkspace({
  initialCustomerNumber,
}: CreditRiskWorkspaceProps) {
  const initialNumber = Number(initialCustomerNumber)
  const validInitialNumber = Number.isInteger(initialNumber) && initialNumber > 0
  const [activeView, setActiveView] = useState<WorkspaceView>(
    validInitialNumber ? 'customer' : 'priority',
  )
  const [query, setQuery] = useState(validInitialNumber ? String(initialNumber) : '')
  const [results, setResults] = useState<CreditRiskCustomerSearchResult[]>([])
  const [searchStatus, setSearchStatus] = useState<AsyncStatus>('idle')
  const [searchError, setSearchError] = useState('')
  const [selectedCustomerNumber, setSelectedCustomerNumber] = useState<number | null>(
    validInitialNumber ? initialNumber : null,
  )
  const [bands, setBands] = useState<RiskBandResponse | null>(null)
  const [bandStatus, setBandStatus] = useState<AsyncStatus>('loading')
  const [bandError, setBandError] = useState('')
  const [snapshot, setSnapshot] = useState<CustomerRiskSnapshot | null>(null)
  const [assessments, setAssessments] = useState<CreditRiskAssessment[]>([])
  const [customerStatus, setCustomerStatus] = useState<AsyncStatus>(
    validInitialNumber ? 'loading' : 'idle',
  )
  const [historyStatus, setHistoryStatus] = useState<AsyncStatus>(
    validInitialNumber ? 'loading' : 'idle',
  )
  const [historyError, setHistoryError] = useState('')
  const [customerError, setCustomerError] = useState('')
  const [draft, setDraft] = useState<AssessmentDraft>(emptyDraft)
  const [errors, setErrors] = useState<AssessmentErrors>({})
  const [saveStatus, setSaveStatus] = useState<AsyncStatus>('idle')
  const [saveMessage, setSaveMessage] = useState('')
  const [saveMessageKind, setSaveMessageKind] = useState<'success' | 'error' | 'notice'>('success')
  const searchAbort = useRef<AbortController | null>(null)
  const searchGeneration = useRef(0)
  const customerGeneration = useRef(0)
  const saveInFlight = useRef(false)

  const bandRows = bands?.bands ?? []
  const latestAssessment = assessments[0] ?? snapshot?.latest_assessment ?? null
  const displayedBand = latestAssessment?.band ?? null
  const contactAddress = snapshot?.customer.address_lines.filter(Boolean).join(', ') ?? ''

  const selectedSearchCustomer = useMemo(
    () => results.find((item) => item.customer_number === selectedCustomerNumber) ?? null,
    [results, selectedCustomerNumber],
  )

  const runBandRequest = useCallback((controller: AbortController) => {
    getRiskBands(controller.signal)
      .then((response) => {
        setBands(response)
        setBandStatus('success')
      })
      .catch((error) => {
        if (isAbortError(error)) {
          return
        }
        setBands(null)
        setBandStatus('error')
        setBandError(errorMessage(error, 'Unable to load the risk-band configuration.'))
      })

  }, [])

  const retryBands = useCallback(() => {
    const controller = new AbortController()
    setBandStatus('loading')
    setBandError('')
    runBandRequest(controller)
  }, [runBandRequest])

  useEffect(() => {
    const controller = new AbortController()
    runBandRequest(controller)
    return () => controller.abort()
  }, [runBandRequest])

  useEffect(() => {
    if (selectedCustomerNumber === null) {
      return
    }

    const controller = new AbortController()
    const customerNumber = selectedCustomerNumber
    const generation = customerGeneration.current + 1
    customerGeneration.current = generation

    getCustomerRiskSnapshot(customerNumber, controller.signal)
      .then((customerSnapshot) => {
        if (customerGeneration.current !== generation) {
          return
        }
        setSnapshot(customerSnapshot)
        setCustomerStatus('success')
      })
      .catch((error) => {
        if (isAbortError(error) || customerGeneration.current !== generation) {
          return
        }
        setCustomerStatus('error')
        setCustomerError(errorMessage(error, 'Unable to load this customer risk workspace.'))
      })

    getCustomerRiskAssessments(customerNumber, controller.signal)
      .then((history) => {
        if (customerGeneration.current !== generation) {
          return
        }
        setAssessments(history.assessments)
        setHistoryStatus('success')
      })
      .catch((error) => {
        if (isAbortError(error) || customerGeneration.current !== generation) {
          return
        }
        setHistoryStatus('error')
        setHistoryError(errorMessage(error, 'Unable to load local assessment history.'))
      })

    return () => {
      controller.abort()
      if (customerGeneration.current === generation) {
        customerGeneration.current += 1
      }
    }
  }, [selectedCustomerNumber])

  async function submitSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (saveInFlight.current) {
      return
    }
    const search = query.trim()

    if (!search) {
      setSearchStatus('error')
      setSearchError('Enter a customer number, name, phone, address, ZIP, or open invoice.')
      return
    }

    searchAbort.current?.abort()
    const controller = new AbortController()
    const generation = searchGeneration.current + 1
    searchGeneration.current = generation
    searchAbort.current = controller
    setSearchStatus('loading')
    setSearchError('')
    setResults([])
    setSelectedCustomerNumber(null)
    customerGeneration.current += 1
    setSnapshot(null)
    setAssessments([])
    setCustomerStatus('idle')

    try {
      const response = await searchCreditRiskCustomers(search, controller.signal)
      if (searchGeneration.current !== generation) {
        return
      }
      setResults(response.customers)
      setSearchStatus('success')
    } catch (error) {
      if (isAbortError(error) || searchGeneration.current !== generation) {
        return
      }
      setSearchStatus('error')
      setSearchError(errorMessage(error, 'Customer search failed.'))
    }
  }

  function selectCustomer(customerNumber: number) {
    if (saveInFlight.current || saveStatus === 'loading') {
      return
    }
    setCustomerStatus('loading')
    setHistoryStatus('loading')
    setCustomerError('')
    setHistoryError('')
    setSaveStatus('idle')
    setSaveMessage('')
    setSaveMessageKind('success')
    setSnapshot(null)
    setAssessments([])
    setDraft(emptyDraft())
    setErrors({})
    setSelectedCustomerNumber(customerNumber)
  }

  function openPriorityCustomer(customerNumber: number) {
    setActiveView('customer')
    setQuery(String(customerNumber))
    setResults([])
    setSearchStatus('idle')
    setSearchError('')
    selectCustomer(customerNumber)
  }

  function changeDraft(field: keyof AssessmentDraft, value: string) {
    setDraft((current) => ({ ...current, [field]: value }))
    setErrors((current) => {
      if (!current[field]) {
        return current
      }
      const next = { ...current }
      delete next[field]
      return next
    })
    if (saveStatus !== 'idle') {
      setSaveStatus('idle')
      setSaveMessage('')
      setSaveMessageKind('success')
    }
  }

  async function submitAssessment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (
      saveInFlight.current ||
      selectedCustomerNumber === null ||
      !snapshot ||
      !bands
    ) {
      return
    }

    const nextErrors = validateAssessmentDraft(draft, bands.bands)
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors)
      setSaveStatus('error')
      setSaveMessageKind('error')
      setSaveMessage('Correct the highlighted fields before saving the assessment.')
      return
    }

    const customerNumber = selectedCustomerNumber
    saveInFlight.current = true
    setSaveStatus('loading')
    setSaveMessage('')
    setErrors({})

    try {
      const createdAssessment = await createCustomerRiskAssessment(
        customerNumber,
        toCreateAssessmentRequest(draft),
      )

      const [snapshotResult, historyResult] = await Promise.allSettled([
        getCustomerRiskSnapshot(customerNumber),
        getCustomerRiskAssessments(customerNumber),
      ])

      if (selectedCustomerNumber !== customerNumber) {
        return
      }

      if (snapshotResult.status === 'fulfilled') {
        setSnapshot(snapshotResult.value)
      }

      if (historyResult.status === 'fulfilled') {
        setAssessments(historyResult.value.assessments)
        setHistoryStatus('success')
        setHistoryError('')
      } else {
        setAssessments((current) => [
          createdAssessment,
          ...current.filter(
            (assessment) => assessment.assessment_id !== createdAssessment.assessment_id,
          ),
        ])
        setHistoryStatus('error')
        setHistoryError(
          errorMessage(historyResult.reason, 'The assessment was saved, but history reload failed.'),
        )
      }

      setDraft(emptyDraft())
      setSaveStatus('success')
      if (historyResult.status === 'fulfilled') {
        setSaveMessageKind('success')
        setSaveMessage(
          `Assessment saved. Reloaded ${historyResult.value.count} append-only history record${historyResult.value.count === 1 ? '' : 's'}.`,
        )
      } else {
        setSaveMessageKind('notice')
        setSaveMessage('Assessment saved, but the local history could not be reloaded. The saved response remains visible below.')
      }
    } catch (error) {
      setSaveStatus('error')
      setSaveMessageKind('error')
      setSaveMessage(errorMessage(error, 'Unable to save the assessment.'))
    } finally {
      saveInFlight.current = false
    }
  }

  return (
    <section className="credit-risk-shell">
      <header className="credit-risk-header">
        <div>
          <span className="credit-risk-eyebrow">CREDIT RISK INTELLIGENCE · INCREMENT 5</span>
          <h1>Credit Risk Workspace</h1>
          <p>
            Prioritize assessed-customer review, inspect source evidence, and record
            professional credit-line proposals without creating an approval or ERP action.
          </p>
        </div>
        <div className="credit-risk-local-badge">
          <span />
          Local assessment state · ERP read only
        </div>
      </header>

      <nav className="credit-risk-view-tabs" aria-label="Credit Risk workspace views">
        <button
          type="button"
          className={activeView === 'portfolio' ? 'is-active' : ''}
          aria-current={activeView === 'portfolio' ? 'page' : undefined}
          disabled={saveStatus === 'loading'}
          onClick={() => setActiveView('portfolio')}
        >
          Portfolio Monitoring
        </button>
        <button
          type="button"
          className={activeView === 'priority' ? 'is-active' : ''}
          aria-current={activeView === 'priority' ? 'page' : undefined}
          disabled={saveStatus === 'loading'}
          onClick={() => setActiveView('priority')}
        >
          Priority &amp; Alerts
        </button>
        <button
          type="button"
          className={activeView === 'customer' ? 'is-active' : ''}
          aria-current={activeView === 'customer' ? 'page' : undefined}
          disabled={saveStatus === 'loading'}
          onClick={() => setActiveView('customer')}
        >
          Customer Risk 360
        </button>
        <button
          type="button"
          className={activeView === 'potential_customers' ? 'is-active' : ''}
          aria-current={activeView === 'potential_customers' ? 'page' : undefined}
          disabled={saveStatus === 'loading'}
          onClick={() => setActiveView('potential_customers')}
        >
          Potential New Customers
        </button>
        <button
          type="button"
          className={activeView === 'credit_line' ? 'is-active' : ''}
          aria-current={activeView === 'credit_line' ? 'page' : undefined}
          disabled={saveStatus === 'loading'}
          onClick={() => setActiveView('credit_line')}
        >
          Credit-Line Intelligence
        </button>
        <button
          type="button"
          className={activeView === 'order_decision' ? 'is-active' : ''}
          aria-current={activeView === 'order_decision' ? 'page' : undefined}
          disabled={saveStatus === 'loading'}
          onClick={() => setActiveView('order_decision')}
        >
          Order Decision Preparation
        </button>
        <button
          type="button"
          className={activeView === 'erp_evidence' ? 'is-active' : ''}
          aria-current={activeView === 'erp_evidence' ? 'page' : undefined}
          disabled={saveStatus === 'loading'}
          onClick={() => setActiveView('erp_evidence')}
        >
          ERP Evidence
        </button>
      </nav>

      {activeView === 'priority' && (
        <PriorityAlertsPanel onOpenCustomer={openPriorityCustomer} />
      )}

      {activeView === 'portfolio' && (
        <PortfolioMonitoringPanel onOpenCustomer={openPriorityCustomer} />
      )}

      {activeView === 'potential_customers' && (
        <PotentialCustomersPanel />
      )}

      {(activeView === 'customer' || activeView === 'credit_line' || activeView === 'order_decision' || activeView === 'erp_evidence') && (
        <>

      <div className="credit-risk-search-card">
        <form onSubmit={submitSearch}>
          <label htmlFor="credit-risk-customer-search">Find a customer</label>
          <div>
            <input
              id="credit-risk-customer-search"
              type="search"
              value={query}
              placeholder="Customer number, name, phone, address, ZIP, or open invoice"
              onChange={(event) => setQuery(event.target.value)}
              disabled={searchStatus === 'loading' || saveStatus === 'loading'}
            />
            <button
              type="submit"
              className="credit-risk-primary-button"
              disabled={searchStatus === 'loading' || saveStatus === 'loading'}
            >
              {searchStatus === 'loading' ? 'Searching…' : 'Search customers'}
            </button>
          </div>
        </form>

        {searchError && <StatusMessage kind="error">{searchError}</StatusMessage>}
        {searchStatus === 'success' && results.length === 0 && (
          <StatusMessage kind="notice">
            No active customers matched that search. No placeholder customer was opened.
          </StatusMessage>
        )}
        {results.length > 0 && (
          <div className="credit-risk-results-block">
            <div>
              <strong>{results.length} customer{results.length === 1 ? '' : 's'} found</strong>
              <small>Select the customer whose current source evidence you want to review.</small>
            </div>
            <CustomerSearchList
              results={results}
              selectedCustomerNumber={selectedCustomerNumber}
              disabled={customerStatus === 'loading' || saveStatus === 'loading'}
              onSelect={selectCustomer}
            />
          </div>
        )}
      </div>

      {activeView === 'customer' && bandStatus === 'error' && (
        <StatusMessage kind="error">
          <span>{bandError}</span>
          <button type="button" onClick={retryBands}>Retry band configuration</button>
        </StatusMessage>
      )}

      {activeView === 'customer' && bandStatus === 'loading' && (
        <StatusMessage kind="notice">Loading governed risk-band configuration…</StatusMessage>
      )}

      {customerStatus === 'loading' && (
        <div className="credit-risk-loading" role="status">
          <span className="credit-risk-spinner" />
          <div>
            <strong>Loading current customer risk evidence</strong>
            <p>Reading Customer 360 facts and append-only assessment history…</p>
          </div>
        </div>
      )}

      {customerStatus === 'error' && (
        <StatusMessage kind="error">{customerError}</StatusMessage>
      )}

      {activeView === 'customer' && customerStatus === 'error' && selectedCustomerNumber !== null && (
        <div className="credit-risk-degraded-history">
          <div>
            <strong>Live ERP evidence is unavailable.</strong>
            <p>
              ETOP will not present mismatched or stale customer facts and will not permit a new
              assessment without a current evidence snapshot. Existing local history remains separate.
            </p>
          </div>
          {historyError && <StatusMessage kind="error">{historyError}</StatusMessage>}
          <AssessmentHistory assessments={assessments} status={historyStatus} />
        </div>
      )}

      {customerStatus === 'idle' && selectedCustomerNumber === null && results.length === 0 && (
        <div className="credit-risk-empty-workspace">
          <strong>Search the real customer base to begin.</strong>
          <p>
            The workspace will show only evidence returned by connected sources and will
            identify every known gap before an assessment can be recorded.
          </p>
        </div>
      )}

      {snapshot && customerStatus === 'success' && (
        <div className="credit-risk-workspace">
          <section className="credit-risk-customer-header">
            <div>
              <div className="credit-risk-title-row">
                <h2>{snapshot.customer.customer_name}</h2>
                <SourceTag status={snapshot.source.status} />
              </div>
              <p>
                Customer {snapshot.customer.customer_number}
                {snapshot.customer.dba_name ? ` · ${snapshot.customer.dba_name}` : ''}
              </p>
              <small>
                {contactAddress || 'Address unavailable'} · {snapshot.customer.phone || 'Phone unavailable'}
              </small>
            </div>
            <div className="credit-risk-source-summary">
              <span>Source retrieved</span>
              <strong>{formatDateTime(snapshot.source.retrieved_at)}</strong>
              <small>{snapshot.source.system} · {snapshot.source.access}</small>
            </div>
          </section>

          {activeView === 'customer' ? (
          <>
          <section className="credit-risk-summary-grid">
            <div>
              <span>Manual risk rating</span>
              <strong>{latestAssessment ? latestAssessment.manual_rating : 'Not assessed'}</strong>
              <small>{displayedBand?.meaning ?? 'No local professional assessment'}</small>
            </div>
            <div>
              <span>Credit line</span>
              <strong>{formatMoney(snapshot.credit.credit_line)}</strong>
              <small>{snapshot.credit.terms_description}</small>
            </div>
            <div className="credit-risk-summary--partial">
              <span>Partial exposure</span>
              <strong>{formatMoney(snapshot.exposure.partial_exposure)}</strong>
              <small>{snapshot.exposure.completeness} evidence</small>
            </div>
            <div>
              <span>Past due</span>
              <strong>{formatMoney(snapshot.aging.past_due)}</strong>
              <small>Signed/net aging amount</small>
            </div>
            <div>
              <span>Next review</span>
              <strong>{formatDate(latestAssessment?.next_review_date)}</strong>
              <small>{latestAssessment ? 'From latest assessment' : 'Not scheduled'}</small>
            </div>
          </section>

          <div className="credit-risk-grid">
            <ExposurePanel snapshot={snapshot} />
            <AgingPanel aging={snapshot.aging} />
            <PaymentPanel payment={snapshot.payment} />
            {bands && <BandReference response={bands} />}
            <AssessmentForm
              bands={bandRows}
              draft={draft}
              errors={errors}
              busy={saveStatus === 'loading'}
              disabled={bandStatus !== 'success' || saveStatus === 'loading'}
              onChange={changeDraft}
              onSubmit={submitAssessment}
            />
            {saveMessage && (
              <div className="credit-risk-grid-message">
                <StatusMessage kind={saveMessageKind}>
                  {saveMessage}
                </StatusMessage>
              </div>
            )}
            {historyError && (
              <div className="credit-risk-grid-message">
                <StatusMessage kind="error">{historyError}</StatusMessage>
              </div>
            )}
            <AssessmentHistory assessments={assessments} status={historyStatus} />
          </div>

          <footer className="credit-risk-workspace-footer">
            <strong>Governance boundary</strong>
            <span>
              Assessment type: {snapshot.governance.assessment_type.replaceAll('_', ' ')} ·
              Automatic score: {snapshot.governance.automatic_score ? 'enabled' : 'not enabled'} ·
              ERP write: {snapshot.governance.erp_write ? 'enabled' : 'not permitted'}
            </span>
            {selectedSearchCustomer && (
              <small>Selected from shared Customer 360 search contract.</small>
            )}
          </footer>
          </>
          ) : activeView === 'credit_line' ? (
            <CreditLineIntelligencePanel customerNumber={snapshot.customer.customer_number} />
          ) : activeView === 'order_decision' ? (
            <OrderDecisionPreparationPanel
              key={snapshot.customer.customer_number}
              customerNumber={snapshot.customer.customer_number}
            />
          ) : (
            <CreditERPEvidencePanel
              key={snapshot.customer.customer_number}
              customerNumber={snapshot.customer.customer_number}
            />
          )}
        </div>
      )}
        </>
      )}
    </section>
  )
}
