import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const centerPath = path.resolve(
  process.cwd(),
  'src/modules/document-intelligence/components/LockboxAutomationCenter.tsx',
)
const centerSource = fs.readFileSync(centerPath, 'utf8')

const handlerMatch = centerSource.match(
  /const openReasonReview = \(reasonCode: string\) => \{([\s\S]*?)\n  \}/,
)
assert.ok(handlerMatch, 'A governed-reason workspace opener must exist.')

const handlerSource = handlerMatch[1]
assert.match(
  handlerSource,
  /reviewTransactions\.find\(\(transaction\) => \(/,
  'The opener must start from the review queue ordering.',
)
assert.match(
  handlerSource,
  /transactionNeedsProfessionalReview\(transaction\)/,
  'The opener must not select a completed or held transaction.',
)
assert.match(
  handlerSource,
  /transactionMatchesPrimaryReason\([\s\S]*reasonCode/,
  'The selected transaction must match the clicked governed reason.',
)
assert.match(
  handlerSource,
  /openTransactionQueue\('exceptions', reasonCode\)/,
  'The reason must remain the active queue filter.',
)
assert.match(
  handlerSource,
  /void openReview\(firstTransaction\.transaction_id\)/,
  'The first matching transaction must open in the review workspace.',
)

assert.match(
  centerSource,
  /onClick=\{\(\) => openReasonReview\(reason\.code\)\}/,
  'Each governed reason button must use the workspace opener.',
)
const reasonButton = centerSource.match(
  /<button\s+key=\{reason\.code\}[\s\S]*?<\/button>/,
)
assert.ok(reasonButton, 'The governed-reason action button must exist.')
assert.match(reasonButton[0], /disabled=\{/)
assert.match(reasonButton[0], /reason\.count/)
assert.match(reasonButton[0], /isLoadingReview/)
assert.match(reasonButton[0], /isProcessing/)
assert.match(reasonButton[0], /isRestoring/)
assert.match(
  centerSource,
  /queueTransactionIds=\{visibleTransactions\.map\(/,
  'The workspace must receive the active filtered worklist for Next.',
)
assert.match(
  centerSource,
  /onClose=\{\(\) => setReviewTransactionId\(''\)\}/,
  'Closing the workspace must not clear the reason filter.',
)

console.log(
  'Lockbox governed-reason navigation passed: a reason opens its first active transaction, preserves the filtered workspace queue, and returns to the same filter.',
)
