import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  askAPVendorSpendQuestion,
  getAPVendorSpendReadiness,
} from './api'
import { Message, StatusTag } from './components'
import {
  errorMessage,
  formatCurrency,
  formatDateTime,
  formatNumber,
  isAbortError,
  titleCase,
} from './format'
import type {
  APSpendQuestionResponse,
  APSpendReadinessResponse,
} from './types'

type AsyncStatus = 'idle' | 'loading' | 'success' | 'error'

const starterQuestions = [
  'What was total vendor spend in division 3 for calendar year 2026?',
  'Which vendor had the highest spend for account 5050-3 this month?',
  'Which vendor had the highest spend each month for account 5050-3 in calendar year 2026?',
  'Which vendor had the highest spend for account 5050-3 in ERP accounting year 2026 period 8?',
]

function monthLabel(year: number, month: number): string {
  return new Intl.DateTimeFormat(undefined, {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(Date.UTC(year, month - 1, 1)))
}

function timeBasisLabel(result: APSpendQuestionResponse): string {
  const { parsed } = result
  if (parsed.time_basis === 'calendar_invoice_date') {
    const range = parsed.range_start && parsed.range_end_exclusive
      ? `${parsed.range_start} through ${parsed.range_end_exclusive} (exclusive)`
      : 'Calendar range unavailable'
    return `PMGDTEINV calendar invoice date · ${range}`
  }
  if (parsed.time_basis === 'erp_accounting_period') {
    return `PMGYR ${parsed.year ?? '—'} · PMGPR ${parsed.accounting_period ?? '—'}`
  }
  if (parsed.time_basis === 'erp_accounting_year') {
    return `PMGYR ${parsed.year ?? '—'} · raw ERP accounting year`
  }
  return 'Not resolved'
}

export default function APVendorSpendIntelligence({ refreshKey }: { refreshKey: number }) {
  const [readiness, setReadiness] = useState<APSpendReadinessResponse | null>(null)
  const [readinessStatus, setReadinessStatus] = useState<AsyncStatus>('loading')
  const [readinessError, setReadinessError] = useState('')
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState<APSpendQuestionResponse | null>(null)
  const [questionStatus, setQuestionStatus] = useState<AsyncStatus>('idle')
  const [questionError, setQuestionError] = useState('')
  const readinessAbortRef = useRef<AbortController | null>(null)
  const questionAbortRef = useRef<AbortController | null>(null)
  const questionGeneration = useRef(0)

  const loadReadiness = useCallback(async () => {
    readinessAbortRef.current?.abort()
    const controller = new AbortController()
    readinessAbortRef.current = controller
    setReadinessStatus('loading')
    setReadinessError('')
    try {
      const response = await getAPVendorSpendReadiness(controller.signal)
      setReadiness(response)
      setReadinessStatus('success')
    } catch (error) {
      if (isAbortError(error)) return
      setReadiness(null)
      setReadinessStatus('error')
      setReadinessError(errorMessage(error, 'Unable to verify AP vendor-spend source readiness.'))
    }
  }, [])

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void loadReadiness()
    }, 0)
    return () => {
      window.clearTimeout(timeoutId)
      readinessAbortRef.current?.abort()
      questionAbortRef.current?.abort()
    }
  }, [loadReadiness, refreshKey])

  async function askQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const normalized = question.trim()
    if (normalized.length < 3) {
      setQuestionStatus('error')
      setQuestionError('Enter a total-spend or highest-vendor question with a division and date scope.')
      return
    }

    questionAbortRef.current?.abort()
    const controller = new AbortController()
    questionAbortRef.current = controller
    const generation = questionGeneration.current + 1
    questionGeneration.current = generation
    setQuestionStatus('loading')
    setQuestionError('')
    setResult(null)
    try {
      const response = await askAPVendorSpendQuestion(normalized, controller.signal)
      if (generation !== questionGeneration.current) return
      setResult(response)
      setReadiness(response.readiness)
      setQuestionStatus('success')
    } catch (error) {
      if (isAbortError(error) || generation !== questionGeneration.current) return
      setQuestionStatus('error')
      setQuestionError(errorMessage(error, 'Unable to answer the governed AP vendor-spend question.'))
    }
  }

  return (
    <div className="ap-spend-intelligence">
      <section className="ap-panel ap-spend-boundary">
        <div className="ap-panel-heading">
          <div>
            <span className="ap-kicker">Deterministic question service</span>
            <h2>Ask about vendor spend</h2>
          </div>
          <StatusTag status="read only" />
        </div>
        <p>
          ETOP parses only three governed forms: total signed posted AP GL-distribution amount, highest vendor for one period, and highest vendor for each calendar month in one year. It never sends the question to an external model and never turns it into arbitrary SQL.
        </p>
        <p>
          “Spend” here means <strong>PMGLDS.PMGAMTINV signed as stored</strong>. It is not cash paid, current open AP, approval status, payment execution, or a vendor-performance score.
        </p>
      </section>

      <section className="ap-panel">
        <div className="ap-panel-heading">
          <div>
            <span className="ap-kicker">Source gate</span>
            <h2>Mapping readiness</h2>
          </div>
          {readiness && <StatusTag status={readiness.status} />}
        </div>
        {readinessStatus === 'loading' && (
          <div className="ap-loading ap-loading--compact" role="status">
            <span className="ap-spinner" />
            <div><strong>Verifying source fields</strong><p>Reading bounded INFORMATION_SCHEMA metadata only…</p></div>
          </div>
        )}
        {readinessStatus === 'error' && (
          <Message kind="error">
            <span>{readinessError}</span>
            <button type="button" onClick={() => void loadReadiness()}>Retry readiness</button>
          </Message>
        )}
        {readiness && readinessStatus === 'success' && (
          <>
            <div className="ap-spend-readiness-grid">
              {readiness.mapping_checks.map((check) => (
                <article key={check.key}>
                  <div><strong>{check.label}</strong><StatusTag status={check.status} /></div>
                  <span>{check.source}</span>
                  <p>{check.explanation}</p>
                  {check.missing_fields.length > 0 && <small>Missing: {check.missing_fields.join(', ')}</small>}
                  {check.incompatible_fields.length > 0 && <small>Incompatible: {check.incompatible_fields.join('; ')}</small>}
                </article>
              ))}
              <article>
                <div><strong>Local data dictionary</strong><StatusTag status={readiness.local_data_dictionary_status} /></div>
                <span>{readiness.local_data_dictionary_path || 'Not present in accepted source tree'}</span>
                <p>Diagnostic metadata only. SRC-005 plus runtime schema verification govern this bounded mapping.</p>
              </article>
            </div>
            <details className="ap-spend-date-bases">
              <summary>Date bases and unresolved mappings</summary>
              <div>
                {readiness.date_bases.map((basis) => (
                  <article key={basis.key}>
                    <span><strong>{basis.label}</strong><StatusTag status={basis.status} /></span>
                    <p>{basis.explanation}</p>
                    <small>{basis.source_fields.join(', ') || 'No source connected'}</small>
                  </article>
                ))}
              </div>
              <ul>
                {readiness.product_owner_mappings_needed.map((gap) => <li key={gap}>{gap}</li>)}
              </ul>
            </details>
            {readiness.warnings.length > 0 && <Message kind="notice"><ul>{readiness.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></Message>}
          </>
        )}
      </section>

      <section className="ap-panel ap-spend-question-panel">
        <div className="ap-panel-heading">
          <div><span className="ap-kicker">Supported natural language</span><h2>Ask one question</h2></div>
        </div>
        <form onSubmit={askQuestion}>
          <label htmlFor="ap-spend-question">Vendor-spend question</label>
          <div>
            <textarea
              id="ap-spend-question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              maxLength={300}
              rows={3}
              placeholder="Example: Which vendor had the highest spend for account 5050-3 this month?"
              disabled={questionStatus === 'loading'}
            />
            <button className="ap-primary-button" type="submit" disabled={questionStatus === 'loading'}>
              {questionStatus === 'loading' ? 'Reading ERP evidence…' : 'Answer from ERP evidence'}
            </button>
          </div>
        </form>
        <div className="ap-spend-examples" aria-label="Supported example questions">
          {starterQuestions.map((example) => (
            <button type="button" key={example} onClick={() => setQuestion(example)}>{example}</button>
          ))}
        </div>
        <small>For `account 5050-3`, ETOP parses account 5050 and division 3. Calendar questions use invoice date; explicit ERP accounting questions use PMGYR/PMGPR.</small>
      </section>

      {questionStatus === 'loading' && (
        <div className="ap-loading" role="status">
          <span className="ap-spinner" />
          <div><strong>Running governed aggregate</strong><p>Fixed intent, parameter-bound filters, read-only PMGLDS evidence…</p></div>
        </div>
      )}
      {questionError && <Message kind="error">{questionError}</Message>}

      {result && questionStatus === 'success' && (
        <>
          <Message kind={result.status === 'answered' ? 'success' : result.status === 'degraded' ? 'error' : 'notice'}>
            <div><strong>{titleCase(result.status)}</strong><span>{result.answer_text}</span></div>
          </Message>

          <section className="ap-panel">
            <div className="ap-panel-heading">
              <div><span className="ap-kicker">Parser trace</span><h2>What ETOP understood</h2></div>
              <StatusTag status={result.parsed.intent || 'intent unavailable'} />
            </div>
            <dl className="ap-spend-parsed-grid">
              <div><dt>Division</dt><dd>{result.parsed.division || 'Unavailable'}</dd></div>
              <div><dt>GL account</dt><dd>{result.parsed.account || 'All accounts in division'}</dd></div>
              <div><dt>Date basis</dt><dd>{timeBasisLabel(result)}</dd></div>
              <div><dt>Parser</dt><dd>{result.parsed.parser_version}</dd></div>
            </dl>
            {result.parsed.interpretation_notes.length > 0 && <ul className="ap-spend-notes">{result.parsed.interpretation_notes.map((note) => <li key={note}>{note}</li>)}</ul>}
            {(result.parsed.missing_slots.length > 0 || result.parsed.ambiguous_slots.length > 0 || result.parsed.unavailable_slots.length > 0) && (
              <div className="ap-spend-slot-gaps">
                <span>Missing: {result.parsed.missing_slots.join(', ') || 'none'}</span>
                <span>Ambiguous: {result.parsed.ambiguous_slots.join(', ') || 'none'}</span>
                <span>Unavailable: {result.parsed.unavailable_slots.join(', ') || 'none'}</span>
              </div>
            )}
          </section>

          {result.total && result.total.amount_available_row_count > 0 && (
            <section className="ap-panel">
              <div className="ap-panel-heading"><div><span className="ap-kicker">Exact aggregate</span><h2>Signed distribution totals</h2></div></div>
              <div className="ap-spend-total-grid">
                <article><span>Positive distributions</span><strong>{formatCurrency(result.total.positive_distribution_amount)}</strong><small>PMGAMTINV &gt; 0</small></article>
                <article><span>Negative distributions</span><strong>{formatCurrency(result.total.negative_distribution_amount)}</strong><small>PMGAMTINV &lt; 0</small></article>
                <article className="is-net"><span>Net signed amount</span><strong>{formatCurrency(result.total.net_signed_amount)}</strong><small>Positive plus negative</small></article>
                <article><span>Evidence coverage</span><strong>{formatNumber(result.total.distribution_row_count)} rows</strong><small>{formatNumber(result.total.invoice_identity_count)} invoice identities · {formatNumber(result.total.vendor_count)} vendors</small></article>
              </div>
            </section>
          )}

          {result.ranking.length > 0 && (
            <section className="ap-panel">
              <div className="ap-panel-heading">
                <div><span className="ap-kicker">Deterministic order</span><h2>Vendor ranking</h2><p>Net signed PMGAMTINV descending; displayed ties retain the same rank. {result.leader_set_complete === false ? 'The leader tie may extend beyond the row cap.' : ''}</p></div>
                <StatusTag status={result.ranking_complete === false ? 'partial' : 'available'} />
              </div>
              <div className="ap-spend-table-wrap">
                <table className="ap-spend-table">
                  <thead><tr><th>Rank</th><th>Vendor</th><th>Positive</th><th>Negative</th><th>Net signed</th><th>Invoices / rows</th></tr></thead>
                  <tbody>
                    {result.ranking.map((vendor) => (
                      <tr key={`${vendor.rank}:${vendor.vendor_number}`} className={vendor.rank === 1 ? 'is-leader' : ''}>
                        <td>{vendor.rank}</td>
                        <td><strong>{vendor.vendor_name || 'Vendor name unavailable'}</strong><small>#{vendor.vendor_number}</small></td>
                        <td>{formatCurrency(vendor.positive_distribution_amount)}</td>
                        <td>{formatCurrency(vendor.negative_distribution_amount)}</td>
                        <td><strong>{formatCurrency(vendor.net_signed_amount)}</strong></td>
                        <td>{formatNumber(vendor.invoice_identity_count)} / {formatNumber(vendor.distribution_row_count)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {result.monthly_periods.length > 0 && (
            <section className="ap-panel">
              <div className="ap-panel-heading">
                <div>
                  <span className="ap-kicker">Twelve fixed monthly rankings</span>
                  <h2>Highest vendor by calendar month</h2>
                  <p>Ordered January through December. Each month is independently bounded to {result.monthly_leader_limit} displayed vendors inside the same read-only ERP snapshot.</p>
                </div>
                <StatusTag status={result.monthly_periods.every((period) => period.leader_set_complete) ? 'available' : 'partial'} />
              </div>
              <div className="ap-spend-table-wrap">
                <table className="ap-spend-table ap-spend-monthly-table">
                  <thead><tr><th>Calendar month</th><th>Highest vendor evidence</th><th>Net signed</th><th>Coverage</th></tr></thead>
                  <tbody>
                    {result.monthly_periods.map((period) => (
                      <tr key={`${period.calendar_year}-${period.calendar_month}`} className={period.status === 'available' ? 'is-leader' : ''}>
                        <td>
                          <strong>{monthLabel(period.calendar_year, period.calendar_month)}</strong>
                          <small>{period.range_start} to {period.range_end_exclusive} (exclusive)</small>
                        </td>
                        <td>
                          {period.leaders.length === 0 ? (
                            <span>No non-null amount evidence</span>
                          ) : period.leaders.map((vendor) => (
                            <span key={vendor.vendor_number} className="ap-spend-monthly-vendor">
                              <strong>{vendor.vendor_name || `Vendor #${vendor.vendor_number}`}</strong>
                              <small>#{vendor.vendor_number} · positive {formatCurrency(vendor.positive_distribution_amount)} · negative {formatCurrency(vendor.negative_distribution_amount)}</small>
                            </span>
                          ))}
                        </td>
                        <td><strong>{period.leaders.length > 0 ? formatCurrency(period.leaders[0].net_signed_amount) : '—'}</strong></td>
                        <td>
                          <StatusTag status={period.status === 'available' ? period.leader_set_complete ? 'available' : 'partial' : 'unavailable'} />
                          <small>{period.status === 'no_evidence' ? 'No non-null amount evidence' : period.leader_set_complete ? 'Leader set complete' : 'Additional rank-1 ties may be hidden'}</small>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {result.warnings.length > 0 && <Message kind="notice"><ul>{result.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></Message>}

          <section className="ap-panel ap-spend-evidence">
            <div className="ap-panel-heading"><div><span className="ap-kicker">Evidence envelope</span><h2>Source, coverage, and limits</h2></div></div>
            <div className="ap-spend-evidence-grid">
              <article><span>Retrieved</span><strong>{formatDateTime(result.generated_at)}</strong><small>{result.evidence_as_of ? `Snapshot opened ${formatDateTime(result.evidence_as_of)}` : 'No completed source snapshot'}</small></article>
              <article><span>Sources</span><strong>{result.source_references.map((source) => source.source_object).join(', ') || 'No financial rows queried'}</strong><small>{result.readiness.source_schema}</small></article>
              <article><span>Ranking row cap</span><strong>{result.monthly_periods.length > 0 ? `${result.monthly_leader_limit} per month` : result.ranking_row_limit}</strong><small>{result.monthly_periods.length > 0 ? `${result.monthly_period_limit} fixed calendar periods` : result.ranking_complete == null ? 'Not applicable' : result.ranking_complete ? 'Displayed ranking complete' : result.leader_set_complete === false ? 'Additional rank-1 vendors may be hidden' : 'Additional lower-ranked vendors not displayed'}</small></article>
              <article><span>Evidence consistency</span><strong>{result.evidence_consistency === 'single_read_only_consistent_snapshot' ? 'One read-only snapshot' : result.evidence_consistency === 'consistent_snapshot_query_failed' ? 'Snapshot query failed' : 'No financial query'}</strong><small>{result.evidence_consistency === 'single_read_only_consistent_snapshot' ? 'Totals, ranking, and names share one database snapshot' : result.evidence_consistency === 'consistent_snapshot_query_failed' ? 'No completed evidence packet or consistency claim' : 'No source snapshot was asserted'}</small></article>
              <article><span>Evidence SHA-256</span><strong>{result.evidence_sha256.slice(0, 16)}…</strong><small>{result.contract_version}</small></article>
            </div>
            {result.coverage.map((item) => (
              <div className="ap-spend-coverage-row" key={item.key}>
                <span><strong>{item.label}</strong><StatusTag status={item.status} /></span>
                <p>{item.explanation}</p>
                <small>{item.source || 'No source'} · {item.record_count ?? 0} row(s) · complete {String(item.complete)}</small>
              </div>
            ))}
            <div className="ap-spend-governance">
              <strong>No financial action</strong>
              <p>{result.governance.source_authority}</p>
              <ul>{result.governance.statements.map((statement) => <li key={statement}>{statement}</li>)}</ul>
            </div>
          </section>
        </>
      )}
    </div>
  )
}
