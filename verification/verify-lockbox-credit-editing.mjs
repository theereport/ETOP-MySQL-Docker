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

const rulesPath = path.resolve(
  process.cwd(),
  'src/modules/document-intelligence/components/lockboxAllocationRules.ts',
)
const rulesSource = fs.readFileSync(rulesPath, 'utf8')
const rulesTranspiled = ts.transpileModule(rulesSource, {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText.replace(
  "'./erpInvoiceNumber'",
  `'${invoiceRuleUrl}'`,
)
const rules = await import(
  `data:text/javascript;base64,${Buffer.from(rulesTranspiled).toString('base64')}`
)

const negativeDebitCredit = {
  invoice_number: '431063896',
  transaction_type: 'Debit',
  original_amount: -916,
  open_balance: 916,
  due_date: '2026-08-10',
  aging_bucket: 'Current',
}
const effect = rules.getInvoiceBusinessEffect(negativeDebitCredit)

assert.equal(effect.businessType, 'credit')
assert.equal(effect.rawTransactionType, 'Debit')
assert.equal(effect.negativeDebit, true)
assert.equal(effect.amount, -916)

const recommendationPath = path.resolve(
  process.cwd(),
  'src/modules/document-intelligence/components/lockboxRecommendation.ts',
)
const recommendationSource = fs.readFileSync(recommendationPath, 'utf8')
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
    if (specifier === './lockboxAllocationRules') return rules
    if (specifier === './erpInvoiceNumber') return invoiceRules
    throw new Error(`Unexpected import in regression: ${specifier}`)
  },
  recommendationModule,
  recommendationModule.exports,
)

const current = {
  status: 'recommended',
  transaction_id: 'credit-regression',
  customer_match: {
    customer_number: '431664',
    customer_name: 'Credit Example',
    confidence: 1,
    matched_on: ['ERP customer verified.'],
    warnings: [],
  },
  decision: {
    status: 'recommended',
    overall_confidence: 0.7,
    payment_intent: {
      intent_type: 'oldest_first',
      confidence: 0.7,
      explanation: [],
    },
    decision_reasons: [],
    warnings: [],
  },
  suggested_allocations: [
    {
      invoice_number: '431063896',
      open_amount: 916,
      suggested_apply_amount: 916,
      confidence: 0.7,
      reason: 'Regression recommendation.',
    },
    {
      invoice_number: '431074492',
      open_amount: 142,
      suggested_apply_amount: 142,
      confidence: 0.7,
      reason: 'Regression recommendation.',
    },
  ],
  check_amount: 1058,
  suggested_total: 1058,
  difference: 0,
  can_auto_approve: false,
  decision_reasons: [],
  warnings: [],
}

const reconciled =
  recommendationModule.exports.reconcileRecommendationWithOpenInvoices(
    current,
    [
      negativeDebitCredit,
      {
        invoice_number: '431074492',
        transaction_type: 'Debit',
        original_amount: 142,
        open_balance: 142,
        due_date: '2026-07-10',
      },
    ],
  )

const credit = reconciled.suggested_allocations.find(
  (allocation) => allocation.invoice_number === '431063896',
)
assert.ok(credit)
assert.equal(credit.transaction_type, 'credit')
assert.equal(credit.erp_transaction_type, 'Debit')
assert.equal(credit.negative_debit_credit, true)
assert.equal(Number(credit.open_amount), -916)
assert.equal(Number(credit.suggested_apply_amount), -916)
assert.equal(Number(reconciled.suggested_total), -774)
assert.equal(Number(reconciled.difference), 1832)
assert.equal(reconciled.status, 'review_required')
assert.equal(reconciled.can_auto_approve, false)

const workspacePath = path.resolve(
  process.cwd(),
  'src/modules/document-intelligence/components/LockboxReviewWorkspace.tsx',
)
const workspaceSource = fs.readFileSync(workspacePath, 'utf8')
assert.match(workspaceSource, /\+ Add ERP Invoice/)
assert.match(workspaceSource, /\+ Add Blank Row/)
assert.match(workspaceSource, /cash-ai-delete-row/)
assert.match(workspaceSource, /Reset Draft to Prepared Recommendation/)
assert.match(workspaceSource, /ERP Debit · negative source amount/)

console.log(
  'Lockbox credit/editing regression passed: negative debit is a credit and recommendation rows are editable.',
)
