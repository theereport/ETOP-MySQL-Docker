import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const root = resolve(import.meta.dirname, '..')

function read(path) {
  return readFileSync(resolve(root, path), 'utf8')
}

function requireText(path, text) {
  const source = read(path)
  if (!source.includes(text)) {
    throw new Error(`${path} is missing required evidence: ${text}`)
  }
  return source
}

const repository = read('backend/modules/erp_evidence/repository.py')
const executableSql = repository.match(/(?:SELECT|WITH)[\s\S]*?(?="""|''')/gi) ?? []
for (const sql of executableSql) {
  if (/\b(?:INSERT|UPDATE|DELETE|REPLACE|ALTER|DROP|TRUNCATE|CREATE)\b/i.test(sql)) {
    throw new Error(`ERP Evidence repository contains a mutation statement: ${sql.slice(0, 120)}`)
  }
}

for (const table of ['TMCUST', 'TMAROP', 'PMVEND', 'PMHD', 'PMDT', 'PMGLDS', 'PTHD', 'PTDT', 'PTPY']) {
  requireText('backend/modules/erp_evidence/repository.py', table)
}
requireText('backend/modules/erp_evidence/repository.py', '"input_invoice_detail"')
requireText('backend/modules/erp_evidence/service.py', '"input_invoice_detail": "AP invoice input detail"')

for (const boundary of [
  'PVACCBNK (bank account number)',
  'PVROUBNK (bank routing number)',
  'PVIDFED (federal tax identifier)',
  'Vendor-name discovery returns bounded candidates for human selection',
  'accounts_payable_invoice_evidence_by_direct_erp_identity',
]) {
  requireText('backend/modules/erp_evidence/service.py', boundary)
}

requireText('backend/main.py', 'app.include_router(erp_evidence_router)')
requireText('src/features/accounts-payable/AccountsPayableWorkspace.tsx', "id: 'erp_evidence'")
requireText('src/features/credit-risk/CreditRiskWorkspace.tsx', "activeView === 'erp_evidence'")
requireText('src/features/accounts-payable/APERPEvidenceWorkspace.tsx', 'Sensitive fields deliberately excluded')
requireText('src/features/accounts-payable/APERPEvidenceWorkspace.tsx', 'does not require an imported OCR invoice')
requireText('src/features/accounts-payable/api.ts', '/erp-evidence/accounts-payable/invoice-search')
requireText('src/features/accounts-payable/api.ts', '/erp-evidence/accounts-payable/invoice-evidence')
requireText('src/features/credit-risk/CreditERPEvidencePanel.tsx', 'Current nonzero Open A/R')

console.log('ERP Evidence Gateway static verification passed.')
