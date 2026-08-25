import {
  saveLockboxTransactionReview,
} from '../api'
import type {
  LockboxReviewResult,
  LockboxReviewStatus,
  ReviewedLockboxAllocation,
  ReviewedLockboxTransaction,
  SaveLockboxTransactionReviewRequest,
} from '../types'

import {
  createLockboxPreparationContext,
  prepareLockboxTransaction,
} from './lockboxPreparation'
import { normalizeErpInvoiceNumber } from './erpInvoiceNumber'
import type {
  LockboxPreparationContext,
  PreparedLockboxTransaction,
} from './lockboxPreparation'

const CACHE_VERSION = 3
const LEGACY_CACHE_VERSIONS = new Set([1, 2])
const CACHE_PREFIX = 'etop.lockbox.prepared'
const PREPARATION_DATABASE = 'etop-local-workflow'
const PREPARATION_STORE = 'lockbox-preparation'
const PREPARATION_DATABASE_VERSION = 1
const AMOUNT_TOLERANCE = 0.01
const PREPARATION_TIMEOUT_MS = 120_000
const SAVE_TIMEOUT_MS = 30_000
const DEFAULT_PREPARATION_CONCURRENCY = 6
const MAX_PREPARATION_CONCURRENCY = 8

type PreparedCache = {
  version: number
  jobId: string
  savedAt: string
  expectedTransactionCount?: number
  transactions: Record<string, PreparedLockboxTransaction>
}

type PreparedCacheEntry = {
  key: string
  jobId: string
  transactionId: string
  savedAt: string
  expectedTransactionCount?: number
  prepared: PreparedLockboxTransaction
}

export type LockboxBatchPreparationProgress = {
  current: number
  total: number
  transactionId: string
}

export type LockboxBatchPreparationResult = {
  review: LockboxReviewResult
  preparedTransactions: Record<string, PreparedLockboxTransaction>
  coverage: LockboxPreparationCoverage
}

export type LockboxPreparationCoverage = {
  total: number
  completed: number
  prepared: number
  failed: number
  decided: number
  complete: boolean
  missingTransactionIds: string[]
}

export type LockboxBatchPreparationOptions = {
  existingTransactions?: Record<string, PreparedLockboxTransaction>
  retryFailed?: boolean
  concurrency?: number
}

function cacheKey(jobId: string): string {
  return `${CACHE_PREFIX}.${jobId}`
}

function browserStorage(): Storage | null {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage
  } catch {
    return null
  }
}

let preparationDatabasePromise: Promise<IDBDatabase | null> | null = null

function openPreparationDatabase(): Promise<IDBDatabase | null> {
  if (typeof indexedDB === 'undefined') {
    return Promise.resolve(null)
  }
  if (preparationDatabasePromise) return preparationDatabasePromise

  preparationDatabasePromise = new Promise((resolve) => {
    let settled = false
    const finish = (database: IDBDatabase | null) => {
      if (settled) return
      settled = true
      resolve(database)
    }

    try {
      const request = indexedDB.open(
        PREPARATION_DATABASE,
        PREPARATION_DATABASE_VERSION,
      )
      request.onupgradeneeded = () => {
        const database = request.result
        if (!database.objectStoreNames.contains(PREPARATION_STORE)) {
          const store = database.createObjectStore(
            PREPARATION_STORE,
            { keyPath: 'key' },
          )
          store.createIndex('jobId', 'jobId', { unique: false })
        }
      }
      request.onsuccess = () => finish(request.result)
      request.onerror = () => finish(null)
      request.onblocked = () => finish(null)
    } catch {
      finish(null)
    }
  })
  return preparationDatabasePromise
}

function transactionCompleted(
  transaction: IDBTransaction,
): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve()
    transaction.onerror = () => reject(
      transaction.error ?? new Error('Preparation cache write failed.'),
    )
    transaction.onabort = () => reject(
      transaction.error ?? new Error('Preparation cache write aborted.'),
    )
  })
}

function legacyPreparedTransactions(
  jobId: string,
): Record<string, PreparedLockboxTransaction> {
  const storage = browserStorage()
  if (!storage || !jobId) return {}

  try {
    const payload = JSON.parse(
      storage.getItem(cacheKey(jobId)) || 'null',
    ) as PreparedCache | null
    if (
      !payload
      || (
        payload.version !== CACHE_VERSION
        && !LEGACY_CACHE_VERSIONS.has(payload.version)
      )
      || payload.jobId !== jobId
      || !payload.transactions
    ) {
      return {}
    }
    return payload.transactions
  } catch {
    return {}
  }
}

function saveLegacyPreparedTransactions(
  jobId: string,
  transactions: Record<string, PreparedLockboxTransaction>,
  expectedTransactionCount?: number,
): void {
  const storage = browserStorage()
  if (!storage || !jobId) return

  const payload: PreparedCache = {
    version: CACHE_VERSION,
    jobId,
    savedAt: new Date().toISOString(),
    expectedTransactionCount,
    transactions,
  }
  try {
    storage.setItem(cacheKey(jobId), JSON.stringify(payload))
  } catch {
    // The durable review record still holds customer and allocation fields.
  }
}

function cacheEntry(
  jobId: string,
  prepared: PreparedLockboxTransaction,
  expectedTransactionCount?: number,
): PreparedCacheEntry {
  return {
    key: `${jobId}:${prepared.transactionId}`,
    jobId,
    transactionId: prepared.transactionId,
    savedAt: new Date().toISOString(),
    expectedTransactionCount,
    prepared,
  }
}

async function writePreparedEntries(
  jobId: string,
  transactions: Record<string, PreparedLockboxTransaction>,
  expectedTransactionCount?: number,
): Promise<boolean> {
  const database = await openPreparationDatabase()
  if (!database) return false

  try {
    const transaction = database.transaction(
      PREPARATION_STORE,
      'readwrite',
    )
    const store = transaction.objectStore(PREPARATION_STORE)
    for (const prepared of Object.values(transactions)) {
      store.put(
        cacheEntry(jobId, prepared, expectedTransactionCount),
      )
    }
    await transactionCompleted(transaction)
    return true
  } catch {
    return false
  }
}

async function savePreparedLockboxTransaction(
  jobId: string,
  prepared: PreparedLockboxTransaction,
  expectedTransactionCount?: number,
): Promise<void> {
  if (
    await writePreparedEntries(
      jobId,
      { [prepared.transactionId]: prepared },
      expectedTransactionCount,
    )
  ) {
    return
  }

  saveLegacyPreparedTransactions(
    jobId,
    {
      ...legacyPreparedTransactions(jobId),
      [prepared.transactionId]: prepared,
    },
    expectedTransactionCount,
  )
}

export async function loadPreparedLockboxTransactions(
  jobId: string,
): Promise<Record<string, PreparedLockboxTransaction>> {
  if (!jobId) return {}
  const legacy = legacyPreparedTransactions(jobId)
  const database = await openPreparationDatabase()
  if (!database) return legacy

  try {
    const transaction = database.transaction(
      PREPARATION_STORE,
      'readonly',
    )
    const request = transaction.objectStore(PREPARATION_STORE)
      .index('jobId')
      .getAll(jobId)
    const entries = await new Promise<PreparedCacheEntry[]>(
      (resolve, reject) => {
        request.onsuccess = () => resolve(
          request.result as PreparedCacheEntry[],
        )
        request.onerror = () => reject(request.error)
      },
    )
    const prepared = {
      ...legacy,
      ...Object.fromEntries(
        entries.map((entry) => [
          entry.transactionId,
          entry.prepared,
        ]),
      ),
    }
    if (
      Object.keys(legacy).length > 0
      && await writePreparedEntries(jobId, legacy)
    ) {
      browserStorage()?.removeItem(cacheKey(jobId))
    }
    return prepared
  } catch {
    return legacy
  }
}

export async function savePreparedLockboxTransactions(
  jobId: string,
  transactions: Record<string, PreparedLockboxTransaction>,
  expectedTransactionCount?: number,
): Promise<void> {
  if (
    !jobId
    || await writePreparedEntries(
      jobId,
      transactions,
      expectedTransactionCount,
    )
  ) {
    return
  }
  saveLegacyPreparedTransactions(
    jobId,
    transactions,
    expectedTransactionCount,
  )
}

export async function clearPreparedLockboxTransactions(
  jobId: string,
): Promise<void> {
  try {
    browserStorage()?.removeItem(cacheKey(jobId))
  } catch {
    // Cache cleanup must not block durable lockbox processing.
  }

  const database = await openPreparationDatabase()
  if (!database || !jobId) return
  try {
    const transaction = database.transaction(
      PREPARATION_STORE,
      'readwrite',
    )
    const index = transaction.objectStore(PREPARATION_STORE)
      .index('jobId')
    const request = index.openCursor(IDBKeyRange.only(jobId))
    request.onsuccess = () => {
      const cursor = request.result
      if (!cursor) return
      cursor.delete()
      cursor.continue()
    }
    await transactionCompleted(transaction)
  } catch {
    // A stale analytical cache may be overwritten by the new processing run.
  }
}

function isDurableHumanDecision(
  transaction: ReviewedLockboxTransaction,
): boolean {
  return (
    transaction.status === 'approved'
    || transaction.status === 'corrected'
    || transaction.status === 'held'
  )
}

export function getLockboxPreparationCoverage(
  review: LockboxReviewResult,
  preparedTransactions: Record<string, PreparedLockboxTransaction>,
): LockboxPreparationCoverage {
  const missingTransactionIds: string[] = []
  let prepared = 0
  let failed = 0
  let decided = 0

  for (const transaction of review.transactions) {
    const result = preparedTransactions[transaction.transaction_id]
    if (result) {
      prepared += 1
      if (result.status === 'failed') failed += 1
      continue
    }
    if (isDurableHumanDecision(transaction)) {
      decided += 1
      continue
    }
    missingTransactionIds.push(transaction.transaction_id)
  }

  const total = review.transactions.length
  const completed = prepared + decided
  return {
    total,
    completed,
    prepared,
    failed,
    decided,
    complete: completed === total,
    missingTransactionIds,
  }
}

function recommendationAllocations(
  transaction: ReviewedLockboxTransaction,
  prepared: PreparedLockboxTransaction,
): ReviewedLockboxAllocation[] {
  const suggestions =
    prepared.recommendation?.suggested_allocations ?? []
  if (suggestions.length === 0) {
    return transaction.allocations.map((allocation) => ({
      ...allocation,
    }))
  }

  const defaultPage = String(
    transaction.remittance_pages?.[0]
    || transaction.check_page
    || 1,
  )
  const pagesByInvoice = new Map(
    transaction.allocations.map((allocation) => [
      allocation.invoice_number.replace(/\D/g, ''),
      allocation.invoice_page,
    ]),
  )

  return suggestions.map((suggestion) => ({
    invoice_number: suggestion.invoice_number,
    net_invoice_amount: Number(suggestion.suggested_apply_amount),
    invoice_page:
      pagesByInvoice.get(suggestion.invoice_number.replace(/\D/g, ''))
      || defaultPage,
    confidence: suggestion.confidence,
  }))
}

export function isPreparedAllocationBalanced(
  transaction: ReviewedLockboxTransaction,
  prepared: PreparedLockboxTransaction,
): boolean {
  const recommendation = prepared.recommendation
  if (
    prepared.status !== 'ready'
    || recommendation?.status !== 'recommended'
    || recommendation.suggested_allocations.length === 0
  ) {
    return false
  }

  const suggestedTotal = recommendation.suggested_allocations.reduce(
    (total, allocation) => (
      total + Number(allocation.suggested_apply_amount || 0)
    ),
    0,
  )
  return (
    Math.abs(transaction.check_amount - suggestedTotal)
    <= AMOUNT_TOLERANCE
  )
}

function nextStatus(
  transaction: ReviewedLockboxTransaction,
  prepared: PreparedLockboxTransaction,
): LockboxReviewStatus {
  if (transaction.status === 'approved') return 'approved'
  if (transaction.status === 'corrected') return 'corrected'
  if (transaction.status === 'held') return 'held'
  if (isPreparedAllocationBalanced(transaction, prepared)) return 'balanced'
  if (transaction.status === 'no_remittance') return 'no_remittance'
  return 'review_required'
}

export function preparedReviewPayload(
  transaction: ReviewedLockboxTransaction,
  prepared: PreparedLockboxTransaction,
): SaveLockboxTransactionReviewRequest {
  const customer = prepared.customer
  return {
    allocations: recommendationAllocations(transaction, prepared),
    reviewer: transaction.reviewer,
    notes: transaction.notes,
    status: nextStatus(transaction, prepared),
    override_reason: transaction.override_reason,
    customer_number:
      customer?.customerNumber || transaction.customer_number || '',
    customer_name:
      customer?.customerName || transaction.customer_name || '',
    customer_phone:
      customer?.phone
      || transaction.customer_phone
      || transaction.phone_number
      || '',
    customer_address_line_1:
      customer?.addressLine1
      || transaction.customer_address_line_1
      || transaction.address_line_1
      || '',
    customer_address_line_2:
      customer?.addressLine2
      || transaction.customer_address_line_2
      || transaction.address_line_2
      || '',
    customer_city:
      customer?.city
      || transaction.customer_city
      || transaction.city
      || '',
    customer_state:
      customer?.state
      || transaction.customer_state
      || transaction.state
      || '',
    customer_postal_code:
      customer?.postalCode
      || transaction.customer_postal_code
      || transaction.customer_zip
      || transaction.postal_code
      || '',
  }
}

function preparationSaveFailure(
  prepared: PreparedLockboxTransaction,
  error: unknown,
): PreparedLockboxTransaction {
  const warning = error instanceof Error
    ? error.message
    : 'The prepared ERP and allocation result could not be saved.'
  return {
    ...prepared,
    status: 'failed',
    message: `${prepared.message} The prepared result could not be saved.`,
    warnings: prepared.warnings.includes(warning)
      ? prepared.warnings
      : [...prepared.warnings, warning],
  }
}

function preparationFailure(
  transaction: ReviewedLockboxTransaction,
  error: unknown,
): PreparedLockboxTransaction {
  const timedOut = (
    error instanceof DOMException
    && error.name === 'AbortError'
  )
  const message = timedOut
    ? (
      'ERP and allocation preparation timed out for this transaction. '
      + 'It remains in the professional review queue.'
    )
    : error instanceof Error
      ? error.message
      : 'ERP and allocation preparation could not be completed.'

  return {
    transactionId: transaction.transaction_id,
    status: 'failed',
    preparedAt: new Date().toISOString(),
    invoiceNumbers: transaction.allocations
      .map((allocation) => normalizeErpInvoiceNumber(
        allocation.invoice_number,
      ))
      .filter(Boolean),
    customer: null,
    customerSource: null,
    recommendation: null,
    message,
    warnings: [message],
  }
}

async function prepareWithTimeout(
  transaction: ReviewedLockboxTransaction,
  context: LockboxPreparationContext,
): Promise<PreparedLockboxTransaction> {
  const controller = new AbortController()
  const timeout = window.setTimeout(
    () => controller.abort(),
    PREPARATION_TIMEOUT_MS,
  )
  try {
    return await prepareLockboxTransaction(
      transaction,
      controller.signal,
      context,
    )
  } catch (error) {
    return preparationFailure(transaction, error)
  } finally {
    window.clearTimeout(timeout)
  }
}

async function createPreparationContextWithTimeout(
  transactions: ReviewedLockboxTransaction[],
): Promise<LockboxPreparationContext> {
  const controller = new AbortController()
  const timeout = window.setTimeout(
    () => controller.abort(),
    PREPARATION_TIMEOUT_MS,
  )
  try {
    return await createLockboxPreparationContext(
      transactions,
      controller.signal,
    )
  } catch {
    return createLockboxPreparationContext([])
  } finally {
    window.clearTimeout(timeout)
  }
}

async function savePreparedReviewWithTimeout(
  jobId: string,
  transaction: ReviewedLockboxTransaction,
  prepared: PreparedLockboxTransaction,
): Promise<LockboxReviewResult> {
  const controller = new AbortController()
  const timeout = window.setTimeout(
    () => controller.abort(),
    SAVE_TIMEOUT_MS,
  )
  try {
    return await saveLockboxTransactionReview(
      jobId,
      transaction.transaction_id,
      preparedReviewPayload(transaction, prepared),
      controller.signal,
    )
  } finally {
    window.clearTimeout(timeout)
  }
}

export async function prepareAndPersistLockboxReview(
  jobId: string,
  initialReview: LockboxReviewResult,
  onProgress?: (
    progress: LockboxBatchPreparationProgress,
  ) => void,
  options: LockboxBatchPreparationOptions = {},
): Promise<LockboxBatchPreparationResult> {
  let review = initialReview
  const existingTransactions = (
    options.existingTransactions
    ?? await loadPreparedLockboxTransactions(jobId)
  )
  const preparedTransactions: Record<
    string,
    PreparedLockboxTransaction
  > = {
    ...existingTransactions,
  }
  const transactions = initialReview.transactions
  const pendingTransactions = transactions.filter((transaction) => {
    if (isDurableHumanDecision(transaction)) return false
    const existing = preparedTransactions[transaction.transaction_id]
    if (!existing) return true
    return options.retryFailed && existing.status === 'failed'
  })
  const alreadyCompleted =
    transactions.length - pendingTransactions.length
  const context = await createPreparationContextWithTimeout(
    pendingTransactions,
  )
  const requestedConcurrency = Number.isFinite(options.concurrency)
    ? Number(options.concurrency)
    : DEFAULT_PREPARATION_CONCURRENCY
  const concurrency = Math.max(
    1,
    Math.min(
      Math.floor(requestedConcurrency),
      MAX_PREPARATION_CONCURRENCY,
      pendingTransactions.length || 1,
    ),
  )
  let nextIndex = 0
  let newlyCompleted = 0
  let persistence = Promise.resolve()

  const persistPreparedResult = async (
    transaction: ReviewedLockboxTransaction,
    prepared: PreparedLockboxTransaction,
  ) => {
    let terminalPrepared = prepared
    try {
      review = await savePreparedReviewWithTimeout(
        jobId,
        transaction,
        prepared,
      )
    } catch (error) {
      terminalPrepared = preparationSaveFailure(prepared, error)
    }

    preparedTransactions[transaction.transaction_id] =
      terminalPrepared
    await savePreparedLockboxTransaction(
      jobId,
      terminalPrepared,
      transactions.length,
    )
    newlyCompleted += 1
    onProgress?.({
      current: alreadyCompleted + newlyCompleted,
      total: transactions.length,
      transactionId: transaction.transaction_id,
    })
  }

  const workers = Array.from(
    { length: concurrency },
    async () => {
      while (nextIndex < pendingTransactions.length) {
        const index = nextIndex
        nextIndex += 1
        const transaction = pendingTransactions[index]
        const prepared = await prepareWithTimeout(
          transaction,
          context,
        )
        const nextPersistence = persistence.then(() => (
          persistPreparedResult(transaction, prepared)
        ))
        persistence = nextPersistence.catch(() => undefined)
        await nextPersistence
      }
    },
  )
  await Promise.all(workers)
  await persistence

  const coverage = getLockboxPreparationCoverage(
    initialReview,
    preparedTransactions,
  )
  await savePreparedLockboxTransactions(
    jobId,
    preparedTransactions,
    transactions.length,
  )
  return { review, preparedTransactions, coverage }
}
