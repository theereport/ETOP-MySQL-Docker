import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import ts from 'typescript'

function loadTypeScriptModule(sourcePath, dependencies = {}) {
  const source = fs.readFileSync(sourcePath, 'utf8')
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText
  const module = { exports: {} }
  new Function('require', 'module', 'exports', transpiled)(
    (specifier) => {
      if (specifier in dependencies) return dependencies[specifier]
      throw new Error(`Unexpected dependency: ${specifier}`)
    },
    module,
    module.exports,
  )
  return module.exports
}

const componentRoot = path.resolve(
  process.cwd(),
  'src/modules/document-intelligence/components',
)
const invoiceRules = loadTypeScriptModule(path.join(
  componentRoot,
  'erpInvoiceNumber.ts',
))
const allocationRules = loadTypeScriptModule(
  path.join(componentRoot, 'lockboxAllocationRules.ts'),
  {
    './erpInvoiceNumber': invoiceRules,
  },
)

const serviceCharge = {
  customer_number: 'SYNTHETIC-CUSTOMER',
  invoice_number: '8',
  invoice_count: 8,
  transaction_type: 'SC',
  open_amount: 14.18,
  due_date: '2026-07-10',
}
const serviceChargeIdentity = allocationRules.getLegacyOpenItemIdentity(
  serviceCharge,
)
assert.deepEqual(serviceChargeIdentity, {
  key: 'open:SYNTHETIC-CUSTOMER|SC|8|8',
  displayNumber: '8',
  normalizedInvoiceNumber: '',
  allocationKind: 'service_charge',
  rawTransactionType: 'SC',
  openItemKey: 'SYNTHETIC-CUSTOMER|SC|8|8',
  invoiceCount: 8,
})
assert.equal(allocationRules.isLegacyServiceCharge(serviceCharge), true)

const invoice = {
  customer_number: 'SYNTHETIC-CUSTOMER',
  invoice_number: '999000001',
  invoice_count: 1,
  transaction_type: 'IN',
  open_amount: 100,
  due_date: '2026-07-10',
}
assert.equal(
  allocationRules.getLegacyOpenItemIdentity(invoice).key,
  'invoice:999000001',
)
assert.equal(
  allocationRules.getLegacyOpenItemIdentity({
    ...invoice,
    invoice_number: '1234567',
  }),
  null,
)

const recommendation = allocationRules.applyExactDueDatePriority(
  null,
  {
    confidence_score: 1,
    combination_result: {
      invoice_details: [invoice, serviceCharge],
    },
  },
  114.18,
)
assert.ok(recommendation)
assert.equal(recommendation.suggested_allocations.length, 2)
assert.equal(recommendation.suggested_total, 114.18)
assert.equal(recommendation.difference, 0)
const projectedServiceCharge = recommendation.suggested_allocations.find(
  (item) => item.allocation_kind === 'service_charge',
)
assert.ok(projectedServiceCharge)
assert.equal(projectedServiceCharge.invoice_number, '8')
assert.equal(
  projectedServiceCharge.open_item_key,
  'SYNTHETIC-CUSTOMER|SC|8|8',
)
assert.equal(projectedServiceCharge.erp_transaction_type, 'SC')
assert.equal(recommendation.can_auto_approve, false)

const recommendationSource = fs.readFileSync(
  path.join(componentRoot, 'lockboxRecommendation.ts'),
  'utf8',
)
assert.match(recommendationSource, /ERP open-A\/R retrieval failed/)
const openInvoiceFunction = recommendationSource.slice(
  recommendationSource.indexOf('export async function getLockboxOpenInvoices'),
  recommendationSource.indexOf(
    'export function reconcileRecommendationWithOpenInvoices',
  ),
)
assert.doesNotMatch(
  openInvoiceFunction,
  /return null/,
)

const workspaceSource = fs.readFileSync(
  path.join(componentRoot, 'LockboxReviewWorkspace.tsx'),
  'utf8',
)
assert.match(workspaceSource, /getLegacyOpenItemIdentity\(invoice\)/)
assert.match(workspaceSource, /current ERP open item\(s\)/)
assert.match(workspaceSource, /ERP Open A\/R/)
assert.match(workspaceSource, /\+ Add ERP Invoice \/ SC/)
assert.match(workspaceSource, /allocation_kind: identity\.allocationKind/)
assert.match(workspaceSource, /open_item_key: identity\.openItemKey/)
const openInvoiceFailure = workspaceSource.slice(
  workspaceSource.indexOf('}).catch((error) => {'),
  workspaceSource.indexOf('}).finally(() => {'),
)
assert.match(openInvoiceFailure, /setShowOpenInvoicePicker\(true\)/)

console.log(
  'Lockbox ERP Open-A/R regression passed: current open items are visible, HTTP failures remain visible, and governed SC rows participate without entering invoice-owner matching.',
)
