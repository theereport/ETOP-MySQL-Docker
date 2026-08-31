import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import type { ChangeEvent, DragEvent } from 'react'

import APVendorNumberSearchField from './APVendorNumberSearchField'
import {
  getAPGLCodingSuggestions,
  getAPVendorInvoiceFileUrl,
  getAPVendorInvoiceJob,
  getAPVendorInvoiceJobs,
  getAPVendorInvoiceResult,
  getAPVendorInvoiceReview,
  getAPVendorInvoiceRuns,
  reprocessAPVendorInvoice,
  saveAPVendorInvoiceReview,
  syncAccountsPayableInvoiceJob,
  uploadAPVendorInvoice,
} from './api'
import { errorMessage, formatDateTime, isAbortError } from './format'
import type {
  APGLCodingSuggestionsResponse,
  APSyncResponse,
  APVendorInvoiceDocumentJob,
  APVendorInvoiceDocumentResult,
  APVendorInvoiceEvidenceCandidate,
  APVendorInvoiceFieldEvidence,
  APVendorInvoiceProcessingRun,
  APVendorInvoiceReview,
} from './types'

type AsyncStatus = 'idle' | 'loading' | 'success' | 'error'
type ActionTone = 'success' | 'warning'

type Props = {
  onOpenImportedEvidence: (jobId: string) => void
  onProjectionChanged: () => Promise<void>
}

const MAX_VENDOR_INVOICE_BYTES = 50 * 1024 * 1024
const DATASET_PAGE_SIZE = 50

const FIELD_LABELS: Record<string, string> = {
  vendor_number: 'Vendor number',
  vendor_name: 'Vendor name',
  invoice_number: 'Invoice number',
  invoice_date: 'Invoice date',
  due_date: 'Due date',
  purchase_order_number: 'Purchase order',
  terms: 'Payment terms',
  subtotal: 'Subtotal',
  tax: 'Tax',
  freight: 'Freight',
  discount: 'Discount',
  total_amount: 'Invoice total',
  currency: 'Currency',
  ocr_confidence: 'OCR confidence',
}

const REVIEWABLE_FIELD_NAMES = Object.keys(FIELD_LABELS).filter(
  (fieldName) => fieldName !== 'ocr_confidence',
)
const REVIEWABLE_FIELD_NAME_SET = new Set(REVIEWABLE_FIELD_NAMES)

function displayValue(value: unknown): string {
  return value === null || value === undefined ? '' : String(value)
}

function confidence(value: number | null | undefined): string {
  return value === null || value === undefined
    ? 'Unavailable'
    : `${(value * 100).toFixed(1)}%`
}

function distinctEvidenceCandidates(
  evidence: APVendorInvoiceFieldEvidence,
): APVendorInvoiceEvidenceCandidate[] {
  const retained = [
    ...(evidence.candidates ?? []),
    ...(evidence.observations ?? []),
  ]
  const seen = new Set<string>()
  return retained.filter((candidate) => {
    const value = displayValue(candidate.value).trim()
    if (!value) return false
    const key = `${typeof candidate.value}:${value}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function fileSize(value: number): string {
  return value >= 1024 * 1024
    ? `${(value / (1024 * 1024)).toFixed(1)} MB`
    : `${Math.max(1, Math.round(value / 1024))} KB`
}

function GLCodingSuggestionsHint({
  status,
  suggestions,
}: {
  status: AsyncStatus
  suggestions: APGLCodingSuggestionsResponse | null
}) {
  if (status === 'idle') return null
  if (status === 'loading') {
    return <small className="ap-capture-gl-hint">Checking this vendor's historical GL coding…</small>
  }
  if (status === 'error' || !suggestions) {
    return null
  }
  if (suggestions.suggestions.length === 0) {
    return (
      <small className="ap-capture-gl-hint">
        No reliable historical GL coding shortlist for this vendor
        {suggestions.total_coded_invoice_count > 0 ? ' (too few real coding choices to rank)' : ' (no coding history found)'}.
      </small>
    )
  }
  return (
    <small className="ap-capture-gl-hint">
      This vendor typically codes to: {suggestions.suggestions.map((item) => (
        `${[item.gl_division, item.gl_account, item.gl_department].filter(Boolean).join('-')}${item.gl_account_description ? ` (${item.gl_account_description})` : ''} — ${item.match_percent}%`
      )).join(' · ')}
      {' · reference only, not a coding entry'}
    </small>
  )
}

export default function APVendorInvoiceCapture({
  onOpenImportedEvidence,
  onProjectionChanged,
}: Props) {
  const inputRef = useRef<HTMLInputElement | null>(null)
  const datasetGeneration = useRef(0)
  const detailGeneration = useRef(0)
  const selectedJobIdRef = useRef<string | null>(null)
  const [jobs, setJobs] = useState<APVendorInvoiceDocumentJob[]>([])
  const [datasetTotal, setDatasetTotal] = useState(0)
  const [datasetLoadingMore, setDatasetLoadingMore] = useState(false)
  const [datasetStatus, setDatasetStatus] = useState<AsyncStatus>('loading')
  const [datasetError, setDatasetError] = useState('')
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null)
  const [result, setResult] = useState<APVendorInvoiceDocumentResult | null>(null)
  const [runs, setRuns] = useState<APVendorInvoiceProcessingRun[]>([])
  const [review, setReview] = useState<APVendorInvoiceReview | null>(null)
  const [detailStatus, setDetailStatus] = useState<AsyncStatus>('idle')
  const [detailError, setDetailError] = useState('')
  const [actionStatus, setActionStatus] = useState<AsyncStatus>('idle')
  const [actionTone, setActionTone] = useState<ActionTone>('success')
  const [actionMessage, setActionMessage] = useState('')
  const [actionError, setActionError] = useState('')
  const [reviewer, setReviewer] = useState('')
  const [notes, setNotes] = useState('')
  const [reviewOutcome, setReviewOutcome] = useState<'approved' | 'needs_correction' | 'needs_learning'>('approved')
  const [correctedFields, setCorrectedFields] = useState<Record<string, string>>({})
  const [unavailableFields, setUnavailableFields] = useState<string[]>([])
  const [syncResult, setSyncResult] = useState<APSyncResponse | null>(null)
  const [isDragActive, setIsDragActive] = useState(false)
  const dragDepth = useRef(0)
  const [glSuggestions, setGlSuggestions] = useState<APGLCodingSuggestionsResponse | null>(null)
  const [glSuggestionsStatus, setGlSuggestionsStatus] = useState<AsyncStatus>('idle')
  const selectedJob = useMemo(
    () => jobs.find((job) => job.job_id === selectedJobId) ?? null,
    [jobs, selectedJobId],
  )

  const selectJob = useCallback((jobId: string | null) => {
    selectedJobIdRef.current = jobId
    detailGeneration.current += 1
    setSelectedJobId(jobId)
  }, [])

  const loadDataset = useCallback(async (
    signal?: AbortSignal,
    offset = 0,
    append = false,
  ) => {
    const generation = datasetGeneration.current + 1
    datasetGeneration.current = generation
    if (append) setDatasetLoadingMore(true)
    else setDatasetStatus('loading')
    setDatasetError('')
    try {
      const page = await getAPVendorInvoiceJobs(
        DATASET_PAGE_SIZE,
        offset,
        signal,
      )
      if (datasetGeneration.current !== generation) return
      setJobs((current) => {
        if (!append) return page.jobs
        const byId = new Map(current.map((job) => [job.job_id, job]))
        page.jobs.forEach((job) => byId.set(job.job_id, job))
        return [...byId.values()]
      })
      setDatasetTotal(page.total)
      setDatasetStatus('success')
      if (selectedJobIdRef.current === null && page.jobs[0]) {
        selectJob(page.jobs[0].job_id)
      }
    } catch (error) {
      if (isAbortError(error) || datasetGeneration.current !== generation) return
      if (!append) {
        setJobs([])
        setDatasetTotal(0)
      }
      setDatasetStatus('error')
      setDatasetError(errorMessage(error, 'Unable to load the vendor invoice dataset.'))
    } finally {
      if (datasetGeneration.current === generation) setDatasetLoadingMore(false)
    }
  }, [selectJob])

  useEffect(() => {
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => {
      void loadDataset(controller.signal)
    }, 0)
    return () => {
      window.clearTimeout(timeoutId)
      controller.abort()
      datasetGeneration.current += 1
    }
  }, [loadDataset])

  const loadSelected = useCallback(async (
    job: APVendorInvoiceDocumentJob,
    signal?: AbortSignal,
  ) => {
    const generation = detailGeneration.current + 1
    detailGeneration.current = generation
    setDetailStatus('loading')
    setDetailError('')
    setResult(null)
    setRuns([])
    setReview(null)
    setUnavailableFields([])
    try {
      const [nextRuns, nextReview] = await Promise.all([
        getAPVendorInvoiceRuns(job.job_id, signal),
        getAPVendorInvoiceReview(job.job_id, signal),
      ])
      const nextResult = (
        job.status === 'completed'
        || nextRuns.some((run) => run.status === 'completed')
      )
        ? await getAPVendorInvoiceResult(job.job_id, signal)
        : null
      if (
        detailGeneration.current !== generation
        || selectedJobIdRef.current !== job.job_id
      ) return
      setRuns(nextRuns)
      setReview(nextReview)
      setResult(nextResult)
      setReviewer(nextReview.review.reviewer)
      setNotes(nextReview.review.notes)
      setReviewOutcome(
        nextReview.review.status === 'needs_correction' || nextReview.review.status === 'needs_learning'
          ? nextReview.review.status
          : 'approved',
      )
      const sourceFields = nextResult?.parsed.fields ?? {}
      const corrected = nextReview.review.corrected_fields ?? {}
      setUnavailableFields(
        (nextReview.review.unavailable_fields ?? []).filter(
          (fieldName) => REVIEWABLE_FIELD_NAME_SET.has(fieldName),
        ),
      )
      setCorrectedFields(
        Object.fromEntries(
          Object.keys(FIELD_LABELS).map((field) => [
            field,
            displayValue(corrected[field] ?? sourceFields[field]),
          ]),
        ),
      )
      setDetailStatus('success')
    } catch (error) {
      if (
        isAbortError(error)
        || detailGeneration.current !== generation
        || selectedJobIdRef.current !== job.job_id
      ) return
      setDetailStatus('error')
      setDetailError(errorMessage(error, 'Unable to load invoice extraction evidence.'))
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => {
      if (!selectedJob) {
        detailGeneration.current += 1
        setResult(null)
        setRuns([])
        setReview(null)
        setUnavailableFields([])
        setDetailStatus('idle')
        return
      }
      void loadSelected(selectedJob, controller.signal)
    }, 0)
    return () => {
      window.clearTimeout(timeoutId)
      controller.abort()
      detailGeneration.current += 1
    }
  }, [loadSelected, selectedJob])

  const reviewVendorNumber = correctedFields.vendor_number?.trim() ?? ''

  useEffect(() => {
    if (!reviewVendorNumber || !/^\d+$/.test(reviewVendorNumber)) {
      setGlSuggestions(null)
      setGlSuggestionsStatus('idle')
      return
    }
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => {
      setGlSuggestionsStatus('loading')
      getAPGLCodingSuggestions(reviewVendorNumber, controller.signal)
        .then((response) => {
          setGlSuggestions(response)
          setGlSuggestionsStatus('success')
        })
        .catch((error) => {
          if (isAbortError(error)) return
          setGlSuggestions(null)
          setGlSuggestionsStatus('error')
        })
    }, 400)
    return () => {
      window.clearTimeout(timeoutId)
      controller.abort()
    }
  }, [reviewVendorNumber])

  const fieldEvidence = useMemo(() => {
    const evidence = result?.parsed.field_evidence ?? {}
    return Object.keys(FIELD_LABELS).map((fieldName) => ({
      fieldName,
      evidence: evidence[fieldName] ?? {
        field_name: fieldName,
        value: null,
        source: 'unavailable',
        page: null,
        location: null,
        confidence: null,
        authority: 'unavailable',
        rule_version: null,
        validation_status: 'unavailable',
      } satisfies APVendorInvoiceFieldEvidence,
    }))
  }, [result])

  function setFieldUnavailable(fieldName: string, unavailable: boolean) {
    if (!REVIEWABLE_FIELD_NAME_SET.has(fieldName)) return
    if (unavailable) {
      setUnavailableFields((current) => (
        current.includes(fieldName) ? current : [...current, fieldName]
      ))
      setCorrectedFields((current) => {
        const next = { ...current }
        delete next[fieldName]
        return next
      })
      return
    }
    setUnavailableFields((current) => current.filter((item) => item !== fieldName))
    setCorrectedFields((current) => ({
      ...current,
      [fieldName]: displayValue(result?.parsed.fields?.[fieldName]),
    }))
  }

  async function refreshSelected(jobId: string) {
    const refreshed = await getAPVendorInvoiceJob(jobId)
    setJobs((current) => {
      const found = current.some((job) => job.job_id === jobId)
      return found
        ? current.map((job) => (job.job_id === jobId ? refreshed : job))
        : [refreshed, ...current]
    })
    if (selectedJobIdRef.current === jobId) {
      await loadSelected(refreshed)
    }
  }

  function isPdfFile(file: File): boolean {
    return file.name.toLowerCase().endsWith('.pdf')
      && (!file.type || ['application/pdf', 'application/x-pdf', 'application/octet-stream'].includes(file.type))
  }

  async function uploadFiles(files: File[]) {
    if (files.length === 0) return
    setActionMessage('')
    setActionTone('success')
    setActionError('')
    setSyncResult(null)

    const accepted: File[] = []
    const failures: string[] = []
    files.forEach((file) => {
      if (!isPdfFile(file)) {
        failures.push(`${file.name} — not a PDF`)
      } else if (file.size === 0 || file.size > MAX_VENDOR_INVOICE_BYTES) {
        failures.push(`${file.name} — empty or over 50 MB`)
      } else {
        accepted.push(file)
      }
    })

    if (accepted.length === 0) {
      setActionStatus('error')
      setActionError(
        failures.length > 0
          ? `No files uploaded: ${failures.join('; ')}.`
          : 'Vendor Invoice Dataset & OCR accepts PDF files only.',
      )
      return
    }

    setActionStatus('loading')
    let succeeded = 0
    let lastJobId: string | null = null
    for (const file of accepted) {
      try {
        const intake = await uploadAPVendorInvoice(file)
        lastJobId = intake.job.job_id
        if (intake.intake_status === 'failed') {
          failures.push(`${file.name} — ${intake.job.message}`)
        } else {
          succeeded += 1
        }
      } catch (error) {
        failures.push(`${file.name} — ${errorMessage(error, 'upload failed')}`)
      }
    }

    await loadDataset()
    if (lastJobId) selectJob(lastJobId)

    setActionStatus(succeeded > 0 ? 'success' : 'error')
    if (succeeded > 0) {
      setActionTone('warning')
      setActionMessage(
        succeeded === 1 && failures.length === 0
          ? 'Vendor invoice preserved and processed.'
          : `${succeeded} of ${files.length} vendor invoice${files.length === 1 ? '' : 's'} preserved and processed.`,
      )
    }
    if (failures.length > 0) {
      setActionError(
        `${failures.length} file${failures.length === 1 ? '' : 's'} not uploaded: ${failures.join('; ')}`,
      )
    }
  }

  function uploadFile(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? [])
    event.target.value = ''
    void uploadFiles(files)
  }

  function handleDragEnter(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    dragDepth.current += 1
    setIsDragActive(true)
  }

  function handleDragOver(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
  }

  function handleDragLeave(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    dragDepth.current = Math.max(0, dragDepth.current - 1)
    if (dragDepth.current === 0) setIsDragActive(false)
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    dragDepth.current = 0
    setIsDragActive(false)
    void uploadFiles(Array.from(event.dataTransfer.files ?? []))
  }

  async function reprocess() {
    if (!selectedJob) return
    setActionStatus('loading')
    setActionError('')
    setActionMessage('')
    try {
      const processed = await reprocessAPVendorInvoice(selectedJob.job_id)
      setActionStatus('success')
      setActionTone('warning')
      setActionMessage(`${processed.job.message} A new processing run was appended; every prior run remains retrievable.`)
      await refreshSelected(selectedJob.job_id)
    } catch (error) {
      setActionStatus('error')
      setActionError(errorMessage(error, 'Unable to create a new processing run.'))
      await refreshSelected(selectedJob.job_id)
    }
  }

  async function saveReview() {
    if (!selectedJob || !result) return
    if (!result.processing_run_id) {
      setActionStatus('error')
      setActionError('Reload or reprocess this document before saving review evidence; the current run identity is unavailable.')
      return
    }
    const actionJobId = selectedJob.job_id
    if (!reviewer.trim() || !notes.trim()) {
      setActionStatus('error')
      setActionError('Reviewer and review notes are required for extraction review evidence.')
      return
    }
    const sourceFields = result.parsed.fields ?? {}
    const unavailableFieldSet = new Set(unavailableFields)
    const corrections = Object.fromEntries(
      Object.entries(correctedFields)
        .map(([field, value]) => [field, value.trim()] as const)
        .filter(([field, value]) => (
          !unavailableFieldSet.has(field)
          && value !== ''
          && value !== displayValue(sourceFields[field])
        )),
    )
    setActionStatus('loading')
    setActionError('')
    setActionMessage('')
    setActionTone('success')
    try {
      const saved = await saveAPVendorInvoiceReview(selectedJob.job_id, {
        expected_processing_run_id: result.processing_run_id,
        status: reviewOutcome,
        reviewer: reviewer.trim(),
        notes: notes.trim(),
        corrected_fields: corrections,
        unavailable_fields: REVIEWABLE_FIELD_NAMES.filter(
          (fieldName) => unavailableFieldSet.has(fieldName),
        ),
      })
      if (selectedJobIdRef.current === actionJobId) {
        setReview(saved)
        setUnavailableFields(saved.review.unavailable_fields ?? [])
      }
      setActionStatus('success')
      setActionMessage(
        reviewOutcome === 'approved'
          ? 'Extraction evidence review saved. This is not invoice approval or payment authorization.'
          : 'Correction/unavailable review evidence saved without overwriting the processing run.',
      )
    } catch (error) {
      setActionStatus('error')
      setActionError(errorMessage(error, 'Unable to save extraction review evidence.'))
    }
  }

  async function syncCurrentEvidence() {
    if (!selectedJob) return
    setActionStatus('loading')
    setActionError('')
    setActionMessage('')
    setSyncResult(null)
    setActionTone('success')
    try {
      const synced = await syncAccountsPayableInvoiceJob(selectedJob.job_id)
      setSyncResult(synced)
      setActionStatus('success')
      setActionMessage(
        'This exact current extraction and correction evidence synchronized idempotently into the AP evidence projection.',
      )
      await onProjectionChanged()
    } catch (error) {
      setActionStatus('error')
      setActionError(errorMessage(error, 'Unable to synchronize Document Intelligence evidence into AP.'))
    }
  }

  const extractionReviewed = Boolean(
    result?.processing_run_id
    && review?.review.status === 'approved'
    && review.review.processing_run_id === result.processing_run_id,
  )
  const legacyPageSources = new Set(
    (result?.extraction.pages ?? [])
      .map((page) => page.text_source)
      .filter((source): source is string => Boolean(source)),
  )
  const legacyTextSource = legacyPageSources.has('native_pdf_text') && legacyPageSources.has('local_tesseract_ocr')
    ? 'mixed_native_and_ocr'
    : legacyPageSources.has('native_pdf_text')
      ? 'native_pdf_text'
      : legacyPageSources.has('local_tesseract_ocr')
        ? 'local_tesseract_ocr'
        : 'unavailable'
  const textSource = result?.parsed.field_summary?.text_source
    ?? result?.extraction.text_source_summary
    ?? legacyTextSource
  const textSourceLabel = textSource === 'native_pdf_text'
    ? 'Native PDF text'
    : textSource === 'local_tesseract_ocr'
      ? 'Local OCR text'
      : textSource === 'mixed_native_and_ocr'
        ? 'Native + local OCR'
        : 'Text unavailable'
  const ocrAttemptedCount = result?.extraction.ocr_attempted_pages?.length ?? 0
  const ocrCompletedCount = result?.extraction.ocr_completed_pages?.length ?? 0
  const ocrStatusLabel = ocrAttemptedCount === 0 && textSource === 'native_pdf_text'
    ? 'OCR not needed'
    : `OCR ${ocrCompletedCount} / ${ocrAttemptedCount} pages · ${confidence(result?.extraction.ocr_average_confidence)}`
  const availableFieldCount = result?.parsed.field_summary?.available_count
    ?? Object.values(result?.parsed.field_evidence ?? {}).filter(
      (item) => item.validation_status === 'available' && item.field_name !== 'ocr_confidence',
    ).length
  const businessFieldCount = result?.parsed.field_summary?.business_field_count ?? 13
  const keyFieldsRecognized = result?.parsed.key_field_readiness?.status === 'key_fields_recognized'

  return (
    <section className="ap-vendor-capture">
      <div className="ap-capture-intro">
        <div>
          <span className="ap-kicker">PSS-007 · LOCAL DOCUMENT EVIDENCE</span>
          <h3>Vendor Invoice Dataset &amp; OCR</h3>
          <p>
            Upload a PDF, preserve its SHA-256 original, extract native text, use local Tesseract only
            on insufficient pages, review field evidence, then synchronize the current evidence into AP.
          </p>
        </div>
        <div className="ap-capture-actions-column">
          <div className="ap-capture-actions">
            <button type="button" className="ap-primary-button" disabled={actionStatus === 'loading'} onClick={() => inputRef.current?.click()}>
              {actionStatus === 'loading' ? 'Working…' : 'Upload vendor invoice'}
            </button>
            <input ref={inputRef} hidden type="file" accept="application/pdf,.pdf" multiple onChange={uploadFile} />
            <button type="button" className="ap-secondary-button" disabled={datasetStatus === 'loading'} onClick={() => void loadDataset()}>
              {datasetStatus === 'loading' ? 'Refreshing…' : 'Refresh dataset'}
            </button>
          </div>
          <div
            className={`ap-capture-dropzone${isDragActive ? ' is-active' : ''}`}
            onDragEnter={handleDragEnter}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            <span>Drag and drop one or more PDF files here to upload them all at once</span>
          </div>
        </div>
      </div>

      <div className="ap-control-boundary">
        Extraction is analytical document evidence. It never approves an invoice, authorizes payment,
        posts to the ledger, or writes to ERP. No external AI service receives the document.
      </div>

      {actionError && <div className="ap-capture-message is-error">{actionError}</div>}
      {actionMessage && <div className={`ap-capture-message is-${actionTone}`}>{actionMessage}</div>}
      {syncResult && (
        <div className="ap-capture-message is-success">
          AP sync: imported {syncResult.imported_count}, updated {syncResult.updated_count}, unchanged {syncResult.unchanged_count}.
        </div>
      )}

      {datasetStatus === 'loading' && (
        <div className="ap-loading" role="status"><span className="ap-spinner" /><div><strong>Loading vendor invoice dataset</strong><p>Reading preserved Document Intelligence jobs and current states…</p></div></div>
      )}
      {datasetStatus === 'error' && (
        <div className="ap-capture-message is-error"><span>{datasetError}</span><button type="button" onClick={() => void loadDataset()}>Retry</button></div>
      )}
      {datasetStatus === 'success' && jobs.length === 0 && (
        <div className="ap-empty-state"><strong>No vendor invoice documents are registered.</strong><p>Upload the first governed PDF. ETOP will not create a sample or placeholder invoice.</p></div>
      )}

      {jobs.length > 0 && (
        <div className="ap-capture-layout">
          <aside className="ap-capture-dataset" aria-label="Vendor invoice dataset">
            <header><strong>Preserved invoice dataset</strong><span>{jobs.length} of {datasetTotal} document{datasetTotal === 1 ? '' : 's'}</span></header>
            {jobs.map((job) => (
              <button type="button" key={job.job_id} className={job.job_id === selectedJobId ? 'is-selected' : ''} onClick={() => selectJob(job.job_id)}>
                <span><strong>{job.original_file_name}</strong><small>{formatDateTime(job.created_at)} · {fileSize(job.file_size_bytes)}</small></span>
                <span className={`ap-capture-status is-${job.status}`}>{job.status.replaceAll('_', ' ')}</span>
                {job.duplicate_of_job_id && <em>Exact bytes also registered in {job.duplicate_of_job_id}</em>}
              </button>
            ))}
            {jobs.length < datasetTotal && (
              <button
                type="button"
                className="ap-secondary-button ap-dataset-load-more"
                disabled={datasetLoadingMore}
                onClick={() => void loadDataset(undefined, jobs.length, true)}
              >
                {datasetLoadingMore ? 'Loading more…' : 'Load older invoices'}
              </button>
            )}
          </aside>

          <div className="ap-capture-detail">
            {detailStatus === 'loading' && (
              <div className="ap-loading" role="status"><span className="ap-spinner" /><div><strong>Loading extraction evidence</strong><p>Reading current result, review history, and immutable runs…</p></div></div>
            )}
            {detailStatus === 'error' && <div className="ap-capture-message is-error">{detailError}</div>}
            {detailStatus === 'success' && selectedJob && (
              <>
                <section className="ap-panel ap-capture-source">
                  <div className="ap-panel-heading"><div><span className="ap-kicker">Preserved source</span><h3>{selectedJob.original_file_name}</h3></div><a className="ap-secondary-button" href={getAPVendorInvoiceFileUrl(selectedJob.job_id)} target="_blank" rel="noreferrer">Open original PDF</a></div>
                  <dl>
                    <div><dt>SHA-256</dt><dd>{selectedJob.source_sha256 ?? 'Unavailable for legacy upload'}</dd></div>
                    <div><dt>Current state</dt><dd>{selectedJob.status.replaceAll('_', ' ')}</dd></div>
                    <div><dt>Content classification confidence</dt><dd>{selectedJob.confidence > 0 ? confidence(selectedJob.confidence) : 'Unavailable'} · operator-constrained parser selection</dd></div>
                    <div><dt>Job</dt><dd>{selectedJob.job_id}</dd></div>
                  </dl>
                  <p>{selectedJob.message}</p>
                </section>

                {selectedJob.status === 'failed' && !result && (
                  <div className="ap-capture-message is-error">
                    <span>The original remains preserved, but no current extraction is available. Correct transient local processing problems and retry; corrupt or encrypted PDFs require a supported replacement.</span>
                    <button type="button" onClick={() => void reprocess()} disabled={actionStatus === 'loading'}>Retry processing</button>
                  </div>
                )}

                {result && (
                  <>
                    <section className="ap-panel">
                      <div className="ap-panel-heading"><div><span className="ap-kicker">Current processing run</span><h3>Parser &amp; OCR evidence</h3></div><div className="ap-capture-heading-actions"><span className={`ap-capture-status ${keyFieldsRecognized ? 'is-completed' : 'is-review'}`}>{keyFieldsRecognized ? 'Key fields recognized' : 'Key fields need review'}</span><button type="button" className="ap-secondary-button" onClick={() => void reprocess()} disabled={actionStatus === 'loading'}>Append reprocess run</button></div></div>
                      <div className="ap-capture-run-summary">
                        <article><span>Run</span><strong>#{result.processing_run_number ?? '—'}</strong><small>{result.processing_run_id ?? 'Legacy current result'}</small></article>
                        <article><span>Parser</span><strong>{result.parsed.parser ?? 'Unavailable'}</strong><small>{result.parsed.parser_version ?? 'Version unavailable'}</small></article>
                        <article><span>Text extraction</span><strong>{textSourceLabel}</strong><small>{ocrStatusLabel}</small></article>
                        <article><span>Field coverage</span><strong>{availableFieldCount} / {businessFieldCount}</strong><small>{result.parsed.field_summary?.message ?? result.parsed.key_field_readiness?.message ?? 'Human review remains required.'}</small></article>
                      </div>
                      {(result.parsed.validation?.errors?.length || result.parsed.validation?.warnings?.length) ? (
                        <div className="ap-capture-validation">
                          {result.parsed.validation.errors?.map((item) => <p className="is-error" key={item}>{item}</p>)}
                          {result.parsed.validation.warnings?.map((item) => <p key={item}>{item}</p>)}
                        </div>
                      ) : null}
                    </section>

                    <section className="ap-panel">
                      <div className="ap-panel-heading"><div><span className="ap-kicker">Field-level provenance</span><h3>Extracted invoice evidence</h3></div><span className="ap-capture-status is-review">Human review required</span></div>
                      <div className="ap-capture-fields">
                        {fieldEvidence.map(({ fieldName, evidence }) => {
                          const candidates = distinctEvidenceCandidates(evidence)
                          return (
                            <article key={fieldName}>
                              <div><strong>{FIELD_LABELS[fieldName]}</strong><span className={`ap-capture-field-state is-${evidence.validation_status}`}>{evidence.validation_status}</span></div>
                              <b>{displayValue(evidence.value) || 'Unavailable'}</b>
                              <small>Confidence {confidence(evidence.confidence)} · {evidence.authority}</small>
                              <small>{evidence.page ? `Page ${evidence.page} · ` : ''}{evidence.location ?? 'Location unavailable'}</small>
                              <small>{evidence.source} · {evidence.pairing_method?.replaceAll('_', ' ') ?? 'pairing unavailable'} · {evidence.rule_version ?? 'Rule version unavailable'}</small>
                              {evidence.observation_count && evidence.observation_count > 1 ? <em>{evidence.observation_count} corroborating observations retained</em> : null}
                              {evidence.candidate_count && evidence.candidate_count > 1 ? <em>{evidence.candidate_count} conflicting distinct candidates retained</em> : null}
                              {candidates.length > 0 && (
                                <details className="ap-capture-candidates">
                                  <summary>Review {candidates.length} distinct retained candidate{candidates.length === 1 ? '' : 's'}</summary>
                                  <ol>
                                    {candidates.map((candidate, index) => (
                                      <li key={`${displayValue(candidate.value)}-${index}`}>
                                        <strong>{displayValue(candidate.value)}</strong>
                                        <small>{candidate.page ? `Page ${candidate.page} · ` : ''}{candidate.location ?? 'Location unavailable'}</small>
                                        <small>{candidate.source ?? candidate.source_method ?? 'Source unavailable'} · Confidence {confidence(candidate.confidence)}</small>
                                      </li>
                                    ))}
                                  </ol>
                                </details>
                              )}
                            </article>
                          )
                        })}
                      </div>
                    </section>

                    <section className="ap-panel ap-capture-review">
                      <div className="ap-panel-heading"><div><span className="ap-kicker">Existing Document Intelligence review store</span><h3>Review or correct extraction</h3></div><span>{review?.history.length ?? 0} prior review record{review?.history.length === 1 ? '' : 's'}</span></div>
                      <div className="ap-capture-review-grid">
                        {fieldEvidence.filter(({ fieldName }) => fieldName !== 'ocr_confidence').map(({ fieldName }) => {
                          const isUnavailable = unavailableFields.includes(fieldName)
                          return (
                            <div className={`ap-capture-review-field ${isUnavailable ? 'is-unavailable' : ''}`} key={fieldName}>
                              <label>
                                <span>{FIELD_LABELS[fieldName]}</span>
                                {fieldName === 'vendor_number' ? (
                                  <APVendorNumberSearchField
                                    value={correctedFields.vendor_number ?? ''}
                                    disabled={isUnavailable}
                                    onChangeText={(nextValue) => setCorrectedFields((current) => ({ ...current, vendor_number: nextValue }))}
                                    onSelect={(vendorNumber, vendorName) => setCorrectedFields((current) => ({
                                      ...current,
                                      vendor_number: vendorNumber,
                                      ...(vendorName ? { vendor_name: vendorName } : {}),
                                    }))}
                                  />
                                ) : (
                                  <input
                                    value={correctedFields[fieldName] ?? ''}
                                    placeholder={isUnavailable ? 'Marked unavailable' : undefined}
                                    disabled={isUnavailable}
                                    onChange={(event) => setCorrectedFields((current) => ({ ...current, [fieldName]: event.target.value }))}
                                  />
                                )}
                              </label>
                              {fieldName === 'vendor_number' && (
                                <GLCodingSuggestionsHint
                                  status={glSuggestionsStatus}
                                  suggestions={glSuggestions}
                                />
                              )}
                              <button
                                type="button"
                                className="ap-capture-unavailable-button"
                                aria-pressed={isUnavailable}
                                onClick={() => setFieldUnavailable(fieldName, !isUnavailable)}
                              >
                                {isUnavailable ? 'Restore extracted value' : 'Mark unavailable'}
                              </button>
                              {isUnavailable && <small>Machine and source-text fallback values will be suppressed during AP sync.</small>}
                            </div>
                          )
                        })}
                      </div>
                      <div className="ap-capture-review-meta">
                        <label><span>Reviewer</span><input value={reviewer} maxLength={200} onChange={(event) => setReviewer(event.target.value)} /></label>
                        <label><span>Extraction review outcome</span><select value={reviewOutcome} onChange={(event) => setReviewOutcome(event.target.value as typeof reviewOutcome)}><option value="approved">Extraction evidence reviewed</option><option value="needs_correction">More correction required</option><option value="needs_learning">Correction saved for learning</option></select></label>
                        <label className="is-wide"><span>Review notes</span><textarea value={notes} maxLength={10000} rows={3} onChange={(event) => setNotes(event.target.value)} /></label>
                      </div>
                      <div className="ap-capture-review-actions">
                        <button type="button" className="ap-primary-button" onClick={() => void saveReview()} disabled={actionStatus === 'loading'}>Save extraction review</button>
                        <small>“Extraction evidence reviewed” is not invoice approval, coding acceptance, payment authorization, or posting.</small>
                      </div>
                    </section>

                    <section className="ap-panel">
                      <div className="ap-panel-heading"><div><span className="ap-kicker">Append-only provenance</span><h3>Processing run history</h3></div><span>{runs.length} run{runs.length === 1 ? '' : 's'}</span></div>
                      <div className="ap-capture-runs">
                        {runs.map((run) => (
                          <article key={run.processing_run_id}><div><strong>Run #{run.run_number} · {run.status}</strong><span>{formatDateTime(run.completed_at)}</span></div><small>{run.processor_version} · {run.parser ?? 'Parser unavailable'} {run.parser_version ?? ''}</small><p>{run.message}</p></article>
                        ))}
                      </div>
                    </section>

                    <section className="ap-panel ap-capture-sync">
                      <div><span className="ap-kicker">AP evidence projection</span><h3>Synchronize and reopen</h3><p>The sync is idempotent. Changed corrections append an AP evidence revision; identical evidence is a no-op.</p></div>
                      <div>
                        <button type="button" className="ap-primary-button" disabled={actionStatus === 'loading' || !extractionReviewed} onClick={() => void syncCurrentEvidence()}>Sync reviewed extraction</button>
                        <button type="button" className="ap-secondary-button" disabled={!syncResult} onClick={() => onOpenImportedEvidence(selectedJob.job_id)}>Reopen in Invoice Intelligence</button>
                      </div>
                      {!extractionReviewed && <small>Save “Extraction evidence reviewed” before using this controlled sync action.</small>}
                      {review?.review.status === 'approved' && !extractionReviewed && (
                        <small>The saved review belongs to a prior processing run and cannot authorize synchronization of the current extraction.</small>
                      )}
                    </section>
                  </>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
