import {
  type FormEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react'
import {
  bootstrapWorkflowAccount,
  getBootstrapStatus,
  getWorkflowSession,
  getWorkflowToken,
  loginWorkflow,
  logoutWorkflow,
  saveWorkflowToken,
  WORKFLOW_SESSION_EVENT,
} from '../workflow-foundation/api'
import type { WorkflowBootstrapStatus, WorkflowSession } from '../workflow-foundation/types'
import { AccessContext, type AccessContextValue } from './AccessContext'
import {
  activateSecurityInvitation,
  previewSecurityInvitation,
} from './api'
import type { SecurityInvitationPreview } from './types'
import './SecurityAccess.css'

function inviteTokenFromHash(): string | null {
  const match = window.location.hash.match(/^#invite=([A-Za-z0-9_-]{32,256})$/)
  return match ? match[1] : null
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'The local access request failed.'
}

export default function AccessProvider({ children }: { children: ReactNode }) {
  const [bootstrap, setBootstrap] = useState<WorkflowBootstrapStatus | null>(null)
  const [session, setSession] = useState<WorkflowSession | null>(null)
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [inviteToken, setInviteToken] = useState<string | null>(inviteTokenFromHash)
  const [invitation, setInvitation] = useState<SecurityInvitationPreview | null>(null)

  const refreshAccess = useCallback(async () => {
    if (!getWorkflowToken()) {
      setSession(null)
      return
    }
    setSession(await getWorkflowSession())
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    const initialize = async () => {
      setLoading(true)
      setError('')
      try {
        const status = await getBootstrapStatus(controller.signal)
        if (controller.signal.aborted) return
        setBootstrap(status)
        const token = inviteTokenFromHash()
        setInviteToken(token)
        if (token) {
          setInvitation(await previewSecurityInvitation(token, controller.signal))
        } else if (getWorkflowToken() && !status.bootstrap_required) {
          setSession(await getWorkflowSession())
        }
      } catch (loadError) {
        if (!controller.signal.aborted) setError(errorMessage(loadError))
      } finally {
        if (!controller.signal.aborted) setLoading(false)
      }
    }
    void initialize()
    return () => controller.abort()
  }, [])

  useEffect(() => {
    const handleSessionChange = () => {
      if (!getWorkflowToken()) {
        setSession(null)
        return
      }
      void refreshAccess().catch((refreshError) => setError(errorMessage(refreshError)))
    }
    window.addEventListener(WORKFLOW_SESSION_EVENT, handleSessionChange)
    return () => window.removeEventListener(WORKFLOW_SESSION_EVENT, handleSessionChange)
  }, [refreshAccess])

  async function authenticate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!bootstrap) return
    const data = new FormData(event.currentTarget)
    setSubmitting(true)
    setError('')
    try {
      const result = bootstrap.bootstrap_required
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
      setSession(result)
      setBootstrap({ ...bootstrap, bootstrap_required: false, account_count: Math.max(1, bootstrap.account_count) })
    } catch (authError) {
      setError(errorMessage(authError))
    } finally {
      setSubmitting(false)
    }
  }

  async function activateInvitation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!inviteToken) return
    const data = new FormData(event.currentTarget)
    const password = String(data.get('password') ?? '')
    const confirmation = String(data.get('confirmation') ?? '')
    if (password !== confirmation) {
      setError('The password confirmation does not match.')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      const result = await activateSecurityInvitation(inviteToken, password)
      saveWorkflowToken(result.token)
      setSession(result)
      setInviteToken(null)
      setInvitation(null)
      window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}`)
    } catch (activationError) {
      setError(errorMessage(activationError))
    } finally {
      setSubmitting(false)
    }
  }

  const value = useMemo<AccessContextValue | null>(() => {
    if (!session) return null
    const allowed = new Set(session.permissions.module_ids)
    return {
      session,
      canAccess: (moduleId) => allowed.has(moduleId),
      refreshAccess,
      signOut: async () => {
        await logoutWorkflow()
        setSession(null)
      },
    }
  }, [refreshAccess, session])

  if (loading) {
    return <main className="security-gate"><section><strong>Loading protected ETOP access…</strong></section></main>
  }

  if (inviteToken) {
    return (
      <main className="security-gate">
        <section className="security-auth-card">
          <span>ETOP · CONTROLLED LOCAL INVITATION</span>
          <h1>{invitation ? `Welcome, ${invitation.display_name}` : 'Invitation unavailable'}</h1>
          {invitation ? (
            <>
              <p>Activate <strong>@{invitation.username}</strong> for this ETOP instance. The link is single-use and expires {new Date(invitation.expires_at).toLocaleString()}.</p>
              <form onSubmit={activateInvitation}>
                <label>New password<input name="password" type="password" minLength={12} maxLength={200} required autoComplete="new-password" /></label>
                <label>Confirm password<input name="confirmation" type="password" minLength={12} maxLength={200} required autoComplete="new-password" /></label>
                {error && <p className="security-error">{error}</p>}
                <button type="submit" disabled={submitting}>{submitting ? 'Activating…' : 'Activate secure access'}</button>
              </form>
            </>
          ) : <p className="security-error">{error || 'The invitation cannot be used.'}</p>}
          <aside><strong>Local assurance boundary</strong><p>This account authenticates only to this ETOP instance. Module access does not grant financial approval, payment, posting, cash-application, or ERP authority.</p></aside>
        </section>
      </main>
    )
  }

  if (!bootstrap || !value) {
    return (
      <main className="security-gate">
        <section className="security-auth-card">
          <span>ETOP · IDENTITY & MODULE ACCESS</span>
          <h1>{bootstrap?.bootstrap_required ? 'Establish the first administrator' : 'Sign in to ETOP'}</h1>
          <p>{bootstrap?.bootstrap_required ? 'The first local account bootstraps Work Management and Security & Access administration.' : 'Use the local account supplied by your ETOP administrator.'}</p>
          {bootstrap && (
            <form onSubmit={authenticate}>
              {bootstrap.bootstrap_required && <label>Display name<input name="display_name" minLength={2} maxLength={120} required autoComplete="name" /></label>}
              <label>Username<input name="username" minLength={3} maxLength={80} pattern="[A-Za-z0-9._-]+" required autoComplete="username" /></label>
              <label>Password<input name="password" type="password" minLength={12} maxLength={200} required autoComplete={bootstrap.bootstrap_required ? 'new-password' : 'current-password'} /></label>
              {error && <p className="security-error">{error}</p>}
              <button type="submit" disabled={submitting}>{submitting ? 'Checking…' : bootstrap.bootstrap_required ? 'Create administrator' : 'Sign in'}</button>
            </form>
          )}
          {!bootstrap && <p className="security-error">{error || 'The local identity service is unavailable.'}</p>}
          {bootstrap && <aside><strong>Authentication boundary</strong><p>{bootstrap.authentication_boundary}</p><strong>Authority boundary</strong><p>{bootstrap.authority_boundary}</p></aside>}
        </section>
      </main>
    )
  }

  if (value.session.permissions.module_ids.length === 0) {
    return (
      <main className="security-gate">
        <section className="security-auth-card">
          <span>ETOP · DEFAULT DENY</span>
          <h1>No modules are enabled</h1>
          <p>Your account is active, but an administrator has not enabled an ETOP module for it. Contact the local Workflow Coordinator.</p>
          <button type="button" onClick={() => void value.signOut()}>Sign out</button>
          <aside><strong>Access boundary</strong><p>ETOP hides module navigation and the backend denies its API routes until access is explicitly enabled.</p></aside>
        </section>
      </main>
    )
  }

  return <AccessContext.Provider value={value}>{children}</AccessContext.Provider>
}
