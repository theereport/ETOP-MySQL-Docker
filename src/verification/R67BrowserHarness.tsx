import { useState, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'

import App from '../App'
import WorkspaceErrorBoundary from '../components/WorkspaceErrorBoundary'
import { AccessContext } from '../features/security-access/AccessContext'
import LockboxAutomationCenter from '../modules/document-intelligence/components/LockboxAutomationCenter'
import type {
  DocumentJob,
  DurableLockboxPreparation,
  LockboxProcessingResult,
  LockboxReviewResult,
  LockboxTransaction,
  ReviewedLockboxTransaction,
} from '../modules/document-intelligence/types'
import type {
  AccessContextValue,
} from '../features/security-access/AccessContext'

const RAW_REVIEW_SENTINEL = 'RAW-REVIEW-MUST-STAY-HIDDEN'
const PROJECTED_CUSTOMER = 'Projected Customer'

declare global {
  interface Window {
    __etopR67UnexpectedErrors: string[]
  }
}

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message)
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds))
}

async function waitFor(
  predicate: () => boolean,
  message: string,
  timeoutMilliseconds = 5_000,
): Promise<void> {
  const deadline = Date.now() + timeoutMilliseconds
  while (!predicate()) {
    if (Date.now() >= deadline) throw new Error(message)
    await delay(10)
  }
}

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function unexpectedFetch(): never {
  window.__etopR67UnexpectedErrors.push('unexpected-fetch')
  throw new Error('Unexpected synthetic browser request.')
}

function requestUrl(input: RequestInfo | URL): URL {
  if (input instanceof Request) return new URL(input.url)
  return new URL(String(input), window.location.href)
}

function mount(node: ReactNode): { host: HTMLDivElement; root: Root } {
  document.body.replaceChildren()
  const host = document.createElement('div')
  host.id = 'r67-harness-root'
  document.body.append(host)
  const root = createRoot(host)
  root.render(node)
  return { host, root }
}

const rawTransaction: LockboxTransaction = {
  transaction_id: 'T001',
  envelope_number: 1,
  lockbox: 'synthetic-lockbox',
  date: '2026-08-14',
  batch: 1,
  batch_item: 1,
  check_number: 'synthetic-check',
  check_amount: 100,
  aba_routing: '',
  account_number: '',
  customer_name: RAW_REVIEW_SENTINEL,
  allocations: [],
  allocation_total: 0,
  difference: 100,
  balanced: false,
  status: 'review_required',
  check_page: 1,
  remittance_pages: [],
}

const reviewedTransaction: ReviewedLockboxTransaction = {
  ...rawTransaction,
  original_allocations: [],
  status: 'review_required',
  reviewer: '',
  notes: '',
  override_reason: '',
  misc_gl: { reason: '', gl_code: '', location: '', department: '', amount: 0 },
  reviewed_at: null,
}

const processingResult: LockboxProcessingResult = {
  job_id: 'source-test',
  source_file_name: 'synthetic-lockbox.pdf',
  lockbox: 'synthetic-lockbox',
  transaction_date: '2026-08-14',
  transaction_count: 1,
  allocation_count: 0,
  total_check_amount: 100,
  total_allocation_amount: 0,
  total_difference: 100,
  balanced_count: 0,
  review_count: 1,
  transactions: [rawTransaction],
  warnings: [],
}

const rawReview: LockboxReviewResult = {
  ...processingResult,
  approved_count: 7,
  corrected_count: 0,
  held_count: 0,
  transactions: [reviewedTransaction],
}

const terminalSummary: DurableLockboxPreparation = {
  job_id: 'preparation-test',
  source_job_id: 'source-test',
  source_file_hash: 'synthetic-source-hash',
  state: 'complete',
  expected_count: 1,
  terminal_count: 1,
  balanced_count: 0,
  exception_count: 1,
  preserved_count: 0,
  preparation_generation: 1,
  rule_version: 'synthetic-rule',
  service_version: 'synthetic-service',
  complete: true,
  counts_final: true,
  current_for_rule: true,
  reconciled: true,
  recommendation_not_decision: true,
  can_auto_approve: false,
  erp_write_performed: false,
  exception_reason_summary: {
    total_exception_count: 1,
    by_primary_reason: [{
      code: 'synthetic_review',
      category: 'synthetic',
      label: 'Synthetic review',
      description: 'Synthetic browser-only exception.',
      review_guidance: 'Retain professional review.',
      count: 1,
    }],
  },
}

const fullPreparation: DurableLockboxPreparation = {
  ...terminalSummary,
  transactions: [{
    transaction_id: 'T001',
    ordinal: 1,
    state: 'prepared_exception',
    source: { original_source: { allocations: [] } },
    result: {
      customer_resolution: {
        status: 'resolved',
        customer_number: 'synthetic-customer',
        selected_confidence: 1,
        selection_basis: 'current_open_invoice_owner',
        matched_on: ['invoice'],
        warnings: [],
        matching_evidence: { failed_selection_gates: [] },
      },
      customer_snapshot: {
        fields: {
          customer_number: 'synthetic-customer',
          customer_name: PROJECTED_CUSTOMER,
          phone: '',
          address_line_1: '',
          address_line_2: '',
          city: '',
          state: '',
          postal_code: '',
        },
      },
      exception_analysis: {
        primary_reason: {
          code: 'synthetic_review',
          label: 'Synthetic review',
          review_guidance: 'Retain professional review.',
        },
      },
      can_auto_approve: false,
      erp_write_performed: false,
    },
    error: null,
    retry_eligible: false,
  }],
}

const pdfJob: DocumentJob = {
  job_id: 'source-test',
  original_file_name: 'synthetic-lockbox.pdf',
  stored_file_name: 'synthetic-lockbox.pdf',
  content_type: 'application/pdf',
  file_size_bytes: 1,
  document_type: 'pnc_lockbox',
  confidence: 1,
  status: 'completed',
  message: 'Synthetic browser regression only.',
  created_at: '2026-08-14T00:00:00Z',
  updated_at: '2026-08-14T00:00:00Z',
}

async function verifyLockboxTransition(): Promise<void> {
  let detailRequested = false
  let releaseDetail: (response: Response) => void = () => {
    throw new Error('Synthetic detail resolver was not initialized.')
  }
  const detailResponse = new Promise<Response>((resolve) => {
    releaseDetail = resolve
  })

  window.localStorage.clear()
  window.fetch = async (input) => {
    const url = requestUrl(input)
    if (url.pathname.endsWith('/jobs/source-test/lockbox/result')) {
      return jsonResponse(processingResult)
    }
    if (url.pathname.endsWith('/jobs/source-test/lockbox/review')) {
      return jsonResponse(rawReview)
    }
    if (url.pathname.endsWith('/jobs/source-test/lockbox/preparation/current')) {
      assert(
        url.searchParams.get('include_transactions') === 'false',
        'Current preparation must begin with summary-only detail.',
      )
      return jsonResponse(terminalSummary)
    }
    if (url.pathname.endsWith('/lockbox/preparation/preparation-test')) {
      assert(
        url.searchParams.get('include_transactions') === 'true',
        'Terminal summary must trigger exact full-detail retrieval.',
      )
      detailRequested = true
      return detailResponse
    }
    return unexpectedFetch()
  }

  const { host, root } = mount(
    <LockboxAutomationCenter jobs={[pdfJob]} />,
  )
  await waitFor(
    () => detailRequested,
    'Lockbox did not request full detail after the terminal summary.',
  )
  await waitFor(
    () => host.textContent?.includes('Preparation Incomplete') === true,
    'Terminal summary did not retain the fail-closed preparation state.',
  )
  assert(
    !host.textContent?.includes(RAW_REVIEW_SENTINEL),
    'Raw review data rendered before governed projection.',
  )
  const approvedMetric = () => Array.from(
    host.querySelectorAll<HTMLButtonElement>('.lockbox-mini-metrics button'),
  ).find((button) => button.querySelector('span')?.textContent === 'Approved')
  assert(approvedMetric(), 'The Approved governed metric is unavailable.')
  assert(
    approvedMetric()?.querySelector('strong')?.textContent === '—',
    'Raw approved count rendered before governed projection.',
  )

  releaseDetail(jsonResponse(fullPreparation))
  await waitFor(
    () => host.textContent?.includes(PROJECTED_CUSTOMER) === true,
    'The governed full-detail projection did not render.',
  )
  assert(
    !host.textContent?.includes(RAW_REVIEW_SENTINEL),
    'Raw review data remained visible after governed projection.',
  )
  assert(
    host.querySelector('.lockbox-review-row') !== null,
    'The governed exception queue did not become review-ready.',
  )
  assert(
    approvedMetric()?.querySelector('strong')?.textContent === '0',
    'The projected approved count did not replace the hidden raw count.',
  )
  root.unmount()
}

const access: AccessContextValue = {
  session: {
    expires_at: '2099-01-01T00:00:00Z',
    user: {
      person_id: 'synthetic-person',
      user_id: 'synthetic-user',
      username: 'synthetic',
      display_name: 'Synthetic User',
      status: 'active',
      roles: [],
      authentication_assurance: 'local_credential',
      authority_status: 'not_configured',
      created_at: '2026-08-14T00:00:00Z',
    },
    permissions: {
      module_ids: ['dashboard', 'ai_assistant'],
      access_version: 1,
      default_behavior: 'deny',
      authority_effect: 'none',
      decision_authority: false,
    },
    authority_boundary: 'Synthetic browser regression; no authority.',
  },
  canAccess: (moduleId) => ['dashboard', 'ai_assistant'].includes(moduleId),
  refreshAccess: async () => undefined,
  signOut: async () => undefined,
}

async function verifyAssistantVisibility(): Promise<void> {
  window.localStorage.clear()
  window.fetch = async (input) => {
    const url = requestUrl(input)
    if (url.pathname.endsWith('/knowledge/status')) {
      return jsonResponse({
        ready: true,
        documents: 0,
        chunks: 0,
        departments: [],
        database: 'synthetic',
      })
    }
    if (url.pathname.endsWith('/knowledge/reindex/status')) {
      return jsonResponse({
        running: false,
        status: 'idle',
        started_at: null,
        completed_at: null,
        return_code: null,
        message: 'Synthetic browser regression only.',
        output: '',
      })
    }
    return unexpectedFetch()
  }

  const { host, root } = mount(
    <AccessContext.Provider value={access}>
      <App />
    </AccessContext.Provider>,
  )
  await waitFor(
    () => host.querySelector('[aria-label="Toggle AI assistant"]') !== null,
    'The actual application shell did not render.',
  )
  assert(
    host.querySelector('.desktop-assistant-panel') === null,
    'The local assistant panel opened on initial render.',
  )

  const toggle = host.querySelector<HTMLButtonElement>(
    '[aria-label="Toggle AI assistant"]',
  )
  assert(toggle, 'The explicit titlebar assistant toggle is unavailable.')
  toggle.click()
  await waitFor(
    () => host.querySelector('.desktop-assistant-panel') !== null,
    'The explicit titlebar toggle did not open the assistant.',
  )

  const askAi = Array.from(host.querySelectorAll<HTMLButtonElement>('button'))
    .find((button) => button.textContent?.trim() === 'Ask AI')
  assert(askAi, 'The authorized full-page Ask AI navigation is unavailable.')
  askAi.click()
  await waitFor(
    () => (
      host.querySelector('.desktop-assistant-panel') === null
      && host.querySelector('.full-assistant-page') !== null
    ),
    'Full-page Ask AI navigation did not close the assistant panel.',
  )

  toggle.click()
  await waitFor(
    () => host.querySelector('.desktop-assistant-panel') !== null,
    'The titlebar toggle did not reopen the assistant for navigation proof.',
  )

  const home = Array.from(host.querySelectorAll<HTMLButtonElement>('button'))
    .find((button) => button.textContent?.trim() === 'Home')
  assert(home, 'The authorized Home navigation control is unavailable.')
  home.click()
  await waitFor(
    () => host.querySelector('.desktop-assistant-panel') === null,
    'Successful workspace navigation did not close the assistant.',
  )
  root.unmount()
}

function Thrower(): never {
  throw new Error('R67_EXPECTED_BOUNDARY_THROW')
}

function RecoverableBoundaryHarness({
  onReturnHome,
}: {
  onReturnHome: () => void
}) {
  const [throwing, setThrowing] = useState(true)
  return (
    <div data-shell-sentinel="present">
      <WorkspaceErrorBoundary
        workspaceName="Synthetic Workspace"
        onReturnHome={() => {
          setThrowing(false)
          onReturnHome()
        }}
      >
        {throwing ? <Thrower /> : <div>RECOVERED-DASHBOARD</div>}
      </WorkspaceErrorBoundary>
    </div>
  )
}

async function verifyVisibleErrorBoundary(): Promise<void> {
  let returnedHome = false
  const { host, root } = mount(
    <RecoverableBoundaryHarness
      onReturnHome={() => { returnedHome = true }}
    />,
  )
  await waitFor(
    () => host.querySelector('[role="alert"]') !== null,
    'The workspace error boundary did not render a visible fallback.',
  )
  assert(
    host.querySelector('[data-shell-sentinel="present"]') !== null,
    'The workspace error boundary removed the surrounding shell.',
  )
  assert(
    !host.textContent?.includes('R67_EXPECTED_BOUNDARY_THROW'),
    'The visible error fallback exposed raw exception details.',
  )
  const returnButton = Array.from(
    host.querySelectorAll<HTMLButtonElement>('button'),
  ).find((button) => button.textContent?.includes('Return to Dashboard'))
  assert(returnButton, 'The visible error fallback has no dashboard action.')
  returnButton.click()
  await waitFor(
    () => host.textContent?.includes('RECOVERED-DASHBOARD') === true,
    'The dashboard fallback action did not recover the workspace boundary.',
  )
  assert(returnedHome, 'The dashboard fallback callback did not execute.')
  assert(
    host.querySelector('[role="alert"]') === null,
    'The visible error fallback did not clear after recovery.',
  )
  root.unmount()
}

async function main(): Promise<void> {
  assert(
    import.meta.env.VITE_ETOP_ENVIRONMENT === 'isolated_test',
    'R6.7 browser regression is restricted to the isolated test environment.',
  )
  await verifyLockboxTransition()
  await verifyAssistantVisibility()
  await verifyVisibleErrorBoundary()
  assert(
    window.__etopR67UnexpectedErrors.length === 0,
    'The R6.7 browser regression observed an unexpected runtime error.',
  )
  document.body.replaceChildren()
  document.body.dataset.r67Status = 'passed'
  const marker = document.createElement('div')
  marker.id = 'r67-browser-pass'
  marker.textContent = 'R67_BROWSER_HARNESS_PASS'
  document.body.append(marker)
}

void main().catch(() => {
  document.body.replaceChildren()
  document.body.dataset.r67Status = 'failed'
  document.body.textContent = 'R67_BROWSER_HARNESS_FAILED'
})
