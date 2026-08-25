import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import test from 'node:test'

function source(path) {
  return readFileSync(new URL(`../${path}`, import.meta.url), 'utf8')
}

test('exact R72 launcher readiness survives the Payment Notes router merge', () => {
  const main = source('backend/main.py')

  assert.match(main, /backend_ready/)
  assert.match(main, /madden_database_ready/)
  assert.match(main, /knowledge_ready/)
  assert.match(main, /madden_database\.test_connection\(\)/)
  assert.match(
    main,
    /from modules\.payment_notes\.api import router as payment_notes_router/,
  )
  assert.match(main, /app\.include_router\(payment_notes_router\)/)
  assert.ok(!main.startsWith('\uFEFF'), 'backend/main.py must not gain a BOM')
})

test('Payment Notes ERP access remains fixed, bounded, and read only', () => {
  const repository = source('backend/modules/payment_notes/erp_repository.py')

  assert.match(repository, /FROM KMTDTA\.WHSIGPAY/)
  assert.match(repository, /FROM KMTDTA\.WHSIGIMG/)
  assert.match(repository, /UPPER\(TRIM\(TYPE\)\) = 'CHECK'/)
  assert.match(repository, /CRTSTAMP >= %s/)
  assert.match(repository, /CRTSTAMP < %s/)
  assert.match(repository, /EXPECTED_PAYMENT_ROW_LIMIT/)
  assert.match(repository, /SIGNATURE_ROW_LIMIT/)
  assert.doesNotMatch(
    repository,
    /\b(?:INSERT|UPDATE|DELETE|MERGE|REPLACE|TRUNCATE|DROP|ALTER)\b/i,
  )
})

test('candidate completeness, cross-run policy, and sensitive bank redaction fail closed', () => {
  const matching = source('backend/modules/payment_notes/matching.py')
  const capture = source('backend/modules/payment_notes/remote_capture.py')
  const service = source('backend/modules/payment_notes/service.py')

  assert.match(matching, /candidate_population_complete/)
  assert.match(matching, /CROSS_RUN_REUSE_POLICY_UNRESOLVED/)
  assert.match(capture, /SENSITIVE_BANK_FIELDS/)
  assert.match(capture, /accountNo/)
  assert.match(capture, /routingNo/)
  assert.match(service, /redacted_raw_values\(\)/)
  assert.match(service, /canonical_evidence_sha256/)
  assert.doesNotMatch(service, /self\.repository\.initialize\(\)/)
})

test('trailing optional bank fields and asynchronous form resets are deterministic', () => {
  const capture = source('backend/modules/payment_notes/remote_capture.py')
  const workspace = source('src/features/payment-notes/PaymentNotesWorkspace.tsx')
  const components = source('src/features/payment-notes/components.tsx')

  assert.match(capture, /payment-notes-remote-capture@1\.1\.0/)
  assert.match(capture, /OPTIONAL_TRAILING_HEADERS = \("checkNo", "CaptureChannel"\)/)
  assert.match(capture, /SOURCE_TRAILING_OPTIONAL_COLUMNS_PADDED/)
  assert.match(workspace, /const form = event\.currentTarget/)
  assert.match(components, /const form = event\.currentTarget/)
  assert.doesNotMatch(workspace, /event\.currentTarget\.reset\(\)/)
  assert.doesNotMatch(components, /event\.currentTarget\.reset\(\)/)
})

test('Payment Notes presentation avoids financial approval and reconciliation labels', () => {
  const directory = new URL('../src/features/payment-notes/', import.meta.url)
  const combined = readdirSync(directory)
    .filter((name) => name.endsWith('.ts') || name.endsWith('.tsx'))
    .map((name) => readFileSync(new URL(name, directory), 'utf8'))
    .join('\n')

  assert.match(combined, /LOCAL_REVIEW_ACCEPTED_MATCH/)
  assert.match(combined, /ARITHMETICALLY_BALANCED/)
  assert.match(combined, /LOCAL_REVIEW_COMPLETE/)
  assert.doesNotMatch(combined, /CONFIRMED_MANUAL_MATCH/)
  assert.doesNotMatch(combined, /['"]RECONCILED['"]/)
  assert.match(combined, /recommendation_only/)
  assert.match(combined, /erp_write_performed/)
})
