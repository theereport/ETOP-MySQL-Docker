import {
  useMemo,
  useState,
} from 'react'

import type {
  AutomationDefinition,
  AutomationStatus,
} from './AutomationCenter'

type AutomationCatalogProps = {
  automations: AutomationDefinition[]
  isRunning: boolean

  onCreate: () => void

  onOpen: (
    automation: AutomationDefinition,
  ) => void

  onEdit: (
    automation: AutomationDefinition,
  ) => void

  onDuplicate: (
    automation: AutomationDefinition,
  ) => void

  onDelete: (
    automationId: string,
  ) => void

  onToggleStatus: (
    automationId: string,
  ) => void

  onRunNow: (
    automation: AutomationDefinition,
  ) => void
}

type StatusFilter =
  | 'all'
  | AutomationStatus

type SortOption =
  | 'updated-desc'
  | 'name-asc'
  | 'status'
  | 'next-run'

function formatDateTime(
  value: string | null,
) {
  if (!value) {
    return 'Not scheduled'
  }

  const parsedDate = new Date(value)

  if (
    Number.isNaN(
      parsedDate.getTime(),
    )
  ) {
    return value
  }

  return parsedDate.toLocaleString()
}

function formatSource(
  automation: AutomationDefinition,
) {
  switch (automation.sourceType) {
    case 'report':
      return automation.reportName ||
        'Saved Report'

    case 'sql':
      return 'Direct SQL'

    case 'powershell':
      return 'PowerShell Script'

    case 'python':
      return 'Python Script'

    default:
      return automation.sourceType
  }
}

function formatSchedule(
  automation: AutomationDefinition,
) {
  const {
    frequency,
    time,
    daysOfWeek,
    dayOfMonth,
  } = automation.schedule

  if (frequency === 'manual') {
    return 'Manual only'
  }

  if (frequency === 'daily') {
    return `Daily at ${time}`
  }

  if (frequency === 'weekly') {
    const dayNames = [
      'Sun',
      'Mon',
      'Tue',
      'Wed',
      'Thu',
      'Fri',
      'Sat',
    ]

    const selectedDays =
      daysOfWeek
        .map(
          (day) =>
            dayNames[day],
        )
        .filter(Boolean)
        .join(', ')

    return `${selectedDays || 'Weekly'} at ${time}`
  }

  if (frequency === 'monthly') {
    return `Monthly on day ${
      dayOfMonth ?? 1
    } at ${time}`
  }

  return (
    automation.schedule
      .cronExpression ||
    'Custom schedule'
  )
}

function AutomationCatalog({
  automations,
  isRunning,
  onCreate,
  onOpen,
  onEdit,
  onDuplicate,
  onDelete,
  onToggleStatus,
  onRunNow,
}: AutomationCatalogProps) {
  const [
    searchText,
    setSearchText,
  ] = useState('')

  const [
    statusFilter,
    setStatusFilter,
  ] = useState<StatusFilter>('all')

  const [
    categoryFilter,
    setCategoryFilter,
  ] = useState('all')

  const [
    sortOption,
    setSortOption,
  ] = useState<SortOption>(
    'updated-desc',
  )

  const [
    automationToDelete,
    setAutomationToDelete,
  ] =
    useState<AutomationDefinition | null>(
      null,
    )

  const categories = useMemo(() => {
    return Array.from(
      new Set(
        automations
          .map(
            (automation) =>
              automation.category.trim(),
          )
          .filter(Boolean),
      ),
    ).sort((left, right) =>
      left.localeCompare(right),
    )
  }, [automations])

  const visibleAutomations =
    useMemo(() => {
      const normalizedSearch =
        searchText
          .trim()
          .toLowerCase()

      const filtered =
        automations.filter(
          (automation) => {
            if (
              statusFilter !==
                'all' &&
              automation.status !==
                statusFilter
            ) {
              return false
            }

            if (
              categoryFilter !==
                'all' &&
              automation.category !==
                categoryFilter
            ) {
              return false
            }

            if (
              !normalizedSearch
            ) {
              return true
            }

            const searchTarget = [
              automation.name,
              automation.description,
              automation.category,
              automation.reportName,
              automation.sourceType,
              automation.status,
            ]
              .join(' ')
              .toLowerCase()

            return searchTarget.includes(
              normalizedSearch,
            )
          },
        )

      return filtered.sort(
        (left, right) => {
          if (
            sortOption ===
            'name-asc'
          ) {
            return left.name.localeCompare(
              right.name,
            )
          }

          if (
            sortOption ===
            'status'
          ) {
            return left.status.localeCompare(
              right.status,
            )
          }

          if (
            sortOption ===
            'next-run'
          ) {
            if (
              !left.nextRunAt &&
              !right.nextRunAt
            ) {
              return 0
            }

            if (
              !left.nextRunAt
            ) {
              return 1
            }

            if (
              !right.nextRunAt
            ) {
              return -1
            }

            return (
              new Date(
                left.nextRunAt,
              ).getTime() -
              new Date(
                right.nextRunAt,
              ).getTime()
            )
          }

          return (
            new Date(
              right.updatedAt,
            ).getTime() -
            new Date(
              left.updatedAt,
            ).getTime()
          )
        },
      )
    }, [
      automations,
      categoryFilter,
      searchText,
      sortOption,
      statusFilter,
    ])

  const confirmDelete = () => {
    if (!automationToDelete) {
      return
    }

    onDelete(
      automationToDelete.id,
    )

    setAutomationToDelete(null)
  }

  return (
    <section className="automation-catalog">
      <div className="automation-catalog-header">
        <div>
          <span className="automation-eyebrow">
            Automation library
          </span>

          <h2>All Automations</h2>

          <p>
            Manage scheduled reports,
            SQL jobs, scripts, and delivery
            workflows.
          </p>
        </div>

        <button
          type="button"
          className="automation-primary-button"
          onClick={onCreate}
        >
          New Automation
        </button>
      </div>

      <div className="automation-catalog-toolbar">
        <div className="automation-search-field">
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
            placeholder="Search automations"
            aria-label="Search automations"
          />
        </div>

        <select
          value={statusFilter}
          onChange={(event) =>
            setStatusFilter(
              event.target
                .value as StatusFilter,
            )
          }
          aria-label="Filter by status"
        >
          <option value="all">
            All statuses
          </option>

          <option value="active">
            Active
          </option>

          <option value="paused">
            Paused
          </option>

          <option value="draft">
            Draft
          </option>

          <option value="error">
            Error
          </option>
        </select>

        <select
          value={categoryFilter}
          onChange={(event) =>
            setCategoryFilter(
              event.target.value,
            )
          }
          aria-label="Filter by category"
        >
          <option value="all">
            All categories
          </option>

          {categories.map(
            (category) => (
              <option
                key={category}
                value={category}
              >
                {category}
              </option>
            ),
          )}
        </select>

        <select
          value={sortOption}
          onChange={(event) =>
            setSortOption(
              event.target
                .value as SortOption,
            )
          }
          aria-label="Sort automations"
        >
          <option value="updated-desc">
            Recently updated
          </option>

          <option value="name-asc">
            Name
          </option>

          <option value="status">
            Status
          </option>

          <option value="next-run">
            Next run
          </option>
        </select>
      </div>

      <div className="automation-catalog-summary">
        <strong>
          {visibleAutomations.length}
        </strong>

        <span>
          automation
          {visibleAutomations.length ===
          1
            ? ''
            : 's'}
        </span>
      </div>

      {automations.length === 0 ? (
        <div className="automation-empty-state">
          <strong>
            No automations created
          </strong>

          <span>
            Create your first automation
            to schedule a report, query,
            or script.
          </span>

          <button
            type="button"
            className="automation-primary-button"
            onClick={onCreate}
          >
            Create Automation
          </button>
        </div>
      ) : visibleAutomations.length ===
        0 ? (
        <div className="automation-empty-state">
          <strong>
            No matching automations
          </strong>

          <span>
            Adjust your search or filter
            selections.
          </span>
        </div>
      ) : (
        <div className="automation-card-grid">
          {visibleAutomations.map(
            (automation) => (
              <article
                key={automation.id}
                className="automation-catalog-card"
              >
                <div className="automation-card-header">
                  <div>
                    <span
                      className={`automation-status ${automation.status}`}
                    >
                      {automation.status}
                    </span>

                    <h3>
                      {automation.name}
                    </h3>
                  </div>

                  <span className="automation-card-category">
                    {automation.category ||
                      'General'}
                  </span>
                </div>

                <p className="automation-card-description">
                  {automation.description ||
                    'No description provided.'}
                </p>

                <div className="automation-card-details">
                  <div>
                    <span>Source</span>

                    <strong>
                      {formatSource(
                        automation,
                      )}
                    </strong>
                  </div>

                  <div>
                    <span>Schedule</span>

                    <strong>
                      {formatSchedule(
                        automation,
                      )}
                    </strong>
                  </div>

                  <div>
                    <span>Output</span>

                    <strong>
                      {automation.outputFormat.toUpperCase()}
                    </strong>
                  </div>

                  <div>
                    <span>Delivery</span>

                    <strong>
                      {automation.delivery.method}
                    </strong>
                  </div>
                </div>

                <div className="automation-card-run-details">
                  <div>
                    <span>Last run</span>

                    <strong>
                      {formatDateTime(
                        automation.lastRunAt,
                      )}
                    </strong>
                  </div>

                  <div>
                    <span>Next run</span>

                    <strong>
                      {formatDateTime(
                        automation.nextRunAt,
                      )}
                    </strong>
                  </div>
                </div>

                <div className="automation-card-actions">
                  <button
                    type="button"
                    className="automation-primary-button"
                    onClick={() =>
                      onRunNow(
                        automation,
                      )
                    }
                    disabled={isRunning}
                  >
                    {isRunning
                      ? 'Running…'
                      : 'Run Now'}
                  </button>

                  <button
                    type="button"
                    className="automation-secondary-button"
                    onClick={() =>
                      onOpen(
                        automation,
                      )
                    }
                  >
                    Open
                  </button>

                  <button
                    type="button"
                    className="automation-secondary-button"
                    onClick={() =>
                      onEdit(
                        automation,
                      )
                    }
                  >
                    Edit
                  </button>
                </div>

                <div className="automation-card-footer">
                  <button
                    type="button"
                    onClick={() =>
                      onToggleStatus(
                        automation.id,
                      )
                    }
                  >
                    {automation.status ===
                    'active'
                      ? 'Pause'
                      : 'Activate'}
                  </button>

                  <button
                    type="button"
                    onClick={() =>
                      onDuplicate(
                        automation,
                      )
                    }
                  >
                    Duplicate
                  </button>

                  <button
                    type="button"
                    className="danger"
                    onClick={() =>
                      setAutomationToDelete(
                        automation,
                      )
                    }
                  >
                    Delete
                  </button>
                </div>
              </article>
            ),
          )}
        </div>
      )}

      {automationToDelete && (
        <div
          className="automation-modal-backdrop"
          role="presentation"
          onMouseDown={() =>
            setAutomationToDelete(
              null,
            )
          }
        >
          <div
            className="automation-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-automation-title"
            onMouseDown={(event) =>
              event.stopPropagation()
            }
          >
            <span className="automation-eyebrow">
              Confirm deletion
            </span>

            <h2 id="delete-automation-title">
              Delete automation?
            </h2>

            <p>
              This will remove{' '}
              <strong>
                {
                  automationToDelete.name
                }
              </strong>{' '}
              from the Automation Center.
              Existing execution history will
              remain available.
            </p>

            <div className="automation-modal-actions">
              <button
                type="button"
                className="automation-secondary-button"
                onClick={() =>
                  setAutomationToDelete(
                    null,
                  )
                }
              >
                Cancel
              </button>

              <button
                type="button"
                className="automation-danger-button"
                onClick={confirmDelete}
              >
                Delete Automation
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}

export default AutomationCatalog