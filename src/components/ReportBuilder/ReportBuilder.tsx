import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

import ExportPanel from './ExportPanel'
import ReportCatalog from './ReportCatalog'
import ReportDesigner from './ReportDesigner'
import ReportFilters from './ReportFilters'
import ReportPreview from './ReportPreview'
import ReportSchedulePanel from './ReportSchedulePanel'

import {
  createReport,
  deleteReport,
  executeReportPreview,
  exportReportCsv,
  getReportSchedules,
  getReports,
  getSqlRuntimeCapabilities,
  updateReport,
} from '../../services/reportApi'

import type {
  ReportParameter,
  ReportParameterOption,
  ReportParameterType,
  SavedReport,
  SqlRuntimeCapabilities,
} from '../../services/reportApi'

import {
  createRequestLineage,
  resolveReportSql,
  validateReportDefinition,
} from '../../services/reportWorkflow'

import './ReportBuilder.css'

export type {
  ReportParameter,
  ReportParameterOption,
  ReportParameterType,
  SavedReport,
}

export type ReportColumn = {
  key: string
  label: string
}

export type ReportRow = Record<
  string,
  string | number | boolean | null
>

export type ReportExecutionResult = {
  columns: ReportColumn[]
  rows: ReportRow[]
  rowCount: number
  rowLimit: number
  executionTimeMs: number
  truncated: boolean
}

type ReportBuilderView =
  | 'catalog'
  | 'designer'
  | 'preview'

type Props = {
  initialReportId?: string
}

const createEmptyReport = (): SavedReport => {
  const now = new Date().toISOString()

  return {
    id: crypto.randomUUID(),
    name: 'Untitled Report',
    description: '',
    category: 'General',
    sql: '',
    parameters: [],
    database: 'ERP',
    outputFormat: 'xlsx',
    createdAt: now,
    updatedAt: now,
  }
}

function createParameterValues(
  report: SavedReport,
  currentValues: Record<string, string> = {},
  previousParameters: ReportParameter[] = [],
) {
  return report.parameters.reduce<Record<string, string>>(
    (values, parameter) => {
      const previousParameter = previousParameters.find(
        (candidate) => candidate.id === parameter.id,
      )

      const previousValue = previousParameter
        ? currentValues[previousParameter.name]
        : undefined

      values[parameter.name] =
        currentValues[parameter.name] ??
        previousValue ??
        parameter.defaultValue ??
        ''

      return values
    },
    {},
  )
}

function ReportBuilder({ initialReportId }: Props) {
  const [view, setView] =
    useState<ReportBuilderView>('catalog')
  const [savedReports, setSavedReports] = useState<
    SavedReport[]
  >([])
  const [activeReport, setActiveReport] =
    useState<SavedReport>(() => createEmptyReport())
  const [parameterValues, setParameterValues] = useState<
    Record<string, string>
  >({})
  const [executionResult, setExecutionResult] =
    useState<ReportExecutionResult | null>(null)
  const [sqlCapabilities, setSqlCapabilities] =
    useState<SqlRuntimeCapabilities | null>(null)
  const [isLoadingReports, setIsLoadingReports] =
    useState(true)
  const [isSavingReport, setIsSavingReport] =
    useState(false)
  const [isRunning, setIsRunning] = useState(false)
  const [isExporting, setIsExporting] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [successMessage, setSuccessMessage] = useState('')
  const [catalogErrorMessage, setCatalogErrorMessage] =
    useState('')
  const [sqlRuntimeError, setSqlRuntimeError] =
    useState('')
  const [loadAttempt, setLoadAttempt] = useState(0)
  const [previewLineage] = useState(createRequestLineage)
  const previewAbortControllerRef =
    useRef<AbortController | null>(null)

  const invalidatePreview = () => {
    previewLineage.invalidate()
    previewAbortControllerRef.current?.abort()
    previewAbortControllerRef.current = null
    setExecutionResult(null)
    setIsRunning(false)
  }

  useEffect(
    () => () => {
      previewLineage.invalidate()
      previewAbortControllerRef.current?.abort()
    },
    [previewLineage],
  )

  useEffect(() => {
    let isMounted = true

    const loadWorkspace = async () => {
      previewLineage.invalidate()
      previewAbortControllerRef.current?.abort()
      previewAbortControllerRef.current = null
      setExecutionResult(null)
      setIsRunning(false)
      setIsLoadingReports(true)
      setCatalogErrorMessage('')
      setSqlRuntimeError('')

      const [reportsResult, sqlResult] =
        await Promise.allSettled([
          getReports(),
          getSqlRuntimeCapabilities(),
        ])

      if (!isMounted) {
        return
      }

      if (reportsResult.status === 'fulfilled') {
        const reports = reportsResult.value
        setSavedReports(reports)

        const requestedReport = initialReportId
          ? reports.find(
              (report) => report.id === initialReportId,
            )
          : undefined

        if (requestedReport) {
          setActiveReport({
            ...requestedReport,
            parameters: [...requestedReport.parameters],
          })
          setParameterValues(
            createParameterValues(requestedReport),
          )
          setExecutionResult(null)
          setView('designer')
        }
      } else {
        setCatalogErrorMessage(
          reportsResult.reason instanceof Error
            ? reportsResult.reason.message
            : 'Unable to load saved reports.',
        )
      }

      if (sqlResult.status === 'fulfilled') {
        setSqlCapabilities(sqlResult.value)
      } else {
        setSqlCapabilities(null)
        setSqlRuntimeError(
          sqlResult.reason instanceof Error
            ? sqlResult.reason.message
            : 'The read-only ERP reporting connection is unavailable.',
        )
      }

      setIsLoadingReports(false)
    }

    void loadWorkspace()

    return () => {
      isMounted = false
    }
  }, [initialReportId, loadAttempt, previewLineage])

  const hasUnsavedChanges = useMemo(() => {
    const savedVersion = savedReports.find(
      (report) => report.id === activeReport.id,
    )

    if (!savedVersion) {
      return Boolean(
        activeReport.sql.trim() ||
          activeReport.name !== 'Untitled Report' ||
          activeReport.parameters.length,
      )
    }

    return (
      JSON.stringify(savedVersion) !==
      JSON.stringify(activeReport)
    )
  }, [activeReport, savedReports])

  const persistedActiveReport = savedReports.find(
    (report) => report.id === activeReport.id,
  )
  const isActiveReportSaved = Boolean(persistedActiveReport)
  const schedulePanelKey = `${activeReport.id}-${persistedActiveReport?.updatedAt ?? 'new'}`

  const confirmDiscardChanges = () =>
    !hasUnsavedChanges ||
    window.confirm(
      'Discard the unsaved changes to this report?',
    )

  const handleCreateReport = () => {
    if (!confirmDiscardChanges()) {
      return
    }

    invalidatePreview()
    setActiveReport(createEmptyReport())
    setParameterValues({})
    setErrorMessage('')
    setSuccessMessage('')
    setView('designer')
  }

  const handleOpenReport = (report: SavedReport) => {
    if (
      activeReport.id !== report.id &&
      !confirmDiscardChanges()
    ) {
      return
    }

    invalidatePreview()
    setActiveReport({
      ...report,
      parameters: [...report.parameters],
    })
    setParameterValues(createParameterValues(report))
    setErrorMessage('')
    setSuccessMessage('')
    setView('designer')
  }

  const handleActiveReportChange = (
    nextReport: SavedReport,
  ) => {
    invalidatePreview()
    setParameterValues((currentValues) =>
      createParameterValues(
        nextReport,
        currentValues,
        activeReport.parameters,
      ),
    )
    setActiveReport(nextReport)
    setSuccessMessage('')
  }

  const handleParameterValuesChange = (
    values: Record<string, string>,
  ) => {
    invalidatePreview()
    setParameterValues(values)
    setSuccessMessage('')
  }

  const handleDuplicateReport = async (
    report: SavedReport,
  ) => {
    const now = new Date().toISOString()
    const duplicatedReport: SavedReport = {
      ...report,
      id: crypto.randomUUID(),
      name: `${report.name} Copy`,
      createdAt: now,
      updatedAt: now,
      parameters: report.parameters.map((parameter) => ({
        ...parameter,
        options: parameter.options
          ? [...parameter.options]
          : undefined,
      })),
    }

    setIsSavingReport(true)
    setErrorMessage('')
    setSuccessMessage('')

    try {
      const savedDuplicate = await createReport(
        duplicatedReport,
      )

      setSavedReports((currentReports) => [
        savedDuplicate,
        ...currentReports,
      ])
      setActiveReport(savedDuplicate)
      setParameterValues(
        createParameterValues(savedDuplicate),
      )
      setExecutionResult(null)
      setSuccessMessage('Report duplicated and saved.')
      setView('designer')
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to duplicate the report.',
      )
    } finally {
      setIsSavingReport(false)
    }
  }

  const handleDeleteReport = async (
    reportId: string,
  ): Promise<boolean> => {
    setErrorMessage('')
    setSuccessMessage('')

    try {
      const schedules = await getReportSchedules(reportId)

      if (schedules.length) {
        throw new Error(
          `Delete the ${schedules.length} connected schedule${schedules.length === 1 ? '' : 's'} before deleting this report.`,
        )
      }

      await deleteReport(reportId)
      setSavedReports((currentReports) =>
        currentReports.filter(
          (report) => report.id !== reportId,
        ),
      )

      if (activeReport.id === reportId) {
        setActiveReport(createEmptyReport())
        setParameterValues({})
        setExecutionResult(null)
        setView('catalog')
      }

      setSuccessMessage('Report deleted.')
      return true
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to delete the report.',
      )
      return false
    }
  }

  const handleSaveReport = async () => {
    const validation = validateReportDefinition(activeReport)

    if (validation.errors.length) {
      setErrorMessage(validation.errors[0])
      return
    }

    const reportToSave: SavedReport = {
      ...activeReport,
      name: activeReport.name.trim(),
      category: activeReport.category.trim(),
      sql: activeReport.sql.trim(),
    }
    const existingReport = savedReports.find(
      (report) => report.id === reportToSave.id,
    )

    setIsSavingReport(true)
    setErrorMessage('')
    setSuccessMessage('')

    try {
      const savedReport = existingReport
        ? await updateReport(
            reportToSave.id,
            reportToSave,
          )
        : await createReport(reportToSave)

      setSavedReports((currentReports) => {
        const reportExists = currentReports.some(
          (report) => report.id === savedReport.id,
        )

        return reportExists
          ? currentReports.map((report) =>
              report.id === savedReport.id
                ? savedReport
                : report,
            )
          : [savedReport, ...currentReports]
      })
      setActiveReport(savedReport)
      setSuccessMessage(
        validation.warnings.length
          ? `Report saved. ${validation.warnings[0]}`
          : 'Report saved.',
      )
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to save the report.',
      )
    } finally {
      setIsSavingReport(false)
    }
  }

  const validateExecution = () => {
    if (!sqlCapabilities) {
      setErrorMessage(
        sqlRuntimeError ||
          'The read-only ERP reporting connection is unavailable.',
      )
      return false
    }

    try {
      resolveReportSql(activeReport, parameterValues)
      return true
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'The report definition is invalid.',
      )
      return false
    }
  }

  const handleRunPreview = async () => {
    if (!validateExecution() || !sqlCapabilities) {
      return
    }

    previewAbortControllerRef.current?.abort()
    const requestId = previewLineage.begin()
    const abortController = new AbortController()
    previewAbortControllerRef.current = abortController
    setIsRunning(true)
    setErrorMessage('')
    setSuccessMessage('')

    try {
      const response = await executeReportPreview(
        activeReport,
        parameterValues,
        Math.min(250, sqlCapabilities.maximumLimit),
        abortController.signal,
      )

      if (!previewLineage.isCurrent(requestId)) {
        return
      }

      setExecutionResult({
        columns: response.columns.map((column) => ({
          key: column,
          label: column,
        })),
        rows: response.rows,
        rowCount: response.rowCount,
        rowLimit: response.rowLimit,
        executionTimeMs: response.executionTimeMs,
        truncated: response.truncated,
      })
      setView('preview')
    } catch (error) {
      if (
        !previewLineage.isCurrent(requestId) ||
        abortController.signal.aborted
      ) {
        return
      }

      setExecutionResult(null)
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to execute the report.',
      )
    } finally {
      if (previewLineage.isCurrent(requestId)) {
        if (
          previewAbortControllerRef.current ===
          abortController
        ) {
          previewAbortControllerRef.current = null
        }
        setIsRunning(false)
      }
    }
  }

  const handleExport = async () => {
    if (!validateExecution() || !sqlCapabilities) {
      return
    }

    setIsExporting(true)
    setErrorMessage('')
    setSuccessMessage('')

    try {
      const { blob, contentDisposition } =
        await exportReportCsv(
          activeReport,
          parameterValues,
          sqlCapabilities.maximumLimit,
        )
      const filenameMatch = contentDisposition?.match(
        /filename="?([^";]+)"?/i,
      )
      const safeReportName = activeReport.name
        .trim()
        .replace(/[^a-z0-9_-]+/gi, '_')
      const filename =
        filenameMatch?.[1] ??
        `${safeReportName || 'report'}.csv`
      const fileUrl = URL.createObjectURL(blob)
      const downloadLink = document.createElement('a')

      downloadLink.href = fileUrl
      downloadLink.download = filename
      document.body.appendChild(downloadLink)
      downloadLink.click()
      downloadLink.remove()
      URL.revokeObjectURL(fileUrl)
      setSuccessMessage(
        `CSV export downloaded. The server limit is ${sqlCapabilities.maximumLimit.toLocaleString()} rows.`,
      )
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to export the report.',
      )
    } finally {
      setIsExporting(false)
    }
  }

  const handleReturnToCatalog = () => {
    if (!confirmDiscardChanges()) {
      return
    }

    invalidatePreview()
    setErrorMessage('')
    setSuccessMessage('')
    setView('catalog')
  }

  return (
    <div className="report-builder-page">
      <header className="report-builder-header">
        <div>
          <span className="report-builder-eyebrow">
            Reporting workspace
          </span>
          <h1>Report Builder</h1>
          <p>
            Design and save reusable read-only reports, preview ERP results,
            download controlled CSV exports, and connect saved reports to a
            recurring schedule.
          </p>
        </div>

        <div className="report-builder-header-actions">
          {view !== 'catalog' && (
            <button
              type="button"
              className="report-secondary-button"
              onClick={handleReturnToCatalog}
            >
              Report Catalog
            </button>
          )}
          <button
            type="button"
            className="report-primary-button"
            onClick={handleCreateReport}
          >
            New Report
          </button>
        </div>
      </header>

      <nav className="report-builder-tabs" aria-label="Report Builder views">
        <button
          type="button"
          className={view === 'catalog' ? 'active' : undefined}
          onClick={handleReturnToCatalog}
        >
          Catalog
        </button>
        <button
          type="button"
          className={view === 'designer' ? 'active' : undefined}
          onClick={() => setView('designer')}
        >
          Designer
        </button>
        <button
          type="button"
          className={view === 'preview' ? 'active' : undefined}
          onClick={() => setView('preview')}
          disabled={!executionResult}
        >
          Preview
        </button>
      </nav>

      {errorMessage && (
        <div className="report-builder-error" role="alert">
          <div>
            <strong>Report Builder error</strong>
            <span>{errorMessage}</span>
          </div>
          <button
            type="button"
            onClick={() => setErrorMessage('')}
            aria-label="Dismiss error"
          >
            ×
          </button>
        </div>
      )}

      {successMessage && (
        <div className="report-builder-success" role="status">
          <span>{successMessage}</span>
          <button
            type="button"
            onClick={() => setSuccessMessage('')}
            aria-label="Dismiss message"
          >
            ×
          </button>
        </div>
      )}

      {sqlRuntimeError && !isLoadingReports && (
        <div className="report-builder-runtime-warning" role="status">
          <div>
            <strong>Design and catalog are available</strong>
            <span>
              {sqlRuntimeError} Preview and direct export are paused.
            </span>
          </div>
          <button
            type="button"
            className="report-secondary-button"
            onClick={() =>
              setLoadAttempt((attempt) => attempt + 1)
            }
          >
            Retry Connection
          </button>
        </div>
      )}

      {isLoadingReports && (
        <div className="report-builder-loading">
          Loading the report catalog and read-only ERP connection…
        </div>
      )}

      {catalogErrorMessage && !isLoadingReports && (
        <div className="report-load-failure" role="alert">
          <strong>Saved reports could not be loaded</strong>
          <span>{catalogErrorMessage}</span>
          <button
            type="button"
            className="report-primary-button"
            onClick={() =>
              setLoadAttempt((attempt) => attempt + 1)
            }
          >
            Retry Catalog
          </button>
        </div>
      )}

      {view === 'catalog' &&
        !isLoadingReports &&
        !catalogErrorMessage && (
          <ReportCatalog
            reports={savedReports}
            isBusy={isSavingReport}
            onCreate={handleCreateReport}
            onOpen={handleOpenReport}
            onDuplicate={handleDuplicateReport}
            onDelete={handleDeleteReport}
          />
        )}

      {view === 'designer' && (
        <div className="report-builder-workspace">
          <div className="report-builder-main-column">
            <ReportDesigner
              report={activeReport}
              hasUnsavedChanges={hasUnsavedChanges}
              isRunning={isRunning}
              isSaving={isSavingReport}
              canRun={Boolean(sqlCapabilities)}
              onChange={handleActiveReportChange}
              onSave={handleSaveReport}
              onRunPreview={handleRunPreview}
            />
          </div>

          <aside className="report-builder-side-column">
            <ReportFilters
              parameters={activeReport.parameters}
              values={parameterValues}
              onChange={handleParameterValuesChange}
            />
            <ExportPanel
              reportName={activeReport.name}
              isExporting={isExporting}
              canExport={Boolean(
                activeReport.sql.trim() && sqlCapabilities,
              )}
              maximumRows={
                sqlCapabilities?.maximumLimit ?? null
              }
              onExport={handleExport}
            />
            <ReportSchedulePanel
              key={schedulePanelKey}
              report={activeReport}
              isSaved={isActiveReportSaved}
              hasUnsavedChanges={hasUnsavedChanges}
            />
          </aside>
        </div>
      )}

      {view === 'preview' && (
        <div className="report-builder-preview-layout">
          <ReportPreview
            key={`${activeReport.id}-${executionResult?.executionTimeMs ?? 0}`}
            reportName={activeReport.name}
            result={executionResult}
            isRunning={isRunning}
            exportLimit={
              sqlCapabilities?.maximumLimit ?? null
            }
            onRefresh={handleRunPreview}
          />
          <div className="report-builder-preview-sidebar">
            <ExportPanel
              reportName={activeReport.name}
              isExporting={isExporting}
              canExport={Boolean(
                activeReport.sql.trim() && sqlCapabilities,
              )}
              maximumRows={
                sqlCapabilities?.maximumLimit ?? null
              }
              onExport={handleExport}
            />
            <ReportSchedulePanel
              key={schedulePanelKey}
              report={activeReport}
              isSaved={isActiveReportSaved}
              hasUnsavedChanges={hasUnsavedChanges}
            />
          </div>
        </div>
      )}
    </div>
  )
}

export default ReportBuilder
