import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const root = process.cwd()
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8')

const center = read('src/features/accounts-payable/APControlCenter.tsx')
const workspace = read('src/features/accounts-payable/AccountsPayableWorkspace.tsx')
const api = read('src/features/accounts-payable/api.ts')
const service = read('backend/modules/accounts_payable/service.py')
const repository = read('backend/modules/accounts_payable/repository.py')
const schemas = read('backend/modules/accounts_payable/schemas.py')

assert.match(workspace, /Approval Center/)
assert.match(workspace, /Payment Controls/)
assert.match(workspace, /APControlCenter/)
assert.match(api, /createAPControlCase/)
assert.match(api, /createAPControlReview/)
assert.match(api, /control-cases/)
assert.match(center, /Create immutable control case/)
assert.match(center, /Save append-only disposition/)
assert.match(center, /Evidence ready is not invoice approval/i)
assert.match(center, /cannot enter a governed approval tier, authorize payment, release funds, post to ERP/i)
assert.match(center, /source_evidence_sha256/)
assert.match(service, /source_evidence_current/)
assert.match(service, /requester_reviewer_distinct/)
assert.match(service, /reviewer_payment_preparer_distinct/)
assert.match(service, /approval_authority.*unavailable/s)
assert.match(service, /payment_execution.*unavailable/s)
assert.match(repository, /CREATE TABLE IF NOT EXISTS ap_control_cases/)
assert.match(repository, /CREATE TABLE IF NOT EXISTS ap_control_reviews/)
assert.match(repository, /AP control cases are append-only/)
assert.match(schemas, /can_enter_governed_approval: Literal\[False\]/)
assert.match(schemas, /can_authorize_payment: Literal\[False\]/)
assert.match(schemas, /approval_effect: Literal\["none"\]/)
assert.match(schemas, /payment_effect: Literal\["none"\]/)
assert.doesNotMatch(center, />Approve</)
assert.doesNotMatch(center, />Pay</)

console.log('Accounts Payable Increment 2 workflow passed: immutable evidence-bound control cases, readiness and segregation gates, append-only professional dispositions, source-revision invalidation, and no approval/payment execution are present.')
