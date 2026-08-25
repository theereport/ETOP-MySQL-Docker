import type {
  ReportParameter,
  SavedReport,
} from './reportApi'

export type ReportValidationResult = {
  errors: string[]
  warnings: string[]
}

export type ResolvedReportSql = {
  sql: string
  parametersUsed: string[]
}

export type RequestLineage = {
  begin: () => number
  invalidate: () => void
  isCurrent: (requestId: number) => boolean
}

export function createRequestLineage(): RequestLineage {
  let generation = 0

  return {
    begin: () => {
      generation += 1
      return generation
    },
    invalidate: () => {
      generation += 1
    },
    isCurrent: (requestId: number) =>
      requestId === generation,
  }
}

const PARAMETER_NAME_PATTERN =
  /^[A-Za-z_][A-Za-z0-9_]*$/

type PlaceholderSpan = {
  start: number
  end: number
  name: string
}

function findPlaceholderSpans(sql: string) {
  const spans: PlaceholderSpan[] = []
  let state:
    | 'normal'
    | 'single'
    | 'double'
    | 'backtick'
    | 'line-comment'
    | 'block-comment' = 'normal'

  for (let index = 0; index < sql.length; index += 1) {
    const character = sql[index]
    const nextCharacter = sql[index + 1]

    if (state === 'line-comment') {
      if (character === '\n') {
        state = 'normal'
      }
      continue
    }

    if (state === 'block-comment') {
      if (character === '*' && nextCharacter === '/') {
        state = 'normal'
        index += 1
      }
      continue
    }

    if (state !== 'normal') {
      const quote =
        state === 'single'
          ? "'"
          : state === 'double'
            ? '"'
            : '`'

      if (character === '\\') {
        index += 1
        continue
      }

      if (character === quote) {
        if (nextCharacter === quote) {
          index += 1
        } else {
          state = 'normal'
        }
      }
      continue
    }

    if (character === '-' && nextCharacter === '-') {
      state = 'line-comment'
      index += 1
      continue
    }

    if (character === '#') {
      state = 'line-comment'
      continue
    }

    if (character === '/' && nextCharacter === '*') {
      state = 'block-comment'
      index += 1
      continue
    }

    if (character === "'") {
      state = 'single'
      continue
    }

    if (character === '"') {
      state = 'double'
      continue
    }

    if (character === '`') {
      state = 'backtick'
      continue
    }

    if (
      character !== ':' ||
      sql[index - 1] === ':' ||
      !/[A-Za-z_]/.test(nextCharacter ?? '')
    ) {
      continue
    }

    let end = index + 2

    while (/[A-Za-z0-9_]/.test(sql[end] ?? '')) {
      end += 1
    }

    spans.push({
      start: index,
      end,
      name: sql.slice(index + 1, end),
    })
    index = end - 1
  }

  return spans
}

function parameterDisplayName(
  parameter: ReportParameter,
) {
  return parameter.label.trim() || parameter.name
}

export function getSqlParameterNames(sql: string) {
  const names = new Set<string>()

  for (const placeholder of findPlaceholderSpans(sql)) {
    names.add(placeholder.name)
  }

  return [...names]
}

export function validateReportDefinition(
  report: SavedReport,
): ReportValidationResult {
  const errors: string[] = []
  const warnings: string[] = []
  const trimmedName = report.name.trim()
  const trimmedCategory = report.category.trim()
  const trimmedSql = report.sql.trim()

  if (!trimmedName) {
    errors.push('Enter a report name.')
  }

  if (!trimmedCategory) {
    errors.push('Enter a report category.')
  }

  if (!trimmedSql) {
    errors.push('Enter a read-only SQL query.')
  }

  const parametersByName = new Map<
    string,
    ReportParameter
  >()

  for (const parameter of report.parameters) {
    const name = parameter.name.trim()

    if (!name) {
      errors.push(
        `${parameterDisplayName(parameter)} needs a parameter name.`,
      )
      continue
    }

    if (!PARAMETER_NAME_PATTERN.test(name)) {
      errors.push(
        `Parameter "${name}" must start with a letter or underscore and contain only letters, numbers, and underscores.`,
      )
    }

    if (parametersByName.has(name)) {
      errors.push(
        `Parameter name "${name}" is used more than once.`,
      )
    } else {
      parametersByName.set(name, parameter)
    }

    if (
      parameter.type === 'select' &&
      !parameter.options?.length
    ) {
      errors.push(
        `${parameterDisplayName(parameter)} needs at least one selection option.`,
      )
    }

    if (parameter.defaultValue?.trim()) {
      try {
        resolveParameterValue(
          parameter,
          parameter.defaultValue,
        )
      } catch (error) {
        errors.push(
          error instanceof Error
            ? error.message
            : `${parameterDisplayName(parameter)} has an invalid default value.`,
        )
      }
    }
  }

  const placeholders = getSqlParameterNames(trimmedSql)

  for (const placeholder of placeholders) {
    if (!parametersByName.has(placeholder)) {
      errors.push(
        `SQL placeholder :${placeholder} does not have a matching report parameter.`,
      )
    }
  }

  for (const parameter of report.parameters) {
    if (
      parameter.name.trim() &&
      !placeholders.includes(parameter.name.trim())
    ) {
      warnings.push(
        `${parameterDisplayName(parameter)} is defined but not used in the SQL query.`,
      )
    }
  }

  return {
    errors,
    warnings,
  }
}

function escapeSqlString(value: string) {
  const bytes = new TextEncoder().encode(value)
  const hexadecimal = Array.from(bytes, (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('')

  return `CONVERT(0x${hexadecimal} USING utf8mb4)`
}

function resolveParameterValue(
  parameter: ReportParameter,
  rawValue: string,
) {
  const value = rawValue.trim()
  const displayName = parameterDisplayName(parameter)

  if (!value) {
    if (parameter.required) {
      throw new Error(`${displayName} is required.`)
    }

    return 'NULL'
  }

  if (parameter.type === 'number') {
    if (
      !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(value) ||
      !Number.isFinite(Number(value))
    ) {
      throw new Error(
        `${displayName} must be a valid number.`,
      )
    }

    return value
  }

  if (parameter.type === 'boolean') {
    if (value !== 'true' && value !== 'false') {
      throw new Error(
        `${displayName} must be Yes or No.`,
      )
    }

    return value === 'true' ? 'TRUE' : 'FALSE'
  }

  if (parameter.type === 'date') {
    const parsedDate = new Date(`${value}T00:00:00Z`)

    if (
      !/^\d{4}-\d{2}-\d{2}$/.test(value) ||
      Number.isNaN(parsedDate.getTime()) ||
      parsedDate.toISOString().slice(0, 10) !== value
    ) {
      throw new Error(
        `${displayName} must be a valid date.`,
      )
    }
  }

  if (parameter.type === 'select') {
    const allowedValues = new Set(
      parameter.options?.map((option) => option.value),
    )

    if (!allowedValues.has(rawValue)) {
      throw new Error(
        `${displayName} must use one of its configured options.`,
      )
    }
  }

  return escapeSqlString(rawValue)
}

export function resolveReportSql(
  report: SavedReport,
  values: Record<string, string>,
): ResolvedReportSql {
  const validation = validateReportDefinition(report)

  if (validation.errors.length) {
    throw new Error(validation.errors[0])
  }

  const parametersByName = new Map(
    report.parameters.map((parameter) => [
      parameter.name,
      parameter,
    ]),
  )

  const spans = findPlaceholderSpans(report.sql)
  const parametersUsed = [
    ...new Set(spans.map((span) => span.name)),
  ]
  let sql = report.sql

  for (const span of [...spans].reverse()) {
    const parameter = parametersByName.get(span.name)

    if (!parameter) {
      continue
    }

    const rawValue =
      values[span.name] ?? parameter.defaultValue ?? ''
    const resolvedValue = resolveParameterValue(
      parameter,
      rawValue,
    )

    sql =
      sql.slice(0, span.start) +
      resolvedValue +
      sql.slice(span.end)
  }

  return {
    sql,
    parametersUsed,
  }
}

export function reportCanBeScheduled(
  report: SavedReport,
) {
  return getSqlParameterNames(report.sql).length === 0
}
