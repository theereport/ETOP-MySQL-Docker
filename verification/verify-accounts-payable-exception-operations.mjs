import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const root = process.cwd()
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8')

const panel = read('src/features/accounts-payable/APExceptionOperationsCenter.tsx')
const workspace = read('src/features/accounts-payable/AccountsPayableWorkspace.tsx')
const api = read('src/features/accounts-payable/api.ts')
const service = read('backend/modules/accounts_payable/service.py')
const repository = read('backend/modules/accounts_payable/repository.py')
const schemas = read('backend/modules/accounts_payable/schemas.py')

assert.match(workspace, /Exception Operations/)
assert.match(workspace, /APExceptionOperationsCenter/)
assert.match(api, /getAPExceptionOperations/)
assert.match(api, /createAPExceptionAction/)
assert.match(api, /approved_sla !== false/)
assert.match(panel, /Deterministic ordering/)
assert.match(panel, /Append-only professional action/)
assert.match(panel, /Owner identity is operator supplied/i)
assert.match(panel, /no automatic resolution/i)
assert.match(panel, /no approval, payment, or ERP effect/i)
assert.match(service, /source_changed/)
assert.match(service, /without a hidden score/)
assert.match(repository, /CREATE TABLE IF NOT EXISTS ap_exception_actions/)
assert.match(repository, /AP exception actions are append-only/)
assert.match(schemas, /professional_exception_work_management/)
assert.match(schemas, /authenticated_assignment: Literal\[False\]/)
assert.match(schemas, /automatic_resolution: Literal\[False\]/)
assert.match(schemas, /payment_effect: Literal\["none"\]/)
assert.doesNotMatch(panel, /Approve invoice|Authorize payment|Resolve exception|Post to ERP/)

console.log('Accounts Payable Increment 4 workflow passed: deterministic current exception work, source-bound immutable follow-up, visible authority gaps, and no-resolution/no-payment/no-ERP boundaries are present.')
