import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import ts from 'typescript'

const root = process.cwd()
const workflowPath = path.resolve(
  root,
  'src/services/reportWorkflow.ts',
)
const workflowSource = fs.readFileSync(workflowPath, 'utf8')
const workflowTranspiled = ts.transpileModule(workflowSource, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText
const workflowModule = { exports: {} }

new Function('module', 'exports', workflowTranspiled)(
  workflowModule,
  workflowModule.exports,
)

const {
  createRequestLineage,
  getSqlParameterNames,
  reportCanBeScheduled,
  resolveReportSql,
  validateReportDefinition,
} = workflowModule.exports

const previewLineage = createRequestLineage()
const firstPreview = previewLineage.begin()
const secondPreview = previewLineage.begin()

assert.equal(previewLineage.isCurrent(firstPreview), false)
assert.equal(previewLineage.isCurrent(secondPreview), true)
previewLineage.invalidate()
assert.equal(previewLineage.isCurrent(secondPreview), false)

const baseReport = {
  id: 'report-test',
  name: 'Customer Review',
  description: '',
  category: 'Credit',
  sql: `SELECT *
FROM DTA273.TMCUST
WHERE CUNAME = :customer_name
  AND CUNUMBER >= :minimum_customer
  AND CUSTATE = :state
  AND :include_inactive = TRUE
  AND CUDATE >= :as_of_date
  AND :optional_filter IS NULL`,
  parameters: [
    {
      id: 'p1',
      name: 'customer_name',
      label: 'Customer name',
      type: 'text',
      required: true,
    },
    {
      id: 'p2',
      name: 'minimum_customer',
      label: 'Minimum customer',
      type: 'number',
      required: true,
    },
    {
      id: 'p3',
      name: 'state',
      label: 'State',
      type: 'select',
      required: true,
      options: [
        { label: 'Ohio', value: 'OH' },
        { label: 'Texas', value: 'TX' },
      ],
    },
    {
      id: 'p4',
      name: 'include_inactive',
      label: 'Include inactive',
      type: 'boolean',
      required: true,
    },
    {
      id: 'p5',
      name: 'as_of_date',
      label: 'As of date',
      type: 'date',
      required: true,
    },
    {
      id: 'p6',
      name: 'optional_filter',
      label: 'Optional filter',
      type: 'text',
      required: false,
    },
  ],
  database: 'ERP',
  outputFormat: 'xlsx',
  createdAt: '2026-08-05T00:00:00.000Z',
  updatedAt: '2026-08-05T00:00:00.000Z',
}

assert.deepEqual(
  getSqlParameterNames(
    `SELECT :one, :one, value::text, ':ignored', :two
     FROM source -- :commented
     /* :also_commented */`,
  ),
  ['one', 'two'],
)

assert.deepEqual(validateReportDefinition(baseReport).errors, [])
assert.equal(reportCanBeScheduled(baseReport), false)

const resolved = resolveReportSql(baseReport, {
  customer_name: "O'Reilly OR 1=1 --",
  minimum_customer: '150000',
  state: 'OH',
  include_inactive: 'false',
  as_of_date: '2026-08-05',
  optional_filter: '',
})

assert.match(
  resolved.sql,
  /CUNAME = CONVERT\(0x4f275265696c6c79204f5220313d31202d2d USING utf8mb4\)/,
)
assert.match(resolved.sql, /CUNUMBER >= 150000/)
assert.match(
  resolved.sql,
  /CUSTATE = CONVERT\(0x4f48 USING utf8mb4\)/,
)
assert.match(resolved.sql, /AND FALSE = TRUE/)
assert.match(
  resolved.sql,
  /CUDATE >= CONVERT\(0x323032362d30382d3035 USING utf8mb4\)/,
)
assert.match(resolved.sql, /AND NULL IS NULL/)
assert.doesNotMatch(resolved.sql, /:customer_name/)
assert.doesNotMatch(resolved.sql, /O'Reilly OR 1=1/)

assert.throws(
  () =>
    resolveReportSql(baseReport, {
      customer_name: 'Test',
      minimum_customer: '1 OR 1=1',
      state: 'OH',
      include_inactive: 'true',
      as_of_date: '2026-08-05',
    }),
  /must be a valid number/,
)

assert.throws(
  () =>
    resolveReportSql(baseReport, {
      customer_name: 'Test',
      minimum_customer: '100',
      state: 'CA',
      include_inactive: 'true',
      as_of_date: '2026-08-05',
    }),
  /configured options/,
)

assert.throws(
  () =>
    resolveReportSql(baseReport, {
      minimum_customer: '100',
      state: 'OH',
      include_inactive: 'true',
      as_of_date: '2026-08-05',
    }),
  /Customer name is required/,
)

assert.throws(
  () =>
    resolveReportSql(baseReport, {
      customer_name: 'Test',
      minimum_customer: '100',
      state: 'OH',
      include_inactive: 'true',
      as_of_date: '2026-02-30',
    }),
  /must be a valid date/,
)

const invalidReport = {
  ...baseReport,
  sql: 'SELECT * FROM source WHERE value = :missing',
  parameters: [
    baseReport.parameters[0],
    { ...baseReport.parameters[0], id: 'duplicate' },
  ],
}
const invalidResult = validateReportDefinition(invalidReport)

assert.ok(
  invalidResult.errors.some((error) =>
    error.includes('used more than once'),
  ),
)
assert.ok(
  invalidResult.errors.some((error) =>
    error.includes(':missing'),
  ),
)

const nonParameterizedReport = {
  ...baseReport,
  sql: 'SELECT CUNUMBER FROM DTA273.TMCUST',
  parameters: [],
}
assert.equal(reportCanBeScheduled(nonParameterizedReport), true)

const apiSource = fs.readFileSync(
  path.resolve(root, 'src/services/reportApi.ts'),
  'utf8',
)
const builderSource = fs.readFileSync(
  path.resolve(
    root,
    'src/components/ReportBuilder/ReportBuilder.tsx',
  ),
  'utf8',
)
const exportSource = fs.readFileSync(
  path.resolve(
    root,
    'src/components/ReportBuilder/ExportPanel.tsx',
  ),
  'utf8',
)
const scheduleSource = fs.readFileSync(
  path.resolve(
    root,
    'src/components/ReportBuilder/ReportSchedulePanel.tsx',
  ),
  'utf8',
)

assert.match(apiSource, /SQL_API_BASE}\/execute/)
assert.match(apiSource, /SQL_API_BASE}\/export/)
assert.match(apiSource, /AUTOMATION_API_BASE/)
assert.doesNotMatch(apiSource, /reports\/execute/)
assert.doesNotMatch(apiSource, /reports\/export/)
assert.match(builderSource, /getSqlRuntimeCapabilities/)
assert.match(builderSource, /catalogErrorMessage/)
assert.match(builderSource, /ReportSchedulePanel/)
assert.match(builderSource, /previewAbortControllerRef/)
assert.match(builderSource, /previewLineage\.isCurrent/)
assert.ok(
  (builderSource.match(/previewLineage\.invalidate\(\)/g) ?? [])
    .length >= 3,
)
assert.match(apiSource, /signal\?: AbortSignal/)
assert.match(exportSource, /Direct Excel unavailable/)
assert.match(exportSource, /server limit/)
assert.match(
  scheduleSource,
  /const WEEKDAYS = \[\s*'Sunday',\s*'Monday'/,
)

console.log(
  'Report workflow regression passed: report definitions validate, named values render as typed SQL literals, injection-shaped text stays escaped, invalid values fail closed, real SQL routes power preview/CSV export, and unsupported direct Excel/parameterized schedules are explicit.',
)
