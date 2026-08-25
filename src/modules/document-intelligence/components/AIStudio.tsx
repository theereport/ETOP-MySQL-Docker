import { useEffect, useMemo, useState } from 'react'

import {
  getDocumentParsers,
  getTrainingSessions,
  getTrainingSummary,
  getVendorInvoiceJobs,
} from '../api'

import type {
  TrainingSession,
  TrainingSummary,
} from '../types'

type StudioView = 'overview' | 'datasets' | 'training' | 'models' | 'rules'

const EMPTY_SUMMARY: TrainingSummary = {
  total_sessions: 0,
  total_documents: 0,
  expected_rows: 0,
  matched_rows: 0,
  missing_rows: 0,
  extra_rows: 0,
  amount_errors: 0,
  average_accuracy: 0,
  latest_session: null,
}

function percent(value: number) {
  return `${value.toFixed(1)}%`
}

function formatDate(value: string | undefined) {
  if (!value) return 'Not available'
  return new Date(value).toLocaleString('en-US')
}

export default function AIStudio() {
  const [view, setView] = useState<StudioView>('overview')
  const [summary, setSummary] = useState<TrainingSummary>(EMPTY_SUMMARY)
  const [sessions, setSessions] = useState<TrainingSession[]>([])
  const [vendorInvoiceDocumentCount, setVendorInvoiceDocumentCount] = useState(0)
  const [vendorParserAvailable, setVendorParserAvailable] = useState(false)
  const [vendorDatasetAvailable, setVendorDatasetAvailable] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [errorMessage, setErrorMessage] = useState('')

  const refresh = async () => {
    setIsLoading(true)
    setErrorMessage('')

    try {
      const [nextSummary, nextSessions] = await Promise.all([
        getTrainingSummary(),
        getTrainingSessions(50),
      ])
      setSummary(nextSummary)
      setSessions(nextSessions)
      const [vendorJobs, parsers] = await Promise.allSettled([
        getVendorInvoiceJobs(1, 0),
        getDocumentParsers(),
      ])
      setVendorDatasetAvailable(vendorJobs.status === 'fulfilled')
      setVendorInvoiceDocumentCount(
        vendorJobs.status === 'fulfilled' ? vendorJobs.value.total : 0,
      )
      setVendorParserAvailable(
        parsers.status === 'fulfilled'
        && parsers.value.some((parser) => parser.document_type === 'vendor_invoice'),
      )
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to load AI Studio data.',
      )
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      void refresh()
    }, 0)
    return () => window.clearTimeout(timeoutId)
  }, [])

  const rowAccuracy = useMemo(() => {
    if (summary.expected_rows === 0) return 0
    return (summary.matched_rows / summary.expected_rows) * 100
  }, [summary])

  const exceptionCount =
    summary.missing_rows + summary.extra_rows + summary.amount_errors

  return (
    <div className="ai-studio-shell">
      <aside className="ai-studio-nav">
        <div>
          <span>AI STUDIO</span>
          <strong>Training & Evaluation</strong>
        </div>
        {([
          ['overview', 'Overview', '⌂'],
          ['datasets', 'Datasets', '▦'],
          ['training', 'Training Runs', '↻'],
          ['models', 'Models', '◇'],
          ['rules', 'Rules', '⚙'],
        ] as const).map(([key, label, icon]) => (
          <button
            type="button"
            key={key}
            className={view === key ? 'active' : ''}
            onClick={() => setView(key)}
          >
            <span>{icon}</span>
            {label}
          </button>
        ))}
      </aside>

      <section className="ai-studio-content">
        <header className="ai-studio-header">
          <div>
            <span>LOCAL DOCUMENT INTELLIGENCE</span>
            <h2>{view === 'overview' ? 'AI Studio Overview' : view === 'datasets' ? 'Dataset Manager' : view === 'training' ? 'Training Runs' : view === 'models' ? 'Model Registry' : 'Business Rules'}</h2>
            <p>Measure ETOP against approved outputs and preserve every comparison as auditable training data.</p>
          </div>
          <button type="button" className="secondary" onClick={() => void refresh()} disabled={isLoading}>
            {isLoading ? 'Refreshing…' : 'Refresh'}
          </button>
        </header>

        {errorMessage && <div className="ed-banner error">{errorMessage}</div>}

        {view === 'overview' && (
          <>
            <section className="ai-studio-metrics">
              <article><span>Training Sessions</span><strong>{summary.total_sessions}</strong><small>Ground-truth comparisons</small></article>
              <article><span>Documents Trained</span><strong>{summary.total_documents}</strong><small>Unique source PDFs</small></article>
              <article><span>Average Accuracy</span><strong>{percent(summary.average_accuracy)}</strong><small>Across completed sessions</small></article>
              <article><span>Row Match Rate</span><strong>{percent(rowAccuracy)}</strong><small>{summary.matched_rows.toLocaleString()} of {summary.expected_rows.toLocaleString()} rows</small></article>
              <article><span>Open Differences</span><strong>{exceptionCount.toLocaleString()}</strong><small>Missing, extra, or wrong amount</small></article>
            </section>

            <div className="ai-studio-grid">
              <article className="ed-card ai-dataset-card">
                <div className="ed-card-heading">
                  <div><strong>PNC Lockbox Dataset</strong><span>Production ground-truth dataset</span></div>
                  <span className="ai-status-badge">ACTIVE</span>
                </div>
                <div className="ai-progress-block">
                  <div><span>Current Accuracy</span><strong>{percent(summary.average_accuracy)}</strong></div>
                  <div className="ai-progress"><span style={{ width: `${Math.min(100, summary.average_accuracy)}%` }} /></div>
                </div>
                <dl className="ai-detail-list">
                  <div><dt>Expected rows</dt><dd>{summary.expected_rows.toLocaleString()}</dd></div>
                  <div><dt>Matched rows</dt><dd>{summary.matched_rows.toLocaleString()}</dd></div>
                  <div><dt>Missing rows</dt><dd>{summary.missing_rows.toLocaleString()}</dd></div>
                  <div><dt>Extra rows</dt><dd>{summary.extra_rows.toLocaleString()}</dd></div>
                  <div><dt>Amount errors</dt><dd>{summary.amount_errors.toLocaleString()}</dd></div>
                </dl>
              </article>

              <article className="ed-card">
                <div className="ed-card-heading">
                  <div><strong>Latest Evaluation</strong><span>Most recent approved PNC comparison</span></div>
                </div>
                {summary.latest_session ? (
                  <div className="ai-latest-run">
                    <strong>{summary.latest_session.source_pdf_name}</strong>
                    <span>{summary.latest_session.ground_truth_file_name}</span>
                    <div className="ai-score-ring">{percent(summary.latest_session.overall_accuracy)}</div>
                    <small>{formatDate(summary.latest_session.updated_at)}</small>
                  </div>
                ) : (
                  <div className="ai-empty-state">Upload an approved PNC workbook from Lockbox Automation to create the first evaluation.</div>
                )}
              </article>
            </div>
          </>
        )}

        {view === 'datasets' && (
          <section className="ed-card">
            <div className="ed-card-heading">
              <div><strong>Registered Datasets</strong><span>Ground truth used to evaluate and improve document parsers</span></div>
            </div>
            <div className="ai-dataset-table">
              <div className="ai-dataset-row header"><span>Dataset</span><span>Documents</span><span>Rows</span><span>Accuracy</span><span>Status</span></div>
              <div className="ai-dataset-row"><strong>PNC Lockbox</strong><span>{summary.total_documents}</span><span>{summary.expected_rows.toLocaleString()}</span><span>{percent(summary.average_accuracy)}</span><span className="ai-status-badge">ACTIVE</span></div>
              <div className="ai-dataset-row"><strong>Vendor Invoice Dataset &amp; OCR</strong><span>{vendorDatasetAvailable ? vendorInvoiceDocumentCount : '—'}</span><span>Field evidence</span><span>Not evaluated</span><span className="ai-status-badge">{vendorDatasetAvailable && vendorParserAvailable ? 'ACTIVE' : 'UNAVAILABLE'}</span></div>
              <div className="ai-dataset-row muted"><strong>Proof of Delivery</strong><span>0</span><span>0</span><span>—</span><span>PLANNED</span></div>
            </div>
          </section>
        )}

        {view === 'training' && (
          <section className="ed-card">
            <div className="ed-card-heading">
              <div><strong>Training History</strong><span>Every saved PDF-to-workbook comparison</span></div>
              <span>{sessions.length} runs</span>
            </div>
            <div className="ed-table-wrap">
              <table className="ed-table">
                <thead><tr><th>Source PDF</th><th>Ground Truth</th><th>Accuracy</th><th>Matched</th><th>Exceptions</th><th>Completed</th></tr></thead>
                <tbody>
                  {sessions.map((session) => (
                    <tr key={session.session_id}>
                      <td><strong>{session.source_pdf_name}</strong></td>
                      <td>{session.ground_truth_file_name}</td>
                      <td><strong>{percent(session.overall_accuracy)}</strong></td>
                      <td>{session.matched_rows} / {session.expected_rows}</td>
                      <td>{session.missing_rows + session.extra_rows + session.amount_errors}</td>
                      <td>{formatDate(session.updated_at)}</td>
                    </tr>
                  ))}
                  {!isLoading && sessions.length === 0 && <tr><td colSpan={6}>No training sessions have been saved yet.</td></tr>}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {view === 'models' && (
          <section className="ai-model-grid">
            <article className="ed-card ai-model-card">
              <div><span>PRODUCTION</span><strong>PNC Lockbox Parser</strong><small>Current deterministic OCR and allocation pipeline</small></div>
              <div className="ai-model-version">v1.0</div>
              <dl className="ai-detail-list"><div><dt>Evaluation accuracy</dt><dd>{percent(summary.average_accuracy)}</dd></div><div><dt>Documents evaluated</dt><dd>{summary.total_documents}</dd></div><div><dt>Deployment</dt><dd>Local</dd></div></dl>
            </article>
            <article className="ed-card ai-model-card planned">
              <div><span>DEVELOPMENT</span><strong>Next Parser Candidate</strong><small>Created when parser changes are replayed against the dataset</small></div>
              <div className="ai-model-version">—</div>
              <button type="button" className="secondary" disabled>Replay foundation planned</button>
            </article>
          </section>
        )}

        {view === 'rules' && (
          <section className="ed-card">
            <div className="ed-card-heading"><div><strong>Active Lockbox Rules</strong><span>Auditable safeguards applied before export</span></div></div>
            <div className="ai-rule-list">
              {[
                ['No-remittance placeholder', 'Use invoice 9999999999 and allocate the full check amount when no valid remittance rows exist.'],
                ['Ignore totals and subtotals', 'Do not export total, subtotal, balance-due, or payment-total lines as invoices.'],
                ['Balance validation', 'Compare allocation total with the check amount before marking a transaction balanced.'],
                ['Identifier protection', 'Reject check, routing, account, batch, and transaction identifiers as invoice candidates.'],
                ['Credit handling', 'Preserve approved negative allocation rows when they are part of the remittance detail.'],
              ].map(([title, description]) => (
                <article key={title}><span className="ai-rule-toggle">✓</span><div><strong>{title}</strong><p>{description}</p></div><small>Active</small></article>
              ))}
            </div>
          </section>
        )}
      </section>
    </div>
  )
}
