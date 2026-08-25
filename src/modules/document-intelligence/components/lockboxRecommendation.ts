import { API_BASE } from '../../../api/client'
import {
  applyExactDueDatePriority,
  getLegacyOpenItemIdentity,
  getInvoiceBusinessEffect,
  normalizeLockboxPaymentDate,
} from './lockboxAllocationRules'
import type {
  LegacyCashApplicationRecommendation,
  LegacyInvoiceDetail,
} from './lockboxAllocationRules'
import { normalizeErpInvoiceNumber } from './erpInvoiceNumber'

export { normalizeErpInvoiceNumber } from './erpInvoiceNumber'

export type LockboxRecommendation = {
  status:
    | 'recommended'
    | 'review_required'
    | 'customer_not_found'
    | 'no_invoice_match'
  transaction_id: string
  customer_match?: {
    customer_number: string
    customer_name: string
    confidence: number
    matched_on: string[]
    warnings: string[]
    customer_phone?: string | null
    phone_number?: string | null
    customer_address_line_1?: string | null
    customer_address_line_2?: string | null
    address_line_1?: string | null
    address_line_2?: string | null
    customer_city?: string | null
    city?: string | null
    customer_state?: string | null
    state?: string | null
    customer_postal_code?: string | null
    postal_code?: string | null
  } | null
  decision?: {
    status: string
    overall_confidence: number
    payment_intent: {
      intent_type: string
      confidence: number
      explanation: string[]
    }
    decision_reasons: string[]
    warnings: string[]
  } | null
  suggested_allocations: Array<{
    invoice_number: string
    open_amount: string | number
    suggested_apply_amount: string | number
    invoice_date?: string | null
    due_date?: string | null
    aging_bucket?: string | null
    transaction_type?: 'debit' | 'credit'
    erp_transaction_type?: string | null
    negative_debit_credit?: boolean
    allocation_kind?: 'invoice' | 'service_charge'
    open_item_key?: string
    normalized_invoice_number?: string
    invoice_count?: number | null
    confidence: number
    reason: string
  }>
  check_amount: string | number
  suggested_total: string | number
  difference: string | number
  can_auto_approve: boolean
  decision_reasons: string[]
  warnings: string[]
  allocation_basis?:
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
}

export function getValidErpInvoiceNumbers(
  allocations: Array<{ invoice_number: string }>,
): string[] {
  return allocations.reduce<string[]>((invoiceNumbers, allocation) => {
    const invoiceNumber = normalizeErpInvoiceNumber(
      allocation.invoice_number.trim(),
    )
    if (invoiceNumber && !invoiceNumbers.includes(invoiceNumber)) {
      invoiceNumbers.push(invoiceNumber)
    }
    return invoiceNumbers
  }, [])
}

export async function getLockboxRecommendation(
  transaction: {
    transaction_id: string
    check_amount: number
    customer_number?: string
    printed_customer_number?: string
    customer_name?: string
    customer_phone?: string
    customer_address_line_1?: string
    customer_address_line_2?: string
    customer_city?: string
    customer_state?: string
    customer_postal_code?: string
    aba_routing?: string
    account_number?: string
    allocations?: Array<{ invoice_number: string }>
  },
  signal?: AbortSignal,
): Promise<LockboxRecommendation> {
  const response = await fetch(
    `${API_BASE}/documents/cash-application/recommend`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      signal,
      body: JSON.stringify({
        transaction_id: transaction.transaction_id,
        check_amount: transaction.check_amount,
        identity: {
          customer_number: transaction.customer_number || '',
          printed_customer_number:
            transaction.printed_customer_number || '',
          customer_name: transaction.customer_name || '',
          customer_phone: transaction.customer_phone || '',
          phone_number: transaction.customer_phone || '',
          customer_address_line_1:
            transaction.customer_address_line_1 || '',
          address_line_1:
            transaction.customer_address_line_1 || '',
          customer_address_line_2:
            transaction.customer_address_line_2 || '',
          address_line_2:
            transaction.customer_address_line_2 || '',
          customer_city: transaction.customer_city || '',
          city: transaction.customer_city || '',
          customer_state: transaction.customer_state || '',
          state: transaction.customer_state || '',
          customer_postal_code:
            transaction.customer_postal_code || '',
          postal_code:
            transaction.customer_postal_code || '',
          aba_routing: transaction.aba_routing || '',
          account_number: transaction.account_number || '',
        },
        extracted_invoice_numbers: getValidErpInvoiceNumbers(
          transaction.allocations || [],
        ),
      }),
    },
  )

  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(
      payload?.detail ||
        'Unable to load the cash-application recommendation.',
    )
  }

  return response.json()
}

type LegacyRecommendationEnvelope = {
  recommendation?: LegacyCashApplicationRecommendation
}

type OpenInvoicesEnvelope = {
  invoices?: LegacyInvoiceDetail[]
}

export type LockboxRecommendationCache = {
  openInvoices: Map<string, Promise<LegacyInvoiceDetail[] | null>>
}

export function createLockboxRecommendationCache():
  LockboxRecommendationCache {
  return {
    openInvoices: new Map(),
  }
}

function legacyApiRoot(): string {
  return API_BASE.replace(/\/api\/v1\/?$/, '')
}

function waitForRequest<T>(
  request: Promise<T>,
  signal?: AbortSignal,
): Promise<T> {
  if (!signal) return request
  if (signal.aborted) {
    return Promise.reject(
      new DOMException('The request was aborted.', 'AbortError'),
    )
  }

  return new Promise<T>((resolve, reject) => {
    const abort = () => {
      reject(new DOMException('The request was aborted.', 'AbortError'))
    }
    signal.addEventListener('abort', abort, { once: true })
    request.then(
      (value) => {
        signal.removeEventListener('abort', abort)
        resolve(value)
      },
      (error) => {
        signal.removeEventListener('abort', abort)
        reject(error)
      },
    )
  })
}

export async function getLockboxOpenInvoices(
  customerNumber: string,
  paymentDate: string,
  signal?: AbortSignal,
  cache?: LockboxRecommendationCache,
): Promise<LegacyInvoiceDetail[] | null> {
  const cacheKey = `${customerNumber}|${paymentDate || 'current'}`
  let request = cache?.openInvoices.get(cacheKey)

  if (!request) {
    const openInvoiceParams = new URLSearchParams()
    if (paymentDate) {
      openInvoiceParams.set('aging_as_of_date', paymentDate)
    }
    const openInvoiceQuery = openInvoiceParams.size > 0
      ? `?${openInvoiceParams.toString()}`
      : ''
    request = fetch(
      `${legacyApiRoot()}/api/test/open-invoices/`
      + `${encodeURIComponent(customerNumber)}`
      + openInvoiceQuery,
    ).then(async (response) => {
      if (!response.ok) {
        const payload = await response.json().catch(() => null)
        throw new Error(
          payload?.detail
          || `ERP open-A/R retrieval failed with HTTP ${response.status}.`,
        )
      }
      const envelope = await response.json() as OpenInvoicesEnvelope
      return envelope.invoices ?? []
    })
    cache?.openInvoices.set(cacheKey, request)
  }

  try {
    return await waitForRequest(request, signal)
  } catch (error) {
    cache?.openInvoices.delete(cacheKey)
    throw error
  }
}

export function reconcileRecommendationWithOpenInvoices(
  current: LockboxRecommendation,
  openInvoices: LegacyInvoiceDetail[],
): LockboxRecommendation {
  const byOpenItemKey = new Map<string, LegacyInvoiceDetail>()
  const byInvoiceNumber = new Map<string, LegacyInvoiceDetail>()
  for (const invoice of openInvoices) {
    const identity = getLegacyOpenItemIdentity(invoice)
    if (!identity) continue
    byOpenItemKey.set(identity.key, invoice)
    if (identity.normalizedInvoiceNumber) {
      byInvoiceNumber.set(identity.normalizedInvoiceNumber, invoice)
    }
  }
  const normalizedCreditInvoices: string[] = []
  const suggestedAllocations = current.suggested_allocations.map(
    (suggestion) => {
      const invoiceNumber = normalizeErpInvoiceNumber(
        suggestion.invoice_number,
      )
      const suggestionIdentity = getLegacyOpenItemIdentity({
        customer_number: current.customer_match?.customer_number,
        invoice_number: suggestion.invoice_number,
        transaction_type: suggestion.erp_transaction_type,
        open_item_key: suggestion.open_item_key,
        invoice_count: suggestion.invoice_count,
      })
      const invoice = (
        suggestionIdentity
          ? byOpenItemKey.get(suggestionIdentity.key)
          : undefined
      ) || byInvoiceNumber.get(invoiceNumber)
      if (!invoice) return suggestion

      const invoiceIdentity = getLegacyOpenItemIdentity(invoice)
      const effect = getInvoiceBusinessEffect(invoice)
      const suggestedValue = Number(suggestion.suggested_apply_amount)
      const fallbackValue = effect.amount ?? suggestedValue
      const signedApplyAmount = effect.businessType === 'credit'
        ? -Math.abs(
          Number.isFinite(suggestedValue)
            ? suggestedValue
            : fallbackValue,
        )
        : Math.abs(
          Number.isFinite(suggestedValue)
            ? suggestedValue
            : fallbackValue,
        )

      if (effect.businessType === 'credit') {
        normalizedCreditInvoices.push(
          invoiceIdentity?.displayNumber || suggestion.invoice_number,
        )
      }

      return {
        ...suggestion,
        open_amount: effect.amount ?? suggestion.open_amount,
        suggested_apply_amount: signedApplyAmount,
        invoice_date: invoice.invoice_date ?? suggestion.invoice_date ?? null,
        due_date: invoice.due_date ?? suggestion.due_date ?? null,
        aging_bucket:
          invoice.due_date_bucket
          || invoice.aging_bucket
          || suggestion.aging_bucket
          || null,
        transaction_type: effect.businessType,
        erp_transaction_type: effect.rawTransactionType || null,
        negative_debit_credit: effect.negativeDebit,
        allocation_kind:
          invoiceIdentity?.allocationKind || suggestion.allocation_kind,
        open_item_key:
          invoiceIdentity?.openItemKey || suggestion.open_item_key,
        normalized_invoice_number:
          invoiceIdentity?.normalizedInvoiceNumber
          || suggestion.normalized_invoice_number,
        invoice_count:
          invoiceIdentity?.invoiceCount ?? suggestion.invoice_count,
      }
    },
  )
  const suggestedTotal = Number(
    suggestedAllocations.reduce(
      (total, allocation) => (
        total + Number(allocation.suggested_apply_amount || 0)
      ),
      0,
    ).toFixed(2),
  )
  const difference = Number(
    (Number(current.check_amount) - suggestedTotal).toFixed(2),
  )
  const creditReason = normalizedCreditInvoices.length > 0
    ? (
      `${normalizedCreditInvoices.length} ERP credit `
      + `${normalizedCreditInvoices.length === 1 ? 'entry was' : 'entries were'} `
      + 'applied as a negative amount.'
    )
    : ''
  const decisionReasons = creditReason
    ? [
      ...current.decision_reasons.filter(
        (reason) => reason !== creditReason,
      ),
      creditReason,
    ]
    : current.decision_reasons
  const status = Math.abs(difference) <= 0.01
    ? current.status
    : 'review_required'

  return {
    ...current,
    status,
    decision: current.decision
      ? {
        ...current.decision,
        status: Math.abs(difference) <= 0.01
          ? current.decision.status
          : 'review_required',
        decision_reasons: creditReason
          ? [
            ...current.decision.decision_reasons.filter(
              (reason) => reason !== creditReason,
            ),
            creditReason,
          ]
          : current.decision.decision_reasons,
      }
      : current.decision,
    suggested_allocations: suggestedAllocations,
    suggested_total: suggestedTotal,
    difference,
    decision_reasons: decisionReasons,
    can_auto_approve: false,
  }
}

export async function applyDueDateAllocationPriority(
  current: LockboxRecommendation | null,
  transaction: {
    customer_number: string
    check_amount: number
    payment_date: string
    invoice_numbers?: string[]
  },
  signal?: AbortSignal,
  cache?: LockboxRecommendationCache,
): Promise<LockboxRecommendation | null> {
  const paymentDate = normalizeLockboxPaymentDate(
    transaction.payment_date,
  )
  if (!transaction.customer_number) return current

  const apiRoot = legacyApiRoot()
  try {
    const openInvoices = await getLockboxOpenInvoices(
      transaction.customer_number,
      paymentDate,
      signal,
      cache,
    )
    if (openInvoices) {
      const reconciled = current
        ? reconcileRecommendationWithOpenInvoices(current, openInvoices)
        : current
      const openInvoicePriority = applyExactDueDatePriority(
        reconciled,
        {
          customer_number: transaction.customer_number,
          confidence_score: 1,
          combination_result: {
            invoice_details: openInvoices,
          },
        },
        transaction.check_amount,
      )
      if (openInvoicePriority !== reconciled) {
        return openInvoicePriority
      }
      return reconciled
    }
  } catch (error) {
    if (signal?.aborted) throw error
    // Preserve the broader recommendation endpoint as the compatibility
    // fallback when the direct open-invoice read is unavailable.
  }

  const params = new URLSearchParams({
    payment_amount: transaction.check_amount.toFixed(2),
  })
  if (paymentDate) params.set('aging_as_of_date', paymentDate)
  ;(transaction.invoice_numbers ?? []).forEach((invoiceNumber) => {
    params.append('invoice_numbers', invoiceNumber)
  })

  const response = await fetch(
    `${apiRoot}/api/test/cash-application-recommendation/`
    + `${encodeURIComponent(transaction.customer_number)}?${params.toString()}`,
    { signal },
  )
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(
      payload?.detail
      || 'Unable to evaluate due-date allocation priority.',
    )
  }

  const envelope = await response.json() as LegacyRecommendationEnvelope
  if (!envelope.recommendation) return current

  return applyExactDueDatePriority(
    current,
    envelope.recommendation,
    transaction.check_amount,
  )
}
