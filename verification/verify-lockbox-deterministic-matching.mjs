import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import ts from 'typescript'

const sourcePath = path.resolve(
  process.cwd(),
  'src/modules/document-intelligence/components/lockboxDraftProjection.ts',
)
const source = fs.readFileSync(sourcePath, 'utf8')
const transpiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText
const module = { exports: {} }
new Function('require', 'module', 'exports', transpiled)(
  () => ({}),
  module,
  module.exports,
)
const projection = module.exports

const recommendation = {
  status: 'recommended',
  transaction_id: 'G-SC-1',
  customer_match: {
    customer_number: '680753',
    customer_name: 'Tires 4 You',
    confidence: 1,
    matched_on: ['Phone, address, and ZIP confirm one ERP customer.'],
    warnings: [],
  },
  decision: {
    status: 'recommended',
    overall_confidence: 1,
    payment_intent: {
      intent_type: 'exact_remittance_plus_oldest_open_items',
      confidence: 1,
      explanation: [],
    },
    decision_reasons: [],
    warnings: [],
  },
  suggested_allocations: [{
    invoice_number: '8',
    open_amount: 14.18,
    suggested_apply_amount: 14.18,
    invoice_date: '2026-06-30',
    due_date: '2026-07-10',
    aging_bucket: 'CURRENT',
    transaction_type: 'debit',
    erp_transaction_type: 'SC',
    negative_debit_credit: false,
    allocation_kind: 'service_charge',
    open_item_key: '680753|SC|8|8',
    normalized_invoice_number: '',
    invoice_count: 8,
    confidence: 1,
    reason: 'The oldest remaining SC open item closes the residual.',
  }],
  check_amount: 14.18,
  suggested_total: 14.18,
  difference: 0,
  can_auto_approve: false,
  decision_reasons: [],
  warnings: [],
  allocation_basis: 'exact_remittance_plus_oldest_open_items',
}

assert.equal(
  projection.shouldProjectRecommendationDraft(
    recommendation,
    false,
    'review_required',
  ),
  true,
)
assert.equal(
  projection.shouldProjectRecommendationDraft(
    recommendation,
    true,
    'review_required',
  ),
  false,
)
assert.equal(
  projection.shouldProjectRecommendationDraft(
    recommendation,
    false,
    'corrected',
  ),
  false,
)
assert.equal(
  projection.shouldProjectRecommendationDraft(
    recommendation,
    false,
    'balanced',
  ),
  false,
)
assert.equal(
  projection.shouldProjectRecommendationDraft(
    recommendation,
    false,
    'held',
  ),
  false,
)

const draft = projection.recommendationDraft(recommendation, '35')
assert.equal(draft.length, 1)
assert.equal(draft[0].invoice_number, '8')
assert.equal(draft[0].net_invoice_amount, 14.18)
assert.equal(draft[0].allocation_kind, 'service_charge')
assert.equal(draft[0].erp_transaction_type, 'SC')
assert.equal(draft[0].open_item_key, '680753|SC|8|8')
assert.equal(projection.isGovernedServiceCharge(draft[0]), true)
assert.equal(projection.isGovernedServiceCharge({
  ...draft[0],
  open_item_key: '',
}), false)

const workspaceSource = fs.readFileSync(path.resolve(
  process.cwd(),
  'src/modules/document-intelligence/components/LockboxReviewWorkspace.tsx',
), 'utf8')
assert.match(workspaceSource, /shouldProjectRecommendationDraft\(/)
assert.match(workspaceSource, /allocationDraftDirtyRef\.current/)
assert.match(workspaceSource, /markAllocationDraftDirty\(true\)/)
assert.match(workspaceSource, /markAllocationDraftDirty\(false\)/)
assert.match(
  workspaceSource,
  /preparedTransaction\?\.customer[\s\S]*transaction\.status !== 'held'/,
)
assert.doesNotMatch(
  workspaceSource,
  /balancedRecommendation\s*&&\s*!allocationDraftDirty/,
)

console.log(
  'Lockbox deterministic-matching regression passed: governed SC rows project immediately and dirty drafts remain protected.',
)
