import {
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import {
  getWorkflowSession,
  getWorkflowToken,
  getWorkflowUsers,
  WORKFLOW_SESSION_EVENT,
  workflowIdempotencyKey,
} from '../workflow-foundation'
import type {
  WorkflowSession,
  WorkflowUser,
} from '../workflow-foundation'
import {
  createCloseControl,
  createCloseCycle,
  createClosePreparation,
  createCloseReview,
  getCloseControlEvents,
  getCloseCycle,
  getCloseCycles,
  getFinancialCloseGovernance,
} from './api'
import type {
  CloseControlEventList,
  CloseControlState,
  CloseCycleDetail,
  CloseCycleSummary,
  FinancialCloseGovernance,
  FinancialCloseWorkspaceProps,
} from './types'
import ClosePlanningTemplates from './ClosePlanningTemplates'
import './FinancialCloseWorkspace.css'

type AsyncStatus = 'idle' | 'loading' | 'ready' | 'error'
type WorkspaceView =
  | 'planning_templates'
  | 'work_plan'
  | 'evidence'
  | 'governance'

const controlStateLabel: Record<CloseControlState, string> = {
  not_started: 'Not started',
  awaiting_review: 'Evidence recorded · review pending',
  attention_required: 'Attention required',
  evidence_sufficient: 'Evidence sufficient',
  stale: 'Stale review · re-review required',
}

function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : 'The local Financial Close request could not be completed.'
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function formatDate(value: string | null): string {
  if (!value) return 'Not scheduled'
  const parsed = new Date(`${value}T00:00:00`)
  return Number.isNaN(parsed.valueOf())
    ? value
    : parsed.toLocaleDateString()
}

function formatDateTime(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.valueOf())
    ? value
    : parsed.toLocaleString()
}

function isCoordinator(session: WorkflowSession | null): boolean {
  return session?.user.roles.some(
    (role) => role.role_id === 'workflow_coordinator',
  ) ?? false
}

export default function FinancialCloseWorkspace({
  onOpenWorkManagement,
}: FinancialCloseWorkspaceProps) {
  const [session, setSession] = useState<WorkflowSession | null>(null)
  const [users, setUsers] = useState<WorkflowUser[]>([])
  const [governance, setGovernance] = useState<FinancialCloseGovernance | null>(null)
  const [cycles, setCycles] = useState<CloseCycleSummary[]>([])
  const [selectedCycleId, setSelectedCycleId] = useState('')
  const [cycle, setCycle] = useState<CloseCycleDetail | null>(null)
  const [selectedControlId, setSelectedControlId] = useState('')
  const [controlEvents, setControlEvents] = useState<CloseControlEventList | null>(null)
  const [view, setView] = useState<WorkspaceView>('work_plan')
  const [rootStatus, setRootStatus] = useState<AsyncStatus>('loading')
  const [cycleStatus, setCycleStatus] = useState<AsyncStatus>('idle')
  const [eventStatus, setEventStatus] = useState<AsyncStatus>('idle')
  const [actionStatus, setActionStatus] = useState<AsyncStatus>('idle')
  const [error, setError] = useState('')
  const [actionMessage, setActionMessage] = useState('')
  const [preparerUserId, setPreparerUserId] = useState('')
  const [reviewerUserId, setReviewerUserId] = useState('')
  const rootGeneration = useRef(0)
  const cycleGeneration = useRef(0)
  const eventGeneration = useRef(0)
  const rootAbort = useRef<AbortController | null>(null)
  const cycleAbort = useRef<AbortController | null>(null)
  const eventAbort = useRef<AbortController | null>(null)

  const activeUsers = useMemo(
    () => users.filter((user) => user.status === 'active'),
    [users],
  )
  const coordinator = isCoordinator(session)
  const selectedControl = useMemo(
    () => cycle?.controls.find(
      (control) => control.control_id === selectedControlId,
    ) ?? null,
    [cycle, selectedControlId],
  )
  const signedInUserId = session?.user.user_id ?? ''
  const exactPreparer = selectedControl?.preparer.user_id === signedInUserId
  const exactReviewer = selectedControl?.reviewer.user_id === signedInUserId
  const reviewAvailable = selectedControl !== null
    && selectedControl.evidence_status !== 'not_recorded'
    && selectedControl.review_currency !== 'current'

  const loadRoot = useCallback(async () => {
    rootAbort.current?.abort()
    const controller = new AbortController()
    rootAbort.current = controller
    const generation = rootGeneration.current + 1
    rootGeneration.current = generation
    setError('')

    if (!getWorkflowToken()) {
      setSession(null)
      setUsers([])
      setGovernance(null)
      setCycles([])
      setSelectedCycleId('')
      setCycle(null)
      setRootStatus('ready')
      return
    }

    setRootStatus('loading')
    try {
      const [nextSession, nextUsers, nextGovernance, nextCycles] = await Promise.all([
        getWorkflowSession(controller.signal),
        getWorkflowUsers(controller.signal),
        getFinancialCloseGovernance(controller.signal),
        getCloseCycles(controller.signal),
      ])
      if (controller.signal.aborted || rootGeneration.current !== generation) return
      setSession(nextSession)
      setUsers(nextUsers)
      setGovernance(nextGovernance)
      setCycles(nextCycles.items)
      setSelectedCycleId((current) => (
        current && nextCycles.items.some((item) => item.cycle_id === current)
          ? current
          : nextCycles.items[0]?.cycle_id ?? ''
      ))
      setRootStatus('ready')
    } catch (loadError) {
      if (isAbortError(loadError) || rootGeneration.current !== generation) return
      setRootStatus('error')
      setError(errorMessage(loadError))
    }
  }, [])

  const loadCycle = useCallback(async (cycleId: string) => {
    cycleAbort.current?.abort()
    const controller = new AbortController()
    cycleAbort.current = controller
    const generation = cycleGeneration.current + 1
    cycleGeneration.current = generation
    setCycleStatus('loading')
    setError('')
    try {
      const detail = await getCloseCycle(cycleId, controller.signal)
      if (controller.signal.aborted || cycleGeneration.current !== generation) return
      setCycle(detail)
      setSelectedControlId((current) => (
        current && detail.controls.some((item) => item.control_id === current)
          ? current
          : detail.controls[0]?.control_id ?? ''
      ))
      setCycleStatus('ready')
    } catch (loadError) {
      if (isAbortError(loadError) || cycleGeneration.current !== generation) return
      setCycle(null)
      setCycleStatus('error')
      setError(errorMessage(loadError))
    }
  }, [])

  const loadControlEvents = useCallback(async (
    cycleId: string,
    controlId: string,
  ) => {
    eventAbort.current?.abort()
    const controller = new AbortController()
    eventAbort.current = controller
    const generation = eventGeneration.current + 1
    eventGeneration.current = generation
    setEventStatus('loading')
    try {
      const result = await getCloseControlEvents(
        cycleId,
        controlId,
        controller.signal,
      )
      if (controller.signal.aborted || eventGeneration.current !== generation) return
      setControlEvents(result)
      setEventStatus('ready')
    } catch (loadError) {
      if (isAbortError(loadError) || eventGeneration.current !== generation) return
      setControlEvents(null)
      setEventStatus('error')
      setError(errorMessage(loadError))
    }
  }, [])

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void loadRoot(), 0)
    window.addEventListener(WORKFLOW_SESSION_EVENT, loadRoot)
    return () => {
      window.clearTimeout(timeoutId)
      window.removeEventListener(WORKFLOW_SESSION_EVENT, loadRoot)
      rootAbort.current?.abort()
    }
  }, [loadRoot])

  useEffect(() => {
    if (!selectedCycleId || !session) {
      return
    }
    const timeoutId = window.setTimeout(
      () => void loadCycle(selectedCycleId),
      0,
    )
    return () => {
      window.clearTimeout(timeoutId)
      cycleAbort.current?.abort()
    }
  }, [loadCycle, selectedCycleId, session])

  useEffect(() => {
    if (!selectedCycleId || !selectedControlId || !session) {
      return
    }
    const timeoutId = window.setTimeout(
      () => void loadControlEvents(selectedCycleId, selectedControlId),
      0,
    )
    return () => {
      window.clearTimeout(timeoutId)
      eventAbort.current?.abort()
    }
  }, [loadControlEvents, selectedControlId, selectedCycleId, session])

  useEffect(() => () => {
    rootAbort.current?.abort()
    cycleAbort.current?.abort()
    eventAbort.current?.abort()
  }, [])

  async function refreshCurrent(message = 'Current local close evidence reloaded.') {
    await loadRoot()
    if (selectedCycleId) await loadCycle(selectedCycleId)
    if (selectedCycleId && selectedControlId) {
      await loadControlEvents(selectedCycleId, selectedControlId)
    }
    setActionMessage(message)
  }

  async function submitCycle(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!coordinator) return
    const form = event.currentTarget
    const data = new FormData(form)
    const periodStart = String(data.get('period_start') ?? '')
    const periodEnd = String(data.get('period_end') ?? '')
    if (periodEnd < periodStart) {
      setError('Period end must be on or after period start.')
      return
    }
    setActionStatus('loading')
    setError('')
    setActionMessage('')
    try {
      const detail = await createCloseCycle({
        entity_label: String(data.get('entity_label') ?? ''),
        period_label: String(data.get('period_label') ?? ''),
        period_start: periodStart,
        period_end: periodEnd,
        target_completion_date: String(data.get('target_completion_date') ?? '') || undefined,
        description: String(data.get('description') ?? ''),
        idempotency_key: workflowIdempotencyKey('financial-close-cycle'),
      })
      form.reset()
      setSelectedCycleId(detail.cycle_id)
      setCycle(detail)
      await loadRoot()
      setActionStatus('ready')
      setActionMessage('Local close work cycle created. No ERP period, books, approval, or posting state changed.')
    } catch (actionError) {
      setActionStatus('error')
      setError(errorMessage(actionError))
    }
  }

  async function submitControl(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!coordinator || !selectedCycleId) return
    if (!preparerUserId || !reviewerUserId) {
      setError('Select one verified preparer and one verified reviewer.')
      return
    }
    if (preparerUserId === reviewerUserId) {
      setError('Preparer and reviewer must be different verified local accounts.')
      return
    }
    const form = event.currentTarget
    const data = new FormData(form)
    setActionStatus('loading')
    setError('')
    setActionMessage('')
    try {
      const created = await createCloseControl(selectedCycleId, {
        title: String(data.get('title') ?? ''),
        description: String(data.get('description') ?? ''),
        planned_date: String(data.get('planned_date') ?? '') || undefined,
        preparer_user_id: preparerUserId,
        reviewer_user_id: reviewerUserId,
        idempotency_key: workflowIdempotencyKey('financial-close-control'),
      })
      form.reset()
      setPreparerUserId('')
      setReviewerUserId('')
      setSelectedControlId(created.control_id)
      await refreshCurrent('Close control added with distinct verified preparer and reviewer. Authority remains none.')
      setActionStatus('ready')
    } catch (actionError) {
      setActionStatus('error')
      setError(errorMessage(actionError))
    }
  }

  async function submitPreparation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedControl || !cycle || !exactPreparer) return
    const form = event.currentTarget
    const data = new FormData(form)
    const disposition = String(data.get('disposition')) as
      | 'reference_recorded'
      | 'missing'
      | 'unavailable'
    const evidenceReference = String(data.get('evidence_reference') ?? '').trim()
    if (disposition === 'reference_recorded' && !evidenceReference) {
      setError('An exact evidence reference is required when recording prepared evidence.')
      return
    }
    setActionStatus('loading')
    setError('')
    setActionMessage('')
    try {
      await createClosePreparation(cycle.cycle_id, selectedControl.control_id, {
        disposition,
        evidence_reference: evidenceReference || undefined,
        note: String(data.get('note') ?? ''),
        expected_control_version: selectedControl.version,
        idempotency_key: workflowIdempotencyKey('financial-close-preparation'),
      })
      form.reset()
      await refreshCurrent('Append-only preparation evidence recorded. No close, approval, or posting action occurred.')
      setActionStatus('ready')
    } catch (actionError) {
      setActionStatus('error')
      setError(errorMessage(actionError))
    }
  }

  async function submitReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!selectedControl || !cycle || !exactReviewer) return
    const form = event.currentTarget
    const data = new FormData(form)
    setActionStatus('loading')
    setError('')
    setActionMessage('')
    try {
      await createCloseReview(cycle.cycle_id, selectedControl.control_id, {
        disposition: String(data.get('disposition')) as
          | 'evidence_sufficient'
          | 'needs_information'
          | 'not_ready'
          | 'deferred',
        note: String(data.get('note') ?? ''),
        expected_control_version: selectedControl.version,
        idempotency_key: workflowIdempotencyKey('financial-close-review'),
      })
      form.reset()
      await refreshCurrent('Append-only evidence-readiness review recorded. This is not approval or period close.')
      setActionStatus('ready')
    } catch (actionError) {
      setActionStatus('error')
      setError(errorMessage(actionError))
    }
  }

  async function handleTemplateCycleCreated(detail: CloseCycleDetail) {
    await loadRoot()
    setSelectedCycleId(detail.cycle_id)
    setCycle(detail)
    setSelectedControlId(detail.controls[0]?.control_id ?? '')
    setView('work_plan')
    setActionMessage(
      `Cycle snapshotted from immutable local template version ${detail.template_lineage?.template_version ?? ''}. Dates remain planning-only; no financial or ERP action occurred.`,
    )
  }

  if (rootStatus === 'loading') {
    return <section className="fc-workspace"><div className="fc-state">Loading local Financial Close evidence…</div></section>
  }

  if (!session && rootStatus === 'error' && getWorkflowToken()) {
    return (
      <section className="fc-workspace">
        <div className="fc-auth-boundary">
          <span>CONTROLLED LOAD FAILURE</span>
          <h1>Financial Close evidence is unavailable</h1>
          <p>{error || 'The authenticated Financial Close evidence could not be loaded.'}</p>
          <button type="button" onClick={() => void loadRoot()}>Retry authenticated load</button>
        </div>
      </section>
    )
  }

  if (!session) {
    return (
      <section className="fc-workspace">
        <div className="fc-auth-boundary">
          <span>AUTHENTICATED LOCAL WORK</span>
          <h1>Financial Close &amp; Controller Intelligence</h1>
          <p>Sign in through Work Management before viewing or recording close-readiness evidence. The shell identity shown elsewhere in ETOP is not financial authority.</p>
          {onOpenWorkManagement && <button type="button" onClick={onOpenWorkManagement}>Open Work Management</button>}
        </div>
      </section>
    )
  }

  return (
    <section className="fc-workspace">
      <header className="fc-header">
        <div>
          <span>FINANCIAL CLOSE · INCREMENT 2</span>
          <h1>Close evidence readiness</h1>
          <p>Reuse immutable local planning drafts, manually snapshot one version into a period cycle, and preserve preparation evidence and independent review using verified local identities.</p>
        </div>
        <div className="fc-boundary-card">
          <strong>Local evidence readiness only</strong>
          <span>ERP period state: Unavailable</span>
          <span>Close / approval / posting effect: None</span>
          <small>Signed in as {session.user.display_name}</small>
        </div>
      </header>

      <nav className="fc-tabs" aria-label="Financial Close views">
        <button type="button" className={view === 'planning_templates' ? 'active' : ''} onClick={() => setView('planning_templates')}>Planning templates</button>
        <button type="button" className={view === 'work_plan' ? 'active' : ''} onClick={() => setView('work_plan')}>Close work plan</button>
        <button type="button" className={view === 'evidence' ? 'active' : ''} onClick={() => setView('evidence')}>Evidence &amp; review</button>
        <button type="button" className={view === 'governance' ? 'active' : ''} onClick={() => setView('governance')}>Coverage &amp; boundaries</button>
        <button type="button" className="fc-refresh" onClick={() => void refreshCurrent()} disabled={actionStatus === 'loading'}>Refresh</button>
      </nav>

      {error && <div className="fc-message error"><strong>Unable to complete the request</strong><span>{error}</span><button type="button" onClick={() => void refreshCurrent()}>Reload current evidence</button></div>}
      {actionMessage && <div className="fc-message success">{actionMessage}</div>}

      {view === 'planning_templates' && (
        <ClosePlanningTemplates
          activeUsers={activeUsers}
          coordinator={coordinator}
          onCycleCreated={handleTemplateCycleCreated}
        />
      )}

      {view === 'work_plan' && (
        <div className="fc-layout">
          <aside className="fc-cycle-panel">
            <div className="fc-panel-heading"><div><span>PERIOD WORK</span><h2>Close cycles</h2></div><b>{cycles.length}</b></div>
            <div className="fc-cycle-list">
              {cycles.map((item) => (
                <button type="button" key={item.cycle_id} className={item.cycle_id === selectedCycleId ? 'active' : ''} onClick={() => { setSelectedCycleId(item.cycle_id); setSelectedControlId('') }}>
                  <strong>{item.period_label}</strong>
                  <span>{item.entity_label} · {formatDate(item.period_start)} – {formatDate(item.period_end)}</span>
                  <small>{item.readiness.replaceAll('_', ' ')} · {item.control_counts.evidence_sufficient} of {item.control_counts.total} controls evidence-sufficient</small>
                </button>
              ))}
              {!cycles.length && <div className="fc-empty"><strong>No close work cycles exist.</strong><p>A Workflow Coordinator may create the first local evidence-readiness cycle. ETOP does not create a placeholder calendar.</p></div>}
            </div>

            {coordinator ? (
              <form className="fc-form" onSubmit={submitCycle}>
                <h3>Create local close cycle</h3>
                <label>Entity label · operator supplied / unverified<input name="entity_label" required minLength={2} maxLength={120} placeholder="Company or reporting entity" /></label>
                <label>Period label<input name="period_label" required minLength={3} maxLength={120} placeholder="Example: August 2026" /></label>
                <div className="fc-form-row"><label>Period start<input name="period_start" type="date" required /></label><label>Period end<input name="period_end" type="date" required /></label></div>
                <label>Operator target date<input name="target_completion_date" type="date" /></label>
                <label>Description<textarea name="description" maxLength={1000} /></label>
                <button type="submit" disabled={actionStatus === 'loading'}>Create evidence-readiness cycle</button>
                <small>Creates local coordination evidence only. It does not open or close an ERP period.</small>
              </form>
            ) : (
              <div className="fc-role-boundary"><strong>Coordinator setup</strong><p>Your authenticated account can perform only the exact preparer or reviewer work assigned to it. Cycle and control setup requires the operational Workflow Coordinator role and grants no financial authority.</p></div>
            )}
          </aside>

          <main className="fc-main-panel">
            {cycleStatus === 'loading' && <div className="fc-state">Loading selected cycle…</div>}
            {cycleStatus === 'error' && <div className="fc-state">The selected cycle could not be loaded.</div>}
            {cycleStatus === 'ready' && cycle && (
              <>
                <div className="fc-cycle-title"><div><span>{cycle.entity_label} · operator supplied / unverified · {formatDate(cycle.period_start)} – {formatDate(cycle.period_end)}</span><h2>{cycle.period_label}</h2><p>{cycle.description || 'No operator description recorded.'}</p>{cycle.template_lineage && <small>Snapshot {cycle.template_lineage.snapshot_id} · {cycle.template_lineage.template_title} version {cycle.template_lineage.template_version} · anchor {formatDate(cycle.template_lineage.calendar_anchor_date)} · hash {cycle.template_lineage.snapshot_sha256.slice(0, 12)}…</small>}</div><div><strong>Local readiness: {cycle.readiness.replaceAll('_', ' ')}</strong><span>Target {formatDate(cycle.target_completion_date)}</span><small>ERP period state unavailable</small></div></div>
                <div className="fc-count-grid">
                  <div><span>Total controls</span><strong>{cycle.control_counts.total}</strong></div>
                  <div><span>Not started</span><strong>{cycle.control_counts.not_started}</strong></div>
                  <div><span>Attention needed</span><strong>{cycle.control_counts.attention_required + cycle.control_counts.stale}</strong></div>
                  <div><span>Awaiting review</span><strong>{cycle.control_counts.awaiting_review}</strong></div>
                  <div><span>Evidence-sufficient</span><strong>{cycle.control_counts.evidence_sufficient}</strong></div>
                </div>

                <div className="fc-panel-heading"><div><span>DATE-ORDERED MANIFEST</span><h2>Control work plan</h2></div><small>Dates are operator supplied, not an approved SLA.</small></div>
                <div className="fc-control-table">
                  <div className="fc-control-row header"><span>Control</span><span>Planned</span><span>Preparer / reviewer</span><span>Evidence state</span></div>
                  {cycle.controls.map((control) => (
                    <button type="button" key={control.control_id} className={`fc-control-row ${control.control_id === selectedControlId ? 'active' : ''}`} onClick={() => { setSelectedControlId(control.control_id); setView('evidence') }}>
                      <span><strong>{control.title}</strong><small>{control.description || control.control_id}</small></span>
                      <span>{formatDate(control.planned_date)}</span>
                      <span><strong>{control.preparer.display_name}</strong><small>Review: {control.reviewer.display_name}</small></span>
                      <span className={`fc-state-pill ${control.state}`}>{controlStateLabel[control.state]}</span>
                    </button>
                  ))}
                  {!cycle.controls.length && <div className="fc-empty"><strong>No control items are recorded.</strong><p>Add the first real close control with distinct verified preparer and reviewer identities.</p></div>}
                </div>

                {coordinator && (
                  <form className="fc-form fc-control-form" onSubmit={submitControl}>
                    <h3>Add close control</h3>
                    {activeUsers.length < 2 && <div className="fc-role-boundary"><strong>Two distinct active accounts are required.</strong><p>Create or activate a second verified local account through Work Management before assigning preparer and reviewer ownership.</p>{onOpenWorkManagement && <button type="button" onClick={onOpenWorkManagement}>Open Work Management</button>}</div>}
                    <div className="fc-form-row"><label>Control title<input name="title" required minLength={3} maxLength={180} /></label><label>Planned date<input name="planned_date" type="date" /></label></div>
                    <label>Description<textarea name="description" maxLength={2000} /></label>
                    <div className="fc-form-row">
                      <label>Verified preparer<select value={preparerUserId} onChange={(event) => setPreparerUserId(event.target.value)} required><option value="">Select account</option>{activeUsers.filter((user) => user.user_id !== reviewerUserId).map((user) => <option key={user.user_id} value={user.user_id}>{user.display_name} (@{user.username})</option>)}</select></label>
                      <label>Distinct verified reviewer<select value={reviewerUserId} onChange={(event) => setReviewerUserId(event.target.value)} required><option value="">Select different account</option>{activeUsers.filter((user) => user.user_id !== preparerUserId).map((user) => <option key={user.user_id} value={user.user_id}>{user.display_name} (@{user.username})</option>)}</select></label>
                    </div>
                    <button type="submit" disabled={actionStatus === 'loading' || activeUsers.length < 2 || !preparerUserId || !reviewerUserId}>Add controlled work item</button>
                    <small>Assignment identifies accountable work only. Neither identity receives close, approval, or posting authority.</small>
                  </form>
                )}
              </>
            )}
            {!selectedCycleId && cycles.length > 0 && <div className="fc-state">Select a close cycle.</div>}
          </main>
        </div>
      )}

      {view === 'evidence' && (
        <div className="fc-evidence-layout">
          <aside className="fc-control-picker">
            <div className="fc-panel-heading"><div><span>SELECTED CYCLE</span><h2>{cycle?.period_label ?? 'No cycle selected'}</h2></div></div>
            {(cycle?.controls ?? []).map((control) => <button type="button" key={control.control_id} className={control.control_id === selectedControlId ? 'active' : ''} onClick={() => setSelectedControlId(control.control_id)}><strong>{control.title}</strong><span>{controlStateLabel[control.state]}</span><small>{formatDate(control.planned_date)}</small></button>)}
            {!cycle?.controls.length && <div className="fc-empty">No recorded controls are available for evidence review.</div>}
          </aside>

          <main className="fc-evidence-main">
            {!selectedControl && <div className="fc-state">Select a control item to inspect its exact preparation and review evidence.</div>}
            {selectedControl && (
              <>
                <div className="fc-control-detail-heading"><div><span>{selectedControl.control_id} · version {selectedControl.version}</span><h2>{selectedControl.title}</h2><p>{selectedControl.description || 'No description recorded.'}</p></div><span className={`fc-state-pill ${selectedControl.state}`}>{controlStateLabel[selectedControl.state]}</span></div>
                <div className="fc-identity-grid"><div><span>Exact preparer</span><strong>{selectedControl.preparer.display_name}</strong><small>@{selectedControl.preparer.username}</small></div><div><span>Exact reviewer</span><strong>{selectedControl.reviewer.display_name}</strong><small>@{selectedControl.reviewer.username}</small></div><div><span>Planned date</span><strong>{formatDate(selectedControl.planned_date)}</strong><small>{selectedControl.template_lineage ? `Snapshot offset ${selectedControl.template_lineage.planned_offset_days >= 0 ? '+' : ''}${selectedControl.template_lineage.planned_offset_days} days` : 'Operator supplied'}</small></div><div><span>Evidence observation</span><strong>{selectedControl.evidence_status.replaceAll('_', ' ')}</strong><small>Append-only preparer evidence</small></div><div><span>Review currency</span><strong>{selectedControl.review_currency.replaceAll('_', ' ')}</strong><small>Current only for the exact prepared version</small></div>{selectedControl.template_lineage && <div><span>Immutable template source</span><strong>Version {selectedControl.template_lineage.template_version}</strong><small>{selectedControl.template_lineage.template_item_id} · {selectedControl.template_lineage.template_item_sha256.slice(0, 12)}…</small></div>}</div>

                <div className="fc-action-grid">
                  <section>
                    <h3>Preparation evidence</h3>
                    {exactPreparer ? (
                      <form className="fc-form" onSubmit={submitPreparation}>
                        <label>Evidence observation<select name="disposition" defaultValue="reference_recorded"><option value="reference_recorded">Exact evidence reference recorded</option><option value="missing">Required evidence is missing</option><option value="unavailable">Required evidence is unavailable</option></select></label>
                        <label>Exact evidence reference<input name="evidence_reference" maxLength={500} placeholder="Document, report, schedule, or governed local reference" /></label>
                        <label>Preparer note<textarea name="note" required minLength={3} maxLength={2000} /></label>
                        <button type="submit" disabled={actionStatus === 'loading'}>Record append-only preparation</button>
                      </form>
                    ) : <div className="fc-role-boundary"><strong>Assigned preparer only</strong><p>Signed in as {session.user.display_name}. Only {selectedControl.preparer.display_name} may append preparation evidence to this control.</p></div>}
                  </section>
                  <section>
                    <h3>Independent evidence review</h3>
                    {exactReviewer ? (
                      <form className="fc-form" onSubmit={submitReview}>
                        <label>Review disposition<select name="disposition" defaultValue="needs_information"><option value="evidence_sufficient" disabled={selectedControl.evidence_status !== 'reference_recorded'}>Evidence sufficient for later close review</option><option value="needs_information">Needs information</option><option value="not_ready">Not ready for close review</option><option value="deferred">Deferred</option></select></label>
                        <label>Reviewer note<textarea name="note" required minLength={3} maxLength={2000} /></label>
                        <button type="submit" disabled={actionStatus === 'loading' || !reviewAvailable}>Record append-only review</button>
                        {!reviewAvailable && <small>A new preparation observation is required before another reviewer disposition can be recorded.</small>}
                        {selectedControl.evidence_status !== 'reference_recorded' && reviewAvailable && <small>Missing or unavailable evidence may be reviewed for follow-up, but it cannot be marked evidence sufficient.</small>}
                      </form>
                    ) : <div className="fc-role-boundary"><strong>Assigned reviewer only</strong><p>Signed in as {session.user.display_name}. Only {selectedControl.reviewer.display_name} may record the independent evidence-readiness review.</p></div>}
                  </section>
                </div>

                <section className="fc-timeline-panel">
                  <div className="fc-panel-heading"><div><span>APPEND-ONLY TRACE</span><h2>Control evidence timeline</h2></div>{controlEvents?.integrity && <strong className={controlEvents.integrity.valid ? 'valid' : 'invalid'}>{controlEvents.integrity.valid ? 'Integrity verified' : 'Integrity failed'}</strong>}</div>
                  {eventStatus === 'loading' && <div className="fc-state compact">Loading exact event history…</div>}
                  {eventStatus === 'error' && <div className="fc-state compact">Event history is unavailable.</div>}
                  <div className="fc-timeline">
                    {(controlEvents?.items ?? []).map((item) => <article key={item.event_id}><i /><div><strong>{item.event_type.replaceAll('_', ' ')}</strong><p>{Object.entries(item.details).map(([key, value]) => `${key.replaceAll('_', ' ')}: ${String(value)}`).join(' · ') || 'No additional event detail.'}</p><small>{item.actor.display_name} · {formatDateTime(item.occurred_at)} · hash {item.record_hash.slice(0, 12)}…</small></div></article>)}
                    {eventStatus === 'ready' && !controlEvents?.items.length && <div className="fc-empty">No event evidence has been recorded for this control.</div>}
                  </div>
                </section>
              </>
            )}
          </main>
        </div>
      )}

      {view === 'governance' && (
        <div className="fc-governance-grid">
          <section><span>SOURCE COVERAGE</span><h2>What Increment 2 can prove</h2>{governance?.source_coverage.map((item) => <article key={item.key}><strong>{item.label}</strong><b>{item.status.replaceAll('_', ' ')}</b><p>{item.explanation}</p></article>)}</section>
          <section><span>AUTHORITY BOUNDARY</span><h2>What this workspace cannot do</h2><div className="fc-boundary-list"><p><strong>ERP / GL period state</strong><span>Unavailable</span></p><p><strong>Books close effect</strong><span>None</span></p><p><strong>Approval effect</strong><span>None</span></p><p><strong>Posting effect</strong><span>None</span></p><p><strong>ERP write</strong><span>False</span></p></div>{governance?.authority.statements.map((statement) => <p key={statement}>{statement}</p>)}</section>
          <section className="fc-deferred"><span>DEFERRED CAPABILITIES</span><h2>Later governed increments</h2>{governance?.deferred_capabilities.map((item) => <article key={item.key}><strong>{item.label}</strong><p>{item.reason}</p></article>)}</section>
        </div>
      )}
    </section>
  )
}
