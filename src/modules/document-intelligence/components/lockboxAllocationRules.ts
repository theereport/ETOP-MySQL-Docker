import type {
  LockboxRecommendation,
} from './lockboxRecommendation'
import { isValidErpInvoiceNumber } from './erpInvoiceNumber'

type NumericValue = string | number | null | undefined

export type LegacyInvoiceDetail = {
  customer_number?: string | number | null
  invoice_number?: string | number | null
  invoice_date?: string | null
  due_date?: string | null
  transaction_type?: string | null
  transaction_type_code?: string | null
  entry_type?: string | null
  document_type?: string | null
  debit_credit?: string | null
  invoice_count?: number | null
  open_item_key?: string | null
  reference_number?: string | number | null
  signed_amount?: NumericValue
  transaction_amount?: NumericValue
  amount?: NumericValue
  debit_amount?: NumericValue
  credit_amount?: NumericValue
  original_amount?: NumericValue
  open_balance?: NumericValue
  current_amount?: NumericValue
  open_amount?: NumericValue
  recommended_amount?: NumericValue
  suggested_apply_amount?: NumericValue
  due_date_bucket?: string | null
  aging_bucket?: string | null
}

type LegacyCombinationMatch = {
  invoice_numbers?: Array<string | number>
  invoices?: Array<string | LegacyInvoiceDetail>
  total_amount?: NumericValue
  matched_amount?: NumericValue
  payment_total?: NumericValue
  due_dates?: string[]
  earliest_due_date?: string | null
  latest_due_date?: string | null
}

type LegacyCombinationResult = {
  matches?: LegacyCombinationMatch[]
  recommended_invoice_numbers?: Array<string | number>
  recommended_invoices?: LegacyInvoiceDetail[]
  invoice_details?: LegacyInvoiceDetail[]
  candidates?: LegacyInvoiceDetail[]
}

export type LegacyCashApplicationRecommendation = {
  customer_number?: string | number
  status?: string
  confidence_score?: number
  recommended_invoice_numbers?: Array<string | number>
  reasons?: string[]
  combination_result?: LegacyCombinationResult | null
}

type ExactDueDateGroup = {
  dueDate: string
  details: Array<Required<
    Pick<LegacyInvoiceDetail, 'invoice_number' | 'due_date'>
  > & LegacyInvoiceDetail & { applyAmount: number }>
  total: number
}

const AMOUNT_TOLERANCE = 0.01
const CREDIT_TYPE = /^(?:c|cr|credit|credit memo|credit adjustment)$/i
const DEBIT_TYPE = /^(?:d|dr|debit)$/i

function normalizeInvoiceNumber(value: unknown): string {
  return String(value ?? '').replace(/\D/g, '')
}

function numericValue(...values: NumericValue[]): number | null {
  for (const value of values) {
    if (value === null || value === undefined || value === '') continue
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

function transactionType(detail: LegacyInvoiceDetail): string {
  return [
    detail.transaction_type,
    detail.transaction_type_code,
    detail.entry_type,
    detail.document_type,
  ].find((value) => typeof value === 'string' && value.trim())?.trim() ?? ''
}

export type LegacyOpenItemIdentity = {
  key: string
  displayNumber: string
  normalizedInvoiceNumber: string
  allocationKind: 'invoice' | 'service_charge'
  rawTransactionType: string
  openItemKey: string
  invoiceCount: number | null
}

export function getLegacyOpenItemIdentity(
  detail: LegacyInvoiceDetail,
): LegacyOpenItemIdentity | null {
  const rawTransactionType = transactionType(detail)
  const normalizedTransactionType = rawTransactionType.toUpperCase()
  const rawInvoiceNumber = String(detail.invoice_number ?? '').trim()
  const normalizedInvoiceNumber = normalizeInvoiceNumber(rawInvoiceNumber)
  const invoiceCount = detail.invoice_count === null
    || detail.invoice_count === undefined
    ? null
    : Number(detail.invoice_count)

  if (normalizedTransactionType === 'SC') {
    const referenceNumber = String(detail.reference_number ?? '').trim()
    const displayNumber = rawInvoiceNumber
      || referenceNumber
      || `SC ${invoiceCount ?? 'open item'}`
    const openItemKey = String(detail.open_item_key ?? '').trim() || [
      String(detail.customer_number ?? '').trim(),
      'SC',
      rawInvoiceNumber || referenceNumber,
      invoiceCount ?? '',
    ].join('|')
    return {
      key: `open:${openItemKey}`,
      displayNumber,
      normalizedInvoiceNumber: '',
      allocationKind: 'service_charge',
      rawTransactionType: rawTransactionType || 'SC',
      openItemKey,
      invoiceCount,
    }
  }

  if (!isValidErpInvoiceNumber(normalizedInvoiceNumber)) return null
  return {
    key: `invoice:${normalizedInvoiceNumber}`,
    displayNumber: normalizedInvoiceNumber,
    normalizedInvoiceNumber,
    allocationKind: 'invoice',
    rawTransactionType,
    openItemKey: String(detail.open_item_key ?? '').trim(),
    invoiceCount,
  }
}

export function isLegacyServiceCharge(
  detail: LegacyInvoiceDetail,
): boolean {
  return getLegacyOpenItemIdentity(detail)?.allocationKind === 'service_charge'
}

export type InvoiceBusinessEffect = {
  businessType: 'debit' | 'credit'
  amount: number | null
  rawTransactionType: string
  negativeDebit: boolean
}

export function getInvoiceBusinessEffect(
  detail: LegacyInvoiceDetail,
): InvoiceBusinessEffect {
  const rawTransactionType = transactionType(detail)
  const signedCandidates = [
    detail.signed_amount,
    detail.transaction_amount,
    detail.open_balance,
    detail.current_amount,
    detail.open_amount,
    detail.original_amount,
    detail.amount,
    detail.recommended_amount,
    detail.suggested_apply_amount,
  ].map((value) => numericValue(value)).filter(
    (value): value is number => value !== null,
  )
  const openAmount = numericValue(
    detail.open_balance,
    detail.current_amount,
    detail.open_amount,
    detail.recommended_amount,
    detail.suggested_apply_amount,
    detail.original_amount,
    detail.transaction_amount,
    detail.signed_amount,
    detail.amount,
  )
  const explicitCreditAmount = numericValue(detail.credit_amount)
  const negativeDebit = (
    DEBIT_TYPE.test(rawTransactionType)
    && signedCandidates.some((value) => value < 0)
  )
  const debitCredit = String(detail.debit_credit ?? '').trim()
  const isCredit = (
    CREDIT_TYPE.test(rawTransactionType)
    || /^(?:c|cr|credit)$/i.test(debitCredit)
    || negativeDebit
    || (explicitCreditAmount !== null && explicitCreditAmount !== 0)
    || signedCandidates.some((value) => value < 0)
  )

  return {
    businessType: isCredit ? 'credit' : 'debit',
    amount: openAmount === null
      ? null
      : isCredit
        ? -Math.abs(openAmount)
        : Math.abs(openAmount),
    rawTransactionType,
    negativeDebit,
  }
}

function normalizedDate(value: unknown): string {
  if (typeof value !== 'string' || !value.trim()) return ''
  const text = value.trim()

  const isoMatch = text.match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (isoMatch) return `${isoMatch[1]}-${isoMatch[2]}-${isoMatch[3]}`

  const compactIsoMatch = text.match(/^(\d{4})(\d{2})(\d{2})$/)
  if (compactIsoMatch) {
    return [
      compactIsoMatch[1],
      compactIsoMatch[2],
      compactIsoMatch[3],
    ].join('-')
  }

  const usMatch = text.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$/)
  if (!usMatch) return ''

  const year = usMatch[3].length === 2
    ? `20${usMatch[3]}`
    : usMatch[3]
  return [
    year,
    usMatch[1].padStart(2, '0'),
    usMatch[2].padStart(2, '0'),
  ].join('-')
}

export function normalizeLockboxPaymentDate(value: unknown): string {
  return normalizedDate(value)
}

function displayDate(value: string): string {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!match) return value
  return `${Number(match[2])}/${Number(match[3])}/${match[1].slice(-2)}`
}

function invoiceDetails(
  recommendation: LegacyCashApplicationRecommendation,
): LegacyInvoiceDetail[] {
  const result = recommendation.combination_result
  if (!result) return []

  const nestedMatchDetails = (result.matches ?? []).flatMap((match) => (
    (match.invoices ?? []).filter(
      (invoice): invoice is LegacyInvoiceDetail => (
        typeof invoice === 'object'
        && invoice !== null
      ),
    )
  ))

  const values = [
    ...(result.recommended_invoices ?? []),
    ...(result.invoice_details ?? []),
    ...(result.candidates ?? []),
    ...nestedMatchDetails,
  ]

  const byInvoice = new Map<string, LegacyInvoiceDetail>()
  for (const detail of values) {
    const identity = getLegacyOpenItemIdentity(detail)
    if (!identity) continue
    const current = byInvoice.get(identity.key)
    byInvoice.set(identity.key, {
      ...current,
      ...detail,
      invoice_number: identity.displayNumber,
      transaction_type: identity.rawTransactionType,
      open_item_key: identity.openItemKey || null,
      invoice_count: identity.invoiceCount,
      due_date: detail.due_date || current?.due_date || null,
    })
  }
  return [...byInvoice.values()]
}

function exactDueDateGroups(
  recommendation: LegacyCashApplicationRecommendation,
  checkAmount: number,
): ExactDueDateGroup[] {
  const groups = new Map<string, ExactDueDateGroup['details']>()

  for (const detail of invoiceDetails(recommendation)) {
    const identity = getLegacyOpenItemIdentity(detail)
    const dueDate = normalizedDate(detail.due_date)
    const applyAmount = getInvoiceBusinessEffect(detail).amount
    if (
      !identity
      || !dueDate
      || applyAmount === null
    ) {
      continue
    }

    const group = groups.get(dueDate) ?? []
    group.push({
      ...detail,
      invoice_number: identity.displayNumber,
      transaction_type: identity.rawTransactionType,
      open_item_key: identity.openItemKey || null,
      invoice_count: identity.invoiceCount,
      due_date: dueDate,
      applyAmount,
    })
    groups.set(dueDate, group)
  }

  return [...groups.entries()]
    .map(([dueDate, details]) => ({
      dueDate,
      details,
      total: Number(
        details.reduce(
          (total, detail) => total + detail.applyAmount,
          0,
        ).toFixed(2),
      ),
    }))
    .filter((group) => (
      group.details.length > 0
      && Math.abs(group.total - checkAmount) <= AMOUNT_TOLERANCE
    ))
    .sort((left, right) => (
      left.dueDate.localeCompare(right.dueDate)
      || left.details.length - right.details.length
    ))
}

function confidenceValue(value: number | undefined): number {
  if (!Number.isFinite(value)) return 0.9
  const confidence = Number(value)
  return confidence > 1
    ? Math.min(confidence / 100, 1)
    : Math.max(0, Math.min(confidence, 1))
}

export function shouldEvaluateDueDatePriority(
  recommendation: LockboxRecommendation | null,
): boolean {
  if (!recommendation) return true
  if (recommendation.suggested_allocations.length === 0) return true
  return recommendation.decision_reasons.some((reason) => (
    /aging bucket|eom aging/i.test(reason)
  ))
}

export function applyExactDueDatePriority(
  current: LockboxRecommendation | null,
  legacy: LegacyCashApplicationRecommendation,
  checkAmount: number,
): LockboxRecommendation | null {
  const groups = exactDueDateGroups(legacy, checkAmount)
  if (groups.length !== 1) return current

  const selected = groups[0]
  const confidence = confidenceValue(legacy.confidence_score)
  const includesServiceCharge = selected.details.some((detail) => (
    getLegacyOpenItemIdentity(detail)?.allocationKind === 'service_charge'
  ))
  const reason = (
    `Check amount exactly matches all ${selected.details.length} open `
    + `${includesServiceCharge ? 'item(s)' : 'invoice(s)'} due `
    + `${displayDate(selected.dueDate)}.`
  )
  const existingReasons = current?.decision_reasons ?? []
  const decisionReasons = [
    reason,
    ...existingReasons.filter((value) => (
      !/aging bucket|eom aging/i.test(value)
      && value !== reason
    )),
  ]

  return {
    status: 'recommended',
    transaction_id: current?.transaction_id ?? '',
    customer_match: current?.customer_match ?? null,
    decision: {
      status: 'recommended',
      overall_confidence: confidence,
      payment_intent: {
        intent_type: 'same_due_date_exact_match',
        confidence,
        explanation: [reason],
      },
      decision_reasons: decisionReasons,
      warnings: current?.decision?.warnings ?? [],
    },
    suggested_allocations: selected.details.map((detail) => {
      const identity = getLegacyOpenItemIdentity(detail)
      return {
        invoice_number: String(detail.invoice_number),
        open_amount: detail.applyAmount,
        suggested_apply_amount: detail.applyAmount,
        invoice_date: detail.invoice_date ?? null,
        due_date: selected.dueDate,
        aging_bucket:
          detail.due_date_bucket
          || detail.aging_bucket
          || selected.dueDate,
        transaction_type:
          getInvoiceBusinessEffect(detail).businessType,
        erp_transaction_type:
          getInvoiceBusinessEffect(detail).rawTransactionType || null,
        negative_debit_credit:
          getInvoiceBusinessEffect(detail).negativeDebit,
        allocation_kind: identity?.allocationKind,
        open_item_key: identity?.openItemKey,
        normalized_invoice_number: identity?.normalizedInvoiceNumber,
        invoice_count: identity?.invoiceCount,
        confidence,
        reason,
      }
    }),
    check_amount: checkAmount,
    suggested_total: selected.total,
    difference: Number((checkAmount - selected.total).toFixed(2)),
    can_auto_approve: false,
    decision_reasons: decisionReasons,
    warnings: current?.warnings ?? [],
    allocation_basis: 'same_due_date_exact_match',
  }
}
