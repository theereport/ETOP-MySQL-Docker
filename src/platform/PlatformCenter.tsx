import {
  useEffect,
  useRef,
  useState,
} from 'react'
import './PlatformCenter.css'
import { searchEnterprise } from './search'
import {
  getNotifications,
  getTasks,
  getTimeline,
  saveNotifications,
  saveTasks,
} from './platformStore'
import type {
  PlatformCenterMode,
  PlatformNotification,
  PlatformTask,
  SearchResult,
} from './types'
// Imported from workflow-foundation's own api.ts, not its barrel - that
// barrel also statically re-exports WorkflowFoundationWorkspace, and this
// file is part of the always-eager PlatformCenter, so a barrel import here
// would pull that lazy-loaded workspace back into the main bundle.
import {
  getWorkflowNotifications,
  getWorkflowTasks,
  getWorkflowToken,
  markWorkflowNotificationRead,
} from '../features/workflow-foundation/api'
import { acknowledgeJobQueueItem, getJobQueueJobs } from '../features/job-queue'

type Props = {
  mode: PlatformCenterMode
  onClose: () => void
  onOpenModule: (
    moduleName: string,
    searchTarget?: SearchResult,
  ) => void
}

export default function PlatformCenter({
  mode,
  onClose,
  onOpenModule,
}: Props) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const [workflowNotifications, setWorkflowNotifications] = useState<PlatformNotification[] | null>(null)
  const [workflowTasks, setWorkflowTasks] = useState<PlatformTask[] | null>(null)
  const [workflowError, setWorkflowError] = useState('')
  const [workflowLoading, setWorkflowLoading] = useState(false)
  const [jobQueueNotifications, setJobQueueNotifications] = useState<PlatformNotification[]>([])
  const searchRequestId = useRef(0)

  const localNotifications = getNotifications()
  const localTasks = getTasks()
  const signedInToWorkflow = Boolean(getWorkflowToken())
  const baseNotifications = signedInToWorkflow ? workflowNotifications ?? [] : localNotifications
  const notifications = [...jobQueueNotifications, ...baseNotifications].sort(
    (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
  )
  const tasks = signedInToWorkflow ? workflowTasks ?? [] : localTasks
  const timeline = getTimeline()

  useEffect(() => {
    if (!signedInToWorkflow || (mode !== 'notifications' && mode !== 'tasks')) {
      return
    }
    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => {
      setWorkflowLoading(true)
      setWorkflowError('')
      void Promise.all([
        getWorkflowNotifications(controller.signal),
        getWorkflowTasks({ mine: true }, controller.signal),
      ])
        .then(([notificationResult, taskResult]) => {
          if (controller.signal.aborted) return
          setWorkflowNotifications(notificationResult.items.map((item) => ({
            id: item.notification_id,
            title: item.title,
            message: item.message,
            createdAt: item.created_at,
            severity: item.severity,
            read: item.read_at !== null,
            module: 'Work Management',
          })))
          setWorkflowTasks(taskResult.items.map((task) => ({
            id: task.task_id,
            title: task.title,
            description: `${task.context_label} · ${task.assignee?.display_name ?? task.queue_role.name}`,
            status: task.state === 'completed'
              ? 'Completed'
              : task.state === 'in_progress'
                ? 'In Progress'
                : 'Open',
            priority: task.priority === 'critical'
              ? 'Critical'
              : task.priority === 'high'
                ? 'High'
                : task.priority === 'medium'
                  ? 'Medium'
                  : 'Low',
            dueDate: task.due_date ?? undefined,
            module: 'Work Management',
          })))
        })
        .catch((error: unknown) => {
          if (!controller.signal.aborted) {
            setWorkflowError(error instanceof Error ? error.message : 'Unable to load durable work.')
          }
        })
        .finally(() => {
          if (!controller.signal.aborted) setWorkflowLoading(false)
        })
    }, 0)
    return () => {
      window.clearTimeout(timeoutId)
      controller.abort()
    }
  }, [mode, refresh, signedInToWorkflow])

  useEffect(() => {
    if (mode !== 'notifications' || !getWorkflowToken()) {
      return undefined
    }
    let active = true
    void getJobQueueJobs()
      .then((jobs) => {
        if (!active) return
        setJobQueueNotifications(
          jobs
            .filter((job) => job.status === 'completed' || job.status === 'failed')
            .map((job) => ({
              id: job.job_id,
              title: job.status === 'failed' ? `${job.title} failed` : `${job.title} completed`,
              message: job.message ?? '',
              createdAt: job.completed_at ?? job.created_at,
              severity: job.status === 'failed' ? 'critical' : 'success',
              read: job.acknowledged_at !== null,
              module: job.result_module ?? undefined,
            })),
        )
      })
      .catch(() => {
        if (active) setJobQueueNotifications([])
      })
    return () => {
      active = false
    }
  }, [mode, refresh])

  useEffect(() => {
    if (mode !== 'search' || !query.trim()) {
      searchRequestId.current += 1
      const resetTimeout = window.setTimeout(() => {
        setResults([])
        setIsSearching(false)
      }, 0)

      return () => window.clearTimeout(resetTimeout)
    }

    const requestId = searchRequestId.current + 1
    searchRequestId.current = requestId
    const controller = new AbortController()
    const timeout = window.setTimeout(async () => {
      setIsSearching(true)

      try {
        const nextResults = await searchEnterprise(
          query,
          controller.signal,
        )

        if (
          searchRequestId.current === requestId &&
          !controller.signal.aborted
        ) {
          setResults(nextResults)
        }
      } finally {
        if (searchRequestId.current === requestId) {
          setIsSearching(false)
        }
      }
    }, 180)

    return () => {
      controller.abort()
      window.clearTimeout(timeout)
    }
  }, [mode, query])

  function openResult(result: SearchResult) {
    if (result.action) {
      onOpenModule(result.action, result)
      onClose()
    }
  }

  async function markAllRead() {
    await Promise.all(
      jobQueueNotifications
        .filter((item) => !item.read)
        .map((item) => acknowledgeJobQueueItem(item.id)),
    )
    if (signedInToWorkflow) {
      await Promise.all(
        baseNotifications
          .filter((item) => !item.read)
          .map((item) => markWorkflowNotificationRead(item.id)),
      )
      setRefresh((value) => value + 1)
      return
    }
    saveNotifications(baseNotifications.map((item) => ({ ...item, read: true })))
    setRefresh((value) => value + 1)
  }

  function toggleTask(taskId: string) {
    if (signedInToWorkflow) {
      void taskId
      onOpenModule('Work Management')
      onClose()
      return
    }
    saveTasks(
      tasks.map((task) =>
        task.id === taskId
          ? {
              ...task,
              status:
                task.status === 'Completed'
                  ? 'Open'
                  : 'Completed',
            }
          : task,
      ),
    )
    setRefresh((value) => value + 1)
  }

  return (
    <div className="platform-center-backdrop" onMouseDown={onClose}>
      <section
        className="platform-center"
        onMouseDown={(event) => event.stopPropagation()}
        aria-modal="true"
        role="dialog"
      >
        <header>
          <div>
            <span>ETOP PLATFORM</span>
            <h2>
              {mode === 'search' && 'Enterprise Search'}
              {mode === 'notifications' && 'Notifications'}
              {mode === 'tasks' && 'My Tasks'}
              {mode === 'timeline' && 'Enterprise Timeline'}
            </h2>
          </div>
          <button type="button" onClick={onClose} aria-label="Close">
            ×
          </button>
        </header>

        {mode === 'search' && (
          <>
            <div className="platform-search-box">
              <span>⌕</span>
              <input
                autoFocus
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (
                    event.key === 'Enter' &&
                    !isSearching &&
                    results[0]
                  ) {
                    event.preventDefault()
                    openResult(results[0])
                  }
                }}
                placeholder="Search customers, modules, reports, SOPs, documents, routes..."
                aria-label="Search the ETOP enterprise"
              />
              <kbd>Esc</kbd>
            </div>

            <div className="platform-center-content">
              {!query.trim() && (
                <div className="platform-empty">
                  <strong>Search the entire enterprise</strong>
                  <p>
                    Begin with a customer number or name, route,
                    report, document, SOP, or module name.
                  </p>
                </div>
              )}

              {isSearching && (
                <div className="platform-empty">Searching locally…</div>
              )}

              {!isSearching &&
                query.trim() &&
                results.length === 0 && (
                  <div className="platform-empty">
                    No matching enterprise objects were found.
                  </div>
                )}

              {!isSearching && results.length > 0 && (
                <div
                  className="platform-result-summary"
                  aria-live="polite"
                >
                  {results.length}{' '}
                  {results.length === 1 ? 'result' : 'results'}
                  <span>Press Enter to open the first result</span>
                </div>
              )}

              <div
                className="platform-result-list"
                role="listbox"
                aria-label="Enterprise search results"
              >
                {results.map((result) => (
                  <button
                    type="button"
                    key={result.id}
                    onClick={() => openResult(result)}
                    role="option"
                    aria-label={`${result.type}: ${result.title}`}
                  >
                    <span className="result-type">{result.type}</span>
                    <span className="result-copy">
                      <strong>{result.title}</strong>
                      <small>{result.subtitle}</small>
                    </span>
                    <span className="result-module">{result.module}</span>
                  </button>
                ))}
              </div>
            </div>
          </>
        )}

        {mode === 'notifications' && (
          <div className="platform-center-content">
            <div className="platform-actions-row">
              <span>{notifications.filter((item) => !item.read).length} unread</span>
              <button type="button" onClick={() => void markAllRead()}>
                Mark all read
              </button>
            </div>
            {signedInToWorkflow && workflowLoading && <div className="platform-empty">Loading durable notifications…</div>}
            {signedInToWorkflow && workflowError && <div className="platform-empty">{workflowError}</div>}
            {!signedInToWorkflow && (
              <div className="platform-empty">
                Sign in through Work Management to use durable notifications. Browser-local legacy notices are shown below.
              </div>
            )}
            <div className="platform-card-list">
              {notifications.map((item) => (
                <article
                  key={item.id}
                  className={`platform-item ${item.read ? 'read' : ''}`}
                >
                  <span className={`severity ${item.severity}`} />
                  <div>
                    <strong>{item.title}</strong>
                    <p>{item.message}</p>
                    <small>{new Date(item.createdAt).toLocaleString()}</small>
                  </div>
                </article>
              ))}
            </div>
          </div>
        )}

        {mode === 'tasks' && (
          <div className="platform-center-content">
            {signedInToWorkflow && workflowLoading && <div className="platform-empty">Loading durable assigned work…</div>}
            {signedInToWorkflow && workflowError && <div className="platform-empty">{workflowError}</div>}
            {!signedInToWorkflow && (
              <div className="platform-empty">
                Sign in through Work Management to use verified durable assignments. Browser-local legacy tasks are shown below.
              </div>
            )}
            <div className="platform-card-list">
              {tasks.map((task) => (
                <button
                  type="button"
                  key={task.id}
                  className={`platform-item task ${task.status === 'Completed' ? 'read' : ''}`}
                  onClick={() => toggleTask(task.id)}
                >
                  <span className="task-check">
                    {task.status === 'Completed' ? '✓' : ''}
                  </span>
                  <div>
                    <strong>{task.title}</strong>
                    <p>{task.description}</p>
                  <small>{task.priority} priority · {task.status}</small>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {mode === 'timeline' && (
          <div className="platform-center-content">
            <div className="platform-card-list">
              {timeline.map((event) => (
                <article key={event.id} className="platform-item">
                  <span className={`severity ${event.severity}`} />
                  <div>
                    <strong>{event.title}</strong>
                    <p>{event.description}</p>
                    <small>
                      {event.module} · {new Date(event.timestamp).toLocaleString()}
                    </small>
                  </div>
                </article>
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
