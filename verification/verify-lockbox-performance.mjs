import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import ts from 'typescript'

const sourcePath = path.resolve(
  process.cwd(),
  'src/modules/document-intelligence/components/lockboxProcessing.ts',
)
const source = fs.readFileSync(sourcePath, 'utf8')
const transpiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
    esModuleInterop: true,
  },
}).outputText

const invoiceRulePath = path.resolve(
  process.cwd(),
  'src/modules/document-intelligence/components/erpInvoiceNumber.ts',
)
const invoiceRuleSource = fs.readFileSync(invoiceRulePath, 'utf8')
const invoiceRuleTranspiled = ts.transpileModule(invoiceRuleSource, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText
const invoiceRuleModule = { exports: {} }
new Function(
  'module',
  'exports',
  invoiceRuleTranspiled,
)(invoiceRuleModule, invoiceRuleModule.exports)

const storage = new Map()
globalThis.window = {
  localStorage: {
    getItem: (key) => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
    removeItem: (key) => storage.delete(key),
  },
  setTimeout,
  clearTimeout,
}

const transactions = Array.from({ length: 12 }, (_, index) => ({
  transaction_id: `performance-${String(index + 1).padStart(2, '0')}`,
  status: 'review_required',
  check_amount: 100,
  allocations: [],
  customer_number: '',
  customer_name: '',
  check_page: 1,
  remittance_pages: [],
}))
const review = {
  job_id: 'performance-regression',
  transactions,
}

let contextCalls = 0
let preparationInFlight = 0
let maximumPreparationInFlight = 0
let saveInFlight = 0
let maximumSaveInFlight = 0
const preparationContext = { shared: true }

const preparedResult = (transactionId) => ({
  transactionId,
  status: 'needs_review',
  preparedAt: '2026-07-30T00:00:00.000Z',
  invoiceNumbers: [],
  customer: null,
  customerSource: null,
  recommendation: null,
  message: 'Prepared performance transaction.',
  warnings: [],
})

const mockRequire = (specifier) => {
  if (specifier === '../api') {
    return {
      saveLockboxTransactionReview: async () => {
        saveInFlight += 1
        maximumSaveInFlight = Math.max(
          maximumSaveInFlight,
          saveInFlight,
        )
        await new Promise((resolve) => setTimeout(resolve, 2))
        saveInFlight -= 1
        return review
      },
    }
  }
  if (specifier === './lockboxPreparation') {
    return {
      createLockboxPreparationContext: async () => {
        contextCalls += 1
        return preparationContext
      },
      prepareLockboxTransaction: async (
        transaction,
        _signal,
        context,
      ) => {
        assert.equal(context, preparationContext)
        preparationInFlight += 1
        maximumPreparationInFlight = Math.max(
          maximumPreparationInFlight,
          preparationInFlight,
        )
        await new Promise((resolve) => setTimeout(resolve, 10))
        preparationInFlight -= 1
        return preparedResult(transaction.transaction_id)
      },
    }
  }
  if (specifier === './erpInvoiceNumber') return invoiceRuleModule.exports
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
const processing = module.exports

const result = await processing.prepareAndPersistLockboxReview(
  'performance-regression',
  review,
)

assert.equal(contextCalls, 1)
assert.equal(maximumPreparationInFlight, 6)
assert.equal(maximumSaveInFlight, 1)
assert.equal(result.coverage.completed, 12)
assert.equal(result.coverage.complete, true)

console.log(
  'Lockbox performance regression passed: 6 read workers + 1 serialized writer.',
)
