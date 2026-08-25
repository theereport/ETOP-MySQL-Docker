import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import ts from 'typescript'
import {
  runBrowserRuntimeRegressions,
  runMandatoryWindowsBrowser,
  sanitizedBrowserStage,
} from './r68-browser-runtime.mjs'

const sourcePath = path.resolve(
  process.cwd(),
  'src/modules/document-intelligence/components/durableLockboxPreparation.ts',
)
const source = fs.readFileSync(sourcePath, 'utf8')
const transpiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
    esModuleInterop: true,
  },
}).outputText

globalThis.window = { setTimeout, clearTimeout }

let currentResponse = null
let detailResponse = null
const currentCalls = []
const detailCalls = []

const mockRequire = (specifier) => {
  if (specifier === '../api') {
    return {
      getCurrentDurableLockboxPreparation: async (sourceJobId) => {
        currentCalls.push(sourceJobId)
        if (!currentResponse) throw new Error('current response not configured')
        return currentResponse
      },
      getDurableLockboxPreparation: async (
        preparationJobId,
        includeTransactions,
      ) => {
        detailCalls.push({ preparationJobId, includeTransactions })
        if (!detailResponse) throw new Error('detail response not configured')
        return detailResponse
      },
      startDurableLockboxPreparation: async () => {
        throw new Error('not used')
      },
    }
  }
  if (
    specifier === './lockboxRecommendation'
    || specifier === './lockboxPreparation'
  ) return {}
  throw new Error(`Unexpected import in governed UI regression: ${specifier}`)
}

const module = { exports: {} }
new Function('require', 'module', 'exports', transpiled)(
  mockRequire,
  module,
  module.exports,
)
const governed = module.exports

const baseTransaction = (id, status = 'review_required') => ({
  transaction_id: id,
  envelope_number: 1,
  lockbox: 'test',
  date: '2026-08-01',
  batch: 1,
  batch_item: 1,
  check_number: id,
  check_amount: 100,
  aba_routing: '',
  account_number: '',
  customer_name: '',
  allocations: [],
  original_allocations: [],
  allocation_total: 0,
  difference: 100,
  balanced: false,
  status,
  check_page: 1,
  remittance_pages: [],
  reviewer: status === 'approved' ? 'human-reviewer' : '',
  notes: '',
  override_reason: '',
  reviewed_at: status === 'approved' ? '2026-08-01T00:00:00Z' : null,
})

const review = {
  job_id: 'source-test',
  source_file_name: 'sample.pdf',
  lockbox: 'test',
  transaction_date: '2026-08-01',
  transaction_count: 5,
  allocation_count: 0,
  total_check_amount: 500,
  total_allocation_amount: 0,
  total_difference: 500,
  balanced_count: 1,
  review_count: 4,
  approved_count: 1,
  corrected_count: 0,
  held_count: 0,
  transactions: [
    baseTransaction('T001'),
    baseTransaction('T002'),
    baseTransaction('T003'),
    baseTransaction('T004', 'no_remittance'),
    baseTransaction('T005', 'approved'),
  ],
  warnings: [],
}

const balancedResult = (id) => ({
  customer_resolution: {
    status: 'resolved',
    customer_number: `customer-${id}`,
    selection_basis: 'current_open_invoice_owner',
    matched_on: ['invoice'],
    warnings: [],
    matching_evidence: { failed_selection_gates: [] },
  },
  customer_snapshot: {
    fields: {
      customer_number: `customer-${id}`,
      customer_name: `Example ${id}`,
      phone: '',
      address_line_1: '',
      address_line_2: '',
      city: '',
      state: '',
      postal_code: '',
    },
  },
  recommendation: {
    status: 'recommended',
    allocations: [{
      invoice_number: `1234567${id.at(-1)}`,
      open_amount: '100.00',
      apply_amount: '100.00',
      business_type: 'Debit',
      reason: 'Synthetic exact recommendation.',
    }],
    check_amount: '100.00',
    suggested_total: '100.00',
    difference: '0.00',
    reasons: ['Exact synthetic test.'],
    warnings: [],
    can_auto_approve: false,
  },
  can_auto_approve: false,
  erp_write_performed: false,
})

const exceptionResult = (code, label) => ({
  exception_analysis: {
    primary_reason: {
      code,
      label,
      review_guidance: 'Keep this transaction in professional review.',
    },
  },
  evidence: {
    customer_resolution: {
      matching_evidence: {
        failed_selection_gates: ['supporting_evidence_only'],
      },
    },
  },
  can_auto_approve: false,
  erp_write_performed: false,
})

const preparation = {
  job_id: 'preparation-test',
  source_job_id: 'source-test',
  source_file_hash: 'hash-test',
  state: 'complete',
  expected_count: 5,
  terminal_count: 5,
  balanced_count: 2,
  exception_count: 2,
  preserved_count: 1,
  preparation_generation: 1,
  rule_version: 'increment3e-rule',
  service_version: 'increment3f-service',
  complete: true,
  counts_final: true,
  current_for_rule: true,
  reconciled: true,
  recommendation_not_decision: true,
  can_auto_approve: false,
  erp_write_performed: false,
  exception_reason_summary: {
    total_exception_count: 2,
    by_primary_reason: [
      { code: 'customer_rank_ambiguity', label: 'Rank ambiguity', count: 1 },
      { code: 'customer_not_found', label: 'Not found', count: 1 },
    ],
  },
  transactions: [
    { transaction_id: 'T001', ordinal: 1, state: 'prepared_balanced', source: { original_source: { allocations: [] } }, result: balancedResult('T001'), error: null },
    { transaction_id: 'T002', ordinal: 2, state: 'prepared_balanced', source: { original_source: { allocations: [] } }, result: balancedResult('T002'), error: null },
    { transaction_id: 'T003', ordinal: 3, state: 'prepared_exception', source: { original_source: { allocations: [] } }, result: exceptionResult('customer_rank_ambiguity', 'Rank ambiguity'), error: {} },
    { transaction_id: 'T004', ordinal: 4, state: 'prepared_exception', source: { original_source: { allocations: [] } }, result: exceptionResult('customer_not_found', 'Not found'), error: {} },
    { transaction_id: 'T005', ordinal: 5, state: 'preexisting_human_disposition', source: { original_source: { allocations: [] } }, result: {}, error: null },
  ],
}

assert.equal(governed.governedPreparationIsFinal(preparation), true)
const projected = governed.projectGovernedLockboxReview(review, preparation)
assert.equal(projected.review.balanced_count, 2)
assert.equal(projected.review.review_count, 2)
assert.equal(projected.review.approved_count, 1)
assert.equal(projected.review.held_count, 0)
assert.equal(
  projected.review.transactions.filter((item) => (
    !['balanced', 'approved', 'corrected'].includes(item.status)
  )).length,
  2,
)
assert.equal(projected.review.transactions[0].allocation_total, 100)
assert.equal(projected.review.transactions[0].customer_number, 'customer-T001')
assert.equal(projected.review.transactions[4].reviewer, 'human-reviewer')
assert.equal(projected.preparedTransactions.T001.recommendation.can_auto_approve, false)
assert.match(projected.preparedTransactions.T003.message, /Rank ambiguity/)

const heldReview = {
  ...review,
  held_count: 1,
  transactions: review.transactions.map((transaction) => (
    transaction.transaction_id === 'T003'
      ? {
        ...transaction,
        status: 'held',
        reviewer: 'hold-reviewer',
        notes: 'Waiting for customer evidence.',
        allocations: [{
          invoice_number: '',
          net_invoice_amount: 25,
          invoice_page: '',
          confidence: 0,
          allocation_kind: 'held_partial',
          erp_transaction_type: '',
        }],
      }
      : transaction
  )),
}
const heldProjected = governed.projectGovernedLockboxReview(
  heldReview,
  preparation,
)
const heldTransaction = heldProjected.review.transactions.find(
  (transaction) => transaction.transaction_id === 'T003',
)
assert.equal(heldProjected.review.held_count, 1)
assert.equal(heldProjected.review.review_count, 1)
assert.equal(heldTransaction.status, 'held')
assert.equal(heldTransaction.reviewer, 'hold-reviewer')
assert.equal(heldTransaction.notes, 'Waiting for customer evidence.')
assert.equal(heldTransaction.allocations[0].invoice_number, '')
assert.equal(heldTransaction.allocations[0].net_invoice_amount, 25)

const incomplete = { ...preparation, complete: false, counts_final: false }
assert.equal(governed.governedPreparationIsFinal(incomplete), false)

const terminalSummary = { ...preparation }
delete terminalSummary.transactions
assert.equal(
  governed.governedPreparationIsFinal(terminalSummary),
  false,
  'A terminal include_transactions=false summary is not review-ready.',
)
assert.deepEqual(
  governed.durableLockboxTransactions(terminalSummary),
  [],
  'An omitted summary transaction array sanitizes to an empty UI collection.',
)
assert.equal(
  governed.governedLockboxReviewIsReady(terminalSummary, {}),
  false,
  'A terminal summary must keep the raw review queue hidden.',
)
assert.equal(
  governed.governedLockboxReviewIsReady(preparation, {}),
  false,
  'Full preparation detail must still keep the raw review hidden before projection.',
)
assert.equal(
  governed.governedLockboxReviewIsReady(
    preparation,
    projected.preparedTransactions,
  ),
  true,
  'Only the exact full governed projection may make the review UI ready.',
)

currentResponse = terminalSummary
detailResponse = preparation
const transitionProgress = []
const transitioned = await governed.loadCurrentDurableLockboxPreparation(
  'source-test',
  (value) => transitionProgress.push(value),
)
assert.equal(transitioned, preparation)
assert.deepEqual(currentCalls, ['source-test'])
assert.deepEqual(detailCalls, [{
  preparationJobId: 'preparation-test',
  includeTransactions: true,
}])
assert.equal(transitionProgress.length, 1)
assert.equal(
  governed.governedPreparationIsFinal(transitionProgress[0]),
  false,
)
assert.equal(
  'transactions' in transitionProgress[0],
  false,
  'Progress callbacks must never publish full detail before governed projection.',
)

const alreadyFullProgress = []
const alreadyFull = await governed.waitForDurableLockboxPreparation(
  preparation,
  (value) => alreadyFullProgress.push(value),
)
assert.equal(alreadyFull, preparation)
assert.equal(alreadyFullProgress.length, 1)
assert.equal(
  'transactions' in alreadyFullProgress[0],
  false,
  'Even an initially full response must remain unpublished until projection.',
)

const malformedTransactions = {
  ...preparation,
  transactions: [...preparation.transactions.slice(0, 4), null],
}
assert.equal(
  governed.governedPreparationIsFinal(malformedTransactions),
  false,
  'Malformed detail cannot satisfy the exact full-transaction gate.',
)
assert.equal(
  governed.durableLockboxTransactions(malformedTransactions).length,
  4,
)
const malformedExtraTransaction = {
  ...preparation,
  transactions: [...preparation.transactions, null],
}
assert.equal(
  governed.governedPreparationIsFinal(malformedExtraTransaction),
  false,
  'An extra malformed transaction cannot hide behind the valid filtered count.',
)
const duplicateTransactions = {
  ...preparation,
  transactions: [
    ...preparation.transactions.slice(0, 4),
    { ...preparation.transactions[4], transaction_id: 'T004' },
  ],
}
assert.equal(
  governed.governedPreparationIsFinal(duplicateTransactions),
  false,
  'Duplicate durable transaction identities cannot satisfy the full-detail gate.',
)
assert.deepEqual(
  governed.durableLockboxExceptionReasons({
    ...terminalSummary,
    exception_reason_summary: { by_primary_reason: null },
  }),
  [],
  'A malformed or legacy exception summary cannot crash the workspace.',
)

const centerSource = fs.readFileSync(path.resolve(
  process.cwd(),
  'src/modules/document-intelligence/components/LockboxAutomationCenter.tsx',
), 'utf8')
assert.doesNotMatch(centerSource, /prepareAndPersistLockboxReview/)
assert.doesNotMatch(centerSource, /loadPreparedLockboxTransactions/)
assert.doesNotMatch(centerSource, /getLockboxPreparationCoverage/)
assert.match(centerSource, /durableLockboxExceptionReasons/)
assert.equal(
  (centerSource.match(/durableLockboxTransactions\([^)]*\)\.find/g) ?? [])
    .length,
  2,
  'Both UI transaction lookups must use the sanitized durable collection.',
)
assert.match(centerSource, /governedPreparationIsFinal/)
assert.match(centerSource, /governedLockboxReviewIsReady/)
assert.match(
  centerSource,
  /const preparationIncomplete = Boolean\(result && !governedReviewReady\)/,
)
assert.match(centerSource, /const preparationHasStarted = Boolean\(durablePreparation\)/)
assert.match(centerSource, /preparationHasStarted \? 'Resume' : 'Start'/)
assert.match(centerSource, /'Starting ERP & Allocations…'/)
assert.match(centerSource, /'Ready to Prepare'/)
assert.match(centerSource, /openTransactionQueue/)
assert.match(centerSource, /reviewReasonFilter/)
assert.match(centerSource, /queueTransactionIds/)
assert.match(centerSource, /primaryLockboxReasonCode\(durable\)/)
assert.match(centerSource, /const actionableReasonCounts/)
assert.match(
  centerSource,
  /reviewReasonFilter\)[\s\S]*transactionNeedsProfessionalReview\(transaction\)[\s\S]*transactionMatchesPrimaryReason/,
)
assert.match(centerSource, /review\?\.held_count/)
assert.match(centerSource, /review\?\.corrected_count/)
assert.match(centerSource, /correctedTransactions\.length/)
assert.match(centerSource, /approvedTransactions\.length/)
assert.match(
  centerSource,
  /preparationIncomplete \? '—' : approvedCount/,
  'Raw approved counts must stay hidden until the governed projection is ready.',
)
assert.match(centerSource, /reason\.code/)
assert.match(centerSource, /effectiveReviewCount > 0\s*\|\| heldCount > 0/)
assert.match(centerSource, /Held Transaction/)
assert.match(centerSource, /heldCount > 0\s*\? 'Held Work Remaining'/)
assert.match(centerSource, /effectiveReviewCount === 0\s*&& heldCount === 0/)
assert.match(centerSource, /aria-label="Filter transaction review queue"/)
assert.match(centerSource, /openTransactionQueue\('corrected'\)/)
assert.match(centerSource, /Saved Corrections/)

const liveReview = {
  ...review,
  transaction_count: 78,
  balanced_count: 19,
  review_count: 59,
  approved_count: 0,
  transactions: Array.from({ length: 78 }, (_, index) => (
    baseTransaction(
      `L${String(index + 1).padStart(3, '0')}`,
      index < 19 ? 'balanced' : 'review_required',
    )
  )),
}
const livePreparation = {
  ...preparation,
  expected_count: 78,
  terminal_count: 78,
  balanced_count: 30,
  exception_count: 48,
  preserved_count: 0,
  exception_reason_summary: {
    total_exception_count: 48,
    by_primary_reason: [
      { code: 'customer_rank_ambiguity', label: 'Rank ambiguity', count: 17 },
      { code: 'customer_not_found', label: 'Not found', count: 11 },
      { code: 'customer_candidate_unconfirmed', label: 'Candidate unconfirmed', count: 9 },
      { code: 'customer_resolved_no_exact_allocation', label: 'Allocation review', count: 6 },
      { code: 'invoice_owner_evidence_incomplete', label: 'Owner incomplete', count: 4 },
      { code: 'customer_conflict', label: 'Customer conflict', count: 1 },
    ],
  },
  transactions: Array.from({ length: 78 }, (_, index) => {
    const id = `L${String(index + 1).padStart(3, '0')}`
    return index < 30
      ? { transaction_id: id, ordinal: index + 1, state: 'prepared_balanced', source: { original_source: { allocations: [] } }, result: balancedResult(id), error: null }
      : { transaction_id: id, ordinal: index + 1, state: 'prepared_exception', source: { original_source: { allocations: [] } }, result: exceptionResult('customer_rank_ambiguity', 'Rank ambiguity'), error: {} }
  }),
}
const liveProjected = governed.projectGovernedLockboxReview(
  liveReview,
  livePreparation,
)
assert.equal(liveProjected.review.balanced_count, 30)
assert.equal(liveProjected.review.review_count, 48)

const browserHarnessHtml = fs.readFileSync(path.resolve(
  process.cwd(),
  'verification/r67-browser-harness.html',
), 'utf8')
const browserHarnessSource = fs.readFileSync(path.resolve(
  process.cwd(),
  'src/verification/R67BrowserHarness.tsx',
), 'utf8')
assert.match(browserHarnessHtml, /R67BrowserHarness\.tsx/)
assert.match(browserHarnessHtml, /__etopR67UnexpectedErrors/)
assert.match(browserHarnessHtml, /unhandledrejection/)
assert.match(browserHarnessSource, /RAW-REVIEW-MUST-STAY-HIDDEN/)
assert.match(browserHarnessSource, /include_transactions.*=== 'false'/)
assert.match(browserHarnessSource, /include_transactions.*=== 'true'/)
assert.match(browserHarnessSource, /Preparation Incomplete/)
assert.match(browserHarnessSource, /desktop-assistant-panel/)
assert.match(browserHarnessSource, /Toggle AI assistant/)
assert.match(browserHarnessSource, /WorkspaceErrorBoundary/)
assert.match(browserHarnessSource, /RECOVERED-DASHBOARD/)
assert.match(browserHarnessSource, /VITE_ETOP_ENVIRONMENT === 'isolated_test'/)
assert.match(browserHarnessSource, /unexpectedFetch/)
assert.doesNotMatch(browserHarnessSource, /https:\/\//)

await runBrowserRuntimeRegressions()

let browserQualificationPassed = true
if (process.platform === 'win32') {
  try {
    await runMandatoryWindowsBrowser()
  } catch (error) {
    browserQualificationPassed = false
    // Qualification evidence receives exactly one sanitized stage code. Raw
    // Edge DOM, stderr, paths, runtime identifiers, and exceptions stay local.
    console.error(sanitizedBrowserStage(error))
    process.exitCode = 1
  }
}

if (browserQualificationPassed) {
  console.log(
    'Governed Lockbox UI regression passed: terminal summary and full-before-projection stay hidden, exact detail is refetched and projected, malformed legacy shapes are contained, and raw 19/59 becomes authoritative 30/48.',
  )
}
