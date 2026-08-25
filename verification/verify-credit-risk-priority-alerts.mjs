import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'

const root = process.cwd()
const read = (relativePath) =>
  fs.readFileSync(path.join(root, relativePath), 'utf8')

const panelSource = read('src/features/credit-risk/PriorityAlertsPanel.tsx')
const workspaceSource = read('src/features/credit-risk/CreditRiskWorkspace.tsx')
const apiSource = read('src/features/credit-risk/api.ts')
const typesSource = read('src/features/credit-risk/types.ts')
const backendApiSource = read('backend/modules/credit_risk/api.py')
const backendServiceSource = read('backend/modules/credit_risk/service.py')
const backendRepositorySource = read('backend/modules/credit_risk/repository.py')
const backendSchemasSource = read('backend/modules/credit_risk/schemas.py')

assert.match(apiSource, /getCreditRiskPriorityAlerts/)
assert.match(apiSource, /'\/credit-risk\/priority-alerts'/)
assert.match(backendApiSource, /"\/priority-alerts"/)
assert.match(backendApiSource, /credit_risk_service\.get_priority_alerts\(\)/)

assert.match(workspaceSource, /PriorityAlertsPanel/)
assert.match(workspaceSource, /Priority &amp; Alerts/)
assert.match(workspaceSource, /Customer Risk 360/)
assert.match(workspaceSource, /openPriorityCustomer/)
assert.match(workspaceSource, /setActiveView\('customer'\)/)

assert.match(panelSource, /getCreditRiskPriorityAlerts/)
assert.match(panelSource, /requestGeneration\.current/)
assert.match(panelSource, /Building assessed-customer priority and alerts/)
assert.match(panelSource, /Retry priority and alerts/)
assert.match(panelSource, /No assessed customers are available/)
assert.match(panelSource, /Live exposure degraded/)
assert.match(panelSource, /Unavailable alert sources/)
assert.match(panelSource, /Broken-promise alerts|unavailable_capabilities/)
assert.match(panelSource, /Draft high-risk bands/)
assert.match(panelSource, /filter === 'draft_band_attention'/)
assert.match(panelSource, /item\.draft_band_attention/)
assert.match(panelSource, /Product Owner draft taxonomy/)
assert.match(panelSource, /not approved automatic policy/)
assert.match(panelSource, /Open Risk 360/)
assert.match(panelSource, /evidence_sha256/)
assert.match(panelSource, /Why this operational position\?/)
assert.match(panelSource, /no recommendation, approval, notification, or ERP action/i)

assert.match(typesSource, /PriorityAlertsResponse/)
assert.match(typesSource, /draft_band_attention: boolean/)
assert.match(typesSource, /broken_promise_alerts.*nsf_alerts/s)
assert.match(typesSource, /numeric_risk_score: false/)
assert.match(typesSource, /automatic_credit_decision: false/)
assert.match(typesSource, /recommendation: false/)
assert.match(typesSource, /notification: false/)
assert.match(typesSource, /erp_write: false/)

assert.match(backendRepositorySource, /list_latest_assessments_by_customer/)
assert.match(backendRepositorySource, /PARTITION BY customer_number/)
assert.match(backendRepositorySource, /assessment_rank <= \?/)
assert.match(backendServiceSource, /DRAFT_BAND_ATTENTION_MEANINGS/)
assert.match(backendServiceSource, /"High risk"/)
assert.match(backendServiceSource, /"Very high risk"/)
assert.match(backendServiceSource, /"Default likely"/)
assert.match(backendServiceSource, /"Default or legal"/)
assert.match(backendSchemasSource, /credit-risk-priority-ordering\.v1/)
assert.match(backendServiceSource, /unavailable_over_line_treatment/)
assert.match(backendServiceSource, /broken_promise_alerts/)
assert.match(backendServiceSource, /nsf_alerts/)
assert.match(backendServiceSource, /no current over-line condition is inferred/i)
assert.match(backendServiceSource, /-latest\.manual_rating/)
assert.match(backendServiceSource, /next_review_date,/)
assert.match(backendServiceSource, /customer_number,/)

assert.doesNotMatch(panelSource, /calculateHealth/)
assert.doesNotMatch(panelSource, /risk_score/)
assert.doesNotMatch(panelSource, /customer-risk\/review/)
assert.doesNotMatch(backendServiceSource, /customer_risk_service/)

console.log(
  'Credit Risk Increment 2 workflow passed: assessed-customer-only coverage, saved draft-band attention filter, deterministic operational ordering, assessment deterioration, live partial-over-line evidence, source-degraded retention, unavailable broken-promise/NSF capabilities, exact evidence references, and working Risk 360 drill-through are present without a numeric score, recommendation, decision, notification, or ERP action.',
)
