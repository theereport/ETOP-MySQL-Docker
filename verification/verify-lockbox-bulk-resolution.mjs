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

let bulkCalls = 0
let individualCalls = 0
let summaryCalls = 0
let recommendationCalls = 0

const customerRecord = (customerNumber, customerName) => ({
  customer_number: customerNumber,
  customer_name: customerName,
  phone: '419-555-0100',
  address_line_1: '100 MAIN STREET',
  address_line_2: '',
  city: 'MINSTER',
  state: 'OH',
  postal_code: '45865',
})

const recommendation = (transaction) => ({
  status: 'recommended',
  transaction_id: transaction.transaction_id,
  customer_match: {
    customer_number: transaction.customer_number,
    customer_name: transaction.customer_name,
    confidence: 1,
    matched_on: ['ERP customer verified from invoice ownership.'],
    warnings: [],
  },
  decision: null,
  suggested_allocations: [{
    invoice_number: transaction.allocations[0].invoice_number,
    open_amount: transaction.check_amount,
    suggested_apply_amount: transaction.check_amount,
    confidence: 1,
    reason: 'Regression allocation.',
  }],
  check_amount: transaction.check_amount,
  suggested_total: transaction.check_amount,
  difference: 0,
  can_auto_approve: false,
  decision_reasons: ['Regression allocation.'],
  warnings: [],
})

const mockRequire = (specifier) => {
  if (specifier === '../../../api/customers') {
    return {
      getCustomerSummary: async (customerNumber) => {
        summaryCalls += 1
        return {
          customer_number: customerNumber,
          customer_name:
            customerNumber === '520459'
              ? 'HORTER FARM RANCH'
              : 'AMBIGUOUS CUSTOMER',
          general: {
            phone: '419-555-0100',
            address_line_1: '100 MAIN STREET',
            city: 'MINSTER',
            state: 'OH',
            postal_code: '45865',
          },
        }
      },
    }
  }
  if (specifier === '../api') {
    return {
      resolveLockboxInvoiceOwners: async (invoiceNumbers) => {
        bulkCalls += 1
        assert.deepEqual(
          invoiceNumbers,
          ['100000001', '100000002', '100000003'],
        )
        return {
          invoice_owners: {
            '100000001': ['520459'],
            '100000002': ['520459'],
            '100000003': ['520459', '777777'],
          },
          customers: [
            customerRecord('520459', 'HORTER FARM RANCH'),
            customerRecord('777777', 'AMBIGUOUS CUSTOMER'),
          ],
          unresolved_invoice_numbers: [],
          warnings: [],
          invoice_count: 3,
          source_query_count: 30,
          read_only: true,
        }
      },
      resolveLockboxCustomer: async () => {
        individualCalls += 1
        return {
          auto_select: true,
          recommended_customer: {
            ...customerRecord('777777', 'AMBIGUOUS CUSTOMER'),
            score: 110,
            confidence: 0.99,
            match_type: 'invoice',
            matched_on: ['Invoice belongs to this ERP customer.'],
            matched_invoice_numbers: ['100000003'],
          },
          candidates: [],
          warnings: [],
        }
      },
    }
  }
  if (specifier === './lockboxAllocationRules') {
    return {
      shouldEvaluateDueDatePriority: () => false,
    }
  }
  if (specifier === './lockboxRecommendation') {
    return {
      createLockboxRecommendationCache: () => ({
        openInvoices: new Map(),
      }),
      getValidErpInvoiceNumbers: (allocations) => (
        allocations.map((allocation) => allocation.invoice_number)
      ),
      getLockboxRecommendation: async (transaction) => {
        recommendationCalls += 1
        return recommendation(transaction)
      },
      applyDueDateAllocationPriority: async (current) => current,
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

const makeTransaction = (id, invoiceNumber) => ({
  transaction_id: id,
  date: '2026-07-30',
  check_amount: 100,
  customer_number: '',
  customer_name: '',
  allocations: [{ invoice_number: invoiceNumber }],
})
const transactions = [
  makeTransaction('bulk-one', '100000001'),
  makeTransaction('bulk-two', '100000002'),
  makeTransaction('bulk-ambiguous', '100000003'),
]

const context = await preparation.createLockboxPreparationContext(
  transactions,
)
const first = await preparation.prepareLockboxTransaction(
  transactions[0],
  undefined,
  context,
)
const second = await preparation.prepareLockboxTransaction(
  transactions[1],
  undefined,
  context,
)
const ambiguous = await preparation.prepareLockboxTransaction(
  transactions[2],
  undefined,
  context,
)

assert.equal(bulkCalls, 1)
assert.equal(individualCalls, 1)
assert.equal(summaryCalls, 2)
assert.equal(recommendationCalls, 3)
assert.equal(first.customer.customerNumber, '520459')
assert.equal(second.customer.customerNumber, '520459')
assert.equal(ambiguous.customer.customerNumber, '777777')
assert.equal(first.customerSource, 'invoice')
assert.equal(ambiguous.customerSource, 'invoice')

console.log(
  'Lockbox bulk-resolution regression passed: one file read, shared customer cache, ambiguity fallback.',
)
