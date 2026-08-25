export const LOCKBOX_DUE_DATE_BUCKETS = [
  { key: 'current', label: 'Current', order: 0 },
  { key: 'past_due_1_30', label: 'Past Due 1–30', order: 1 },
  { key: 'past_due_31_60', label: 'Past Due 31–60', order: 2 },
  { key: 'past_due_61_90', label: 'Past Due 61–90', order: 3 },
  { key: 'past_due_90_plus', label: 'Past Due 90+', order: 4 },
] as const

export type LockboxDueDateBucketKey =
  typeof LOCKBOX_DUE_DATE_BUCKETS[number]['key']

export type LockboxDueDateOpenItem = {
  due_date?: unknown
  aging_bucket?: unknown
  due_date_bucket?: unknown
}

export type LockboxDueDateSummaryGroup = {
  dueDate: string
  bucketKey: LockboxDueDateBucketKey
  bucketLabel: string
  balanceType: 'Debit' | 'Credit'
  count: number
  total: number
}

export type LockboxDueDateSummaryResult = {
  groups: LockboxDueDateSummaryGroup[]
  sourceItemCount: number
  summarizedItemCount: number
  omittedItemCount: number
}

const MILLISECONDS_PER_DAY = 24 * 60 * 60 * 1000

function canonicalDate(value: unknown): string {
  const text = String(value ?? '').trim()
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})(?:$|T)/)
  if (!match) return ''

  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const timestamp = Date.UTC(year, month - 1, day)
  const parsed = new Date(timestamp)
  if (
    parsed.getUTCFullYear() !== year
    || parsed.getUTCMonth() !== month - 1
    || parsed.getUTCDate() !== day
  ) {
    return ''
  }
  return `${match[1]}-${match[2]}-${match[3]}`
}

function dateTimestamp(value: unknown): number | null {
  const date = canonicalDate(value)
  if (!date) return null
  const [year, month, day] = date.split('-').map(Number)
  return Date.UTC(year, month - 1, day)
}

function normalizedBucket(value: unknown): string {
  return String(value ?? '')
    .trim()
    .toUpperCase()
    .replace(/[\u2012\u2013\u2014_]/g, '-')
    .replace(/\s+/g, ' ')
}

function explicitBucket(
  value: unknown,
): LockboxDueDateBucketKey | null {
  const bucket = normalizedBucket(value)

  if (
    [
      'FUTURE',
      'FUTURE DUE',
      'CURRENT',
      'CURRENT DUE',
      'CURRENT-OR-FUTURE',
    ].includes(bucket)
  ) return 'current'

  if (
    [
      'PAST DUE 1-30',
      'PAST DUE 30',
      '1-30',
      'DAYS-1-TO-30',
    ].includes(bucket)
  ) return 'past_due_1_30'

  if (
    [
      'PAST DUE 31-60',
      'PAST DUE 60',
      '31-60',
      'DAYS-31-TO-60',
    ].includes(bucket)
  ) return 'past_due_31_60'

  if (
    [
      'PAST DUE 61-90',
      'PAST DUE 90',
      '61-90',
      'DAYS-61-TO-90',
    ].includes(bucket)
  ) return 'past_due_61_90'

  if (
    [
      'PAST DUE 90+',
      'PAST DUE 91+',
      'PAST DUE 91-120',
      'PAST DUE 120',
      'PAST DUE 121+',
      'PAST DUE 121 PLUS',
      '90+',
      '91+',
      '91-120',
      '121+',
      '121 PLUS',
      'DAYS-91-PLUS',
    ].includes(bucket)
  ) return 'past_due_90_plus'

  return null
}

function bucketFromDates(
  dueDate: string,
  agingAsOfDate: unknown,
): LockboxDueDateBucketKey | null {
  const dueTimestamp = dateTimestamp(dueDate)
  const asOfTimestamp = dateTimestamp(agingAsOfDate)
  if (dueTimestamp === null || asOfTimestamp === null) return null

  const daysPastDue = Math.floor(
    (asOfTimestamp - dueTimestamp) / MILLISECONDS_PER_DAY,
  )
  if (daysPastDue <= 0) return 'current'
  if (daysPastDue <= 30) return 'past_due_1_30'
  if (daysPastDue <= 60) return 'past_due_31_60'
  if (daysPastDue <= 90) return 'past_due_61_90'
  return 'past_due_90_plus'
}

function finiteAmount(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  const amount = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(amount) ? amount : null
}

function bucketDefinition(key: LockboxDueDateBucketKey) {
  return LOCKBOX_DUE_DATE_BUCKETS.find(
    (definition) => definition.key === key,
  ) as typeof LOCKBOX_DUE_DATE_BUCKETS[number]
}

/**
 * Builds a read-only view of every supplied ERP open item. Items are grouped
 * by their exact due date, with signed credit amounts reducing each group.
 * No allocation objects are accepted or returned, which keeps the helper from
 * mutating the review draft.
 */
export function buildLockboxDueDateSummary<
  T extends LockboxDueDateOpenItem,
>(
  openItems: T[],
  agingAsOfDate: unknown,
  getSignedAmount: (item: T) => unknown,
): LockboxDueDateSummaryResult {
  const grouped = new Map<string, {
    dueDate: string
    bucketKey: LockboxDueDateBucketKey
    count: number
    total: number
  }>()
  let omittedItemCount = 0

  openItems.forEach((item) => {
    const dueDate = canonicalDate(item.due_date)
    const amount = finiteAmount(getSignedAmount(item))
    const bucketKey = dueDate
      ? (
        bucketFromDates(dueDate, agingAsOfDate)
        || explicitBucket(item.aging_bucket || item.due_date_bucket)
      )
      : null

    if (!dueDate || amount === null || !bucketKey) {
      omittedItemCount += 1
      return
    }

    const existing = grouped.get(dueDate)
    if (existing) {
      existing.count += 1
      existing.total += amount
      return
    }

    grouped.set(dueDate, {
      dueDate,
      bucketKey,
      count: 1,
      total: amount,
    })
  })

  const groups = Array.from(grouped.values())
    .map((group): LockboxDueDateSummaryGroup => {
      const total = Number(group.total.toFixed(2))
      return {
        dueDate: group.dueDate,
        bucketKey: group.bucketKey,
        bucketLabel: bucketDefinition(group.bucketKey).label,
        balanceType: total < 0 ? 'Credit' : 'Debit',
        count: group.count,
        total,
      }
    })
    .sort((left, right) => {
      const bucketDifference = (
        bucketDefinition(left.bucketKey).order
        - bucketDefinition(right.bucketKey).order
      )
      if (bucketDifference !== 0) return bucketDifference
      return right.dueDate.localeCompare(left.dueDate)
    })

  return {
    groups,
    sourceItemCount: openItems.length,
    summarizedItemCount: openItems.length - omittedItemCount,
    omittedItemCount,
  }
}
