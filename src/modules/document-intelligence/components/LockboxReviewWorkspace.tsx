import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

import {
  getCustomerSummary,
  searchCustomers,
} from '../../../api/customers'
import type {
  CustomerSearchResult,
  CustomerSummary,
} from '../../../features/customer360/types'

import {
  appendLockboxCustomerNote,
  getLockboxCustomerNotes,
  getDocumentFileUrl,
  saveLockboxTransactionReview,
} from '../api'

import type {
  LockboxReviewResult,
  LockboxReviewStatus,
  LockboxCustomerNote,
  ReviewedLockboxAllocation,
} from '../types'

import {
  getLockboxOpenInvoices,
  getValidErpInvoiceNumbers,
  getLockboxRecommendation,
  normalizeErpInvoiceNumber,
  reconcileRecommendationWithOpenInvoices,
} from './lockboxRecommendation'
import { NO_REMITTANCE_INVOICE } from './erpInvoiceNumber'
import type {
  LockboxRecommendation,
} from './lockboxRecommendation'
import {
  getLegacyOpenItemIdentity,
  getInvoiceBusinessEffect,
  normalizeLockboxPaymentDate,
} from './lockboxAllocationRules'
import type {
  LegacyInvoiceDetail,
} from './lockboxAllocationRules'
import {
  buildLockboxAgingBucketResult,
} from './lockboxAgingBuckets'
import type {
  LockboxAgingBucketSummary,
} from './lockboxAgingBuckets'
import {
  buildLockboxDueDateSummary,
} from './lockboxDueDateSummary'
import {
  isGovernedServiceCharge,
  recommendationDraft,
  shouldProjectRecommendationDraft,
} from './lockboxDraftProjection'
import {
  getCustomerAwareLockboxRecommendation,
} from './lockboxPreparation'
import type {
  PreparedErpCustomer,
  PreparedLockboxTransaction,
} from './lockboxPreparation'
import {
  nextLockboxQueueTransactionId,
  previousLockboxQueueTransactionId,
  transactionNeedsProfessionalReview,
} from './lockboxReviewQueue'

type Props = {
  jobId: string
  review: LockboxReviewResult
  initialTransactionId?: string
  preparedTransactions?: Record<string, PreparedLockboxTransaction>
  queueTransactionIds?: string[]
  queueLabel?: string
  onPrepareTransaction?: (
    transactionId: string,
  ) => Promise<PreparedLockboxTransaction>
  onClose: () => void
  onUpdated: (
    review: LockboxReviewResult,
    updatedTransactionId?: string,
  ) => void
}

type CustomerIdentityFields = {
  customer_number?: string
  printed_customer_number?: string
  customer_name?: string
  customer_phone?: string
  phone_number?: string
  customer_address_line_1?: string
  customer_address_line_2?: string
  address_line_1?: string
  address_line_2?: string
  customer_city?: string
  city?: string
  customer_state?: string
  state?: string
  customer_postal_code?: string
  customer_zip?: string
  postal_code?: string
}

type ReviewedTransaction =
  LockboxReviewResult['transactions'][number] & CustomerIdentityFields

type CustomerMatchSource =
  | 'saved'
  | 'search'
  | 'invoice'
  | 'recommendation'
  | null

type ErpCustomerDetails = {
  customerNumber: string
  customerName?: string
  phone?: string
  addressLine1?: string
  addressLine2?: string
  city?: string
  state?: string
  postalCode?: string
}

type ReviewActionModal = 'customer-notes' | 'email-customer' | null

type CustomerEmailDraft = {
  to: string
  cc: string
  subject: string
  body: string
}

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

function normalizeErpCustomerDetails(
  details: ErpCustomerDetails,
  addressLines: string[] = [],
): ErpCustomerDetails {
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
    if (/^[\d\s-]+$/.test(line) && /^\d{5}(?:-\d{4})?$/.test(postalOnly)) {
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
    ...details,
    addressLine1,
    addressLine2,
    city,
    state,
    postalCode,
  }
}

function detailsFromCustomerSummary(
  summary: CustomerSummary,
): ErpCustomerDetails {
  const general = summary.general as CustomerSummary['general']
    & Record<string, unknown>
  const addressLines = Array.isArray(general.address_lines)
    ? general.address_lines.filter(
      (line): line is string => typeof line === 'string' && Boolean(line.trim()),
    )
    : []

  return normalizeErpCustomerDetails({
    customerNumber: String(summary.customer_number),
    customerName: summary.customer_name,
    phone: firstText(general.phone),
    addressLine1: firstText(general.address_line_1, addressLines[0]),
    addressLine2: firstText(general.address_line_2),
    city: firstText(general.city),
    state: firstText(
      general.state,
      general.state_abbreviation,
      typeof general.state_code === 'string' ? general.state_code : '',
    ),
    postalCode: firstText(general.postal_code, general.zip_code),
  }, addressLines)
}

function detailsFromRecommendation(
  match: NonNullable<LockboxRecommendation['customer_match']>,
): ErpCustomerDetails {
  return normalizeErpCustomerDetails({
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

function money(value: number) {
  return value.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
  })
}

function displayDate(value?: string | null) {
  if (!value) return '—'
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (!match) return value
  return `${Number(match[2])}/${Number(match[3])}/${match[1]}`
}

function displayTimestamp(value: string) {
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleString('en-US')
}

function cloneAllocations(
  allocations: ReviewedLockboxAllocation[],
): ReviewedLockboxAllocation[] {
  return allocations.map((allocation) => ({ ...allocation }))
}

function allocationDraftFingerprint(
  allocations: ReviewedLockboxAllocation[],
): string {
  return JSON.stringify(allocations.map((allocation) => ({
    invoice_number: allocation.invoice_number,
    net_invoice_amount: Number(allocation.net_invoice_amount),
    invoice_page: allocation.invoice_page,
    confidence: Number(allocation.confidence),
    allocation_kind: allocation.allocation_kind || '',
    erp_transaction_type: allocation.erp_transaction_type || '',
    open_item_key: allocation.open_item_key || '',
    normalized_invoice_number: allocation.normalized_invoice_number || '',
    invoice_count: allocation.invoice_count ?? null,
  })))
}

function allocationOpenItemKey(
  allocation: ReviewedLockboxAllocation,
): string {
  if (isGovernedServiceCharge(allocation)) {
    return `open:${allocation.open_item_key}`
  }
  const invoiceNumber = normalizeErpInvoiceNumber(
    allocation.invoice_number,
  )
  return invoiceNumber ? `invoice:${invoiceNumber}` : ''
}

export default function LockboxReviewWorkspace({
  jobId,
  review,
  initialTransactionId,
  preparedTransactions = {},
  queueTransactionIds,
  queueLabel = 'Needs Review',
  onPrepareTransaction,
  onClose,
  onUpdated,
}: Props) {
  const dialogRef = useRef<HTMLDivElement | null>(null)
  const closeButtonRef = useRef<HTMLButtonElement | null>(null)
  const previouslyFocusedElementRef = useRef<HTMLElement | null>(null)
  const onCloseRef = useRef(onClose)
  const [selectedId, setSelectedId] = useState(
    initialTransactionId || review.transactions[0]?.transaction_id || '',
  )
  const [allocations, setAllocations] = useState<ReviewedLockboxAllocation[]>([])
  const [, setAllocationDraftDirty] = useState(false)
  const allocationDraftDirtyRef = useRef(false)
  const markAllocationDraftDirty = useCallback((dirty: boolean) => {
    allocationDraftDirtyRef.current = dirty
    setAllocationDraftDirty(dirty)
  }, [])
  const [reviewer, setReviewer] = useState('')
  const [notes, setNotes] = useState('')
  const [overrideReason, setOverrideReason] = useState('')
  const [customerNumber, setCustomerNumber] = useState('')
  const [customerSearch, setCustomerSearch] = useState('')
  const [customerName, setCustomerName] = useState('')
  const [customerPhone, setCustomerPhone] = useState('')
  const [addressLine1, setAddressLine1] = useState('')
  const [addressLine2, setAddressLine2] = useState('')
  const [customerCity, setCustomerCity] = useState('')
  const [customerState, setCustomerState] = useState('')
  const [customerPostalCode, setCustomerPostalCode] = useState('')
  const [customerResults, setCustomerResults] =
    useState<CustomerSearchResult[]>([])
  const [customerSearchError, setCustomerSearchError] = useState('')
  const [isSearchingCustomers, setIsSearchingCustomers] = useState(false)
  const [isLoadingCustomerDetails, setIsLoadingCustomerDetails] =
    useState(false)
  const [customerMatchSource, setCustomerMatchSource] =
    useState<CustomerMatchSource>(null)
  const [invoiceMatchMessage, setInvoiceMatchMessage] = useState('')
  const [, setStatus] = useState<LockboxReviewStatus>('corrected')
  const [isSaving, setIsSaving] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [recommendation, setRecommendation] =
    useState<LockboxRecommendation | null>(null)
  const [isLoadingRecommendation, setIsLoadingRecommendation] = useState(false)
  const [recommendationError, setRecommendationError] = useState('')
  const [preparedOverrides, setPreparedOverrides] = useState<
    Record<string, PreparedLockboxTransaction>
  >({})
  const [preparingSelectionId, setPreparingSelectionId] = useState('')
  const isPreparingSelection = Boolean(preparingSelectionId)
  const [isAllocationDetailExpanded, setIsAllocationDetailExpanded] =
    useState(false)
  const [isTransactionQueueCollapsed, setIsTransactionQueueCollapsed] =
    useState(true)
  const [openInvoices, setOpenInvoices] = useState<LegacyInvoiceDetail[]>([])
  const [isLoadingOpenInvoices, setIsLoadingOpenInvoices] = useState(false)
  const [openInvoiceError, setOpenInvoiceError] = useState('')
  const [selectedDueDates, setSelectedDueDates] = useState<string[]>([])
  const dueDateSelectionBaselineRef = useRef<{
    allocations: ReviewedLockboxAllocation[]
    dirty: boolean
  } | null>(null)
  const [showOpenInvoicePicker, setShowOpenInvoicePicker] = useState(false)
  const [openInvoiceSearch, setOpenInvoiceSearch] = useState('')
  const [reviewActionModal, setReviewActionModal] =
    useState<ReviewActionModal>(null)
  const reviewActionModalRef = useRef<ReviewActionModal>(null)
  const customerNotesRequestSequenceRef = useRef(0)
  const [customerNotes, setCustomerNotes] = useState<LockboxCustomerNote[]>([])
  const [customerNoteBody, setCustomerNoteBody] = useState('')
  const [customerNoteAuthor, setCustomerNoteAuthor] = useState('')
  const [customerNoteError, setCustomerNoteError] = useState('')
  const [isLoadingCustomerNotes, setIsLoadingCustomerNotes] = useState(false)
  const [isSavingCustomerNote, setIsSavingCustomerNote] = useState(false)
  const [emailDraft, setEmailDraft] = useState<CustomerEmailDraft>({
    to: '',
    cc: '',
    subject: '',
    body: '',
  })

  useEffect(() => {
    onCloseRef.current = onClose
  }, [onClose])

  useEffect(() => {
    previouslyFocusedElementRef.current = (
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null
    )
    const focusTimer = window.setTimeout(() => {
      closeButtonRef.current?.focus()
    }, 0)

    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      if (reviewActionModalRef.current) {
        reviewActionModalRef.current = null
        customerNotesRequestSequenceRef.current += 1
        setReviewActionModal(null)
        return
      }
      onCloseRef.current()
    }
    const containDialogFocus = (event: KeyboardEvent) => {
      if (event.key !== 'Tab') return
      const workspaceDialog = dialogRef.current
      const dialog = workspaceDialog?.querySelector<HTMLElement>(
        '.lockbox-action-modal',
      ) || workspaceDialog
      if (!dialog) return
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), '
        + 'select:not([disabled]), textarea:not([disabled]), '
        + '[tabindex]:not([tabindex="-1"])',
      )).filter((element) => !element.hidden)
      if (focusable.length === 0) {
        event.preventDefault()
        dialog.focus()
        return
      }
      const first = focusable[0]
      const last = focusable.at(-1) as HTMLElement
      if (!dialog.contains(document.activeElement)) {
        event.preventDefault()
        ;(event.shiftKey ? last : first).focus()
      } else if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', closeOnEscape)
    document.addEventListener('keydown', containDialogFocus)

    return () => {
      window.clearTimeout(focusTimer)
      document.removeEventListener('keydown', closeOnEscape)
      document.removeEventListener('keydown', containDialogFocus)
      previouslyFocusedElementRef.current?.focus()
    }
  }, [])

  const transaction = (
    review.transactions.find(
      (item) => item.transaction_id === selectedId,
    ) as ReviewedTransaction | undefined
  ) ?? null

  const preparedTransaction = transaction
    ? (
      preparedOverrides[transaction.transaction_id]
      || preparedTransactions[transaction.transaction_id]
      || null
    )
    : null
  const transactionsNeedingReview = useMemo(
    () => review.transactions.filter(transactionNeedsProfessionalReview),
    [review.transactions],
  )
  const queueTransactions = useMemo(() => {
    if (queueTransactionIds) {
      const byId = new Map(review.transactions.map(
        (item) => [item.transaction_id, item],
      ))
      return queueTransactionIds.flatMap((transactionId) => {
        const item = byId.get(transactionId)
        return item ? [item] : []
      })
    }
    return transactionsNeedingReview.length > 0
      ? transactionsNeedingReview
      : review.transactions
  }, [queueTransactionIds, review.transactions, transactionsNeedingReview])

  const validInvoiceNumbers = useMemo(
    () => getValidErpInvoiceNumbers(allocations),
    [allocations],
  )

  const invalidInvoiceNumbers = useMemo(
    () => allocations
      .map((allocation) => allocation.invoice_number.trim())
      .filter((invoiceNumber) => (
        invoiceNumber
        && invoiceNumber !== NO_REMITTANCE_INVOICE
        && !normalizeErpInvoiceNumber(invoiceNumber)
        && !allocations.some((allocation) => (
          allocation.invoice_number.trim() === invoiceNumber
          && isGovernedServiceCharge(allocation)
        ))
      )),
    [allocations],
  )

  const openInvoicesByNumber = useMemo(
    () => new Map(
      openInvoices.flatMap((invoice) => {
        const identity = getLegacyOpenItemIdentity(invoice)
        return identity ? [[identity.key, invoice] as const] : []
      }),
    ),
    [openInvoices],
  )

  const positiveCreditAllocations = useMemo(
    () => allocations.filter((allocation) => {
      const invoice = openInvoicesByNumber.get(
        allocationOpenItemKey(allocation),
      )
      return Boolean(
        invoice
        && getInvoiceBusinessEffect(invoice).businessType === 'credit'
        && Number(allocation.net_invoice_amount) > 0,
      )
    }),
    [allocations, openInvoicesByNumber],
  )

  /* eslint-disable react-hooks/set-state-in-effect -- ERP invoice state must
     reset immediately when the selected customer/transaction changes. */
  useEffect(() => {
    if (!transaction) return
    const savedCustomerNumber = transaction.customer_number || ''
    const customerSearchValue = savedCustomerNumber
      || transaction.printed_customer_number
      || ''

    // This effect intentionally resets the editable draft when the reviewer
    // selects a different transaction.
    setAllocations(cloneAllocations(transaction.allocations))
    markAllocationDraftDirty(false)
    setReviewer(transaction.reviewer)
    setNotes(transaction.notes)
    setOverrideReason(transaction.override_reason)
    setCustomerNumber(savedCustomerNumber)
    setCustomerSearch(customerSearchValue)
    setCustomerName(transaction.customer_name || '')
    setCustomerPhone(
      transaction.customer_phone
      || transaction.phone_number
      || '',
    )
    setAddressLine1(
      transaction.customer_address_line_1
      || transaction.address_line_1
      || '',
    )
    setAddressLine2(
      transaction.customer_address_line_2
      || transaction.address_line_2
      || '',
    )
    setCustomerCity(transaction.customer_city || transaction.city || '')
    setCustomerState(transaction.customer_state || transaction.state || '')
    setCustomerPostalCode(
      transaction.customer_postal_code
      || transaction.customer_zip
      || transaction.postal_code
      || '',
    )
    setStatus(
      transaction.status === 'approved'
        ? 'approved'
        : transaction.status === 'balanced'
          ? 'corrected'
          : transaction.status,
    )
    setErrorMessage('')
    setCustomerResults([])
    setCustomerSearchError('')
    setCustomerMatchSource(
      preparedTransaction?.customerSource
      || (savedCustomerNumber ? 'saved' : null),
    )
    setShowOpenInvoicePicker(false)
    setOpenInvoiceSearch('')
    setInvoiceMatchMessage(preparedTransaction?.message || '')
    setIsLoadingCustomerDetails(false)

    if (
      preparedTransaction?.customer
      && transaction.status !== 'corrected'
      && transaction.status !== 'held'
      && transaction.status !== 'approved'
    ) {
      const preparedCustomer = preparedTransaction.customer
      setCustomerNumber(preparedCustomer.customerNumber)
      setCustomerSearch(preparedCustomer.customerNumber)
      setCustomerName(preparedCustomer.customerName)
      setCustomerPhone(preparedCustomer.phone)
      setAddressLine1(preparedCustomer.addressLine1)
      setAddressLine2(preparedCustomer.addressLine2)
      setCustomerCity(preparedCustomer.city)
      setCustomerState(preparedCustomer.state)
      setCustomerPostalCode(preparedCustomer.postalCode)
    }

    setRecommendation(preparedTransaction?.recommendation || null)
    setRecommendationError(
      preparedTransaction?.status === 'failed'
        ? preparedTransaction.message
        : '',
    )
  }, [markAllocationDraftDirty, preparedTransaction, transaction])

  useEffect(() => {
    setSelectedDueDates([])
    dueDateSelectionBaselineRef.current = null

    if (!transaction || !customerNumber.trim()) {
      setOpenInvoices([])
      setOpenInvoiceError('')
      setIsLoadingOpenInvoices(false)
      setShowOpenInvoicePicker(false)
      return
    }

    const controller = new AbortController()
    setIsLoadingOpenInvoices(true)
    setOpenInvoiceError('')

    void getLockboxOpenInvoices(
      customerNumber.trim(),
      normalizeLockboxPaymentDate(transaction.date),
      controller.signal,
    ).then((invoices) => {
      if (controller.signal.aborted) return
      const resolvedInvoices = invoices ?? []
      setOpenInvoices(resolvedInvoices)
      if (
        transaction.status !== 'approved'
        && transaction.status !== 'corrected'
        && transaction.status !== 'held'
        && transaction.status !== 'balanced'
      ) {
        setShowOpenInvoicePicker(true)
      }
      setRecommendation((current) => (
        current
          ? reconcileRecommendationWithOpenInvoices(
            current,
            resolvedInvoices,
          )
          : current
      ))

      if (
        transaction.status !== 'approved'
        && transaction.status !== 'corrected'
        && transaction.status !== 'held'
      ) {
        const invoiceLookup = new Map(
          resolvedInvoices.flatMap((invoice) => {
            const identity = getLegacyOpenItemIdentity(invoice)
            return identity ? [[identity.key, invoice] as const] : []
          }),
        )
        setAllocations((current) => current.map((allocation) => {
          const invoice = invoiceLookup.get(
            allocationOpenItemKey(allocation),
          )
          if (!invoice) return allocation
          const effect = getInvoiceBusinessEffect(invoice)
          if (
            effect.businessType !== 'credit'
            || Number(allocation.net_invoice_amount) <= 0
          ) {
            return allocation
          }
          return {
            ...allocation,
            net_invoice_amount: -Math.abs(
              Number(allocation.net_invoice_amount),
            ),
          }
        }))
      }
    }).catch((error) => {
      if (controller.signal.aborted) return
      setOpenInvoices([])
      setOpenInvoiceError(
        error instanceof Error
          ? error.message
          : 'Unable to load ERP open invoices for editing.',
      )
      if (
        transaction.status !== 'approved'
        && transaction.status !== 'corrected'
        && transaction.status !== 'held'
        && transaction.status !== 'balanced'
      ) {
        setShowOpenInvoicePicker(true)
      }
    }).finally(() => {
      if (!controller.signal.aborted) setIsLoadingOpenInvoices(false)
    })

    return () => controller.abort()
  }, [customerNumber, transaction])
  /* eslint-enable react-hooks/set-state-in-effect */

  useEffect(() => {
    const query = customerSearch.trim()

    if (
      query.length < 2
      || (customerNumber && query === customerNumber)
    ) {
      return
    }

    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      setIsSearchingCustomers(true)
      setCustomerSearchError('')

      void searchCustomers(query, controller.signal, false)
        .then((response) => {
          setCustomerResults(response.customers)
          if (response.customers.length === 0) {
            setCustomerSearchError(
              'No ERP customers matched that open invoice, customer number, name, phone, or address.',
            )
          }
        })
        .catch((error) => {
          if (controller.signal.aborted) return
          setCustomerResults([])
          setCustomerSearchError(
            error instanceof Error
              ? error.message
              : 'Unable to search ERP customers.',
          )
        })
        .finally(() => {
          if (!controller.signal.aborted) {
            setIsSearchingCustomers(false)
          }
        })
    }, 300)

    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [customerNumber, customerSearch])

  const allocationTotal = useMemo(
    () => allocations.reduce(
      (total, allocation) => total + Number(allocation.net_invoice_amount || 0),
      0,
    ),
    [allocations],
  )

  const difference = transaction
    ? Number((transaction.check_amount - allocationTotal).toFixed(2))
    : 0
  const balanced = Math.abs(difference) <= 0.01
  const hasUnsavedAllocationChanges = Boolean(
    transaction
    && allocationDraftFingerprint(allocations)
      !== allocationDraftFingerprint(transaction.allocations),
  )
  const hasUnsavedReviewChanges = Boolean(transaction && (
    hasUnsavedAllocationChanges
    || reviewer !== transaction.reviewer
    || notes !== transaction.notes
    || overrideReason !== transaction.override_reason
    || customerNumber.trim() !== (transaction.customer_number || '').trim()
    || customerName.trim() !== (transaction.customer_name || '').trim()
    || customerPhone.trim() !== firstText(
      transaction.customer_phone,
      transaction.phone_number,
    )
    || addressLine1.trim() !== firstText(
      transaction.customer_address_line_1,
      transaction.address_line_1,
    )
    || addressLine2.trim() !== firstText(
      transaction.customer_address_line_2,
      transaction.address_line_2,
    )
    || customerCity.trim() !== firstText(
      transaction.customer_city,
      transaction.city,
    )
    || customerState.trim() !== firstText(
      transaction.customer_state,
      transaction.state,
    )
    || customerPostalCode.trim() !== firstText(
      transaction.customer_postal_code,
      transaction.customer_zip,
      transaction.postal_code,
    )
  ))

  const activePage = useMemo(() => {
  if (!transaction) return 1

  const remittancePage = transaction.remittance_pages?.[0]
  if (remittancePage && remittancePage > 0) {
    return remittancePage
  }

  if (transaction.check_page && transaction.check_page > 0) {
    return transaction.check_page
  }

  const allocationPage = allocations.find(
    (item) => item.invoice_page,
  )?.invoice_page

  const parsed = Number.parseInt(String(allocationPage || ''), 10)

  if (Number.isFinite(parsed) && parsed > 0) {
    return parsed
  }

  return 1
}, [allocations, transaction])

  const agingBucketResult = useMemo(
    () => buildLockboxAgingBucketResult(
      openInvoices,
      String(activePage),
    ),
    [activePage, openInvoices],
  )

  const dueDateSummary = useMemo(
    () => buildLockboxDueDateSummary(
      openInvoices,
      transaction
        ? normalizeLockboxPaymentDate(transaction.date)
        : '',
      (invoice) => getInvoiceBusinessEffect(invoice).amount,
    ),
    [openInvoices, transaction],
  )

  // A final governed recommendation may arrive after customer resolution or
  // open-A/R retrieval. Project it only while the reviewer draft is untouched.
  useEffect(() => {
    if (!transaction || !recommendation) return
    if (!shouldProjectRecommendationDraft(
      recommendation,
      allocationDraftDirtyRef.current,
      transaction.status,
    )) return

    setAllocations(recommendationDraft(recommendation, String(activePage)))
    markAllocationDraftDirty(false)
  }, [
    activePage,
    markAllocationDraftDirty,
    recommendation,
    transaction,
  ])
  const updateAllocation = (
    index: number,
    field: keyof ReviewedLockboxAllocation,
    value: string,
  ) => {
    markAllocationDraftDirty(true)
    setAllocations((current) => current.map((allocation, rowIndex) => {
      if (rowIndex !== index) return allocation
      if (field === 'net_invoice_amount') {
        return { ...allocation, [field]: Number(value) }
      }
      return { ...allocation, [field]: value }
    }))
  }

  const addAllocation = () => {
    markAllocationDraftDirty(true)
    setAllocations((current) => [
      ...current,
      {
        invoice_number: '',
        net_invoice_amount: 0,
        invoice_page: String(activePage),
        confidence: 1,
      },
    ])
  }

  const allocatedInvoiceNumbers = useMemo(
    () => new Set(
      allocations.map(allocationOpenItemKey).filter(Boolean),
    ),
    [allocations],
  )

  const openInvoiceTotal = useMemo(
    () => Number(openInvoices.reduce((total, invoice) => (
      total + Number(getInvoiceBusinessEffect(invoice).amount ?? 0)
    ), 0).toFixed(2)),
    [openInvoices],
  )

  const availableOpenInvoices = useMemo(() => {
    const search = openInvoiceSearch.trim().toLowerCase()
    return openInvoices.filter((invoice) => {
      const identity = getLegacyOpenItemIdentity(invoice)
      if (!identity || allocatedInvoiceNumbers.has(identity.key)) {
        return false
      }
      if (!search) return true
      const effect = getInvoiceBusinessEffect(invoice)
      return [
        identity.displayNumber,
        identity.allocationKind,
        identity.openItemKey,
        invoice.reference_number,
        invoice.due_date,
        invoice.aging_bucket,
        invoice.due_date_bucket,
        effect.businessType,
        effect.rawTransactionType,
        effect.amount,
      ].some((value) => String(value ?? '').toLowerCase().includes(search))
    })
  }, [
    allocatedInvoiceNumbers,
    openInvoiceSearch,
    openInvoices,
  ])

  const addOpenInvoice = (invoice: LegacyInvoiceDetail) => {
    const identity = getLegacyOpenItemIdentity(invoice)
    if (!identity || allocatedInvoiceNumbers.has(identity.key)) return
    const effect = getInvoiceBusinessEffect(invoice)
    markAllocationDraftDirty(true)
    setAllocations((current) => [
      ...current,
      {
        invoice_number: identity.displayNumber,
        net_invoice_amount: effect.amount ?? 0,
        invoice_page: String(activePage),
        confidence: 1,
        allocation_kind: identity.allocationKind,
        erp_transaction_type: identity.rawTransactionType,
        open_item_key: identity.openItemKey,
        normalized_invoice_number: identity.normalizedInvoiceNumber,
        invoice_count: identity.invoiceCount,
      },
    ])
    setStatus('corrected')
    setOpenInvoiceSearch('')
  }

  const applyNoRemittance = () => {
    if (!transaction) return
    setAllocations([
      {
        invoice_number: '9999999999',
        net_invoice_amount: transaction.check_amount,
        invoice_page: String(transaction.check_page || activePage),
        confidence: 1,
      },
    ])
    markAllocationDraftDirty(true)
    setStatus('corrected')
  }

  const applyAgingBucket = (bucket: LockboxAgingBucketSummary) => {
    if (
      !transaction
      || !customerNumber.trim()
      || isLoadingOpenInvoices
      || openInvoiceError
      || !bucket.selectable
    ) return

    if (
      hasUnsavedAllocationChanges
      && !window.confirm(
        `Replace the unsaved allocation draft with all ${bucket.count} `
        + `${bucket.label} ERP open items?`,
      )
    ) return

    setAllocations(cloneAllocations(bucket.allocations))
    markAllocationDraftDirty(true)
    setStatus('corrected')
    setShowOpenInvoicePicker(false)
    setOpenInvoiceSearch('')
    setErrorMessage('')
  }

  const toggleDueDateGroup = (dueDate: string) => {
    if (
      !transaction
      || !customerNumber.trim()
      || isLoadingOpenInvoices
      || openInvoiceError
    ) return

    const normalizedDueDate = String(dueDate || '').trim().slice(0, 10)
    if (!normalizedDueDate) return

    const wasSelected = selectedDueDates.includes(normalizedDueDate)
    const nextDueDates = wasSelected
      ? selectedDueDates.filter((value) => value !== normalizedDueDate)
      : [...selectedDueDates, normalizedDueDate]

    if (selectedDueDates.length === 0 && !wasSelected) {
      if (
        hasUnsavedAllocationChanges
        && !window.confirm(
          'Replace the current unsaved allocation draft with the selected '
          + 'ERP due-date group(s)?',
        )
      ) return

      dueDateSelectionBaselineRef.current = {
        allocations: cloneAllocations(allocations),
        dirty: allocationDraftDirtyRef.current,
      }
    }

    if (nextDueDates.length === 0) {
      const baseline = dueDateSelectionBaselineRef.current
      if (baseline) {
        setAllocations(cloneAllocations(baseline.allocations))
        markAllocationDraftDirty(baseline.dirty)
      }
      dueDateSelectionBaselineRef.current = null
      setSelectedDueDates([])
      setStatus('corrected')
      setErrorMessage('')
      return
    }

    const selectedSet = new Set(nextDueDates)
    const nextAllocations: ReviewedLockboxAllocation[] = []
    const seenOpenItems = new Set<string>()

    for (const invoice of openInvoices) {
      const invoiceDueDate = String(invoice.due_date || '').trim().slice(0, 10)
      if (!selectedSet.has(invoiceDueDate)) continue

      const identity = getLegacyOpenItemIdentity(invoice)
      const effect = getInvoiceBusinessEffect(invoice)
      if (!identity || effect.amount == null || seenOpenItems.has(identity.key)) {
        continue
      }

      seenOpenItems.add(identity.key)
      nextAllocations.push({
        invoice_number: identity.displayNumber,
        net_invoice_amount: effect.amount,
        invoice_page: String(activePage),
        confidence: 1,
        allocation_kind: identity.allocationKind,
        erp_transaction_type: identity.rawTransactionType,
        open_item_key: identity.openItemKey,
        normalized_invoice_number: identity.normalizedInvoiceNumber,
        invoice_count: identity.invoiceCount,
      })
    }

    if (nextAllocations.length === 0) {
      setErrorMessage(
        'No selectable ERP open items were found for the selected due-date group(s).',
      )
      return
    }

    setSelectedDueDates(nextDueDates)
    setAllocations(nextAllocations)
    markAllocationDraftDirty(true)
    setStatus('corrected')
    setShowOpenInvoicePicker(false)
    setOpenInvoiceSearch('')
    setErrorMessage('')
  }

  const selectedDueDateSummary = useMemo(() => {
    const selected = new Set(selectedDueDates)
    return dueDateSummary.groups.reduce(
      (summary, group) => {
        if (!selected.has(group.dueDate)) return summary
        summary.groupCount += 1
        summary.itemCount += group.count
        summary.total += Number(group.total || 0)
        return summary
      },
      { groupCount: 0, itemCount: 0, total: 0 },
    )
  }, [dueDateSummary.groups, selectedDueDates])

  const applyErpCustomerDetails = useCallback((
    details: ErpCustomerDetails,
    source: Exclude<CustomerMatchSource, null>,
  ) => {
    const normalized = normalizeErpCustomerDetails(details)
    setCustomerNumber(normalized.customerNumber)
    setCustomerSearch(normalized.customerNumber)
    setCustomerName(normalized.customerName || '')
    setCustomerPhone(normalized.phone || '')
    setAddressLine1(normalized.addressLine1 || '')
    setAddressLine2(normalized.addressLine2 || '')
    setCustomerCity(normalized.city || '')
    setCustomerState(normalized.state || '')
    setCustomerPostalCode(normalized.postalCode || '')
    setCustomerResults([])
    setCustomerMatchSource(source)
  }, [])

  const hydrateErpCustomer = useCallback(async (
    customerNumberToLoad: string,
    source: Exclude<CustomerMatchSource, null>,
    fallbackDetails?: ErpCustomerDetails,
    signal?: AbortSignal,
  ): Promise<ErpCustomerDetails | null> => {
    let resolvedDetails = fallbackDetails
      ? normalizeErpCustomerDetails(fallbackDetails)
      : null
    if (resolvedDetails && !signal?.aborted) {
      applyErpCustomerDetails(resolvedDetails, source)
    }

    setIsLoadingCustomerDetails(true)
    setCustomerSearchError('')

    try {
      const summary = await getCustomerSummary(
        customerNumberToLoad,
        signal,
      )
      if (signal?.aborted) return null
      resolvedDetails = detailsFromCustomerSummary(summary)
      applyErpCustomerDetails(resolvedDetails, source)
    } catch (error) {
      if (
        error instanceof DOMException
        && error.name === 'AbortError'
      ) {
        return null
      }
      if (!fallbackDetails) {
        setCustomerSearchError(
          error instanceof Error
            ? error.message
            : 'Unable to load the selected ERP customer.',
        )
      }
    } finally {
      setIsLoadingCustomerDetails(false)
    }
    return resolvedDetails
  }, [applyErpCustomerDetails])

  const selectCustomer = async (customer: CustomerSearchResult) => {
    const customerNumberToLoad = String(customer.customer_number)
    const fallbackDetails = normalizeErpCustomerDetails({
      customerNumber: customerNumberToLoad,
      customerName: customer.customer_name,
      phone: customer.phone,
      addressLine1: customer.address_line_1,
      addressLine2: customer.address_line_2,
      city: customer.city,
      state: customer.state,
      postalCode: customer.postal_code || customer.zip_code,
    })

    const resolvedDetails = await hydrateErpCustomer(
      customerNumberToLoad,
      'search',
      fallbackDetails,
    )
    await loadRecommendation(resolvedDetails || fallbackDetails)
  }

  const loadRecommendation = async (
    customerOverride?: ErpCustomerDetails,
  ) => {
    if (!transaction) return

    setIsLoadingRecommendation(true)
    setRecommendationError('')

    try {
      const requestedCustomerNumber = (
        customerOverride?.customerNumber
        || customerNumber
      ).trim()
      const requestedCustomer: PreparedErpCustomer | null =
        requestedCustomerNumber
          ? {
            customerNumber: requestedCustomerNumber,
            customerName:
              customerOverride?.customerName || customerName.trim(),
            phone: customerOverride?.phone || customerPhone.trim(),
            addressLine1:
              customerOverride?.addressLine1 || addressLine1.trim(),
            addressLine2:
              customerOverride?.addressLine2 || addressLine2.trim(),
            city: customerOverride?.city || customerCity.trim(),
            state: customerOverride?.state || customerState.trim(),
            postalCode:
              customerOverride?.postalCode || customerPostalCode.trim(),
          }
          : null
      const analysisTransaction: ReviewedTransaction = {
        ...transaction,
        customer_number: requestedCustomerNumber,
        customer_name:
          requestedCustomer?.customerName || customerName.trim(),
        customer_phone:
          requestedCustomer?.phone || customerPhone.trim(),
        customer_address_line_1:
          requestedCustomer?.addressLine1 || addressLine1.trim(),
        customer_address_line_2:
          requestedCustomer?.addressLine2 || addressLine2.trim(),
        customer_city:
          requestedCustomer?.city || customerCity.trim(),
        customer_state:
          requestedCustomer?.state || customerState.trim(),
        customer_postal_code:
          requestedCustomer?.postalCode || customerPostalCode.trim(),
        allocations,
      }

      let result: LockboxRecommendation
      if (requestedCustomer) {
        const analyzed = await getCustomerAwareLockboxRecommendation(
          analysisTransaction,
          requestedCustomer,
        )
        result = analyzed.recommendation
        const additionalWarnings = analyzed.warnings.filter(
          (warning) => !result.warnings.includes(warning),
        )
        if (additionalWarnings.length > 0) {
          setRecommendationError(additionalWarnings.join(' '))
        }
      } else {
        result = await getLockboxRecommendation({
          transaction_id: transaction.transaction_id,
          check_amount: transaction.check_amount,
          customer_number: '',
          printed_customer_number:
            transaction.printed_customer_number || '',
          customer_name: customerName.trim(),
          customer_phone: customerPhone.trim(),
          customer_address_line_1: addressLine1.trim(),
          customer_address_line_2: addressLine2.trim(),
          customer_city: customerCity.trim(),
          customer_state: customerState.trim(),
          customer_postal_code: customerPostalCode.trim(),
          aba_routing: transaction.aba_routing,
          account_number: transaction.account_number,
          allocations,
        })
      }

      setRecommendation(result)

      if (result.customer_match?.customer_number) {
        const matchedByInvoice = result.customer_match.matched_on.some(
          (reason) => reason.toLowerCase().includes('invoice'),
        )
        const source: Exclude<CustomerMatchSource, null> = matchedByInvoice
          ? 'invoice'
          : customerMatchSource || 'recommendation'

        await hydrateErpCustomer(
          String(result.customer_match.customer_number),
          source,
          detailsFromRecommendation(result.customer_match),
        )
      }
    } catch (error) {
      setRecommendationError(
        error instanceof Error
          ? error.message
          : 'Unable to load the cash-application recommendation.',
      )
    } finally {
      setIsLoadingRecommendation(false)
    }
  }

  const applyRecommendation = () => {
    if (!transaction || !recommendation) return

    const recommendedRows = recommendationDraft(
      recommendation,
      String(activePage),
    )

    if (recommendedRows.length === 0) return

    setAllocations(recommendedRows)
    markAllocationDraftDirty(false)
    setStatus('corrected')
    setNotes((current) => {
      const note = `Prepared recommendation applied: ${recommendedRows.length} allocation row(s).`
      return current.trim() ? `${current.trim()}\n${note}` : note
    })
  }

  const save = async (nextStatus: LockboxReviewStatus) => {
    if (!transaction) return
    const isHolding = nextStatus === 'held'
    if (
      !isHolding
      && allocations.some((allocation) => !allocation.invoice_number.trim())
    ) {
      setErrorMessage('Every allocation needs an invoice number before saving.')
      return
    }
    if (!isHolding && invalidInvoiceNumbers.length > 0) {
      setErrorMessage(
        'Correct the highlighted invoice values. ERP invoice numbers must contain exactly 8 or 9 digits.',
      )
      return
    }
    if (!isHolding && positiveCreditAllocations.length > 0) {
      setErrorMessage(
        'ERP credit allocations must use a negative amount. Correct the highlighted credit rows before saving.',
      )
      return
    }
    if (nextStatus === 'approved' && !balanced && !overrideReason.trim()) {
      setErrorMessage('Enter an override reason before approving an unbalanced transaction.')
      return
    }

    setIsSaving(true)
    setErrorMessage('')
    try {
      const reviewPayload = {
        allocations,
        reviewer,
        notes,
        status: nextStatus,
        override_reason: overrideReason,
        customer_number: customerNumber.trim(),
        customer_name: customerName.trim(),
        customer_phone: customerPhone.trim(),
        customer_address_line_1: addressLine1.trim(),
        customer_address_line_2: addressLine2.trim(),
        customer_city: customerCity.trim(),
        customer_state: customerState.trim(),
        customer_postal_code: customerPostalCode.trim(),
      }

      const updated = await saveLockboxTransactionReview(
        jobId,
        transaction.transaction_id,
        reviewPayload,
      )
      onUpdated(updated, transaction.transaction_id)
      setStatus(nextStatus)
      if (nextStatus === 'approved' || nextStatus === 'held') {
        const nextTransactionId = nextLockboxQueueTransactionId(
          queueTransactions,
          transaction.transaction_id,
        )
        if (nextTransactionId) {
          await selectTransaction(nextTransactionId)
        } else {
          onClose()
        }
      }
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : 'Unable to save this review.',
      )
    } finally {
      setIsSaving(false)
    }
  }

  const advanceWithoutSaving = async () => {
    if (!transaction || isSaving || isPreparingSelection) return
    if (
      hasUnsavedReviewChanges
      && !window.confirm(
        'Leave this transaction in Open Review and discard the unsaved '
        + 'changes currently shown on this screen?',
      )
    ) return

    const nextTransactionId = nextLockboxQueueTransactionId(
      queueTransactions,
      transaction.transaction_id,
    )
    if (nextTransactionId) {
      await selectTransaction(nextTransactionId)
    } else {
      onClose()
    }
  }

  const goBackWithoutSaving = async () => {
    if (!transaction || isSaving || isPreparingSelection) return
    if (
      hasUnsavedReviewChanges
      && !window.confirm(
        'Leave this transaction in Open Review and discard the unsaved '
        + 'changes currently shown on this screen?',
      )
    ) return

    const previousTransactionId = previousLockboxQueueTransactionId(
      queueTransactions,
      transaction.transaction_id,
    )
    if (previousTransactionId) {
      await selectTransaction(previousTransactionId)
    }
  }

  const openReviewActionModal = (modal: Exclude<ReviewActionModal, null>) => {
    reviewActionModalRef.current = modal
    setReviewActionModal(modal)
  }

  const closeReviewActionModal = () => {
    reviewActionModalRef.current = null
    customerNotesRequestSequenceRef.current += 1
    setReviewActionModal(null)
  }

  const openCustomerNotes = async () => {
    if (!transaction) return
    const requestSequence = customerNotesRequestSequenceRef.current + 1
    customerNotesRequestSequenceRef.current = requestSequence
    openReviewActionModal('customer-notes')
    setCustomerNotes([])
    setCustomerNoteBody('')
    setCustomerNoteAuthor(reviewer.trim())
    setCustomerNoteError('')
    setIsLoadingCustomerNotes(false)

    const persistedCustomerNumber = (
      transaction.customer_number || ''
    ).trim()
    if (!customerNumber.trim()) {
      setCustomerNoteError(
        'Select and save an ERP customer before adding a customer note.',
      )
      return
    }
    if (customerNumber.trim() !== persistedCustomerNumber) {
      setCustomerNoteError(
        'Save the changed ERP customer selection before opening its notes.',
      )
      return
    }

    setIsLoadingCustomerNotes(true)
    try {
      const response = await getLockboxCustomerNotes(
        jobId,
        transaction.transaction_id,
      )
      if (customerNotesRequestSequenceRef.current === requestSequence) {
        setCustomerNotes(response.notes)
      }
    } catch (error) {
      if (customerNotesRequestSequenceRef.current === requestSequence) {
        setCustomerNoteError(
          error instanceof Error
            ? error.message
            : 'Unable to load customer notes.',
        )
      }
    } finally {
      if (customerNotesRequestSequenceRef.current === requestSequence) {
        setIsLoadingCustomerNotes(false)
      }
    }
  }

  const saveCustomerNote = async () => {
    if (!transaction || isSavingCustomerNote) return
    const body = customerNoteBody.trim()
    const author = customerNoteAuthor.trim()
    if (!body || !author) {
      setCustomerNoteError(
        'Enter both the note author and customer note before saving.',
      )
      return
    }

    setIsSavingCustomerNote(true)
    setCustomerNoteError('')
    try {
      const response = await appendLockboxCustomerNote(
        jobId,
        transaction.transaction_id,
        { body, author },
      )
      setCustomerNotes(response.notes)
      setCustomerNoteBody('')
    } catch (error) {
      setCustomerNoteError(
        error instanceof Error
          ? error.message
          : 'Unable to save the customer note.',
      )
    } finally {
      setIsSavingCustomerNote(false)
    }
  }

  const openCustomerEmailDraft = () => {
    if (!transaction) return
    setEmailDraft({
      to: '',
      cc: '',
      subject: `Remittance detail request - Check ${transaction.check_number}`,
      body: [
        `Hello ${customerName.trim() || 'Customer'},`,
        '',
        `We are reviewing check ${transaction.check_number} for ${money(transaction.check_amount)} received ${displayDate(transaction.date)}.`,
        'Please reply with the remittance detail needed to apply this payment.',
        '',
        'Thank you,',
        'K&M Tire Accounts Receivable',
      ].join('\n'),
    })
    openReviewActionModal('email-customer')
  }

  const selectTransaction = async (transactionId: string) => {
    if (transactionId === selectedId || isPreparingSelection) return

    closeReviewActionModal()

    if (!onPrepareTransaction) {
      setSelectedId(transactionId)
      return
    }

    setPreparingSelectionId(transactionId)
    setErrorMessage('')
    try {
      const prepared = await onPrepareTransaction(transactionId)
      setPreparedOverrides((current) => ({
        ...current,
        [transactionId]: prepared,
      }))
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to prepare the selected transaction.',
      )
    } finally {
      setSelectedId(transactionId)
      setPreparingSelectionId('')
    }
  }

  const customerSourceLabel =
    customerMatchSource === 'invoice'
      ? 'matched from a remittance invoice'
      : customerMatchSource === 'search'
        ? 'selected from ERP search'
        : customerMatchSource === 'recommendation'
          ? 'selected from ERP match recommendations'
          : customerMatchSource === 'saved'
            ? 'saved on this review'
            : ''

  if (!transaction) return null

  return (
    <div
      ref={dialogRef}
      className="lockbox-review-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="lockbox-review-dialog-label lockbox-review-dialog-transaction"
      tabIndex={-1}
    >
      <style>{`
        .cash-ai-panel {
          margin: 16px 14px;
          padding: 16px;
          border: 1px solid #2c405b;
          border-radius: 10px;
          color: #edf4fc;
          background: #101a29;
          box-shadow: 0 14px 36px rgba(0, 0, 0, .2);
        }
        .cash-ai-panel.expanded {
          position: fixed;
          z-index: 2100;
          inset: 24px;
          margin: 0;
          overflow: auto;
          padding: 24px;
          border-color: #4d78b4;
          box-shadow: 0 34px 120px rgba(0, 0, 0, .72);
        }
        .cash-ai-panel-header {
          display: flex;
          justify-content: space-between;
          align-items: flex-start;
          gap: 12px;
          margin-bottom: 14px;
        }
        .cash-ai-panel-header strong {
          color: #f3f7fd;
          font-size: 16px;
        }
        .cash-ai-panel-header span {
          display: block;
          margin-top: 3px;
          color: #91a3bb;
          font-size: 12px;
        }
        .cash-ai-panel-header-actions {
          display: flex;
          align-items: center;
          justify-content: flex-end;
          gap: 8px;
          flex-wrap: wrap;
        }
        .cash-ai-status {
          display: inline-flex;
          padding: 5px 9px;
          border-radius: 999px;
          font-size: 12px;
          font-weight: 700;
          text-transform: capitalize;
        }
        .cash-ai-status.recommended {
          background: #dcfce7;
          color: #166534;
        }
        .cash-ai-status.review_required {
          background: #fef3c7;
          color: #92400e;
        }
        .cash-ai-status.no_invoice_match,
        .cash-ai-status.customer_not_found {
          background: #fee2e2;
          color: #991b1b;
        }
        .cash-ai-metrics {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 8px;
          margin-bottom: 14px;
        }
        .cash-ai-metric {
          padding: 10px;
          border: 1px solid #2b3c53;
          border-radius: 8px;
          background: #0c1420;
        }
        .cash-ai-metric span {
          display: block;
          color: #8496ae;
          font-size: 11px;
          margin-bottom: 4px;
        }
        .cash-ai-metric strong {
          color: #f1f6fd;
          font-size: 15px;
        }
        .cash-ai-allocation-detail {
          margin: 14px 0;
          border: 1px solid #334b69;
          border-radius: 10px;
          overflow: hidden;
          background: #0b131f;
        }
        .cash-ai-allocation-heading {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          padding: 9px 11px;
          border-bottom: 1px solid #2a3d56;
          background: #132034;
        }
        .cash-ai-allocation-heading strong {
          color: #f1f6fd;
        }
        .cash-ai-allocation-heading span {
          color: #8da2bc;
          font-size: 11px;
        }
        .cash-ai-allocation-heading-actions {
          display: flex;
          align-items: center;
          justify-content: flex-end;
          gap: 8px;
          flex-wrap: wrap;
        }
        .cash-ai-allocation-heading-actions button {
          padding: 6px 9px;
        }
        .cash-ai-table-wrap {
          min-height: 230px;
          max-height: 390px;
          overflow: auto;
          scrollbar-width: auto;
          scrollbar-color: #7fa7db #111a28;
        }
        .cash-ai-panel.expanded .cash-ai-table-wrap {
          min-height: 420px;
          max-height: calc(100vh - 330px);
        }
        .cash-ai-table {
          width: 100%;
          border-collapse: collapse;
          background: #0b131f;
        }
        .cash-ai-table th,
        .cash-ai-table td {
          padding: 8px 10px;
          border-bottom: 1px solid #223249;
          color: #dce6f4;
          text-align: left;
          font-size: 12px;
          white-space: nowrap;
        }
        .cash-ai-table th {
          position: sticky;
          z-index: 1;
          top: 0;
          color: #91a7c1;
          background: #111d2e;
          font-size: 11px;
          text-transform: uppercase;
          letter-spacing: .05em;
        }
        .cash-ai-table td:first-child,
        .cash-ai-table td:nth-child(3) {
          color: #a9c9fb;
          font-weight: 700;
        }
        .cash-ai-table input {
          min-width: 96px;
          max-width: 132px;
          padding: 5px 7px;
          border: 1px solid #3b526f;
          border-radius: 7px;
          color: #edf4fc;
          background: #101b2a;
        }
        .cash-ai-table input.credit-sign-error {
          border-color: #ef8d8d;
          color: #ffd2d2;
          background: rgba(153, 27, 27, .18);
        }
        .cash-ai-type {
          display: inline-flex;
          padding: 3px 6px;
          border-radius: 999px;
          font-size: 10px;
          font-weight: 800;
          text-transform: uppercase;
          letter-spacing: .04em;
        }
        .cash-ai-type.debit {
          color: #9bc1f7;
          background: rgba(59, 130, 246, .15);
        }
        .cash-ai-type.credit {
          color: #79dfb0;
          background: rgba(34, 197, 94, .14);
        }
        .cash-ai-type-note {
          display: block;
          margin-top: 4px;
          color: #8497b0;
          font-size: 10px;
          white-space: normal;
        }
        .cash-ai-delete-row {
          width: 26px;
          height: 26px;
          padding: 0;
          border: 1px solid #6b3542;
          border-radius: 7px;
          color: #f8b4bd;
          background: rgba(127, 29, 29, .2);
          font-size: 18px;
        }
        .cash-ai-open-invoice-picker {
          padding: 12px;
          border-top: 1px solid #2a3d56;
          background: #0f1928;
        }
        .cash-ai-open-invoice-picker input {
          width: 100%;
          margin-bottom: 9px;
          padding: 9px 10px;
          border: 1px solid #3b526f;
          border-radius: 7px;
          color: #edf4fc;
          background: #0b131f;
        }
        .cash-ai-open-invoice-list {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 7px;
          max-height: 230px;
          overflow: auto;
          scrollbar-width: auto;
          scrollbar-color: #7fa7db #111a28;
        }
        .cash-ai-open-invoice {
          display: grid;
          grid-template-columns: minmax(0, 1fr) auto;
          gap: 4px 10px;
          padding: 9px 10px;
          border: 1px solid #30445f;
          border-radius: 8px;
          text-align: left;
          color: #dbe8f8;
          background: #111d2e;
        }
        .cash-ai-open-invoice:hover,
        .cash-ai-open-invoice:focus-visible {
          border-color: #6591cb;
          background: #182841;
        }
        .cash-ai-open-invoice strong {
          color: #a9c9fb;
        }
        .cash-ai-open-invoice span {
          color: #e7eef8;
          font-weight: 700;
        }
        .cash-ai-open-invoice small {
          grid-column: 1 / -1;
          color: #8497b0;
        }
        .cash-ai-editor-note,
        .cash-ai-open-invoice-state {
          padding: 8px 12px;
          border-top: 1px solid #263952;
          color: #8fa2ba;
          background: #101b2b;
          font-size: 11px;
        }
        .cash-ai-credit-warning {
          margin: 10px 0;
          padding: 9px 11px;
          border: 1px solid rgba(239, 141, 141, .42);
          border-radius: 8px;
          color: #ffc2c2;
          background: rgba(127, 29, 29, .16);
          font-size: 11px;
        }
        .cash-ai-allocation-empty {
          display: grid;
          min-height: 230px;
          place-items: center;
          padding: 24px;
          color: #92a4ba;
          text-align: center;
        }
        .cash-ai-reasons {
          margin: 10px 0 14px;
          padding-left: 18px;
          color: #b1bfd0;
          font-size: 12px;
        }
        .cash-ai-actions {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
        }
        .erp-customer-search-field {
          position: relative;
          display: flex;
          flex-direction: column;
          color: #8595ab;
          font-size: 11px;
          font-weight: 700;
        }
        .erp-customer-search-field input {
          width: 100%;
          margin-top: 5px;
        }
        .erp-customer-search-state {
          min-height: 16px;
          margin-top: 5px;
          color: #7f90a7;
          font-size: 10px;
          font-weight: 500;
        }
        .erp-customer-results {
          position: absolute;
          z-index: 20;
          top: calc(100% - 13px);
          left: 0;
          right: 0;
          max-height: 280px;
          overflow: auto;
          border: 1px solid #3c526f;
          border-radius: 8px;
          background: #111a28;
          box-shadow: 0 14px 32px rgba(0, 0, 0, .36);
        }
        .erp-customer-result {
          display: block;
          width: 100%;
          padding: 10px 12px;
          border: 0;
          border-bottom: 1px solid #26364d;
          border-radius: 0;
          text-align: left;
          background: transparent;
        }
        .erp-customer-result:last-child {
          border-bottom: 0;
        }
        .erp-customer-result:hover,
        .erp-customer-result:focus-visible {
          background: #1b2a3d;
        }
        .erp-customer-result strong,
        .erp-customer-result span,
        .erp-customer-result small {
          display: block;
        }
        .erp-customer-result strong {
          color: #edf4fc;
          font-size: 12px;
        }
        .erp-customer-result span {
          margin-top: 3px;
          color: #8db8f4;
          font-size: 11px;
        }
        .erp-customer-result small {
          margin-top: 3px;
          color: #7f90a7;
          font-size: 10px;
        }
        .erp-customer-selection,
        .erp-invoice-match-message,
        .erp-customer-search-error {
          grid-column: 1 / -1;
        }
        .erp-customer-selection {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          padding: 9px 11px;
          border: 1px solid rgba(65, 190, 131, .34);
          border-radius: 8px;
          color: #76dcae;
          background: rgba(65, 190, 131, .08);
          font-size: 11px;
        }
        .erp-customer-selection button {
          padding: 4px 8px;
        }
        .erp-customer-search-error {
          color: #ef9b9b;
          font-size: 11px;
        }
        .erp-invoice-match-message {
          padding: 9px 11px;
          border: 1px solid rgba(87, 137, 207, .35);
          border-radius: 8px;
          color: #a9c8f7;
          background: rgba(57, 105, 171, .11);
          font-size: 11px;
          line-height: 1.45;
        }
        .erp-invoice-match-message.success {
          border-color: rgba(65, 190, 131, .34);
          color: #76dcae;
          background: rgba(65, 190, 131, .08);
        }
        .erp-match-reasons {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          margin: 0 0 12px;
        }
        .erp-match-reasons span {
          padding: 5px 8px;
          border-radius: 999px;
          color: #315f46;
          background: #dcfce7;
          font-size: 11px;
        }
        @media (max-width: 900px) {
          .cash-ai-metrics {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
          .cash-ai-open-invoice-list {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
      <div className="lockbox-review-shell">
        <header className="lockbox-review-topbar">
          <div>
            <span id="lockbox-review-dialog-label">LOCKBOX REVIEW WORKSPACE</span>
            <strong id="lockbox-review-dialog-transaction">
              {transaction.transaction_id}
            </strong>
            <small>
              {customerName || 'Unknown customer'} · Check {transaction.check_number}
            </small>
          </div>
          <div className="lockbox-review-topbar-actions">
            {preparedTransaction && (
              <div className={`lockbox-prepared-badge ${preparedTransaction.status}`}>
                <strong>
                  {preparedTransaction.status === 'ready'
                    ? 'Prepared before review'
                    : preparedTransaction.status === 'needs_review'
                      ? 'Prepared · exception remains'
                      : 'Preparation incomplete'}
                </strong>
                <span>
                  {preparedTransaction.recommendation?.suggested_allocations.length ?? 0}
                  {' '}suggested allocation(s)
                </span>
              </div>
            )}
            <button
              ref={closeButtonRef}
              type="button"
              className="secondary"
              onClick={onClose}
            >
              Close Review
            </button>
          </div>
        </header>

        <div className={`lockbox-review-body ${
          isTransactionQueueCollapsed ? 'queue-collapsed' : ''
        }`}>
          <aside className={`lockbox-review-queue ${
            isTransactionQueueCollapsed ? 'collapsed' : ''
          }`}>
            <button
              type="button"
              className="lockbox-review-queue-toggle"
              aria-label={isTransactionQueueCollapsed
                ? 'Expand transactions'
                : 'Collapse transactions'}
              aria-expanded={!isTransactionQueueCollapsed}
              onClick={() => setIsTransactionQueueCollapsed(
                (current) => !current,
              )}
            >
              <span aria-hidden="true">
                {isTransactionQueueCollapsed ? '›' : '‹'}
              </span>
              {!isTransactionQueueCollapsed && 'Collapse'}
            </button>
            {!isTransactionQueueCollapsed && (
              <>
              <div className="lockbox-review-queue-heading">
                <strong>{queueLabel}</strong>
                <span>{queueTransactions.length} transaction{queueTransactions.length === 1 ? '' : 's'}</span>
                </div>
                {queueTransactions.map((item) => (
                  <button
                    key={item.transaction_id}
                    type="button"
                    className={`lockbox-review-transaction ${
                      item.transaction_id === selectedId ? 'active' : ''
                    }`}
                    disabled={isPreparingSelection}
                    onClick={() => void selectTransaction(item.transaction_id)}
                  >
                    <div><strong>{item.transaction_id}</strong><span>{money(item.check_amount)}</span></div>
                    <small className={`ed-lockbox-status ${item.status}`}>
                      {preparingSelectionId === item.transaction_id
                        ? 'preparing'
                        : item.status.replace('_', ' ')}
                    </small>
                  </button>
                ))}
              </>
            )}
          </aside>

          <section className="lockbox-review-pdf">
            <div className="lockbox-review-pane-heading">
              <div><strong>Source PDF</strong><span>Page {activePage}</span></div>
              <a href={`${getDocumentFileUrl(jobId)}#page=${activePage}`} target="_blank" rel="noreferrer">Open PDF</a>
            </div>
            <iframe
              key={`${selectedId}-${activePage}`}
              title={`PNC PDF page ${activePage}`}
              src={`${getDocumentFileUrl(jobId)}#page=${activePage}&zoom=page-width`}
            />
          </section>

          <section className="lockbox-review-editor">
            <div className="lockbox-review-pane-heading">
              <div><strong>Prepared Review</strong><span>ERP evidence and original OCR rows remain preserved for review and training</span></div>
            </div>

            {errorMessage && <div className="ed-banner error">{errorMessage}</div>}

            <div className="lockbox-customer-section">
              <div className="lockbox-review-pane-heading">
                <div>
                  <strong>Customer Identity</strong>
                  <span>Correct these values to create customer-matching training data</span>
                </div>
              </div>

              <div className="lockbox-review-fields lockbox-customer-fields">
                <div className="erp-customer-search-field">
                  <label htmlFor="erp-customer-search">
                    ERP Customer Number / Search
                  </label>
                  <input
                    id="erp-customer-search"
                    value={customerSearch}
                    onChange={(event) => {
                      const nextValue = event.target.value
                      setCustomerSearch(nextValue)
                      if (
                        nextValue.trim().length < 2
                        || nextValue.trim() === customerNumber
                      ) {
                        setCustomerResults([])
                        setCustomerSearchError('')
                        setIsSearchingCustomers(false)
                      }
                    }}
                    onKeyDown={(event) => {
                      if (event.key === 'Escape') {
                        setCustomerResults([])
                      }
                    }}
                    placeholder="Open invoice, customer number, name, phone, address, city, or ZIP"
                    autoComplete="off"
                  />
                  <span className="erp-customer-search-state">
                    {isPreparingSelection
                      ? `Preparing ${validInvoiceNumbers.length === 1 ? 'invoice' : 'invoices'} against ERP…`
                      : isSearchingCustomers
                      ? 'Searching ERP customers…'
                      : isLoadingCustomerDetails
                        ? 'Loading authoritative ERP details…'
                        : 'Type at least 2 characters, then select a customer.'}
                  </span>

                  {customerResults.length > 0 && (
                    <div className="erp-customer-results">
                      {customerResults.slice(0, 12).map((customer) => (
                        <button
                          key={customer.customer_number}
                          type="button"
                          className="erp-customer-result"
                          onClick={() => void selectCustomer(customer)}
                        >
                          <strong>{customer.customer_name}</strong>
                          <span>Customer #{customer.customer_number}</span>
                          <small>
                            {[
                              customer.phone,
                              customer.city,
                              customer.state,
                              customer.zip_code || customer.postal_code,
                            ].filter(Boolean).join(' · ') || 'ERP customer record'}
                          </small>
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                <label>
                  Customer Name
                  <input
                    value={customerName}
                    onChange={(event) => setCustomerName(event.target.value)}
                    placeholder="Customer or payer name"
                  />
                </label>

                <label>
                  Phone Number
                  <input
                    value={customerPhone}
                    onChange={(event) => setCustomerPhone(event.target.value)}
                    placeholder="Phone number, when available"
                  />
                </label>

                <label>
                  Address Line 1
                  <input
                    value={addressLine1}
                    onChange={(event) => setAddressLine1(event.target.value)}
                    placeholder="Street address"
                  />
                </label>

                <label>
                  Address Line 2
                  <input
                    value={addressLine2}
                    onChange={(event) => setAddressLine2(event.target.value)}
                    placeholder="Suite, unit, or additional address"
                  />
                </label>

                <label>
                  City
                  <input
                    value={customerCity}
                    onChange={(event) => setCustomerCity(event.target.value)}
                    placeholder="City"
                  />
                </label>

                <label>
                  State
                  <input
                    value={customerState}
                    onChange={(event) => setCustomerState(event.target.value)}
                    placeholder="State"
                    maxLength={2}
                  />
                </label>

                <label>
                  ZIP Code
                  <input
                    value={customerPostalCode}
                    onChange={(event) => setCustomerPostalCode(event.target.value)}
                    placeholder="ZIP or postal code"
                  />
                </label>

                {customerNumber && (
                  <div className="erp-customer-selection">
                    <span>
                      Selected ERP customer #{customerNumber}
                      {customerSourceLabel ? ` · ${customerSourceLabel}` : ''}
                    </span>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => {
                        setCustomerNumber('')
                        setCustomerSearch('')
                        setCustomerMatchSource(null)
                        setCustomerResults([])
                      }}
                    >
                      Clear
                    </button>
                  </div>
                )}

                {invoiceMatchMessage && (
                  <div className={`erp-invoice-match-message ${customerMatchSource === 'invoice' ? 'success' : ''}`}>
                    {invoiceMatchMessage}
                  </div>
                )}

                {customerSearchError && (
                  <div className="erp-customer-search-error">
                    {customerSearchError}
                  </div>
                )}
              </div>
            </div>

            <div className={`cash-ai-panel ${
              isAllocationDetailExpanded ? 'expanded' : ''
            }`}>
              <div className="cash-ai-panel-header">
                <div>
                  <strong>Cash Application Recommendation</strong>
                  <span>
                    Prepared from remittance invoices, verified ERP identity,
                    open invoices, aging, and payment amount
                  </span>
                </div>
                <div className="cash-ai-panel-header-actions">
                  {recommendation && (
                    <span className={`cash-ai-status ${recommendation.status}`}>
                      {recommendation.status.replaceAll('_', ' ')}
                    </span>
                  )}
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => setIsAllocationDetailExpanded(
                      (current) => !current,
                    )}
                  >
                    {isAllocationDetailExpanded
                      ? 'Return to Review'
                      : 'Expand Allocation Detail'}
                  </button>
                </div>
              </div>

              {recommendationError && (
                <div className="ed-banner error">{recommendationError}</div>
              )}

              {!recommendation ? (
                <div className="cash-ai-actions">
                  <button
                    type="button"
                    className="primary"
                    disabled={isLoadingRecommendation}
                    onClick={() => void loadRecommendation()}
                  >
                    {isLoadingRecommendation
                      ? 'Analyzing…'
                      : 'Get AI Recommendation'}
                  </button>
                </div>
              ) : (
                <>
                  <div className="cash-ai-metrics">
                    <div className="cash-ai-metric">
                      <span>Customer</span>
                      <strong>
                        {recommendation.customer_match?.customer_number || customerNumber}
                      </strong>
                    </div>
                    <div className="cash-ai-metric">
                      <span>Overall Confidence</span>
                      <strong>
                        {Math.round(
                          Number(recommendation.decision?.overall_confidence || 0) * 100,
                        )}%
                      </strong>
                    </div>
                  <div className="cash-ai-metric">
                      <span>Editable Draft Total</span>
                      <strong>{money(allocationTotal)}</strong>
                    </div>
                    <div className="cash-ai-metric">
                      <span>Draft Difference</span>
                      <strong>{money(difference)}</strong>
                    </div>
                  </div>

                  {recommendation.customer_match?.matched_on.length ? (
                    <div className="erp-match-reasons">
                      {recommendation.customer_match.matched_on.map((reason) => (
                        <span key={reason}>✓ {reason}</span>
                      ))}
                    </div>
                  ) : null}

                  <section className="cash-ai-allocation-detail">
                    <div className="cash-ai-allocation-heading">
                      <div>
                        <strong>Editable ERP Open-Item Allocation</strong>
                        <span>
                          {allocations.length} draft row(s) · {openInvoices.length}
                          {' '}current ERP open item(s) · ERP total {money(openInvoiceTotal)}
                        </span>
                      </div>
                      <div className="cash-ai-allocation-heading-actions">
                        <button
                          type="button"
                          className="secondary"
                          disabled={!customerNumber || isLoadingOpenInvoices}
                          onClick={() => setShowOpenInvoicePicker(
                            (current) => !current,
                          )}
                        >
                          {isLoadingOpenInvoices
                            ? 'Loading ERP Open A/R…'
                            : showOpenInvoicePicker
                              ? 'Close ERP Open A/R'
                              : '+ Add ERP Invoice / SC'}
                        </button>
                        <button
                          type="button"
                          className="secondary"
                          onClick={addAllocation}
                        >
                          + Add Blank Row
                        </button>
                      </div>
                    </div>
                    <div className="cash-ai-table-wrap">
                      {allocations.length > 0 ? (
                        <table className="cash-ai-table">
                          <thead>
                            <tr>
                              <th>Invoice</th>
                              <th>ERP Effect</th>
                              <th>Open Amount</th>
                              <th>Apply Amount</th>
                              <th>Due Date</th>
                              <th>Aging</th>
                              <th>Confidence</th>
                              <th />
                            </tr>
                          </thead>
                          <tbody>
                            {allocations.map((allocation, index) => {
                              const invoiceNumber = normalizeErpInvoiceNumber(
                                allocation.invoice_number,
                              )
                              const suggestion =
                                recommendation.suggested_allocations.find(
                                  (item) => (
                                    allocation.open_item_key
                                      ? item.open_item_key
                                        === allocation.open_item_key
                                      : Boolean(invoiceNumber)
                                        && normalizeErpInvoiceNumber(
                                          item.invoice_number,
                                        ) === invoiceNumber
                                  ),
                                )
                              const invoice = openInvoicesByNumber.get(
                                allocationOpenItemKey(allocation),
                              )
                              const effect = invoice
                                ? getInvoiceBusinessEffect(invoice)
                                : {
                                  businessType:
                                    suggestion?.transaction_type || 'debit',
                                  amount: suggestion
                                    ? Number(suggestion.open_amount)
                                    : null,
                                  rawTransactionType:
                                    suggestion?.erp_transaction_type || '',
                                  negativeDebit:
                                    Boolean(
                                      suggestion?.negative_debit_credit,
                                    ),
                                }
                              const creditSignError = (
                                effect.businessType === 'credit'
                                && Number(allocation.net_invoice_amount) > 0
                              )
                              const invalidInvoice = Boolean(
                                allocation.invoice_number.trim()
                                && allocation.invoice_number
                                  !== NO_REMITTANCE_INVOICE
                                && !invoiceNumber
                                && !isGovernedServiceCharge(allocation)
                              )

                              return (
                                <tr key={`${index}-${allocation.invoice_number}`}>
                                  <td>
                                    <input
                                      aria-label={`Invoice number for allocation row ${index + 1}`}
                                      className={
                                        invalidInvoice
                                          ? 'invalid-invoice'
                                          : ''
                                      }
                                      value={allocation.invoice_number}
                                      onChange={(event) => updateAllocation(
                                        index,
                                        'invoice_number',
                                        event.target.value,
                                      )}
                                      title={
                                        invalidInvoice
                                          ? 'ERP invoice numbers must contain exactly 8 or 9 digits.'
                                          : undefined
                                      }
                                    />
                                  </td>
                                  <td>
                                    <span className={`cash-ai-type ${
                                      effect.businessType
                                    }`}>
                                      {effect.businessType}
                                    </span>
                                    {effect.negativeDebit && (
                                      <small className="cash-ai-type-note">
                                        ERP Debit · negative source amount
                                      </small>
                                    )}
                                    {isGovernedServiceCharge(allocation) && (
                                      <small className="cash-ai-type-note">
                                        ERP SC · service charge
                                      </small>
                                    )}
                                  </td>
                                  <td>
                                    {effect.amount === null
                                      ? '—'
                                      : money(effect.amount)}
                                  </td>
                                  <td>
                                    <input
                                      aria-label={`Apply amount for allocation row ${index + 1}`}
                                      type="number"
                                      step="0.01"
                                      className={
                                        creditSignError
                                          ? 'credit-sign-error'
                                          : ''
                                      }
                                      value={allocation.net_invoice_amount}
                                      onChange={(event) => updateAllocation(
                                        index,
                                        'net_invoice_amount',
                                        event.target.value,
                                      )}
                                      title={
                                        creditSignError
                                          ? 'ERP credits must be applied as negative amounts.'
                                          : undefined
                                      }
                                    />
                                  </td>
                                  <td>
                                    {displayDate(
                                      invoice?.due_date
                                      || suggestion?.due_date,
                                    )}
                                  </td>
                                  <td>
                                    {invoice?.due_date_bucket
                                      || invoice?.aging_bucket
                                      || suggestion?.aging_bucket
                                      || '—'}
                                  </td>
                                  <td>
                                    {Math.round(
                                      allocation.confidence * 100,
                                    )}%
                                  </td>
                                  <td>
                                    <button
                                      type="button"
                                      className="cash-ai-delete-row"
                                      aria-label={`Remove invoice ${
                                        allocation.invoice_number || index + 1
                                      }`}
                                      onClick={() => {
                                        markAllocationDraftDirty(true)
                                        setAllocations(
                                          (current) => current.filter(
                                            (_, rowIndex) => rowIndex !== index,
                                          ),
                                        )
                                      }}
                                    >
                                      ×
                                    </button>
                                  </td>
                                </tr>
                              )
                            })}
                          </tbody>
                        </table>
                      ) : (
                        <div className="cash-ai-allocation-empty">
                          No draft allocations remain. Add an ERP invoice or a
                          service charge from current ERP Open A/R, or add a
                          blank row to build the reviewed allocation.
                        </div>
                      )}
                    </div>
                    {showOpenInvoicePicker && (
                      <div className="cash-ai-open-invoice-picker">
                        <input
                          value={openInvoiceSearch}
                          onChange={(event) => setOpenInvoiceSearch(
                            event.target.value,
                          )}
                          placeholder="Search invoice, SC, reference, due date, aging, debit, or credit"
                          autoFocus
                        />
                        {openInvoiceError ? (
                          <div className="cash-ai-open-invoice-state">
                            {openInvoiceError}
                          </div>
                        ) : availableOpenInvoices.length > 0 ? (
                          <div className="cash-ai-open-invoice-list">
                            {availableOpenInvoices.slice(0, 80).map(
                              (invoice) => {
                                const identity =
                                  getLegacyOpenItemIdentity(invoice)
                                if (!identity) return null
                                const effect =
                                  getInvoiceBusinessEffect(invoice)
                                return (
                                  <button
                                    type="button"
                                    className="cash-ai-open-invoice"
                                    key={identity.key}
                                    onClick={() => addOpenInvoice(invoice)}
                                  >
                                    <strong>
                                      {identity.allocationKind === 'service_charge'
                                        ? `SC · ${identity.displayNumber}`
                                        : identity.displayNumber}
                                    </strong>
                                    <span>
                                      {effect.amount === null
                                        ? '—'
                                        : money(effect.amount)}
                                    </span>
                                    <small>
                                      {effect.businessType === 'credit'
                                        ? 'Credit'
                                        : identity.allocationKind === 'service_charge'
                                          ? 'Service charge'
                                          : 'Debit'}
                                      {' · Due '}
                                      {displayDate(invoice.due_date)}
                                      {' · '}
                                      {invoice.due_date_bucket
                                        || invoice.aging_bucket
                                        || 'No aging bucket'}
                                      {invoice.reference_number
                                        ? ` · Ref ${invoice.reference_number}`
                                        : ''}
                                      {identity.invoiceCount !== null
                                        ? ` · Count ${identity.invoiceCount}`
                                        : ''}
                                    </small>
                                  </button>
                                )
                              },
                            )}
                          </div>
                        ) : (
                          <div className="cash-ai-open-invoice-state">
                            {isLoadingOpenInvoices
                              ? 'Loading current ERP Open A/R…'
                              : 'No additional ERP open items match this search.'}
                          </div>
                        )}
                      </div>
                    )}
                    <div className="cash-ai-editor-note">
                      Edit, add, or remove rows here. Changes are not final
                      until you save the correction or approve the transaction.
                    </div>
                  </section>

                  {positiveCreditAllocations.length > 0 && (
                    <div className="cash-ai-credit-warning">
                      Credit rows must use negative apply amounts. ETOP detected
                      {` ${positiveCreditAllocations.length} `}
                      credit sign that must be corrected before saving.
                    </div>
                  )}

                  {recommendation.decision_reasons.length > 0 && (
                    <ul className="cash-ai-reasons">
                      {recommendation.decision_reasons.map((reason) => (
                        <li key={reason}>{reason}</li>
                      ))}
                    </ul>
                  )}

                  <div className="cash-ai-actions">
                    <button
                      type="button"
                      className="primary"
                      disabled={
                        recommendation.suggested_allocations.length === 0
                        || isLoadingOpenInvoices
                      }
                      onClick={applyRecommendation}
                    >
                      Reset Draft to Prepared Recommendation
                    </button>
                    <button
                      type="button"
                      className="secondary"
                      disabled={isLoadingRecommendation}
                      onClick={() => void loadRecommendation()}
                    >
                      {isLoadingRecommendation ? 'Refreshing…' : 'Refresh'}
                    </button>
                  </div>
                </>
              )}
            </div>

            {!recommendation && (
            <div className="lockbox-editable-allocation-section">
              <div className="lockbox-editable-allocation-heading">
                <div>
                  <strong>Editable Invoice Allocations</strong>
                  <span>Review or correct the rows that will be saved</span>
                </div>
                <button type="button" className="secondary" onClick={addAllocation}>+ Add Row</button>
              </div>
              <div className="lockbox-allocation-table-wrap">
                <table className="lockbox-allocation-table">
                  <thead><tr><th>Invoice Number</th><th>Amount</th><th>Page</th><th>Confidence</th><th /></tr></thead>
                  <tbody>
                    {allocations.map((allocation, index) => {
                      const invoiceNumber = allocation.invoice_number.trim()
                      const invalidInvoice = Boolean(
                        invoiceNumber
                        && invoiceNumber !== NO_REMITTANCE_INVOICE
                        && !normalizeErpInvoiceNumber(invoiceNumber)
                        && !isGovernedServiceCharge(allocation),
                      )
                      return (
                        <tr key={`${index}-${allocation.invoice_number}`}>
                          <td>
                            <input
                              aria-label={`Invoice number for allocation row ${index + 1}`}
                              className={invalidInvoice ? 'invalid-invoice' : ''}
                              value={allocation.invoice_number}
                              onChange={(event) => updateAllocation(index, 'invoice_number', event.target.value)}
                              title={invalidInvoice ? 'ERP invoice numbers must contain exactly 8 or 9 digits.' : undefined}
                            />
                          </td>
                          <td><input aria-label={`Amount for allocation row ${index + 1}`} type="number" step="0.01" value={allocation.net_invoice_amount} onChange={(event) => updateAllocation(index, 'net_invoice_amount', event.target.value)} /></td>
                          <td><input aria-label={`PDF page for allocation row ${index + 1}`} value={allocation.invoice_page} onChange={(event) => updateAllocation(index, 'invoice_page', event.target.value)} /></td>
                          <td><span className="lockbox-confidence">{Math.round(allocation.confidence * 100)}%</span></td>
                          <td><button type="button" className="lockbox-delete-row" aria-label={`Remove allocation row ${index + 1}`} onClick={() => {
                            markAllocationDraftDirty(true)
                            setAllocations((current) => current.filter((_, rowIndex) => rowIndex !== index))
                          }}>×</button></td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
            )}

            {invalidInvoiceNumbers.length > 0 && (
              <div className="lockbox-invoice-format-warning">
                ERP invoice numbers must contain exactly 8 or 9 digits. Invalid OCR values are not sent to customer matching.
              </div>
            )}

            <section
              className="lockbox-due-date-summary"
              aria-labelledby="lockbox-due-date-summary-heading"
            >
              <div className="lockbox-due-date-summary-heading">
                <div>
                  <strong id="lockbox-due-date-summary-heading">
                    ERP Open A/R by Due Date
                  </strong>
                  <span>
                    Select one or more exact due-date groups to replace the
                    allocation draft with those current ERP open items.
                  </span>
                </div>
              </div>
              {Boolean(
                customerNumber.trim()
                && !isLoadingOpenInvoices
                && !openInvoiceError
                && dueDateSummary.groups.length > 0,
              ) && (
                <ul className="lockbox-due-date-summary-list">
                  {dueDateSummary.groups.map((group) => {
                    const selected = selectedDueDates.includes(group.dueDate)
                    return (
                      <li
                        key={group.dueDate}
                        className={selected ? 'selected' : ''}
                        role="checkbox"
                        aria-checked={selected}
                        tabIndex={0}
                        onClick={() => toggleDueDateGroup(group.dueDate)}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter' || event.key === ' ') {
                            event.preventDefault()
                            toggleDueDateGroup(group.dueDate)
                          }
                        }}
                      >
                        <span className="due-date-selection-mark" aria-hidden="true">
                          {selected ? '✓' : ''}
                        </span>
                        <span className={
                          group.balanceType === 'Credit'
                            ? 'credit'
                            : 'debit'
                        }>
                          {group.balanceType}
                        </span>
                        <span>Due {displayDate(group.dueDate)}</span>
                        <span>{group.bucketLabel}</span>
                        <span>Count {group.count}</span>
                        <strong>{money(group.total)}</strong>
                      </li>
                    )
                  })}
                </ul>
              )}
              {selectedDueDateSummary.groupCount > 0 && (
                <div className="lockbox-due-date-selection-summary">
                  <strong>
                    {selectedDueDateSummary.groupCount} due-date group(s) selected
                  </strong>
                  <span>
                    {selectedDueDateSummary.itemCount} ERP open item(s)
                    {' · '}{money(selectedDueDateSummary.total)}
                  </span>
                  <small>
                    Toggle groups to add or remove them. Clearing the final
                    selected group restores the draft that existed before
                    due-date selection began.
                  </small>
                </div>
              )}
              <div className={`lockbox-due-date-summary-state ${
                openInvoiceError ? 'error' : ''
              }`} role="status">
                {!customerNumber.trim()
                  ? 'Select a verified ERP customer to load due-date totals.'
                  : isLoadingOpenInvoices
                    ? 'Loading all current ERP open items…'
                    : openInvoiceError
                      ? openInvoiceError
                      : dueDateSummary.groups.length === 0
                        ? 'No ERP open items are available to summarize.'
                        : dueDateSummary.omittedItemCount > 0
                          ? `${dueDateSummary.omittedItemCount} open item${
                            dueDateSummary.omittedItemCount === 1 ? '' : 's'
                          } could not be summarized because due-date or amount evidence is incomplete.`
                          : `${dueDateSummary.summarizedItemCount} open item${
                            dueDateSummary.summarizedItemCount === 1 ? '' : 's'
                          } summarized across ${dueDateSummary.groups.length} due date${
                            dueDateSummary.groups.length === 1 ? '' : 's'
                          }.`}
              </div>
            </section>

            <section
              className="lockbox-aging-bucket-section"
              aria-labelledby="lockbox-aging-bucket-heading"
            >
              <div className="lockbox-aging-bucket-heading">
                <div>
                  <strong id="lockbox-aging-bucket-heading">
                    Apply an ERP Aging Bucket
                  </strong>
                  <span>
                    Replaces the current draft with every signed current ERP
                    open item in the selected bucket. It does not save or approve.
                  </span>
                </div>
              </div>
              <div className="lockbox-aging-bucket-grid">
                {agingBucketResult.buckets.map((bucket) => {
                  const hasCompleteEvidence = Boolean(
                    customerNumber.trim()
                    && !isLoadingOpenInvoices
                    && !openInvoiceError
                    && bucket.selectable,
                  )
                  const incompleteEvidenceMessage = bucket.invalidItemCount > 0
                    ? `${bucket.invalidItemCount} item${bucket.invalidItemCount === 1 ? '' : 's'} with incomplete identity, amount, or due-date evidence`
                    : ''
                  const dueDateCoverage = bucket.firstDueDate
                    ? bucket.firstDueDate === bucket.lastDueDate
                      ? `Due ${displayDate(bucket.firstDueDate)}`
                      : `Due ${displayDate(bucket.firstDueDate)}–${
                        displayDate(bucket.lastDueDate)
                      }`
                    : bucket.count > 0
                      ? 'Due-date evidence incomplete'
                      : 'No current ERP open items'

                  return (
                    <button
                      key={bucket.key}
                      type="button"
                      disabled={!hasCompleteEvidence}
                      title={bucket.invalidItemCount > 0
                        ? 'This bucket cannot be applied because one or more current ERP items has incomplete identity, amount, or due-date evidence.'
                        : undefined}
                      onClick={() => applyAgingBucket(bucket)}
                    >
                      <strong>{bucket.label}</strong>
                      <span>
                        {bucket.count} item{bucket.count === 1 ? '' : 's'}
                        {' · '}
                        {bucket.total === null ? 'Unavailable' : money(bucket.total)}
                      </span>
                      <small>{dueDateCoverage}</small>
                      {incompleteEvidenceMessage && (
                        <small className="error">
                          {incompleteEvidenceMessage}
                        </small>
                      )}
                    </button>
                  )
                })}
              </div>
              <div className={`lockbox-aging-bucket-state ${
                openInvoiceError ? 'error' : ''
              }`}>
                {!customerNumber.trim()
                  ? 'Select a verified ERP customer to load bucket evidence.'
                  : isLoadingOpenInvoices
                    ? 'Loading current ERP Open A/R bucket evidence…'
                    : openInvoiceError
                      ? openInvoiceError
                      : agingBucketResult.unclassifiedItemCount > 0
                        ? `${agingBucketResult.unclassifiedItemCount} current ERP open item(s) are not selectable because aging evidence is unavailable.`
                        : 'Select a populated bucket to replace the editable allocation draft.'}
              </div>
            </section>

            <button type="button" className="lockbox-placeholder-rule" onClick={applyNoRemittance}>
              Apply no-remittance rule: 9999999999 for {money(transaction.check_amount)}
            </button>

            <div className="lockbox-review-fields">
              <label>Reviewer<input value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder="Reviewer name" /></label>
              <label>Review notes<textarea value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="What was corrected?" /></label>
              {!balanced && <label>Override reason<textarea value={overrideReason} onChange={(event) => setOverrideReason(event.target.value)} placeholder="Required only when approving an unbalanced transaction" /></label>}
            </div>
          </section>

          <aside className="lockbox-review-validation">
            <div className="lockbox-review-pane-heading"><div><strong>Validation</strong><span>Updates as you edit</span></div></div>
            <div className="lockbox-validation-card"><span>Check Amount</span><strong>{money(transaction.check_amount)}</strong></div>
            <div className="lockbox-validation-card"><span>Allocation Total</span><strong>{money(allocationTotal)}</strong></div>
            <div className={`lockbox-validation-card ${balanced ? 'success' : 'warning'}`}><span>Difference</span><strong>{money(difference)}</strong></div>
            <div className={`lockbox-balance-state ${balanced ? 'success' : 'warning'}`}><b>{balanced ? '✓' : '!'}</b><div><strong>{balanced ? 'Balanced' : 'Review Required'}</strong><span>{balanced ? 'Ready for approval' : 'Allocations do not match the check amount'}</span></div></div>

            <div className="lockbox-original-summary">
              <span>Parser originally found</span>
              <strong>{transaction.original_allocations.length} rows · {money(transaction.original_allocations.reduce((sum, item) => sum + item.net_invoice_amount, 0))}</strong>
            </div>

            <div className="lockbox-review-actions">
              <div className="lockbox-review-customer-actions">
                <button
                  type="button"
                  className="secondary"
                  disabled={
                    isSaving
                    || isPreparingSelection
                    || !previousLockboxQueueTransactionId(
                      queueTransactions,
                      transaction.transaction_id,
                    )
                  }
                  onClick={() => void goBackWithoutSaving()}
                >
                  Back
                </button>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => void openCustomerNotes()}
                >
                  Customer Notes
                </button>
                <button
                  type="button"
                  className="secondary"
                  onClick={openCustomerEmailDraft}
                >
                  Email Customer
                </button>
              </div>
              <div className="lockbox-review-routing-actions">
                <button
                  type="button"
                  className="secondary"
                  disabled={isSaving || isPreparingSelection}
                  onClick={() => void advanceWithoutSaving()}
                >
                  Next
                </button>
                <button
                  type="button"
                  className="secondary hold"
                  disabled={isSaving || isPreparingSelection}
                  onClick={() => void save('held')}
                >
                  {isSaving ? 'Saving…' : 'Hold'}
                </button>
              </div>
              <button type="button" className="secondary" disabled={isSaving} onClick={() => void save('corrected')}>{isSaving ? 'Saving…' : 'Save Correction'}</button>
              <button type="button" className="primary" disabled={isSaving} onClick={() => void save('approved')}>{isSaving ? 'Saving…' : 'Approve Transaction'}</button>
            </div>
          </aside>
        </div>
      </div>
      {reviewActionModal === 'customer-notes' && (
        <div className="lockbox-action-modal-overlay">
          <section
            className="lockbox-action-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="lockbox-customer-notes-title"
          >
            <header>
              <div>
                <strong id="lockbox-customer-notes-title">
                  Customer Notes
                </strong>
                <span>
                  {customerNumber.trim() || 'No ERP customer selected'}
                  {customerName.trim() ? ` · ${customerName.trim()}` : ''}
                </span>
              </div>
              <button
                type="button"
                className="secondary"
                autoFocus
                onClick={closeReviewActionModal}
              >
                Close
              </button>
            </header>

            <div className="lockbox-customer-note-history">
              {isLoadingCustomerNotes ? (
                <p>Loading customer notes…</p>
              ) : customerNoteError && customerNotes.length === 0 ? (
                <p>Customer notes are unavailable.</p>
              ) : customerNotes.length === 0 ? (
                <p>No saved notes are available for this customer.</p>
              ) : (
                <ol>
                  {customerNotes.map((note) => (
                    <li key={note.note_id}>
                      <p>{note.body}</p>
                      <small>
                        {note.author} · {displayTimestamp(note.created_at)}
                        {' · '}
                        Transaction {note.source_transaction_id}
                        {note.source_check_number
                          ? ` · Check ${note.source_check_number}`
                          : ''}
                      </small>
                    </li>
                  ))}
                </ol>
              )}
            </div>

            <div className="lockbox-action-modal-fields">
              <label>
                Author
                <input
                  value={customerNoteAuthor}
                  maxLength={200}
                  onChange={(event) => setCustomerNoteAuthor(
                    event.target.value,
                  )}
                  placeholder="Reviewer name"
                />
              </label>
              <label>
                New customer note
                <textarea
                  value={customerNoteBody}
                  maxLength={4000}
                  onChange={(event) => setCustomerNoteBody(
                    event.target.value,
                  )}
                  placeholder="Add an append-only note for this customer"
                />
              </label>
            </div>
            {customerNoteError && (
              <p className="lockbox-action-modal-error" role="alert">
                {customerNoteError}
              </p>
            )}
            <footer>
              <button
                type="button"
                className="primary"
                disabled={
                  isLoadingCustomerNotes
                  || isSavingCustomerNote
                  || !customerNoteBody.trim()
                  || !customerNoteAuthor.trim()
                  || customerNumber.trim()
                    !== (transaction.customer_number || '').trim()
                }
                onClick={() => void saveCustomerNote()}
              >
                {isSavingCustomerNote ? 'Saving…' : 'Save Customer Note'}
              </button>
            </footer>
          </section>
        </div>
      )}
      {reviewActionModal === 'email-customer' && (
        <div className="lockbox-action-modal-overlay">
          <section
            className="lockbox-action-modal lockbox-email-draft-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="lockbox-email-customer-title"
          >
            <header>
              <div>
                <strong id="lockbox-email-customer-title">
                  Email Customer · Draft
                </strong>
                <span>
                  Template only · Outlook is not connected
                </span>
              </div>
              <button
                type="button"
                className="secondary"
                autoFocus
                onClick={closeReviewActionModal}
              >
                Close
              </button>
            </header>
            <div className="lockbox-action-modal-fields">
              <label>
                To
                <input
                  type="email"
                  value={emailDraft.to}
                  onChange={(event) => setEmailDraft((current) => ({
                    ...current,
                    to: event.target.value,
                  }))}
                  placeholder="Customer email address"
                />
              </label>
              <label>
                CC
                <input
                  type="text"
                  value={emailDraft.cc}
                  onChange={(event) => setEmailDraft((current) => ({
                    ...current,
                    cc: event.target.value,
                  }))}
                  placeholder="Optional"
                />
              </label>
              <label>
                Subject
                <input
                  value={emailDraft.subject}
                  onChange={(event) => setEmailDraft((current) => ({
                    ...current,
                    subject: event.target.value,
                  }))}
                />
              </label>
              <label>
                Message
                <textarea
                  value={emailDraft.body}
                  onChange={(event) => setEmailDraft((current) => ({
                    ...current,
                    body: event.target.value,
                  }))}
                />
              </label>
            </div>
            <p className="lockbox-email-integration-state">
              No email will be sent or transmitted. Sending becomes available
              only after a separately governed Outlook integration.
            </p>
            <footer>
              <button
                type="button"
                className="primary"
                disabled
                title="Outlook integration is not connected"
              >
                Send via Outlook (Unavailable)
              </button>
            </footer>
          </section>
        </div>
      )}
    </div>
  )
}
