import {
  getCurrentDurableLockboxPreparation,
  getDurableLockboxPreparation,
  startDurableLockboxPreparation,
} from '../api'
import type {
  DurableLockboxPreparation,
  DurableLockboxPreparationTransaction,
  LockboxReviewResult,
  ReviewedLockboxAllocation,
} from '../types'
import type {
  LockboxRecommendation,
} from './lockboxRecommendation'
import type {
  PreparedErpCustomer,
  PreparedLockboxTransaction,
} from './lockboxPreparation'

const POLL_INTERVAL_MS = 750
const MAX_POLL_TIME_MS = 30 * 60 * 1000

type JsonMap = Record<string, unknown>

function object(value: unknown): JsonMap {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as JsonMap
    : {}
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : String(value ?? '')
}

function number(value: unknown): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.map(text).filter(Boolean) : []
}

function durableTransaction(
  value: unknown,
): value is DurableLockboxPreparationTransaction {
  const candidate = object(value)
  return typeof candidate.transaction_id === 'string'
    && candidate.transaction_id.trim().length > 0
    && candidate.transaction_id === candidate.transaction_id.trim()
}

export function durableLockboxTransactions(
  preparation: DurableLockboxPreparation | null,
): DurableLockboxPreparationTransaction[] {
  return Array.isArray(preparation?.transactions)
    ? preparation.transactions.filter(durableTransaction)
    : []
}

export function durableLockboxExceptionReasons(
  preparation: DurableLockboxPreparation | null,
) {
  const reasons = preparation?.exception_reason_summary?.by_primary_reason
  return Array.isArray(reasons)
    ? reasons.filter((reason) => (
      reason !== null
      && typeof reason === 'object'
      && typeof reason.code === 'string'
      && reason.code.trim().length > 0
      && typeof reason.label === 'string'
    ))
    : []
}

function delay(signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('The request was aborted.', 'AbortError'))
      return
    }
    const timeout = window.setTimeout(resolve, POLL_INTERVAL_MS)
    signal?.addEventListener('abort', () => {
      window.clearTimeout(timeout)
      reject(new DOMException('The request was aborted.', 'AbortError'))
    }, { once: true })
  })
}

function governedPreparationSummaryIsFinal(
  preparation: DurableLockboxPreparation | null,
): boolean {
  return Boolean(
    preparation?.complete
    && preparation.counts_final
    && preparation.reconciled
    && preparation.current_for_rule !== false
    && preparation.terminal_count === preparation.expected_count
    && (
      preparation.balanced_count
      + preparation.exception_count
      + preparation.preserved_count
      === preparation.expected_count
    )
    && preparation.recommendation_not_decision
    && !preparation.can_auto_approve
    && !preparation.erp_write_performed
  )
}

function progressSummary(
  preparation: DurableLockboxPreparation,
): DurableLockboxPreparation {
  const { transactions: _transactions, ...summary } = preparation
  return summary
}

export function governedPreparationHasFullTransactions(
  preparation: DurableLockboxPreparation | null,
): boolean {
  const transactions = durableLockboxTransactions(preparation)
  const transactionIds = new Set(
    transactions.map((transaction) => transaction.transaction_id),
  )
  return Boolean(
    preparation
    && Number.isInteger(preparation.expected_count)
    && preparation.expected_count >= 0
    && Array.isArray(preparation.transactions)
    && preparation.transactions.length === preparation.expected_count
    && transactions.length === preparation.expected_count
    && transactionIds.size === preparation.expected_count
  )
}

export function governedPreparationIsFinal(
  preparation: DurableLockboxPreparation | null,
): boolean {
  return governedPreparationSummaryIsFinal(preparation)
    && governedPreparationHasFullTransactions(preparation)
}

export function governedLockboxReviewIsReady(
  preparation: DurableLockboxPreparation | null,
  preparedTransactions: Readonly<Record<string, unknown>>,
): boolean {
  const transactions = durableLockboxTransactions(preparation)
  return governedPreparationIsFinal(preparation)
    && Object.keys(preparedTransactions).length === transactions.length
    && transactions.every((transaction) => (
      Object.prototype.hasOwnProperty.call(
        preparedTransactions,
        transaction.transaction_id,
      )
    ))
}

export async function waitForDurableLockboxPreparation(
  initial: DurableLockboxPreparation,
  onProgress?: (preparation: DurableLockboxPreparation) => void,
  signal?: AbortSignal,
): Promise<DurableLockboxPreparation> {
  let current = initial
  const startedAt = Date.now()
  onProgress?.(progressSummary(current))
  while (!governedPreparationSummaryIsFinal(current)) {
    if (current.complete && !current.reconciled) {
      throw new Error(
        'Governed Lockbox preparation completed without reconciling every transaction.',
      )
    }
    if (Date.now() - startedAt > MAX_POLL_TIME_MS) {
      throw new Error('Governed Lockbox preparation did not finish within 30 minutes.')
    }
    await delay(signal)
    current = await getDurableLockboxPreparation(
      current.job_id,
      false,
      signal,
    )
    onProgress?.(progressSummary(current))
  }
  if (!governedPreparationHasFullTransactions(current)) {
    current = await getDurableLockboxPreparation(
      current.job_id,
      true,
      signal,
    )
  }
  if (!governedPreparationIsFinal(current)) {
    throw new Error(
      'Governed Lockbox preparation detail is incomplete or malformed.',
    )
  }
  return current
}

export async function startAndWaitForDurableLockboxPreparation(
  sourceJobId: string,
  onProgress?: (preparation: DurableLockboxPreparation) => void,
  signal?: AbortSignal,
): Promise<DurableLockboxPreparation> {
  return waitForDurableLockboxPreparation(
    await startDurableLockboxPreparation(sourceJobId, signal),
    onProgress,
    signal,
  )
}

export async function loadCurrentDurableLockboxPreparation(
  sourceJobId: string,
  onProgress?: (preparation: DurableLockboxPreparation) => void,
  signal?: AbortSignal,
): Promise<DurableLockboxPreparation> {
  return waitForDurableLockboxPreparation(
    await getCurrentDurableLockboxPreparation(sourceJobId, signal),
    onProgress,
    signal,
  )
}

function sourceTransaction(
  transaction: DurableLockboxPreparationTransaction,
): JsonMap {
  return object(transaction.source.original_source)
}

function resultFor(
  transaction: DurableLockboxPreparationTransaction,
): JsonMap {
  return object(transaction.result)
}

function customerResolutionFor(
  transaction: DurableLockboxPreparationTransaction,
): JsonMap {
  const result = resultFor(transaction)
  const direct = object(result.customer_resolution)
  return Object.keys(direct).length > 0
    ? direct
    : object(object(result.evidence).customer_resolution)
}

function customerFor(
  transaction: DurableLockboxPreparationTransaction,
): PreparedErpCustomer | null {
  const result = resultFor(transaction)
  const snapshot = object(result.customer_snapshot)
  const fields = object(snapshot.fields)
  const resolution = customerResolutionFor(transaction)
  const resolutionSnapshot = object(resolution.customer_snapshot)
  const candidate = Object.keys(fields).length > 0
    ? fields
    : resolutionSnapshot
  const customerNumber = text(
    candidate.customer_number || resolution.customer_number,
  )
  if (!customerNumber) return null
  return {
    customerNumber,
    customerName: text(candidate.customer_name),
    phone: text(candidate.phone),
    addressLine1: text(candidate.address_line_1),
    addressLine2: text(candidate.address_line_2),
    city: text(candidate.city),
    state: text(candidate.state),
    postalCode: text(candidate.postal_code),
  }
}

function recommendationFor(
  transaction: DurableLockboxPreparationTransaction,
  customer: PreparedErpCustomer | null,
): LockboxRecommendation | null {
  const result = resultFor(transaction)
  const recommendation = object(result.recommendation)
  if (!recommendation.status) return null
  const allocations = Array.isArray(recommendation.allocations)
    ? recommendation.allocations.map((value) => {
      const allocation = object(value)
      return {
        invoice_number: text(allocation.invoice_number),
        open_amount: number(allocation.open_amount),
        suggested_apply_amount: number(allocation.apply_amount),
        invoice_date: text(allocation.invoice_date) || null,
        due_date: text(allocation.due_date) || null,
        aging_bucket: text(allocation.aging_bucket) || null,
        transaction_type: (
          text(allocation.business_type).toLowerCase() === 'credit'
            ? 'credit'
            : 'debit'
        ) as 'debit' | 'credit',
        erp_transaction_type: text(allocation.raw_transaction_type) || null,
        negative_debit_credit: Boolean(allocation.negative_debit_credit),
        allocation_kind: text(allocation.allocation_kind) === 'service_charge'
          ? 'service_charge' as const
          : 'invoice' as const,
        open_item_key: text(allocation.open_item_key),
        normalized_invoice_number: text(
          allocation.normalized_invoice_number,
        ),
        invoice_count: allocation.invoice_count === null
          || allocation.invoice_count === undefined
          ? null
          : number(allocation.invoice_count),
        confidence: 1,
        reason: text(allocation.reason),
      }
    })
    : []
  const resolution = customerResolutionFor(transaction)
  const selectedConfidence = number(resolution.selected_confidence)
  const overallConfidence = (
    text(recommendation.status) === 'recommended'
    && Math.abs(number(recommendation.difference)) <= 0.01
  )
    ? selectedConfidence
    : Math.min(selectedConfidence, 0.99)
  return {
    status: text(recommendation.status) === 'recommended'
      ? 'recommended'
      : 'review_required',
    transaction_id: transaction.transaction_id,
    customer_match: customer ? {
      customer_number: customer.customerNumber,
      customer_name: customer.customerName,
      confidence: selectedConfidence,
      matched_on: strings(resolution.matched_on),
      warnings: strings(resolution.warnings),
      customer_phone: customer.phone,
      customer_address_line_1: customer.addressLine1,
      customer_address_line_2: customer.addressLine2,
      customer_city: customer.city,
      customer_state: customer.state,
      customer_postal_code: customer.postalCode,
    } : null,
    decision: {
      status: text(recommendation.status) === 'recommended'
        ? 'recommended'
        : 'review_required',
      overall_confidence: overallConfidence,
      payment_intent: {
        intent_type: text(recommendation.method),
        confidence: overallConfidence,
        explanation: strings(recommendation.reasons),
      },
      decision_reasons: strings(recommendation.reasons),
      warnings: strings(recommendation.warnings),
    },
    suggested_allocations: allocations,
    check_amount: number(recommendation.check_amount),
    suggested_total: number(recommendation.suggested_total),
    difference: number(recommendation.difference),
    can_auto_approve: false,
    decision_reasons: strings(recommendation.reasons),
    warnings: strings(recommendation.warnings),
    allocation_basis: text(recommendation.method) as (
      | 'same_due_date_exact_match'
      | 'invoice_exact_match'
      | 'aging_match'
      | 'combination_match'
      | 'exact_remittance_plus_oldest_open_items'
      | 'exact_remittance_plus_unique_open_item'
      | 'ambiguous_remittance_residual_open_items'
      | 'partial_exact_remittance'
      | 'exact_remittance_invoices'
      | 'exact_total_open_balance'
      | 'exact_aging_bucket_match'
      | 'oldest_open_items_exact_match'
      | 'unique_exact_due_date_group_combination'
      | 'exact_remittance_invoice_cap_plus_service_charge'
      | 'service_charge_residual_review'
    ),
  }
}

function primaryReason(
  transaction: DurableLockboxPreparationTransaction,
): JsonMap {
  const result = resultFor(transaction)
  return object(object(result.exception_analysis).primary_reason)
}

function preparedFor(
  transaction: DurableLockboxPreparationTransaction,
): PreparedLockboxTransaction {
  const customer = customerFor(transaction)
  const recommendation = recommendationFor(transaction, customer)
  const reason = primaryReason(transaction)
  const source = sourceTransaction(transaction)
  const invoiceNumbers = Array.isArray(source.allocations)
    ? source.allocations.map((value) => text(object(value).invoice_number)).filter(Boolean)
    : []
  const message = transaction.state === 'prepared_balanced'
    ? 'Governed preparation found one balanced recommendation. Review it before approval.'
    : [text(reason.label), text(reason.review_guidance)].filter(Boolean).join(' — ')
      || text(object(transaction.error).message)
      || 'Governed preparation retained this transaction for professional review.'
  const resolution = customerResolutionFor(transaction)
  const matchingEvidence = object(resolution.matching_evidence)
  const gateWarnings = strings(matchingEvidence.failed_selection_gates)
    .map((gate) => `Evidence gate: ${gate.replaceAll('_', ' ')}`)
  const candidateWarnings = Array.isArray(matchingEvidence.ranked_candidates)
    ? matchingEvidence.ranked_candidates.map((value) => {
      const candidate = object(value)
      const identity = [
        text(candidate.customer_number),
        text(candidate.customer_name),
      ].filter(Boolean).join(' · ')
      const matchedOn = strings(candidate.matched_on).join(', ')
      return [
        `Candidate ${identity || 'identity unavailable'}`,
        `score ${number(candidate.score)}`,
        matchedOn ? `matched on ${matchedOn}` : '',
      ].filter(Boolean).join(' — ')
    })
    : []
  return {
    transactionId: transaction.transaction_id,
    status: transaction.state === 'prepared_balanced'
      ? 'ready'
      : 'needs_review',
    preparedAt: text(transaction.result && resultFor(transaction).prepared_at)
      || new Date().toISOString(),
    invoiceNumbers,
    customer,
    customerSource: customer
      ? text(object(resultFor(transaction).customer_resolution).selection_basis)
        .includes('invoice') ? 'invoice' : 'recommendation'
      : null,
    recommendation,
    message,
    warnings: [
      ...gateWarnings,
      ...candidateWarnings,
      ...strings(object(transaction.error).warnings),
      ...strings(resolution.warnings),
    ],
  }
}

function suggestedAllocations(
  prepared: PreparedLockboxTransaction,
  source: ReviewedLockboxAllocation[],
): ReviewedLockboxAllocation[] {
  if (prepared.status !== 'ready' || !prepared.recommendation) return source
  return prepared.recommendation.suggested_allocations.map((allocation) => ({
    invoice_number: allocation.invoice_number,
    net_invoice_amount: number(allocation.suggested_apply_amount),
    invoice_page: '',
    confidence: allocation.confidence,
    allocation_kind: allocation.allocation_kind,
    erp_transaction_type: allocation.erp_transaction_type || '',
    open_item_key: allocation.open_item_key,
    normalized_invoice_number: allocation.normalized_invoice_number,
    invoice_count: allocation.invoice_count,
  }))
}

export function projectGovernedLockboxReview(
  review: LockboxReviewResult,
  preparation: DurableLockboxPreparation,
): {
  review: LockboxReviewResult
  preparedTransactions: Record<string, PreparedLockboxTransaction>
} {
  if (!governedPreparationIsFinal(preparation)) {
    throw new Error('Governed preparation is not complete and reconciled.')
  }
  const durableById = new Map(
    durableLockboxTransactions(preparation).map(
      (item) => [item.transaction_id, item],
    ),
  )
  const preparedTransactions: Record<string, PreparedLockboxTransaction> = {}
  const transactions = review.transactions.map((transaction) => {
    const durable = durableById.get(transaction.transaction_id)
    if (!durable) {
      throw new Error(
        `Governed preparation omitted transaction ${transaction.transaction_id}.`,
      )
    }
    const prepared = preparedFor(durable)
    preparedTransactions[transaction.transaction_id] = prepared
    if (
      transaction.status === 'corrected'
      || transaction.status === 'held'
      || transaction.status === 'carryover'
      || transaction.status === 'approved'
    ) {
      return transaction
    }
    const allocations = suggestedAllocations(prepared, transaction.allocations)
    const allocationTotal = allocations.reduce(
      (total, allocation) => total + number(allocation.net_invoice_amount),
      0,
    )
    const difference = number(transaction.check_amount) - allocationTotal
    const customer = prepared.customer
    return {
      ...transaction,
      ...(customer ? {
        customer_number: customer.customerNumber,
        customer_name: customer.customerName,
        customer_phone: customer.phone,
        customer_address_line_1: customer.addressLine1,
        customer_address_line_2: customer.addressLine2,
        customer_city: customer.city,
        customer_state: customer.state,
        customer_postal_code: customer.postalCode,
      } : {}),
      allocations,
      allocation_total: Math.round(allocationTotal * 100) / 100,
      difference: Math.round(difference * 100) / 100,
      balanced: durable.state === 'prepared_balanced',
      status: durable.state === 'prepared_balanced'
        ? 'balanced' as const
        : transaction.status === 'no_remittance'
          ? 'no_remittance' as const
          : 'review_required' as const,
    }
  })
  const approvedCount = transactions.filter((item) => item.status === 'approved').length
  const correctedCount = transactions.filter((item) => item.status === 'corrected').length
  const heldCount = transactions.filter((item) => item.status === 'held').length
  const carryoverCount = transactions.filter((item) => item.status === 'carryover').length
  const balancedCount = transactions.filter((item) => item.status === 'balanced').length
  const reviewCount = (
    transactions.length
    - balancedCount
    - approvedCount
    - correctedCount
    - heldCount
    - carryoverCount
  )
  return {
    preparedTransactions,
    review: {
      ...review,
      balanced_count: balancedCount,
      review_count: reviewCount,
      approved_count: approvedCount,
      corrected_count: correctedCount,
      held_count: heldCount,
      carryover_count: carryoverCount,
      transactions,
    },
  }
}
