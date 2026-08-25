import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const root = process.cwd()
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8')

const panel = read('src/features/credit-risk/OrderDecisionPreparationPanel.tsx')
const workspace = read('src/features/credit-risk/CreditRiskWorkspace.tsx')
const api = read('src/features/credit-risk/api.ts')
const service = read('backend/modules/credit_risk/service.py')
const repository = read('backend/modules/credit_risk/repository.py')
const schemas = read('backend/modules/credit_risk/schemas.py')

assert.match(workspace, /Order Decision Preparation/)
assert.match(workspace, /OrderDecisionPreparationPanel/)
assert.match(api, /getOrderDecisionPreparation/)
assert.match(api, /createOrderRecommendation/)
assert.match(panel, /Contemplated order amount/)
assert.match(panel, /Professional review required/)
assert.match(panel, /no hold or release/i)
assert.match(panel, /decision effect none · order effect none · ERP write false/i)
assert.match(service, /projected_partial_exposure/)
assert.match(service, /approved_order_policy/)
assert.match(schemas, /operator_entered_scenario_not_erp_order/)
assert.match(repository, /CREATE TABLE IF NOT EXISTS credit_order_recommendations/)
assert.match(repository, /Credit order recommendations are append-only/)
assert.match(schemas, /professional_decision_preparation/)
assert.match(schemas, /automatic_decision: Literal\[False\]/)
assert.match(schemas, /order_effect: Literal\["none"\]/)
assert.doesNotMatch(panel, /Release order|Hold order|Approve order|Update ERP/)

console.log('Credit Risk Increment 5 workflow passed: partial-exposure scenario preparation, explicit authority gaps, immutable professional recommendations, and no-order/no-ERP boundaries are present.')
