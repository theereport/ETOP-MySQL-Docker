import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'


const root = process.cwd()
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8')

const repository = read('backend/modules/erp_evidence/repository.py')
const database = read('backend/core/database.py')
const parser = read('backend/modules/erp_evidence/ap_spend_parser.py')
const schemas = read('backend/modules/erp_evidence/ap_spend_schemas.py')
const service = read('backend/modules/erp_evidence/ap_spend_service.py')
const api = read('backend/modules/erp_evidence/api.py')
const workspace = read('src/features/accounts-payable/AccountsPayableWorkspace.tsx')
const panel = read('src/features/accounts-payable/APVendorSpendIntelligence.tsx')
const frontendApi = read('src/features/accounts-payable/api.ts')
const capability = read('ETOP-Blueprint/04_Capabilities/CAP-AP-001_Accounts_Payable_Invoice_Intelligence.md')
const source = read('ETOP-Blueprint/12_Governance/Source_Records/SRC-010_AP_Vendor_Spend_Intelligence_Source.md')
const decision = read('ETOP-Blueprint/10_Architecture_Decision_Records/ADR-017_Governed_AP_Vendor_Spend_Questions.md')

for (const field of [
  'PMGNBVND',
  'PMGNBINV',
  'PMGAMTINV',
  'PMGDTEINV',
  'PMGNBGLDV',
  'PMGNBGL',
  'PMGPR',
  'PMGYR',
]) {
  assert.match(repository, new RegExp(`\\b${field}\\b`), `${field} mapping is missing`)
}

assert.match(repository, /SUM\(CASE WHEN G\.PMGAMTINV > 0/)
assert.match(repository, /SUM\(CASE WHEN G\.PMGAMTINV < 0/)
assert.match(repository, /SUM\(G\.PMGAMTINV\)/)
assert.match(repository, /G\.PMGNBGLDV = %s/)
assert.match(repository, /G\.PMGNBGL = %s/)
assert.match(repository, /date_expression = "G\.PMGDTEINV"/)
assert.match(repository, /STR_TO_DATE\(LPAD/)
assert.match(repository, /calendar_date_encoding/)
assert.match(repository, /LIMIT \{bounded_limit \+ 1\}/)
assert.match(repository, /HAVING COUNT\(G\.PMGAMTINV\) > 0/)
assert.match(repository, /COUNT\(DISTINCT G\.PMGNBINV\)/)
assert.doesNotMatch(repository, /CAST\(G\.PMGNBINV/i)
assert.match(repository, /read_consistent_snapshot/)
assert.match(repository, /AP_SPEND_MONTHLY_PERIOD_LIMIT = 12/)
assert.match(repository, /AP_SPEND_MONTHLY_LEADER_LIMIT = 10/)
assert.match(repository, /for month in range\(1, self\.AP_SPEND_MONTHLY_PERIOD_LIMIT \+ 1\)/)
assert.match(database, /start_transaction\(/)
assert.match(database, /consistent_snapshot=True/)
assert.match(database, /readonly=True/)

const executableSql = repository.match(/(?:SELECT|WITH)[\s\S]*?(?="""|''')/gi) ?? []
for (const sql of executableSql) {
  assert.doesNotMatch(sql, /\b(?:INSERT|UPDATE|DELETE|REPLACE|ALTER|DROP|TRUNCATE|CREATE)\b/i)
}
assert.doesNotMatch(repository, /question/)

assert.match(parser, /Interpreted account \{combined_account\}-\{combined_division\}/)
assert.match(parser, /calendar_invoice_date/)
assert.match(parser, /erp_accounting_period/)
assert.match(parser, /fiscal_calendar/)
assert.match(parser, /arbitrary_sql/)
assert.match(parser, /unsupported_question_modifier/)
assert.match(parser, /time_basis/)
assert.match(parser, /top_vendor_by_month/)

assert.match(schemas, /signed_posted_ap_gl_distribution_amount/)
assert.match(service, /positive_distribution_amount/)
assert.match(service, /negative_distribution_amount/)
assert.match(service, /net_signed_amount/)
assert.match(service, /never generates or executes model-authored SQL/)
assert.match(service, /current open Accounts Payable/)
assert.match(service, /canonical_hash/)
assert.match(service, /leader_set_complete/)
assert.match(service, /does not assert an exact tie count/)
assert.match(service, /zero-valued SQL aggregate is an empty-sum placeholder/)
assert.match(schemas, /leader_set_complete/)
assert.match(service, /ETOP_AP_PMGDTEINV_NUMERIC_ENCODING/)
assert.match(service, /_numeric_date_type_gap/)
assert.match(service, /CHARACTER_INVOICE_IDENTITY_TYPES = \{"char", "varchar"\}/)
assert.match(service, /_invoice_identity_type_gap/)
assert.match(service, /if field == "PMGNBINV"/)
assert.match(
  service,
  /PMGLDS_EXACT_NUMERIC_FIELDS = \([\s\S]*"PMGNBVND"[\s\S]*"PMGAMTINV"[\s\S]*"PMGNBGLDV"[\s\S]*"PMGNBGL"[\s\S]*\)/,
)
assert.match(service, /single_read_only_consistent_snapshot/)
assert.match(service, /monthly_periods/)

assert.match(api, /vendor-spend-readiness/)
assert.match(api, /vendor-spend-question/)
assert.doesNotMatch(api, /@router\.(?:post|put|patch|delete)\([^)]*vendor-spend/i)
assert.match(frontendApi, /askAPVendorSpendQuestion/)
assert.match(frontendApi, /getAPVendorSpendReadiness/)

assert.match(workspace, /id: 'spend_intelligence'/)
assert.match(workspace, /APVendorSpendIntelligence/)
assert.match(panel, /Ask about vendor spend/)
assert.match(panel, /PMGLDS\.PMGAMTINV signed as stored/)
assert.match(panel, /What ETOP understood/)
assert.match(panel, /Date basis/)
assert.match(panel, /Positive distributions/)
assert.match(panel, /Negative distributions/)
assert.match(panel, /Net signed amount/)
assert.match(panel, /Source, coverage, and limits/)
assert.match(panel, /Highest vendor by calendar month/)
assert.match(panel, /monthly_periods\.map/)
assert.match(panel, /never turns it into arbitrary SQL/)
assert.doesNotMatch(panel, />\s*(?:Approve|Pay|Post|Export)\s*</i)

assert.match(source, /SRC-010/)
assert.match(decision, /ADR-017/)
assert.match(capability, /Bounded ERP Vendor Spend Intelligence/)
assert.match(decision, /no export, recommendation, Decision, approval, payment, posting/i)

console.log('AP Vendor Spend Intelligence verification passed: deterministic questions, bound read-only aggregates, exact date basis, signed disclosure, provenance, and no financial action are present.')
