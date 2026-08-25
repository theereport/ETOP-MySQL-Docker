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
  { './erpInvoiceNumber': invoiceRules },
)
const agingBuckets = loadTypeScriptModule(
  path.join(componentRoot, 'lockboxAgingBuckets.ts'),
  { './lockboxAllocationRules': allocationRules },
)

const openItems = [
  {
    invoice_number: '990000001',
    transaction_type: 'IN',
    open_amount: 10,
    due_date: '2026-10-10',
    aging_bucket: 'Future',
  },
  {
    invoice_number: '990000002',
    transaction_type: 'IN',
    open_amount: 100,
    due_date: '2026-09-10',
    aging_bucket: 'Current',
  },
  {
    invoice_number: '990000003',
    transaction_type: 'Debit',
    original_amount: -20,
    open_balance: 20,
    due_date: '2026-09-10',
    aging_bucket: 'CURRENT DUE',
  },
  {
    customer_number: 'SYNTHETIC-CUSTOMER',
    invoice_number: '8',
    invoice_count: 8,
    transaction_type: 'SC',
    open_amount: 5,
    due_date: '2026-09-10',
    aging_bucket: 'Current',
  },
  {
    invoice_number: '990000004',
    transaction_type: 'IN',
    open_amount: 30,
    due_date: '2026-08-20',
    aging_bucket: 'Past Due 1-30',
  },
  {
    invoice_number: '990000005',
    transaction_type: 'IN',
    open_amount: 60,
    due_date: '2026-07-20',
    aging_bucket: 'Past Due 31-60',
  },
  {
    invoice_number: '990000006',
    transaction_type: 'IN',
    open_amount: 90,
    due_date: '2026-06-20',
    aging_bucket: 'Past Due 61-90',
  },
  {
    invoice_number: '990000007',
    transaction_type: 'IN',
    open_amount: 120,
    due_date: '2026-05-20',
    aging_bucket: 'Past Due 91-120',
  },
  {
    invoice_number: '990000008',
    transaction_type: 'IN',
    open_amount: 121,
    due_date: '2026-04-20',
    aging_bucket: 'Past Due 121+',
  },
]

const result = agingBuckets.buildLockboxAgingBucketResult(openItems, '10')
assert.equal(result.buckets.length, 7)
assert.equal(result.unclassifiedItemCount, 0)

const current = result.buckets.find((bucket) => bucket.key === 'current')
assert.ok(current)
assert.equal(current.count, 3)
assert.equal(current.total, 85)
assert.equal(current.selectable, true)
assert.equal(current.firstDueDate, '2026-09-10')
assert.equal(current.lastDueDate, '2026-09-10')
assert.equal(current.allocations.length, 3)
assert.equal(
  current.allocations.find((item) => item.invoice_number === '990000003')
    .net_invoice_amount,
  -20,
)
assert.equal(
  current.allocations.find((item) => item.allocation_kind === 'service_charge')
    .open_item_key,
  'SYNTHETIC-CUSTOMER|SC|8|8',
)

const pastDue121 = result.buckets.find(
  (bucket) => bucket.key === 'past_due_121_plus',
)
assert.ok(pastDue121)
assert.equal(pastDue121.total, 121)
assert.equal(pastDue121.allocations[0].invoice_page, '10')

const incomplete = agingBuckets.buildLockboxAgingBucketResult([
  ...openItems,
  {
    invoice_number: 'invalid',
    transaction_type: 'IN',
    open_amount: 50,
    due_date: '2026-09-10',
    aging_bucket: 'Current',
  },
  {
    invoice_number: '990000009',
    transaction_type: 'IN',
    open_amount: 25,
    due_date: null,
    aging_bucket: 'Unknown',
  },
], '10')
const incompleteCurrent = incomplete.buckets.find(
  (bucket) => bucket.key === 'current',
)
assert.ok(incompleteCurrent)
assert.equal(incompleteCurrent.selectable, false)
assert.equal(incompleteCurrent.total, null)
assert.equal(incompleteCurrent.invalidItemCount, 1)
assert.equal(incomplete.unclassifiedItemCount, 1)

const workspaceSource = fs.readFileSync(
  path.join(componentRoot, 'LockboxReviewWorkspace.tsx'),
  'utf8',
)
assert.match(workspaceSource, /useState\(true\)/)
assert.match(workspaceSource, /Expand transactions/)
assert.match(workspaceSource, /window\.confirm/)
assert.match(workspaceSource, /setAllocations\(cloneAllocations\(bucket\.allocations\)\)/)
assert.match(workspaceSource, /It does not save or approve/)
assert.match(workspaceSource, /save\('held'\)/)
assert.match(workspaceSource, /nextStatus === 'approved' \|\| nextStatus === 'held'/)
assert.match(workspaceSource, /Leave this transaction in Open Review and discard the unsaved/)
assert.match(workspaceSource, /const hasUnsavedReviewChanges/)
assert.match(workspaceSource, /const hasUnsavedAllocationChanges/)
assert.match(workspaceSource, /hasUnsavedAllocationChanges\s*&&\s*!window\.confirm/)
assert.match(workspaceSource, />\s*Next\s*</)
assert.match(workspaceSource, />\s*\{isSaving \? 'Saving…' : 'Hold'\}\s*</)
assert.match(workspaceSource, /role="dialog"/)
assert.match(workspaceSource, /aria-modal="true"/)
assert.match(workspaceSource, /closeOnEscape/)
assert.match(workspaceSource, /containDialogFocus/)
assert.match(workspaceSource, /dialog\.contains\(document\.activeElement\)/)
assert.match(workspaceSource, /previouslyFocusedElementRef\.current\?\.focus\(\)/)
assert.match(workspaceSource, /incompleteEvidenceMessage/)
assert.match(workspaceSource, /aria-label=\{`Invoice number for allocation row/)
assert.match(workspaceSource, /aria-label=\{`Remove allocation row/)

const stylesheet = fs.readFileSync(path.resolve(
  process.cwd(),
  'src/modules/document-intelligence/DocumentIntelligence.css',
), 'utf8')
assert.match(stylesheet, /\.lockbox-review-body\.queue-collapsed/)
assert.match(stylesheet, /\.lockbox-aging-bucket-grid/)

console.log(
  'Lockbox bucket-review regression passed: seven ERP aging buckets preserve signed open-item identity, incomplete evidence fails closed, selection replaces only the local draft, and the transaction rail starts collapsed.',
)
