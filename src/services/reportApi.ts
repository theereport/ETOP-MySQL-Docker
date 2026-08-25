import { resolveReportSql } from './reportWorkflow'

export type ReportParameterType =
  | 'text'
  | 'number'
  | 'date'
  | 'boolean'
  | 'select'

export type ReportParameterOption = {
  label: string
  value: string
}

export type ReportParameter = {
  id: string
  name: string
  label: string
  type: ReportParameterType
  required: boolean
  defaultValue?: string
  placeholder?: string
  options?: ReportParameterOption[]
}

export type SavedReport = {
  id: string
  name: string
  description: string
  category: string
  sql: string
  parameters: ReportParameter[]
  database: string
  outputFormat: 'csv' | 'xlsx' | 'json'
  createdAt: string
  updatedAt: string
}

export type SqlRuntimeCapabilities = {
  connected: boolean
  database?: string
  defaultLimit: number
  maximumLimit: number
}

export type ReportSqlResult = {
  columns: string[]
  rows: Array<
    Record<string, string | number | boolean | null>
  >
  rowCount: number
  executionTimeMs: number
  truncated: boolean
  rowLimit: number
}

export type ReportScheduleFrequency =
  | 'daily'
  | 'weekly'
  | 'monthly'

export type ReportSchedule = {
  id: string
  name: string
  description: string
  category: string
  status: 'active' | 'paused' | 'draft' | 'error'
  sourceType: 'report'
  reportId: string
  reportName: string
  sql: string
  scriptPath: string
  outputFormat: 'csv' | 'xlsx' | 'pdf'
  fileNameTemplate: string
  schedule: {
    frequency:
      | ReportScheduleFrequency
      | 'manual'
      | 'custom'
    time: string
    daysOfWeek: number[]
    dayOfMonth: number | null
    cronExpression: string
    timezone: string
  }
  delivery: {
    method: 'email' | 'folder' | 'none'
    recipients: string[]
    ccRecipients: string[]
    subject: string
    message: string
    outputFolder: string
    attachOutput: boolean
  }
  createdAt: string
  updatedAt: string
  lastRunAt: string | null
  nextRunAt: string | null
  lastRunStatus:
    | 'running'
    | 'success'
    | 'warning'
    | 'failed'
    | 'cancelled'
    | null
}

export type SaveReportScheduleInput = {
  id?: string
  name: string
  frequency: ReportScheduleFrequency
  time: string
  dayOfWeek: number
  dayOfMonth: number
  timezone: string
  outputFormat: 'csv' | 'xlsx'
}

type ReportListResponse = {
  items: SavedReport[]
  total: number
}

type SaveReportPayload = {
  id?: string
  name: string
  description: string
  category: string
  sql: string
  parameters: ReportParameter[]
  database: string
  outputFormat: 'csv' | 'xlsx' | 'json'
}

const PLATFORM_API_BASE =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, '') ??
  'http://127.0.0.1:8000/api/v1'

const API_ORIGIN = PLATFORM_API_BASE.replace(
  /\/api\/v1$/,
  '',
)

const REPORT_API_BASE = `${PLATFORM_API_BASE}/reports`
const AUTOMATION_API_BASE =
  `${PLATFORM_API_BASE}/automations`
const SQL_API_BASE = `${API_ORIGIN}/sql`

async function getErrorMessage(
  response: Response,
  fallback?: string,
): Promise<string> {
  const errorPayload = await response
    .clone()
    .json()
    .catch(() => null)

  return (
    errorPayload?.detail ??
    errorPayload?.message ??
    fallback ??
    `Request failed with status ${response.status}.`
  )
}

async function requireOk(
  response: Response,
  fallback?: string,
) {
  if (!response.ok) {
    throw new Error(
      await getErrorMessage(response, fallback),
    )
  }

  return response
}

function reportPayload(
  report: SavedReport,
): SaveReportPayload {
  return {
    name: report.name,
    description: report.description,
    category: report.category,
    sql: report.sql,
    parameters: report.parameters,
    database: report.database,
    outputFormat: report.outputFormat,
  }
}

export async function getReports(): Promise<SavedReport[]> {
  const response = await fetch(REPORT_API_BASE)

  await requireOk(
    response,
    'Unable to load the saved report catalog.',
  )

  const payload =
    (await response.json()) as ReportListResponse

  return payload.items ?? []
}

export async function getReport(
  reportId: string,
): Promise<SavedReport> {
  const response = await fetch(
    `${REPORT_API_BASE}/${encodeURIComponent(reportId)}`,
  )

  await requireOk(response, 'Unable to load the report.')

  return (await response.json()) as SavedReport
}

export async function createReport(
  report: SavedReport,
): Promise<SavedReport> {
  const response = await fetch(REPORT_API_BASE, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      ...reportPayload(report),
      id: report.id,
    }),
  })

  await requireOk(response, 'Unable to save the report.')

  return (await response.json()) as SavedReport
}

export async function updateReport(
  reportId: string,
  report: SavedReport,
): Promise<SavedReport> {
  const response = await fetch(
    `${REPORT_API_BASE}/${encodeURIComponent(reportId)}`,
    {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(reportPayload(report)),
    },
  )

  await requireOk(response, 'Unable to update the report.')

  return (await response.json()) as SavedReport
}

export async function deleteReport(
  reportId: string,
): Promise<void> {
  const response = await fetch(
    `${REPORT_API_BASE}/${encodeURIComponent(reportId)}`,
    {
      method: 'DELETE',
    },
  )

  await requireOk(response, 'Unable to delete the report.')
}

export async function getSqlRuntimeCapabilities(): Promise<SqlRuntimeCapabilities> {
  const response = await fetch(`${SQL_API_BASE}/connection`)

  await requireOk(
    response,
    'The read-only ERP reporting connection is unavailable.',
  )

  const payload = (await response.json()) as {
    connected?: boolean
    success?: boolean
    database?: string
    default_limit?: number
    maximum_limit?: number
  }

  const connected = payload.connected ?? payload.success ?? true

  if (!connected) {
    throw new Error(
      'The read-only ERP reporting connection is unavailable.',
    )
  }

  return {
    connected,
    database: payload.database,
    defaultLimit: payload.default_limit ?? 500,
    maximumLimit: payload.maximum_limit ?? 5000,
  }
}

export async function executeReportPreview(
  report: SavedReport,
  parameterValues: Record<string, string>,
  rowLimit: number,
  signal?: AbortSignal,
): Promise<ReportSqlResult> {
  const resolved = resolveReportSql(
    report,
    parameterValues,
  )

  const response = await fetch(`${SQL_API_BASE}/execute`, {
    method: 'POST',
    signal,
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      sql: resolved.sql,
      row_limit: rowLimit,
    }),
  })

  await requireOk(response, 'Unable to execute the report.')

  const payload = (await response.json()) as {
    columns?: string[]
    rows?: ReportSqlResult['rows']
    row_count?: number
    execution_ms?: number
    row_limit?: number
    limit_applied?: boolean
  }

  const rows = payload.rows ?? []
  const effectiveLimit = payload.row_limit ?? rowLimit

  return {
    columns: payload.columns ?? [],
    rows,
    rowCount: payload.row_count ?? rows.length,
    executionTimeMs: payload.execution_ms ?? 0,
    truncated: rows.length >= effectiveLimit,
    rowLimit: effectiveLimit,
  }
}

export async function exportReportCsv(
  report: SavedReport,
  parameterValues: Record<string, string>,
  rowLimit: number,
) {
  const resolved = resolveReportSql(
    report,
    parameterValues,
  )

  const response = await fetch(`${SQL_API_BASE}/export`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      sql: resolved.sql,
      row_limit: rowLimit,
    }),
  })

  await requireOk(response, 'Unable to export the report.')

  return {
    blob: await response.blob(),
    contentDisposition: response.headers.get(
      'Content-Disposition',
    ),
  }
}

export async function getReportSchedules(
  reportId: string,
): Promise<ReportSchedule[]> {
  const response = await fetch(AUTOMATION_API_BASE)

  await requireOk(
    response,
    'Unable to load report schedules.',
  )

  const payload = (await response.json()) as {
    automations?: ReportSchedule[]
  }

  return (payload.automations ?? []).filter(
    (automation) =>
      automation.sourceType === 'report' &&
      automation.reportId === reportId,
  )
}

export async function saveReportSchedule(
  report: SavedReport,
  input: SaveReportScheduleInput,
  existingSchedule?: ReportSchedule,
): Promise<ReportSchedule> {
  const now = new Date().toISOString()

  const schedule: ReportSchedule = {
    id: input.id ?? existingSchedule?.id ?? crypto.randomUUID(),
    name: input.name.trim(),
    description:
      existingSchedule?.description ??
      `Scheduled export for ${report.name}.`,
    category: report.category,
    status: existingSchedule?.status ?? 'active',
    sourceType: 'report',
    reportId: report.id,
    reportName: report.name,
    sql: '',
    scriptPath: '',
    outputFormat: input.outputFormat,
    fileNameTemplate:
      existingSchedule?.fileNameTemplate ??
      '{automation_name}_{yyyy-MM-dd}',
    schedule: {
      frequency: input.frequency,
      time: input.time,
      daysOfWeek:
        input.frequency === 'weekly'
          ? [input.dayOfWeek]
          : [],
      dayOfMonth:
        input.frequency === 'monthly'
          ? input.dayOfMonth
          : null,
      cronExpression: '',
      timezone: input.timezone,
    },
    delivery:
      existingSchedule?.delivery ?? {
        method: 'none',
        recipients: [],
        ccRecipients: [],
        subject: '{automation_name} - {run_date}',
        message:
          'The scheduled report has completed.',
        outputFolder: '',
        attachOutput: true,
      },
    createdAt: existingSchedule?.createdAt ?? now,
    updatedAt: now,
    lastRunAt: existingSchedule?.lastRunAt ?? null,
    nextRunAt: existingSchedule?.nextRunAt ?? null,
    lastRunStatus:
      existingSchedule?.lastRunStatus ?? null,
  }

  const response = await fetch(AUTOMATION_API_BASE, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(schedule),
  })

  await requireOk(response, 'Unable to save the report schedule.')

  const payload = (await response.json()) as {
    automation: ReportSchedule
  }

  return payload.automation
}

export async function setReportScheduleStatus(
  schedule: ReportSchedule,
  status: 'active' | 'paused',
): Promise<ReportSchedule> {
  const response = await fetch(AUTOMATION_API_BASE, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      ...schedule,
      status,
      updatedAt: new Date().toISOString(),
    }),
  })

  await requireOk(
    response,
    'Unable to update the report schedule.',
  )

  const payload = (await response.json()) as {
    automation: ReportSchedule
  }

  return payload.automation
}

export async function deleteReportSchedule(
  scheduleId: string,
): Promise<void> {
  const response = await fetch(
    `${AUTOMATION_API_BASE}/${encodeURIComponent(scheduleId)}`,
    {
      method: 'DELETE',
    },
  )

  await requireOk(
    response,
    'Unable to delete the report schedule.',
  )
}
