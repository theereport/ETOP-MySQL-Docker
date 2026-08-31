import { type FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { getWorkflowRoles } from '../workflow-foundation/api'
import type {
  ETOPModuleId,
  WorkflowRole,
  WorkflowRoleId,
} from '../workflow-foundation/types'
import { useAccess } from './AccessContext'
import {
  changeSecurityUserStatus,
  createPasswordReset,
  createSecurityInvitation,
  getSecurityInvitations,
  getSecurityUsers,
  replaceSecurityUserModules,
  revokeSecurityInvitation,
  setUserPassword,
} from './api'
import type {
  SecurityInvitation,
  SecurityInvitationCreateResponse,
  SecurityModule,
  SecurityPasswordResetCreateResponse,
  SecurityUser,
} from './types'
import './SecurityAccess.css'

type View = 'users' | 'invite' | 'invitations'

function messageFor(error: unknown): string {
  return error instanceof Error ? error.message : 'The security request failed.'
}

function formatDate(value: string): string {
  const parsed = new Date(value)
  return Number.isNaN(parsed.valueOf()) ? value : parsed.toLocaleString()
}

export default function SecurityAccessWorkspace() {
  const { session, refreshAccess } = useAccess()
  const [view, setView] = useState<View>('users')
  const [users, setUsers] = useState<SecurityUser[]>([])
  const [modules, setModules] = useState<SecurityModule[]>([])
  const [roles, setRoles] = useState<WorkflowRole[]>([])
  const [invitations, setInvitations] = useState<SecurityInvitation[]>([])
  const [drafts, setDrafts] = useState<Record<string, ETOPModuleId[]>>({})
  const [createdInvitation, setCreatedInvitation] = useState<SecurityInvitationCreateResponse | null>(null)
  const [resetPanelUserId, setResetPanelUserId] = useState('')
  const [createdReset, setCreatedReset] = useState<SecurityPasswordResetCreateResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [workingId, setWorkingId] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [security, nextRoles, nextInvitations] = await Promise.all([
        getSecurityUsers(),
        getWorkflowRoles(),
        getSecurityInvitations(),
      ])
      setUsers(security.users)
      setModules(security.modules)
      setRoles(nextRoles)
      setInvitations(nextInvitations)
      setDrafts(Object.fromEntries(
        security.users.map((item) => [item.user.user_id, item.configured_module_ids]),
      ))
    } catch (loadError) {
      setError(messageFor(loadError))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const timeoutId = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(timeoutId)
  }, [load])

  const modulesByGroup = useMemo(() => {
    const grouped = new Map<string, SecurityModule[]>()
    modules.forEach((module) => {
      grouped.set(module.group, [...(grouped.get(module.group) ?? []), module])
    })
    return grouped
  }, [modules])

  function updateDraft(userId: string, moduleId: ETOPModuleId, checked: boolean) {
    setDrafts((current) => {
      const selected = new Set(current[userId] ?? [])
      if (checked) selected.add(moduleId)
      else selected.delete(moduleId)
      return { ...current, [userId]: [...selected].sort() as ETOPModuleId[] }
    })
  }

  async function saveModules(user: SecurityUser) {
    setWorkingId(user.user.user_id)
    setError('')
    setMessage('')
    try {
      const updated = await replaceSecurityUserModules(
        user.user.user_id,
        drafts[user.user.user_id] ?? [],
        user.access_version,
      )
      setUsers((current) => current.map((item) => (
        item.user.user_id === updated.user.user_id ? updated : item
      )))
      setDrafts((current) => ({
        ...current,
        [updated.user.user_id]: updated.configured_module_ids,
      }))
      setMessage(`Module access saved for ${updated.user.display_name}. New routes are denied until explicitly enabled.`)
    } catch (saveError) {
      setError(messageFor(saveError))
    } finally {
      setWorkingId('')
    }
  }

  async function changeStatus(user: SecurityUser) {
    const nextStatus = user.user.status === 'active' ? 'inactive' : 'active'
    setWorkingId(user.user.user_id)
    setError('')
    setMessage('')
    try {
      const updated = await changeSecurityUserStatus(
        user.user.user_id,
        nextStatus,
        user.status_version,
      )
      setUsers((current) => current.map((item) => (
        item.user.user_id === updated.user.user_id ? updated : item
      )))
      setMessage(`${updated.user.display_name} was ${nextStatus === 'active' ? 'reactivated' : 'suspended'}.`)
    } catch (statusError) {
      setError(messageFor(statusError))
    } finally {
      setWorkingId('')
    }
  }

  function toggleResetPanel(userId: string) {
    setResetPanelUserId((current) => (current === userId ? '' : userId))
    setCreatedReset(null)
    setError('')
    setMessage('')
  }

  async function generateResetLink(user: SecurityUser) {
    setWorkingId(user.user.user_id)
    setError('')
    setMessage('')
    setCreatedReset(null)
    try {
      const created = await createPasswordReset(user.user.user_id)
      setCreatedReset(created)
      setMessage('Password reset link created. Copy it now; its raw token is not stored and the link is displayed only once.')
    } catch (resetError) {
      setError(messageFor(resetError))
    } finally {
      setWorkingId('')
    }
  }

  async function copyResetLink() {
    if (!createdReset) return
    try {
      await navigator.clipboard.writeText(createdReset.reset_link)
      setMessage('Password reset link copied to the clipboard.')
    } catch {
      setError('The browser could not copy the link. Select and copy it manually.')
    }
  }

  async function submitNewPassword(event: FormEvent<HTMLFormElement>, user: SecurityUser) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const password = String(data.get('new_password') ?? '')
    const confirmation = String(data.get('confirmation') ?? '')
    if (password !== confirmation) {
      setError('The password confirmation does not match.')
      return
    }
    setWorkingId(user.user.user_id)
    setError('')
    setMessage('')
    try {
      const updated = await setUserPassword(user.user.user_id, password, user.credential_version)
      setUsers((current) => current.map((item) => (
        item.user.user_id === updated.user.user_id ? updated : item
      )))
      setResetPanelUserId('')
      setMessage(`Password set directly for ${updated.user.display_name}. Their active sessions were signed out.`)
    } catch (passwordError) {
      setError(messageFor(passwordError))
    } finally {
      setWorkingId('')
    }
  }

  async function createInvitation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const roleIds = data.getAll('role_ids').map(String) as WorkflowRoleId[]
    const moduleIds = data.getAll('module_ids').map(String) as ETOPModuleId[]
    setWorkingId('invite')
    setError('')
    setMessage('')
    setCreatedInvitation(null)
    try {
      const created = await createSecurityInvitation({
        display_name: String(data.get('display_name') ?? ''),
        username: String(data.get('username') ?? ''),
        role_ids: roleIds,
        module_ids: moduleIds,
        expires_in_hours: Number(data.get('expires_in_hours') ?? 48),
      })
      setCreatedInvitation(created)
      setInvitations(await getSecurityInvitations())
      setMessage('Invitation created. Copy the link now; its raw token is not stored and the link is displayed only once.')
      event.currentTarget.reset()
    } catch (inviteError) {
      setError(messageFor(inviteError))
    } finally {
      setWorkingId('')
    }
  }

  async function copyInvitationLink() {
    if (!createdInvitation) return
    try {
      await navigator.clipboard.writeText(createdInvitation.invitation_link)
      setMessage('Invitation link copied to the clipboard.')
    } catch {
      setError('The browser could not copy the link. Select and copy it manually.')
    }
  }

  async function revokeInvitation(invitationId: string) {
    setWorkingId(invitationId)
    setError('')
    setMessage('')
    try {
      const revoked = await revokeSecurityInvitation(invitationId)
      setInvitations((current) => current.map((item) => (
        item.invitation_id === revoked.invitation_id ? revoked : item
      )))
      if (createdInvitation?.invitation_id === invitationId) {
        setCreatedInvitation(null)
      }
      setMessage(`The invitation for ${revoked.display_name} was revoked. Its link can no longer be activated.`)
    } catch (revokeError) {
      setError(messageFor(revokeError))
    } finally {
      setWorkingId('')
    }
  }

  return (
    <section className="security-workspace">
      <header className="security-header">
        <div><span className="security-kicker">LOCAL IDENTITY · SERVER-ENFORCED ACCESS</span><h1>Security & Access</h1><p>Create controlled invitations, suspend or reactivate accounts, and explicitly enable the ETOP modules each person can use.</p></div>
        <div><span>Signed in administrator</span><strong>{session.user.display_name}</strong><small>Workflow Coordinator · no financial authority</small><button type="button" onClick={() => void refreshAccess()}>Refresh my access</button></div>
      </header>

      <div className="security-boundary"><strong>Default deny</strong><span>Every newly registered module stays off until an administrator enables it.</span><span>Frontend navigation and backend API routes use the same effective permission profile.</span></div>
      {error && <div className="security-banner security-banner--error">{error}</div>}
      {message && <div className="security-banner security-banner--success">{message}</div>}

      <nav className="security-tabs" aria-label="Security and Access views">
        <button type="button" className={view === 'users' ? 'is-active' : ''} onClick={() => setView('users')}>Users & module access</button>
        <button type="button" className={view === 'invite' ? 'is-active' : ''} onClick={() => setView('invite')}>Create invitation</button>
        <button type="button" className={view === 'invitations' ? 'is-active' : ''} onClick={() => setView('invitations')}>Invitation history</button>
      </nav>

      {loading && <div className="security-empty">Loading governed access profiles…</div>}

      {!loading && view === 'users' && (
        <div className="security-user-list">
          {users.map((item) => {
            const self = item.user.user_id === session.user.user_id
            const selected = new Set(drafts[item.user.user_id] ?? [])
            const changed = JSON.stringify([...selected].sort()) !== JSON.stringify([...item.configured_module_ids].sort())
            return (
              <article className={item.user.status === 'inactive' ? 'is-suspended' : ''} key={item.user.user_id}>
                <header><div><strong>{item.user.display_name}</strong><span>@{item.user.username} · {item.user.roles.map((role) => role.name).join(' · ')}</span></div><b>{item.user.status === 'active' ? 'Active' : 'Suspended'}</b></header>
                <div className="security-all-actions"><button type="button" disabled={self} onClick={() => setDrafts((current) => ({ ...current, [item.user.user_id]: modules.map((module) => module.module_id) }))}>Enable all modules</button><button type="button" disabled={self} onClick={() => setDrafts((current) => ({ ...current, [item.user.user_id]: [] }))}>Disable all modules</button></div>
                <div className="security-module-groups">
                  {[...modulesByGroup.entries()].map(([group, groupModules]) => (
                    <fieldset key={group}><legend>{group}</legend>{groupModules.map((module) => <label key={module.module_id}><input type="checkbox" checked={selected.has(module.module_id)} disabled={self} onChange={(event) => updateDraft(item.user.user_id, module.module_id, event.target.checked)} /><span><strong>{module.name}</strong><small>{module.description}</small></span></label>)}</fieldset>
                  ))}
                </div>
                <footer><span>Access profile v{item.access_version} · account status v{item.status_version}{self ? ' · your own controls require another active administrator' : ''}</span><div><button type="button" disabled={self || !changed || workingId === item.user.user_id} onClick={() => void saveModules(item)}>Save module access</button><button type="button" className="security-danger" disabled={self || workingId === item.user.user_id} onClick={() => void changeStatus(item)}>{item.user.status === 'active' ? 'Suspend user' : 'Reactivate user'}</button><button type="button" onClick={() => toggleResetPanel(item.user.user_id)}>{resetPanelUserId === item.user.user_id ? 'Close password reset' : 'Reset password'}</button></div></footer>
                {resetPanelUserId === item.user.user_id && (
                  <div className="security-reset-panel">
                    <div className="security-reset-link">
                      <div><span className="security-kicker">ONE-TIME ACTIVATION</span><h3>Generate a reset link (preferred)</h3><p>Share this link with {item.user.display_name} so they can set their own new password.</p></div>
                      <button type="button" disabled={workingId === item.user.user_id} onClick={() => void generateResetLink(item)}>{workingId === item.user.user_id ? 'Creating…' : 'Generate reset link'}</button>
                      {createdReset && createdReset.user_id === item.user.user_id && (
                        <><textarea readOnly value={createdReset.reset_link} aria-label="Password reset link" /><button type="button" onClick={() => void copyResetLink()}>Copy reset link</button><small>Expires {formatDate(createdReset.expires_at)}. The database stores only the SHA-256 token hash; closing this result means the raw link cannot be recovered.</small></>
                      )}
                    </div>
                    <form className="security-reset-direct" onSubmit={(event) => void submitNewPassword(event, item)}>
                      <div><span className="security-kicker">FALLBACK</span><h3>Set a new password directly</h3><p>Immediately replaces their password and signs out their active sessions.</p></div>
                      <label>New password<input name="new_password" type="password" minLength={12} maxLength={200} required autoComplete="new-password" /></label>
                      <label>Confirm password<input name="confirmation" type="password" minLength={12} maxLength={200} required autoComplete="new-password" /></label>
                      <button type="submit" disabled={workingId === item.user.user_id}>{workingId === item.user.user_id ? 'Setting…' : 'Set new password'}</button>
                    </form>
                  </div>
                )}
              </article>
            )
          })}
        </div>
      )}

      {!loading && view === 'invite' && (
        <div className="security-invite-layout">
          <form className="security-panel" onSubmit={createInvitation}>
            <div><span className="security-kicker">ONE-TIME ACTIVATION</span><h2>Set up a user</h2><p>Choose the operational roles and exact modules before sharing the generated project link.</p></div>
            <label>Display name<input name="display_name" minLength={2} maxLength={120} required /></label>
            <label>Username<input name="username" minLength={3} maxLength={80} pattern="[A-Za-z0-9._-]+" required /></label>
            <label>Link expires<select name="expires_in_hours" defaultValue="48"><option value="24">24 hours</option><option value="48">48 hours</option><option value="72">72 hours</option><option value="168">7 days</option></select></label>
            <fieldset><legend>Operational workflow roles</legend>{roles.map((role) => <label key={role.role_id}><input type="checkbox" name="role_ids" value={role.role_id} defaultChecked={role.role_id === 'workflow_observer'} /><span><strong>{role.name}</strong><small>{role.description}</small></span></label>)}</fieldset>
            <fieldset><legend>Module access</legend>{modules.map((module) => <label key={module.module_id}><input type="checkbox" name="module_ids" value={module.module_id} defaultChecked={module.module_id === 'dashboard' || module.module_id === 'work_management'} /><span><strong>{module.name}</strong><small>{module.group} · off by default for future modules</small></span></label>)}</fieldset>
            <button type="submit" disabled={workingId === 'invite'}>{workingId === 'invite' ? 'Creating…' : 'Create invitation link'}</button>
          </form>
          <aside className="security-panel security-link-panel">
            <span className="security-kicker">SHARE CONTROL</span><h2>Project access link</h2>
            {createdInvitation ? <><p>Share this exact link with <strong>{createdInvitation.display_name}</strong>. It expires {formatDate(createdInvitation.expires_at)} and stops working after activation.</p><textarea readOnly value={createdInvitation.invitation_link} aria-label="Invitation link" /><button type="button" onClick={() => void copyInvitationLink()}>Copy invitation link</button><small>The database stores only the SHA-256 token hash. Closing or replacing this result means the raw link cannot be recovered.</small></> : <div className="security-empty">Create an invitation to generate a single-use project link.</div>}
          </aside>
        </div>
      )}

      {!loading && view === 'invitations' && (
        <section className="security-panel">
          <div><span className="security-kicker">DURABLE INVITATION EVIDENCE</span><h2>Invitation history</h2></div>
          <div className="security-invitation-list">{invitations.map((item) => <article key={item.invitation_id}><div><strong>{item.display_name}</strong><span>@{item.username} · {item.module_ids.length} modules · {item.role_ids.length} roles</span></div><div className="security-invitation-state"><b className={`status-${item.status}`}>{item.status}</b>{item.status === 'pending' && <button type="button" className="security-danger" disabled={workingId === item.invitation_id} onClick={() => void revokeInvitation(item.invitation_id)}>Revoke</button>}</div><small>Created {formatDate(item.created_at)} · expires {formatDate(item.expires_at)}{item.activated_at ? ` · activated ${formatDate(item.activated_at)}` : ''}</small></article>)}</div>
          {!invitations.length && <div className="security-empty">No invitation evidence exists yet.</div>}
        </section>
      )}
    </section>
  )
}
