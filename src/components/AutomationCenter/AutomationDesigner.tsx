import {
  useMemo,
  useState,
} from 'react'

import type {
  AutomationDefinition,
  AutomationDeliveryMethod,
  AutomationFrequency,
  AutomationOutputFormat,
  AutomationSourceType,
} from './AutomationCenter'

type AutomationDesignerProps = {
  automation: AutomationDefinition

  onChange: (
    automation: AutomationDefinition,
  ) => void

  onSave: (automation?: AutomationDefinition,) => void
  onCancel: () => void
}

type DesignerStep =
  | 'source'
  | 'schedule'
  | 'output'
  | 'delivery'
  | 'review'

type SavedReportReference = {
  id: string
  name: string
  category?: string
  description?: string
}

const REPORT_STORAGE_KEYS = [
  'enterprise-ai-workbench.reports',
  'enterprise-ai-workbench.saved-reports',
  'report-builder.saved-reports',
]

const STEPS: Array<{
  id: DesignerStep
  number: number
  label: string
}> = [
  {
    id: 'source',
    number: 1,
    label: 'Source',
  },
  {
    id: 'schedule',
    number: 2,
    label: 'Schedule',
  },
  {
    id: 'output',
    number: 3,
    label: 'Output',
  },
  {
    id: 'delivery',
    number: 4,
    label: 'Delivery',
  },
  {
    id: 'review',
    number: 5,
    label: 'Review',
  },
]

const DAY_OPTIONS = [
  {
    value: 0,
    label: 'Sun',
  },
  {
    value: 1,
    label: 'Mon',
  },
  {
    value: 2,
    label: 'Tue',
  },
  {
    value: 3,
    label: 'Wed',
  },
  {
    value: 4,
    label: 'Thu',
  },
  {
    value: 5,
    label: 'Fri',
  },
  {
    value: 6,
    label: 'Sat',
  },
]

function loadSavedReports(): SavedReportReference[] {
  for (const storageKey of REPORT_STORAGE_KEYS) {
    try {
      const storedValue =
        window.localStorage.getItem(storageKey)

      if (!storedValue) {
        continue
      }

      const parsedValue = JSON.parse(storedValue)

      if (!Array.isArray(parsedValue)) {
        continue
      }

      const reports = parsedValue
        .map((report): SavedReportReference | null => {
          if (
            !report ||
            typeof report !== 'object'
          ) {
            return null
          }

          const id =
            typeof report.id === 'string'
              ? report.id
              : ''

          const name =
            typeof report.name === 'string'
              ? report.name
              : typeof report.title === 'string'
                ? report.title
                : ''

          if (!id || !name) {
            return null
          }

          return {
            id,
            name,
            category:
              typeof report.category === 'string'
                ? report.category
                : '',
            description:
              typeof report.description === 'string'
                ? report.description
                : '',
          }
        })
        .filter(
          (
            report,
          ): report is SavedReportReference =>
            report !== null,
        )

      if (reports.length > 0) {
        return reports
      }
    } catch {
      // Try the next known storage key.
    }
  }

  return []
}

function parseRecipientList(
  value: string,
) {
  return value
    .split(/[,;\n]/)
    .map((recipient) => recipient.trim())
    .filter(Boolean)
}

function formatRecipientList(
  recipients: string[],
) {
  return recipients.join(', ')
}

function formatTime(
  value: string,
) {
  if (!value) {
    return 'No time selected'
  }

  const [hoursText, minutesText] =
    value.split(':')

  const hours = Number(hoursText)
  const minutes = Number(minutesText)

  if (
    !Number.isFinite(hours) ||
    !Number.isFinite(minutes)
  ) {
    return value
  }

  const date = new Date()

  date.setHours(
    hours,
    minutes,
    0,
    0,
  )

  return date.toLocaleTimeString([], {
    hour: 'numeric',
    minute: '2-digit',
  })
}

function formatScheduleSummary(
  automation: AutomationDefinition,
) {
  const {
    frequency,
    time,
    daysOfWeek,
    dayOfMonth,
    cronExpression,
  } = automation.schedule

  if (frequency === 'manual') {
    return 'Manual execution only'
  }

  if (frequency === 'daily') {
    return `Every day at ${formatTime(time)}`
  }

  if (frequency === 'weekly') {
    const selectedDays = DAY_OPTIONS
      .filter((day) =>
        daysOfWeek.includes(day.value),
      )
      .map((day) => day.label)
      .join(', ')

    return `Every ${
      selectedDays || 'selected weekday'
    } at ${formatTime(time)}`
  }

  if (frequency === 'monthly') {
    return `On day ${
      dayOfMonth ?? 1
    } of each month at ${formatTime(time)}`
  }

  return cronExpression
    ? `Custom schedule: ${cronExpression}`
    : 'Custom schedule not configured'
}

function formatSourceSummary(
  automation: AutomationDefinition,
) {
  if (automation.sourceType === 'report') {
    return (
      automation.reportName ||
      'No saved report selected'
    )
  }

  if (automation.sourceType === 'sql') {
    return automation.sql.trim()
      ? 'Direct SQL query'
      : 'SQL query not entered'
  }

  if (
    automation.sourceType ===
    'powershell'
  ) {
    return automation.scriptPath.trim()
      ? `PowerShell: ${automation.scriptPath}`
      : 'PowerShell script not selected'
  }

  return automation.scriptPath.trim()
    ? `Python: ${automation.scriptPath}`
    : 'Python script not selected'
}

function AutomationDesigner({
  automation,
  onChange,
  onSave,
  onCancel,
}: AutomationDesignerProps) {
  const [currentStep, setCurrentStep] =
    useState<DesignerStep>('source')

  const [savedReports] = useState<
    SavedReportReference[]
  >(() => loadSavedReports())

  const currentStepIndex =
    STEPS.findIndex(
      (step) => step.id === currentStep,
    )

  const selectedReport = useMemo(
    () =>
      savedReports.find(
        (report) =>
          report.id === automation.reportId,
      ) ?? null,
    [
      automation.reportId,
      savedReports,
    ],
  )

  const updateAutomation = <
    Key extends keyof AutomationDefinition,
  >(
    key: Key,
    value: AutomationDefinition[Key],
  ) => {
    onChange({
      ...automation,
      [key]: value,
    })
  }

  const updateSchedule = <
    Key extends keyof AutomationDefinition['schedule'],
  >(
    key: Key,
    value: AutomationDefinition['schedule'][Key],
  ) => {
    onChange({
      ...automation,
      schedule: {
        ...automation.schedule,
        [key]: value,
      },
    })
  }

  const updateDelivery = <
    Key extends keyof AutomationDefinition['delivery'],
  >(
    key: Key,
    value: AutomationDefinition['delivery'][Key],
  ) => {
    onChange({
      ...automation,
      delivery: {
        ...automation.delivery,
        [key]: value,
      },
    })
  }

  const handleSourceTypeChange = (
    sourceType: AutomationSourceType,
  ) => {
    onChange({
      ...automation,
      sourceType,
      reportId:
        sourceType === 'report'
          ? automation.reportId
          : '',
      reportName:
        sourceType === 'report'
          ? automation.reportName
          : '',
      sql:
        sourceType === 'sql'
          ? automation.sql
          : '',
      scriptPath:
        sourceType === 'powershell' ||
        sourceType === 'python'
          ? automation.scriptPath
          : '',
    })
  }

  const handleReportChange = (
    reportId: string,
  ) => {
    const report =
      savedReports.find(
        (item) => item.id === reportId,
      ) ?? null

    onChange({
      ...automation,
      reportId,
      reportName: report?.name ?? '',
    })
  }

  const handleFrequencyChange = (
    frequency: AutomationFrequency,
  ) => {
    const nextDays =
      frequency === 'weekly' &&
      automation.schedule.daysOfWeek.length === 0
        ? [1]
        : automation.schedule.daysOfWeek

    updateAutomation('schedule', {
      ...automation.schedule,
      frequency,
      daysOfWeek: nextDays,
      dayOfMonth:
        frequency === 'monthly'
          ? automation.schedule.dayOfMonth ?? 1
          : automation.schedule.dayOfMonth,
    })
  }

  const toggleDay = (
    dayValue: number,
  ) => {
    const isSelected =
      automation.schedule.daysOfWeek.includes(
        dayValue,
      )

    const nextDays = isSelected
      ? automation.schedule.daysOfWeek.filter(
          (day) => day !== dayValue,
        )
      : [
          ...automation.schedule.daysOfWeek,
          dayValue,
        ].sort((left, right) => left - right)

    updateSchedule(
      'daysOfWeek',
      nextDays,
    )
  }

  const goToPreviousStep = () => {
    if (currentStepIndex <= 0) {
      return
    }

    setCurrentStep(
      STEPS[currentStepIndex - 1].id,
    )
  }

  const goToNextStep = () => {
    if (
      currentStepIndex >=
      STEPS.length - 1
    ) {
      return
    }

    setCurrentStep(
      STEPS[currentStepIndex + 1].id,
    )
  }

  const handleSaveDraft = () => {
    onSave({
      ...automation,
      status: 'draft',
    })

    window.setTimeout(() => {
      onSave()
    }, 0)
  }

  const handleActivate = () => {
    onSave({
      ...automation,
      status: 'active',
    })

    window.setTimeout(() => {
      onSave()
    }, 0)
  }

  return (
    <section className="automation-designer">
      <div className="automation-designer-header">
        <div>
          <span className="automation-eyebrow">
            Workflow designer
          </span>

          <h2>
            {automation.name ||
              'Untitled Automation'}
          </h2>

          <p>
            Configure the source, schedule,
            output, and delivery settings for
            this workflow.
          </p>
        </div>

        <button
          type="button"
          className="automation-secondary-button"
          onClick={onCancel}
        >
          Cancel
        </button>
      </div>

      <div className="automation-designer-layout">
        <aside className="automation-designer-sidebar">
          <div className="automation-designer-identity">
            <label>
              <span>Automation name</span>

              <input
                type="text"
                value={automation.name}
                onChange={(event) =>
                  updateAutomation(
                    'name',
                    event.target.value,
                  )
                }
                placeholder="Enter automation name"
              />
            </label>

            <label>
              <span>Category</span>

              <input
                type="text"
                value={automation.category}
                onChange={(event) =>
                  updateAutomation(
                    'category',
                    event.target.value,
                  )
                }
                placeholder="Accounting"
              />
            </label>

            <label>
              <span>Description</span>

              <textarea
                value={automation.description}
                onChange={(event) =>
                  updateAutomation(
                    'description',
                    event.target.value,
                  )
                }
                placeholder="Describe what this automation does."
                rows={4}
              />
            </label>
          </div>

          <nav className="automation-designer-steps">
            {STEPS.map((step, index) => {
              const isActive =
                step.id === currentStep

              const isComplete =
                index < currentStepIndex

              return (
                <button
                  key={step.id}
                  type="button"
                  className={[
                    isActive ? 'active' : '',
                    isComplete ? 'complete' : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  onClick={() =>
                    setCurrentStep(step.id)
                  }
                >
                  <span className="automation-step-number">
                    {isComplete
                      ? '✓'
                      : step.number}
                  </span>

                  <span>
                    {step.label}
                  </span>
                </button>
              )
            })}
          </nav>
        </aside>

        <div className="automation-designer-content">
          {currentStep === 'source' && (
            <div className="automation-designer-step">
              <div className="automation-step-heading">
                <span className="automation-eyebrow">
                  Step 1
                </span>

                <h3>
                  Choose the automation source
                </h3>

                <p>
                  Select the report, query, or
                  script that will run when this
                  automation is executed.
                </p>
              </div>

              <div className="automation-source-grid">
                <button
                  type="button"
                  className={
                    automation.sourceType ===
                    'report'
                      ? 'automation-source-card active'
                      : 'automation-source-card'
                  }
                  onClick={() =>
                    handleSourceTypeChange(
                      'report',
                    )
                  }
                >
                  <strong>Saved Report</strong>

                  <span>
                    Run a report created in the
                    Report Builder.
                  </span>
                </button>

                <button
                  type="button"
                  className={
                    automation.sourceType ===
                    'sql'
                      ? 'automation-source-card active'
                      : 'automation-source-card'
                  }
                  onClick={() =>
                    handleSourceTypeChange(
                      'sql',
                    )
                  }
                >
                  <strong>SQL Query</strong>

                  <span>
                    Execute a direct read-only SQL
                    query.
                  </span>
                </button>

                <button
                  type="button"
                  className={
                    automation.sourceType ===
                    'powershell'
                      ? 'automation-source-card active'
                      : 'automation-source-card'
                  }
                  onClick={() =>
                    handleSourceTypeChange(
                      'powershell',
                    )
                  }
                >
                  <strong>PowerShell</strong>

                  <span>
                    Run a local PowerShell script.
                  </span>
                </button>

                <button
                  type="button"
                  className={
                    automation.sourceType ===
                    'python'
                      ? 'automation-source-card active'
                      : 'automation-source-card'
                  }
                  onClick={() =>
                    handleSourceTypeChange(
                      'python',
                    )
                  }
                >
                  <strong>Python</strong>

                  <span>
                    Run a local Python script.
                  </span>
                </button>
              </div>

              {automation.sourceType ===
                'report' && (
                <div className="automation-form-card">
                  <label>
                    <span>Saved report</span>

                    <select
                      value={
                        automation.reportId
                      }
                      onChange={(event) =>
                        handleReportChange(
                          event.target.value,
                        )
                      }
                    >
                      <option value="">
                        Select a report
                      </option>

                      {savedReports.map(
                        (report) => (
                          <option
                            key={report.id}
                            value={report.id}
                          >
                            {report.name}
                            {report.category
                              ? ` — ${report.category}`
                              : ''}
                          </option>
                        ),
                      )}
                    </select>
                  </label>

                  {savedReports.length ===
                    0 && (
                    <div className="automation-inline-warning">
                      No saved Report Builder
                      reports were found in local
                      storage. Save a report first,
                      or choose SQL or a script
                      source.
                    </div>
                  )}

                  {selectedReport && (
                    <div className="automation-selected-source">
                      <span>
                        Selected report
                      </span>

                      <strong>
                        {selectedReport.name}
                      </strong>

                      {selectedReport.description && (
                        <p>
                          {
                            selectedReport.description
                          }
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )}

              {automation.sourceType ===
                'sql' && (
                <div className="automation-form-card">
                  <label>
                    <span>Read-only SQL</span>

                    <textarea
                      className="automation-code-editor"
                      value={automation.sql}
                      onChange={(event) =>
                        updateAutomation(
                          'sql',
                          event.target.value,
                        )
                      }
                      placeholder={`SELECT
    CUNUMBER,
    CUNAME,
    CUBALANCE
FROM CUSTOMER
WHERE CUBALANCE > 0;`}
                      rows={16}
                      spellCheck={false}
                    />
                  </label>

                  <div className="automation-inline-notice">
                    SQL validation and table
                    restrictions should also be
                    enforced by the backend before
                    execution.
                  </div>
                </div>
              )}

              {(automation.sourceType ===
                'powershell' ||
                automation.sourceType ===
                  'python') && (
                <div className="automation-form-card">
                  <label>
                    <span>
                      {automation.sourceType ===
                      'powershell'
                        ? 'PowerShell script path'
                        : 'Python script path'}
                    </span>

                    <input
                      type="text"
                      value={
                        automation.scriptPath
                      }
                      onChange={(event) =>
                        updateAutomation(
                          'scriptPath',
                          event.target.value,
                        )
                      }
                      placeholder={
                        automation.sourceType ===
                        'powershell'
                          ? 'C:\\Reports\\WeeklyCreditReport.ps1'
                          : 'C:\\AI\\Scripts\\report_job.py'
                      }
                    />
                  </label>

                  <div className="automation-inline-notice">
                    The backend service must have
                    permission to access and run
                    this local path.
                  </div>
                </div>
              )}
            </div>
          )}

          {currentStep === 'schedule' && (
            <div className="automation-designer-step">
              <div className="automation-step-heading">
                <span className="automation-eyebrow">
                  Step 2
                </span>

                <h3>
                  Configure the schedule
                </h3>

                <p>
                  Choose when this automation
                  should run.
                </p>
              </div>

              <div className="automation-frequency-grid">
                {(
                  [
                    'manual',
                    'daily',
                    'weekly',
                    'monthly',
                    'custom',
                  ] as AutomationFrequency[]
                ).map((frequency) => (
                  <button
                    key={frequency}
                    type="button"
                    className={
                      automation.schedule
                        .frequency === frequency
                        ? 'automation-frequency-card active'
                        : 'automation-frequency-card'
                    }
                    onClick={() =>
                      handleFrequencyChange(
                        frequency,
                      )
                    }
                  >
                    <strong>
                      {frequency
                        .charAt(0)
                        .toUpperCase() +
                        frequency.slice(1)}
                    </strong>
                  </button>
                ))}
              </div>

              {automation.schedule.frequency !==
                'manual' && (
                <div className="automation-form-card automation-form-grid">
                  <label>
                    <span>Run time</span>

                    <input
                      type="time"
                      value={
                        automation.schedule.time
                      }
                      onChange={(event) =>
                        updateSchedule(
                          'time',
                          event.target.value,
                        )
                      }
                    />
                  </label>

                  <label>
                    <span>Timezone</span>

                    <input
                      type="text"
                      value={
                        automation.schedule
                          .timezone
                      }
                      onChange={(event) =>
                        updateSchedule(
                          'timezone',
                          event.target.value,
                        )
                      }
                      placeholder="America/New_York"
                    />
                  </label>
                </div>
              )}

              {automation.schedule.frequency ===
                'weekly' && (
                <div className="automation-form-card">
                  <span className="automation-field-label">
                    Run on
                  </span>

                  <div className="automation-day-picker">
                    {DAY_OPTIONS.map((day) => (
                      <button
                        key={day.value}
                        type="button"
                        className={
                          automation.schedule.daysOfWeek.includes(
                            day.value,
                          )
                            ? 'active'
                            : undefined
                        }
                        onClick={() =>
                          toggleDay(day.value)
                        }
                      >
                        {day.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {automation.schedule.frequency ===
                'monthly' && (
                <div className="automation-form-card">
                  <label>
                    <span>Day of month</span>

                    <input
                      type="number"
                      min={1}
                      max={31}
                      value={
                        automation.schedule
                          .dayOfMonth ?? 1
                      }
                      onChange={(event) =>
                        updateSchedule(
                          'dayOfMonth',
                          Math.min(
                            31,
                            Math.max(
                              1,
                              Number(
                                event.target
                                  .value,
                              ) || 1,
                            ),
                          ),
                        )
                      }
                    />
                  </label>
                </div>
              )}

              {automation.schedule.frequency ===
                'custom' && (
                <div className="automation-form-card">
                  <label>
                    <span>CRON expression</span>

                    <input
                      type="text"
                      value={
                        automation.schedule
                          .cronExpression
                      }
                      onChange={(event) =>
                        updateSchedule(
                          'cronExpression',
                          event.target.value,
                        )
                      }
                      placeholder="0 7 * * 1-5"
                    />
                  </label>

                  <div className="automation-inline-notice">
                    Example: run at 7:00 AM
                    Monday through Friday using
                    <code>0 7 * * 1-5</code>.
                  </div>
                </div>
              )}

              <div className="automation-schedule-summary">
                <span>Schedule summary</span>

                <strong>
                  {formatScheduleSummary(
                    automation,
                  )}
                </strong>
              </div>
            </div>
          )}

          {currentStep === 'output' && (
            <div className="automation-designer-step">
              <div className="automation-step-heading">
                <span className="automation-eyebrow">
                  Step 3
                </span>

                <h3>
                  Configure the output
                </h3>

                <p>
                  Select the file format and
                  filename pattern.
                </p>
              </div>

              <div className="automation-output-grid">
                {(
                  [
                    'xlsx',
                    'csv',
                    'pdf',
                  ] as AutomationOutputFormat[]
                ).map((format) => (
                  <button
                    key={format}
                    type="button"
                    className={
                      automation.outputFormat ===
                      format
                        ? 'automation-output-card active'
                        : 'automation-output-card'
                    }
                    onClick={() =>
                      updateAutomation(
                        'outputFormat',
                        format,
                      )
                    }
                  >
                    <strong>
                      {format.toUpperCase()}
                    </strong>

                    <span>
                      {format === 'xlsx' &&
                        'Formatted Excel workbook'}

                      {format === 'csv' &&
                        'Fast export for large data'}

                      {format === 'pdf' &&
                        'Presentation-ready document'}
                    </span>
                  </button>
                ))}
              </div>

              <div className="automation-form-card">
                <label>
                  <span>Filename template</span>

                  <input
                    type="text"
                    value={
                      automation.fileNameTemplate
                    }
                    onChange={(event) =>
                      updateAutomation(
                        'fileNameTemplate',
                        event.target.value,
                      )
                    }
                    placeholder="{automation_name}_{yyyy-MM-dd}"
                  />
                </label>

                <div className="automation-template-tokens">
                  <span>Available tokens</span>

                  <code>
                    {'{automation_name}'}
                  </code>

                  <code>
                    {'{yyyy-MM-dd}'}
                  </code>

                  <code>
                    {'{yyyyMMdd}'}
                  </code>

                  <code>
                    {'{HHmm}'}
                  </code>

                  <code>
                    {'{run_date}'}
                  </code>
                </div>
              </div>

              <div className="automation-output-preview">
                <span>Example filename</span>

                <strong>
                  {automation.fileNameTemplate
                    .replace(
                      '{automation_name}',
                      automation.name ||
                        'Automation',
                    )
                    .replace(
                      '{yyyy-MM-dd}',
                      new Date()
                        .toISOString()
                        .slice(0, 10),
                    )
                    .replace(
                      '{yyyyMMdd}',
                      new Date()
                        .toISOString()
                        .slice(0, 10)
                        .replaceAll('-', ''),
                    )
                    .replace(
                      '{run_date}',
                      new Date().toLocaleDateString(),
                    )}
                  .
                  {automation.outputFormat}
                </strong>
              </div>
            </div>
          )}

          {currentStep === 'delivery' && (
            <div className="automation-designer-step">
              <div className="automation-step-heading">
                <span className="automation-eyebrow">
                  Step 4
                </span>

                <h3>
                  Configure delivery
                </h3>

                <p>
                  Send the output by email, save it
                  to a folder, or retain it without
                  delivery.
                </p>
              </div>

              <div className="automation-delivery-grid">
                {(
                  [
                    'none',
                    'email',
                    'folder',
                  ] as AutomationDeliveryMethod[]
                ).map((method) => (
                  <button
                    key={method}
                    type="button"
                    className={
                      automation.delivery.method ===
                      method
                        ? 'automation-delivery-card active'
                        : 'automation-delivery-card'
                    }
                    onClick={() =>
                      updateDelivery(
                        'method',
                        method,
                      )
                    }
                  >
                    <strong>
                      {method === 'none'
                        ? 'No Delivery'
                        : method
                            .charAt(0)
                            .toUpperCase() +
                          method.slice(1)}
                    </strong>

                    <span>
                      {method === 'none' &&
                        'Run and retain execution history only.'}

                      {method === 'email' &&
                        'Email the generated output.'}

                      {method === 'folder' &&
                        'Save the output to a local or network folder.'}
                    </span>
                  </button>
                ))}
              </div>

              {automation.delivery.method ===
                'email' && (
                <div className="automation-form-card">
                  <label>
                    <span>To</span>

                    <textarea
                      value={formatRecipientList(
                        automation.delivery
                          .recipients,
                      )}
                      onChange={(event) =>
                        updateDelivery(
                          'recipients',
                          parseRecipientList(
                            event.target.value,
                          ),
                        )
                      }
                      placeholder="josh@company.com, katie@company.com"
                      rows={3}
                    />
                  </label>

                  <label>
                    <span>CC</span>

                    <textarea
                      value={formatRecipientList(
                        automation.delivery
                          .ccRecipients,
                      )}
                      onChange={(event) =>
                        updateDelivery(
                          'ccRecipients',
                          parseRecipientList(
                            event.target.value,
                          ),
                        )
                      }
                      placeholder="accounting@company.com"
                      rows={2}
                    />
                  </label>

                  <label>
                    <span>Subject</span>

                    <input
                      type="text"
                      value={
                        automation.delivery.subject
                      }
                      onChange={(event) =>
                        updateDelivery(
                          'subject',
                          event.target.value,
                        )
                      }
                      placeholder="{automation_name} - {run_date}"
                    />
                  </label>

                  <label>
                    <span>Email message</span>

                    <textarea
                      value={
                        automation.delivery.message
                      }
                      onChange={(event) =>
                        updateDelivery(
                          'message',
                          event.target.value,
                        )
                      }
                      rows={6}
                    />
                  </label>

                  <label className="automation-checkbox-field">
                    <input
                      type="checkbox"
                      checked={
                        automation.delivery
                          .attachOutput
                      }
                      onChange={(event) =>
                        updateDelivery(
                          'attachOutput',
                          event.target.checked,
                        )
                      }
                    />

                    <span>
                      Attach the generated output
                      file
                    </span>
                  </label>
                </div>
              )}

              {automation.delivery.method ===
                'folder' && (
                <div className="automation-form-card">
                  <label>
                    <span>Output folder</span>

                    <input
                      type="text"
                      value={
                        automation.delivery
                          .outputFolder
                      }
                      onChange={(event) =>
                        updateDelivery(
                          'outputFolder',
                          event.target.value,
                        )
                      }
                      placeholder="C:\Reports\Scheduled"
                    />
                  </label>

                  <div className="automation-inline-notice">
                    Local folders and network paths
                    must be accessible to the
                    backend process running the
                    automation.
                  </div>
                </div>
              )}
            </div>
          )}

          {currentStep === 'review' && (
            <div className="automation-designer-step">
              <div className="automation-step-heading">
                <span className="automation-eyebrow">
                  Step 5
                </span>

                <h3>
                  Review the automation
                </h3>

                <p>
                  Confirm the workflow before
                  saving it as a draft or
                  activating it.
                </p>
              </div>

              <div className="automation-review-card">
                <div className="automation-review-title">
                  <span>
                    Automation
                  </span>

                  <strong>
                    {automation.name ||
                      'Untitled Automation'}
                  </strong>

                  <p>
                    {automation.description ||
                      'No description provided.'}
                  </p>
                </div>

                <div className="automation-review-grid">
                  <div>
                    <span>Source</span>

                    <strong>
                      {formatSourceSummary(
                        automation,
                      )}
                    </strong>
                  </div>

                  <div>
                    <span>Schedule</span>

                    <strong>
                      {formatScheduleSummary(
                        automation,
                      )}
                    </strong>
                  </div>

                  <div>
                    <span>Timezone</span>

                    <strong>
                      {
                        automation.schedule
                          .timezone
                      }
                    </strong>
                  </div>

                  <div>
                    <span>Output</span>

                    <strong>
                      {automation.outputFormat.toUpperCase()}
                    </strong>
                  </div>

                  <div>
                    <span>Filename</span>

                    <strong>
                      {
                        automation.fileNameTemplate
                      }
                    </strong>
                  </div>

                  <div>
                    <span>Delivery</span>

                    <strong>
                      {
                        automation.delivery
                          .method
                      }
                    </strong>
                  </div>
                </div>

                {automation.delivery.method ===
                  'email' && (
                  <div className="automation-review-section">
                    <span>
                      Email recipients
                    </span>

                    <strong>
                      {automation.delivery
                        .recipients.length > 0
                        ? automation.delivery.recipients.join(
                            ', ',
                          )
                        : 'No recipients entered'}
                    </strong>
                  </div>
                )}

                {automation.delivery.method ===
                  'folder' && (
                  <div className="automation-review-section">
                    <span>
                      Output folder
                    </span>

                    <strong>
                      {automation.delivery
                        .outputFolder ||
                        'No folder selected'}
                    </strong>
                  </div>
                )}
              </div>

              <div className="automation-review-actions">
                <button
                  type="button"
                  className="automation-secondary-button"
                  onClick={handleSaveDraft}
                >
                  Save Draft
                </button>

                <button
                  type="button"
                  className="automation-primary-button"
                  onClick={handleActivate}
                >
                  Save and Activate
                </button>
              </div>
            </div>
          )}

          <footer className="automation-designer-footer">
            <button
              type="button"
              className="automation-secondary-button"
              onClick={goToPreviousStep}
              disabled={currentStepIndex === 0}
            >
              Previous
            </button>

            <div className="automation-designer-footer-status">
              Step {currentStepIndex + 1} of{' '}
              {STEPS.length}
            </div>

            {currentStep !== 'review' ? (
              <button
                type="button"
                className="automation-primary-button"
                onClick={goToNextStep}
              >
                Continue
              </button>
            ) : (
              <button
                type="button"
                className="automation-secondary-button"
                onClick={onCancel}
              >
                Return to Automations
              </button>
            )}
          </footer>
        </div>
      </div>
    </section>
  )
}

export default AutomationDesigner