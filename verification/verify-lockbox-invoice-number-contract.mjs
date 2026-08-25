import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import ts from 'typescript'

const sourcePath = path.resolve(
  process.cwd(),
  'src/modules/document-intelligence/components/erpInvoiceNumber.ts',
)
const source = fs.readFileSync(sourcePath, 'utf8')
const transpiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText

const module = { exports: {} }
const execute = new Function('module', 'exports', transpiled)
execute(module, module.exports)

const {
  ERP_INVOICE_RULE_VERSION,
  NO_REMITTANCE_INVOICE,
  isValidErpInvoiceNumber,
  normalizeErpInvoiceNumber,
} = module.exports

assert.equal(
  ERP_INVOICE_RULE_VERSION,
  'erp-invoice-number-admission@1.2.0',
)
assert.equal(normalizeErpInvoiceNumber('43-051-670'), '43051670')
assert.equal(normalizeErpInvoiceNumber('431-051-670'), '431051670')
assert.equal(normalizeErpInvoiceNumber('9-999-000-001'), '')
assert.equal(normalizeErpInvoiceNumber('1234567'), '')
assert.equal(normalizeErpInvoiceNumber(NO_REMITTANCE_INVOICE), '')
assert.equal(isValidErpInvoiceNumber('43051670'), true)
assert.equal(isValidErpInvoiceNumber('431051670'), true)
assert.equal(isValidErpInvoiceNumber('9999000001'), false)
assert.equal(isValidErpInvoiceNumber(NO_REMITTANCE_INVOICE), false)

console.log(
  'Lockbox invoice-number regression passed: 8/9 digits accepted; 7/10 digits and the placeholder rejected.',
)
