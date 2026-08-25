import {
  getCustomerSummary,
} from '../../../api/customers'
import type {
  CustomerSummary,
} from '../../../features/customer360/types'

import {
  resolveLockboxCustomer,
  resolveLockboxInvoiceOwners,
} from '../api'
import type {
  BulkInvoiceOwnerCustomer,
  CustomerMatchCandidate,
  ReviewedLockboxTransaction,
} from '../types'

import {
  applyDueDateAllocationPriority,
  createLockboxRecommendationCache,
  getLockboxRecommendation,
  getValidErpInvoiceNumbers,
} from './lockboxRecommendation'
import type {
  LockboxRecommendation,
  LockboxRecommendationCache,
} from './lockboxRecommendation'
export type PreparedErpCustomer = {
  customerNumber: string
  customerName: string
  phone: string
  addressLine1: string
  addressLine2: string
  city: string
  state: string
  postalCode: string
}

export type LockboxPreparationStatus =
  | 'ready'
  | 'needs_review'
  | 'failed'

export type PreparedLockboxTransaction = {
  transactionId: string
  status: LockboxPreparationStatus
  preparedAt: string
  invoiceNumbers: string[]
  customer: PreparedErpCustomer | null
  customerSource: 'invoice' | 'recommendation' | 'saved' | null
  recommendation: LockboxRecommendation | null
  message: string
  warnings: string[]
}

export type LockboxPreparationContext = {
  invoiceOwners: Map<string, string[]>
  invoiceCustomers: Map<string, PreparedErpCustomer>
  customerSummaries: Map<string, Promise<PreparedErpCustomer>>
  recommendationCache: LockboxRecommendationCache
  warnings: string[]
}

const BULK_INVOICE_CHUNK_SIZE = 250

const US_STATE_CODES = new Set([
  'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
  'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
  'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
  'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
  'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
  'DC',
])

function firstText(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) {
      return value.trim()
    }
  }
  return ''
}

function normalizePostalCode(value: unknown): string {
  const text = firstText(value)
  const match = text.match(/\b(\d{5})(?:-?(\d{4}))?\b/)
  if (!match) return text.replace(/-+$/, '')
  return match[2] ? `${match[1]}-${match[2]}` : match[1]
}

function parseCityStatePostal(value: unknown): {
  city: string
  state: string
  postalCode: string
} | null {
  const text = firstText(value)
  const match = text.match(
    /^(.+?)(?:,\s*|\s+)([A-Z]{2})(?:\s+(\d{5}(?:-\d{0,4})?))?$/i,
  )
  if (!match) return null

  const state = match[2].toUpperCase()
  if (!US_STATE_CODES.has(state)) return null

  return {
    city: match[1].trim(),
    state,
    postalCode: normalizePostalCode(match[3]),
  }
}

export function normalizePreparedErpCustomer(
  details: Partial<PreparedErpCustomer> & Pick<
    PreparedErpCustomer,
    'customerNumber'
  >,
  addressLines: string[] = [],
): PreparedErpCustomer {
  let addressLine1 = firstText(details.addressLine1, addressLines[0])
  let addressLine2 = firstText(details.addressLine2)
  let city = firstText(details.city)
  let state = firstText(details.state).toUpperCase()
  let postalCode = normalizePostalCode(details.postalCode)

  const supplementalLines = [
    addressLine2,
    ...addressLines.slice(1),
  ].filter((line, index, lines) => (
    Boolean(line)
    && line !== addressLine1
    && lines.indexOf(line) === index
  ))

  for (const line of supplementalLines) {
    const locality = parseCityStatePostal(line)
    if (locality) {
      city = locality.city || city
      state = locality.state || state
      postalCode = locality.postalCode || postalCode
      if (line === addressLine2) addressLine2 = ''
      continue
    }

    const postalOnly = normalizePostalCode(line)
    if (
      /^[\d\s-]+$/.test(line)
      && /^\d{5}(?:-\d{4})?$/.test(postalOnly)
    ) {
      postalCode = postalOnly
      continue
    }

    if (!addressLine2) addressLine2 = line
  }

  if (!addressLine1 && addressLine2) {
    addressLine1 = addressLine2
    addressLine2 = ''
  }

  return {
    customerNumber: String(details.customerNumber),
    customerName: firstText(details.customerName),
    phone: firstText(details.phone),
    addressLine1,
    addressLine2,
    city,
    state,
    postalCode,
  }
}

export function preparedCustomerFromSummary(
  summary: CustomerSummary,
): PreparedErpCustomer {
  const general = summary.general as CustomerSummary['general']
    & Record<string, unknown>
  const addressLines = Array.isArray(general.address_lines)
    ? general.address_lines.filter(
      (line): line is string => (
        typeof line === 'string'
        && Boolean(line.trim())
      ),
    )
    : []

  return normalizePreparedErpCustomer({
    customerNumber: String(summary.customer_number),
    customerName: summary.customer_name,
    phone: firstText(general.phone),
    addressLine1: firstText(
      general.address_line_1,
      addressLines[0],
    ),
    addressLine2: firstText(general.address_line_2),
    city: firstText(general.city),
    state: firstText(
      general.state,
      general.state_abbreviation,
      typeof general.state_code === 'string'
        ? general.state_code
        : '',
    ),
    postalCode: firstText(
      general.postal_code,
      general.zip_code,
    ),
  }, addressLines)
}

export function preparedCustomerFromCandidate(
  candidate: CustomerMatchCandidate,
): PreparedErpCustomer {
  return normalizePreparedErpCustomer({
    customerNumber: candidate.customer_number,
    customerName: candidate.customer_name,
    phone: candidate.phone,
    addressLine1: candidate.address_line_1,
    addressLine2: candidate.address_line_2,
    city: candidate.city,
    state: candidate.state,
    postalCode: candidate.postal_code,
  })
}

function preparedCustomerFromBulkInvoice(
  customer: BulkInvoiceOwnerCustomer,
): PreparedErpCustomer {
  return normalizePreparedErpCustomer({
    customerNumber: customer.customer_number,
    customerName: customer.customer_name,
    phone: customer.phone,
    addressLine1: customer.address_line_1,
    addressLine2: customer.address_line_2,
    city: customer.city,
    state: customer.state,
    postalCode: customer.postal_code,
  })
}

export function preparedCustomerFromRecommendation(
  match: NonNullable<LockboxRecommendation['customer_match']>,
): PreparedErpCustomer {
  return normalizePreparedErpCustomer({
    customerNumber: String(match.customer_number),
    customerName: match.customer_name,
    phone: firstText(match.customer_phone, match.phone_number),
    addressLine1: firstText(
      match.customer_address_line_1,
      match.address_line_1,
    ),
    addressLine2: firstText(
      match.customer_address_line_2,
      match.address_line_2,
    ),
    city: firstText(match.customer_city, match.city),
    state: firstText(match.customer_state, match.state),
    postalCode: firstText(
      match.customer_postal_code,
      match.postal_code,
    ),
  })
}

function recommendationInput(
  transaction: ReviewedLockboxTransaction,
  customer?: PreparedErpCustomer | null,
) {
  return {
    transaction_id: transaction.transaction_id,
    check_amount: transaction.check_amount,
    customer_number: (
      customer?.customerNumber
      || transaction.customer_number
      || ''
    ),
    printed_customer_number:
      transaction.printed_customer_number || '',
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
    aba_routing: transaction.aba_routing,
    account_number: transaction.account_number,
    allocations: transaction.allocations,
  }
}

export async function getCustomerAwareLockboxRecommendation(
  transaction: ReviewedLockboxTransaction,
  customer: PreparedErpCustomer,
  signal?: AbortSignal,
  context?: LockboxPreparationContext,
): Promise<{
  recommendation: LockboxRecommendation
  warnings: string[]
}> {
  let recommendation = await getLockboxRecommendation(
    recommendationInput(transaction, customer),
    signal,
  )
  const warnings = [...recommendation.warnings]

  try {
    const prioritized = await applyDueDateAllocationPriority(
      recommendation,
      {
        customer_number: customer.customerNumber,
        check_amount: transaction.check_amount,
        payment_date: transaction.date,
        invoice_numbers: getValidErpInvoiceNumbers(
          transaction.allocations,
        ),
      },
      signal,
      context?.recommendationCache,
    )
    if (prioritized) recommendation = prioritized
  } catch (error) {
    if (signal?.aborted) throw error
    warnings.push(
      error instanceof Error
        ? error.message
        : 'Due-date allocation analysis could not be completed.',
    )
  }

  return {
    recommendation,
    warnings: uniqueWarnings(warnings),
  }
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

async function loadCustomerMaster(
  customer: PreparedErpCustomer,
  signal?: AbortSignal,
  context?: LockboxPreparationContext,
): Promise<PreparedErpCustomer> {
  if (!context) {
    const summary = await getCustomerSummary(
      customer.customerNumber,
      signal,
    )
    return preparedCustomerFromSummary(summary)
  }

  let request = context.customerSummaries.get(
    customer.customerNumber,
  )
  if (!request) {
    request = getCustomerSummary(customer.customerNumber)
      .then(preparedCustomerFromSummary)
    context.customerSummaries.set(customer.customerNumber, request)
  }

  try {
    return await waitForRequest(request, signal)
  } catch (error) {
    context.customerSummaries.delete(customer.customerNumber)
    throw error
  }
}

function bulkInvoiceCustomer(
  invoiceNumbers: string[],
  context?: LockboxPreparationContext,
): PreparedErpCustomer | null {
  if (!context || invoiceNumbers.length === 0) return null

  const owners = new Set(
    invoiceNumbers.flatMap(
      (invoiceNumber) => (
        context.invoiceOwners.get(invoiceNumber) ?? []
      ),
    ),
  )
  if (owners.size !== 1) return null

  const customerNumber = [...owners][0]
  return (
    context.invoiceCustomers.get(customerNumber)
    ?? normalizePreparedErpCustomer({ customerNumber })
  )
}

export async function createLockboxPreparationContext(
  transactions: ReviewedLockboxTransaction[],
  signal?: AbortSignal,
): Promise<LockboxPreparationContext> {
  const context: LockboxPreparationContext = {
    invoiceOwners: new Map(),
    invoiceCustomers: new Map(),
    customerSummaries: new Map(),
    recommendationCache: createLockboxRecommendationCache(),
    warnings: [],
  }
  const invoiceNumbers = transactions.reduce<string[]>(
    (values, transaction) => {
      for (
        const invoiceNumber of getValidErpInvoiceNumbers(
          transaction.allocations,
        )
      ) {
        if (!values.includes(invoiceNumber)) {
          values.push(invoiceNumber)
        }
      }
      return values
    },
    [],
  )

  for (
    let offset = 0;
    offset < invoiceNumbers.length;
    offset += BULK_INVOICE_CHUNK_SIZE
  ) {
    try {
      const response = await resolveLockboxInvoiceOwners(
        invoiceNumbers.slice(
          offset,
          offset + BULK_INVOICE_CHUNK_SIZE,
        ),
        signal,
      )
      for (const [invoiceNumber, owners] of Object.entries(
        response.invoice_owners,
      )) {
        context.invoiceOwners.set(invoiceNumber, owners)
      }
      for (const customer of response.customers) {
        const prepared = preparedCustomerFromBulkInvoice(customer)
        context.invoiceCustomers.set(
          prepared.customerNumber,
          prepared,
        )
      }
      context.warnings.push(...response.warnings)
    } catch (error) {
      if (signal?.aborted) throw error
      context.warnings.push(
        error instanceof Error
          ? error.message
          : 'Bulk ERP invoice resolution was unavailable.',
      )
    }
  }

  return context
}

function invoiceMatched(
  recommendation: LockboxRecommendation | null,
): boolean {
  return Boolean(
    recommendation?.customer_match?.matched_on.some(
      (reason) => reason.toLowerCase().includes('invoice'),
    ),
  )
}

function uniqueWarnings(values: Array<string | undefined>): string[] {
  return values.reduce<string[]>((warnings, value) => {
    const warning = value?.trim()
    if (warning && !warnings.includes(warning)) warnings.push(warning)
    return warnings
  }, [])
}

export async function prepareLockboxTransaction(
  transaction: ReviewedLockboxTransaction,
  signal?: AbortSignal,
  context?: LockboxPreparationContext,
): Promise<PreparedLockboxTransaction> {
  const invoiceNumbers = getValidErpInvoiceNumbers(
    transaction.allocations,
  )
  const warnings: string[] = [...(context?.warnings ?? [])]
  let customer: PreparedErpCustomer | null = null
  let customerSource:
    PreparedLockboxTransaction['customerSource'] = null
  let discoveryRecommendation: LockboxRecommendation | null = null
  let finalRecommendation: LockboxRecommendation | null = null

  try {
    if (transaction.customer_number) {
      customer = normalizePreparedErpCustomer({
        customerNumber: transaction.customer_number,
        customerName: transaction.customer_name,
        phone:
          transaction.customer_phone
          || transaction.phone_number
          || '',
        addressLine1:
          transaction.customer_address_line_1
          || transaction.address_line_1
          || '',
        addressLine2:
          transaction.customer_address_line_2
          || transaction.address_line_2
          || '',
        city:
          transaction.customer_city
          || transaction.city
          || '',
        state:
          transaction.customer_state
          || transaction.state
          || '',
        postalCode:
          transaction.customer_postal_code
          || transaction.customer_zip
          || transaction.postal_code
          || '',
      })
      customerSource = 'saved'
    }

    if (!customer && invoiceNumbers.length > 0) {
      customer = bulkInvoiceCustomer(invoiceNumbers, context)
      if (customer) {
        customerSource = 'invoice'
      }
    }

    if (!customer && invoiceNumbers.length > 0) {
      try {
        const match = await resolveLockboxCustomer(
          {
            invoice_numbers: invoiceNumbers,
            phone:
              transaction.customer_phone
              || transaction.phone_number
              || '',
            address_line_1:
              transaction.customer_address_line_1
              || transaction.address_line_1
              || '',
            city:
              transaction.customer_city
              || transaction.city
              || '',
            state:
              transaction.customer_state
              || transaction.state
              || '',
            postal_code:
              transaction.customer_postal_code
              || transaction.customer_zip
              || transaction.postal_code
              || '',
            customer_name: transaction.customer_name || '',
            limit: 8,
          },
          signal,
        )
        warnings.push(...match.warnings)
        const candidate = match.recommended_customer
        const verifiedInvoices =
          candidate?.matched_invoice_numbers.filter(
            (invoiceNumber) => (
              invoiceNumbers.includes(invoiceNumber)
            ),
          ) ?? []
        if (
          match.auto_select
          && candidate
          && candidate.match_type === 'invoice'
          && verifiedInvoices.length > 0
        ) {
          customer = preparedCustomerFromCandidate(candidate)
          customerSource = 'invoice'
        }
      } catch (error) {
        if (signal?.aborted) throw error
        warnings.push(
          error instanceof Error
            ? error.message
            : 'The general customer-match lookup was unavailable.',
        )
      }
    }

    if (!customer) {
      try {
        discoveryRecommendation = await getLockboxRecommendation(
          recommendationInput(transaction),
          signal,
        )
        warnings.push(...discoveryRecommendation.warnings)
        if (discoveryRecommendation.customer_match?.customer_number) {
          customer = preparedCustomerFromRecommendation(
            discoveryRecommendation.customer_match,
          )
          customerSource = invoiceMatched(discoveryRecommendation)
            ? 'invoice'
            : 'recommendation'
        }
      } catch (error) {
        if (signal?.aborted) throw error
        warnings.push(
          error instanceof Error
            ? error.message
            : 'The initial cash-application analysis was unavailable.',
        )
      }
    }

    if (customer?.customerNumber) {
      try {
        customer = await loadCustomerMaster(
          customer,
          signal,
          context,
        )
      } catch (error) {
        if (signal?.aborted) throw error
        warnings.push(
          error instanceof Error
            ? error.message
            : 'ERP customer-master details could not be loaded.',
        )
      }

      // Always run the decision engine again with the resolved ERP customer.
      // The first pass may identify the invoice owner without having enough
      // customer context to retrieve and allocate the open invoices.
      try {
        const analyzed = await getCustomerAwareLockboxRecommendation(
          transaction,
          customer,
          signal,
          context,
        )
        finalRecommendation = analyzed.recommendation
        warnings.push(...analyzed.warnings)

        if (finalRecommendation.customer_match?.customer_number) {
          const finalCustomer = preparedCustomerFromRecommendation(
            finalRecommendation.customer_match,
          )
          customer = normalizePreparedErpCustomer({
            ...finalCustomer,
            customerName:
              customer.customerName || finalCustomer.customerName,
            phone: customer.phone || finalCustomer.phone,
            addressLine1:
              customer.addressLine1 || finalCustomer.addressLine1,
            addressLine2:
              customer.addressLine2 || finalCustomer.addressLine2,
            city: customer.city || finalCustomer.city,
            state: customer.state || finalCustomer.state,
            postalCode:
              customer.postalCode || finalCustomer.postalCode,
          })
        }
      } catch (error) {
        if (signal?.aborted) throw error
        warnings.push(
          error instanceof Error
            ? error.message
            : 'Open-invoice allocation analysis could not be completed.',
        )
      }
    }

    const recommendation =
      finalRecommendation || discoveryRecommendation
    const cleanedWarnings = uniqueWarnings(warnings)
    const hasAllocation = Boolean(
      recommendation?.suggested_allocations.length,
    )
    const status: LockboxPreparationStatus =
      customer && hasAllocation
        ? 'ready'
        : customer || recommendation
          ? 'needs_review'
          : 'failed'

    let message = 'ERP preparation could not be completed.'
    if (customer && hasAllocation) {
      message = (
        `Prepared customer #${customer.customerNumber} and `
        + `${recommendation?.suggested_allocations.length ?? 0} `
        + 'invoice allocation recommendation(s) before review.'
      )
    } else if (customer) {
      message = (
        `ERP resolved customer #${customer.customerNumber}, but no `
        + 'open-invoice allocation was recommended. Manual review is required.'
      )
    } else if (invoiceNumbers.length === 0) {
      message = (
        'No valid 8- or 9-digit remittance invoice was available. '
        + 'OCR identity remains visible for manual review.'
      )
    } else {
      message = (
        `ERP could not verify invoice ${invoiceNumbers.join(', ')}. `
        + 'OCR identity remains visible for manual review.'
      )
    }

    return {
      transactionId: transaction.transaction_id,
      status,
      preparedAt: new Date().toISOString(),
      invoiceNumbers,
      customer,
      customerSource,
      recommendation,
      message,
      warnings: cleanedWarnings,
    }
  } catch (error) {
    if (signal?.aborted) throw error
    return {
      transactionId: transaction.transaction_id,
      status: 'failed',
      preparedAt: new Date().toISOString(),
      invoiceNumbers,
      customer: null,
      customerSource: null,
      recommendation: null,
      message: (
        error instanceof Error
          ? error.message
          : 'ERP preparation could not be completed.'
      ),
      warnings: uniqueWarnings(warnings),
    }
  }
}
