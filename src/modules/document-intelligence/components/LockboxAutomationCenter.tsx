import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

import {
  downloadLockboxExport,
  downloadLockboxReviewQueueExport,
  downloadReviewedLockboxExport,
  getLockboxResult,
  getLockboxReview,
  processLockboxJob,
  uploadLockboxGroundTruth,
} from '../api'

import type {
  DocumentJob,
  DurableLockboxPreparation,
  LockboxProcessingResult,
  TrainingSession,
  LockboxReviewResult,
} from '../types'

import LockboxReviewWorkspace from './LockboxReviewWorkspace'
import type {
  PreparedLockboxTransaction,
} from './lockboxPreparation'
import {
  durableLockboxExceptionReasons,
  durableLockboxTransactions,
  governedLockboxReviewIsReady,
  governedPreparationIsFinal,
  loadCurrentDurableLockboxPreparation,
  projectGovernedLockboxReview,
  startAndWaitForDurableLockboxPreparation,
} from './durableLockboxPreparation'
import {
  primaryLockboxReasonCode,
  transactionNeedsProfessionalReview,
} from './lockboxReviewQueue'

const LAST_LOCKBOX_JOB_KEY = 'etop.document-intelligence.last-lockbox-job'
const PNC_COMPARISON_TRAINING_VISIBLE = false

type ReviewQueueFilter =
  | 'all'
  | 'balanced'
  | 'exceptions'
  | 'corrected'
  | 'held'
  | 'approved'

function transactionMatchesPrimaryReason(
  preparation: DurableLockboxPreparation | null,
  transactionId: string,
  reasonCode: string,
): boolean {
  const durable = durableLockboxTransactions(preparation).find(
    (transaction) => transaction.transaction_id === transactionId,
  )
  return primaryLockboxReasonCode(durable) === reasonCode
}

type Props = {
  jobs: DocumentJob[]
  isUploading?: boolean
  onUploadPdf?: (file: File) => Promise<DocumentJob>
  onRefresh?: () => Promise<void>
}

function money(value: number | null) {
  if (value === null) return '—'
  return value.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
  })
}

export default function LockboxAutomationCenter({
  jobs,
  isUploading = false,
  onUploadPdf,
  onRefresh,
}: Props) {
  const [selectedJobId, setSelectedJobId] = useState('')
  const [result, setResult] = useState<LockboxProcessingResult | null>(null)
  const [training, setTraining] = useState<TrainingSession | null>(null)
  const [review, setReview] = useState<LockboxReviewResult | null>(null)
  const [reviewTransactionId, setReviewTransactionId] = useState('')
  const [preparedTransactions, setPreparedTransactions] = useState<
    Record<string, PreparedLockboxTransaction>
  >({})
  const [durablePreparation, setDurablePreparation] = useState<
    DurableLockboxPreparation | null
  >(null)
  const [preparingTransactionId, setPreparingTransactionId] = useState('')
  const [preparationMessage, setPreparationMessage] = useState('')
  const [reviewFilter, setReviewFilter] =
    useState<ReviewQueueFilter>('exceptions')
  const [reviewReasonFilter, setReviewReasonFilter] = useState('')
  const [isLoadingReview, setIsLoadingReview] = useState(false)
  const [groundTruthFile, setGroundTruthFile] = useState<File | null>(null)
  const [isProcessing, setIsProcessing] = useState(false)
  const [isComparing, setIsComparing] = useState(false)
  const [isExportingQueue, setIsExportingQueue] = useState(false)
  const [isExportingParserOriginal, setIsExportingParserOriginal] = useState(false)
  const [isExportingReviewed, setIsExportingReviewed] = useState(false)
  const [isUploadingPdf, setIsUploadingPdf] = useState(false)
  const [isRestoring, setIsRestoring] = useState(false)
  const [processedJobIds, setProcessedJobIds] = useState<Set<string>>(
    () => new Set(),
  )
  const [errorMessage, setErrorMessage] = useState('')
  const pdfInputRef = useRef<HTMLInputElement | null>(null)
  const groundTruthInputRef = useRef<HTMLInputElement | null>(null)
  const recoveryAttemptedRef = useRef(false)
  const reviewQueueRef = useRef<HTMLElement | null>(null)
  const preparedTransactionsRef = useRef<
    Record<string, PreparedLockboxTransaction>
  >({})

  const pdfJobs = useMemo(
    () => jobs.filter((job) => job.original_file_name?.toLowerCase().endsWith('.pdf')),
    [jobs],
  )

  const selectedJob = pdfJobs.find((job) => job.job_id === selectedJobId) ?? null

  const clearPreparedTransactions = useCallback(() => {
    preparedTransactionsRef.current = {}
    setPreparedTransactions({})
    setPreparationMessage('')
    setPreparingTransactionId('')
    setDurablePreparation(null)
  }, [])

  const preparationProgress = useCallback((
    preparation: DurableLockboxPreparation,
  ) => {
    setDurablePreparation(preparation)
    setPreparingTransactionId(
      governedPreparationIsFinal(preparation) ? '' : 'governed-preparation',
    )
    setPreparationMessage(
      governedPreparationIsFinal(preparation)
        ? (
          `Governed generation ${preparation.preparation_generation} `
          + `reconciled ${preparation.expected_count} transaction(s): `
          + `${preparation.balanced_count} balanced recommendation(s), `
          + `${preparation.exception_count} professional review exception(s).`
        )
        : (
          `Governed preparation ${preparation.terminal_count} of `
          + `${preparation.expected_count} transaction(s)…`
        ),
    )
  }, [])

  const applyGovernedPreparation = useCallback((
    nextReview: LockboxReviewResult,
    preparation: DurableLockboxPreparation,
  ): LockboxReviewResult => {
    const projected = projectGovernedLockboxReview(nextReview, preparation)
    preparedTransactionsRef.current = projected.preparedTransactions
    setPreparedTransactions(projected.preparedTransactions)
    setDurablePreparation(preparation)
    setReview(projected.review)
    return projected.review
  }, [])

  const prepareTransactionForReview = useCallback(async (
    nextReview: LockboxReviewResult,
    requestedTransactionId = '',
  ): Promise<PreparedLockboxTransaction> => {
    const transaction = (
      nextReview.transactions.find(
        (item) => item.transaction_id === requestedTransactionId,
      )
      || nextReview.transactions.find(transactionNeedsProfessionalReview)
      || nextReview.transactions[0]
    )

    if (!transaction) {
      throw new Error('No lockbox transaction is available for review.')
    }

    const prepared = preparedTransactionsRef.current[
      transaction.transaction_id
    ]
    if (!prepared) {
      throw new Error(
        'The governed preparation does not contain this transaction.',
      )
    }
    setPreparationMessage(prepared.message)
    return prepared
  }, [])

  const restoreProcessedJob = useCallback(async (
    jobId: string,
    openWorkspace = false,
    quiet = false,
  ) => {
    if (!jobId) return false
    setIsRestoring(true)
    if (!quiet) setErrorMessage('')

    try {
      const processed = await getLockboxResult(jobId)
      let nextReview: LockboxReviewResult | null = null
      try {
        nextReview = await getLockboxReview(jobId)
      } catch {
        nextReview = null
      }

      setSelectedJobId(jobId)
      setResult(processed)
      setReview(nextReview)
      setTraining(null)
      let governed: DurableLockboxPreparation | null = null
      if (nextReview) {
        try {
          governed = await loadCurrentDurableLockboxPreparation(
            jobId,
            preparationProgress,
          )
          nextReview = applyGovernedPreparation(nextReview, governed)
        } catch {
          governed = null
          preparedTransactionsRef.current = {}
          setPreparedTransactions({})
          setDurablePreparation(null)
          setPreparationMessage(
            'No complete current-rule governed preparation is available yet.',
          )
        }
      }
      setProcessedJobIds((current) => {
        const next = new Set(current)
        next.add(jobId)
        return next
      })
      window.localStorage.setItem(LAST_LOCKBOX_JOB_KEY, jobId)

      if (openWorkspace) {
        if (!nextReview) {
          throw new Error(
            'The saved OCR result opened, but its review state is unavailable.',
          )
        }
        if (!governed) {
          governed = await startAndWaitForDurableLockboxPreparation(
            jobId,
            preparationProgress,
          )
          nextReview = applyGovernedPreparation(nextReview, governed)
        }
        const prepared = await prepareTransactionForReview(
          nextReview,
          '',
        )
        setReviewTransactionId(prepared.transactionId)
      }
      return true
    } catch (error) {
      setResult(null)
      setReview(null)
      if (!quiet) {
        setErrorMessage(
          error instanceof Error
            ? `The PDF is available, but no saved lockbox OCR result could be opened. ${error.message}`
            : 'The PDF is available, but no saved lockbox OCR result could be opened.',
        )
      }
      return false
    } finally {
      setPreparingTransactionId('')
      setIsRestoring(false)
    }
  }, [
    applyGovernedPreparation,
    preparationProgress,
    prepareTransactionForReview,
  ])

  useEffect(() => {
    if (recoveryAttemptedRef.current || pdfJobs.length === 0) return
    recoveryAttemptedRef.current = true

    const savedJobId = window.localStorage.getItem(LAST_LOCKBOX_JOB_KEY)
    const recoveryCandidates = [...pdfJobs].sort((left, right) => {
      if (left.job_id === savedJobId) return -1
      if (right.job_id === savedJobId) return 1
      if (left.status === 'completed' && right.status !== 'completed') return -1
      if (right.status === 'completed' && left.status !== 'completed') return 1
      return (
        new Date(right.updated_at).getTime()
        - new Date(left.updated_at).getTime()
      )
    })

    const timer = window.setTimeout(() => {
      void (async () => {
        for (const job of recoveryCandidates) {
          setSelectedJobId(job.job_id)
          if (await restoreProcessedJob(job.job_id, false, true)) {
            return
          }
        }
        setSelectedJobId(recoveryCandidates[0]?.job_id || '')
      })()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [pdfJobs, restoreProcessedJob])

  const selectExistingJob = async (jobId: string) => {
    setSelectedJobId(jobId)
    setReviewFilter('exceptions')
    setReviewReasonFilter('')
    setResult(null)
    setTraining(null)
    setReview(null)
    setGroundTruthFile(null)
    setReviewTransactionId('')
    clearPreparedTransactions()
    setErrorMessage('')
    if (groundTruthInputRef.current) groundTruthInputRef.current.value = ''
    if (!jobId) {
      window.localStorage.removeItem(LAST_LOCKBOX_JOB_KEY)
      return
    }

    window.localStorage.setItem(LAST_LOCKBOX_JOB_KEY, jobId)
    // Lockbox processing persists a separate result. Older jobs can therefore
    // still say "uploaded" even though their OCR result and review are saved.
    // Probe the durable lockbox result instead of trusting the generic status.
    await restoreProcessedJob(jobId, false, true)
  }

  const uploadPdf = async (file: File | undefined) => {
    if (!file || !onUploadPdf) return
    setIsUploadingPdf(true)
    setErrorMessage('')
    setResult(null)
    setTraining(null)
    setReview(null)
    setReviewFilter('exceptions')
    setReviewReasonFilter('')
    clearPreparedTransactions()

    try {
      const existingJobs = [...pdfJobs]
        .sort((left, right) => (
          new Date(right.created_at).getTime()
          - new Date(left.created_at).getTime()
        ))
        .filter((job) => (
          job.original_file_name.toLowerCase() === file.name.toLowerCase()
          && job.file_size_bytes === file.size
        ))

      if (existingJobs.length > 0) {
        for (const existingJob of existingJobs) {
          setSelectedJobId(existingJob.job_id)
          if (
            await restoreProcessedJob(
              existingJob.job_id,
              true,
              true,
            )
          ) {
            return
          }
        }

        const existingJob = existingJobs[0]
        setSelectedJobId(existingJob.job_id)
        window.localStorage.setItem(
          LAST_LOCKBOX_JOB_KEY,
          existingJob.job_id,
        )
        return
      }

      const job = await onUploadPdf(file)
      setSelectedJobId(job.job_id)
      window.localStorage.setItem(LAST_LOCKBOX_JOB_KEY, job.job_id)
      await onRefresh?.()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to upload the PNC PDF.')
    } finally {
      setIsUploadingPdf(false)
      if (pdfInputRef.current) pdfInputRef.current.value = ''
    }
  }

  const processSelected = async () => {
    if (!selectedJobId) {
      setErrorMessage('Upload or select a PNC lockbox PDF first.')
      return
    }
    setIsProcessing(true)
    setErrorMessage('')
    setTraining(null)
    setReviewFilter('exceptions')
    setReviewReasonFilter('')
    clearPreparedTransactions()
    try {
      const processed = await processLockboxJob(selectedJobId)
      const initialReview = await getLockboxReview(selectedJobId)
      setResult(processed)
      setReview(initialReview)
      const governed = await startAndWaitForDurableLockboxPreparation(
        selectedJobId,
        preparationProgress,
      )
      applyGovernedPreparation(initialReview, governed)
      setProcessedJobIds((current) => {
        const next = new Set(current)
        next.add(selectedJobId)
        return next
      })
      window.localStorage.setItem(LAST_LOCKBOX_JOB_KEY, selectedJobId)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to process the lockbox.')
    } finally {
      setPreparingTransactionId('')
      setIsProcessing(false)
    }
  }

  const openReview = async (transactionId = '') => {
    if (!selectedJobId) return
    setIsLoadingReview(true)
    setErrorMessage('')
    try {
      let nextReview = await getLockboxReview(selectedJobId)
      let governed = durablePreparation
      if (!governedPreparationIsFinal(governed)) {
        governed = await startAndWaitForDurableLockboxPreparation(
          selectedJobId,
          preparationProgress,
        )
      }
      if (!governed) {
        throw new Error('Governed Lockbox preparation is unavailable.')
      }
      nextReview = applyGovernedPreparation(nextReview, governed)
      const prepared = await prepareTransactionForReview(
        nextReview,
        transactionId,
      )
      setReviewTransactionId(prepared.transactionId)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to open lockbox review.')
    } finally {
      setIsLoadingReview(false)
    }
  }

  const compareGroundTruth = async () => {
    if (!selectedJobId || !groundTruthFile) {
      setErrorMessage('Select a processed PDF and its approved PNC Excel workbook.')
      return
    }
    setIsComparing(true)
    setErrorMessage('')
    try {
      setTraining(await uploadLockboxGroundTruth(selectedJobId, groundTruthFile))
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Unable to compare the PNC workbook.')
    } finally {
      setIsComparing(false)
    }
  }

  const exceptionTransactions = training?.transactions.filter(
    (transaction) => !transaction.balanced,
  ) ?? []
  const reviewTransactions = review?.transactions ?? result?.transactions ?? []
  const unresolvedTransactions = reviewTransactions.filter(
    transactionNeedsProfessionalReview,
  )
  const heldTransactions = reviewTransactions.filter(
    (transaction) => transaction.status === 'held',
  )
  const correctedTransactions = reviewTransactions.filter(
    (transaction) => transaction.status === 'corrected',
  )
  const approvedTransactions = reviewTransactions.filter(
    (transaction) => transaction.status === 'approved',
  )
  const actionableReasonCounts = new Map<string, number>()
  unresolvedTransactions.forEach((transaction) => {
    const durable = durableLockboxTransactions(durablePreparation).find(
      (item) => item.transaction_id === transaction.transaction_id,
    )
    const code = primaryLockboxReasonCode(durable)
    if (code) {
      actionableReasonCounts.set(
        code,
        (actionableReasonCounts.get(code) ?? 0) + 1,
      )
    }
  })
  const actionableReasons = durableLockboxExceptionReasons(
    durablePreparation,
  ).map((reason) => ({
    ...reason,
    count: actionableReasonCounts.get(reason.code) ?? 0,
  }))
  const visibleTransactions = reviewTransactions.filter((transaction) => {
    if (reviewReasonFilter) {
      return transactionNeedsProfessionalReview(transaction)
      && transactionMatchesPrimaryReason(
        durablePreparation,
        transaction.transaction_id,
        reviewReasonFilter,
      )
    }
    if (reviewFilter === 'all') return true
    if (reviewFilter === 'balanced') {
      return transaction.status === 'balanced'
    }
    if (reviewFilter === 'approved') {
      return transaction.status === 'approved'
    }
    if (reviewFilter === 'corrected') {
      return transaction.status === 'corrected'
    }
    if (reviewFilter === 'held') {
      return transaction.status === 'held'
    }
    return unresolvedTransactions.some(
      (item) => item.transaction_id === transaction.transaction_id,
    )
  })
  const effectiveReviewCount = unresolvedTransactions.length
  const heldCount = review?.held_count ?? heldTransactions.length
  const correctedCount = (
    review?.corrected_count ?? correctedTransactions.length
  )
  const approvedCount = review?.approved_count ?? approvedTransactions.length
  const activeReason = reviewReasonFilter
    ? actionableReasons.find(
      (reason) => reason.code === reviewReasonFilter,
    ) ?? null
    : null
  const reviewQueueLabel = activeReason
    ? activeReason.label
    : reviewFilter === 'all'
      ? 'All transactions'
      : reviewFilter === 'balanced'
        ? 'Prepared & Balanced'
        : reviewFilter === 'approved'
          ? 'Approved'
          : reviewFilter === 'corrected'
            ? 'Saved Corrections'
            : reviewFilter === 'held'
              ? 'Held'
              : 'Needs Review'

  const openTransactionQueue = (
    filter: ReviewQueueFilter,
    reasonCode = '',
  ) => {
    setReviewFilter(filter)
    setReviewReasonFilter(reasonCode)
    window.requestAnimationFrame(() => {
      reviewQueueRef.current?.scrollIntoView({
        behavior: 'smooth',
        block: 'start',
      })
    })
  }

  const openReasonReview = (reasonCode: string) => {
    const firstTransaction = reviewTransactions.find((transaction) => (
      transactionNeedsProfessionalReview(transaction)
      && transactionMatchesPrimaryReason(
        durablePreparation,
        transaction.transaction_id,
        reasonCode,
      )
    ))

    openTransactionQueue('exceptions', reasonCode)
    if (firstTransaction) {
      void openReview(firstTransaction.transaction_id)
    }
  }

  const exportVisibleQueue = async () => {
    if (!selectedJobId || visibleTransactions.length === 0) return
    setIsExportingQueue(true)
    setErrorMessage('')
    try {
      await downloadLockboxReviewQueueExport(selectedJobId, {
        transaction_ids: visibleTransactions.map(
          (transaction) => transaction.transaction_id,
        ),
        queue_label: reviewQueueLabel,
        reason_code: reviewReasonFilter,
      })
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to export the transaction review queue.',
      )
    } finally {
      setIsExportingQueue(false)
    }
  }

  const exportOriginalParserResult = async () => {
    if (!selectedJobId) return
    setIsExportingParserOriginal(true)
    setErrorMessage('')
    try {
      await downloadLockboxExport(selectedJobId)
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to export the original parser result.',
      )
    } finally {
      setIsExportingParserOriginal(false)
    }
  }

  const exportReviewedResult = async () => {
    if (!selectedJobId) return
    setIsExportingReviewed(true)
    setErrorMessage('')
    try {
      await downloadReviewedLockboxExport(selectedJobId)
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to export the reviewed PNC workbook.',
      )
    } finally {
      setIsExportingReviewed(false)
    }
  }

  const governedReviewReady = governedLockboxReviewIsReady(
    durablePreparation,
    preparedTransactions,
  )
  const preparationIncomplete = Boolean(result && !governedReviewReady)
  const preparationHasStarted = Boolean(durablePreparation)

  const currentStep = PNC_COMPARISON_TRAINING_VISIBLE && training
    ? 5
    : result
      ? preparationIncomplete
        ? 2
        : effectiveReviewCount > 0 || heldCount > 0
          ? 3
          : 4
      : selectedJobId
        ? 2
        : 1
  const heroStatus = result
    ? preparationIncomplete
      ? preparationHasStarted
        ? 'Preparation Incomplete'
        : 'Ready to Prepare'
      : effectiveReviewCount > 0
        ? 'Review Required'
        : heldCount > 0
          ? 'Held Work Remaining'
          : 'Ready to Export'
    : isRestoring
      ? 'Opening Saved Result'
      : selectedJobId
        ? 'Ready to Process'
        : 'Waiting for PDF'

  return (
    <div className="lockbox-center-v2">
      <section className="lockbox-hero">
        <div>
          <span>PNC LOCKBOX AUTOMATION</span>
          <h2>Upload, process, review, and export in one workflow.</h2>
          <p>Saved reviewer corrections continue improving OCR and document extraction accuracy.</p>
        </div>
        <div className="lockbox-hero-status">
          <span className={
            result
            && !preparationIncomplete
            && effectiveReviewCount === 0
            && heldCount === 0
              ? 'ready'
              : ''
          } />
          <div><strong>{heroStatus}</strong><small>{selectedJob?.original_file_name ?? 'No lockbox selected'}</small></div>
        </div>
      </section>

      <section
        className={`lockbox-stepper ${
          PNC_COMPARISON_TRAINING_VISIBLE ? '' : 'four-step'
        }`}
        aria-label="Lockbox workflow"
      >
        {(PNC_COMPARISON_TRAINING_VISIBLE
          ? ['Upload', 'Process', 'Review', 'Export', 'Train']
          : ['Upload', 'Process', 'Review', 'Export']
        ).map((label, index) => {
          const step = index + 1
          return <div key={label} className={step < currentStep ? 'complete' : step === currentStep ? 'active' : ''}><b>{step < currentStep ? '✓' : step}</b><span>{label}</span></div>
        })}
      </section>

      {errorMessage && <div className="ed-banner error">{errorMessage}</div>}

      <section className="lockbox-workflow-grid">
        <article className="ed-card lockbox-workflow-card">
          <header><span>1</span><div><strong>Upload PNC PDF</strong><small>Start a new lockbox or select one already uploaded</small></div></header>
          <button type="button" className="lockbox-drop-zone" onClick={() => pdfInputRef.current?.click()} disabled={!onUploadPdf || isUploadingPdf || isUploading}>
            <b>⇧</b>
            <strong>{isUploadingPdf || isUploading ? 'Uploading…' : 'Choose PNC PDF'}</strong>
            <span>PDF files stay on this computer</span>
          </button>
          <input ref={pdfInputRef} hidden type="file" accept="application/pdf,.pdf" onChange={(event) => void uploadPdf(event.target.files?.[0])} />
          <label className="lockbox-existing-select">
            Or select an existing PDF
            <select value={selectedJobId} onChange={(event) => void selectExistingJob(event.target.value)}>
              <option value="">Select a PDF job</option>
              {pdfJobs.map((job) => <option key={job.job_id} value={job.job_id}>{job.original_file_name} · {processedJobIds.has(job.job_id) ? 'processed' : job.status}</option>)}
            </select>
          </label>
        </article>

        <article className="ed-card lockbox-workflow-card">
          <header><span>2</span><div><strong>Process Lockbox</strong><small>Run OCR, resolve ERP customers, prepare allocations, and save the exception queue</small></div></header>
          <div className="lockbox-action-body">
            <div className="lockbox-selected-file"><span>Selected file</span><strong>{selectedJob?.original_file_name ?? 'None selected'}</strong><small>{selectedJob ? `${(selectedJob.file_size_bytes / 1048576).toFixed(2)} MB · ${result || processedJobIds.has(selectedJob.job_id) ? 'processed' : selectedJob.status}` : 'Upload or select a PDF first'}</small></div>
            {(result || processedJobIds.has(selectedJobId)) && !preparationIncomplete && (
              <button type="button" className="secondary lockbox-large-action" onClick={() => void restoreProcessedJob(selectedJobId, true)} disabled={isRestoring || isProcessing}>
                {isRestoring ? 'Opening Saved OCR…' : result ? 'Reopen Saved Review' : 'Open Processed Lockbox'}
              </button>
            )}
            <button
              type="button"
              className="primary lockbox-large-action"
              onClick={() => void (
                preparationIncomplete
                  ? openReview()
                  : processSelected()
              )}
              disabled={
                isProcessing
                || isRestoring
                || isLoadingReview
                || !selectedJobId
              }
            >
              {isProcessing
                ? preparingTransactionId
                  ? 'Preparing ERP & Allocations…'
                  : 'Processing OCR…'
                : isLoadingReview && preparationIncomplete
                  ? preparationHasStarted
                    ? 'Resuming ERP & Allocations…'
                    : 'Starting ERP & Allocations…'
                  : preparationIncomplete
                    ? (
                      `${preparationHasStarted ? 'Resume' : 'Start'} `
                      + `ERP & Allocations `
                      + `(${durablePreparation?.terminal_count ?? 0}/`
                      + `${durablePreparation?.expected_count ?? result?.transaction_count ?? 0})`
                    )
                    : result
                      ? 'Reprocess PNC Lockbox'
                      : 'Process PNC Lockbox'}
            </button>
          </div>
        </article>

        <article className="ed-card lockbox-workflow-card">
          <header><span>3</span><div><strong>Review Exceptions</strong><small>Open the saved transactions that still require professional review</small></div></header>
          {result ? (
            <>
              <div className="lockbox-mini-metrics">
                <button type="button" onClick={() => openTransactionQueue('all')}>
                  <strong>{result.transaction_count}</strong><span>Transactions</span>
                </button>
                <button type="button" disabled={preparationIncomplete} onClick={() => openTransactionQueue('balanced')}>
                  <strong>{preparationIncomplete ? '—' : review?.balanced_count ?? durablePreparation?.balanced_count ?? 0}</strong><span>Prepared & Balanced</span>
                </button>
                <button type="button" disabled={preparationIncomplete} className={!preparationIncomplete && effectiveReviewCount > 0 ? 'warning' : ''} onClick={() => openTransactionQueue('exceptions')}>
                  <strong>{preparationIncomplete ? '—' : effectiveReviewCount}</strong>
                  <span>{preparationIncomplete ? 'Review Count Pending' : 'Needs Review'}</span>
                </button>
                <button type="button" disabled={preparationIncomplete} className={heldCount > 0 ? 'hold' : ''} onClick={() => openTransactionQueue('held')}>
                  <strong>{preparationIncomplete ? '—' : heldCount}</strong><span>Held</span>
                </button>
                <button type="button" disabled={preparationIncomplete} onClick={() => openTransactionQueue('corrected')}>
                  <strong>{preparationIncomplete ? '—' : correctedCount}</strong><span>Saved Corrections</span>
                </button>
                <button type="button" disabled={preparationIncomplete} onClick={() => openTransactionQueue('approved')}>
                  <strong>{preparationIncomplete ? '—' : approvedCount}</strong><span>Approved</span>
                </button>
              </div>
              <button
                type="button"
                className="primary lockbox-large-action"
                onClick={() => {
                  openTransactionQueue('exceptions', '')
                  void openReview()
                }}
                disabled={isLoadingReview || isProcessing || isRestoring}
              >
                {isLoadingReview
                  ? preparationIncomplete
                    ? 'Resuming Preparation…'
                    : 'Opening Saved Review…'
                  : preparationIncomplete
                    ? (
                      `${preparationHasStarted ? 'Resume' : 'Start'} `
                      + `ERP & Allocation Preparation `
                      + `(${durablePreparation?.terminal_count ?? 0}/`
                      + `${durablePreparation?.expected_count ?? result.transaction_count})`
                    )
                    : effectiveReviewCount > 0
                      ? `Open ${effectiveReviewCount} Review Exception${effectiveReviewCount === 1 ? '' : 's'}`
                      : 'Review Prepared Results'}
              </button>
              {preparationMessage && (
                <div className={`lockbox-preparation-status ${
                  preparingTransactionId ? 'working' : ''
                }`}>
                  {preparationMessage}
                </div>
              )}
              {!preparationIncomplete
                && durablePreparation
                && actionableReasons.length > 0
                && (
                  <div className="lockbox-preparation-reasons">
                    <strong>Governed exception reasons</strong>
                    {actionableReasons.map(
                      (reason) => (
                        <button
                          key={reason.code}
                          type="button"
                          disabled={
                            (reason.count ?? 0) === 0
                            || isLoadingReview
                            || isProcessing
                            || isRestoring
                          }
                          onClick={() => openReasonReview(reason.code)}
                        >
                          <span>{reason.label}</span>
                          <b>{reason.count ?? 0}</b>
                        </button>
                      ),
                    )}
                  </div>
                )}
            </>
          ) : <div className="lockbox-empty-step">{isRestoring ? 'Opening the saved OCR result and review…' : 'Process the selected PDF, or reopen a completed lockbox, to populate the review queue.'}</div>}
        </article>

        <article className="ed-card lockbox-workflow-card">
          <header><span>4</span><div><strong>Export PNC Excel</strong><small>Download the generated workbook after reviewing exceptions</small></div></header>
          <div className="lockbox-action-body">
            <div className="lockbox-selected-file"><span>Check total</span><strong>{result ? money(result.total_check_amount) : '—'}</strong><small>{result ? `${result.allocation_count} output rows` : 'No processed result'}</small></div>
            {result ? (
              <div className="lockbox-export-actions">
                <button
                  type="button"
                  className="ed-button-link secondary lockbox-large-action"
                  onClick={() => void exportOriginalParserResult()}
                  disabled={isExportingParserOriginal}
                >
                  {isExportingParserOriginal ? 'Exporting…' : 'Original Parser Export'}
                </button>
                {preparationIncomplete
                  || effectiveReviewCount > 0
                  || heldCount > 0 ? (
                  <button
                    type="button"
                    className="secondary lockbox-large-action"
                    disabled
                  >
                    {preparationIncomplete
                      ? 'Reviewed Export Pending Preparation'
                      : heldCount > 0 && effectiveReviewCount > 0
                        ? `Resolve ${effectiveReviewCount} Review Exception${effectiveReviewCount === 1 ? '' : 's'} and ${heldCount} Held Transaction${heldCount === 1 ? '' : 's'} Before Export`
                        : heldCount > 0
                          ? `Resolve ${heldCount} Held Transaction${heldCount === 1 ? '' : 's'} Before Export`
                      : `Resolve ${effectiveReviewCount} Review Exception${effectiveReviewCount === 1 ? '' : 's'} Before Export`}
                  </button>
                ) : (
                  <button
                    type="button"
                    className="ed-button-link lockbox-large-action primary"
                    onClick={() => void exportReviewedResult()}
                    disabled={isExportingReviewed}
                  >
                    {isExportingReviewed ? 'Exporting…' : 'Reviewed PNC Excel'}
                  </button>
                )}
              </div>
            ) : <button type="button" className="secondary lockbox-large-action" disabled>Download PNC Excel</button>}
          </div>
        </article>

        {PNC_COMPARISON_TRAINING_VISIBLE && (
        <article className="ed-card lockbox-workflow-card lockbox-training-card">
          <header><span>5</span><div><strong>Train From PNC Comparison</strong><small>Upload the approved PNC workbook and save the differences</small></div></header>
          <div className="lockbox-training-upload">
            <input ref={groundTruthInputRef} type="file" accept=".xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={(event) => setGroundTruthFile(event.target.files?.[0] ?? null)} disabled={!result} />
            <div><strong>{groundTruthFile?.name ?? 'No approved workbook selected'}</strong><span>This workbook is treated as the answer key.</span></div>
            <button type="button" className="primary" onClick={() => void compareGroundTruth()} disabled={!result || !groundTruthFile || isComparing}>{isComparing ? 'Comparing…' : 'Compare & Save Training'}</button>
          </div>
        </article>
        )}
      </section>

      {PNC_COMPARISON_TRAINING_VISIBLE && training && (
        <>
          <section className="lockbox-accuracy-grid">
            <article><span>Overall Accuracy</span><strong>{training.overall_accuracy.toFixed(1)}%</strong></article>
            <article><span>Transaction Accuracy</span><strong>{training.transaction_accuracy.toFixed(1)}%</strong></article>
            <article><span>Invoice Accuracy</span><strong>{training.invoice_accuracy.toFixed(1)}%</strong></article>
            <article><span>Amount Accuracy</span><strong>{training.amount_accuracy.toFixed(1)}%</strong></article>
          </section>
          <section className="ed-card">
            <div className="ed-card-heading"><div><strong>Ground-Truth Differences</strong><span>{training.ground_truth_file_name}</span></div><span className={`ed-training-badge ${exceptionTransactions.length === 0 ? 'success' : 'warning'}`}>{exceptionTransactions.length === 0 ? 'All Matched' : `${exceptionTransactions.length} Exceptions`}</span></div>
            {exceptionTransactions.length === 0 ? <div className="ed-banner success">ETOP matched every transaction and invoice allocation in the approved PNC workbook.</div> : (
              <div className="ed-training-comparisons">
                {exceptionTransactions.map((transaction) => (
                  <article key={transaction.transaction_id}>
                    <header><div><strong>{transaction.transaction_id}</strong><span>Expected {money(transaction.expected_check_amount)} · ETOP {money(transaction.actual_check_amount)}</span></div><b>{transaction.accuracy.toFixed(1)}%</b></header>
                    <div className="ed-table-wrap"><table className="ed-table"><thead><tr><th>Difference</th><th>Invoice</th><th>Expected</th><th>ETOP</th></tr></thead><tbody>{transaction.differences.filter((row) => row.difference_type !== 'matched').map((row, index) => <tr key={`${row.invoice_number}-${row.difference_type}-${index}`}><td><span className={`ed-difference ${row.difference_type}`}>{row.difference_type.replace('_', ' ')}</span></td><td><strong>{row.invoice_number || 'Blank'}</strong></td><td>{money(row.expected_amount)}</td><td>{money(row.actual_amount)}</td></tr>)}</tbody></table></div>
                  </article>
                ))}
              </div>
            )}
          </section>
        </>
      )}

      {result && (
        <section className="ed-card" ref={reviewQueueRef}>
          <div className="ed-card-heading">
            <div><strong>Transaction Review Queue</strong><span>{reviewQueueLabel} · {result.lockbox} · {result.transaction_date}</span></div>
            <div className="lockbox-queue-toolbar">
              <select
                aria-label="Filter transaction review queue"
                value={reviewReasonFilter ? 'reason' : reviewFilter}
                onChange={(event) => {
                  const value = event.target.value
                  if (value === 'reason') return
                  setReviewReasonFilter('')
                  setReviewFilter(value as ReviewQueueFilter)
                }}
              >
                <option value="all">All transactions</option>
                <option value="balanced">Prepared &amp; Balanced</option>
                <option value="exceptions">Exceptions only</option>
                <option value="corrected">Saved corrections only</option>
                <option value="held">Held only</option>
                <option value="approved">Approved only</option>
                {activeReason && (
                  <option value="reason">Reason: {activeReason.label}</option>
                )}
              </select>
              {activeReason && (
                <button
                  type="button"
                  className="secondary"
                  onClick={() => openTransactionQueue('exceptions')}
                >
                  Clear reason filter
                </button>
              )}
              <button
                type="button"
                className="secondary"
                onClick={() => void exportVisibleQueue()}
                disabled={
                  preparationIncomplete
                  || visibleTransactions.length === 0
                  || isExportingQueue
                }
              >
                {isExportingQueue ? 'Exporting…' : 'Export to Excel'}
              </button>
              <div className="ed-lockbox-total"><span>Check Total</span><strong>{money(result.total_check_amount)}</strong></div>
            </div>
          </div>
          {preparationIncomplete ? (
            <div className="ed-banner warning">
              ERP customer and allocation preparation is
              {preparationHasStarted ? ' incomplete. Resume ' : ' ready. Start '}
              preparation before ETOP calculates or displays the exception
              queue.
            </div>
          ) : visibleTransactions.length === 0 && (
            <div className="ed-banner success">
              No transactions match {reviewQueueLabel}. Use All transactions
              to inspect the complete lockbox.
            </div>
          )}
          {!preparationIncomplete && (
            <div className="ed-table-wrap"><table className="ed-table"><thead><tr><th>Status</th><th>Transaction</th><th>Customer</th><th>Check</th><th>Check Amount</th><th>Invoices</th><th>Allocated</th><th>Difference</th><th /></tr></thead><tbody>{visibleTransactions.map((transaction) => <tr key={transaction.transaction_id} className="lockbox-review-row" onDoubleClick={() => void openReview(transaction.transaction_id)}><td><span className={`ed-lockbox-status ${transaction.status}`}>{transaction.status === 'approved' ? 'Approved' : transaction.status === 'held' ? 'Held' : transaction.status === 'corrected' ? 'Corrected' : transaction.status === 'balanced' ? 'Prepared' : transaction.status === 'no_remittance' ? 'No Remittance' : 'Review'}</span></td><td><strong>{transaction.transaction_id}</strong><small>Batch {transaction.batch} / Item {transaction.batch_item}</small></td><td>{transaction.customer_name}</td><td>{transaction.check_number}</td><td>{money(transaction.check_amount)}</td><td>{transaction.allocations.length}</td><td>{money(transaction.allocation_total)}</td><td>{money(transaction.difference)}</td><td><button type="button" className="secondary" disabled={Boolean(preparingTransactionId)} onClick={() => void openReview(transaction.transaction_id)}>{preparingTransactionId === transaction.transaction_id ? 'Preparing…' : 'Review'}</button></td></tr>)}</tbody></table></div>
          )}
        </section>
      )}

      {review && reviewTransactionId && (
        <LockboxReviewWorkspace
          jobId={selectedJobId}
          review={review}
          initialTransactionId={reviewTransactionId}
          preparedTransactions={preparedTransactions}
          queueTransactionIds={visibleTransactions.map(
            (transaction) => transaction.transaction_id,
          )}
          queueLabel={reviewQueueLabel}
          onPrepareTransaction={(transactionId) => (
            prepareTransactionForReview(review, transactionId)
          )}
          onClose={() => setReviewTransactionId('')}
          onUpdated={(updated, updatedTransactionId) => {
            const projected = durablePreparation
              ? projectGovernedLockboxReview(updated, durablePreparation)
              : { review: updated, preparedTransactions }
            setReview(projected.review)
            const savedTransactionId = (
              updatedTransactionId || reviewTransactionId
            )
            if (savedTransactionId) {
              const currentPrepared =
                projected.preparedTransactions[savedTransactionId]
              const savedTransaction = updated.transactions.find(
                (transaction) => (
                  transaction.transaction_id === savedTransactionId
                ),
              )
              const savedCustomer = savedTransaction?.customer_number
                ? {
                  customerNumber: savedTransaction.customer_number,
                  customerName: savedTransaction.customer_name || '',
                  phone:
                    savedTransaction.customer_phone
                    || savedTransaction.phone_number
                    || '',
                  addressLine1:
                    savedTransaction.customer_address_line_1
                    || savedTransaction.address_line_1
                    || '',
                  addressLine2:
                    savedTransaction.customer_address_line_2
                    || savedTransaction.address_line_2
                    || '',
                  city:
                    savedTransaction.customer_city
                    || savedTransaction.city
                    || '',
                  state:
                    savedTransaction.customer_state
                    || savedTransaction.state
                    || '',
                  postalCode:
                    savedTransaction.customer_postal_code
                    || savedTransaction.customer_zip
                    || savedTransaction.postal_code
                    || '',
                }
                : currentPrepared?.customer ?? null
              const nextPrepared = currentPrepared
                ? {
                  ...projected.preparedTransactions,
                  [savedTransactionId]: {
                    ...currentPrepared,
                    preparedAt: new Date().toISOString(),
                    recommendation: null,
                    customer: savedCustomer,
                    customerSource: 'saved' as const,
                    message: (
                      'Saved review restored from the durable lockbox record; '
                      + 'no recommendation recalculation is required.'
                    ),
                  },
                }
                : projected.preparedTransactions
              preparedTransactionsRef.current = nextPrepared
              setPreparedTransactions(nextPrepared)
            }
            setReviewTransactionId((current) => current)
          }}
        />
      )}

    </div>
  )
}
