import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import ts from 'typescript'

const root = process.cwd()
const featureRoot = path.join(root, 'src/features/financial-close')
const backendRoot = path.join(root, 'backend/modules/financial_close')
const featureFiles = [
  'index.ts',
  'types.ts',
  'api.ts',
  'FinancialCloseWorkspace.tsx',
  'FinancialCloseWorkspace.css',
  'ClosePlanningTemplates.tsx',
  'ClosePlanningTemplates.css',
]

for (const fileName of featureFiles) {
  assert.ok(
    fs.existsSync(path.join(featureRoot, fileName)),
    `Missing Financial Close frontend file: ${fileName}`,
  )
}

const readFeature = (fileName) =>
  fs.readFileSync(path.join(featureRoot, fileName), 'utf8')
const readBackend = (fileName) =>
  fs.readFileSync(path.join(backendRoot, fileName), 'utf8')

for (const fileName of featureFiles.filter((name) => /\.(ts|tsx)$/.test(name))) {
  const result = ts.transpileModule(readFeature(fileName), {
    compilerOptions: {
      jsx: ts.JsxEmit.ReactJSX,
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
    reportDiagnostics: true,
    fileName,
  })
  assert.equal(
    result.diagnostics?.length ?? 0,
    0,
    `${fileName} has TypeScript syntax diagnostics`,
  )
}

const api = readFeature('api.ts')
const types = readFeature('types.ts')
const workspace = readFeature('FinancialCloseWorkspace.tsx')
const planning = readFeature('ClosePlanningTemplates.tsx')
const styles = readFeature('FinancialCloseWorkspace.css')
const planningStyles = readFeature('ClosePlanningTemplates.css')
const allRuntimeSource = `${api}\n${types}\n${workspace}\n${planning}`
const backendSchemas = readBackend('schemas.py')
const backendRepository = readBackend('repository.py')
const backendService = readBackend('service.py')
const backendApi = readBackend('api.py')
const backendTests = fs.readFileSync(
  path.join(root, 'backend/test_financial_close_readiness.py'),
  'utf8',
)
const sourceRecord = fs.readFileSync(
  path.join(root, 'ETOP-Blueprint/12_Governance/Source_Records/SRC-008_Financial_Close_Planning_Templates_Source.md'),
  'utf8',
)
const architectureDecision = fs.readFileSync(
  path.join(root, 'ETOP-Blueprint/10_Architecture_Decision_Records/ADR-015_Local_Close_Planning_Template_Version_and_Cycle_Snapshot.md'),
  'utf8',
)
const capability = fs.readFileSync(
  path.join(root, 'ETOP-Blueprint/04_Capabilities/CAP-FC-001_Financial_Close_and_Controller_Intelligence.md'),
  'utf8',
)
const decision = fs.readFileSync(
  path.join(root, 'ETOP-Blueprint/09_Decision_Models/DEC-FC-001_Close_Control_Evidence_Readiness.md'),
  'utf8',
)
const traceability = fs.readFileSync(
  path.join(root, 'ETOP-Blueprint/12_Governance/BLUEPRINT_TRACEABILITY_MATRIX.csv'),
  'utf8',
)

assert.match(api, /getWorkflowToken/)
assert.match(api, /Authorization/)
assert.match(api, /Bearer \$\{token\}/)
assert.match(api, /clearWorkflowToken/)
assert.match(api, /'\/governance'/)
assert.match(api, /'\/cycles'/)
assert.match(api, /'\/templates'/)
assert.match(api, /\/versions/)
assert.match(api, /\/instantiate/)
assert.match(api, /\/cycles\/\$\{encodeURIComponent\(cycleId\)\}/)
assert.match(api, /\/controls/)
assert.match(api, /\/preparations/)
assert.match(api, /\/reviews/)
assert.match(api, /\/events/)

assert.match(types, /financial-close-readiness\.v1/)
assert.match(types, /financial-close-planning\.v1/)
assert.match(types, /local_user_authored_planning_draft/)
assert.match(types, /calendar_anchor_plus_offset_days/)
assert.match(types, /template_version_sha256/)
assert.match(types, /snapshot_sha256/)
assert.match(types, /entity_label: string/)
assert.match(types, /'not_recorded'/)
assert.match(types, /'reference_recorded'/)
assert.match(types, /'missing'/)
assert.match(types, /'unavailable'/)
assert.match(types, /'not_reviewed'/)
assert.match(types, /'current'/)
assert.match(types, /'stale'/)
assert.match(types, /'evidence_sufficient'/)
assert.match(types, /'needs_information'/)
assert.match(types, /'not_ready'/)
assert.match(types, /'deferred'/)
assert.match(types, /authority_effect: 'none'/)
assert.match(types, /close_effect: 'none'/)
assert.match(types, /approval_effect: 'none'/)
assert.match(types, /posting_effect: 'none'/)
assert.match(types, /erp_write: false/)

assert.match(workspace, /getWorkflowSession/)
assert.match(workspace, /getWorkflowUsers/)
assert.match(workspace, /WORKFLOW_SESSION_EVENT/)
assert.match(workspace, /role\.role_id === 'workflow_coordinator'/)
assert.match(workspace, /Preparer and reviewer must be different verified local accounts/)
assert.match(workspace, /selectedControl\?\.preparer\.user_id === signedInUserId/)
assert.match(workspace, /selectedControl\?\.reviewer\.user_id === signedInUserId/)
assert.match(workspace, /selectedControl\.review_currency !== 'current'/)
assert.match(workspace, /selectedControl\.evidence_status !== 'reference_recorded'/)
assert.match(workspace, /expected_control_version: selectedControl\.version/)
assert.match(workspace, /workflowIdempotencyKey\('financial-close-preparation'\)/)
assert.match(workspace, /workflowIdempotencyKey\('financial-close-review'\)/)
assert.match(workspace, /Append-only preparation evidence recorded/)
assert.match(workspace, /Append-only evidence-readiness review recorded/)
assert.match(workspace, /operator supplied \/ unverified/i)
assert.match(workspace, /ERP period state: Unavailable/)
assert.match(workspace, /Close \/ approval \/ posting effect: None/)
assert.match(workspace, /ETOP does not create a placeholder calendar/)
assert.match(workspace, /Loading local Financial Close evidence/)
assert.match(workspace, /No close work cycles exist/)
assert.match(workspace, /Unable to complete the request/)
assert.match(workspace, /Reload current evidence/)
assert.match(workspace, /Integrity verified/)
assert.match(workspace, /FINANCIAL CLOSE · INCREMENT 2/)
assert.match(workspace, /Planning templates/)
assert.match(workspace, /Snapshot offset/)

assert.match(planning, /createCloseTemplate/)
assert.match(planning, /createCloseTemplateVersion/)
assert.match(planning, /instantiateCloseTemplate/)
assert.match(planning, /getCloseTemplates/)
assert.match(planning, /getCloseTemplate/)
assert.match(planning, /Local user-authored planning drafts/i)
assert.match(planning, /Each saved version is immutable/)
assert.match(planning, /Planning anchor date/)
assert.match(planning, /calendar_anchor_date/)
assert.match(planning, /planned_offset_days/)
assert.match(planning, /expected_latest_version: template\.latest_version/)
assert.match(planning, /Every control requires different preparer and reviewer accounts/)
assert.match(planning, /Instantiate exact version into local cycle/)
assert.match(planning, /No recurrence, task, message, or ERP action/)
assert.match(planning, /Policy effect: None/)
assert.match(planning, /Automation \/ notification effect: None/)
assert.match(planning, /Loading immutable local close-planning templates/)
assert.match(planning, /No planning templates exist/)
assert.match(planning, /Planning templates are unavailable/)
assert.match(planning, /Integrity verified/)
assert.match(planning, /createIdempotencyKeyRef = useRef<string \| null>\(null\)/)
assert.match(planning, /instantiateIdempotencyKeyRef = useRef<string \| null>\(null\)/)
assert.match(planning, /idempotency_key: createIdempotencyKeyRef\.current \?\?=/)
assert.match(planning, /idempotency_key: instantiateIdempotencyKeyRef\.current \?\?=/)
assert.match(planning, /onChange=\{resetCreateSubmission\}/)
assert.match(planning, /onChange=\{resetInstantiationSubmission\}/)
assert.match(planning, /revisionTemplateId !== template\.template_id/)
assert.match(planning, /onClick=\{\(\) => selectTemplate\(item\.template_id\)\}/)

assert.doesNotMatch(allRuntimeSource, /getWorkflowTasks|createWorkflowTask|transitionWorkflowTask|assignWorkflowTask/)
assert.doesNotMatch(allRuntimeSource, /localStorage|sessionStorage/)
assert.doesNotMatch(allRuntimeSource, /madden|TMGL|GMAD|INSERT INTO|UPDATE\s+\w+|DELETE FROM/i)
assert.doesNotMatch(allRuntimeSource, /setInterval|Notification\(|createAutomation|createWorkflowTask/)
assert.doesNotMatch(workspace, />\s*(Approve|Post|Certify|Reopen|Close books|Close period|Create journal)\s*</i)
assert.doesNotMatch(planning, />\s*(Approve|Post|Certify|Reopen|Close books|Close period|Create journal)\s*</i)
assert.doesNotMatch(workspace, /const\s+(mock|default)(Cycles|Controls|Evidence)/i)

assert.match(styles, /\.fc-workspace/)
assert.match(styles, /\.fc-state-pill\.attention_required/)
assert.match(styles, /\.fc-state-pill\.evidence_sufficient/)
assert.match(styles, /@media \(max-width: 760px\)/)
assert.match(planningStyles, /\.fc-template-workspace/)
assert.match(planningStyles, /\.fc-template-layout/)
assert.match(planningStyles, /@media \(max-width: 760px\)/)

assert.match(backendSchemas, /PLANNING_CONTRACT_VERSION = "financial-close-planning\.v1"/)
assert.match(backendSchemas, /local_user_authored_planning_draft/)
assert.match(backendSchemas, /calendar_effect: Literal\["planning_dates_only"\]/)
assert.match(backendRepository, /CREATE TABLE IF NOT EXISTS fc_control_templates/)
assert.match(backendRepository, /CREATE TABLE IF NOT EXISTS fc_template_versions/)
assert.match(backendRepository, /CREATE TABLE IF NOT EXISTS fc_template_items/)
assert.match(backendRepository, /CREATE TABLE IF NOT EXISTS fc_template_events/)
assert.match(backendRepository, /CREATE TABLE IF NOT EXISTS fc_cycle_template_snapshots/)
assert.match(backendRepository, /fc_cycle_template_snapshots_no_update/)
assert.match(backendRepository, /fc_template_events_no_delete/)
assert.match(backendRepository, /instantiate_template_cycle/)
assert.match(backendRepository, /_revalidate_instantiation_identities/)
assert.match(backendRepository, /_verify_template_record_bindings/)
assert.match(backendService, /calendar_anchor_plus_offset_days/)
assert.match(backendService, /timedelta\(\s*days=int\(source_item\["planned_offset_days"\]\)\s*\)/)
assert.match(backendService, /_require_coordinator\(session\)/)
assert.match(backendService, /_validate_cycle_snapshot_binding/)
assert.match(backendApi, /"\/templates\/\{template_id\}\/versions\/\{template_version\}\/instantiate"/)
assert.match(backendTests, /test_templates_are_local_immutable_versioned_drafts_and_do_not_auto_create_cycles/)
assert.match(backendTests, /test_manual_template_instantiation_snapshots_exact_version_and_dates/)
assert.match(backendTests, /test_template_and_snapshot_history_is_append_only_and_tamper_evident/)
assert.match(backendTests, /test_instantiation_revalidates_active_identities_inside_atomic_write/)
assert.match(backendTests, /test_snapshot_read_rejects_rehashed_item_binding_forgery/)
assert.match(backendTests, /test_template_integrity_rejects_deleted_valid_chain_tail/)
assert.match(backendTests, /test_router_exposes_only_bounded_readiness_and_manual_planning_operations/)

assert.match(sourceRecord, /local_user_authored_planning_draft/)
assert.match(sourceRecord, /No recurrence engine is introduced/)
assert.match(architectureDecision, /Later template\s+versions cannot change an existing cycle/)
assert.match(architectureDecision, /planning effect\s+only/i)
assert.match(capability, /\*\*Version:\*\* 0\.2\.0/)
assert.match(capability, /SRC-007\/SRC-008/)
assert.match(decision, /\*\*Version:\*\* 0\.2\.0/)
assert.match(decision, /provenance rules, not accounting-policy rules/)
assert.match(traceability, /"SRC-008","2026-08-08","originates","ADR-015"/)
assert.match(traceability, /"backend\/test_financial_close_readiness\.py","0\.7\.0 Step 6 Increment 2"/)

const planningBackend = `${backendSchemas}\n${backendRepository}\n${backendService}\n${backendApi}`
assert.doesNotMatch(planningBackend, /modules\.erp_evidence|pyodbc|pymssql|sqlalchemy|TMGL|GMAD/i)
assert.doesNotMatch(planningBackend, /create_workflow_task|create_notification|send_notification|set_interval|scheduler|cron/i)
assert.doesNotMatch(backendApi, /@router\.(put|patch|delete)/)
assert.doesNotMatch(backendApi, /@router\.(get|post)\([^)]*\/(approve|certify|close|reopen|post|notify|automate|erp|ledger)/i)

console.log(
  'Financial Close Increment 2 verification passed: governed immutable local planning-template versions, manual anchor-date cycle snapshots, distinct verified preparer/reviewer defaults, persistent loading/empty/error flows, retained Increment 1 evidence review, and no ERP, close, approval, posting, automation, notification, or shared-task effect are present.',
)
