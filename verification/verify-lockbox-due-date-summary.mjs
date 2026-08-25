import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const require = createRequire(import.meta.url)
const ts = require('typescript')

function loadTypeScriptModule(sourcePath) {
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
const summaryModule = loadTypeScriptModule(path.join(
  componentRoot,
  'lockboxDueDateSummary.ts',
))

const openItems = [
  { id: 'current-debit', due_date: '2026-09-10', amount: 100 },
  { id: 'current-credit', due_date: '2026-09-10', amount: -25 },
  { id: 'current-zero-day', due_date: '2026-08-14', amount: 5 },
  { id: 'one-day', due_date: '2026-08-13', amount: 10 },
  { id: 'thirty-days', due_date: '2026-07-15', amount: 20 },
  { id: 'thirty-one-days', due_date: '2026-07-14', amount: 30 },
  { id: 'sixty-days', due_date: '2026-06-15', amount: 40 },
  { id: 'sixty-one-days', due_date: '2026-06-14', amount: 50 },
  { id: 'ninety-days', due_date: '2026-05-16', amount: 60 },
  { id: 'ninety-one-days', due_date: '2026-05-15', amount: 70 },
  { id: 'net-credit-debit', due_date: '2026-04-15', amount: 15 },
  { id: 'net-credit-credit', due_date: '2026-04-15', amount: -45 },
  { id: 'missing-date', due_date: null, amount: 80 },
  { id: 'missing-amount', due_date: '2026-03-15', amount: null },
]
const unchangedOpenItems = structuredClone(openItems)

const result = summaryModule.buildLockboxDueDateSummary(
  openItems,
  '2026-08-14',
  (item) => item.amount,
)

assert.deepEqual(openItems, unchangedOpenItems)
assert.equal(result.sourceItemCount, 14)
assert.equal(result.summarizedItemCount, 12)
assert.equal(result.omittedItemCount, 2)
assert.equal(result.groups.length, 10)

const september = result.groups.find(
  (group) => group.dueDate === '2026-09-10',
)
assert.ok(september)
assert.equal(september.bucketLabel, 'Current')
assert.equal(september.balanceType, 'Debit')
assert.equal(september.count, 2)
assert.equal(september.total, 75)

const netCredit = result.groups.find(
  (group) => group.dueDate === '2026-04-15',
)
assert.ok(netCredit)
assert.equal(netCredit.bucketLabel, 'Past Due 90+')
assert.equal(netCredit.balanceType, 'Credit')
assert.equal(netCredit.count, 2)
assert.equal(netCredit.total, -30)

const expectedBoundaries = new Map([
  ['2026-08-14', 'Current'],
  ['2026-08-13', 'Past Due 1–30'],
  ['2026-07-15', 'Past Due 1–30'],
  ['2026-07-14', 'Past Due 31–60'],
  ['2026-06-15', 'Past Due 31–60'],
  ['2026-06-14', 'Past Due 61–90'],
  ['2026-05-16', 'Past Due 61–90'],
  ['2026-05-15', 'Past Due 90+'],
])
for (const [dueDate, expectedBucket] of expectedBoundaries) {
  assert.equal(
    result.groups.find((group) => group.dueDate === dueDate)?.bucketLabel,
    expectedBucket,
  )
}

assert.deepEqual(
  result.groups.map((group) => group.dueDate),
  [
    '2026-09-10',
    '2026-08-14',
    '2026-08-13',
    '2026-07-15',
    '2026-07-14',
    '2026-06-15',
    '2026-06-14',
    '2026-05-16',
    '2026-05-15',
    '2026-04-15',
  ].filter((date) => result.groups.some((group) => group.dueDate === date)),
)

const explicitFallback = summaryModule.buildLockboxDueDateSummary([
  {
    due_date: '2026-01-01',
    aging_bucket: 'Past Due 121+',
    amount: 10,
  },
  {
    due_date: '2026-01-02',
    aging_bucket: 'current_or_future',
    amount: 5,
  },
], '', (item) => item.amount)
assert.equal(explicitFallback.groups[0].bucketLabel, 'Current')
assert.equal(explicitFallback.groups[1].bucketLabel, 'Past Due 90+')

const workspaceSource = fs.readFileSync(
  path.join(componentRoot, 'LockboxReviewWorkspace.tsx'),
  'utf8',
)
assert.match(workspaceSource, /buildLockboxDueDateSummary\(\s*openInvoices,/)
assert.match(
  workspaceSource,
  /\(invoice\) => getInvoiceBusinessEffect\(invoice\)\.amount/,
)
assert.match(workspaceSource, /ERP Open A\/R by Due Date/)
assert.match(workspaceSource, /This does not change the allocation draft/)
assert.match(workspaceSource, /Count \{group\.count\}/)
assert.match(workspaceSource, /money\(group\.total\)/)
assert.match(
  workspaceSource,
  /customerNumber\.trim\(\)\s*&&\s*!isLoadingOpenInvoices\s*&&\s*!openInvoiceError/,
)

const helperSource = fs.readFileSync(
  path.join(componentRoot, 'lockboxDueDateSummary.ts'),
  'utf8',
)
assert.doesNotMatch(helperSource, /setAllocations|ReviewedLockboxAllocation/)

const stylesheet = fs.readFileSync(path.resolve(
  process.cwd(),
  'src/modules/document-intelligence/DocumentIntelligence.css',
), 'utf8')
assert.match(stylesheet, /\.lockbox-due-date-summary-list/)
assert.match(stylesheet, /\.lockbox-due-date-summary-list \.credit/)

console.log(
  'Lockbox due-date summary regression passed: all supplied ERP items are grouped by exact due date, boundary-aged into five buckets, signed credits reduce totals, incomplete evidence stays visible, and the allocation draft is not mutated.',
)
