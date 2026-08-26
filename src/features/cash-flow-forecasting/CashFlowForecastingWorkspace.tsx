import { useEffect, useState } from 'react'
import {
  createSnapshot,
  getAccuracyHistory,
  getCurrentForecast,
  recordClosedWeeks,
  refreshApCache,
} from './api'
import type {
  CashFlowAccuracyWeek,
  CashFlowForecastResponse,
  PriorYearWeekComparison,
  WeeklyProjection,
} from './types'
import './CashFlowForecastingWorkspace.css'

const money = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0,
})

function formatMoney(value: number | null | undefined): string {
  return value == null ? 'Unavailable' : money.format(value)
}

function formatDate(value: string | null | undefined): string {
  if (!value) return 'Unavailable'
  const date = new Date(`${value}T00:00:00`)
  return Number.isNaN(date.valueOf())
    ? value
    : date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return 'Unavailable'
  const date = new Date(value)
  return Number.isNaN(date.valueOf())
    ? value
    : date.toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })
}

function varianceClass(value: number | null | undefined): string {
  if (value == null) return ''
  if (value > 0) return 'cff-variance-positive'
  if (value < 0) return 'cff-variance-negative'
  return ''
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback
}

export default function CashFlowForecastingWorkspace() {
  const [forecast, setForecast] = useState<CashFlowForecastResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [accuracyWeeks, setAccuracyWeeks] = useState<CashFlowAccuracyWeek[]>([])

  const [actionMessage, setActionMessage] = useState('')
  const [refreshingApCache, setRefreshingApCache] = useState(false)
  const [creatingSnapshot, setCreatingSnapshot] = useState(false)
  const [recordingClosedWeeks, setRecordingClosedWeeks] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError('')
    getCurrentForecast(undefined, controller.signal)
      .then(setForecast)
      .catch((err) => {
        if (controller.signal.aborted) return
        setError(errorMessage(err, 'Unable to load the cash flow forecast.'))
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false)
      })

    getAccuracyHistory(controller.signal)
      .then((response) => setAccuracyWeeks(response.weeks))
      .catch(() => undefined)

    return () => controller.abort()
  }, [])

  async function handleRefreshApCache() {
    setRefreshingApCache(true)
    setActionMessage('Scanning open payables - this takes a few minutes...')
    try {
      const result = await refreshApCache()
      setActionMessage(
        result.status === 'ok'
          ? `AP cache refreshed: ${result.weeks_cached} weeks cached from ${result.source_rows?.toLocaleString()} rows.`
          : `AP cache refresh unavailable: ${result.message ?? 'unknown error'}`,
      )
      const updated = await getCurrentForecast()
      setForecast(updated)
    } catch (err) {
      setActionMessage(errorMessage(err, 'AP cache refresh failed.'))
    } finally {
      setRefreshingApCache(false)
    }
  }

  async function handleCreateSnapshot() {
    setCreatingSnapshot(true)
    try {
      const result = await createSnapshot()
      setActionMessage(`Snapshot saved: ${result.snapshot_id}`)
    } catch (err) {
      setActionMessage(errorMessage(err, 'Could not save a snapshot.'))
    } finally {
      setCreatingSnapshot(false)
    }
  }

  async function handleRecordClosedWeeks() {
    setRecordingClosedWeeks(true)
    try {
      const result = await recordClosedWeeks()
      setActionMessage(
        `Recorded ${result.recorded} newly-closed week(s); ${result.already_recorded} already on file.`,
      )
      const response = await getAccuracyHistory()
      setAccuracyWeeks(response.weeks)
    } catch (err) {
      setActionMessage(errorMessage(err, 'Could not record closed weeks.'))
    } finally {
      setRecordingClosedWeeks(false)
    }
  }

  return (
    <div className="cff-workspace">
      <header className="cff-header">
        <div>
          <h2>Cash Flow Forecasting</h2>
          <p className="cff-subtitle">
            14-week rolling operating cash flow projection, with a same-week-last-year
            backtest and an accuracy history that builds as weeks close.
          </p>
        </div>
        <div className="cff-actions">
          <button onClick={handleRefreshApCache} disabled={refreshingApCache}>
            {refreshingApCache ? 'Refreshing AP cache...' : 'Refresh AP cache'}
          </button>
          <button onClick={handleCreateSnapshot} disabled={creatingSnapshot}>
            {creatingSnapshot ? 'Saving...' : 'Save snapshot'}
          </button>
          <button onClick={handleRecordClosedWeeks} disabled={recordingClosedWeeks}>
            {recordingClosedWeeks ? 'Recording...' : 'Record closed weeks'}
          </button>
        </div>
      </header>

      {actionMessage && <div className="cff-action-message">{actionMessage}</div>}

      {loading && <div className="cff-status">Loading forecast...</div>}
      {error && <div className="cff-status cff-status-error">{error}</div>}

      {forecast && (
        <>
          <section className="cff-starting-position">
            <h3>Starting cash position</h3>
            <div className="cff-position-grid">
              <div>
                <span className="cff-position-label">As of business day</span>
                <span className="cff-position-value">
                  {formatDate(forecast.starting_position.business_day)}
                </span>
              </div>
              <div>
                <span className="cff-position-label">Net available</span>
                <span className="cff-position-value">
                  {formatMoney(forecast.starting_position.net_available)}
                </span>
              </div>
              <div>
                <span className="cff-position-label">Line of Credit balance</span>
                <span className="cff-position-value">
                  {formatMoney(forecast.starting_position.line_of_credit_balance)}
                </span>
              </div>
              <div>
                <span className="cff-position-label">Line of Credit available</span>
                <span className="cff-position-value">
                  {formatMoney(forecast.starting_position.line_of_credit_available)}
                </span>
              </div>
            </div>
            <p className="cff-explanation">{forecast.starting_position.explanation}</p>
          </section>

          <section className="cff-table-section">
            <h3>14-week projection</h3>
            <div className="cff-table-scroll">
              <table className="cff-table">
                <thead>
                  <tr>
                    <th>Week</th>
                    <th>Projected AR</th>
                    <th>Projected AP</th>
                    <th>Projected other</th>
                    <th>Projected ending balance</th>
                  </tr>
                </thead>
                <tbody>
                  {forecast.weeks.map((week: WeeklyProjection) => (
                    <tr key={week.week_index}>
                      <td>
                        {formatDate(week.week_start)} - {formatDate(week.week_end)}
                      </td>
                      <td>{formatMoney(week.projected_ar)}</td>
                      <td>{formatMoney(week.projected_ap)}</td>
                      <td>{formatMoney(week.projected_other)}</td>
                      <td>{formatMoney(week.projected_ending_balance)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="cff-table-section">
            <h3>Same week, last year</h3>
            <div className="cff-table-scroll">
              <table className="cff-table">
                <thead>
                  <tr>
                    <th>Week</th>
                    <th>Prior-year week</th>
                    <th>2025 projected AR</th>
                    <th>2025 actual AR</th>
                    <th>Variance AR</th>
                    <th>2025 actual AP</th>
                    <th>2025 projected other</th>
                    <th>2025 actual other</th>
                    <th>Variance other</th>
                    <th>2025 actual ending</th>
                    <th>Week closed?</th>
                    <th>This year actual ending</th>
                  </tr>
                </thead>
                <tbody>
                  {forecast.prior_year_comparison.map((week: PriorYearWeekComparison) => (
                    <tr key={week.week_index}>
                      <td>{formatDate(week.week_start)}</td>
                      <td>
                        {formatDate(week.prior_year_week_start)} -{' '}
                        {formatDate(week.prior_year_week_end)}
                      </td>
                      <td>{formatMoney(week.prior_year_projected_ar)}</td>
                      <td>{formatMoney(week.prior_year_actual_ar)}</td>
                      <td className={varianceClass(week.prior_year_variance_ar)}>
                        {formatMoney(week.prior_year_variance_ar)}
                      </td>
                      <td>{formatMoney(week.prior_year_actual_ap)}</td>
                      <td>{formatMoney(week.prior_year_projected_other)}</td>
                      <td>{formatMoney(week.prior_year_actual_other)}</td>
                      <td className={varianceClass(week.prior_year_variance_other)}>
                        {formatMoney(week.prior_year_variance_other)}
                      </td>
                      <td>{formatMoney(week.prior_year_actual_ending_balance)}</td>
                      <td>{week.current_year_week_closed ? 'Closed' : 'Open'}</td>
                      <td>{formatMoney(week.current_year_actual_ending_balance)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="cff-explanation">
              AP has no prior-year projected figure - MaddenCo does not retain a permanent
              due-date record for paid invoices, so only the actual AP cash-out is shown for
              2025.
            </p>
          </section>

          {accuracyWeeks.length > 0 && (
            <section className="cff-table-section">
              <h3>Accuracy history (closed weeks)</h3>
              <div className="cff-table-scroll">
                <table className="cff-table">
                  <thead>
                    <tr>
                      <th>Week</th>
                      <th>Projected ending</th>
                      <th>Actual ending</th>
                      <th>Variance</th>
                      <th>Recorded</th>
                    </tr>
                  </thead>
                  <tbody>
                    {accuracyWeeks.map((week) => (
                      <tr key={`${week.week_start}-${week.week_end}`}>
                        <td>
                          {formatDate(week.week_start)} - {formatDate(week.week_end)}
                        </td>
                        <td>{formatMoney(week.projected_ending_balance)}</td>
                        <td>{formatMoney(week.actual_ending_balance)}</td>
                        <td className={varianceClass(week.variance_ending_balance)}>
                          {formatMoney(week.variance_ending_balance)}
                        </td>
                        <td>{formatDateTime(week.recorded_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <section className="cff-gaps">
            <h3>What this module does not compute</h3>
            <ul>
              {forecast.gaps.map((gap) => (
                <li key={gap.code}>
                  <strong>{gap.label}.</strong> {gap.explanation}
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  )
}
