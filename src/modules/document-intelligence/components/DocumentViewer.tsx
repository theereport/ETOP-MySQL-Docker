import {
  useEffect,
  useMemo,
  useState,
} from 'react'

import {
  getDocumentFile,
  generateLearningExamples,
  getDocumentReview,
  saveDocumentReview,
} from '../api'

import type {
  DocumentJob,
  DocumentResult,
  DocumentReviewHistoryItem,
  DocumentReviewStatus,
} from '../types'

import {
  confidencePercent,
  formatDocumentType,
  objectEntries,
} from '../utils'

type Props = {
  job: DocumentJob
  result: DocumentResult | null
  onBack: () => void
}

type EditableFields =
  Record<string, unknown>

function displayValue(
  value: unknown,
): string {
  if (
    value === null ||
    value === undefined
  ) {
    return ''
  }

  if (
    typeof value === 'object'
  ) {
    return JSON.stringify(
      value,
      null,
      2,
    )
  }

  return String(value)
}

function parseEditedValue(
  original: unknown,
  value: string,
): unknown {
  if (
    typeof original === 'number'
  ) {
    const parsed =
      Number(value)

    return Number.isNaN(parsed)
      ? value
      : parsed
  }

  if (
    typeof original === 'boolean'
  ) {
    return (
      value.trim().toLowerCase() ===
      'true'
    )
  }

  if (
    original &&
    typeof original === 'object'
  ) {
    try {
      return JSON.parse(value)
    } catch {
      return value
    }
  }

  return value
}

export default function DocumentViewer({
  job,
  result,
  onBack,
}: Props) {
  const [
    fileUrl,
    setFileUrl,
  ] = useState('')

  const [
    fileError,
    setFileError,
  ] = useState('')

  const [
    isLoadingFile,
    setIsLoadingFile,
  ] = useState(true)

  const [
    page,
    setPage,
  ] = useState(1)

  const [
    zoom,
    setZoom,
  ] = useState(100)

  const [
    fields,
    setFields,
  ] = useState<EditableFields>(
    () => ({
      ...(result?.parsed ?? {}),
    }),
  )

  const [
    activeTab,
    setActiveTab,
  ] = useState<
    'fields' | 'raw' | 'evidence'
  >('fields')

  const [
    copied,
    setCopied,
  ] = useState(false)

  const [
    reviewStatus,
    setReviewStatus,
  ] = useState<DocumentReviewStatus>(
    'pending',
  )

  const [
    reviewer,
    setReviewer,
  ] = useState('')

  const [
    notes,
    setNotes,
  ] = useState('')

  const [
    reviewHistory,
    setReviewHistory,
  ] = useState<
    DocumentReviewHistoryItem[]
  >([])

  const [
    isSavingReview,
    setIsSavingReview,
  ] = useState(false)

  const [
    reviewMessage,
    setReviewMessage,
  ] = useState('')

  const [
    reviewError,
    setReviewError,
  ] = useState('')

  const [isGeneratingLearning, setIsGeneratingLearning] = useState(false)

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      setFields({
        ...(result?.parsed ?? {}),
      })
    }, 0)
    return () => window.clearTimeout(timeoutId)
  }, [job.job_id, result])


  useEffect(() => {
    const controller =
      new AbortController()

    const timeoutId = window.setTimeout(() => {
      setReviewMessage('')
      setReviewError('')

      void getDocumentReview(
        job.job_id,
        controller.signal,
      )
      .then((payload) => {
        setReviewStatus(
          payload.review.status,
        )
        setReviewer(
          payload.review.reviewer,
        )
        setNotes(
          payload.review.notes,
        )
        setReviewHistory(
          payload.history,
        )

        if (
          Object.keys(
            payload.review
              .corrected_fields,
          ).length > 0
        ) {
          setFields({
            ...(result?.parsed ??
              {}),
            ...payload.review
              .corrected_fields,
          })
        }
      })
      .catch((error) => {
        if (
          controller.signal.aborted
        ) {
          return
        }

        setReviewError(
          error instanceof Error
            ? error.message
            : 'Unable to load review data.',
        )
      })
    }, 0)

    return () => {
      window.clearTimeout(timeoutId)
      controller.abort()
    }
  }, [job.job_id, result])

  useEffect(() => {
    const controller =
      new AbortController()

    let currentUrl = ''

    const timeoutId = window.setTimeout(() => {
      setIsLoadingFile(true)
      setFileError('')
      setFileUrl('')

      void getDocumentFile(
        job.job_id,
        controller.signal,
      )
      .then((blob) => {
        if (controller.signal.aborted) return
        currentUrl =
          URL.createObjectURL(blob)
        setFileUrl(currentUrl)
      })
      .catch((error) => {
        if (
          controller.signal.aborted
        ) {
          return
        }

        setFileError(
          error instanceof Error
            ? error.message
            : 'Unable to load the PDF.',
        )
      })
      .finally(() => {
        if (
          !controller.signal.aborted
        ) {
          setIsLoadingFile(false)
        }
      })
    }, 0)

    return () => {
      window.clearTimeout(timeoutId)
      controller.abort()

      if (currentUrl) {
        URL.revokeObjectURL(
          currentUrl,
        )
      }
    }
  }, [job.job_id])

  const pdfSource =
    useMemo(() => {
      if (!fileUrl) {
        return ''
      }

      return `${fileUrl}#page=${page}&zoom=${zoom}`
    }, [fileUrl, page, zoom])

  const changedCount =
    useMemo(() => {
      const original =
        result?.parsed ?? {}

      return Object.keys(fields)
        .filter(
          (key) =>
            JSON.stringify(
              fields[key],
            ) !==
            JSON.stringify(
              original[key],
            ),
        )
        .length
    }, [fields, result])

  const copyFields = async () => {
    await navigator.clipboard.writeText(
      JSON.stringify(
        fields,
        null,
        2,
      ),
    )

    setCopied(true)

    window.setTimeout(
      () => setCopied(false),
      1400,
    )
  }

  const generateLearning = async () => {
    setIsGeneratingLearning(true)
    setReviewMessage('')
    setReviewError('')
    try {
      const response = await generateLearningExamples(job.job_id)
      setReviewMessage(`${response.created} learning example${response.created === 1 ? '' : 's'} created. ${response.skipped} skipped.`)
    } catch (error) {
      setReviewError(error instanceof Error ? error.message : 'Unable to generate learning examples.')
    } finally {
      setIsGeneratingLearning(false)
    }
  }

  const saveReview = async (
    nextStatus: DocumentReviewStatus =
      reviewStatus,
  ) => {
    if (!result?.processing_run_id) {
      setReviewError(
        'The current processing run identity is unavailable. Reload or reprocess the document before saving review evidence.',
      )
      return
    }
    setIsSavingReview(true)
    setReviewMessage('')
    setReviewError('')

    const original =
      result?.parsed ?? {}

    const correctedFields =
      Object.fromEntries(
        Object.entries(fields).filter(
          ([key, value]) =>
            JSON.stringify(value) !==
            JSON.stringify(
              original[key],
            ),
        ),
      )

    try {
      const payload =
        await saveDocumentReview(
          job.job_id,
          {
            expected_processing_run_id:
              result.processing_run_id,
            status: nextStatus,
            reviewer:
              reviewer.trim(),
            notes: notes.trim(),
            corrected_fields:
              correctedFields,
          },
        )

      setReviewStatus(
        payload.review.status,
      )
      setReviewHistory(
        payload.history,
      )
      setReviewMessage(
        'Review saved successfully.',
      )
    } catch (error) {
      setReviewError(
        error instanceof Error
          ? error.message
          : 'Unable to save the review.',
      )
    } finally {
      setIsSavingReview(false)
    }
  }

  return (
    <section className="ed-viewer-shell">
      <header className="ed-viewer-header">
        <div className="ed-viewer-heading">
          <button
            type="button"
            className="ed-back-button"
            onClick={onBack}
          >
            ←
          </button>

          <div>
            <span>
              DOCUMENT REVIEW
            </span>
            <strong>
              {
                job.original_file_name
              }
            </strong>
            <small>
              {formatDocumentType(
                job.document_type,
              )}{' '}
              ·{' '}
              {confidencePercent(
                job.confidence,
              )}{' '}
              confidence
            </small>
          </div>
        </div>

        <div className="ed-viewer-actions">
          <span
            className={`ed-review-status ${reviewStatus}`}
          >
            {formatDocumentType(
              reviewStatus,
            )}
          </span>

          {changedCount > 0 && (
            <span className="ed-change-badge">
              {changedCount}{' '}
              unsaved change
              {changedCount === 1
                ? ''
                : 's'}
            </span>
          )}

          <button
            type="button"
            onClick={() => {
              setFields({
                ...(result?.parsed ??
                  {}),
              })
            }}
            disabled={
              changedCount === 0
            }
          >
            Reset Fields
          </button>

          <button
            type="button"
            onClick={() =>
              void copyFields()
            }
          >
            {copied
              ? 'Copied'
              : 'Copy JSON'}
          </button>
        </div>
      </header>

      <div className="ed-viewer-grid">
        <article className="ed-pdf-panel">
          <div className="ed-pdf-toolbar">
            <div>
              <button
                type="button"
                onClick={() =>
                  setZoom(
                    (value) =>
                      Math.max(
                        50,
                        value - 10,
                      ),
                  )
                }
              >
                −
              </button>

              <span>
                {zoom}%
              </span>

              <button
                type="button"
                onClick={() =>
                  setZoom(
                    (value) =>
                      Math.min(
                        200,
                        value + 10,
                      ),
                  )
                }
              >
                +
              </button>

              <button
                type="button"
                onClick={() =>
                  setZoom(100)
                }
              >
                Reset zoom
              </button>
            </div>

            <label>
              Page
              <input
                type="number"
                min={1}
                value={page}
                onChange={(event) =>
                  setPage(
                    Math.max(
                      1,
                      Number(
                        event.target
                          .value,
                      ) || 1,
                    ),
                  )
                }
              />
            </label>
          </div>

          <div className="ed-pdf-frame">
            {isLoadingFile && (
              <div className="ed-pdf-message">
                Loading PDF…
              </div>
            )}

            {fileError && (
              <div className="ed-pdf-message error">
                <strong>
                  PDF unavailable
                </strong>
                <span>
                  {fileError}
                </span>
                <small>
                  Confirm the backend
                  file endpoint from the
                  Sprint 2 installation
                  guide is installed.
                </small>
              </div>
            )}

            {pdfSource &&
              !fileError && (
                <iframe
                  key={pdfSource}
                  title={
                    job.original_file_name
                  }
                  src={pdfSource}
                />
              )}
          </div>
        </article>

        <article className="ed-review-panel">
          <div className="ed-review-tabs">
            <button
              type="button"
              className={
                activeTab === 'fields'
                  ? 'active'
                  : ''
              }
              onClick={() =>
                setActiveTab('fields')
              }
            >
              Extracted Fields
            </button>

            <button
              type="button"
              className={
                activeTab === 'evidence'
                  ? 'active'
                  : ''
              }
              onClick={() =>
                setActiveTab(
                  'evidence',
                )
              }
            >
              Evidence
            </button>

            <button
              type="button"
              className={
                activeTab === 'raw'
                  ? 'active'
                  : ''
              }
              onClick={() =>
                setActiveTab('raw')
              }
            >
              Raw Output
            </button>
          </div>

          {activeTab ===
            'fields' && (
            <div className="ed-review-fields">
              <div className="ed-review-summary">
                <div>
                  <span>
                    Document Type
                  </span>
                  <strong>
                    {formatDocumentType(
                      job.document_type,
                    )}
                  </strong>
                </div>

                <div>
                  <span>
                    Parser
                  </span>
                  <strong>
                    {result?.classifier ??
                      '—'}
                  </strong>
                </div>

                <div>
                  <span>
                    Confidence
                  </span>
                  <strong>
                    {confidencePercent(
                      job.confidence,
                    )}
                  </strong>
                </div>
              </div>

              <div className="ed-editable-field-list">
                {objectEntries(
                  fields,
                ).map(
                  ([
                    field,
                    value,
                  ]) => {
                    const original =
                      result?.parsed?.[
                        field
                      ]

                    const changed =
                      JSON.stringify(
                        value,
                      ) !==
                      JSON.stringify(
                        original,
                      )

                    const multiline =
                      typeof value ===
                        'object' ||
                      displayValue(
                        value,
                      ).length > 80

                    return (
                      <label
                        key={field}
                        className={
                          changed
                            ? 'changed'
                            : ''
                        }
                      >
                        <span>
                          {formatDocumentType(
                            field,
                          )}
                          {changed && (
                            <b>
                              Edited
                            </b>
                          )}
                        </span>

                        {multiline ? (
                          <textarea
                            value={displayValue(
                              value,
                            )}
                            onChange={(
                              event,
                            ) =>
                              setFields(
                                (
                                  current,
                                ) => ({
                                  ...current,
                                  [field]:
                                    parseEditedValue(
                                      original,
                                      event
                                        .target
                                        .value,
                                    ),
                                }),
                              )
                            }
                          />
                        ) : (
                          <input
                            value={displayValue(
                              value,
                            )}
                            onChange={(
                              event,
                            ) =>
                              setFields(
                                (
                                  current,
                                ) => ({
                                  ...current,
                                  [field]:
                                    parseEditedValue(
                                      original,
                                      event
                                        .target
                                        .value,
                                    ),
                                }),
                              )
                            }
                          />
                        )}
                      </label>
                    )
                  },
                )}

                {objectEntries(
                  fields,
                ).length === 0 && (
                  <div className="ed-empty">
                    No parsed fields were
                    returned.
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab ===
            'evidence' && (
            <div className="ed-evidence-panel">
              <strong>
                Classification Evidence
              </strong>

              {result
                ?.classification_evidence
                .map(
                  (
                    evidence,
                    index,
                  ) => (
                    <article
                      key={`${evidence}-${index}`}
                    >
                      <span>
                        {index + 1}
                      </span>
                      <p>
                        {evidence}
                      </p>
                    </article>
                  ),
                )}

              {!result
                ?.classification_evidence
                .length && (
                <div className="ed-empty">
                  No classification
                  evidence was returned.
                </div>
              )}
            </div>
          )}

          {activeTab === 'raw' && (
            <div className="ed-raw-output">
              <details open>
                <summary>
                  Parsed Output
                </summary>
                <pre>
                  {JSON.stringify(
                    fields,
                    null,
                    2,
                  )}
                </pre>
              </details>

              <details>
                <summary>
                  Extraction Output
                </summary>
                <pre>
                  {JSON.stringify(
                    result?.extraction ??
                      {},
                    null,
                    2,
                  )}
                </pre>
              </details>
            </div>
          )}

          <div className="ed-review-decision">
            <div className="ed-review-decision-heading">
              <div>
                <span>
                  REVIEW DECISION
                </span>
                <strong>
                  Validate and route
                </strong>
              </div>

              <select
                value={reviewStatus}
                onChange={(event) =>
                  setReviewStatus(
                    event.target
                      .value as DocumentReviewStatus,
                  )
                }
              >
                <option value="pending">
                  Pending
                </option>
                <option value="approved">
                  Approved
                </option>
                <option value="rejected">
                  Rejected
                </option>
                <option value="needs_correction">
                  Needs Correction
                </option>
                <option value="needs_learning">
                  Needs Learning
                </option>
              </select>
            </div>

            <div className="ed-review-decision-grid">
              <label>
                Reviewer
                <input
                  value={reviewer}
                  onChange={(event) =>
                    setReviewer(
                      event.target.value,
                    )
                  }
                  placeholder="Reviewer name"
                />
              </label>

              <label className="wide">
                Notes
                <textarea
                  value={notes}
                  onChange={(event) =>
                    setNotes(
                      event.target.value,
                    )
                  }
                  placeholder="Why was this approved, corrected, rejected, or sent to learning?"
                />
              </label>
            </div>

            {reviewError && (
              <div className="ed-inline-message error">
                {reviewError}
              </div>
            )}

            {reviewMessage && (
              <div className="ed-inline-message success">
                {reviewMessage}
              </div>
            )}

            <div className="ed-review-decision-actions">
              <button
                type="button"
                onClick={() =>
                  void saveReview()
                }
                disabled={
                  isSavingReview
                }
              >
                {isSavingReview
                  ? 'Saving…'
                  : 'Save Review'}
              </button>

              <button
                type="button"
                className="primary"
                onClick={() =>
                  void saveReview(
                    'approved',
                  )
                }
                disabled={
                  isSavingReview
                }
              >
                Approve
              </button>

              <button
                type="button"
                className="danger"
                onClick={() =>
                  void saveReview(
                    'rejected',
                  )
                }
                disabled={
                  isSavingReview
                }
              >
                Reject
              </button>

              <button type="button" onClick={() => void generateLearning()} disabled={isGeneratingLearning || changedCount === 0}>
                {isGeneratingLearning ? 'Generating…' : 'Create Learning Examples'}
              </button>
            </div>

            <details className="ed-review-history">
              <summary>
                Review History (
                {reviewHistory.length})
              </summary>

              <div>
                {reviewHistory.map(
                  (item) => (
                    <article key={item.id}>
                      <div>
                        <span
                          className={`ed-review-status ${item.status}`}
                        >
                          {formatDocumentType(
                            item.status,
                          )}
                        </span>
                        <strong>
                          {item.reviewer ||
                            'Unassigned reviewer'}
                        </strong>
                        <small>
                          {new Date(
                            item.created_at,
                          ).toLocaleString()}
                        </small>
                      </div>

                      {item.notes && (
                        <p>
                          {item.notes}
                        </p>
                      )}

                      {Object.keys(
                        item.corrected_fields,
                      ).length > 0 && (
                        <pre>
                          {JSON.stringify(
                            item.corrected_fields,
                            null,
                            2,
                          )}
                        </pre>
                      )}
                    </article>
                  ),
                )}

                {reviewHistory.length ===
                  0 && (
                  <div className="ed-empty">
                    No review history yet.
                  </div>
                )}
              </div>
            </details>
          </div>
        </article>
      </div>
    </section>
  )
}
