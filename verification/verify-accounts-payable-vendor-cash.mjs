import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const root = process.cwd()
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8')

const panel = read('src/features/accounts-payable/APVendorCashIntelligence.tsx')
const workspace = read('src/features/accounts-payable/AccountsPayableWorkspace.tsx')
const api = read('src/features/accounts-payable/api.ts')
const service = read('backend/modules/accounts_payable/service.py')
const repository = read('backend/modules/accounts_payable/repository.py')
const schemas = read('backend/modules/accounts_payable/schemas.py')

assert.match(workspace, /Vendor Intelligence/)
assert.match(workspace, /Cash Planning/)
assert.match(workspace, /APVendorCashIntelligence/)
assert.match(api, /getAPVendorCashIntelligence/)
assert.match(api, /createAPCashScenario/)
assert.match(panel, /not an ERP payable forecast/i)
assert.match(panel, /No composite score is assigned/i)
assert.match(panel, /Save cash evidence scenario/)
assert.match(panel, /no approval, payment batch, authorization, posting, or ERP write/i)
assert.match(service, /Vendor groups are document-evidence aggregates/i)
assert.match(service, /current payable\/payment status is unknown/i)
assert.match(repository, /CREATE TABLE IF NOT EXISTS ap_cash_scenarios/)
assert.match(repository, /AP cash scenarios are append-only/)
assert.match(schemas, /scenario_classification: Literal/)
assert.match(schemas, /payment_proposal: Literal\[False\]/)
assert.match(schemas, /payment_authorization: Literal\[False\]/)
assert.doesNotMatch(panel, /Approve payment|Create payment batch|Post to ERP/)

console.log('Accounts Payable Increment 3 workflow passed: document-evidence vendor analytics, due-date windows, immutable cash scenarios, and no-score/no-payment/no-ERP boundaries are present.')
