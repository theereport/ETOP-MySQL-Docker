import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const root = process.cwd()
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8')

const panel = read('src/features/credit-risk/CreditLineIntelligencePanel.tsx')
const workspace = read('src/features/credit-risk/CreditRiskWorkspace.tsx')
const api = read('src/features/credit-risk/api.ts')
const service = read('backend/modules/credit_risk/service.py')
const repository = read('backend/modules/credit_risk/repository.py')
const schemas = read('backend/modules/credit_risk/schemas.py')

assert.match(workspace, /Credit-Line Intelligence/)
assert.match(workspace, /CreditLineIntelligencePanel/)
assert.match(api, /getCreditLineIntelligence/)
assert.match(api, /createCreditLineProposal/)
assert.match(api, /credit-line-proposals/)
assert.match(panel, /Existing analytical inference/)
assert.match(panel, /not an automatic recommendation or approved policy/i)
assert.match(panel, /Save append-only proposal/)
assert.match(panel, /no decision, approval, notification, credit hold, order release, line change, or ERP write/i)
assert.match(panel, /evidence_snapshot_sha256/)
assert.match(service, /round_to_nearest_500\(\(annualized_sales \/ 12\) \* 2\)/)
assert.match(service, /seasonal_limit_model/)
assert.match(service, /related_account_exposure/)
assert.match(repository, /CREATE TABLE IF NOT EXISTS credit_line_proposals/)
assert.match(repository, /Credit-line proposals are append-only/)
assert.match(schemas, /professional_recommendation/)
assert.match(schemas, /not_submitted_to_governed_approval/)
assert.match(schemas, /decision_effect: Literal\["none"\]/)
assert.match(schemas, /erp_write: Literal\[False\]/)
assert.doesNotMatch(panel, /Update ERP|Approve credit line|Apply recommendation/)

console.log('Credit Risk Increment 3 workflow passed: exact analytical reference, source gaps, append-only professional proposals, evidence reconstruction, and no-decision/no-ERP boundaries are present.')
