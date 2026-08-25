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

const transactions = Array.from({ length: 125 }, (_, index) => ({
  transaction_id: `transaction-${String(index + 1).padStart(3, '0')}`,
  status: 'review_required',
  check_amount: 100,
  allocations: [],
  customer_number: '',
  customer_name: '',
  check_page: 1,
  remittance_pages: [],
}))
const review = {
  job_id: 'resume-regression',
  transactions,
}

const preparationCalls = []
const saveCalls = []
const preparedResult = (transactionId) => ({
  transactionId,
  status: 'needs_review',
  preparedAt: '2026-07-30T00:00:00.000Z',
  invoiceNumbers: [],
  customer: null,
  customerSource: null,
  recommendation: null,
  message: 'Prepared regression transaction.',
  warnings: [],
})

const mockRequire = (specifier) => {
  if (specifier === '../api') {
    return {
      saveLockboxTransactionReview: async (
        _jobId,
        transactionId,
      ) => {
        saveCalls.push(transactionId)
        return review
      },
    }
  }
  if (specifier === './lockboxPreparation') {
    return {
      createLockboxPreparationContext: async () => ({}),
      prepareLockboxTransaction: async (transaction) => {
        preparationCalls.push(transaction.transaction_id)
        if (transaction.transaction_id === 'transaction-064') {
          throw new Error('Simulated ERP lookup failure.')
        }
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

const existingTransactions = Object.fromEntries(
  transactions.slice(0, 27).map((transaction) => [
    transaction.transaction_id,
    preparedResult(transaction.transaction_id),
  ]),
)
storage.set(
  'etop.lockbox.prepared.resume-regression',
  JSON.stringify({
    version: 1,
    jobId: 'resume-regression',
    savedAt: '2026-07-30T00:00:00.000Z',
    transactions: existingTransactions,
  }),
)
const legacyCache = await processing.loadPreparedLockboxTransactions(
  'resume-regression',
)
const partialCoverage = processing.getLockboxPreparationCoverage(
  review,
  legacyCache,
)
assert.equal(Object.keys(legacyCache).length, 27)
assert.equal(partialCoverage.completed, 27)
assert.equal(partialCoverage.complete, false)
assert.equal(partialCoverage.missingTransactionIds.length, 98)

const progress = []
const result = await processing.prepareAndPersistLockboxReview(
  'resume-regression',
  review,
  (item) => progress.push(item),
  { existingTransactions },
)

assert.equal(preparationCalls.length, 98)
assert.equal(saveCalls.length, 98)
assert.equal(preparationCalls[0], 'transaction-028')
assert.equal(preparationCalls.at(-1), 'transaction-125')
assert.equal(
  preparationCalls.includes('transaction-001'),
  false,
)
assert.equal(progress[0].current, 28)
assert.equal(progress.at(-1).current, 125)
assert.equal(result.coverage.total, 125)
assert.equal(result.coverage.completed, 125)
assert.equal(result.coverage.complete, true)
assert.equal(result.coverage.failed, 1)
assert.equal(result.coverage.missingTransactionIds.length, 0)
assert.equal(
  result.preparedTransactions['transaction-064'].status,
  'failed',
)

console.log(
  'Lockbox resume regression passed: 27 cached + 98 resumed = 125 checked.',
)
