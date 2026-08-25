import { useMemo, useState } from 'react'

import type { SavedReport } from './ReportBuilder'

type ReportCatalogProps = {
  reports: SavedReport[]
  isBusy: boolean
  onCreate: () => void
  onOpen: (report: SavedReport) => void
  onDuplicate: (report: SavedReport) => void
  onDelete: (reportId: string) => Promise<boolean>
}

type SortMode =
  | 'updated-desc'
  | 'updated-asc'
  | 'name-asc'
  | 'name-desc'

function formatDateTime(value: string) {
  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return value
  }

  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date)
}

function ReportCatalog({
  reports,
  isBusy,
  onCreate,
  onOpen,
  onDuplicate,
  onDelete,
}: ReportCatalogProps) {
  const [searchText, setSearchText] = useState('')
  const [categoryFilter, setCategoryFilter] =
    useState('All')
  const [sortMode, setSortMode] =
    useState<SortMode>('updated-desc')
  const [pendingDelete, setPendingDelete] =
    useState<SavedReport | null>(null)
  const [isDeleting, setIsDeleting] = useState(false)

  const categories = useMemo(() => {
    const uniqueCategories = new Set(
      reports
        .map((report) => report.category.trim())
        .filter(Boolean),
    )

    return ['All', ...Array.from(uniqueCategories).sort()]
  }, [reports])

  const filteredReports = useMemo(() => {
    const normalizedSearch = searchText
      .trim()
      .toLowerCase()

    const filtered = reports.filter((report) => {
      const matchesCategory =
        categoryFilter === 'All' ||
        report.category === categoryFilter

      if (!matchesCategory) {
        return false
      }

      if (!normalizedSearch) {
        return true
      }

      const searchableText = [
        report.name,
        report.description,
        report.category,
        report.sql,
      ]
        .join(' ')
        .toLowerCase()

      return searchableText.includes(normalizedSearch)
    })

    return [...filtered].sort((left, right) => {
      switch (sortMode) {
        case 'updated-asc':
          return (
            new Date(left.updatedAt).getTime() -
            new Date(right.updatedAt).getTime()
          )

        case 'name-asc':
          return left.name.localeCompare(right.name)

        case 'name-desc':
          return right.name.localeCompare(left.name)

        case 'updated-desc':
        default:
          return (
            new Date(right.updatedAt).getTime() -
            new Date(left.updatedAt).getTime()
          )
      }
    })
  }, [
    reports,
    searchText,
    categoryFilter,
    sortMode,
  ])

  const handleConfirmDelete = async () => {
    if (!pendingDelete) {
      return
    }

    setIsDeleting(true)

    const deleted = await onDelete(pendingDelete.id)

    if (deleted) {
      setPendingDelete(null)
    }

    setIsDeleting(false)
  }

  return (
    <section className="report-catalog">
      <div className="report-catalog-toolbar">
        <div className="report-catalog-search">
          <span aria-hidden="true">⌕</span>

          <input
            type="search"
            value={searchText}
            onChange={(event) =>
              setSearchText(event.target.value)
            }
            placeholder="Search reports, descriptions, SQL, or categories"
            aria-label="Search saved reports"
          />
        </div>

        <div className="report-catalog-filters">
          <label>
            <span>Category</span>

            <select
              value={categoryFilter}
              onChange={(event) =>
                setCategoryFilter(event.target.value)
              }
            >
              {categories.map((category) => (
                <option
                  key={category}
                  value={category}
                >
                  {category}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span>Sort</span>

            <select
              value={sortMode}
              onChange={(event) =>
                setSortMode(
                  event.target.value as SortMode,
                )
              }
            >
              <option value="updated-desc">
                Recently updated
              </option>

              <option value="updated-asc">
                Oldest updated
              </option>

              <option value="name-asc">
                Name A–Z
              </option>

              <option value="name-desc">
                Name Z–A
              </option>
            </select>
          </label>
        </div>
      </div>

      <div className="report-catalog-summary">
        <div>
          <strong>{filteredReports.length}</strong>
          <span>
            report
            {filteredReports.length === 1 ? '' : 's'} shown
          </span>
        </div>

        <button
          type="button"
          className="report-primary-button"
          onClick={onCreate}
          disabled={isBusy}
        >
          Create Report
        </button>
      </div>

      {reports.length === 0 ? (
        <div className="report-catalog-empty">
          <div className="report-catalog-empty-icon">
            ▦
          </div>

          <strong>No saved reports yet</strong>

          <p>
            Create your first report, define its SQL and
            parameters, then save it to the local catalog.
          </p>

          <button
            type="button"
            className="report-primary-button"
            onClick={onCreate}
            disabled={isBusy}
          >
            Create First Report
          </button>
        </div>
      ) : filteredReports.length === 0 ? (
        <div className="report-catalog-empty">
          <div className="report-catalog-empty-icon">
            ∅
          </div>

          <strong>No reports match your filters</strong>

          <p>
            Adjust the search text or category selection to
            display additional reports.
          </p>

          <button
            type="button"
            className="report-secondary-button"
            onClick={() => {
              setSearchText('')
              setCategoryFilter('All')
            }}
          >
            Clear Filters
          </button>
        </div>
      ) : (
        <div className="report-catalog-grid">
          {filteredReports.map((report) => (
            <article
              key={report.id}
              className="report-catalog-card"
            >
              <button
                type="button"
                className="report-catalog-card-main"
                onClick={() => onOpen(report)}
                disabled={isBusy}
              >
                <div className="report-catalog-card-heading">
                  <div className="report-catalog-card-icon">
                    R
                  </div>

                  <div>
                    <strong>{report.name}</strong>

                    <span>{report.category}</span>
                  </div>
                </div>

                <p>
                  {report.description.trim() ||
                    'No description has been added to this report.'}
                </p>

                <div className="report-catalog-card-meta">
                  <span>
                    Updated{' '}
                    <strong>
                      {formatDateTime(report.updatedAt)}
                    </strong>
                  </span>

                  <span>
                    Parameters{' '}
                    <strong>
                      {report.parameters.length}
                    </strong>
                  </span>
                </div>

                <div className="report-catalog-sql-preview">
                  <code>
                    {report.sql.trim() ||
                      'No SQL has been entered.'}
                  </code>
                </div>
              </button>

              <div className="report-catalog-card-actions">
                <button
                  type="button"
                  onClick={() => onOpen(report)}
                  disabled={isBusy}
                >
                  Open
                </button>

                <button
                  type="button"
                  onClick={() => onDuplicate(report)}
                  disabled={isBusy}
                >
                  Duplicate
                </button>

                <button
                  type="button"
                  className="danger"
                  onClick={() =>
                    setPendingDelete(report)
                  }
                  disabled={isBusy}
                >
                  Delete
                </button>
              </div>
            </article>
          ))}
        </div>
      )}

      {pendingDelete && (
        <div
          className="report-modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              if (!isDeleting) {
                setPendingDelete(null)
              }
            }
          }}
        >
          <div
            className="report-confirm-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-report-heading"
          >
            <div className="report-confirm-modal-icon">
              !
            </div>

            <h2 id="delete-report-heading">
              Delete report?
            </h2>

            <p>
              <strong>{pendingDelete.name}</strong> will be
              permanently removed from the local report
              catalog.
            </p>

            <div className="report-confirm-modal-actions">
              <button
                type="button"
                className="report-secondary-button"
                onClick={() =>
                  setPendingDelete(null)
                }
                disabled={isDeleting}
              >
                Cancel
              </button>

              <button
                type="button"
                className="report-danger-button"
                onClick={() => void handleConfirmDelete()}
                disabled={isDeleting}
              >
                {isDeleting ? 'Deleting…' : 'Delete Report'}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}

export default ReportCatalog
