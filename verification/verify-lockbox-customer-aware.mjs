import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import ts from 'typescript'

const sourcePath = path.resolve(
  process.cwd(),
  'src/modules/document-intelligence/components/lockboxPreparation.ts',
)
const source = fs.readFileSync(sourcePath, 'utf8')
const transpiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
    esModuleInterop: true,
  },
}).outputText

const genericRecommendation = {
  status: 'no_invoice_match',
  transaction_id: 'customer-520459-check',
  customer_match: {
    customer_number: '520459',
    customer_name: 'HORTER FARM RANCH',
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

const julyInvoices = [
  ['520199578', 83],
  ['471068556', 24],
  ['520200104', 337.36],
  ['471074502', 162],
  ['471075656', 274],
  ['520200656', 249],
]
let genericCalls = 0
let dueDateCalls = 0

const mockRequire = (specifier) => {
  if (specifier === '../../../api/customers') {
    return { getCustomerSummary: async () => ({}) }
  }
  if (specifier === '../api') {
    return { resolveLockboxCustomer: async () => ({ warnings: [] }) }
  }
  if (specifier === './lockboxAllocationRules') {
    return {
      shouldEvaluateDueDatePriority: () => true,
    }
  }
  if (specifier === './lockboxRecommendation') {
    return {
      getValidErpInvoiceNumbers: () => [],
      getLockboxRecommendation: async (transaction) => {
        genericCalls += 1
        assert.equal(transaction.customer_number, '520459')
        return genericRecommendation
      },
      applyDueDateAllocationPriority: async (
        current,
        transaction,
      ) => {
        dueDateCalls += 1
        assert.equal(current, genericRecommendation)
        assert.equal(transaction.customer_number, '520459')
        assert.equal(transaction.check_amount, 1129.36)
        assert.equal(transaction.payment_date, '2026-07-30')
        return {
          ...genericRecommendation,
          status: 'recommended',
          suggested_allocations: julyInvoices.map(
            ([invoiceNumber, amount]) => ({
              invoice_number: invoiceNumber,
              open_amount: amount,
              suggested_apply_amount: amount,
              due_date: '2026-07-10',
              confidence: 1,
              reason: 'Exact 7/10 due-date group.',
            }),
          ),
          suggested_total: 1129.36,
          difference: 0,
          decision_reasons: [
            'Check amount exactly matches all 6 open invoice(s) due 7/10/26.',
          ],
          allocation_basis: 'same_due_date_exact_match',
        }
      },
    }
  }
  throw new Error(`Unexpected import in regression: ${specifier}`)
}

const module = { exports: {} }
const execute = new Function(
  'require',
  'module',
  'exports',
  transpiled,
)
execute(mockRequire, module, module.exports)
const preparation = module.exports

const result = await preparation.getCustomerAwareLockboxRecommendation(
  {
    transaction_id: 'customer-520459-check',
    date: '2026-07-30',
    check_amount: 1129.36,
    customer_number: '520459',
    customer_name: 'HORTER FARM RANCH',
    allocations: [],
  },
  {
    customerNumber: '520459',
    customerName: 'HORTER FARM RANCH',
    phone: '605-492-3641',
    addressLine1: '225 MAIN STREET SOUTH',
    addressLine2: '',
    city: 'BRISTOL',
    state: 'SD',
    postalCode: '57219',
  },
)

assert.equal(genericCalls, 1)
assert.equal(dueDateCalls, 1)
assert.equal(result.recommendation.status, 'recommended')
assert.equal(result.recommendation.suggested_allocations.length, 6)
assert.equal(Number(result.recommendation.suggested_total), 1129.36)
assert.equal(Number(result.recommendation.difference), 0)
assert.equal(result.recommendation.can_auto_approve, false)
assert.ok(
  result.recommendation.suggested_allocations.every(
    (allocation) => allocation.due_date === '2026-07-10',
  ),
)

console.log(
  'Customer-aware regression passed: customer 520459 returns 6 July 10 invoices.',
)
