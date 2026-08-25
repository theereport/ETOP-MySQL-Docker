import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const root = process.cwd()
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8')

const panel = read('src/features/credit-risk/PortfolioMonitoringPanel.tsx')
const workspace = read('src/features/credit-risk/CreditRiskWorkspace.tsx')
const api = read('src/features/credit-risk/api.ts')
const service = read('backend/modules/credit_risk/service.py')
const repository = read('backend/modules/credit_risk/repository.py')
const schemas = read('backend/modules/credit_risk/schemas.py')

assert.match(workspace, /Portfolio Monitoring/)
assert.match(workspace, /PortfolioMonitoringPanel/)
assert.match(api, /getCreditPortfolioMonitoring/)
assert.match(api, /createCreditPortfolioReview/)
assert.match(panel, /Draft watchlist/)
assert.match(panel, /available partial exposure/i)
assert.match(panel, /Record portfolio review/)
assert.match(panel, /no decision, notification, or ERP write/i)
assert.match(service, /assessed customers only/i)
assert.match(service, /partial exposure only where that evidence is available/i)
assert.match(repository, /CREATE TABLE IF NOT EXISTS credit_portfolio_reviews/)
assert.match(repository, /Credit portfolio reviews are append-only/)
assert.match(schemas, /professional_workflow_metadata/)
assert.match(schemas, /approved_portfolio_policy: Literal\[False\]/)
assert.match(schemas, /automatic_decision: Literal\[False\]/)
assert.doesNotMatch(panel, /Approve credit|Update ERP|Send notification/)

console.log('Credit Risk Increment 4 workflow passed: assessed-customer monitoring, partial-evidence concentration, append-only professional review metadata, and no-decision/no-ERP boundaries are present.')
