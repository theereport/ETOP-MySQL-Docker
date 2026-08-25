import { Fragment, useMemo, useState } from 'react'

import type {
  AutomationDefinition,
  AutomationExecution,
} from './AutomationCenter'

type ExecutionHistoryProps = {
  executions: AutomationExecution[]
  automations: AutomationDefinition[]
  isRunning: boolean
  onOpenExecution: (execution: AutomationExecution) => void
  onRetryExecution?: (execution: AutomationExecution) => void
  onRunAutomation?: (automation: AutomationDefinition) => void
  onClearHistory?: () => void
  onBack?: () => void
}

type ExecutionStatusFilter =
  | 'all'
  | 'running'
  | 'success'
  | 'warning'
  | 'failed'
  | 'cancelled'

type DateRangeFilter = 'all' | 'today' | '7-days' | '30-days'

type SortOption =
  | 'started-desc'
  | 'started-asc'
  | 'duration-desc'
  | 'duration-asc'
  | 'rows-desc'
  | 'status'

function formatDateTime(value: string | null | undefined) {
  if (!value) {
    return '-'
  }

  const parsedDate = new Date(value)

  return Number.isNaN(parsedDate.getTime())
    ? value
    : parsedDate.toLocaleString()
}

function formatDuration(durationMs: number | null | undefined) {
  if (durationMs === null || durationMs === undefined) {
    return '-'
  }

  if (durationMs < 1000) {
    return `${durationMs} ms`
  }

  const totalSeconds = durationMs / 1000

  if (totalSeconds < 60) {
    return `${totalSeconds.toFixed(2)} sec`
  }

  const totalMinutes = Math.floor(totalSeconds / 60)
  const remainingSeconds = Math.floor(totalSeconds % 60)

  if (totalMinutes < 60) {
    return `${totalMinutes}m ${remainingSeconds}s`
  }

  const totalHours = Math.floor(totalMinutes / 60)
  const remainingMinutes = totalMinutes % 60

  return `${totalHours}h ${remainingMinutes}m`
}

function formatRowCount(rowCount: number | null | undefined) {
  return rowCount === null || rowCount === undefined
    ? '-'
    : rowCount.toLocaleString()
}

function getExecutionTimestamp(execution: AutomationExecution) {
  const timestamp = new Date(execution.startedAt).getTime()
  return Number.isNaN(timestamp) ? 0 : timestamp
}

function isExecutionInDateRange(
  execution: AutomationExecution,
  dateRange: DateRangeFilter,
) {
  if (dateRange === 'all') {
    return true
  }

  const startedTimestamp = getExecutionTimestamp(execution)

  if (!startedTimestamp) {
    return false
  }

  const now = new Date()

  if (dateRange === 'today') {
    const startOfToday = new Date(
      now.getFullYear(),
      now.getMonth(),
      now.getDate(),
    ).getTime()

    return startedTimestamp >= startOfToday
  }

  const days = dateRange === '7-days' ? 7 : 30
  const cutoff = now.getTime() - days * 24 * 60 * 60 * 1000

  return startedTimestamp >= cutoff
}

function getFileNameFromPath(filePath: string) {
  const normalizedPath = filePath.replaceAll('\\', '/')

  return normalizedPath.split('/').filter(Boolean).at(-1) || filePath
}

function getExecutionOutputPath(execution: AutomationExecution) {
  if (execution.outputFilePath) {
    return execution.outputFilePath
  }

  return execution.outputFileName
}

function getExecutionError(execution: AutomationExecution) {
  return execution.errorDetails || ''
}

function ExecutionHistory({
  executions,
  automations,
  isRunning,
  onOpenExecution,
  onRetryExecution,
  onRunAutomation,
  onClearHistory,
  onBack,
}: ExecutionHistoryProps) {
  const [searchText, setSearchText] = useState('')
  const [statusFilter, setStatusFilter] =
    useState<ExecutionStatusFilter>('all')
  const [automationFilter, setAutomationFilter] = useState('all')
  const [dateRangeFilter, setDateRangeFilter] =
    useState<DateRangeFilter>('all')
  const [sortOption, setSortOption] =
    useState<SortOption>('started-desc')
  const [selectedExecution, setSelectedExecution] =
    useState<AutomationExecution | null>(null)
  const [showClearConfirmation, setShowClearConfirmation] = useState(false)
  const [expandedErrorIds, setExpandedErrorIds] = useState<string[]>([])

  const filteredExecutions = useMemo(() => {
    const normalizedSearch = searchText.trim().toLowerCase()

    const filtered = executions.filter((execution) => {
      if (
        statusFilter !== 'all' &&
        execution.status !== statusFilter
      ) {
        return false
      }

      if (
        automationFilter !== 'all' &&
        execution.automationId !== automationFilter
      ) {
        return false
      }

      if (!isExecutionInDateRange(execution, dateRangeFilter)) {
        return false
      }

      if (!normalizedSearch) {
        return true
      }

      const searchTarget = [
        execution.automationName,
        execution.status,
        execution.outputFileName,
        execution.outputFilePath,
        execution.message,
        execution.errorDetails,
        execution.triggeredBy,
        execution.startedAt,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()

      return searchTarget.includes(normalizedSearch)
    })

    return [...filtered].sort((left, right) => {
      if (sortOption === 'started-asc') {
        return getExecutionTimestamp(left) - getExecutionTimestamp(right)
      }

      if (sortOption === 'duration-desc') {
        return (right.durationMs ?? -1) - (left.durationMs ?? -1)
      }

      if (sortOption === 'duration-asc') {
        return (
          (left.durationMs ?? Number.MAX_SAFE_INTEGER) -
          (right.durationMs ?? Number.MAX_SAFE_INTEGER)
        )
      }

      if (sortOption === 'rows-desc') {
        return (right.rowCount ?? -1) - (left.rowCount ?? -1)
      }

      if (sortOption === 'status') {
        return left.status.localeCompare(right.status)
      }

      return getExecutionTimestamp(right) - getExecutionTimestamp(left)
    })
  }, [
    automationFilter,
    dateRangeFilter,
    executions,
    searchText,
    sortOption,
    statusFilter,
  ])

  const statistics = useMemo(() => {
    const successful = executions.filter(
      (execution) => execution.status === 'success',
    ).length
    const failed = executions.filter(
      (execution) => execution.status === 'failed',
    ).length
    const running = executions.filter(
      (execution) => execution.status === 'running',
    ).length
    const completed = successful + failed
    const successRate = completed > 0 ? (successful / completed) * 100 : 0

    const durations = executions
      .map((execution) => execution.durationMs)
      .filter(
        (duration): duration is number =>
          typeof duration === 'number' && duration >= 0,
      )

    const averageDuration =
      durations.length > 0
        ? durations.reduce((total, duration) => total + duration, 0) /
          durations.length
        : null

    return {
      total: executions.length,
      successful,
      failed,
      running,
      successRate,
      averageDuration,
    }
  }, [executions])

  const toggleError = (executionId: string) => {
    setExpandedErrorIds((currentIds) =>
      currentIds.includes(executionId)
        ? currentIds.filter((id) => id !== executionId)
        : [...currentIds, executionId],
    )
  }

  const handleOpenDetails = (execution: AutomationExecution) => {
    setSelectedExecution(execution)
    onOpenExecution(execution)
  }

  const handleRetry = (execution: AutomationExecution) => {
    if (onRetryExecution) {
      onRetryExecution(execution)
      return
    }

    const automation = automations.find(
      (item) => item.id === execution.automationId,
    )

    if (automation && onRunAutomation) {
      onRunAutomation(automation)
    }
  }

  const canRetry = (execution: AutomationExecution) =>
    execution.status !== 'running' &&
    Boolean(onRetryExecution || onRunAutomation)

  const confirmClearHistory = () => {
    onClearHistory?.()
    setShowClearConfirmation(false)
  }

  const resetFilters = () => {
    setSearchText('')
    setStatusFilter('all')
    setAutomationFilter('all')
    setDateRangeFilter('all')
    setSortOption('started-desc')
  }

  return (
    <section className="execution-history">
      <div className="execution-history-header">
        <div>
          <span className="automation-eyebrow">Audit and monitoring</span>
          <h2>Execution History</h2>
          <p>
            Review automation runs, outputs, row counts, performance, and
            errors.
          </p>
        </div>

        <div className="execution-history-header-actions">
          {onBack && (
            <button
              type="button"
              className="automation-secondary-button"
              onClick={onBack}
            >
              Back
            </button>
          )}

          {onClearHistory && (
            <button
              type="button"
              className="automation-danger-button"
              onClick={() => setShowClearConfirmation(true)}
              disabled={executions.length === 0}
            >
              Clear History
            </button>
          )}
        </div>
      </div>

      <div className="execution-history-stat-grid">
        <article className="automation-stat-card">
          <span>Total Runs</span>
          <strong>{statistics.total.toLocaleString()}</strong>
        </article>

        <article className="automation-stat-card">
          <span>Successful</span>
          <strong>{statistics.successful.toLocaleString()}</strong>
        </article>

        <article className="automation-stat-card">
          <span>Failed</span>
          <strong>{statistics.failed.toLocaleString()}</strong>
        </article>

        <article className="automation-stat-card">
          <span>Running</span>
          <strong>{statistics.running.toLocaleString()}</strong>
        </article>

        <article className="automation-stat-card">
          <span>Success Rate</span>
          <strong>{statistics.successRate.toFixed(1)}%</strong>
        </article>

        <article className="automation-stat-card">
          <span>Average Duration</span>
          <strong>{formatDuration(statistics.averageDuration)}</strong>
        </article>
      </div>

      <div className="execution-history-toolbar">
        <div className="automation-search-field">
          <span aria-hidden="true">⌕</span>
          <input
            type="search"
            value={searchText}
            onChange={(event) => setSearchText(event.target.value)}
            placeholder="Search runs, files, or errors"
            aria-label="Search execution history"
          />
        </div>

        <select
          value={statusFilter}
          onChange={(event) =>
            setStatusFilter(event.target.value as ExecutionStatusFilter)
          }
          aria-label="Filter executions by status"
        >
          <option value="all">All statuses</option>
          <option value="running">Running</option>
          <option value="success">Success</option>
          <option value="warning">Warning</option>
          <option value="failed">Failed</option>
          <option value="cancelled">Cancelled</option>
        </select>

        <select
          value={automationFilter}
          onChange={(event) => setAutomationFilter(event.target.value)}
          aria-label="Filter by automation"
        >
          <option value="all">All automations</option>
          {automations
            .slice()
            .sort((left, right) => left.name.localeCompare(right.name))
            .map((automation) => (
              <option key={automation.id} value={automation.id}>
                {automation.name}
              </option>
            ))}
        </select>

        <select
          value={dateRangeFilter}
          onChange={(event) =>
            setDateRangeFilter(event.target.value as DateRangeFilter)
          }
          aria-label="Filter by date range"
        >
          <option value="all">All dates</option>
          <option value="today">Today</option>
          <option value="7-days">Last 7 days</option>
          <option value="30-days">Last 30 days</option>
        </select>

        <select
          value={sortOption}
          onChange={(event) =>
            setSortOption(event.target.value as SortOption)
          }
          aria-label="Sort execution history"
        >
          <option value="started-desc">Newest first</option>
          <option value="started-asc">Oldest first</option>
          <option value="duration-desc">Longest duration</option>
          <option value="duration-asc">Shortest duration</option>
          <option value="rows-desc">Highest row count</option>
          <option value="status">Status</option>
        </select>
      </div>

      <div className="execution-history-summary">
        <div>
          Showing <strong>{filteredExecutions.length.toLocaleString()}</strong>{' '}
          of <strong>{executions.length.toLocaleString()}</strong> executions
        </div>

        {filteredExecutions.length !== executions.length && (
          <button type="button" onClick={resetFilters}>
            Reset filters
          </button>
        )}
      </div>

      {executions.length === 0 ? (
        <div className="automation-empty-state">
          <strong>No execution history</strong>
          <span>
            Run an automation to begin tracking status, performance, and
            generated files.
          </span>
        </div>
      ) : filteredExecutions.length === 0 ? (
        <div className="automation-empty-state">
          <strong>No matching executions</strong>
          <span>Adjust the filters or search terms to find another run.</span>
        </div>
      ) : (
        <div className="execution-history-table-wrapper">
          <table className="automation-table execution-history-table">
            <thead>
              <tr>
                <th>Automation</th>
                <th>Status</th>
                <th>Started</th>
                <th>Completed</th>
                <th>Duration</th>
                <th>Rows</th>
                <th>Output</th>
                <th>Triggered By</th>
                <th>Actions</th>
              </tr>
            </thead>

            <tbody>
              {filteredExecutions.map((execution) => {
                const errorExpanded = expandedErrorIds.includes(execution.id)
                const outputPath = getExecutionOutputPath(execution)
                const errorDetails = getExecutionError(execution)

                return (
                  <Fragment key={execution.id}>
                    <tr
                      className={
                        execution.status === 'running'
                          ? 'automation-running-row'
                          : undefined
                      }
                    >
                      <td>
                        <div className="execution-automation-cell">
                          <strong>{execution.automationName}</strong>
                          <span>Run ID: {execution.id}</span>
                        </div>
                      </td>

                      <td>
                        <span
                          className={`automation-status ${execution.status}`}
                        >
                          {execution.status}
                        </span>
                      </td>

                      <td className="execution-date-cell">
                        {formatDateTime(execution.startedAt)}
                      </td>

                      <td className="execution-date-cell">
                        {formatDateTime(execution.completedAt)}
                      </td>

                      <td className="execution-duration">
                        {formatDuration(execution.durationMs)}
                      </td>

                      <td className="execution-row-count">
                        {formatRowCount(execution.rowCount)}
                      </td>

                      <td>
                        {outputPath ? (
                          <div className="execution-output-cell">
                            <strong title={outputPath}>
                              {execution.outputFileName ||
                                getFileNameFromPath(outputPath)}
                            </strong>
                            <span title={outputPath}>{outputPath}</span>
                          </div>
                        ) : (
                          '-'
                        )}
                      </td>

                      <td>
                        <span className="execution-trigger">
                          {execution.triggeredBy}
                        </span>
                      </td>

                      <td>
                        <div className="execution-row-actions">
                          <button
                            type="button"
                            onClick={() => handleOpenDetails(execution)}
                          >
                            Details
                          </button>

                          {canRetry(execution) && (
                            <button
                              type="button"
                              onClick={() => handleRetry(execution)}
                              disabled={isRunning}
                            >
                              Retry
                            </button>
                          )}

                          {errorDetails && (
                            <button
                              type="button"
                              className="danger"
                              onClick={() => toggleError(execution.id)}
                            >
                              {errorExpanded ? 'Hide Error' : 'View Error'}
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>

                    {errorDetails && errorExpanded && (
                      <tr className="execution-error-row">
                        <td colSpan={9}>
                          <div className="execution-error-panel">
                            <div>
                              <span>Error details</span>
                              <strong>Automation run failed</strong>
                            </div>
                            <pre>{errorDetails}</pre>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {selectedExecution && (
        <div
          className="automation-modal-backdrop"
          role="presentation"
          onMouseDown={() => setSelectedExecution(null)}
        >
          <div
            className="automation-modal automation-execution-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="execution-details-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="automation-modal-header">
              <div>
                <span className="automation-eyebrow">Execution details</span>
                <h2 id="execution-details-title">
                  {selectedExecution.automationName}
                </h2>
              </div>

              <button
                type="button"
                aria-label="Close execution details"
                onClick={() => setSelectedExecution(null)}
              >
                ×
              </button>
            </div>

            <div className="execution-detail-grid">
              <div className="execution-detail-item">
                <span>Status</span>
                <strong>
                  <span
                    className={`automation-status ${selectedExecution.status}`}
                  >
                    {selectedExecution.status}
                  </span>
                </strong>
              </div>

              <div className="execution-detail-item">
                <span>Started</span>
                <strong>{formatDateTime(selectedExecution.startedAt)}</strong>
              </div>

              <div className="execution-detail-item">
                <span>Completed</span>
                <strong>{formatDateTime(selectedExecution.completedAt)}</strong>
              </div>

              <div className="execution-detail-item">
                <span>Duration</span>
                <strong>{formatDuration(selectedExecution.durationMs)}</strong>
              </div>

              <div className="execution-detail-item">
                <span>Rows returned</span>
                <strong>{formatRowCount(selectedExecution.rowCount)}</strong>
              </div>

              <div className="execution-detail-item">
                <span>Triggered by</span>
                <strong>{selectedExecution.triggeredBy}</strong>
              </div>

              <div className="execution-detail-item full-width">
                <span>Run ID</span>
                <strong>{selectedExecution.id}</strong>
              </div>
            </div>

            {selectedExecution.message && (
              <div className="execution-detail-message">
                <strong>Execution message</strong>
                <p>{selectedExecution.message}</p>
              </div>
            )}

            {getExecutionOutputPath(selectedExecution) && (
              <div className="execution-detail-message">
                <strong>Generated output</strong>
                <p>{getExecutionOutputPath(selectedExecution)}</p>
              </div>
            )}

            {getExecutionError(selectedExecution) && (
              <div className="execution-detail-error">
                <strong>Error details</strong>
                <pre>{getExecutionError(selectedExecution)}</pre>
              </div>
            )}

            <div className="automation-modal-actions">
              {canRetry(selectedExecution) && (
                <button
                  type="button"
                  className="automation-secondary-button"
                  onClick={() => handleRetry(selectedExecution)}
                  disabled={isRunning}
                >
                  Retry Execution
                </button>
              )}

              <button
                type="button"
                className="automation-primary-button"
                onClick={() => setSelectedExecution(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {showClearConfirmation && (
        <div
          className="automation-modal-backdrop"
          role="presentation"
          onMouseDown={() => setShowClearConfirmation(false)}
        >
          <div
            className="automation-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="clear-history-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <span className="automation-eyebrow">Confirm action</span>
            <h2 id="clear-history-title">Clear execution history?</h2>
            <p>
              This will remove all locally stored execution records. It will not
              delete generated report files or automation definitions.
            </p>

            <div className="automation-modal-actions">
              <button
                type="button"
                className="automation-secondary-button"
                onClick={() => setShowClearConfirmation(false)}
              >
                Cancel
              </button>

              <button
                type="button"
                className="automation-danger-button"
                onClick={confirmClearHistory}
              >
                Clear History
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}

export default ExecutionHistory