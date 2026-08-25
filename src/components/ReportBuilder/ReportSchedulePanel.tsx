import {
  useEffect,
  useMemo,
  useState,
} from 'react'

import {
  deleteReportSchedule,
  getReportSchedules,
  saveReportSchedule,
  setReportScheduleStatus,
} from '../../services/reportApi'

import type {
  ReportSchedule,
  ReportScheduleFrequency,
  SavedReport,
} from '../../services/reportApi'

import { reportCanBeScheduled } from '../../services/reportWorkflow'

type ReportSchedulePanelProps = {
  report: SavedReport
  isSaved: boolean
  hasUnsavedChanges: boolean
}

type ScheduleDraft = {
  id?: string
  name: string
  frequency: ReportScheduleFrequency
  time: string
  dayOfWeek: number
  dayOfMonth: number
  outputFormat: 'csv' | 'xlsx'
}

const WEEKDAYS = [
  'Sunday',
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
]

function createDraft(report: SavedReport): ScheduleDraft {
  return {
    name: `${report.name.trim() || 'Report'} Schedule`,
    frequency: 'daily',
    time: '07:00',
    dayOfWeek: 0,
    dayOfMonth: 1,
    outputFormat:
      report.outputFormat === 'csv' ? 'csv' : 'xlsx',
  }
}

function formatDateTime(value: string | null) {
  if (!value) {
    return 'Not scheduled'
  }

  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return value
  }

  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  }).format(date)
}

function scheduleSummary(schedule: ReportSchedule) {
  const time = schedule.schedule.time

  if (schedule.schedule.frequency === 'weekly') {
    const day =
      WEEKDAYS[schedule.schedule.daysOfWeek[0] ?? 0]

    return `Weekly on ${day} at ${time}`
  }

  if (schedule.schedule.frequency === 'monthly') {
    return `Monthly on day ${schedule.schedule.dayOfMonth ?? 1} at ${time}`
  }

  return `Daily at ${time}`
}

function ReportSchedulePanel({
  report,
  isSaved,
  hasUnsavedChanges,
}: ReportSchedulePanelProps) {
  const [schedules, setSchedules] = useState<
    ReportSchedule[]
  >([])
  const [draft, setDraft] = useState<ScheduleDraft>(() =>
    createDraft(report),
  )
  const [isLoading, setIsLoading] = useState(isSaved)
  const [isSaving, setIsSaving] = useState(false)
  const [busyScheduleId, setBusyScheduleId] =
    useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [successMessage, setSuccessMessage] = useState('')
  const timezone = useMemo(
    () =>
      Intl.DateTimeFormat().resolvedOptions().timeZone ||
      'America/New_York',
    [],
  )

  const supportsScheduledParameters =
    reportCanBeScheduled(report)

  const canSaveSchedule =
    isSaved &&
    !hasUnsavedChanges &&
    supportsScheduledParameters

  const loadSchedules = async () => {
    if (!isSaved) {
      setSchedules([])
      return
    }

    setIsLoading(true)
    setErrorMessage('')

    try {
      setSchedules(await getReportSchedules(report.id))
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to load report schedules.',
      )
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    if (!isSaved) {
      return
    }

    let isCurrent = true

    void getReportSchedules(report.id)
      .then((nextSchedules) => {
        if (isCurrent) {
          setSchedules(nextSchedules)
        }
      })
      .catch((error: unknown) => {
        if (isCurrent) {
          setErrorMessage(
            error instanceof Error
              ? error.message
              : 'Unable to load report schedules.',
          )
        }
      })
      .finally(() => {
        if (isCurrent) {
          setIsLoading(false)
        }
      })

    return () => {
      isCurrent = false
    }
  }, [report.id, isSaved])

  const handleSave = async () => {
    const name = draft.name.trim()

    if (!name) {
      setErrorMessage('Enter a schedule name.')
      return
    }

    if (!/^\d{2}:\d{2}$/.test(draft.time)) {
      setErrorMessage('Choose a valid schedule time.')
      return
    }

    if (!canSaveSchedule) {
      return
    }

    const existingSchedule = draft.id
      ? schedules.find((schedule) => schedule.id === draft.id)
      : undefined

    setIsSaving(true)
    setErrorMessage('')
    setSuccessMessage('')

    try {
      const savedSchedule = await saveReportSchedule(
        report,
        {
          ...draft,
          name,
          timezone,
        },
        existingSchedule,
      )

      setSchedules((currentSchedules) => {
        const exists = currentSchedules.some(
          (schedule) => schedule.id === savedSchedule.id,
        )

        return exists
          ? currentSchedules.map((schedule) =>
              schedule.id === savedSchedule.id
                ? savedSchedule
                : schedule,
            )
          : [savedSchedule, ...currentSchedules]
      })

      setDraft(createDraft(report))
      setSuccessMessage(
        existingSchedule
          ? 'Schedule updated.'
          : 'Schedule created.',
      )
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to save the report schedule.',
      )
    } finally {
      setIsSaving(false)
    }
  }

  const handleEdit = (schedule: ReportSchedule) => {
    setDraft({
      id: schedule.id,
      name: schedule.name,
      frequency:
        schedule.schedule.frequency === 'weekly' ||
        schedule.schedule.frequency === 'monthly'
          ? schedule.schedule.frequency
          : 'daily',
      time: schedule.schedule.time,
      dayOfWeek:
        schedule.schedule.daysOfWeek[0] ?? 0,
      dayOfMonth:
        schedule.schedule.dayOfMonth ?? 1,
      outputFormat:
        schedule.outputFormat === 'csv' ? 'csv' : 'xlsx',
    })
    setErrorMessage('')
    setSuccessMessage('')
  }

  const handleStatusChange = async (
    schedule: ReportSchedule,
  ) => {
    setBusyScheduleId(schedule.id)
    setErrorMessage('')
    setSuccessMessage('')

    try {
      const updatedSchedule = await setReportScheduleStatus(
        schedule,
        schedule.status === 'active' ? 'paused' : 'active',
      )

      setSchedules((currentSchedules) =>
        currentSchedules.map((candidate) =>
          candidate.id === updatedSchedule.id
            ? updatedSchedule
            : candidate,
        ),
      )
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to update the report schedule.',
      )
    } finally {
      setBusyScheduleId(null)
    }
  }

  const handleDelete = async (
    schedule: ReportSchedule,
  ) => {
    if (
      !window.confirm(
        `Delete the schedule "${schedule.name}"?`,
      )
    ) {
      return
    }

    setBusyScheduleId(schedule.id)
    setErrorMessage('')
    setSuccessMessage('')

    try {
      await deleteReportSchedule(schedule.id)
      setSchedules((currentSchedules) =>
        currentSchedules.filter(
          (candidate) => candidate.id !== schedule.id,
        ),
      )

      if (draft.id === schedule.id) {
        setDraft(createDraft(report))
      }
    } catch (error) {
      setErrorMessage(
        error instanceof Error
          ? error.message
          : 'Unable to delete the report schedule.',
      )
    } finally {
      setBusyScheduleId(null)
    }
  }

  return (
    <section className="report-panel-card report-schedule-panel">
      <div className="report-panel-heading">
        <div>
          <strong>Schedule</strong>
          <span>
            Persist a recurring export through Automation Center.
          </span>
        </div>

        <span className="report-panel-icon">◷</span>
      </div>

      {!isSaved ? (
        <div className="report-capability-note">
          Save this report before creating a schedule.
        </div>
      ) : hasUnsavedChanges ? (
        <div className="report-capability-note">
          Save the current report changes before scheduling them.
        </div>
      ) : !supportsScheduledParameters ? (
        <div className="report-capability-note report-capability-note-warning">
          Parameterized report schedules are unavailable because the current
          automation executor cannot bind saved parameter values. Manual
          preview and CSV export remain available.
        </div>
      ) : null}

      {errorMessage && (
        <div className="report-inline-error" role="alert">
          <span>{errorMessage}</span>
          {isSaved && (
            <button type="button" onClick={() => void loadSchedules()}>
              Retry
            </button>
          )}
        </div>
      )}

      {successMessage && (
        <div className="report-inline-success" role="status">
          {successMessage}
        </div>
      )}

      <div className="report-schedule-form">
        <label className="report-filter-field report-schedule-field-full">
          <span>Schedule name</span>
          <input
            type="text"
            value={draft.name}
            onChange={(event) =>
              setDraft((currentDraft) => ({
                ...currentDraft,
                name: event.target.value,
              }))
            }
            disabled={!canSaveSchedule || isSaving}
          />
        </label>

        <label className="report-filter-field">
          <span>Frequency</span>
          <select
            value={draft.frequency}
            onChange={(event) =>
              setDraft((currentDraft) => ({
                ...currentDraft,
                frequency: event.target
                  .value as ReportScheduleFrequency,
              }))
            }
            disabled={!canSaveSchedule || isSaving}
          >
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
          </select>
        </label>

        <label className="report-filter-field">
          <span>Time</span>
          <input
            type="time"
            value={draft.time}
            onChange={(event) =>
              setDraft((currentDraft) => ({
                ...currentDraft,
                time: event.target.value,
              }))
            }
            disabled={!canSaveSchedule || isSaving}
          />
        </label>

        {draft.frequency === 'weekly' && (
          <label className="report-filter-field report-schedule-field-full">
            <span>Day</span>
            <select
              value={draft.dayOfWeek}
              onChange={(event) =>
                setDraft((currentDraft) => ({
                  ...currentDraft,
                  dayOfWeek: Number(event.target.value),
                }))
              }
              disabled={!canSaveSchedule || isSaving}
            >
              {WEEKDAYS.map((day, index) => (
                <option key={day} value={index}>
                  {day}
                </option>
              ))}
            </select>
          </label>
        )}

        {draft.frequency === 'monthly' && (
          <label className="report-filter-field report-schedule-field-full">
            <span>Day of month</span>
            <input
              type="number"
              min={1}
              max={31}
              value={draft.dayOfMonth}
              onChange={(event) =>
                setDraft((currentDraft) => ({
                  ...currentDraft,
                  dayOfMonth: Math.min(
                    31,
                    Math.max(1, Number(event.target.value) || 1),
                  ),
                }))
              }
              disabled={!canSaveSchedule || isSaving}
            />
          </label>
        )}

        <label className="report-filter-field report-schedule-field-full">
          <span>Output</span>
          <select
            value={draft.outputFormat}
            onChange={(event) =>
              setDraft((currentDraft) => ({
                ...currentDraft,
                outputFormat: event.target
                  .value as 'csv' | 'xlsx',
              }))
            }
            disabled={!canSaveSchedule || isSaving}
          >
            <option value="csv">CSV</option>
            <option value="xlsx">Excel workbook</option>
          </select>
        </label>
      </div>

      <div className="report-schedule-save-row">
        {draft.id && (
          <button
            type="button"
            className="report-secondary-button"
            onClick={() => setDraft(createDraft(report))}
            disabled={isSaving}
          >
            Cancel Edit
          </button>
        )}

        <button
          type="button"
          className="report-primary-button"
          onClick={() => void handleSave()}
          disabled={!canSaveSchedule || isSaving}
        >
          {isSaving
            ? 'Saving…'
            : draft.id
              ? 'Update Schedule'
              : 'Create Schedule'}
        </button>
      </div>

      <div className="report-schedule-timezone">
        Timezone: <strong>{timezone}</strong>
      </div>

      <div className="report-schedule-list-heading">
        <strong>Existing schedules</strong>
        <span>{schedules.length}</span>
      </div>

      {isLoading ? (
        <div className="report-empty-state">Loading schedules…</div>
      ) : schedules.length === 0 ? (
        <div className="report-empty-state">
          No schedules are connected to this report.
        </div>
      ) : (
        <div className="report-schedule-list">
          {schedules.map((schedule) => (
            <article key={schedule.id} className="report-schedule-item">
              <div>
                <strong>{schedule.name}</strong>
                <span>{scheduleSummary(schedule)}</span>
                <span>
                  {schedule.outputFormat.toUpperCase()} · Next:{' '}
                  {formatDateTime(schedule.nextRunAt)}
                </span>
              </div>

              <span
                className={`report-schedule-status report-schedule-status-${schedule.status}`}
              >
                {schedule.status}
              </span>

              <div className="report-schedule-actions">
                <button type="button" onClick={() => handleEdit(schedule)}>
                  Edit
                </button>
                <button
                  type="button"
                  onClick={() => void handleStatusChange(schedule)}
                  disabled={busyScheduleId === schedule.id}
                >
                  {schedule.status === 'active' ? 'Pause' : 'Activate'}
                </button>
                <button
                  type="button"
                  className="danger"
                  onClick={() => void handleDelete(schedule)}
                  disabled={busyScheduleId === schedule.id}
                >
                  Delete
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  )
}

export default ReportSchedulePanel
