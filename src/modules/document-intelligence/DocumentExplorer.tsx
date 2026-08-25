import {
  useMemo,
  useState,
} from 'react'

import type {
  DocumentJob,
  DocumentType,
} from './types'

type SortKey =
  | 'created_desc'
  | 'created_asc'
  | 'name_asc'
  | 'name_desc'
  | 'confidence_desc'
  | 'confidence_asc'

type DocumentExplorerProps = {
  jobs: DocumentJob[]
  onOpen: (
    job: DocumentJob,
  ) => void
  onProcess: (
    job: DocumentJob,
  ) => void
  isBusy?: boolean
}

type StoredMetadata = {
  favorites: string[]
  tags: Record<string, string[]>
}

const STORAGE_KEY =
  'etop.document-explorer.metadata'

const PAGE_SIZE_OPTIONS = [
  10,
  25,
  50,
  100,
]

function loadMetadata(): StoredMetadata {
  try {
    const value =
      window.localStorage.getItem(
        STORAGE_KEY,
      )

    if (!value) {
      return {
        favorites: [],
        tags: {},
      }
    }

    const parsed =
      JSON.parse(value) as
        Partial<StoredMetadata>

    return {
      favorites:
        Array.isArray(
          parsed.favorites,
        )
          ? parsed.favorites
          : [],
      tags:
        parsed.tags &&
        typeof parsed.tags ===
          'object'
          ? parsed.tags
          : {},
    }
  } catch {
    return {
      favorites: [],
      tags: {},
    }
  }
}

function saveMetadata(
  value: StoredMetadata,
): void {
  window.localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify(value),
  )
}

function formatType(
  value: string,
): string {
  return value
    .split('_')
    .map(
      (part) =>
        part.charAt(0).toUpperCase() +
        part.slice(1),
    )
    .join(' ')
}

function formatBytes(
  value: number,
): string {
  if (value < 1024) {
    return `${value} B`
  }

  if (value < 1024 * 1024) {
    return `${(
      value / 1024
    ).toFixed(1)} KB`
  }

  return `${(
    value /
    (1024 * 1024)
  ).toFixed(1)} MB`
}

function confidencePercent(
  value: number,
): string {
  return `${Math.round(
    value * 100,
  )}%`
}

function uniqueTypes(
  jobs: DocumentJob[],
): DocumentType[] {
  return Array.from(
    new Set(
      jobs.map(
        (job) =>
          job.document_type,
      ),
    ),
  )
}

function DocumentExplorer({
  jobs,
  onOpen,
  onProcess,
  isBusy = false,
}: DocumentExplorerProps) {
  const [
    search,
    setSearch,
  ] = useState('')

  const [
    selectedType,
    setSelectedType,
  ] = useState<
    DocumentType | 'all'
  >('all')

  const [
    selectedStatus,
    setSelectedStatus,
  ] = useState<
    DocumentJob['status'] | 'all'
  >('all')

  const [
    confidenceFilter,
    setConfidenceFilter,
  ] = useState<
    | 'all'
    | 'high'
    | 'review'
    | 'low'
  >('all')

  const [
    favoriteOnly,
    setFavoriteOnly,
  ] = useState(false)

  const [
    selectedTag,
    setSelectedTag,
  ] = useState('all')

  const [
    sortKey,
    setSortKey,
  ] = useState<SortKey>(
    'created_desc',
  )

  const [
    pageSize,
    setPageSize,
  ] = useState(25)

  const [
    page,
    setPage,
  ] = useState(1)

  const [
    selectedIds,
    setSelectedIds,
  ] = useState<string[]>([])

  const [
    metadata,
    setMetadata,
  ] = useState<StoredMetadata>(
    () => loadMetadata(),
  )

  const [
    tagDraft,
    setTagDraft,
  ] = useState('')

  const types = useMemo(
    () => uniqueTypes(jobs),
    [jobs],
  )

  const allTags = useMemo(
    () =>
      Array.from(
        new Set(
          Object.values(
            metadata.tags,
          ).flat(),
        ),
      ).sort(),
    [metadata.tags],
  )

  const filteredJobs =
    useMemo(() => {
      const normalizedSearch =
        search.trim().toLowerCase()

      const next = jobs.filter(
        (job) => {
          if (
            normalizedSearch &&
            ![
              job.original_file_name,
              job.document_type,
              job.status,
              job.message,
            ]
              .join(' ')
              .toLowerCase()
              .includes(
                normalizedSearch,
              )
          ) {
            return false
          }

          if (
            selectedType !==
              'all' &&
            job.document_type !==
              selectedType
          ) {
            return false
          }

          if (
            selectedStatus !==
              'all' &&
            job.status !==
              selectedStatus
          ) {
            return false
          }

          if (
            confidenceFilter ===
              'high' &&
            job.confidence < 0.9
          ) {
            return false
          }

          if (
            confidenceFilter ===
              'review' &&
            !(
              job.confidence < 0.9 ||
              job.document_type ===
                'unknown'
            )
          ) {
            return false
          }

          if (
            confidenceFilter ===
              'low' &&
            job.confidence >= 0.6
          ) {
            return false
          }

          if (
            favoriteOnly &&
            !metadata.favorites.includes(
              job.job_id,
            )
          ) {
            return false
          }

          if (
            selectedTag !==
              'all' &&
            !(
              metadata.tags[
                job.job_id
              ] ?? []
            ).includes(
              selectedTag,
            )
          ) {
            return false
          }

          return true
        },
      )

      next.sort(
        (left, right) => {
          switch (sortKey) {
            case 'created_asc':
              return (
                new Date(
                  left.created_at,
                ).getTime() -
                new Date(
                  right.created_at,
                ).getTime()
              )

            case 'name_asc':
              return left.original_file_name.localeCompare(
                right.original_file_name,
              )

            case 'name_desc':
              return right.original_file_name.localeCompare(
                left.original_file_name,
              )

            case 'confidence_desc':
              return (
                right.confidence -
                left.confidence
              )

            case 'confidence_asc':
              return (
                left.confidence -
                right.confidence
              )

            case 'created_desc':
            default:
              return (
                new Date(
                  right.created_at,
                ).getTime() -
                new Date(
                  left.created_at,
                ).getTime()
              )
          }
        },
      )

      return next
    }, [
      jobs,
      search,
      selectedType,
      selectedStatus,
      confidenceFilter,
      favoriteOnly,
      selectedTag,
      sortKey,
      metadata.favorites,
      metadata.tags,
    ])

  const totalPages =
    Math.max(
      1,
      Math.ceil(
        filteredJobs.length /
          pageSize,
      ),
    )

  const effectivePage =
    Math.min(
      page,
      totalPages,
    )

  const visibleJobs =
    filteredJobs.slice(
      (effectivePage - 1) *
        pageSize,
      effectivePage * pageSize,
    )

  const updateMetadata = (
    next: StoredMetadata,
  ) => {
    setMetadata(next)
    saveMetadata(next)
  }

  const toggleFavorite = (
    jobId: string,
  ) => {
    const exists =
      metadata.favorites.includes(
        jobId,
      )

    updateMetadata({
      ...metadata,
      favorites: exists
        ? metadata.favorites.filter(
            (id) => id !== jobId,
          )
        : [
            ...metadata.favorites,
            jobId,
          ],
    })
  }

  const toggleSelected = (
    jobId: string,
  ) => {
    setSelectedIds(
      (current) =>
        current.includes(jobId)
          ? current.filter(
              (id) => id !== jobId,
            )
          : [
              ...current,
              jobId,
            ],
    )
  }

  const togglePageSelection =
    () => {
      const pageIds =
        visibleJobs.map(
          (job) => job.job_id,
        )

      const allSelected =
        pageIds.every(
          (id) =>
            selectedIds.includes(id),
        )

      setSelectedIds(
        (current) =>
          allSelected
            ? current.filter(
                (id) =>
                  !pageIds.includes(id),
              )
            : Array.from(
                new Set([
                  ...current,
                  ...pageIds,
                ]),
              ),
      )
    }

  const addTagToSelection = () => {
    const tag =
      tagDraft.trim()

    if (
      !tag ||
      selectedIds.length === 0
    ) {
      return
    }

    const nextTags = {
      ...metadata.tags,
    }

    selectedIds.forEach(
      (jobId) => {
        nextTags[jobId] =
          Array.from(
            new Set([
              ...(nextTags[
                jobId
              ] ?? []),
              tag,
            ]),
          )
      },
    )

    updateMetadata({
      ...metadata,
      tags: nextTags,
    })

    setTagDraft('')
  }

  const removeTag = (
    jobId: string,
    tag: string,
  ) => {
    updateMetadata({
      ...metadata,
      tags: {
        ...metadata.tags,
        [jobId]: (
          metadata.tags[
            jobId
          ] ?? []
        ).filter(
          (value) =>
            value !== tag,
        ),
      },
    })
  }

  const clearFilters = () => {
    setSearch('')
    setSelectedType('all')
    setSelectedStatus('all')
    setConfidenceFilter('all')
    setFavoriteOnly(false)
    setSelectedTag('all')
    setPage(1)
  }

  return (
    <section className="document-explorer">
      <div className="de-toolbar">
        <div className="de-search">
          <span>⌕</span>
          <input
            value={search}
            onChange={(event) => {
              setSearch(
                event.target.value,
              )
              setPage(1)
            }}
            placeholder="Search documents, types, statuses, or messages"
          />
        </div>

        <select
          value={selectedType}
          onChange={(event) => {
            setSelectedType(
              event.target.value as
                | DocumentType
                | 'all',
            )
            setPage(1)
          }}
        >
          <option value="all">
            All document types
          </option>

          {types.map(
            (type) => (
              <option
                value={type}
                key={type}
              >
                {formatType(type)}
              </option>
            ),
          )}
        </select>

        <select
          value={selectedStatus}
          onChange={(event) => {
            setSelectedStatus(
              event.target.value as
                | DocumentJob['status']
                | 'all',
            )
            setPage(1)
          }}
        >
          <option value="all">
            All statuses
          </option>
          <option value="uploaded">
            Uploaded
          </option>
          <option value="processing">
            Processing
          </option>
          <option value="completed">
            Completed
          </option>
          <option value="failed">
            Failed
          </option>
        </select>

        <select
          value={confidenceFilter}
          onChange={(event) => {
            setConfidenceFilter(
              event.target.value as
                | 'all'
                | 'high'
                | 'review'
                | 'low',
            )
            setPage(1)
          }}
        >
          <option value="all">
            All confidence
          </option>
          <option value="high">
            High (90%+)
          </option>
          <option value="review">
            Needs review
          </option>
          <option value="low">
            Low (below 60%)
          </option>
        </select>

        <select
          value={selectedTag}
          onChange={(event) => {
            setSelectedTag(
              event.target.value,
            )
            setPage(1)
          }}
        >
          <option value="all">
            All tags
          </option>

          {allTags.map(
            (tag) => (
              <option
                key={tag}
                value={tag}
              >
                {tag}
              </option>
            ),
          )}
        </select>

        <button
          type="button"
          className={
            favoriteOnly
              ? 'de-favorite-filter active'
              : 'de-favorite-filter'
          }
          onClick={() => {
            setFavoriteOnly(
              (value) => !value,
            )
            setPage(1)
          }}
        >
          ★ Favorites
        </button>

        <button
          type="button"
          onClick={clearFilters}
        >
          Clear
        </button>
      </div>

      <div className="de-summary">
        <div>
          <strong>
            {filteredJobs.length}
          </strong>
          <span>
            matching documents
          </span>
        </div>

        <div className="de-summary-controls">
          <label>
            Sort
            <select
              value={sortKey}
              onChange={(event) =>
                setSortKey(
                  event.target
                    .value as SortKey,
                )
              }
            >
              <option value="created_desc">
                Newest first
              </option>
              <option value="created_asc">
                Oldest first
              </option>
              <option value="name_asc">
                Name A–Z
              </option>
              <option value="name_desc">
                Name Z–A
              </option>
              <option value="confidence_desc">
                Confidence high–low
              </option>
              <option value="confidence_asc">
                Confidence low–high
              </option>
            </select>
          </label>

          <label>
            Rows
            <select
              value={pageSize}
              onChange={(event) => {
                setPageSize(
                  Number(
                    event.target
                      .value,
                  ),
                )
                setPage(1)
              }}
            >
              {PAGE_SIZE_OPTIONS.map(
                (value) => (
                  <option
                    key={value}
                    value={value}
                  >
                    {value}
                  </option>
                ),
              )}
            </select>
          </label>
        </div>
      </div>

      {selectedIds.length > 0 && (
        <div className="de-bulk-bar">
          <strong>
            {selectedIds.length}{' '}
            selected
          </strong>

          <div>
            <input
              value={tagDraft}
              onChange={(event) =>
                setTagDraft(
                  event.target.value,
                )
              }
              placeholder="Add tag"
            />

            <button
              type="button"
              onClick={
                addTagToSelection
              }
            >
              Apply Tag
            </button>

            <button
              type="button"
              onClick={() =>
                setSelectedIds([])
              }
            >
              Clear Selection
            </button>
          </div>
        </div>
      )}

      <div className="de-table-wrap">
        <table className="de-table">
          <thead>
            <tr>
              <th>
                <input
                  type="checkbox"
                  checked={
                    visibleJobs.length >
                      0 &&
                    visibleJobs.every(
                      (job) =>
                        selectedIds.includes(
                          job.job_id,
                        ),
                    )
                  }
                  onChange={
                    togglePageSelection
                  }
                />
              </th>
              <th />
              <th>Document</th>
              <th>Type</th>
              <th>Confidence</th>
              <th>Status</th>
              <th>Tags</th>
              <th>Created</th>
              <th>Size</th>
              <th />
            </tr>
          </thead>

          <tbody>
            {visibleJobs.map(
              (job) => {
                const tags =
                  metadata.tags[
                    job.job_id
                  ] ?? []

                const isFavorite =
                  metadata.favorites.includes(
                    job.job_id,
                  )

                return (
                  <tr
                    key={job.job_id}
                  >
                    <td>
                      <input
                        type="checkbox"
                        checked={selectedIds.includes(
                          job.job_id,
                        )}
                        onChange={() =>
                          toggleSelected(
                            job.job_id,
                          )
                        }
                      />
                    </td>

                    <td>
                      <button
                        type="button"
                        className={
                          isFavorite
                            ? 'de-star active'
                            : 'de-star'
                        }
                        title={
                          isFavorite
                            ? 'Remove favorite'
                            : 'Add favorite'
                        }
                        onClick={() =>
                          toggleFavorite(
                            job.job_id,
                          )
                        }
                      >
                        ★
                      </button>
                    </td>

                    <td>
                      <button
                        type="button"
                        className="de-document-link"
                        onClick={() =>
                          onOpen(job)
                        }
                      >
                        <strong>
                          {
                            job.original_file_name
                          }
                        </strong>
                        <small>
                          {job.message}
                        </small>
                      </button>
                    </td>

                    <td>
                      {formatType(
                        job.document_type,
                      )}
                    </td>

                    <td>
                      <span className="de-confidence-bar">
                        <i
                          style={{
                            width:
                              confidencePercent(
                                job.confidence,
                              ),
                          }}
                        />
                      </span>
                      {confidencePercent(
                        job.confidence,
                      )}
                    </td>

                    <td>
                      <span
                        className={`ed-status ${job.status}`}
                      >
                        {job.status}
                      </span>
                    </td>

                    <td>
                      <div className="de-tags">
                        {tags.map(
                          (tag) => (
                            <button
                              type="button"
                              key={tag}
                              title="Remove tag"
                              onClick={() =>
                                removeTag(
                                  job.job_id,
                                  tag,
                                )
                              }
                            >
                              {tag} ×
                            </button>
                          ),
                        )}

                        {tags.length ===
                          0 && (
                          <span>—</span>
                        )}
                      </div>
                    </td>

                    <td>
                      {new Date(
                        job.created_at,
                      ).toLocaleString()}
                    </td>

                    <td>
                      {formatBytes(
                        job.file_size_bytes,
                      )}
                    </td>

                    <td>
                      {job.status ===
                      'uploaded' ? (
                        <button
                          type="button"
                          disabled={isBusy}
                          onClick={() =>
                            onProcess(job)
                          }
                        >
                          Process
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() =>
                            onOpen(job)
                          }
                        >
                          Open
                        </button>
                      )}
                    </td>
                  </tr>
                )
              },
            )}
          </tbody>
        </table>

        {visibleJobs.length ===
          0 && (
          <div className="de-empty">
            No documents match the
            current filters.
          </div>
        )}
      </div>

      <div className="de-pagination">
        <span>
          Page {effectivePage} of{' '}
          {totalPages}
        </span>

        <div>
          <button
            type="button"
            disabled={
              effectivePage === 1
            }
            onClick={() =>
              setPage(
                (value) =>
                  Math.max(
                    1,
                    value - 1,
                  ),
              )
            }
          >
            Previous
          </button>

          <button
            type="button"
            disabled={
              effectivePage ===
              totalPages
            }
            onClick={() =>
              setPage(
                (value) =>
                  Math.min(
                    totalPages,
                    value + 1,
                  ),
              )
            }
          >
            Next
          </button>
        </div>
      </div>
    </section>
  )
}

export default DocumentExplorer
