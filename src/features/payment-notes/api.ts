import { API_BASE, ApiError } from '../../api/client'
import { clearWorkflowToken, getWorkflowToken } from '../workflow-foundation'
import type {
  BankItem,
  CreateItemReviewRequest,
  CrossRunReuseEvidence,
  DepositSummary,
  ExpectedPaymentQueryProvenance,
  ItemReview,
  MatchClassification,
  MatchFeature,
  PaymentNoteCandidate,
  PaymentNotesCountSummary,
  PaymentNotesERPProvenance,
  PaymentNotesRunDetail,
  PaymentNotesRunListResponse,
  PaymentNotesRunSummary,
  ReviewResponse,
  RouteReferenceListResponse,
  RouteReferenceStatus,
  RouteReferenceSummary,
  SignatureEvidence,
  SignatureQueryProvenance,
  SignatureState,
} from './types'

type PaymentNotesRequestOptions = Omit<RequestInit, 'body'> & { body?: unknown }
type JsonRecord = Record<string, unknown>

const matchedClassifications = new Set<MatchClassification>([
  'AUTO_MATCHED',
  'LOCAL_REVIEW_ACCEPTED_MATCH',
])

function contractError(context: string): never {
  throw new ApiError(`Payment Notes returned an invalid ${context} response.`, 502)
}

function record(value: unknown, context: string): JsonRecord {
  if (!value || typeof value !== 'object' || Array.isArray(value)) contractError(context)
  return value as JsonRecord
}

function records(value: unknown, context: string): JsonRecord[] {
  if (!Array.isArray(value)) contractError(context)
  return value.map((item) => record(item, context))
}

function textField(value: JsonRecord, key: string, context: string): string {
  const field = value[key]
  if (typeof field !== 'string') contractError(context)
  return field
}

function optionalText(value: JsonRecord, key: string, context: string): string | null {
  const field = value[key]
  if (field === null || field === undefined) return null
  if (typeof field !== 'string') contractError(context)
  return field
}

function numberField(value: JsonRecord, key: string, context: string): number {
  const field = value[key]
  if (typeof field !== 'number' || !Number.isFinite(field)) contractError(context)
  return field
}

function integerField(value: JsonRecord, key: string, context: string): number {
  const field = numberField(value, key, context)
  if (!Number.isSafeInteger(field) || field < 0) contractError(context)
  return field
}

function booleanField(value: JsonRecord, key: string, context: string): boolean {
  const field = value[key]
  if (typeof field !== 'boolean') contractError(context)
  return field
}

function textArray(value: unknown, context: string): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== 'string')) contractError(context)
  return value as string[]
}

function cents(value: unknown, context: string): number {
  const raw = typeof value === 'number' ? String(value) : value
  if (typeof raw !== 'string' || !/^-?\d+(?:\.\d{1,2})?$/.test(raw)) contractError(context)
  const negative = raw.startsWith('-')
  const unsigned = negative ? raw.slice(1) : raw
  const [whole, fraction = ''] = unsigned.split('.')
  const result = Number(whole) * 100 + Number(fraction.padEnd(2, '0'))
  if (!Number.isSafeInteger(result)) contractError(context)
  return negative ? -result : result
}

async function paymentNotesRequest(
  path: string,
  options: PaymentNotesRequestOptions = {},
): Promise<unknown> {
  const token = getWorkflowToken()
  if (!token) {
    throw new ApiError('Sign in through Work Management before using Payment Notes.', 401)
  }

  const headers = new Headers(options.headers)
  headers.set('Accept', 'application/json')
  headers.set('Authorization', `Bearer ${token}`)

  let body: BodyInit | undefined
  if (options.body instanceof FormData) {
    body = options.body
  } else if (options.body !== undefined) {
    headers.set('Content-Type', 'application/json')
    body = JSON.stringify(options.body)
  }

  const response = await fetch(`${API_BASE}/payment-notes${path}`, {
    ...options,
    headers,
    body,
    credentials: options.credentials ?? 'include',
  })
  if (response.status === 204) return undefined

  const responseBody: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    if (response.status === 401) clearWorkflowToken()
    const bodyRecord = responseBody && typeof responseBody === 'object' && !Array.isArray(responseBody)
      ? responseBody as JsonRecord
      : null
    const detail = bodyRecord?.detail
    const detailRecord = detail && typeof detail === 'object' && !Array.isArray(detail)
      ? detail as JsonRecord
      : null
    const message = typeof detail === 'string'
      ? detail
      : typeof detailRecord?.message === 'string'
        ? detailRecord.message
        : `Payment Notes request failed with status ${response.status}.`
    throw new ApiError(message, response.status, responseBody)
  }
  return responseBody
}

export function paymentNotesIdempotencyKey(prefix: string): string {
  const identity = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`
  return `${prefix}-${identity}`
}

function adaptRouteReference(value: unknown): RouteReferenceSummary {
  const source = record(value, 'route-reference')
  const mappingCount = numberField(source, 'mapping_count', 'route-reference')
  const conflictCount = numberField(source, 'conflict_count', 'route-reference')
  const warnings = textArray(source.warnings, 'route-reference warnings')
  const isActive = booleanField(source, 'is_active', 'route-reference')
  return {
    reference_id: textField(source, 'reference_id', 'route-reference'),
    source_file_name: textField(source, 'source_name', 'route-reference'),
    source_sha256: textField(source, 'source_sha256', 'route-reference'),
    version_label: textField(source, 'version_label', 'route-reference'),
    created_at: textField(source, 'created_at', 'route-reference'),
    activated_at: optionalText(source, 'activated_at', 'route-reference'),
    state: isActive ? 'active' : 'inactive',
    quality: {
      row_count: numberField(source, 'input_row_count', 'route-reference'),
      unique_mapping_count: mappingCount,
      unique_route_count: null,
      duplicate_mapping_count: numberField(source, 'duplicate_mapping_count', 'route-reference'),
      conflicting_route_count: conflictCount,
      unresolved_store_count: null,
      warnings,
    },
  }
}

function adaptRouteReferenceStatus(value: unknown): RouteReferenceStatus {
  const source = record(value, 'route-reference status')
  const ready = booleanField(source, 'run_creation_allowed', 'route-reference status')
  const active = source.active_reference === null ? null : adaptRouteReference(source.active_reference)
  const message = textField(source, 'message', 'route-reference status')
  return { ready, active_reference: active, blocking_reasons: ready ? [] : [message] }
}

function reviewForItem(value: unknown, version: number): ItemReview | null {
  if (value === null || value === undefined) return null
  const source = record(value, 'review')
  const decision = textField(source, 'decision', 'review')
  if (!['accept_candidate', 'leave_unmatched', 'hold'].includes(decision)) contractError('review')
  return {
    review_id: textField(source, 'event_id', 'review'),
    decision: decision as ItemReview['decision'],
    selected_payment_id: optionalText(source, 'selected_payment_id', 'review'),
    reason: textField(source, 'reason', 'review'),
    actor_name: textField(source, 'actor', 'review'),
    created_at: textField(source, 'occurred_at', 'review'),
    version,
    active: true,
  }
}

function adaptSignature(value: unknown): SignatureEvidence {
  const source = record(value, 'signature evidence')
  const filename = textField(source, 'filename', 'signature evidence')
  return {
    rrn: textField(source, 'rrn', 'signature evidence'),
    invoice_number: textField(source, 'invoice_number', 'signature evidence'),
    signer_name: textField(source, 'signer_name', 'signature evidence') || null,
    file_name: filename || null,
    created_at: textField(source, 'created_at', 'signature evidence') || null,
    uploaded_at: textField(source, 'uploaded_at', 'signature evidence') || null,
    state: filename ? 'SIGNED_EVIDENCE' : 'SIGNATURE_ROW_NO_FILE',
  }
}

function featureLabel(code: string): string {
  const labels: Record<string, string> = {
    location_route_date_scope: 'Location, route, and date scope',
    normalized_check_number: 'Normalized check number',
    amount: 'Exact amount',
  }
  return labels[code] ?? code.replaceAll('_', ' ')
}

function adaptCandidate(value: unknown, signatureIncomplete: boolean): PaymentNoteCandidate {
  const source = record(value, 'match candidate')
  const matchedFactors = textArray(source.matched_factors, 'candidate matched factors')
  const conflictingFactors = textArray(source.conflicting_factors, 'candidate conflicts')
  const signatures = records(source.signatures, 'candidate signatures').map(adaptSignature)
  const customerNumber = textField(source, 'customer_number', 'match candidate')
  const invoiceNumbers = textArray(source.invoice_numbers, 'candidate invoices')
  const invoiceReferenceStatus = textField(source, 'invoice_reference_status', 'match candidate')
  const signatureLookupStatus = textField(source, 'signature_lookup_status', 'match candidate')
  if (![
    'SIGNATURE_UNDETERMINED',
    'SIGNATURE_EVIDENCE_FOUND',
    'SIGNATURE_EVIDENCE_NOT_FOUND',
  ].includes(signatureLookupStatus)) contractError('candidate signature lookup status')
  const signatureState: SignatureState = signatureIncomplete || signatureLookupStatus === 'SIGNATURE_UNDETERMINED'
    ? 'SIGNATURE_UNDETERMINED'
    : signatureLookupStatus === 'SIGNATURE_EVIDENCE_NOT_FOUND'
      ? 'NO_SIGNATURE_EVIDENCE'
      : signatures.some((signature) => Boolean(signature.file_name))
        ? 'SIGNED_EVIDENCE'
        : 'SIGNATURE_ROW_NO_FILE'
  const tier = textField(source, 'candidate_tier', 'match candidate')
  const features: MatchFeature[] = matchedFactors.map((code) => ({
    code,
    label: featureLabel(code),
    matched: true,
    points: 0,
    explanation: `Backend matched factor: ${code}.`,
  }))
  return {
    payment_id: textField(source, 'payment_id', 'match candidate'),
    customer_number: customerNumber || null,
    route: textField(source, 'route', 'match candidate'),
    payment_type: textField(source, 'payment_type', 'match candidate'),
    raw_check_number: textField(source, 'raw_check_number', 'match candidate') || null,
    normalized_check_number: textField(source, 'normalized_check_number', 'match candidate') || null,
    amount_cents: cents(source.amount, 'candidate amount'),
    invoices: invoiceNumbers,
    raw_invoices: textField(source, 'raw_invoices', 'match candidate') || null,
    received: textField(source, 'received', 'match candidate') || null,
    received_at: textField(source, 'received_at', 'match candidate') || null,
    created_at: textField(source, 'created_at', 'match candidate') || null,
    score: null,
    tier,
    eligible_for_automatic_match: ['T1_EXACT_CHECK_AMOUNT', 'T2_AMOUNT_DISAMBIGUATED_CHECK'].includes(tier),
    matched_factors: features,
    conflicts: conflictingFactors.map((code) => `Conflicting factor: ${featureLabel(code)}`),
    rejection_reasons: signatureState === 'SIGNATURE_UNDETERMINED' && !signatureIncomplete
      ? [`Signature lookup undetermined: invoice reference status is ${invoiceReferenceStatus}.`]
      : [],
    signature_state: signatureState,
    signatures,
  }
}

function classificationFor(disposition: string, review: ItemReview | null): MatchClassification {
  if (review?.decision === 'accept_candidate') return 'LOCAL_REVIEW_ACCEPTED_MATCH'
  if (review?.decision === 'leave_unmatched') return 'LOCALLY_RECORDED_UNMATCHED'
  if (review?.decision === 'hold') return 'SUGGESTED_REVIEW'
  const mapping: Record<string, MatchClassification> = {
    EXACT_UNIQUE: 'AUTO_MATCHED',
    EXACT_AMOUNT_DISAMBIGUATED: 'AUTO_MATCHED',
    AMOUNT_CONFLICT: 'CHECK_MATCH_AMOUNT_MISMATCH',
    AMBIGUOUS: 'AMBIGUOUS_MATCH',
    AMBIGUOUS_ASSIGNMENT: 'AMBIGUOUS_MATCH',
    AMOUNT_ONLY_REVIEW: 'SUGGESTED_REVIEW',
    SOURCE_INCOMPLETE: 'SUGGESTED_REVIEW',
    UNMATCHED: 'NO_MATCH',
  }
  return mapping[disposition] ?? 'SUGGESTED_REVIEW'
}

function adaptCrossRunReuseEvidence(value: unknown): CrossRunReuseEvidence {
  const source = record(value, 'cross-run reuse evidence')
  return {
    payment_id: textField(source, 'payment_id', 'cross-run reuse evidence'),
    prior_run_ids: textArray(source.prior_run_ids, 'cross-run prior run identifiers'),
    prior_item_ids: textArray(source.prior_item_ids, 'cross-run prior item identifiers'),
    source_types: textArray(source.source_types, 'cross-run source types'),
  }
}

function adaptBankItem(value: unknown, reviewVersion: number, signatureIncomplete: boolean): BankItem {
  const source = record(value, 'bank item')
  const match = record(source.match, 'bank item match')
  const route = record(source.route_resolution, 'route resolution')
  const currentReview = reviewForItem(source.current_review, reviewVersion)
  const disposition = textField(match, 'disposition', 'bank item match')
  const warnings = [
    ...textArray(source.warnings, 'bank item warnings'),
    ...textArray(match.warnings, 'match warnings'),
  ]
  const candidates = records(match.candidates, 'match candidates')
    .map((candidate) => adaptCandidate(candidate, signatureIncomplete))
  const candidateTotalCount = integerField(match, 'candidate_total_count', 'candidate population')
  const candidateDisplayCap = integerField(match, 'candidate_display_cap', 'candidate population')
  const candidatePopulationComplete = booleanField(match, 'candidate_population_complete', 'candidate population')
  if (
    candidateTotalCount < candidates.length
    || candidates.length > candidateDisplayCap
    || (candidateTotalCount > 0 && candidateDisplayCap < 1)
  ) {
    contractError('candidate population')
  }
  if (candidatePopulationComplete && candidateTotalCount !== candidates.length) {
    contractError('complete candidate population')
  }
  if (!candidatePopulationComplete && candidateTotalCount <= candidates.length) {
    contractError('truncated candidate population')
  }
  if (!candidatePopulationComplete && warnings.length === 0) {
    contractError('candidate population warning')
  }
  const crossRunReuseEvidence = records(match.cross_run_reuse_evidence, 'cross-run reuse evidence')
    .map(adaptCrossRunReuseEvidence)
  const signatures = candidates.flatMap((candidate) => candidate.signatures)
  const signatureState: SignatureState = candidates.length === 0
    ? 'SIGNATURE_UNDETERMINED'
    : candidates.some((candidate) => candidate.signature_state === 'SIGNED_EVIDENCE')
      ? 'SIGNED_EVIDENCE'
      : candidates.some((candidate) => candidate.signature_state === 'SIGNATURE_ROW_NO_FILE')
        ? 'SIGNATURE_ROW_NO_FILE'
        : candidates.some((candidate) => candidate.signature_state === 'SIGNATURE_UNDETERMINED')
          ? 'SIGNATURE_UNDETERMINED'
          : 'NO_SIGNATURE_EVIDENCE'
  const routeStatus = textField(route, 'status', 'route resolution')
  const rawCheck = textField(source, 'raw_check_number', 'bank item')
  const normalizedCheck = textField(source, 'normalized_check_number', 'bank item')
  const classification = classificationFor(disposition, currentReview)
  const selectedPaymentId = currentReview?.decision === 'accept_candidate'
    ? currentReview.selected_payment_id
    : currentReview?.decision === 'leave_unmatched' || currentReview?.decision === 'hold'
      ? null
      : optionalText(match, 'selected_payment_id', 'bank item match')
  const conflicts = candidates.flatMap((candidate) => candidate.conflicts)
  const exceptionCodes = [
    ...(routeStatus === 'mapped' ? [] : [`ROUTE_${routeStatus.toUpperCase()}`]),
    ...(currentReview?.decision === 'hold' ? ['MANUAL_HOLD'] : []),
    ...(!matchedClassifications.has(classification) ? [disposition] : []),
  ]
  return {
    bank_item_id: textField(source, 'item_id', 'bank item'),
    fingerprint: textField(source, 'source_record_sha256', 'bank item'),
    source_line: numberField(source, 'source_row_number', 'bank item'),
    deposit_key: textField(source, 'deposit_key', 'bank item'),
    deposit_no: textField(source, 'deposit_number', 'bank item'),
    item_type: textField(source, 'item_type', 'bank item'),
    bank_location_raw: `${textField(source, 'store_number', 'bank item')} - ${textField(source, 'location_name', 'bank item')}`,
    canonical_location_code: textField(source, 'store_number', 'bank item'),
    payment_location_key: textField(source, 'location_key', 'bank item') || null,
    raw_check_number: rawCheck || null,
    normalized_check_number: normalizedCheck || null,
    amount_cents: cents(source.amount, 'bank item amount'),
    candidate_count: candidates.length,
    candidate_total_count: candidateTotalCount,
    candidate_display_cap: candidateDisplayCap,
    candidate_population_complete: candidatePopulationComplete,
    candidate_population_truncated: !candidatePopulationComplete,
    classification,
    selected_payment_id: selectedPaymentId,
    recommendation_score: null,
    recommendation_tier: textField(match, 'tier', 'bank item match'),
    strongest_mismatch: conflicts[0] ?? warnings[0] ?? null,
    exception_codes: [...new Set(exceptionCodes)],
    explanation: [...new Set([
      ...warnings,
      ...(currentReview?.decision === 'hold'
        ? [`Reviewer placed this item on hold: ${currentReview.reason}`]
        : []),
    ])],
    route_scope: textArray(route.routes, 'route resolution routes'),
    signature_state: signatureState,
    signature_count: signatures.length,
    current_review: currentReview,
    candidates,
    cross_run_reuse_evidence: crossRunReuseEvidence,
  }
}

function adaptExpectedPaymentQuery(value: unknown): ExpectedPaymentQueryProvenance {
  const source = record(value, 'expected-payment query provenance')
  const sourceObject = textField(source, 'source_object', 'expected-payment query provenance')
  if (sourceObject !== 'KMTDTA.WHSIGPAY') contractError('expected-payment source object')
  return {
    source_object: sourceObject,
    store_number: textField(source, 'store_number', 'expected-payment query provenance'),
    routes: textArray(source.routes, 'expected-payment query routes'),
    date_from: textField(source, 'date_from', 'expected-payment query provenance'),
    date_to: textField(source, 'date_to', 'expected-payment query provenance'),
    retrieved_at: textField(source, 'retrieved_at', 'expected-payment query provenance'),
    row_limit: integerField(source, 'row_limit', 'expected-payment query provenance'),
    returned_count: integerField(source, 'returned_count', 'expected-payment query provenance'),
    complete: booleanField(source, 'complete', 'expected-payment query provenance'),
    canonical_evidence_sha256: textField(source, 'canonical_evidence_sha256', 'expected-payment query provenance'),
    error: optionalText(source, 'error', 'expected-payment query provenance'),
  }
}

function adaptSignatureQuery(value: unknown): SignatureQueryProvenance {
  const source = record(value, 'signature query provenance')
  const sourceObject = textField(source, 'source_object', 'signature query provenance')
  if (sourceObject !== 'KMTDTA.WHSIGIMG') contractError('signature source object')
  return {
    source_object: sourceObject,
    retrieved_at: textField(source, 'retrieved_at', 'signature query provenance'),
    row_limit: integerField(source, 'row_limit', 'signature query provenance'),
    pair_count: integerField(source, 'pair_count', 'signature query provenance'),
    returned_count: integerField(source, 'returned_count', 'signature query provenance'),
    complete: booleanField(source, 'complete', 'signature query provenance'),
    canonical_evidence_sha256: textField(source, 'canonical_evidence_sha256', 'signature query provenance'),
    error: optionalText(source, 'error', 'signature query provenance'),
  }
}

function adaptERPProvenance(value: unknown): PaymentNotesERPProvenance {
  const source = record(value, 'ERP provenance')
  const snapshotMode = textField(source, 'snapshot_mode', 'ERP provenance')
  if (snapshotMode !== 'independent_bounded_read_only_queries') contractError('ERP snapshot mode')
  const expectedPaymentQueries = records(source.expected_payment_queries, 'expected-payment query provenance')
    .map(adaptExpectedPaymentQuery)
  const signatureQueries = records(source.signature_queries, 'signature query provenance')
    .map(adaptSignatureQuery)
  const expectedPaymentQueryCount = integerField(source, 'expected_payment_query_count', 'ERP provenance')
  const signatureQueryCount = integerField(source, 'signature_query_count', 'ERP provenance')
  if (expectedPaymentQueryCount !== expectedPaymentQueries.length || signatureQueryCount !== signatureQueries.length) {
    contractError('ERP provenance query counts')
  }
  return {
    contract_version: textField(source, 'contract_version', 'ERP provenance'),
    snapshot_mode: snapshotMode,
    expected_payment_queries: expectedPaymentQueries,
    signature_queries: signatureQueries,
    expected_payment_query_count: expectedPaymentQueryCount,
    signature_query_count: signatureQueryCount,
    complete: booleanField(source, 'complete', 'ERP provenance'),
  }
}

function sum(items: BankItem[], pick: (item: BankItem) => number): number {
  return items.reduce((total, item) => total + pick(item), 0)
}

function adaptDeposit(value: unknown, items: BankItem[]): DepositSummary {
  const source = record(value, 'deposit')
  const depositKey = textField(source, 'deposit_key', 'deposit')
  const depositItems = items.filter((item) => item.deposit_key === depositKey)
  const matched = depositItems.filter((item) => matchedClassifications.has(item.classification))
  const accepted = depositItems.filter((item) => item.classification === 'LOCALLY_RECORDED_UNMATCHED')
  const rawStatus = textField(source, 'status', 'deposit')
  const quarantined = numberField(source, 'quarantined_row_count', 'deposit')
  const physicalItemCount = numberField(source, 'physical_item_count', 'deposit')
  const bankTotalCents = cents(source.physical_total, 'deposit physical total')
  const matchedTotalCents = sum(matched, (item) => item.amount_cents)
  const acceptedTotalCents = sum(accepted, (item) => item.amount_cents)
  const unresolvedCount = physicalItemCount - matched.length - accepted.length
  const unresolvedTotalCents = bankTotalCents - matchedTotalCents - acceptedTotalCents
  if (unresolvedCount < 0 || unresolvedTotalCents < 0) contractError('deposit reconciliation totals')
  const balanceFailure = ['MISSING_BALANCING_ITEM', 'MULTIPLE_BALANCING_ITEMS', 'OUT_OF_BALANCE'].includes(rawStatus)
  const itemBlockers = depositItems.filter((item) => item.exception_codes.some((code) => (
    code.startsWith('ROUTE_') || code === 'SOURCE_INCOMPLETE'
  ))).length
  const blockingCount = (balanceFailure ? 1 : 0) + quarantined + itemBlockers
  const localReviewComplete = depositItems.length > 0
    && depositItems.every((item) => item.current_review !== null)
  const status = balanceFailure
    ? 'BALANCE_FAILED'
    : rawStatus === 'SOURCE_ROWS_QUARANTINED' || unresolvedCount > 0
      ? 'REVIEW_REQUIRED'
      : localReviewComplete
        ? 'LOCAL_REVIEW_COMPLETE'
        : 'ARITHMETICALLY_BALANCED'
  return {
    deposit_key: depositKey,
    deposit_no: textField(source, 'deposit_number', 'deposit'),
    bank_location_raw: `${textField(source, 'store_number', 'deposit')} - ${textField(source, 'location_name', 'deposit')}`,
    canonical_location_code: textField(source, 'store_number', 'deposit'),
    payment_location_key: textField(source, 'location_key', 'deposit') || null,
    create_date: textField(source, 'create_business_date', 'deposit'),
    physical_item_count: physicalItemCount,
    bank_total_cents: bankTotalCents,
    virtual_credit_count: numberField(source, 'balancing_item_count', 'deposit'),
    virtual_credit_amount_cents: cents(source.balancing_total, 'deposit balancing total'),
    virtual_credit_difference_cents: cents(source.difference, 'deposit difference'),
    matched_count: matched.length,
    matched_total_cents: matchedTotalCents,
    accepted_unmatched_count: accepted.length,
    accepted_unmatched_total_cents: acceptedTotalCents,
    unresolved_count: unresolvedCount,
    unresolved_total_cents: unresolvedTotalCents,
    blocking_exception_count: blockingCount,
    balance_status: balanceFailure ? 'BALANCE_FAILED' : 'ARITHMETICALLY_BALANCED',
    status,
    exception_codes: [
      ...(rawStatus === 'BALANCED' ? [] : [rawStatus]),
      ...(quarantined ? ['QUARANTINED_BANK_ROWS'] : []),
      ...textArray(source.warnings, 'deposit warnings'),
    ],
  }
}

function countSummary(items: BankItem[], deposits: DepositSummary[]): PaymentNotesCountSummary {
  const matched = items.filter((item) => matchedClassifications.has(item.classification))
  const accepted = items.filter((item) => item.classification === 'LOCALLY_RECORDED_UNMATCHED')
  return {
    physical_item_count: deposits.reduce((total, deposit) => total + deposit.physical_item_count, 0),
    physical_total_cents: deposits.reduce((total, deposit) => total + deposit.bank_total_cents, 0),
    matched_count: matched.length,
    matched_total_cents: sum(matched, (item) => item.amount_cents),
    accepted_unmatched_count: accepted.length,
    accepted_unmatched_total_cents: sum(accepted, (item) => item.amount_cents),
    unresolved_count: deposits.reduce((total, deposit) => total + deposit.unresolved_count, 0),
    unresolved_total_cents: deposits.reduce((total, deposit) => total + deposit.unresolved_total_cents, 0),
    blocking_exception_count: deposits.reduce((total, deposit) => total + deposit.blocking_exception_count, 0),
  }
}

function adaptRunDetail(value: unknown): PaymentNotesRunDetail {
  const source = record(value, 'run detail')
  const erpProvenance = adaptERPProvenance(source.erp_provenance)
  const rawItems = records(source.items, 'run items')
  const reviewRows = records(source.reviews, 'run reviews')
  const reviewVersions = new Map<string, number>()
  for (const review of reviewRows) {
    const itemId = textField(review, 'item_id', 'run review')
    reviewVersions.set(itemId, (reviewVersions.get(itemId) ?? 0) + 1)
  }
  const warnings = textArray(source.warnings, 'run warnings')
  const signatureIncomplete = warnings.some((warning) => warning.toLowerCase().includes('signature evidence is incomplete'))
  const items = rawItems.map((item) => {
    const itemId = textField(item, 'item_id', 'bank item')
    return adaptBankItem(item, reviewVersions.get(itemId) ?? 0, signatureIncomplete)
  })
  const deposits = records(source.deposits, 'run deposits').map((deposit) => adaptDeposit(deposit, items))
  const summary = countSummary(items, deposits)
  const routeReference = record(source.route_reference, 'run route reference')
  const sourceEvidence = record(source.source, 'run source')
  const runId = textField(source, 'run_id', 'run detail')
  const quarantinedRows = records(source.quarantined_rows, 'quarantined rows')
  const sourceComplete = quarantinedRows.length === 0
    && rawItems.every((item) => booleanField(record(item.match, 'bank item match'), 'source_complete', 'bank item match'))
  const hasBalanceFailure = deposits.some((deposit) => deposit.status === 'BALANCE_FAILED')
  const localReviewComplete = items.length > 0
    && items.every((item) => item.current_review !== null)
  const status = hasBalanceFailure
    ? 'BALANCE_FAILED'
    : (summary.unresolved_count ?? 0) > 0
      ? 'REVIEW_REQUIRED'
      : localReviewComplete
        ? 'LOCAL_REVIEW_COMPLETE'
        : 'ARITHMETICALLY_BALANCED'
  const rulesetVersion = rawItems.length
    ? textField(record(rawItems[0].match, 'bank item match'), 'rule_version', 'bank item match')
    : 'No physical items'
  const run: PaymentNotesRunSummary = {
    run_id: runId,
    source_file_name: textField(sourceEvidence, 'name', 'run source'),
    source_sha256: textField(sourceEvidence, 'sha256', 'run source'),
    created_at: textField(source, 'created_at', 'run detail'),
    date_from: textField(source, 'date_from', 'run detail'),
    date_to: textField(source, 'date_to', 'run detail'),
    business_timezone: 'Not declared by source contract',
    status,
    counts_final: sourceComplete && deposits.every((deposit) => deposit.blocking_exception_count === 0),
    recommendation_only: true,
    erp_write_performed: false,
    route_reference_id: textField(routeReference, 'reference_id', 'run route reference'),
    route_reference_version: textField(routeReference, 'version_label', 'run route reference'),
    route_reference_sha256: textField(routeReference, 'source_sha256', 'run route reference'),
    ruleset_version: rulesetVersion,
    summary,
  }
  return {
    run,
    deposits,
    items,
    warnings: [
      ...warnings,
      ...(quarantinedRows.length ? [`${quarantinedRows.length} bank row(s) were quarantined; totals are not final.`] : []),
    ],
    source_complete: sourceComplete,
    route_reference_ready: Boolean(run.route_reference_id),
    erp_provenance: erpProvenance,
  }
}

function adaptRunSummary(value: unknown): PaymentNotesRunSummary {
  const source = record(value, 'run summary')
  const physicalCount = numberField(source, 'physical_item_count', 'run summary')
  const quarantined = numberField(source, 'quarantined_row_count', 'run summary')
  const backendStatus = textField(source, 'status', 'run summary')
  const status = backendStatus === 'completed'
    ? 'ARITHMETICALLY_BALANCED'
    : backendStatus === 'requires_review' || backendStatus === 'source_incomplete'
      ? 'REVIEW_REQUIRED'
      : backendStatus
  return {
    run_id: textField(source, 'run_id', 'run summary'),
    source_file_name: textField(source, 'source_name', 'run summary'),
    source_sha256: textField(source, 'source_sha256', 'run summary'),
    created_at: textField(source, 'created_at', 'run summary'),
    date_from: textField(source, 'date_from', 'run summary'),
    date_to: textField(source, 'date_to', 'run summary'),
    business_timezone: 'Not declared by source contract',
    status: quarantined ? 'REVIEW_REQUIRED' : status,
    counts_final: false,
    recommendation_only: true,
    erp_write_performed: false,
    route_reference_id: textField(source, 'route_reference_id', 'run summary'),
    route_reference_version: 'Bound reference',
    route_reference_sha256: '',
    ruleset_version: 'Open run for rules',
    summary: {
      physical_item_count: physicalCount,
      physical_total_cents: null,
      matched_count: null,
      matched_total_cents: null,
      accepted_unmatched_count: null,
      accepted_unmatched_total_cents: null,
      unresolved_count: null,
      unresolved_total_cents: null,
      blocking_exception_count: quarantined,
    },
  }
}

export async function getRouteReferenceStatus(signal?: AbortSignal): Promise<RouteReferenceStatus> {
  return adaptRouteReferenceStatus(await paymentNotesRequest('/route-references/status', { signal }))
}

export async function listRouteReferences(signal?: AbortSignal): Promise<RouteReferenceListResponse> {
  const source = record(await paymentNotesRequest('/route-references', { signal }), 'route-reference list')
  return {
    items: records(source.items, 'route-reference list items').map(adaptRouteReference),
    total: numberField(source, 'total', 'route-reference list'),
  }
}

export async function uploadRouteReference(
  file: File,
  versionLabel: string,
  signal?: AbortSignal,
): Promise<RouteReferenceSummary> {
  const form = new FormData()
  form.append('file', file)
  form.append('version_label', versionLabel)
  form.append('idempotency_key', paymentNotesIdempotencyKey('payment-notes-route-upload'))
  return adaptRouteReference(await paymentNotesRequest('/route-references/upload', {
    method: 'POST', body: form, signal,
  }))
}

export async function activateRouteReference(
  referenceId: string,
  signal?: AbortSignal,
): Promise<RouteReferenceSummary> {
  return adaptRouteReference(await paymentNotesRequest(
    `/route-references/${encodeURIComponent(referenceId)}/activate`,
    {
      method: 'POST',
      body: { idempotency_key: paymentNotesIdempotencyKey('payment-notes-route-activate') },
      signal,
    },
  ))
}

export async function listPaymentNotesRuns(
  filters: { limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<PaymentNotesRunListResponse> {
  const limit = filters.limit ?? 50
  const offset = filters.offset ?? 0
  const search = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  const source = record(await paymentNotesRequest(`/runs?${search.toString()}`, { signal }), 'run list')
  return {
    items: records(source.items, 'run list items').map(adaptRunSummary),
    total: numberField(source, 'total', 'run list'),
    limit,
    offset,
  }
}

export async function createPaymentNotesRun(
  file: File,
  dateFrom: string,
  dateTo: string,
  signal?: AbortSignal,
): Promise<PaymentNotesRunDetail> {
  const form = new FormData()
  form.append('file', file)
  form.append('date_from', dateFrom)
  form.append('date_to', dateTo)
  form.append('idempotency_key', paymentNotesIdempotencyKey('payment-notes-import'))
  return adaptRunDetail(await paymentNotesRequest('/runs', { method: 'POST', body: form, signal }))
}

export async function getPaymentNotesRun(
  runId: string,
  signal?: AbortSignal,
): Promise<PaymentNotesRunDetail> {
  return adaptRunDetail(await paymentNotesRequest(`/runs/${encodeURIComponent(runId)}`, { signal }))
}

export async function createItemReview(
  runId: string,
  itemId: string,
  payload: CreateItemReviewRequest,
  signal?: AbortSignal,
): Promise<ReviewResponse> {
  const response = record(await paymentNotesRequest(
    `/runs/${encodeURIComponent(runId)}/items/${encodeURIComponent(itemId)}/reviews`,
    { method: 'POST', body: payload, signal },
  ), 'review')
  if (textField(response, 'run_id', 'review') !== runId || textField(response, 'item_id', 'review') !== itemId) {
    contractError('review identity')
  }
  record(response.event, 'review event')
  record(response.current_review, 'current review')
  const detail = await getPaymentNotesRun(runId, signal)
  const item = detail.items.find((candidate) => candidate.bank_item_id === itemId)
  if (!item) contractError('reviewed item')
  return { item, run: detail.run, detail }
}
