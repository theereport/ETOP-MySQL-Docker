import { type FormEvent, useCallback, useEffect, useState } from 'react'
import {
  createWorkflowTask,
  getWorkflowSession,
  getWorkflowTasks,
  getWorkflowToken,
  WORKFLOW_SESSION_EVENT,
  workflowIdempotencyKey,
} from './api'
import type {
  WorkflowCapability,
  WorkflowRoleId,
  WorkflowSession,
  WorkflowTask,
} from './types'
import './ContextWorkPanel.css'

type Props = {
  capability: WorkflowCapability
  contextType: string
  contextId: string
  contextLabel: string
  defaultTitle: string
}

const roleForCapability: Record<WorkflowCapability, WorkflowRoleId> = {
  credit_risk: 'credit_professional',
  accounts_payable: 'ap_professional',
  lockbox: 'workflow_observer',
  reporting: 'workflow_observer',
  platform: 'workflow_coordinator',
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : 'Unable to load linked governed work.'
}

export default function ContextWorkPanel({
  capability,
  contextType,
  contextId,
  contextLabel,
  defaultTitle,
}: Props) {
  const [session, setSession] = useState<WorkflowSession | null>(null)
  const [tasks, setTasks] = useState<WorkflowTask[]>([])
  const [status, setStatus] = useState<'idle' | 'loading' | 'ready' | 'error'>('idle')
  const [error, setError] = useState('')
  const [messageText, setMessageText] = useState('')

  const load = useCallback(async () => {
    if (!getWorkflowToken()) {
      setSession(null)
      setTasks([])
      setStatus('ready')
      return
    }
    setStatus('loading')
    setError('')
    try {
      const [nextSession, queue] = await Promise.all([
        getWorkflowSession(),
        getWorkflowTasks({ capability }),
      ])
      setSession(nextSession)
      setTasks(queue.items.filter((task) => (
        task.context_type === contextType && task.context_id === contextId
      )))
      setStatus('ready')
    } catch (loadError) {
      setStatus('error')
      setError(message(loadError))
    }
  }, [capability, contextId, contextType])

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void load(), 0)
    window.addEventListener(WORKFLOW_SESSION_EVENT, load)
    return () => {
      window.clearTimeout(timeoutId)
      window.removeEventListener(WORKFLOW_SESSION_EVENT, load)
    }
  }, [load])

  async function createLinkedTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!session) return
    const data = new FormData(event.currentTarget)
    const queueRole = roleForCapability[capability]
    const canSelfAssign = session.user.roles.some((role) => role.role_id === queueRole)
    setStatus('loading')
    setError('')
    setMessageText('')
    try {
      await createWorkflowTask({
        title: String(data.get('title') ?? ''),
        description: String(data.get('description') ?? ''),
        capability,
        context_type: contextType,
        context_id: contextId,
        context_label: contextLabel,
        queue_role_id: queueRole,
        assignee_user_id: canSelfAssign && data.get('assign_to_me') === 'yes'
          ? session.user.user_id
          : undefined,
        priority: String(data.get('priority')) as WorkflowTask['priority'],
        due_date: String(data.get('due_date') ?? '') || undefined,
        idempotency_key: workflowIdempotencyKey('context-work'),
      })
      setMessageText('Verified work item created. The underlying Credit/AP evidence and ERP were not changed.')
      event.currentTarget.reset()
      await load()
    } catch (createError) {
      setStatus('error')
      setError(message(createError))
    }
  }

  return (
    <section className="context-work-panel">
      <div className="context-work-heading">
        <div><span>Shared governed workflow</span><h3>Linked work and ownership</h3></div>
        <strong>{tasks.length} linked</strong>
      </div>
      {!session ? (
        <div className="context-work-boundary">
          <strong>Sign in through Work Management to create verified assignments.</strong>
          <p>Existing operator-entered names remain historical evidence and are not silently converted into authenticated identities.</p>
        </div>
      ) : (
        <>
          <p className="context-work-session">Signed in as <strong>{session.user.display_name}</strong> · assignment establishes work ownership only.</p>
          <div className="context-work-list">
            {tasks.map((task) => <article key={task.task_id}><div><strong>{task.title}</strong><span>{task.state.replaceAll('_', ' ')} · {task.priority}</span></div><p>{task.assignee?.display_name ?? task.queue_role.name}</p><small>{task.task_id} · workflow {task.definition_version}</small></article>)}
            {!tasks.length && <p>No governed work is linked to this exact context.</p>}
          </div>
          <form onSubmit={createLinkedTask}>
            <label>Work title<input name="title" defaultValue={defaultTitle} required minLength={3} maxLength={180} /></label>
            <label>Priority<select name="priority" defaultValue="medium"><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="critical">Critical</option></select></label>
            <label className="context-work-wide">Follow-up context<textarea name="description" maxLength={2000} /></label>
            <label>Due date<input name="due_date" type="date" /></label>
            <label className="context-work-check"><input name="assign_to_me" type="checkbox" value="yes" /> Assign to me when role eligible</label>
            <button type="submit" disabled={status === 'loading'}>{status === 'loading' ? 'Saving…' : 'Create linked work'}</button>
          </form>
        </>
      )}
      {error && <p className="context-work-error">{error}</p>}
      {messageText && <p className="context-work-success">{messageText}</p>}
    </section>
  )
}
