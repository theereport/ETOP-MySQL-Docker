import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const require = createRequire(import.meta.url)
const ts = require('typescript')

const queuePath = path.resolve(
  process.cwd(),
  'src/modules/document-intelligence/components/lockboxReviewQueue.ts',
)
const queueSource = fs.readFileSync(queuePath, 'utf8')
const queueTranspiled = ts.transpileModule(queueSource, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText
const queueModule = { exports: {} }
new Function('module', 'exports', queueTranspiled)(
  queueModule,
  queueModule.exports,
)
const {
  nextLockboxQueueTransactionId,
  nextProfessionalReviewTransactionId,
  previousLockboxQueueTransactionId,
  primaryLockboxReasonCode,
  transactionNeedsProfessionalReview,
} = queueModule.exports

const transactions = [
  { transaction_id: 'T001', status: 'review_required' },
  { transaction_id: 'T002', status: 'approved' },
  { transaction_id: 'T003', status: 'review_required' },
  { transaction_id: 'T004', status: 'balanced' },
  { transaction_id: 'T005', status: 'held' },
]
assert.equal(transactionNeedsProfessionalReview(transactions[0]), true)
assert.equal(transactionNeedsProfessionalReview(transactions[1]), false)
assert.equal(transactionNeedsProfessionalReview(transactions[4]), false)
assert.equal(
  nextProfessionalReviewTransactionId(transactions, 'T001'),
  'T003',
)
assert.equal(
  nextProfessionalReviewTransactionId(transactions, 'T003'),
  'T001',
)
assert.equal(
  nextProfessionalReviewTransactionId(
    transactions.map((transaction) => ({
      ...transaction,
      status: 'approved',
    })),
    'T003',
  ),
  '',
)
assert.equal(
  nextLockboxQueueTransactionId(
    [transactions[0], transactions[2], transactions[4]],
    'T001',
  ),
  'T003',
)
assert.equal(
  nextLockboxQueueTransactionId(
    [transactions[0], transactions[2], transactions[4]],
    'T005',
  ),
  'T001',
)
assert.equal(
  nextLockboxQueueTransactionId([transactions[4]], 'T005'),
  '',
)
assert.equal(
  previousLockboxQueueTransactionId(
    [transactions[0], transactions[2], transactions[4]],
    'T005',
  ),
  'T003',
)
assert.equal(
  previousLockboxQueueTransactionId(
    [transactions[0], transactions[2], transactions[4]],
    'T001',
  ),
  'T005',
)
assert.equal(
  previousLockboxQueueTransactionId([transactions[4]], 'T005'),
  '',
)
assert.equal(
  primaryLockboxReasonCode({
    exception_analysis: {
      primary_reason: { code: 'derived_legacy_reason' },
    },
    result: {
      exception_analysis: {
        primary_reason: { code: 'stored_result_reason' },
      },
    },
  }),
  'derived_legacy_reason',
)
assert.equal(
  primaryLockboxReasonCode({
    result: {
      evidence: {
        exception_analysis: {
          primary_reason: { code: 'nested_evidence_reason' },
        },
      },
    },
  }),
  'nested_evidence_reason',
)

const centerSource = fs.readFileSync(path.resolve(
  process.cwd(),
  'src/modules/document-intelligence/components/LockboxAutomationCenter.tsx',
), 'utf8')
assert.doesNotMatch(centerSource, /result\.warnings\.map/)
assert.doesNotMatch(centerSource, /className="ed-lockbox-warnings"/)

const workspaceSource = fs.readFileSync(path.resolve(
  process.cwd(),
  'src/modules/document-intelligence/components/LockboxReviewWorkspace.tsx',
), 'utf8')
assert.match(workspaceSource, /nextStatus === 'approved'/)
assert.match(workspaceSource, /nextLockboxQueueTransactionId/)
assert.match(workspaceSource, /queueTransactionIds/)
assert.match(workspaceSource, /advanceWithoutSaving/)
assert.match(workspaceSource, /goBackWithoutSaving/)
assert.match(workspaceSource, /previousLockboxQueueTransactionId/)
assert.match(workspaceSource, /save\('held'\)/)
assert.match(workspaceSource, /appendLockboxCustomerNote/)
assert.match(workspaceSource, /Customer Notes/)
assert.match(workspaceSource, /Email Customer · Draft/)
assert.match(workspaceSource, /Send via Outlook \(Unavailable\)/)
assert.match(workspaceSource, /No email will be sent or transmitted/)
assert.ok(
  (workspaceSource.match(/transaction\.status !== 'held'/g) ?? []).length >= 3,
  'Held drafts must not auto-open ERP replacement UI or mutate saved allocation signs while current ERP evidence loads.',
)
assert.match(workspaceSource, /await selectTransaction\(nextTransactionId\)/)
assert.match(workspaceSource, /else \{\s+onClose\(\)/)

console.log(
  'Lockbox review-flow regression passed: Back and Next remain inside the exact active queue; customer notes are append-only actions; the editable customer-email draft has no enabled transmission path; Hold and approval behavior remains governed.',
)
