import {
  useEffect,
  useState,
} from 'react'

import AutomationCatalog from './AutomationCatalog'
import AutomationDashboard from './AutomationDashboard'
import AutomationDesigner from './AutomationDesigner'
import AutomationDetail from './AutomationDetail'
import ExecutionHistory from './ExecutionHistory'

import './AutomationCenter.css'

export type AutomationStatus =
  | 'active'
  | 'paused'
  | 'draft'
  | 'error'

export type AutomationFrequency =
  | 'manual'
  | 'daily'
  | 'weekly'
  | 'monthly'
  | 'custom'

export type AutomationOutputFormat =
  | 'csv'
  | 'xlsx'
  | 'pdf'

export type AutomationDeliveryMethod =
  | 'email'
  | 'folder'
  | 'none'

export type AutomationSchedule = {
  frequency: AutomationFrequency
  time: string
  daysOfWeek: number[]
  dayOfMonth: number | null
  cronExpression: string
  timezone: string
}

export type AutomationDelivery = {
  method: AutomationDeliveryMethod
  recipients: string[]
  ccRecipients: string[]
  subject: string
  message: string
  outputFolder: string
  attachOutput: boolean
}

export type AutomationSourceType =
  | 'report'
  | 'sql'
  | 'powershell'
  | 'python'

export type ExecutionStatus =
  | 'running'
  | 'success'
  | 'warning'
  | 'failed'
  | 'cancelled'

export type AutomationDefinition = {
  id: string
  name: string
  description: string
  category: string
  status: AutomationStatus

  sourceType: AutomationSourceType
  reportId: string
  reportName: string
  sql: string
  scriptPath: string

  outputFormat: AutomationOutputFormat
  fileNameTemplate: string

  schedule: AutomationSchedule
  delivery: AutomationDelivery

  createdAt: string
  updatedAt: string
  lastRunAt: string | null
  nextRunAt: string | null
  lastRunStatus: ExecutionStatus | null
}

export type AutomationExecution = {
  id: string
  automationId: string
  automationName: string

  status: ExecutionStatus

  startedAt: string
  completedAt: string | null

  durationMs: number | null
  rowCount: number | null

  outputFileName: string
  outputFilePath: string

  message: string
  errorDetails: string

  triggeredBy:
    | 'schedule'
    | 'manual'
    | 'retry'
}

type AutomationView =
  | 'dashboard'
  | 'catalog'
  | 'designer'
  | 'detail'
  | 'history'

const AUTOMATION_STORAGE_KEY =
  'enterprise-ai-workbench.automations'

const EXECUTION_STORAGE_KEY =
  'enterprise-ai-workbench.automation-executions'

const AUTOMATION_API_BASE =
  'http://127.0.0.1:8000/api/v1/automations'

function createEmptyAutomation(): AutomationDefinition {
  const now = new Date().toISOString()

  return {
    id: crypto.randomUUID(),

    name: 'Untitled Automation',
    description: '',
    category: 'General',
    status: 'draft',

    sourceType: 'report',
    reportId: '',
    reportName: '',
    sql: '',
    scriptPath: '',

    outputFormat: 'xlsx',
    fileNameTemplate:
      '{automation_name}_{yyyy-MM-dd}',

    schedule: {
      frequency: 'manual',
      time: '07:00',
      daysOfWeek: [1],
      dayOfMonth: 1,
      cronExpression: '',
      timezone:
        Intl.DateTimeFormat()
          .resolvedOptions()
          .timeZone ||
        'America/New_York',
    },

    delivery: {
      method: 'none',
      recipients: [],
      ccRecipients: [],
      subject:
        '{automation_name} - {run_date}',
      message:
        'The scheduled automation has completed. See the attached output.',
      outputFolder: '',
      attachOutput: true,
    },

    createdAt: now,
    updatedAt: now,

    lastRunAt: null,
    nextRunAt: null,
    lastRunStatus: null,
  }
}

function cloneAutomation(
  automation: AutomationDefinition,
): AutomationDefinition {
  return {
    ...automation,

    schedule: {
      ...automation.schedule,
      daysOfWeek: [
        ...automation.schedule.daysOfWeek,
      ],
    },

    delivery: {
      ...automation.delivery,
      recipients: [
        ...automation.delivery.recipients,
      ],
      ccRecipients: [
        ...automation.delivery.ccRecipients,
      ],
    },
  }
}

function loadAutomations(): AutomationDefinition[] {
  try {
    const storedValue =
      window.localStorage.getItem(
        AUTOMATION_STORAGE_KEY,
      )

    if (!storedValue) {
      return []
    }

    const parsedValue: unknown =
      JSON.parse(storedValue)

    if (!Array.isArray(parsedValue)) {
      return []
    }

    return parsedValue as AutomationDefinition[]
  } catch {
    return []
  }
}

function loadExecutions(): AutomationExecution[] {
  try {
    const storedValue =
      window.localStorage.getItem(
        EXECUTION_STORAGE_KEY,
      )

    if (!storedValue) {
      return []
    }

    const parsedValue: unknown =
      JSON.parse(storedValue)

    if (!Array.isArray(parsedValue)) {
      return []
    }

    return parsedValue as AutomationExecution[]
  } catch {
    return []
  }
}

function AutomationCenter() {
  const [
    view,
    setView,
  ] = useState<AutomationView>(
    'dashboard',
  )

  const [
    automations,
    setAutomations,
  ] = useState<
    AutomationDefinition[]
  >(() => loadAutomations())

  const [
    executions,
    setExecutions,
  ] = useState<
    AutomationExecution[]
  >(() => loadExecutions())

  const [
    activeAutomation,
    setActiveAutomation,
  ] =
    useState<AutomationDefinition>(
      () => createEmptyAutomation(),
    )

  const [
    selectedExecution,
    setSelectedExecution,
  ] =
    useState<AutomationExecution | null>(
      null,
    )

  const [
    isRunning,
    setIsRunning,
  ] = useState(false)

  const [
    errorMessage,
    setErrorMessage,
  ] = useState('')

  useEffect(() => {
    let cancelled = false

    const refreshAutomationData =
      async () => {
        try {
          const [
            automationResponse,
            executionResponse,
          ] = await Promise.all([
            fetch(AUTOMATION_API_BASE),
            fetch(
              `${AUTOMATION_API_BASE}/executions?limit=250`,
            ),
          ])

          if (
            !automationResponse.ok ||
            !executionResponse.ok
          ) {
            throw new Error(
              'Unable to load Automation Center data.',
            )
          }

          const automationPayload =
            await automationResponse.json()

          const executionPayload =
            await executionResponse.json()

          if (!cancelled) {
            setAutomations(
              automationPayload.automations ?? [],
            )
            setExecutions(
              executionPayload.executions ?? [],
            )
          }
        } catch (error) {
          if (!cancelled) {
            setErrorMessage(
              error instanceof Error
                ? error.message
                : 'Unable to load Automation Center data.',
            )
          }
        }
      }

    void refreshAutomationData()

    const refreshTimer =
      window.setInterval(
        () => {
          void refreshAutomationData()
        },
        15000,
      )

    return () => {
      cancelled = true
      window.clearInterval(
        refreshTimer,
      )
    }
  }, [])

  const handleCreateAutomation = () => {
    setActiveAutomation(
      createEmptyAutomation(),
    )

    setSelectedExecution(null)
    setErrorMessage('')
    setView('designer')
  }

  const handleOpenAutomation = (
    automation: AutomationDefinition,
  ) => {
    setActiveAutomation(
      cloneAutomation(automation),
    )

    setSelectedExecution(null)
    setErrorMessage('')
    setView('detail')
  }

  const handleEditAutomation = (
    automation: AutomationDefinition,
  ) => {
    setActiveAutomation(
      cloneAutomation(automation),
    )

    setSelectedExecution(null)
    setErrorMessage('')
    setView('designer')
  }

  const handleSaveAutomation = (
    automationOverride?: AutomationDefinition,
  ) => {
    const automationToValidate =
      automationOverride ??
      activeAutomation

    const trimmedName =
      automationToValidate.name.trim()

    if (!trimmedName) {
      setErrorMessage(
        'Enter an automation name before saving.',
      )

      return
    }

    if (
      automationToValidate.sourceType ===
        'report' &&
      !automationToValidate.reportId
    ) {
      setErrorMessage(
        'Select a saved report for this automation.',
      )

      return
    }

    if (
      automationToValidate.sourceType ===
        'sql' &&
      !automationToValidate.sql.trim()
    ) {
      setErrorMessage(
        'Enter SQL for this automation.',
      )

      return
    }

    if (
      (
        [
          'powershell',
          'python',
        ] as AutomationSourceType[]
      ).includes(
        automationToValidate.sourceType,
      ) &&
      !automationToValidate.scriptPath.trim()
    ) {
      setErrorMessage(
        'Enter a script path for this automation.',
      )

      return
    }

    const now =
      new Date().toISOString()

    const automationToSave: AutomationDefinition =
      {
        ...cloneAutomation(
          automationToValidate,
        ),

        name: trimmedName,
        updatedAt: now,
      }

    setAutomations(
      (currentAutomations) => {
        const exists =
          currentAutomations.some(
            (automation) =>
              automation.id ===
              automationToSave.id,
          )

        if (!exists) {
          return [
            automationToSave,
            ...currentAutomations,
          ]
        }

        return currentAutomations.map(
          (automation) =>
            automation.id ===
            automationToSave.id
              ? automationToSave
              : automation,
        )
      },
    )

    void fetch(
      AUTOMATION_API_BASE,
      {
        method: 'POST',
        headers: {
          'Content-Type':
            'application/json',
        },
        body: JSON.stringify(
          automationToSave,
        ),
      },
    )
      .then(async (response) => {
        if (!response.ok) {
          const payload =
            await response
              .json()
              .catch(() => null)

          throw new Error(
            payload?.detail ??
              'Unable to save automation.',
          )
        }

        const payload =
          await response.json()

        const savedAutomation =
          payload.automation as AutomationDefinition

        setAutomations(
          (currentAutomations) =>
            currentAutomations.map(
              (item) =>
                item.id ===
                savedAutomation.id
                  ? savedAutomation
                  : item,
            ),
        )

        setActiveAutomation(
          savedAutomation,
        )
      })
      .catch((error) => {
        setErrorMessage(
          error instanceof Error
            ? error.message
            : 'Unable to save automation.',
        )
      })

    setActiveAutomation(
      automationToSave,
    )

    setErrorMessage('')
    setView('detail')
  }

  const handleDuplicateAutomation = (
    automation: AutomationDefinition,
  ) => {
    const now =
      new Date().toISOString()

    const duplicatedAutomation: AutomationDefinition =
      {
        ...cloneAutomation(automation),

        id: crypto.randomUUID(),
        name: `${automation.name} Copy`,
        status: 'draft',

        createdAt: now,
        updatedAt: now,

        lastRunAt: null,
        nextRunAt: null,
        lastRunStatus: null,
      }

    setAutomations(
      (currentAutomations) => [
        duplicatedAutomation,
        ...currentAutomations,
      ],
    )

    setActiveAutomation(
      duplicatedAutomation,
    )

    setSelectedExecution(null)
    setErrorMessage('')
    setView('designer')
  }

  const handleDeleteAutomation = (
    automationId: string,
  ) => {
    void fetch(
      `${AUTOMATION_API_BASE}/${automationId}`,
      {
        method: 'DELETE',
      },
    ).catch(() => {
      setErrorMessage(
        'Unable to delete automation from the backend.',
      )
    })
    setAutomations(
      (currentAutomations) =>
        currentAutomations.filter(
          (automation) =>
            automation.id !==
            automationId,
        ),
    )

    if (
      activeAutomation.id ===
      automationId
    ) {
      setActiveAutomation(
        createEmptyAutomation(),
      )

      setView('catalog')
    }
  }

  const handleToggleStatus = async (
    automationId: string,
  ) => {
    const automation = automations.find(
      (item) => item.id === automationId,
    )

    if (!automation) {
      setErrorMessage(
        'The selected automation is no longer available.',
      )
      return
    }

    const nextStatus: AutomationStatus =
      automation.status === 'active'
        ? 'paused'
        : 'active'

    const updatedAutomation: AutomationDefinition = {
      ...cloneAutomation(automation),
      status: nextStatus,
      updatedAt: new Date().toISOString(),
    }

    setErrorMessage('')

    try {
      const response = await fetch(
        AUTOMATION_API_BASE,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(updatedAutomation),
        },
      )
      const payload = await response
        .json()
        .catch(() => null)

      if (!response.ok) {
        throw new Error(
          payload?.detail ??
            'Unable to update automation status.',
        )
      }

      const savedAutomation =
        payload?.automation as
          | AutomationDefinition
          | undefined

      if (!savedAutomation) {
        throw new Error(
          'The backend did not return the saved automation.',
        )
      }

      setAutomations((currentAutomations) =>
        currentAutomations.map((item) =>
          item.id === automationId
            ? savedAutomation
            : item,
        ),
      )

      if (activeAutomation.id === automationId) {
        setActiveAutomation(savedAutomation)
      }
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to update automation status.',
      )
    }
  }

  const handleRunNow = async (
    automation: AutomationDefinition,
    triggeredBy:
      | 'manual'
      | 'retry' = 'manual',
  ) => {
    if (isRunning) {
      return
    }

    setIsRunning(true)
    setErrorMessage('')

    const executionId =
      crypto.randomUUID()

    const startedAt =
      new Date().toISOString()

    const pendingExecution: AutomationExecution =
      {
        id: executionId,

        automationId:
          automation.id,

        automationName:
          automation.name,

        status: 'running',

        startedAt,
        completedAt: null,

        durationMs: null,
        rowCount: null,

        outputFileName: '',
        outputFilePath: '',

        message:
          'Automation execution started.',

        errorDetails: '',

        triggeredBy,
      }

    setExecutions(
      (currentExecutions) => [
        pendingExecution,
        ...currentExecutions,
      ],
    )

    const startedPerformance =
      performance.now()

    try {
      const response = await fetch(
        'http://127.0.0.1:8000/api/v1/automations/run',
        {
          method: 'POST',

          headers: {
            'Content-Type':
              'application/json',
          },

          body: JSON.stringify({
            automation_id:
              automation.id,

            automation,

            triggered_by:
              triggeredBy,
          }),
        },
      )

      if (!response.ok) {
        const errorPayload = await response
          .json()
          .catch(() => null)

        throw new Error(
          errorPayload?.detail ??
            errorPayload?.message ??
            `Automation failed with status ${response.status}.`,
        )
      }

      const responseData: {
        status?: string
        duration_ms?: number
        row_count?: number | null
        output_file_name?: string
        output_file_path?: string
        message?: string
      } = await response.json()

      const completedAt =
        new Date().toISOString()

      const durationMs =
        responseData.duration_ms ??
        Math.round(
          performance.now() -
            startedPerformance,
        )

      const executionStatus: ExecutionStatus =
        responseData.status ===
        'warning'
          ? 'warning'
          : 'success'

      setExecutions(
        (currentExecutions) =>
          currentExecutions.map(
            (execution) =>
              execution.id ===
              executionId
                ? {
                    ...execution,

                    status:
                      executionStatus,

                    completedAt,
                    durationMs,

                    rowCount:
                      responseData.row_count ??
                      null,

                    outputFileName:
                      responseData.output_file_name ??
                      '',

                    outputFilePath:
                      responseData.output_file_path ??
                      '',

                    message:
                      responseData.message ??
                      'Automation completed successfully.',

                    errorDetails: '',
                  }
                : execution,
          ),
      )

      const updatedAutomation: AutomationDefinition =
        {
          ...automation,

          lastRunAt: completedAt,
          lastRunStatus:
            executionStatus,

          updatedAt: completedAt,
        }

      setAutomations(
        (currentAutomations) =>
          currentAutomations.map(
            (item) =>
              item.id ===
              automation.id
                ? updatedAutomation
                : item,
          ),
      )

      if (
        activeAutomation.id ===
        automation.id
      ) {
        setActiveAutomation(
          updatedAutomation,
        )
      }
    } catch (error) {
      const completedAt =
        new Date().toISOString()

      const message =
        error instanceof Error
          ? error.message
          : 'Automation execution failed.'

      const durationMs =
        Math.round(
          performance.now() -
            startedPerformance,
        )

      setExecutions(
        (currentExecutions) =>
          currentExecutions.map(
            (execution) =>
              execution.id ===
              executionId
                ? {
                    ...execution,

                    status: 'failed',

                    completedAt,
                    durationMs,

                    message:
                      'Automation execution failed.',

                    errorDetails:
                      message,
                  }
                : execution,
          ),
      )

      setAutomations(
        (currentAutomations) =>
          currentAutomations.map(
            (item) =>
              item.id ===
              automation.id
                ? {
                    ...item,

                    lastRunAt:
                      completedAt,

                    lastRunStatus:
                      'failed',

                    updatedAt:
                      completedAt,
                  }
                : item,
          ),
      )

      if (
        activeAutomation.id ===
        automation.id
      ) {
        setActiveAutomation(
          (currentAutomation) => ({
            ...currentAutomation,

            lastRunAt:
              completedAt,

            lastRunStatus:
              'failed',

            updatedAt:
              completedAt,
          }),
        )
      }

      setErrorMessage(message)
    } finally {
      setIsRunning(false)
    }
  }

  const handleOpenExecution = (
    execution: AutomationExecution,
  ) => {
    setSelectedExecution(
      execution,
    )

    setView('history')
  }

  const handleRetryExecution = (
    execution: AutomationExecution,
  ) => {
    const automation =
      automations.find(
        (item) =>
          item.id ===
          execution.automationId,
      )

    if (!automation) {
      setErrorMessage(
        'The automation associated with this execution no longer exists.',
      )

      return
    }

    void handleRunNow(
      automation,
      'retry',
    )
  }

  const handleClearExecutionHistory =
    () => {
      void fetch(
        `${AUTOMATION_API_BASE}/executions`,
        {
          method: 'DELETE',
        },
      ).catch(() => {
        setErrorMessage(
          'Unable to clear execution history.',
        )
      })

      setExecutions([])
      setSelectedExecution(null)
    }

  const handleViewDashboard = () => {
    setSelectedExecution(null)
    setErrorMessage('')
    setView('dashboard')
  }

  const handleViewCatalog = () => {
    setSelectedExecution(null)
    setErrorMessage('')
    setView('catalog')
  }

  const handleViewHistory = () => {
    setSelectedExecution(null)
    setErrorMessage('')
    setView('history')
  }

  return (
    <div className="automation-center-page">
      <header className="automation-center-header">
        <div>
          <span className="automation-eyebrow">
            Workflow operations
          </span>

          <h1>
            Automation Center
          </h1>

          <p>
            Schedule reports, run
            scripts, monitor executions,
            and manage automated
            delivery.
          </p>
        </div>

        <div className="automation-header-actions">
          <button
            type="button"
            className="automation-secondary-button"
            onClick={
              handleViewHistory
            }
          >
            Execution History
          </button>

          <button
            type="button"
            className="automation-primary-button"
            onClick={
              handleCreateAutomation
            }
          >
            New Automation
          </button>
        </div>
      </header>

      <nav className="automation-tabs">
        <button
          type="button"
          className={
            view === 'dashboard'
              ? 'active'
              : undefined
          }
          onClick={
            handleViewDashboard
          }
        >
          Dashboard
        </button>

        <button
          type="button"
          className={
            view === 'catalog'
              ? 'active'
              : undefined
          }
          onClick={
            handleViewCatalog
          }
        >
          Automations
        </button>

        <button
          type="button"
          className={
            view === 'history'
              ? 'active'
              : undefined
          }
          onClick={
            handleViewHistory
          }
        >
          Execution History
        </button>

        {(
          view === 'designer' ||
          view === 'detail'
        ) && (
          <button
            type="button"
            className="active"
          >
            {view === 'designer'
              ? 'Automation Designer'
              : 'Automation Details'}
          </button>
        )}
      </nav>

      {errorMessage && (
        <div className="automation-error-banner">
          <div>
            <strong>
              Automation Center error
            </strong>

            <span>
              {errorMessage}
            </span>
          </div>

          <button
            type="button"
            aria-label="Dismiss error"
            onClick={() =>
              setErrorMessage('')
            }
          >
            ×
          </button>
        </div>
      )}

      {view === 'dashboard' && (
        <AutomationDashboard
          automations={automations}
          executions={executions}
          isRunning={isRunning}
          onCreate={
            handleCreateAutomation
          }
          onOpenAutomation={
            handleOpenAutomation
          }
          onOpenExecution={
            handleOpenExecution
          }
          onRunNow={
            handleRunNow
          }
          onViewAll={
            handleViewCatalog
          }
          onViewHistory={
            handleViewHistory
          }
        />
      )}

      {view === 'catalog' && (
        <AutomationCatalog
          automations={automations}
          isRunning={isRunning}
          onCreate={
            handleCreateAutomation
          }
          onOpen={
            handleOpenAutomation
          }
          onEdit={
            handleEditAutomation
          }
          onDuplicate={
            handleDuplicateAutomation
          }
          onDelete={
            handleDeleteAutomation
          }
          onToggleStatus={
            handleToggleStatus
          }
          onRunNow={
            handleRunNow
          }
        />
      )}

      {view === 'designer' && (
        <AutomationDesigner
          automation={
            activeAutomation
          }
          onChange={
            setActiveAutomation
          }
          onSave={
            handleSaveAutomation
          }
          onCancel={
            handleViewCatalog
          }
        />
      )}

      {view === 'detail' && (
        <AutomationDetail
          automation={
            activeAutomation
          }
          executions={executions.filter(
            (execution) =>
              execution.automationId ===
              activeAutomation.id,
          )}
          isRunning={isRunning}
          onEdit={() =>
            handleEditAutomation(
              activeAutomation,
            )
          }
          onRunNow={() =>
            void handleRunNow(
              activeAutomation,
            )
          }
          onToggleStatus={() =>
            handleToggleStatus(
              activeAutomation.id,
            )
          }
          onOpenExecution={
            handleOpenExecution
          }
          onBack={
            handleViewCatalog
          }
        />
      )}

      {view === 'history' && (
        <ExecutionHistory
          executions={executions}
          automations={automations}
          isRunning={isRunning}
          onOpenExecution={
            handleOpenExecution
          }
          onRetryExecution={
            handleRetryExecution
          }
          onRunAutomation={
            handleRunNow
          }
          onClearHistory={
            handleClearExecutionHistory
          }
          onBack={
            handleViewDashboard
          }
        />
      )}

      {selectedExecution && (
        <input
          type="hidden"
          value={
            selectedExecution.id
          }
          readOnly
        />
      )}
    </div>
  )
}

export default AutomationCenter
