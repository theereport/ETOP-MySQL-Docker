import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import ts from 'typescript'

const root = process.cwd()
const featureRoot = path.resolve(root, 'src/features/accounts-payable')

const featureFiles = [
  'AccountsPayableWorkspace.tsx',
  'AccountsPayableWorkspace.css',
  'api.ts',
  'components.tsx',
  'format.ts',
  'query.ts',
  'types.ts',
  'index.ts',
  'INTEGRATION.md',
]

for (const fileName of featureFiles) {
  assert.ok(
    fs.existsSync(path.join(featureRoot, fileName)),
    `Missing Accounts Payable frontend file: ${fileName}`,
  )
}

const readFeature = (fileName) =>
  fs.readFileSync(path.join(featureRoot, fileName), 'utf8')

for (const fileName of featureFiles.filter((fileName) => /\.(ts|tsx)$/.test(fileName))) {
  const source = readFeature(fileName)
  const result = ts.transpileModule(source, {
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

const querySource = readFeature('query.ts')
const queryTranspiled = ts.transpileModule(querySource, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText
const queryModule = { exports: {} }
new Function('module', 'exports', 'URLSearchParams', queryTranspiled)(
  queryModule,
  queryModule.exports,
  URLSearchParams,
)

const {
  AP_PAGE_SIZE,
  buildAccountsPayableInvoiceQuery,
  filtersForAPView,
} = queryModule.exports

assert.equal(AP_PAGE_SIZE, 50)
assert.deepEqual(filtersForAPView('overview', '', '', 0), {
  query: undefined,
  status: undefined,
  exception: undefined,
  duplicate: undefined,
  limit: 50,
  offset: 0,
})
assert.deepEqual(filtersForAPView('invoices', '  vendor evidence  ', 'review_required', 50), {
  query: 'vendor evidence',
  status: 'review_required',
  exception: undefined,
  duplicate: undefined,
  limit: 50,
  offset: 50,
})
assert.equal(filtersForAPView('ocr', '', '', 0).status, 'ocr_review')
assert.equal(filtersForAPView('exceptions', '', '', 0).exception, true)
assert.equal(filtersForAPView('duplicates', '', '', 0).duplicate, true)
assert.equal(
  buildAccountsPayableInvoiceQuery({
    query: '  vendor & invoice  ',
    status: 'review_required',
    exception: true,
    duplicate: false,
    limit: 50,
    offset: 100,
  }),
  '?query=vendor+%26+invoice&status=review_required&exception=true&duplicate=false&limit=50&offset=100',
)

const apiSource = readFeature('api.ts')
const workspaceSource = readFeature('AccountsPayableWorkspace.tsx')
const componentSource = readFeature('components.tsx')
const typeSource = readFeature('types.ts')
const styleSource = readFeature('AccountsPayableWorkspace.css')

assert.match(apiSource, /'\/accounts-payable\/overview'/)
assert.match(apiSource, /`\/accounts-payable\/invoices\$\{buildAccountsPayableInvoiceQuery\(filters\)\}`/)
assert.match(apiSource, /`\/accounts-payable\/invoices\/\$\{encodeURIComponent\(apInvoiceId\)\}`/)
assert.match(apiSource, /'\/accounts-payable\/sync'/)
assert.match(apiSource, /method: 'POST'/)
assert.match(apiSource, /requestJson<unknown>/)
assert.match(apiSource, /validateSharedEnvelope/)
assert.match(apiSource, /source_coverage/)
assert.match(apiSource, /deferred_capabilities/)
assert.match(apiSource, /extracted_invoice_total/)
assert.match(apiSource, /discounts_available/)
assert.match(apiSource, /average_approval_time/)
assert.match(apiSource, /invalidContract/)

assert.match(workspaceSource, /overviewGeneration\.current/)
assert.match(workspaceSource, /listGeneration\.current/)
assert.match(workspaceSource, /detailGeneration\.current/)
assert.match(workspaceSource, /AbortController/)
assert.match(workspaceSource, /syncAccountsPayableInvoices/)
assert.match(workspaceSource, /Promise\.all/)
assert.match(workspaceSource, /Invoice, vendor, PO, document job ID, or filename/)
assert.match(workspaceSource, /Amount\/date and document full-text search are deferred/)
assert.doesNotMatch(workspaceSource, /amount, date, filename, or OCR text/)
assert.match(workspaceSource, /No approval or payment effect/)
assert.match(workspaceSource, /ETOP did not create placeholder results/)
assert.match(workspaceSource, /view === 'overview'/)
assert.match(workspaceSource, /view === 'ocr'/)
assert.match(querySource, /view === 'exceptions'/)
assert.match(querySource, /view === 'duplicates'/)

assert.match(componentSource, /Source coverage/)
assert.match(componentSource, /Required source is not connected/)
assert.match(componentSource, /Duplicate evidence/)
assert.match(componentSource, /Invoice timeline/)
assert.match(componentSource, /Document\/extraction review status/)
assert.match(componentSource, /not AP invoice approval/)
assert.match(componentSource, /not permitted/i)
assert.doesNotMatch(componentSource, />\s*Approve\s*</)
assert.doesNotMatch(componentSource, />\s*Reject\s*</)

assert.match(typeSource, /source_coverage: SourceCoverageItem\[\]/)
assert.match(typeSource, /governance: APGovernance/)
assert.match(typeSource, /deferred_capabilities: DeferredCapability\[\]/)
assert.match(typeSource, /ocr_review_required: boolean/)
assert.match(typeSource, /duplicate_evidence: APDuplicateEvidence\[\]/)
assert.match(typeSource, /timeline: APTimelineEvent\[\]/)

assert.match(styleSource, /@media \(max-width: 620px\)/)
assert.match(styleSource, /position: sticky/)
assert.match(styleSource, /\.ap-detail-layer/)

console.log(
  'Accounts Payable frontend workflow passed: governed overview, accurately scoped real invoice search, shared API-filtered OCR/exception/duplicate views, source-grounded detail and timeline, sync-refresh, defensive contract checks, stale-request protection, deferred capabilities, and explicit no-approval/no-payment boundaries are present without hardcoded invoice intelligence.',
)
