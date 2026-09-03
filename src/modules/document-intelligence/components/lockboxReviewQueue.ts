type LockboxQueueTransaction = {
  transaction_id: string
  status: string
}

type LockboxReasonTransaction = {
  exception_analysis?: unknown
  result?: unknown
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
}

export function primaryLockboxReasonCode(
  transaction: LockboxReasonTransaction | null | undefined,
): string {
  const result = record(transaction?.result)
  const evidence = record(result.evidence)
  const analysis = record(
    transaction?.exception_analysis
    ?? result.exception_analysis
    ?? evidence.exception_analysis,
  )
  const primaryReason = record(analysis.primary_reason)
  return typeof primaryReason.code === 'string'
    ? primaryReason.code
    : ''
}

export function transactionNeedsProfessionalReview(
  transaction: Pick<LockboxQueueTransaction, 'status'>,
): boolean {
  return (
    transaction.status !== 'approved'
    && transaction.status !== 'corrected'
    && transaction.status !== 'balanced'
    && transaction.status !== 'held'
    && transaction.status !== 'carryover'
  )
}

export function transactionIsHeld(
  transaction: Pick<LockboxQueueTransaction, 'status'>,
): boolean {
  return transaction.status === 'held'
}

export function transactionIsCarryover(
  transaction: Pick<LockboxQueueTransaction, 'status'>,
): boolean {
  return transaction.status === 'carryover'
}

export function nextProfessionalReviewTransactionId(
  transactions: LockboxQueueTransaction[],
  currentTransactionId: string,
): string {
  const currentIndex = transactions.findIndex(
    (transaction) => transaction.transaction_id === currentTransactionId,
  )
  const orderedRemainder = currentIndex >= 0
    ? [
      ...transactions.slice(currentIndex + 1),
      ...transactions.slice(0, currentIndex),
    ]
    : transactions

  return orderedRemainder.find(transactionNeedsProfessionalReview)
    ?.transaction_id ?? ''
}

export function nextLockboxQueueTransactionId(
  transactions: LockboxQueueTransaction[],
  currentTransactionId: string,
): string {
  if (transactions.length <= 1) return ''
  const currentIndex = transactions.findIndex(
    (transaction) => transaction.transaction_id === currentTransactionId,
  )
  const orderedRemainder = currentIndex >= 0
    ? [
      ...transactions.slice(currentIndex + 1),
      ...transactions.slice(0, currentIndex),
    ]
    : transactions

  return orderedRemainder.find(
    (transaction) => transaction.transaction_id !== currentTransactionId,
  )?.transaction_id ?? ''
}

export function previousLockboxQueueTransactionId(
  transactions: LockboxQueueTransaction[],
  currentTransactionId: string,
): string {
  if (transactions.length <= 1) return ''
  const currentIndex = transactions.findIndex(
    (transaction) => transaction.transaction_id === currentTransactionId,
  )
  const orderedRemainder = currentIndex >= 0
    ? [
      ...transactions.slice(0, currentIndex).reverse(),
      ...transactions.slice(currentIndex + 1).reverse(),
    ]
    : [...transactions].reverse()

  return orderedRemainder.find(
    (transaction) => transaction.transaction_id !== currentTransactionId,
  )?.transaction_id ?? ''
}
