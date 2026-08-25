import { useState } from 'react'

import type {
  ReportParameter,
  ReportParameterType,
  SavedReport,
} from './ReportBuilder'

type ReportDesignerProps = {
  report: SavedReport
  hasUnsavedChanges: boolean
  isRunning: boolean
  isSaving: boolean
  canRun: boolean
  onChange: (report: SavedReport) => void
  onSave: () => void
  onRunPreview: () => void
}

const parameterTypes: Array<{
  value: ReportParameterType
  label: string
}> = [
  {
    value: 'text',
    label: 'Text',
  },
  {
    value: 'number',
    label: 'Number',
  },
  {
    value: 'date',
    label: 'Date',
  },
  {
    value: 'boolean',
    label: 'Yes / No',
  },
  {
    value: 'select',
    label: 'Selection list',
  },
]

function createParameter(
  existingCount: number,
): ReportParameter {
  const parameterNumber = existingCount + 1

  return {
    id: crypto.randomUUID(),
    name: `parameter_${parameterNumber}`,
    label: `Parameter ${parameterNumber}`,
    type: 'text',
    required: false,
    defaultValue: '',
    placeholder: '',
    options: [],
  }
}

function normalizeParameterName(value: string) {
  return value
    .trim()
    .replace(/[^a-zA-Z0-9_]+/g, '_')
    .replace(/^(\d)/, '_$1')
}

function ReportDesigner({
  report,
  hasUnsavedChanges,
  isRunning,
  isSaving,
  canRun,
  onChange,
  onSave,
  onRunPreview,
}: ReportDesignerProps) {
  const [expandedParameterId, setExpandedParameterId] =
    useState<string | null>(null)

  const updateReport = (
    updates: Partial<SavedReport>,
  ) => {
    onChange({
      ...report,
      ...updates,
      updatedAt: new Date().toISOString(),
    })
  }

  const updateParameter = (
    parameterId: string,
    updates: Partial<ReportParameter>,
  ) => {
    updateReport({
      parameters: report.parameters.map((parameter) =>
        parameter.id === parameterId
          ? {
              ...parameter,
              ...updates,
            }
          : parameter,
      ),
    })
  }

  const addParameter = () => {
    const parameter = createParameter(
      report.parameters.length,
    )

    updateReport({
      parameters: [
        ...report.parameters,
        parameter,
      ],
    })

    setExpandedParameterId(parameter.id)
  }

  const removeParameter = (parameterId: string) => {
    updateReport({
      parameters: report.parameters.filter(
        (parameter) => parameter.id !== parameterId,
      ),
    })

    if (expandedParameterId === parameterId) {
      setExpandedParameterId(null)
    }
  }

  const moveParameter = (
    parameterId: string,
    direction: -1 | 1,
  ) => {
    const currentIndex =
      report.parameters.findIndex(
        (parameter) =>
          parameter.id === parameterId,
      )

    const nextIndex = currentIndex + direction

    if (
      currentIndex < 0 ||
      nextIndex < 0 ||
      nextIndex >= report.parameters.length
    ) {
      return
    }

    const nextParameters = [
      ...report.parameters,
    ]

    const [parameter] = nextParameters.splice(
      currentIndex,
      1,
    )

    nextParameters.splice(
      nextIndex,
      0,
      parameter,
    )

    updateReport({
      parameters: nextParameters,
    })
  }

  const updateSelectOptions = (
    parameterId: string,
    value: string,
  ) => {
    const options = value
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => {
        const separatorIndex = line.indexOf('|')

        if (separatorIndex === -1) {
          return {
            label: line,
            value: line,
          }
        }

        return {
          label: line
            .slice(0, separatorIndex)
            .trim(),
          value: line
            .slice(separatorIndex + 1)
            .trim(),
        }
      })

    updateParameter(parameterId, {
      options,
    })
  }

  return (
    <section className="report-designer">
      <div className="report-designer-toolbar">
        <div>
          <strong>Report definition</strong>

          <span>
            {hasUnsavedChanges
              ? 'Unsaved changes'
              : 'All changes saved'}
          </span>
        </div>

        <div className="report-designer-toolbar-actions">
          <button
            type="button"
            className="report-secondary-button"
            onClick={onSave}
            disabled={isSaving || isRunning}
          >
            {isSaving ? 'Saving…' : 'Save Report'}
          </button>

          <button
            type="button"
            className="report-primary-button"
            onClick={onRunPreview}
            disabled={isRunning || isSaving || !canRun}
          >
            {isRunning
              ? 'Running Preview…'
              : 'Run Preview'}
          </button>
        </div>
      </div>

      <div className="report-designer-card">
        <div className="report-designer-section-heading">
          <div>
            <strong>Report information</strong>

            <span>
              Name and organize the saved report.
            </span>
          </div>
        </div>

        <div className="report-designer-form-grid">
          <label className="report-field">
            <span>Report name</span>

            <input
              type="text"
              value={report.name}
              onChange={(event) =>
                updateReport({
                  name: event.target.value,
                })
              }
              placeholder="Example: Credit Utilization Review"
            />
          </label>

          <label className="report-field">
            <span>Category</span>

            <input
              type="text"
              value={report.category}
              onChange={(event) =>
                updateReport({
                  category: event.target.value,
                })
              }
              placeholder="Example: Credit"
            />
          </label>

          <label className="report-field report-field-full">
            <span>Description</span>

            <textarea
              value={report.description}
              onChange={(event) =>
                updateReport({
                  description: event.target.value,
                })
              }
              placeholder="Describe the report’s purpose and expected output."
              rows={3}
            />
          </label>
        </div>
      </div>

      <div className="report-designer-card">
        <div className="report-designer-section-heading">
          <div>
            <strong>SQL query</strong>

            <span>
              Use named placeholders that match the
              parameters defined below.
            </span>
          </div>

          <span className="report-read-only-badge">
            Read only
          </span>
        </div>

        <div className="report-sql-help">
          <span>Parameter examples:</span>

          <code>:start_date</code>
          <code>:end_date</code>
          <code>:customer_number</code>
        </div>

        <textarea
          className="report-sql-editor"
          value={report.sql}
          onChange={(event) =>
            updateReport({
              sql: event.target.value,
            })
          }
          spellCheck={false}
          placeholder={`SELECT
    CUNUMBER,
    CUNAME,
    CUBALANCE
FROM CUSTOMER
WHERE CUNUMBER = :customer_number`}
        />
      </div>

      <div className="report-designer-card">
        <div className="report-designer-section-heading">
          <div>
            <strong>Report parameters</strong>

            <span>
              Define values users can change before
              previewing or exporting.
            </span>
          </div>

          <button
            type="button"
            className="report-secondary-button"
            onClick={addParameter}
          >
            Add Parameter
          </button>
        </div>

        {report.parameters.length === 0 ? (
          <div className="report-parameter-empty">
            <strong>No parameters defined</strong>

            <p>
              This report will run exactly as written.
              Add parameters when users need to supply
              dates, customer numbers, locations, or
              other filters.
            </p>
          </div>
        ) : (
          <div className="report-parameter-list">
            {report.parameters.map(
              (parameter, index) => {
                const isExpanded =
                  expandedParameterId === parameter.id

                const optionText =
                  parameter.options
                    ?.map(
                      (option) =>
                        `${option.label}|${option.value}`,
                    )
                    .join('\n') ?? ''

                return (
                  <article
                    key={parameter.id}
                    className="report-parameter-card"
                  >
                    <button
                      type="button"
                      className="report-parameter-summary"
                      onClick={() =>
                        setExpandedParameterId(
                          isExpanded
                            ? null
                            : parameter.id,
                        )
                      }
                    >
                      <div>
                        <span className="report-parameter-order">
                          {index + 1}
                        </span>

                        <div>
                          <strong>
                            {parameter.label ||
                              parameter.name}
                          </strong>

                          <span>
                            :{parameter.name} ·{' '}
                            {parameter.type}
                            {parameter.required
                              ? ' · required'
                              : ''}
                          </span>
                        </div>
                      </div>

                      <span>
                        {isExpanded ? '−' : '+'}
                      </span>
                    </button>

                    {isExpanded && (
                      <div className="report-parameter-editor">
                        <div className="report-parameter-grid">
                          <label className="report-field">
                            <span>Display label</span>

                            <input
                              type="text"
                              value={parameter.label}
                              onChange={(event) =>
                                updateParameter(
                                  parameter.id,
                                  {
                                    label:
                                      event.target
                                        .value,
                                  },
                                )
                              }
                            />
                          </label>

                          <label className="report-field">
                            <span>Parameter name</span>

                            <input
                              type="text"
                              value={parameter.name}
                              onChange={(event) =>
                                updateParameter(
                                  parameter.id,
                                  {
                                    name:
                                      normalizeParameterName(
                                        event.target
                                          .value,
                                      ),
                                  },
                                )
                              }
                            />
                          </label>

                          <label className="report-field">
                            <span>Type</span>

                            <select
                              value={parameter.type}
                              onChange={(event) =>
                                updateParameter(
                                  parameter.id,
                                  {
                                    type: event
                                      .target
                                      .value as ReportParameterType,
                                  },
                                )
                              }
                            >
                              {parameterTypes.map(
                                (type) => (
                                  <option
                                    key={type.value}
                                    value={type.value}
                                  >
                                    {type.label}
                                  </option>
                                ),
                              )}
                            </select>
                          </label>

                          <label className="report-field">
                            <span>Default value</span>

                            <input
                              type={
                                parameter.type ===
                                'date'
                                  ? 'date'
                                  : parameter.type ===
                                      'number'
                                    ? 'number'
                                    : 'text'
                              }
                              value={
                                parameter.defaultValue ??
                                ''
                              }
                              onChange={(event) =>
                                updateParameter(
                                  parameter.id,
                                  {
                                    defaultValue:
                                      event.target
                                        .value,
                                  },
                                )
                              }
                            />
                          </label>

                          <label className="report-field report-field-full">
                            <span>Placeholder</span>

                            <input
                              type="text"
                              value={
                                parameter.placeholder ??
                                ''
                              }
                              onChange={(event) =>
                                updateParameter(
                                  parameter.id,
                                  {
                                    placeholder:
                                      event.target
                                        .value,
                                  },
                                )
                              }
                            />
                          </label>

                          {parameter.type ===
                            'select' && (
                            <label className="report-field report-field-full">
                              <span>
                                Selection options
                              </span>

                              <textarea
                                value={optionText}
                                onChange={(event) =>
                                  updateSelectOptions(
                                    parameter.id,
                                    event.target
                                      .value,
                                  )
                                }
                                rows={5}
                                placeholder={`Open|OPEN
Closed|CLOSED
All|ALL`}
                              />

                              <small>
                                Enter one option per
                                line using
                                Label|Value.
                              </small>
                            </label>
                          )}

                          <label className="report-checkbox-field">
                            <input
                              type="checkbox"
                              checked={
                                parameter.required
                              }
                              onChange={(event) =>
                                updateParameter(
                                  parameter.id,
                                  {
                                    required:
                                      event.target
                                        .checked,
                                  },
                                )
                              }
                            />

                            <span>
                              Require this parameter
                            </span>
                          </label>
                        </div>

                        <div className="report-parameter-actions">
                          <button
                            type="button"
                            onClick={() =>
                              moveParameter(
                                parameter.id,
                                -1,
                              )
                            }
                            disabled={index === 0}
                          >
                            Move Up
                          </button>

                          <button
                            type="button"
                            onClick={() =>
                              moveParameter(
                                parameter.id,
                                1,
                              )
                            }
                            disabled={
                              index ===
                              report.parameters
                                .length -
                                1
                            }
                          >
                            Move Down
                          </button>

                          <button
                            type="button"
                            className="danger"
                            onClick={() =>
                              removeParameter(
                                parameter.id,
                              )
                            }
                          >
                            Remove
                          </button>
                        </div>
                      </div>
                    )}
                  </article>
                )
              },
            )}
          </div>
        )}
      </div>
    </section>
  )
}

export default ReportDesigner
