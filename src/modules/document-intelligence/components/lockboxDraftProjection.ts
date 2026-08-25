import type {
  LockboxReviewStatus,
  ReviewedLockboxAllocation,
} from '../types'
import type { LockboxRecommendation } from './lockboxRecommendation'

export function isGovernedServiceCharge(
  allocation: ReviewedLockboxAllocation,
): boolean {
  return Boolean(
    allocation.allocation_kind === 'service_charge'
    && allocation.erp_transaction_type?.trim().toUpperCase() === 'SC'
    && allocation.open_item_key?.trim(),
  )
}

export function recommendationDraft(
  recommendation: LockboxRecommendation,
  invoicePage: string,
): ReviewedLockboxAllocation[] {
  return recommendation.suggested_allocations.map((suggestion) => ({
    invoice_number: suggestion.invoice_number,
    net_invoice_amount: Number(suggestion.suggested_apply_amount),
    invoice_page: invoicePage,
    confidence: suggestion.confidence,
    allocation_kind: suggestion.allocation_kind,
    erp_transaction_type: suggestion.erp_transaction_type || '',
    open_item_key: suggestion.open_item_key,
    normalized_invoice_number: suggestion.normalized_invoice_number,
    invoice_count: suggestion.invoice_count,
  }))
}

export function shouldProjectRecommendationDraft(
  recommendation: LockboxRecommendation,
  allocationDraftDirty: boolean,
  transactionStatus: LockboxReviewStatus,
): boolean {
  return Boolean(
    recommendation.status === 'recommended'
    && recommendation.suggested_allocations.length > 0
    && Math.abs(Number(recommendation.difference)) <= 0.01
    && !allocationDraftDirty
    && transactionStatus !== 'corrected'
    && transactionStatus !== 'held'
    && transactionStatus !== 'approved'
    && transactionStatus !== 'balanced',
  )
}
