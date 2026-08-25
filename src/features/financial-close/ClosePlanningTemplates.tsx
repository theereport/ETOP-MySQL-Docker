import {
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import type { WorkflowUser } from '../workflow-foundation'
import { workflowIdempotencyKey } from '../workflow-foundation'
import {
  createCloseTemplate,
  createCloseTemplateVersion,
  getCloseTemplate,
  getCloseTemplates,
  instantiateCloseTemplate,
} from './api'
import type {
  CloseCycleDetail,
  CloseTemplateDetail,
  CloseTemplateSummary,
  CreateCloseTemplateItemRequest,
} from './types'
import './ClosePlanningTemplates.css'

type AsyncStatus = 'idle' | 'loading' | 'ready' | 'error'

type DraftItem = CreateCloseTemplateItemRequest & {
  local_id: string
}

type ClosePlanningTemplatesProps = {
  activeUsers: WorkflowUser[]
  coordinator: boolean
  onCycleCreated: (cycle: CloseCycleDetail) => Promise<void> | void
}

function localId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`
}

function blankItem(): DraftItem {
  return {
    local_id: localId(),
    title: '',
    description: '',
    planned_offset_days: 0,
    preparer_user_id: '',
    reviewer_user_id: '',
  }
}

function errorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : 'The local close-planning request could not be completed.'
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function proposedDate(anchor: string, offset: number): string {
  if (!anchor) return 'Choose anchor date'
  const parsed = new Date(`${anchor}T00:00:00Z`)
  if (Number.isNaN(parsed.valueOf())) return 'Invalid anchor'
  parsed.setUTCDate(parsed.getUTCDate() + offset)
  return parsed.toISOString().slice(0, 10)
}

function requestItems(items: DraftItem[]): CreateCloseTemplateItemRequest[] {
  return items.map((item) => ({
    title: item.title,
    description: item.description,
    planned_offset_days: item.planned_offset_days,
    preparer_user_id: item.preparer_user_id,
    reviewer_user_id: item.reviewer_user_id,
  }))
}

export default function ClosePlanningTemplates({
  activeUsers,
  coordinator,
  onCycleCreated,
}: ClosePlanningTemplatesProps) {
  const [templates, setTemplates] = useState<CloseTemplateSummary[]>([])
  const [selectedTemplateId, setSelectedTemplateId] = useState('')
  const [template, setTemplate] = useState<CloseTemplateDetail | null>(null)
  const [selectedVersion, setSelectedVersion] = useState(0)
  const [listStatus, setListStatus] = useState<AsyncStatus>('loading')
  const [detailStatus, setDetailStatus] = useState<AsyncStatus>('idle')
  const [actionStatus, setActionStatus] = useState<AsyncStatus>('idle')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [createItems, setCreateItems] = useState<DraftItem[]>([blankItem()])
  const [revisionOpen, setRevisionOpen] = useState(false)
  const [revisionTemplateId, setRevisionTemplateId] = useState('')
  const [revisionTitle, setRevisionTitle] = useState('')
  const [revisionDescription, setRevisionDescription] = useState('')
  const [revisionItems, setRevisionItems] = useState<DraftItem[]>([])
  const [calendarAnchor, setCalendarAnchor] = useState('')
  const listAbort = useRef<AbortController | null>(null)
  const detailAbort = useRef<AbortController | null>(null)
  const listGeneration = useRef(0)
  const detailGeneration = useRef(0)
  const createIdempotencyKeyRef = useRef<string | null>(null)
  const instantiateIdempotencyKeyRef = useRef<string | null>(null)

  const version = useMemo(
    () => template?.versions.find((item) => item.version === selectedVersion)
      ?? template?.versions.at(-1)
      ?? null,
    [selectedVersion, template],
  )

  const loadTemplates = useCallback(async (preferredId = '') => {
    listAbort.current?.abort()
    const controller = new AbortController()
    listAbort.current = controller
    const generation = listGeneration.current + 1
    listGeneration.current = generation
    setListStatus('loading')
    setError('')
    try {
      const response = await getCloseTemplates(controller.signal)
      if (controller.signal.aborted || generation !== listGeneration.current) return
      setTemplates(response.items)
      if (!response.items.length) {
        setTemplate(null)
        setDetailStatus('idle')
      }
      setSelectedTemplateId((current) => {
        const candidate = preferredId || current
        return candidate && response.items.some((item) => item.template_id === candidate)
          ? candidate
          : response.items[0]?.template_id ?? ''
      })
      setListStatus('ready')
    } catch (loadError) {
      if (isAbortError(loadError) || generation !== listGeneration.current) return
      setListStatus('error')
      setError(errorMessage(loadError))
    }
  }, [])

  const loadTemplate = useCallback(async (templateId: string) => {
    detailAbort.current?.abort()
    const controller = new AbortController()
    detailAbort.current = controller
    const generation = detailGeneration.current + 1
    detailGeneration.current = generation
    setDetailStatus('loading')
    setError('')
    try {
      const detail = await getCloseTemplate(templateId, controller.signal)
      if (controller.signal.aborted || generation !== detailGeneration.current) return
      setTemplate(detail)
      setSelectedVersion((current) => (
        detail.versions.some((item) => item.version === current)
          ? current
          : detail.latest_version
      ))
      setDetailStatus('ready')
    } catch (loadError) {
      if (isAbortError(loadError) || generation !== detailGeneration.current) return
      setTemplate(null)
      setDetailStatus('error')
      setError(errorMessage(loadError))
    }
  }, [])

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void loadTemplates(), 0)
    return () => {
      window.clearTimeout(timeoutId)
      listAbort.current?.abort()
    }
  }, [loadTemplates])

  useEffect(() => {
    if (!selectedTemplateId) {
      return
    }
    const timeoutId = window.setTimeout(
      () => void loadTemplate(selectedTemplateId),
      0,
    )
    return () => {
      window.clearTimeout(timeoutId)
      detailAbort.current?.abort()
    }
  }, [loadTemplate, selectedTemplateId])

  function updateItem(
    items: DraftItem[],
    setItems: (next: DraftItem[]) => void,
    localItemId: string,
    patch: Partial<DraftItem>,
  ) {
    setItems(items.map((item) => (
      item.local_id === localItemId ? { ...item, ...patch } : item
    )))
  }

  function resetCreateSubmission() {
    createIdempotencyKeyRef.current = null
  }

  function resetInstantiationSubmission() {
    instantiateIdempotencyKeyRef.current = null
  }

  function selectTemplate(templateId: string) {
    setRevisionOpen(false)
    setRevisionTemplateId('')
    setRevisionTitle('')
    setRevisionDescription('')
    setRevisionItems([])
    resetInstantiationSubmission()
    setSelectedTemplateId(templateId)
  }

  function itemEditor(
    items: DraftItem[],
    setItems: (next: DraftItem[]) => void,
    prefix: string,
  ) {
    return (
      <div className="fc-template-item-editor">
        {items.map((item, index) => (
          <fieldset key={item.local_id}>
            <legend>Control {index + 1}</legend>
            <div className="fc-form-row">
              <label>Control title<input value={item.title} required minLength={3} maxLength={180} onChange={(event) => updateItem(items, setItems, item.local_id, { title: event.target.value })} /></label>
              <label>Planning offset · days from anchor<input type="number" min={-3660} max={3660} value={item.planned_offset_days} required onChange={(event) => updateItem(items, setItems, item.local_id, { planned_offset_days: Number(event.target.value) })} /></label>
            </div>
            <label>Description<textarea value={item.description} maxLength={2000} onChange={(event) => updateItem(items, setItems, item.local_id, { description: event.target.value })} /></label>
            <div className="fc-form-row">
              <label>Default verified preparer<select value={item.preparer_user_id} required onChange={(event) => updateItem(items, setItems, item.local_id, { preparer_user_id: event.target.value })}><option value="">Select account</option>{activeUsers.filter((user) => user.user_id !== item.reviewer_user_id).map((user) => <option key={user.user_id} value={user.user_id}>{user.display_name} (@{user.username})</option>)}</select></label>
              <label>Distinct verified reviewer<select value={item.reviewer_user_id} required onChange={(event) => updateItem(items, setItems, item.local_id, { reviewer_user_id: event.target.value })}><option value="">Select different account</option>{activeUsers.filter((user) => user.user_id !== item.preparer_user_id).map((user) => <option key={user.user_id} value={user.user_id}>{user.display_name} (@{user.username})</option>)}</select></label>
            </div>
            {items.length > 1 && <button type="button" className="fc-template-remove" onClick={() => setItems(items.filter((candidate) => candidate.local_id !== item.local_id))}>Remove control</button>}
          </fieldset>
        ))}
        <button type="button" className="fc-template-add" onClick={() => setItems([...items, blankItem()])}>Add another control to {prefix}</button>
      </div>
    )
  }

  function validateItems(items: DraftItem[]): boolean {
    if (!items.length) {
      setError('At least one real planning control is required.')
      return false
    }
    if (items.some((item) => !item.preparer_user_id || !item.reviewer_user_id)) {
      setError('Every control requires a verified preparer and reviewer.')
      return false
    }
    if (items.some((item) => item.preparer_user_id === item.reviewer_user_id)) {
      setError('Every control requires different preparer and reviewer accounts.')
      return false
    }
    return true
  }

  async function submitTemplate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!coordinator || !validateItems(createItems)) return
    const form = event.currentTarget
    const data = new FormData(form)
    setActionStatus('loading')
    setError('')
    setMessage('')
    try {
      const created = await createCloseTemplate({
        title: String(data.get('template_title') ?? ''),
        description: String(data.get('template_description') ?? ''),
        items: requestItems(createItems),
        idempotency_key: createIdempotencyKeyRef.current ??= workflowIdempotencyKey('financial-close-template'),
      })
      resetCreateSubmission()
      form.reset()
      setCreateItems([blankItem()])
      selectTemplate(created.template_id)
      await loadTemplates(created.template_id)
      await loadTemplate(created.template_id)
      setMessage('Immutable local planning-template version 1 recorded. Policy and automation effects remain none.')
      setActionStatus('ready')
    } catch (actionError) {
      setActionStatus('error')
      setError(errorMessage(actionError))
    }
  }

  function openRevision() {
    if (!template) return
    const latest = template.versions.at(-1)
    if (!latest) return
    setRevisionTitle(latest.title)
    setRevisionDescription(latest.description)
    setRevisionItems(latest.items.map((item) => ({
      local_id: localId(),
      title: item.title,
      description: item.description,
      planned_offset_days: item.planned_offset_days,
      preparer_user_id: item.preparer.user_id,
      reviewer_user_id: item.reviewer.user_id,
    })))
    setRevisionTemplateId(template.template_id)
    setRevisionOpen(true)
  }

  async function submitRevision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!coordinator || !template || !validateItems(revisionItems)) return
    if (revisionTemplateId !== template.template_id) {
      setRevisionOpen(false)
      setError('The selected template changed. Reopen the revision from the intended immutable template.')
      return
    }
    const data = new FormData(event.currentTarget)
    setActionStatus('loading')
    setError('')
    setMessage('')
    try {
      const updated = await createCloseTemplateVersion(template.template_id, {
        title: revisionTitle,
        description: revisionDescription,
        change_note: String(data.get('change_note') ?? ''),
        items: requestItems(revisionItems),
        expected_latest_version: template.latest_version,
        idempotency_key: workflowIdempotencyKey('financial-close-template-version'),
      })
      setRevisionOpen(false)
      setRevisionTemplateId('')
      setTemplate(updated)
      setSelectedVersion(updated.latest_version)
      await loadTemplates(updated.template_id)
      setMessage(`Immutable local planning-template version ${updated.latest_version} appended. Earlier versions and cycles remain unchanged.`)
      setActionStatus('ready')
    } catch (actionError) {
      setActionStatus('error')
      setError(errorMessage(actionError))
    }
  }

  async function submitInstantiation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!coordinator || !template || !version) return
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
    setMessage('')
    try {
      const cycle = await instantiateCloseTemplate(
        template.template_id,
        version.version,
        {
          entity_label: String(data.get('entity_label') ?? ''),
          period_label: String(data.get('period_label') ?? ''),
          period_start: periodStart,
          period_end: periodEnd,
          calendar_anchor_date: String(data.get('calendar_anchor_date') ?? ''),
          target_completion_date: String(data.get('target_completion_date') ?? '') || undefined,
          description: String(data.get('cycle_description') ?? ''),
          idempotency_key: instantiateIdempotencyKeyRef.current ??= workflowIdempotencyKey('financial-close-template-cycle'),
        },
      )
      resetInstantiationSubmission()
      await loadTemplate(template.template_id)
      await onCycleCreated(cycle)
      setActionStatus('ready')
    } catch (actionError) {
      setActionStatus('error')
      setError(errorMessage(actionError))
    }
  }

  if (listStatus === 'loading') {
    return <div className="fc-state">Loading immutable local close-planning templates…</div>
  }

  if (listStatus === 'error') {
    return <div className="fc-template-load-error"><strong>Planning templates are unavailable</strong><p>{error}</p><button type="button" onClick={() => void loadTemplates()}>Retry template load</button></div>
  }

  return (
    <div className="fc-template-workspace">
      <header className="fc-template-boundary">
        <div><span>LOCAL USER-AUTHORED PLANNING DRAFTS</span><h2>Reusable close planning templates</h2><p>Each saved version is immutable. Manual instantiation snapshots one exact version and calculates planning dates from the operator-entered anchor. Templates are not approved controls, accounting policy, SLAs, recurrence, or financial authority.</p></div>
        <div><strong>Policy effect: None</strong><span>Automation / notification effect: None</span><span>ERP / GL reads or writes: None</span></div>
      </header>

      {error && <div className="fc-message error"><strong>Unable to complete the planning request</strong><span>{error}</span></div>}
      {message && <div className="fc-message success">{message}</div>}

      <div className="fc-template-layout">
        <aside className="fc-template-catalog">
          <div className="fc-panel-heading"><div><span>REUSABLE LOCAL DRAFTS</span><h2>Templates</h2></div><b>{templates.length}</b></div>
          {templates.map((item) => <button type="button" key={item.template_id} className={item.template_id === selectedTemplateId ? 'active' : ''} onClick={() => selectTemplate(item.template_id)}><strong>{item.title}</strong><span>Version {item.latest_version} · {item.item_count} controls</span><small>Local draft · hash {item.latest_version_sha256.slice(0, 12)}…</small></button>)}
          {!templates.length && <div className="fc-empty"><strong>No planning templates exist.</strong><p>A Workflow Coordinator may record the first real local draft. ETOP seeds no sample or approved checklist.</p></div>}

          {coordinator ? (
            <form className="fc-form fc-template-create" onSubmit={submitTemplate} onChange={resetCreateSubmission}>
              <h3>Create immutable version 1</h3>
              {activeUsers.length < 2 && <div className="fc-role-boundary"><strong>Two active local accounts are required.</strong><p>Each planned control must name different preparer and reviewer identities.</p></div>}
              <label>Template title<input name="template_title" required minLength={3} maxLength={180} /></label>
              <label>Description<textarea name="template_description" maxLength={2000} /></label>
              {itemEditor(createItems, setCreateItems, 'version 1')}
              <button type="submit" disabled={actionStatus === 'loading' || activeUsers.length < 2}>Record local planning draft</button>
              <small>No template is approved or activated. Saving creates only an immutable, attributable local draft.</small>
            </form>
          ) : <div className="fc-role-boundary"><strong>Coordinator setup only</strong><p>Template authoring and manual instantiation require the operational Workflow Coordinator role. This grants no accounting or close authority.</p></div>}
        </aside>

        <main className="fc-template-detail">
          {detailStatus === 'loading' && <div className="fc-state">Loading exact template versions and integrity history…</div>}
          {detailStatus === 'error' && <div className="fc-template-load-error"><strong>Template detail is unavailable</strong><p>{error}</p><button type="button" onClick={() => selectedTemplateId && void loadTemplate(selectedTemplateId)}>Retry exact template load</button></div>}
          {detailStatus === 'idle' && !selectedTemplateId && <div className="fc-state">Create or select a local planning template.</div>}
          {detailStatus === 'ready' && template && version && (
            <>
              <div className="fc-template-title"><div><span>{template.template_id} · local user-authored planning draft</span><h2>{template.title}</h2><p>{template.description || 'No description recorded.'}</p></div><div><strong>{template.integrity.valid ? 'Integrity verified' : 'Integrity failed'}</strong><small>{template.version_count} immutable version{template.version_count === 1 ? '' : 's'}</small></div></div>

              <div className="fc-template-version-bar">
                <label>Inspect exact version<select value={version.version} onChange={(event) => { resetInstantiationSubmission(); setSelectedVersion(Number(event.target.value)) }}>{[...template.versions].reverse().map((item) => <option key={item.version} value={item.version}>Version {item.version} · {item.change_note}</option>)}</select></label>
                <div><strong>SHA-256 {version.version_sha256}</strong><span>Created by {version.created_by.display_name} · never rewritten</span></div>
                {coordinator && <button type="button" onClick={openRevision}>Create next version</button>}
              </div>

              <div className="fc-template-items">
                <div className="fc-template-item header"><span>Planned control</span><span>Offset</span><span>Preparer / reviewer</span><span>Source item</span></div>
                {version.items.map((item) => <div className="fc-template-item" key={item.item_id}><span><strong>{item.title}</strong><small>{item.description || 'No description recorded.'}</small></span><span>{item.planned_offset_days >= 0 ? '+' : ''}{item.planned_offset_days} days<small>from operator anchor</small></span><span><strong>{item.preparer.display_name}</strong><small>Review: {item.reviewer.display_name}</small></span><span>{item.item_id}<small>{item.item_sha256.slice(0, 12)}…</small></span></div>)}
              </div>

              {revisionOpen && coordinator && (
                <form className="fc-form fc-template-revision" onSubmit={submitRevision}>
                  <div className="fc-panel-heading"><div><span>APPEND-ONLY CHANGE</span><h2>Create version {template.latest_version + 1}</h2></div><button type="button" onClick={() => { setRevisionOpen(false); setRevisionTemplateId('') }}>Cancel</button></div>
                  <label>Template title<input value={revisionTitle} required minLength={3} maxLength={180} onChange={(event) => setRevisionTitle(event.target.value)} /></label>
                  <label>Description<textarea value={revisionDescription} maxLength={2000} onChange={(event) => setRevisionDescription(event.target.value)} /></label>
                  <label>Required change note<textarea name="change_note" required minLength={3} maxLength={2000} /></label>
                  {itemEditor(revisionItems, setRevisionItems, `version ${template.latest_version + 1}`)}
                  <button type="submit" disabled={actionStatus === 'loading'}>Append immutable template version</button>
                  <small>Existing versions, instantiated cycles, evidence, and reviews remain unchanged.</small>
                </form>
              )}

              <section className="fc-template-instantiate">
                <div className="fc-panel-heading"><div><span>EXPLICIT MANUAL INSTANTIATION</span><h2>Create a cycle from version {version.version}</h2></div><small>No recurrence, task, message, or ERP action.</small></div>
                {coordinator ? (
                  <form className="fc-form" onSubmit={submitInstantiation} onChange={resetInstantiationSubmission}>
                    <div className="fc-form-row"><label>Entity label · operator supplied / unverified<input name="entity_label" required minLength={2} maxLength={160} /></label><label>Period label<input name="period_label" required minLength={2} maxLength={120} /></label></div>
                    <div className="fc-form-row"><label>Period start<input name="period_start" type="date" required /></label><label>Period end<input name="period_end" type="date" required /></label></div>
                    <div className="fc-form-row"><label>Planning anchor date<input name="calendar_anchor_date" type="date" required value={calendarAnchor} onChange={(event) => setCalendarAnchor(event.target.value)} /></label><label>Operator target date<input name="target_completion_date" type="date" /></label></div>
                    <label>Description<textarea name="cycle_description" maxLength={2000} /></label>
                    <div className="fc-template-preview"><strong>Proposed planning dates</strong>{version.items.map((item) => <span key={item.item_id}>{item.title}<b>{proposedDate(calendarAnchor, item.planned_offset_days)}</b></span>)}<small>The server recomputes and snapshots these dates from the exact version and anchor on manual submission.</small></div>
                    <button type="submit" disabled={actionStatus === 'loading' || !calendarAnchor}>Instantiate exact version into local cycle</button>
                    <small>The resulting cycle and controls preserve version/item hashes. Later template versions cannot rewrite them.</small>
                  </form>
                ) : <div className="fc-role-boundary"><strong>Manual coordinator action required</strong><p>No cycle is generated automatically. A coordinator must supply the calendar context and explicitly instantiate one exact version.</p></div>}
              </section>

              <section className="fc-template-history">
                <div className="fc-panel-heading"><div><span>TAMPER-EVIDENT HISTORY</span><h2>Template lineage</h2></div><strong className={template.integrity.valid ? 'valid' : 'invalid'}>{template.integrity.valid ? 'Integrity verified' : 'Integrity failed'}</strong></div>
                {template.events.map((item) => <article key={item.event_id}><strong>{item.event_type.replaceAll('_', ' ')}</strong><span>{item.actor.display_name} · {new Date(item.occurred_at).toLocaleString()}</span><p>{Object.entries(item.details).map(([key, value]) => `${key.replaceAll('_', ' ')}: ${String(value)}`).join(' · ')}</p><small>sequence {item.sequence} · hash {item.record_hash}</small></article>)}
              </section>
            </>
          )}
        </main>
      </div>
    </div>
  )
}
