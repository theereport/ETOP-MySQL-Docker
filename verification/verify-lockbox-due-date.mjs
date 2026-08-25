import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import ts from 'typescript'

const invoiceRulePath = path.resolve(
  process.cwd(),
  'src/modules/document-intelligence/components/erpInvoiceNumber.ts',
)
const invoiceRuleSource = fs.readFileSync(invoiceRulePath, 'utf8')
const invoiceRuleTranspiled = ts.transpileModule(invoiceRuleSource, {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText
const invoiceRuleUrl = (
  `data:text/javascript;base64,${Buffer.from(invoiceRuleTranspiled).toString('base64')}`
)
const invoiceRules = await import(invoiceRuleUrl)

const sourcePath = path.resolve(
  process.cwd(),
  'src/modules/document-intelligence/components/lockboxAllocationRules.ts',
)
const source = fs.readFileSync(sourcePath, 'utf8')
const transpiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText.replace(
  "'./erpInvoiceNumber'",
  `'${invoiceRuleUrl}'`,
)
const rules = await import(
  `data:text/javascript;base64,${Buffer.from(transpiled).toString('base64')}`
)

const currentRecommendation = {
  status: 'no_invoice_match',
  transaction_id: 'example-1129-36',
  customer_match: {
    customer_number: '520459',
    customer_name: 'Example Customer',
    confidence: 1,
    matched_on: ['customer number supplied by lockbox transaction'],
    warnings: [],
  },
  decision: {
    status: 'review_required',
    overall_confidence: 0.38,
    payment_intent: {
      intent_type: 'aging_match',
      confidence: 0.38,
      explanation: [],
    },
    decision_reasons: [
      'Check amount exactly matches a unique combination of EOM aging buckets.',
    ],
    warnings: [],
  },
  suggested_allocations: [],
  check_amount: 1129.36,
  suggested_total: 0,
  difference: 1129.36,
  can_auto_approve: false,
  decision_reasons: [
    'Check amount exactly matches a unique combination of EOM aging buckets.',
  ],
  warnings: [],
}

const legacyRecommendation = {
  customer_number: '520459',
  confidence_score: 0.96,
  combination_result: {
    invoice_details: [
      { invoice_number: '520199578', due_date: '2026-07-10', open_balance: 83 },
      { invoice_number: '471068556', due_date: '2026-07-10', open_balance: 24 },
      { invoice_number: '520200104', due_date: '2026-07-10', open_balance: 337.36 },
      { invoice_number: '471074502', due_date: '2026-07-10', open_balance: 162 },
      { invoice_number: '471075658', due_date: '2026-07-10', open_balance: 274 },
      { invoice_number: '520200656', due_date: '2026-07-10', open_balance: 249 },
      { invoice_number: '520201029', due_date: '2026-08-10', open_balance: 554.64 },
      { invoice_number: '520201323', due_date: '2026-08-10', open_balance: 656 },
    ],
  },
}

const result = rules.applyExactDueDatePriority(
  currentRecommendation,
  legacyRecommendation,
  1129.36,
)

assert.ok(result)
assert.equal(result.status, 'recommended')
assert.equal(result.allocation_basis, 'same_due_date_exact_match')
assert.equal(result.suggested_allocations.length, 6)
assert.equal(Number(result.suggested_total), 1129.36)
assert.equal(Number(result.difference), 0)
assert.equal(result.can_auto_approve, false)
assert.ok(
  result.suggested_allocations.every(
    (allocation) => allocation.due_date === '2026-07-10',
  ),
)
assert.ok(
  result.decision_reasons[0].includes(
    'all 6 open invoice(s) due 7/10/26',
  ),
)
assert.ok(
  result.decision_reasons.every(
    (reason) => !/aging bucket|eom aging/i.test(reason),
  ),
)

const ambiguousRecommendation = {
  ...legacyRecommendation,
  combination_result: {
    invoice_details: [
      ...legacyRecommendation.combination_result.invoice_details,
      {
        invoice_number: '520299001',
        due_date: '2026-09-10',
        open_balance: 1129.36,
      },
    ],
  },
}
assert.equal(
  rules.applyExactDueDatePriority(
    currentRecommendation,
    ambiguousRecommendation,
    1129.36,
  ),
  currentRecommendation,
)

const recommendationSourcePath = path.resolve(
  process.cwd(),
  'src/modules/document-intelligence/components/lockboxRecommendation.ts',
)
const recommendationSource = fs.readFileSync(
  recommendationSourcePath,
  'utf8',
)
const recommendationTranspiled = ts.transpileModule(
  recommendationSource,
  {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
      esModuleInterop: true,
    },
  },
).outputText
const recommendationModule = { exports: {} }
const executeRecommendation = new Function(
  'require',
  'module',
  'exports',
  recommendationTranspiled,
)
executeRecommendation(
  (specifier) => {
    if (specifier === '../../../api/client') {
      return { API_BASE: 'http://127.0.0.1:8000/api/v1' }
    }
    if (specifier === './lockboxAllocationRules') {
      return rules
    }
    if (specifier === './erpInvoiceNumber') return invoiceRules
    throw new Error(`Unexpected import in regression: ${specifier}`)
  },
  recommendationModule,
  recommendationModule.exports,
)

const requestedUrls = []
globalThis.fetch = async (url) => {
  requestedUrls.push(String(url))
  return {
    ok: true,
    json: async () => ({
      customer_number: '520459',
      invoices:
        legacyRecommendation.combination_result.invoice_details,
    }),
  }
}

const providerResult =
  await recommendationModule.exports.applyDueDateAllocationPriority(
    currentRecommendation,
    {
      customer_number: '520459',
      check_amount: 1129.36,
      payment_date: '2026-07-30',
      invoice_numbers: [],
    },
  )

assert.equal(requestedUrls.length, 1)
assert.ok(
  requestedUrls[0].includes('/api/test/open-invoices/520459'),
)
assert.ok(
  requestedUrls[0].includes('aging_as_of_date=2026-07-30'),
)
assert.equal(providerResult.status, 'recommended')
assert.equal(providerResult.suggested_allocations.length, 6)
assert.equal(Number(providerResult.suggested_total), 1129.36)
assert.ok(
  providerResult.suggested_allocations.every(
    (allocation) => allocation.due_date === '2026-07-10',
  ),
)

console.log(
  'Lockbox due-date regression passed: ERP open invoices return 6 rows = $1,129.36.',
)
