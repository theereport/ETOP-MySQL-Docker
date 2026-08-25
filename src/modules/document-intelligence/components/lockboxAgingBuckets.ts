import type {
  ReviewedLockboxAllocation,
} from '../types'
import {
  getLegacyOpenItemIdentity,
  getInvoiceBusinessEffect,
} from './lockboxAllocationRules'
import type {
  LegacyInvoiceDetail,
} from './lockboxAllocationRules'

export const LOCKBOX_AGING_BUCKETS = [
  { key: 'future', label: 'Future' },
  { key: 'current', label: 'Current' },
  { key: 'past_due_1_30', label: 'Past Due 1–30' },
  { key: 'past_due_31_60', label: 'Past Due 31–60' },
  { key: 'past_due_61_90', label: 'Past Due 61–90' },
  { key: 'past_due_91_120', label: 'Past Due 91–120' },
  { key: 'past_due_121_plus', label: 'Past Due 121+' },
] as const

export type LockboxAgingBucketKey =
  typeof LOCKBOX_AGING_BUCKETS[number]['key']

export type LockboxAgingBucketSummary = {
  key: LockboxAgingBucketKey
  label: string
  count: number
  total: number | null
  firstDueDate: string
  lastDueDate: string
  invalidItemCount: number
  allocations: ReviewedLockboxAllocation[]
  selectable: boolean
}

export type LockboxAgingBucketResult = {
  buckets: LockboxAgingBucketSummary[]
  unclassifiedItemCount: number
}

function normalizedBucket(value: unknown): string {
  return String(value ?? '')
    .trim()
    .toUpperCase()
    .replace(/[\u2012\u2013\u2014]/g, '-')
    .replace(/\s+/g, ' ')
}

export function lockboxAgingBucketKey(
  value: unknown,
): LockboxAgingBucketKey | null {
  const bucket = normalizedBucket(value)

  if (['FUTURE', 'FUTURE DUE'].includes(bucket)) return 'future'
  if (['CURRENT', 'CURRENT DUE'].includes(bucket)) return 'current'
  if (
    ['PAST DUE 1-30', 'PAST DUE 30', '1-30'].includes(bucket)
  ) return 'past_due_1_30'
  if (
    ['PAST DUE 31-60', 'PAST DUE 60', '31-60'].includes(bucket)
  ) return 'past_due_31_60'
  if (
    ['PAST DUE 61-90', 'PAST DUE 90', '61-90'].includes(bucket)
  ) return 'past_due_61_90'
  if (
    ['PAST DUE 91-120', 'PAST DUE 120', '91-120'].includes(bucket)
  ) return 'past_due_91_120'
  if (
    [
      'PAST DUE 121+',
      'PAST DUE 121 PLUS',
      '121+',
      '121 PLUS',
    ].includes(bucket)
  ) return 'past_due_121_plus'

  return null
}

function allocationFromOpenItem(
  invoice: LegacyInvoiceDetail,
  invoicePage: string,
): ReviewedLockboxAllocation | null {
  const identity = getLegacyOpenItemIdentity(invoice)
  const effect = getInvoiceBusinessEffect(invoice)
  if (!identity || effect.amount === null || !Number.isFinite(effect.amount)) {
    return null
  }

  return {
    invoice_number: identity.displayNumber,
    net_invoice_amount: effect.amount,
    invoice_page: invoicePage,
    confidence: 1,
    allocation_kind: identity.allocationKind,
    erp_transaction_type: identity.rawTransactionType,
    open_item_key: identity.openItemKey,
    normalized_invoice_number: identity.normalizedInvoiceNumber,
    invoice_count: identity.invoiceCount,
  }
}

function dueDate(value: unknown): string {
  const text = String(value ?? '').trim()
  return /^\d{4}-\d{2}-\d{2}(?:$|T)/.test(text)
    ? text.slice(0, 10)
    : ''
}

export function buildLockboxAgingBucketResult(
  openInvoices: LegacyInvoiceDetail[],
  invoicePage: string,
): LockboxAgingBucketResult {
  const grouped = new Map<
    LockboxAgingBucketKey,
    LegacyInvoiceDetail[]
  >(
    LOCKBOX_AGING_BUCKETS.map((definition) => [definition.key, []]),
  )
  let unclassifiedItemCount = 0

  openInvoices.forEach((invoice) => {
    const key = lockboxAgingBucketKey(
      invoice.aging_bucket || invoice.due_date_bucket,
    )
    if (!key) {
      unclassifiedItemCount += 1
      return
    }
    grouped.get(key)?.push(invoice)
  })

  return {
    buckets: LOCKBOX_AGING_BUCKETS.map((definition) => {
      const sourceItems = grouped.get(definition.key) ?? []
      const allocations: ReviewedLockboxAllocation[] = []
      const identityKeys = new Set<string>()
      const dates: string[] = []
      let invalidItemCount = 0

      sourceItems.forEach((invoice) => {
        const identity = getLegacyOpenItemIdentity(invoice)
        const allocation = allocationFromOpenItem(invoice, invoicePage)
        const itemDueDate = dueDate(invoice.due_date)
        if (
          !identity
          || !allocation
          || !itemDueDate
          || identityKeys.has(identity.key)
        ) {
          invalidItemCount += 1
          return
        }
        identityKeys.add(identity.key)
        dates.push(itemDueDate)
        allocations.push(allocation)
      })

      dates.sort()
      const selectable = (
        sourceItems.length > 0
        && invalidItemCount === 0
        && allocations.length === sourceItems.length
      )
      const total = sourceItems.length === 0
        ? 0
        : selectable
          ? Number(allocations.reduce(
            (sum, allocation) => (
              sum + Number(allocation.net_invoice_amount)
            ),
            0,
          ).toFixed(2))
          : null

      return {
        ...definition,
        count: sourceItems.length,
        total,
        firstDueDate: dates[0] || '',
        lastDueDate: dates.at(-1) || '',
        invalidItemCount,
        allocations,
        selectable,
      }
    }),
    unclassifiedItemCount,
  }
}
