import { useMemo, useState } from 'react'

import type {
  ReportColumn,
  ReportExecutionResult,
  ReportRow,
} from './ReportBuilder'

type ReportPreviewProps = {
  reportName: string
  result: ReportExecutionResult | null
  isRunning: boolean
  exportLimit: number | null
  onRefresh: () => void
}

type SortDirection = 'asc' | 'desc'

type SortState = {
  key: string
  direction: SortDirection
} | null

function formatExecutionTime(
  milliseconds: number,
) {
  if (milliseconds < 1000) {
    return `${milliseconds} ms`
  }

  return `${(milliseconds / 1000).toFixed(2)} sec`
}

function formatCellValue(
  value: ReportRow[string],
) {
  if (value === null || value === undefined) {
    return ''
  }

  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No'
  }

  return String(value)
}

function compareValues(
  left: ReportRow[string],
  right: ReportRow[string],
) {
  if (
    left === null ||
    left === undefined
  ) {
    return -1
  }

  if (
    right === null ||
    right === undefined
  ) {
    return 1
  }

  if (
    typeof left === 'number' &&
    typeof right === 'number'
  ) {
    return left - right
  }

  const leftText = String(left)
  const rightText = String(right)

  const leftNumber = Number(leftText)
  const rightNumber = Number(rightText)

  if (
    Number.isFinite(leftNumber) &&
    Number.isFinite(rightNumber) &&
    leftText.trim() !== '' &&
    rightText.trim() !== ''
  ) {
    return leftNumber - rightNumber
  }

  return leftText.localeCompare(
    rightText,
    undefined,
    {
      numeric: true,
      sensitivity: 'base',
    },
  )
}

function ReportPreview({
  reportName,
  result,
  isRunning,
  exportLimit,
  onRefresh,
}: ReportPreviewProps) {
  const [searchText, setSearchText] =
    useState('')

  const [sortState, setSortState] =
    useState<SortState>(null)

  const [copiedCell, setCopiedCell] =
    useState<string | null>(null)

  const visibleRows = useMemo(() => {
    if (!result) {
      return []
    }

    const normalizedSearch = searchText
      .trim()
      .toLowerCase()

    let nextRows = [...result.rows]

    if (normalizedSearch) {
      nextRows = nextRows.filter((row) =>
        result.columns.some((column) => {
          const value = formatCellValue(
            row[column.key],
          )

          return value
            .toLowerCase()
            .includes(normalizedSearch)
        }),
      )
    }

    if (sortState) {
      nextRows.sort((left, right) => {
        const comparison = compareValues(
          left[sortState.key],
          right[sortState.key],
        )

        return sortState.direction === 'asc'
          ? comparison
          : comparison * -1
      })
    }

    return nextRows
  }, [
    result,
    searchText,
    sortState,
  ])

  const handleSort = (
    column: ReportColumn,
  ) => {
    setSortState((currentSort) => {
      if (currentSort?.key !== column.key) {
        return {
          key: column.key,
          direction: 'asc',
        }
      }

      if (
        currentSort.direction === 'asc'
      ) {
        return {
          key: column.key,
          direction: 'desc',
        }
      }

      return null
    })
  }

  const getSortIndicator = (
    columnKey: string,
  ) => {
    if (
      sortState?.key !== columnKey
    ) {
      return '↕'
    }

    return sortState.direction === 'asc'
      ? '↑'
      : '↓'
  }

  const handleCopyCell = async (
    rowIndex: number,
    columnKey: string,
    value: ReportRow[string],
  ) => {
    const text = formatCellValue(value)
    const cellKey = `${rowIndex}-${columnKey}`

    try {
      await navigator.clipboard.writeText(
        text,
      )

      setCopiedCell(cellKey)

      window.setTimeout(() => {
        setCopiedCell((currentValue) =>
          currentValue === cellKey
            ? null
            : currentValue,
        )
      }, 1400)
    } catch {
      setCopiedCell(null)
    }
  }

  if (!result) {
    return (
      <section className="report-preview-card">
        <div className="report-empty-state">
          Run a report preview to display results.
        </div>
      </section>
    )
  }

  return (
    <section className="report-preview-card">
      <div className="report-preview-header">
        <div>
          <span className="report-builder-eyebrow">
            Preview results
          </span>

          <h2>
            {reportName || 'Untitled Report'}
          </h2>

          <p>
            Review the controlled preview before downloading or scheduling
            an export.
          </p>
        </div>

        <button
          type="button"
          className="report-secondary-button"
          onClick={onRefresh}
          disabled={isRunning}
        >
          {isRunning
            ? 'Refreshing…'
            : 'Refresh Preview'}
        </button>
      </div>

      <div className="report-preview-stats">
        <div>
          <span>Returned rows</span>
          <strong>
            {result.rows.length.toLocaleString()}
          </strong>
        </div>

        <div>
          <span>Preview limit</span>
          <strong>
            {result.rowLimit.toLocaleString()}
          </strong>
        </div>

        <div>
          <span>Columns</span>
          <strong>
            {result.columns.length}
          </strong>
        </div>

        <div>
          <span>Execution time</span>
          <strong>
            {formatExecutionTime(
              result.executionTimeMs,
            )}
          </strong>
        </div>
      </div>

      {result.truncated && (
        <div className="report-preview-warning">
          <strong>
            Preview limit reached
          </strong>

          <span>
            The server applied the preview limit. Direct CSV export can return
            up to {exportLimit?.toLocaleString() ?? 'the configured server'}
            {' '}rows; larger extracts require a backend capability change.
          </span>
        </div>
      )}

      <div className="report-preview-toolbar">
        <div className="report-preview-search">
          <span aria-hidden="true">
            ⌕
          </span>

          <input
            type="search"
            value={searchText}
            onChange={(event) =>
              setSearchText(
                event.target.value,
              )
            }
            placeholder="Search preview rows"
            aria-label="Search report preview"
          />
        </div>

        <div className="report-preview-result-count">
          <strong>
            {visibleRows.length.toLocaleString()}
          </strong>

          <span>
            visible row
            {visibleRows.length === 1
              ? ''
              : 's'}
          </span>
        </div>
      </div>

      {result.rows.length === 0 ? (
        <div className="report-empty-state">
          The report completed successfully but
          returned no rows.
        </div>
      ) : result.columns.length === 0 ? (
        <div className="report-empty-state">
          The report returned rows without column metadata.
        </div>
      ) : visibleRows.length === 0 ? (
        <div className="report-empty-state">
          No preview rows match the current
          search.
        </div>
      ) : (
        <div className="report-preview-table-wrapper">
          <table className="report-preview-table">
            <thead>
              <tr>
                <th className="report-preview-row-number">
                  #
                </th>

                {result.columns.map(
                  (column) => (
                    <th key={column.key}>
                      <button
                        type="button"
                        onClick={() =>
                          handleSort(column)
                        }
                      >
                        <span>
                          {column.label}
                        </span>

                        <span
                          className={
                            sortState?.key ===
                            column.key
                              ? 'active'
                              : undefined
                          }
                        >
                          {getSortIndicator(
                            column.key,
                          )}
                        </span>
                      </button>
                    </th>
                  ),
                )}
              </tr>
            </thead>

            <tbody>
              {visibleRows.map(
                (row, rowIndex) => (
                  <tr key={rowIndex}>
                    <td className="report-preview-row-number">
                      {rowIndex + 1}
                    </td>

                    {result.columns.map(
                      (column) => {
                        const value =
                          row[column.key]

                        const cellKey =
                          `${rowIndex}-${column.key}`

                        return (
                          <td
                            key={column.key}
                            title="Click to copy"
                            onClick={() =>
                              handleCopyCell(
                                rowIndex,
                                column.key,
                                value,
                              )
                            }
                          >
                            <span>
                              {formatCellValue(
                                value,
                              ) || (
                                <em>
                                  null
                                </em>
                              )}
                            </span>

                            {copiedCell ===
                              cellKey && (
                              <small>
                                Copied
                              </small>
                            )}
                          </td>
                        )
                      },
                    )}
                  </tr>
                ),
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

export default ReportPreview
