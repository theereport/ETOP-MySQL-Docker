import { type FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import {
  assignWorkflowTask,
  bootstrapWorkflowAccount,
  createWorkflowTask,
  createWorkflowUser,
  getBootstrapStatus,
  getWorkflowAudit,
  getWorkflowHealth,
  getWorkflowNotifications,
  getWorkflowRoles,
  getWorkflowSession,
  getWorkflowTask,
  getWorkflowTasks,
  getWorkflowToken,
  getWorkflowUsers,
  loginWorkflow,
  logoutWorkflow,
  markWorkflowNotificationRead,
  saveWorkflowToken,
  transitionWorkflowTask,
  verifyWorkflowAudit,
  workflowIdempotencyKey,
} from './api'
import type {
  WorkflowAuditEvent,
  WorkflowAuditIntegrity,
  WorkflowBootstrapStatus,
  WorkflowCapability,
  WorkflowHealth,
  WorkflowNotificationList,
  WorkflowRole,
  WorkflowRoleId,
  WorkflowSession,
  WorkflowTask,
  WorkflowTaskDetail,
  WorkflowTaskState,
  WorkflowUser,
} from './types'
import './WorkflowFoundationWorkspace.css'

type WorkspaceView = 'queue' | 'create' | 'identity' | 'notifications' | 'audit'
type Status = 'idle' | 'loading' | 'ready' | 'error'

const roleCapability: Record<WorkflowCapability, WorkflowRoleId> = {
  credit_risk: 'credit_professional',
  accounts_payable: 'ap_professional',
  lockbox: 'workflow_observer',
  reporting: 'workflow_observer',
  platform: 'workflow_coordinator',
}

const capabilityLabel: Record<WorkflowCapability, string> = {
  credit_risk: 'Credit Risk',
  accounts_payable: 'Accounts Payable',
  lockbox: 'Lockbox',
  reporting: 'Reporting',
  platform: 'Platform',
}

function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : 'The governed workflow request could not be completed.'
}

function formatDateTime(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleString()
}

function stateLabel(value: string): string {
  return value.replaceAll('_', ' ')
}

function hasRole(user: WorkflowUser | null, roleId: WorkflowRoleId): boolean {
  return user?.roles.some((role) => role.role_id === roleId) ?? false
}

export default function WorkflowFoundationWorkspace() {
  const [bootstrap, setBootstrap] = useState<WorkflowBootstrapStatus | null>(null)
  const [session, setSession] = useState<WorkflowSession | null>(null)
  const [status, setStatus] = useState<Status>('loading')
  const [error, setError] = useState('')
  const [view, setView] = useState<WorkspaceView>('queue')
  const [health, setHealth] = useState<WorkflowHealth | null>(null)
  const [roles, setRoles] = useState<WorkflowRole[]>([])
  const [users, setUsers] = useState<WorkflowUser[]>([])
  const [tasks, setTasks] = useState<WorkflowTask[]>([])
  const [notifications, setNotifications] = useState<WorkflowNotificationList | null>(null)
  const [audit, setAudit] = useState<WorkflowAuditEvent[]>([])
  const [auditIntegrity, setAuditIntegrity] = useState<WorkflowAuditIntegrity | null>(null)
  const [selectedTask, setSelectedTask] = useState<WorkflowTaskDetail | null>(null)
  const [taskFilter, setTaskFilter] = useState({ capability: '', state: '', mine: false })
  const [actionStatus, setActionStatus] = useState<Status>('idle')
  const [actionMessage, setActionMessage] = useState('')
  const [assignmentUserId, setAssignmentUserId] = useState('')
  const [assignmentNote, setAssignmentNote] = useState('')

  const coordinator = hasRole(session?.user ?? null, 'workflow_coordinator')

  const loadQueue = useCallback(async () => {
    const result = await getWorkflowTasks({
      mine: taskFilter.mine,
      capability: taskFilter.capability || undefined,
      state: taskFilter.state || undefined,
    })
    setTasks(result.items)
  }, [taskFilter])

  const loadAuthenticatedData = useCallback(async () => {
    const current = await getWorkflowSession()
    setSession(current)
    const isCoordinator = hasRole(current.user, 'workflow_coordinator')
    const [nextHealth, nextRoles, nextUsers, nextTasks, nextNotifications] = await Promise.all([
      getWorkflowHealth(),
      getWorkflowRoles(),
      getWorkflowUsers(),
      getWorkflowTasks({ mine: taskFilter.mine }),
      getWorkflowNotifications(),
    ])
    setHealth(nextHealth)
    setRoles(nextRoles)
    setUsers(nextUsers)
    setTasks(nextTasks.items)
    setNotifications(nextNotifications)
    if (isCoordinator) {
      const [nextAudit, nextIntegrity] = await Promise.all([
        getWorkflowAudit(),
        verifyWorkflowAudit(),
      ])
      setAudit(nextAudit)
      setAuditIntegrity(nextIntegrity)
    } else {
      setAudit([])
      setAuditIntegrity(null)
    }
  }, [taskFilter.mine])

  useEffect(() => {
    const controller = new AbortController()
    const initialize = async () => {
      setStatus('loading')
      setError('')
      try {
        const nextBootstrap = await getBootstrapStatus(controller.signal)
        if (controller.signal.aborted) return
        setBootstrap(nextBootstrap)
        if (getWorkflowToken() && !nextBootstrap.bootstrap_required) {
          await loadAuthenticatedData()
        }
        if (!controller.signal.aborted) setStatus('ready')
      } catch (loadError) {
        if (!controller.signal.aborted) {
          setStatus('error')
          setError(errorMessage(loadError))
        }
      }
    }
    void initialize()
    return () => controller.abort()
  }, [loadAuthenticatedData])

  useEffect(() => {
    if (!session) return
    const timeoutId = window.setTimeout(() => {
      void loadQueue().catch((loadError) => setError(errorMessage(loadError)))
    }, 0)
    return () => window.clearTimeout(timeoutId)
  }, [loadQueue, session])

  async function authenticate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    setActionStatus('loading')
    setError('')
    try {
      const result = bootstrap?.bootstrap_required
        ? await bootstrapWorkflowAccount({
            display_name: String(data.get('display_name') ?? ''),
            username: String(data.get('username') ?? ''),
            password: String(data.get('password') ?? ''),
          })
        : await loginWorkflow({
            username: String(data.get('username') ?? ''),
            password: String(data.get('password') ?? ''),
          })
      saveWorkflowToken(result.token)
      setBootstrap((current) => current ? { ...current, bootstrap_required: false, account_count: Math.max(1, current.account_count) } : current)
      await loadAuthenticatedData()
      setActionStatus('ready')
    } catch (authError) {
      setActionStatus('error')
      setError(errorMessage(authError))
    }
  }

  async function signOut() {
    setActionStatus('loading')
    try {
      await logoutWorkflow()
      setSession(null)
      setHealth(null)
      setTasks([])
      setNotifications(null)
      setAudit([])
      setSelectedTask(null)
      setActionStatus('idle')
    } catch (signOutError) {
      setActionStatus('error')
      setError(errorMessage(signOutError))
    }
  }

  async function refresh() {
    setActionStatus('loading')
    setError('')
    try {
      await loadAuthenticatedData()
      if (selectedTask) {
        setSelectedTask(await getWorkflowTask(selectedTask.task_id))
      }
      setActionStatus('ready')
      setActionMessage('Current durable workflow state loaded.')
    } catch (refreshError) {
      setActionStatus('error')
      setError(errorMessage(refreshError))
    }
  }

  async function openTask(taskId: string) {
    setActionStatus('loading')
    setError('')
    try {
      const detail = await getWorkflowTask(taskId)
      setSelectedTask(detail)
      setAssignmentUserId(detail.assignee?.user_id ?? '')
      setAssignmentNote('')
      setActionStatus('ready')
    } catch (taskError) {
      setActionStatus('error')
      setError(errorMessage(taskError))
    }
  }

  async function createTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const capability = String(data.get('capability')) as WorkflowCapability
    setActionStatus('loading')
    setError('')
    setActionMessage('')
    try {
      const detail = await createWorkflowTask({
        title: String(data.get('title') ?? ''),
        description: String(data.get('description') ?? ''),
        capability,
        context_type: String(data.get('context_type') ?? ''),
        context_id: String(data.get('context_id') ?? ''),
        context_label: String(data.get('context_label') ?? ''),
        queue_role_id: String(data.get('queue_role_id')) as WorkflowRoleId,
        assignee_user_id: String(data.get('assignee_user_id') ?? '') || undefined,
        priority: String(data.get('priority')) as WorkflowTask['priority'],
        due_date: String(data.get('due_date') ?? '') || undefined,
        idempotency_key: workflowIdempotencyKey('workspace-create'),
      })
      setSelectedTask(detail)
      setView('queue')
      await loadQueue()
      setActionStatus('ready')
      setActionMessage('Governed work item created. No decision or ERP action occurred.')
      event.currentTarget.reset()
    } catch (createError) {
      setActionStatus('error')
      setError(errorMessage(createError))
    }
  }

  async function assignTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedTask || !assignmentUserId) return
    setActionStatus('loading')
    setError('')
    try {
      const updated = await assignWorkflowTask(selectedTask.task_id, {
        assignee_user_id: assignmentUserId,
        note: assignmentNote,
        expected_version: selectedTask.version,
        idempotency_key: workflowIdempotencyKey('workspace-assign'),
      })
      setSelectedTask(updated)
      await loadQueue()
      setActionStatus('ready')
      setActionMessage('Verified work ownership recorded. No decision authority was granted.')
    } catch (assignError) {
      setActionStatus('error')
      setError(errorMessage(assignError))
    }
  }

  async function transitionTask(targetState: WorkflowTaskState) {
    if (!selectedTask) return
    setActionStatus('loading')
    setError('')
    try {
      const updated = await transitionWorkflowTask(selectedTask.task_id, {
        target_state: targetState,
        note: `State changed through the governed work queue to ${stateLabel(targetState)}.`,
        expected_version: selectedTask.version,
        idempotency_key: workflowIdempotencyKey('workspace-transition'),
      })
      setSelectedTask(updated)
      await loadQueue()
      setActionStatus('ready')
      setActionMessage(`Task state changed to ${stateLabel(targetState)}. No underlying business object changed.`)
    } catch (transitionError) {
      setActionStatus('error')
      setError(errorMessage(transitionError))
    }
  }

  async function createUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const roleIds = data.getAll('role_ids').map(String) as WorkflowRoleId[]
    setActionStatus('loading')
    setError('')
    try {
      await createWorkflowUser({
        display_name: String(data.get('display_name') ?? ''),
        username: String(data.get('username') ?? ''),
        password: String(data.get('password') ?? ''),
        role_ids: roleIds,
      })
      setUsers(await getWorkflowUsers())
      setActionStatus('ready')
      setActionMessage('Local workflow account created. Its roles confer no financial authority.')
      event.currentTarget.reset()
    } catch (userError) {
      setActionStatus('error')
      setError(errorMessage(userError))
    }
  }

  async function markRead(notificationId: string) {
    try {
      await markWorkflowNotificationRead(notificationId)
      setNotifications(await getWorkflowNotifications())
    } catch (notificationError) {
      setError(errorMessage(notificationError))
    }
  }

  const selectedRoleId = selectedTask?.queue_role.role_id
  const eligibleUsers = useMemo(
    () => users.filter((user) => user.roles.some((role) => role.role_id === selectedRoleId)),
    [selectedRoleId, users],
  )

  if (status === 'loading') {
    return <section className="workflow-shell workflow-centered"><strong>Loading governed workflow foundation…</strong></section>
  }

  if (!bootstrap || status === 'error') {
    return <section className="workflow-shell workflow-centered"><h1>Work Management unavailable</h1><p>{error || 'The local workflow bootstrap state could not be read.'}</p></section>
  }

  if (!session) {
    return (
      <section className="workflow-shell workflow-auth-shell">
        <div className="workflow-auth-card">
          <span className="workflow-eyebrow">IDENTITY · ASSIGNMENT · GOVERNED WORKFLOW</span>
          <h1>{bootstrap.bootstrap_required ? 'Establish the first local account' : 'Sign in to Work Management'}</h1>
          <p>{bootstrap.bootstrap_required ? 'The first account becomes the local Workflow Coordinator. This controls identities and work ownership only.' : 'Use your local ETOP workflow credentials. Existing ETOP modules remain available without this session.'}</p>
          <form onSubmit={authenticate}>
            {bootstrap.bootstrap_required && <label>Display name<input name="display_name" required minLength={2} autoComplete="name" /></label>}
            <label>Username<input name="username" required minLength={3} pattern="[A-Za-z0-9._-]+" autoComplete="username" /></label>
            <label>Password<input name="password" type="password" required minLength={12} autoComplete={bootstrap.bootstrap_required ? 'new-password' : 'current-password'} /></label>
            {error && <p className="workflow-error">{error}</p>}
            <button type="submit" disabled={actionStatus === 'loading'}>{actionStatus === 'loading' ? 'Working…' : bootstrap.bootstrap_required ? 'Create controlled account' : 'Sign in'}</button>
          </form>
          <div className="workflow-boundary"><strong>Authentication boundary</strong><p>{bootstrap.authentication_boundary}</p><strong>Authority boundary</strong><p>{bootstrap.authority_boundary}</p></div>
        </div>
      </section>
    )
  }

  return (
    <section className="workflow-shell">
      <header className="workflow-header">
        <div><span className="workflow-eyebrow">PLATFORM FOUNDATION · INCREMENT 1</span><h1>Work Management</h1><p>Authenticated local identities, durable role queues, verified work ownership, in-app notifications, and tamper-aware audit evidence.</p></div>
        <div className="workflow-session-card"><span>Signed in locally</span><strong>{session.user.display_name}</strong><small>{session.user.roles.map((role) => role.name).join(' · ')}</small><div><button type="button" onClick={() => void refresh()} disabled={actionStatus === 'loading'}>Refresh</button><button type="button" onClick={() => void signOut()}>Sign out</button></div></div>
      </header>

      <div className="workflow-governance-strip"><span><i /> Local credential authenticated</span><span>Assignment ≠ authority</span><span>No ERP access or execution</span></div>

      {error && <div className="workflow-message workflow-message--error">{error}</div>}
      {actionMessage && <div className="workflow-message workflow-message--success">{actionMessage}</div>}

      <div className="workflow-metrics">
        <article><span>Active accounts</span><strong>{health?.users ?? '—'}</strong></article>
        <article><span>Open work</span><strong>{health?.open_tasks ?? '—'}</strong></article>
        <article><span>Unread notices</span><strong>{health?.unread_notifications ?? '—'}</strong></article>
        <article><span>Audit chain</span><strong>{health?.audit_integrity.valid ? 'Verified' : 'Unavailable'}</strong><small>{health ? `${health.audit_records} records` : ''}</small></article>
      </div>

      <nav className="workflow-tabs" aria-label="Work Management views">
        {([
          ['queue', 'Work Queue'], ['create', 'Create Work'], ['identity', 'People & Roles'],
          ['notifications', `Notifications${notifications?.unread_count ? ` (${notifications.unread_count})` : ''}`],
          ['audit', 'Audit & Boundaries'],
        ] as [WorkspaceView, string][]).map(([id, label]) => <button key={id} type="button" className={view === id ? 'is-active' : ''} onClick={() => setView(id)}>{label}</button>)}
      </nav>

      {view === 'queue' && (
        <div className="workflow-queue-layout">
          <section className="workflow-panel">
            <div className="workflow-panel-heading"><div><span>Durable work</span><h2>{coordinator && !taskFilter.mine ? 'All governed work' : 'Personal and role queues'}</h2></div><strong>{tasks.length}</strong></div>
            <div className="workflow-filters">
              <select value={taskFilter.capability} onChange={(event) => setTaskFilter((current) => ({ ...current, capability: event.target.value }))}><option value="">All capabilities</option>{Object.entries(capabilityLabel).map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select>
              <select value={taskFilter.state} onChange={(event) => setTaskFilter((current) => ({ ...current, state: event.target.value }))}><option value="">All states</option>{['open', 'in_progress', 'deferred', 'completed', 'cancelled', 'reopened'].map((stateValue) => <option key={stateValue} value={stateValue}>{stateLabel(stateValue)}</option>)}</select>
              <label><input type="checkbox" checked={taskFilter.mine} onChange={(event) => setTaskFilter((current) => ({ ...current, mine: event.target.checked }))} /> Assigned to me</label>
            </div>
            {!tasks.length && <div className="workflow-empty"><strong>No work matched this queue.</strong><p>ETOP did not create placeholder tasks.</p></div>}
            <div className="workflow-task-list">{tasks.map((task) => <button type="button" key={task.task_id} onClick={() => void openTask(task.task_id)} className={selectedTask?.task_id === task.task_id ? 'is-selected' : ''}><span className={`workflow-priority workflow-priority--${task.priority}`}>{task.priority}</span><div><strong>{task.title}</strong><p>{task.context_label}</p><small>{capabilityLabel[task.capability]} · {stateLabel(task.state)} · {task.assignee?.display_name ?? task.queue_role.name}</small></div>{task.due_date && <time>{task.due_date}</time>}</button>)}</div>
          </section>

          <section className="workflow-panel workflow-detail-panel">
            {!selectedTask && <div className="workflow-empty"><strong>Select a work item</strong><p>Its context, bound definition version, assignment history, and permitted transitions will appear here.</p></div>}
            {selectedTask && <>
              <div className="workflow-panel-heading"><div><span>{selectedTask.task_id}</span><h2>{selectedTask.title}</h2></div><span className="workflow-state">{stateLabel(selectedTask.state)}</span></div>
              <p>{selectedTask.description || 'No additional description was supplied.'}</p>
              <dl className="workflow-details"><div><dt>Context</dt><dd>{selectedTask.context_type} · {selectedTask.context_id}<small>{selectedTask.context_label}</small></dd></div><div><dt>Workflow</dt><dd>{selectedTask.definition_id}<small>Version {selectedTask.definition_version} · instance v{selectedTask.version}</small></dd></div><div><dt>Queue</dt><dd>{selectedTask.queue_role.name}<small>{selectedTask.assignee ? `Assigned to ${selectedTask.assignee.display_name}` : 'Unassigned role queue'}</small></dd></div><div><dt>Boundary</dt><dd>Work ownership only<small>No authority · no execution</small></dd></div></dl>
              <div className="workflow-action-row">
                {selectedTask.permitted_actions.includes('claim') && <button type="button" onClick={() => { setAssignmentUserId(session.user.user_id); setAssignmentNote('Claimed from an eligible operational role queue.') }}>Prepare claim</button>}
                {selectedTask.permitted_actions.filter((action) => action.startsWith('transition:')).map((action) => { const target = action.split(':')[1] as WorkflowTaskState; return <button type="button" key={action} onClick={() => void transitionTask(target)} disabled={actionStatus === 'loading'}>{stateLabel(target)}</button> })}
              </div>
              {(selectedTask.permitted_actions.includes('assign') || selectedTask.permitted_actions.includes('claim')) && <form className="workflow-assignment-form" onSubmit={assignTask}><label>Verified assignee<select value={assignmentUserId} onChange={(event) => setAssignmentUserId(event.target.value)} required><option value="">Select eligible account</option>{eligibleUsers.map((user) => <option key={user.user_id} value={user.user_id}>{user.display_name}</option>)}</select></label><label>Assignment note<input value={assignmentNote} onChange={(event) => setAssignmentNote(event.target.value)} maxLength={1000} /></label><button type="submit" disabled={!assignmentUserId || actionStatus === 'loading'}>{selectedTask.assignee ? 'Reassign work' : 'Record assignment'}</button></form>}
              <div className="workflow-history"><h3>Immutable task history</h3>{selectedTask.events.map((event) => <article key={event.event_id}><strong>{stateLabel(event.to_state)}</strong><span>{event.actor.display_name} · {formatDateTime(event.created_at)}</span><p>{event.note}</p></article>)}</div>
            </>}
          </section>
        </div>
      )}

      {view === 'create' && <section className="workflow-panel workflow-form-panel"><div className="workflow-panel-heading"><div><span>Version-bound work</span><h2>Create governed follow-up</h2></div></div><p>Create accountable work around an existing context reference. This does not create, approve, or change the referenced business object.</p><form className="workflow-form-grid" onSubmit={createTask}><label>Title<input name="title" required minLength={3} maxLength={180} /></label><label>Capability<select name="capability" defaultValue="credit_risk" onChange={(event) => { const form = event.currentTarget.form; if (form) { const role = form.elements.namedItem('queue_role_id') as HTMLSelectElement; role.value = roleCapability[event.target.value as WorkflowCapability] } }}><option value="credit_risk">Credit Risk</option><option value="accounts_payable">Accounts Payable</option><option value="lockbox">Lockbox</option><option value="reporting">Reporting</option><option value="platform">Platform</option></select></label><label className="workflow-span-2">Description<textarea name="description" maxLength={2000} /></label><label>Context type<input name="context_type" defaultValue="customer" required pattern="[a-z][a-z0-9_]*" /></label><label>Context ID<input name="context_id" required /></label><label className="workflow-span-2">Context label<input name="context_label" required /></label><label>Queue role<select name="queue_role_id" defaultValue="credit_professional">{roles.map((role) => <option key={role.role_id} value={role.role_id}>{role.name}</option>)}</select></label><label>Initial assignee<select name="assignee_user_id"><option value="">Leave in role queue</option>{users.map((user) => <option key={user.user_id} value={user.user_id}>{user.display_name}</option>)}</select></label><label>Priority<select name="priority" defaultValue="medium"><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option></select></label><label>Operator-supplied due date<input name="due_date" type="date" /></label><button type="submit" className="workflow-span-2" disabled={actionStatus === 'loading'}>Create governed work item</button></form></section>}

      {view === 'identity' && <div className="workflow-two-column"><section className="workflow-panel"><div className="workflow-panel-heading"><div><span>Stable local identities</span><h2>People and operational roles</h2></div></div>{users.map((user) => <article className="workflow-user" key={user.user_id}><div><strong>{user.display_name}</strong><small>@{user.username} · {user.authentication_assurance.replaceAll('_', ' ')}</small></div><p>{user.roles.map((role) => role.name).join(' · ')}</p><span>Authority: {user.authority_status.replaceAll('_', ' ')}</span></article>)}</section><section className="workflow-panel">{coordinator ? <><div className="workflow-panel-heading"><div><span>Coordinator control</span><h2>Create local account</h2></div></div><form className="workflow-stacked-form" onSubmit={createUser}><label>Display name<input name="display_name" required minLength={2} /></label><label>Username<input name="username" required minLength={3} pattern="[A-Za-z0-9._-]+" /></label><label>Temporary password<input name="password" type="password" required minLength={12} autoComplete="new-password" /></label><fieldset><legend>Operational roles</legend>{roles.map((role) => <label key={role.role_id}><input type="checkbox" name="role_ids" value={role.role_id} /> <span><strong>{role.name}</strong><small>{role.description}</small></span></label>)}</fieldset><button type="submit" disabled={actionStatus === 'loading'}>Create account</button></form></> : <div className="workflow-empty"><strong>Coordinator control</strong><p>Your identity is authenticated, but you do not hold the operational Workflow Coordinator role.</p></div>}</section></div>}

      {view === 'notifications' && <section className="workflow-panel"><div className="workflow-panel-heading"><div><span>Durable local delivery</span><h2>In-app notifications</h2></div><strong>{notifications?.unread_count ?? 0} unread</strong></div><div className="workflow-notification-list">{notifications?.items.map((item) => <button type="button" key={item.notification_id} className={item.read_at ? 'is-read' : ''} onClick={() => !item.read_at && void markRead(item.notification_id)}><i className={`workflow-severity workflow-severity--${item.severity}`} /><div><strong>{item.title}</strong><p>{item.message}</p><small>{formatDateTime(item.created_at)} · {item.read_at ? 'Read' : 'Mark read'}</small></div></button>)}</div>{!notifications?.items.length && <div className="workflow-empty"><strong>No notifications</strong><p>Notifications are created by verified assignment and task-state events.</p></div>}</section>}

      {view === 'audit' && <div className="workflow-two-column"><section className="workflow-panel"><div className="workflow-panel-heading"><div><span>Boundary declaration</span><h2>What this foundation does</h2></div></div><ul className="workflow-boundary-list"><li>Authenticates a user account to this local ETOP instance.</li><li>Separates Person, user account, operational role, assignment, and authority.</li><li>Binds each task to an exact workflow definition version and context reference.</li><li>Uses optimistic concurrency and idempotency keys for controlled transitions.</li><li>Preserves append-only assignment/event evidence and a SHA-256 audit hash chain.</li></ul><h3>Intentionally unavailable</h3><ul className="workflow-boundary-list workflow-boundary-list--blocked"><li>Financial approval or decision authority</li><li>Approved authority matrices, SLA timers, and automatic escalation</li><li>ERP writes, payment, posting, hold/release, or cash-application execution</li><li>Enterprise identity-provider and multi-machine synchronization</li></ul></section><section className="workflow-panel"><div className="workflow-panel-heading"><div><span>Privileged evidence</span><h2>Audit integrity</h2></div>{coordinator && <strong className={auditIntegrity?.valid ? 'workflow-good' : 'workflow-bad'}>{auditIntegrity?.valid ? 'Verified' : 'Unavailable'}</strong>}</div>{coordinator ? <><p>{auditIntegrity?.checked_records ?? 0} records checked using {auditIntegrity?.algorithm.replaceAll('_', ' ')}.</p><div className="workflow-audit-list">{audit.map((event) => <article key={event.audit_id}><strong>{event.event_type}</strong><span>{event.subject_type} · {event.subject_id}</span><small>{formatDateTime(event.occurred_at)} · {event.record_hash.slice(0, 16)}…</small></article>)}</div></> : <div className="workflow-empty"><strong>Coordinator-only evidence view</strong><p>Audit query access is intentionally separate from ordinary work ownership.</p></div>}</section></div>}
    </section>
  )
}
