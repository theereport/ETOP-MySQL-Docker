import assert from 'node:assert/strict'
import fs from 'node:fs'

const center = fs.readFileSync(
  new URL(
    '../src/modules/document-intelligence/components/LockboxAutomationCenter.tsx',
    import.meta.url,
  ),
  'utf8',
)
const api = fs.readFileSync(
  new URL('../src/modules/document-intelligence/api.ts', import.meta.url),
  'utf8',
)
const css = fs.readFileSync(
  new URL(
    '../src/modules/document-intelligence/DocumentIntelligence.css',
    import.meta.url,
  ),
  'utf8',
)

assert.match(center, /PNC_COMPARISON_TRAINING_VISIBLE = false/)
assert.match(
  center,
  /PNC_COMPARISON_TRAINING_VISIBLE && \(\s*<article[\s\S]*Train From PNC Comparison/,
)
assert.match(center, /downloadLockboxReviewQueueExport\(selectedJobId/)
assert.match(center, /transaction_ids: visibleTransactions\.map/)
assert.match(center, /reason_code: reviewReasonFilter/)
assert.match(center, /'Export to Excel'/)
assert.match(api, /lockbox\/review-queue-export/)
assert.match(api, /response\.blob\(\)/)
assert.match(
  css,
  /@media \(max-width: 620px\)[\s\S]*\.lockbox-stepper\.four-step \{ grid-template-columns: 1fr; \}/,
)

console.log('Lockbox queue export and hidden PNC training verification passed.')
