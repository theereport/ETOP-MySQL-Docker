import {
  type FormEvent,
  type KeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import type { ReactNode } from 'react'


import './App.css'
import './DesktopShell.css'
import SqlWorkspace from './components/SqlWorkspace'
import CashApplication from './components/CashApplication/CashApplication'
import ReportBuilder from './components/ReportBuilder/ReportBuilder'
import AutomationCenter from './components/AutomationCenter/AutomationCenter'
import WorkspaceErrorBoundary from './components/WorkspaceErrorBoundary'
import Customer360 from "./features/customer360/Customer360";
import CreditRiskWorkspace from './features/credit-risk'
import VendorIntelligenceWorkspace from './features/vendor-intelligence'
import ARCollectionsWorkspace from './features/ar-collections'
import FreightLogisticsWorkspace from './features/freight-logistics'
import InventoryPurchasingWorkspace from './features/inventory-purchasing'
import TaxComplianceWorkspace from './features/tax-compliance'
import SalesOrderVisibilityWorkspace from './features/sales-order-visibility'
import PricingContractsWorkspace from './features/pricing-contracts'
import GeneralLedgerWorkspace from './features/general-ledger'
import AccountsPayableWorkspace from './features/accounts-payable'
import FinancialCloseWorkspace from './features/financial-close'
import PaymentNotesWorkspace from './features/payment-notes'
import WorkflowFoundationWorkspace from './features/workflow-foundation'
import {
  SecurityAccessWorkspace,
  useAccess,
} from './features/security-access'
import type { ETOPModuleId } from './features/workflow-foundation/types'
import {
  getWorkflowNotifications,
  getWorkflowTasks,
  getWorkflowToken,
  WORKFLOW_SESSION_EVENT,
} from './features/workflow-foundation'
import EnterpriseDashboard from "./features/enterprise-dashboard/EnterpriseDashboard";
import EnterpriseDocuments from './modules/document-intelligence'
import {
  PlatformCenter,
  getNotifications,
  getTasks,
  type SearchResult,
} from "./platform";
import { moduleManifests } from './platform/registry/manifests'

type AssistantMode = 'knowledge' | 'general'
type CustomerWorkspaceView = 'search' | 'risk-review'

type ModuleStatus =
  | 'Ready'
  | 'Coming Soon'

type ModuleGroup =
  | 'Overview'
  | 'Workspaces'
  | 'Tools'
  | 'System'

type WorkbenchModule = {
  moduleId?: ETOPModuleId
  title: string
  shortTitle: string
  description: string
  hint: string
  group: ModuleGroup
  category?: string
  status: ModuleStatus
  icon: ReactNode
  showInSidebar?: boolean
}

type ChatSource = {
  file_path: string
  file_name: string
  department: string | null
  page_number: number | null
  chunk_number: number
  similarity: number
  excerpt: string
}

type ChatMessage = {
  role: 'user' | 'assistant'
  content: string
  sources?: ChatSource[]
}

type KnowledgeStatus = {
  ready: boolean
  documents: number
  chunks: number
  departments: string[]
  database: string
}

type IndexJobStatus = {
  running: boolean
  status: 'idle' | 'running' | 'completed' | 'failed'
  started_at: string | null
  completed_at: string | null
  return_code: number | null
  message: string
  output: string
}

const API_BASE = 'http://127.0.0.1:8000'

// Sourced from each module's own manifest.ts (see src/platform/registry/manifests.ts)
// instead of one hand-maintained literal — adding a module means adding its
// manifest, not editing this file.
const modules: WorkbenchModule[] = moduleManifests.map((entry) => ({
  moduleId: entry.moduleId as ETOPModuleId | undefined,
  title: entry.title,
  shortTitle: entry.shortTitle,
  description: entry.description,
  hint: entry.hint,
  group: entry.group,
  category: entry.category,
  status: entry.status,
  icon: entry.icon,
  showInSidebar: entry.showInSidebar,
}))

const navigationGroups = ['Overview', 'Workspaces', 'Tools', 'System'] as const

function App() {
  const { session, canAccess, signOut } = useAccess()
  const [selectedModule, setSelectedModule] =
    useState<string>('Dashboard')
  const [customerWorkspaceView, setCustomerWorkspaceView] =
    useState<CustomerWorkspaceView>('search')

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [collapsedCategories, setCollapsedCategories] =
    useState<Record<string, boolean>>({})
  const [assistantPanelOpen, setAssistantPanelOpen] = useState(false)
  const [commandSearch, setCommandSearch] = useState('')
  const [platformCenterMode, setPlatformCenterMode] = useState<'search' | 'notifications' | 'tasks' | 'timeline' | null>(null)
  const [platformRefresh, setPlatformRefresh] = useState(0)
  const [durableBadgeCounts, setDurableBadgeCounts] = useState<{
    notifications: number
    tasks: number
  } | null>(null)
  const [enterpriseSearchTarget, setEnterpriseSearchTarget] =
    useState<SearchResult | null>(null)

  const [assistantMode, setAssistantMode] =
    useState<AssistantMode>('knowledge')

  const [selectedDepartment, setSelectedDepartment] = useState('')

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      content:
        'I am your local Enterprise AI Assistant. Use Company Knowledge mode for indexed SOPs or General Local AI for broader assistance.',
    },
  ])

  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [copiedMessageIndex, setCopiedMessageIndex] =
    useState<number | null>(null)

  const [knowledgeStatus, setKnowledgeStatus] =
    useState<KnowledgeStatus | null>(null)

  const [indexStatus, setIndexStatus] =
    useState<IndexJobStatus | null>(null)

  const [knowledgeError, setKnowledgeError] = useState('')
  const [isRefreshingKnowledge, setIsRefreshingKnowledge] =
    useState(false)

  const messagesEndRef = useRef<HTMLDivElement | null>(null)
  const assistantPanelEndRef = useRef<HTMLDivElement | null>(null)

  const availableModules = useMemo(
    () => modules.filter((module) => (
      module.moduleId ? canAccess(module.moduleId) : false
    )),
    [canAccess],
  )

  const currentModule = useMemo(() => {
    return (
      availableModules.find((module) => module.title === selectedModule) ??
      availableModules[0] ?? modules[0]
    )
  }, [availableModules, selectedModule])

  const commandMatches = useMemo(() => {
    const search = commandSearch.trim().toLowerCase()

    if (!search) {
      return []
    }

    return availableModules.filter((module) => {
      return (
        module.title.toLowerCase().includes(search) ||
        module.shortTitle.toLowerCase().includes(search) ||
        module.description.toLowerCase().includes(search)
      )
    })
  }, [availableModules, commandSearch])

  const systemReady =
    knowledgeStatus?.ready === true && indexStatus?.running !== true

  async function loadKnowledgeStatus() {
    setIsRefreshingKnowledge(true)
    setKnowledgeError('')

    try {
      const [knowledgeResponse, jobResponse] = await Promise.all([
        fetch(`${API_BASE}/knowledge/status`),
        fetch(`${API_BASE}/knowledge/reindex/status`),
      ])

      if (!knowledgeResponse.ok || !jobResponse.ok) {
        throw new Error(
          'Unable to load the local knowledge-base status.',
        )
      }

      const knowledgeData: KnowledgeStatus =
        await knowledgeResponse.json()

      const jobData: IndexJobStatus = await jobResponse.json()

      setKnowledgeStatus(knowledgeData)
      setIndexStatus(jobData)
    } catch (statusError) {
      setKnowledgeError(
        statusError instanceof Error
          ? statusError.message
          : 'Unable to reach the local backend.',
      )
    } finally {
      setIsRefreshingKnowledge(false)
    }
  }

  async function sendMessage(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault()

    const trimmedInput = input.trim()

    if (!trimmedInput || isLoading) {
      return
    }

    const userMessage: ChatMessage = {
      role: 'user',
      content: trimmedInput,
    }

    const updatedMessages = [...messages, userMessage]

    setMessages(updatedMessages)
    setInput('')
    setError('')
    setIsLoading(true)

    try {
      const endpoint =
        assistantMode === 'knowledge'
          ? `${API_BASE}/knowledge/chat`
          : `${API_BASE}/chat`

      const requestBody =
        assistantMode === 'knowledge'
          ? {
              messages: updatedMessages.map((message) => ({
                role: message.role,
                content: message.content,
              })),
              top_k: 6,
              department: selectedDepartment || null,
            }
          : {
              messages: updatedMessages.map((message) => ({
                role: message.role,
                content: message.content,
              })),
            }

      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      })

      const responseBody = await response.json().catch(() => null)

      if (!response.ok) {
        throw new Error(
          responseBody?.detail ??
            `Backend request failed: ${response.status}`,
        )
      }

      setMessages((currentMessages) => [
        ...currentMessages,
        {
          role: 'assistant',
          content: responseBody.response,
          sources:
            assistantMode === 'knowledge'
              ? responseBody.sources
              : undefined,
        },
      ])
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Unable to reach the local AI backend.',
      )
    } finally {
      setIsLoading(false)
    }
  }

  function changeAssistantMode(mode: AssistantMode) {
    if (mode === assistantMode) {
      return
    }

    setAssistantMode(mode)
    setSelectedDepartment('')
    setError('')

    setMessages([
      {
        role: 'assistant',
        content:
          mode === 'knowledge'
            ? 'Company Knowledge mode is active. I will search your indexed local SOPs and show supporting sources.'
            : 'General Local AI mode is active. I will use Gemma locally without searching company documents.',
      },
    ])
  }

  function clearChat() {
    setMessages([
      {
        role: 'assistant',
        content:
          assistantMode === 'knowledge'
            ? 'Chat cleared. I am ready to search your local company knowledge.'
            : 'Chat cleared. I am ready to help using the local Gemma model.',
      },
    ])

    setError('')
    setCopiedMessageIndex(null)
  }

  function handleChatKeyDown(
    event: KeyboardEvent<HTMLTextAreaElement>,
  ) {
    if (
      event.key === 'Enter' &&
      !event.shiftKey &&
      !isLoading
    ) {
      event.preventDefault()
      event.currentTarget.form?.requestSubmit()
    }
  }

  async function copyAnswer(
    content: string,
    messageIndex: number,
  ) {
    try {
      await navigator.clipboard.writeText(content)
      setCopiedMessageIndex(messageIndex)

      window.setTimeout(() => {
        setCopiedMessageIndex(null)
      }, 1800)
    } catch {
      setError('Unable to copy the answer.')
    }
  }

  async function updateAllSops() {
    setKnowledgeError('')

    try {
      const response = await fetch(
        `${API_BASE}/knowledge/reindex`,
        {
          method: 'POST',
        },
      )

      const body = await response.json().catch(() => null)

      if (!response.ok) {
        throw new Error(
          body?.detail ?? 'Unable to start SOP indexing.',
        )
      }

      await loadKnowledgeStatus()
    } catch (updateError) {
      setKnowledgeError(
        updateError instanceof Error
          ? updateError.message
          : 'Unable to start SOP indexing.',
      )
    }
  }

  function openModule(
    moduleName: string,
    targetOrOptions?:
      | SearchResult
      | { customerView?: 'risk-review' },
  ) {
    const requestedModule = modules.find((module) => module.title === moduleName)
    if (!requestedModule?.moduleId || !canAccess(requestedModule.moduleId)) {
      return
    }
    const searchTarget =
      targetOrOptions && 'type' in targetOrOptions
        ? targetOrOptions
        : null

    const customerView =
      targetOrOptions && !('type' in targetOrOptions)
        ? targetOrOptions.customerView
        : undefined

    if (moduleName === 'Customer 360') {
      setCustomerWorkspaceView(customerView ?? 'search')
    }

    setAssistantPanelOpen(false)
    setSelectedModule(moduleName)
    setCommandSearch('')
    setEnterpriseSearchTarget(searchTarget)
  }

  useEffect(() => {
    if (!availableModules.some((module) => module.title === selectedModule)) {
      const fallbackModule = availableModules[0]?.title ?? 'Dashboard'
      const timeoutId = window.setTimeout(() => {
        setAssistantPanelOpen(false)
        setSelectedModule(fallbackModule)
      }, 0)
      return () => window.clearTimeout(timeoutId)
    }
    return undefined
  }, [availableModules, selectedModule])

  useEffect(() => {
    const timeoutId = window.setTimeout(() => {
      if (
        canAccess('dashboard')
        || canAccess('knowledge_base')
        || canAccess('ai_assistant')
      ) {
        void loadKnowledgeStatus()
      }
    }, 0)

    return () => window.clearTimeout(timeoutId)
  }, [canAccess])

  useEffect(() => {
    if (!indexStatus?.running) {
      return
    }

    const intervalId = window.setInterval(() => {
      void loadKnowledgeStatus()
    }, 3000)

    return () => window.clearInterval(intervalId)
  }, [indexStatus?.running])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({
      behavior: 'smooth',
    })

    assistantPanelEndRef.current?.scrollIntoView({
      behavior: 'smooth',
    })
  }, [messages, isLoading])

  useEffect(() => {
    function handlePlatformShortcut(event: globalThis.KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setPlatformCenterMode('search')
      }
      if (event.key === 'Escape') {
        setPlatformCenterMode(null)
      }
    }
    window.addEventListener('keydown', handlePlatformShortcut)
    return () => window.removeEventListener('keydown', handlePlatformShortcut)
  }, [])

  useEffect(() => {
    let active = true
    async function loadDurableBadges() {
      if (!getWorkflowToken() || !canAccess('work_management')) {
        if (active) setDurableBadgeCounts(null)
        return
      }
      try {
        const [notificationResult, taskResult] = await Promise.all([
          getWorkflowNotifications(),
          getWorkflowTasks({ mine: true }),
        ])
        if (active) {
          setDurableBadgeCounts({
            notifications: notificationResult.unread_count,
            tasks: taskResult.items.filter((task) => (
              task.state !== 'completed' && task.state !== 'cancelled'
            )).length,
          })
        }
      } catch {
        if (active) setDurableBadgeCounts(null)
      }
    }
    void loadDurableBadges()
    window.addEventListener(WORKFLOW_SESSION_EVENT, loadDurableBadges)
    return () => {
      active = false
      window.removeEventListener(WORKFLOW_SESSION_EVENT, loadDurableBadges)
    }
  }, [canAccess, platformRefresh])

  const unreadNotificationCount = durableBadgeCounts?.notifications ?? getNotifications().filter(
    (item) => !item.read,
  ).length
  const openTaskCount = durableBadgeCounts?.tasks ?? getTasks().filter(
    (item) => item.status !== 'Completed',
  ).length
  const userInitials = session.user.display_name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('') || 'ET'

  function closePlatformCenter() {
    setPlatformCenterMode(null)
    setPlatformRefresh((value) => value + 1)
  }

  function renderModuleButton(module: WorkbenchModule) {
    return (
      <button
        type="button"
        key={module.title}
        className={
          selectedModule === module.title
            ? 'desktop-nav-item active'
            : 'desktop-nav-item'
        }
        onClick={() => openModule(module.title)}
        title={module.shortTitle}
      >
        <span className="desktop-nav-icon">{module.icon}</span>

        {!sidebarCollapsed && (
          <>
            <span className="desktop-nav-copy">
              <strong>{module.shortTitle}</strong>

              <small>
                {module.status === 'Coming Soon'
                  ? 'Coming soon'
                  : module.hint}
              </small>
            </span>

            {selectedModule === module.title && (
              <span className="nav-active-marker" />
            )}
          </>
        )}
      </button>
    )
  }

  return (
    <div
      className={[
        'desktop-app',
        sidebarCollapsed ? 'sidebar-collapsed' : '',
        assistantPanelOpen ? 'assistant-open' : 'assistant-closed',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <header className="desktop-titlebar">
        <div className="titlebar-left">
          <button
            type="button"
            className="icon-command-button"
            onClick={() =>
              setSidebarCollapsed((current) => !current)
            }
            aria-label="Toggle navigation"
            title="Toggle navigation"
          >
            ☰
          </button>

          <div className="desktop-brand-mark">E</div>

          <div className="desktop-brand-copy">
            <strong>ETOP</strong>
            <span>Enterprise Operations Platform</span>
          </div>
        </div>

        <div className="command-center">
          <span className="command-search-icon">⌕</span>

          <input
            value={commandSearch}
            onChange={(event) => setCommandSearch(event.target.value)}
            onFocus={() => setPlatformCenterMode('search')}
            onClick={() => setPlatformCenterMode('search')}
            placeholder="Search ETOP..."
          />

          <kbd>Ctrl K</kbd>

          {commandMatches.length > 0 && (
            <div className="command-results">
              {commandMatches.map((module) => (
                <button
                  type="button"
                  key={module.title}
                  onClick={() => openModule(module.title)}
                >
                  <span className="command-result-icon">
                    {module.icon}
                  </span>

                  <span>
                    <strong>{module.shortTitle}</strong>
                    <small>{module.description}</small>
                  </span>

                  <em>{module.status}</em>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="titlebar-right">
          <div
            className={
              systemReady
                ? 'connection-pill connected'
                : 'connection-pill'
            }
          >
            <span className="status-dot" />
            Local System
          </div>

          {canAccess('dashboard') && <button type="button" className="icon-command-button platform-badge-button" onClick={() => setPlatformCenterMode('timeline')} title="Enterprise timeline" aria-label="Enterprise timeline">↻</button>}

          {canAccess('work_management') && <button type="button" className="icon-command-button platform-badge-button" onClick={() => setPlatformCenterMode('tasks')} title="My tasks" aria-label="My tasks">✓{openTaskCount > 0 && <span>{openTaskCount}</span>}</button>}

          {canAccess('work_management') && <button type="button" className="icon-command-button platform-badge-button" onClick={() => setPlatformCenterMode('notifications')} title="Notifications" aria-label="Notifications">♢{unreadNotificationCount > 0 && <span>{unreadNotificationCount}</span>}</button>}

          {canAccess('ai_assistant') && <button
            type="button"
            className={
              assistantPanelOpen
                ? 'icon-command-button active'
                : 'icon-command-button'
            }
            onClick={() =>
              setAssistantPanelOpen((current) => !current)
            }
            aria-label="Toggle AI assistant"
            title="Toggle AI assistant"
          >
            ✦
          </button>}

          <div className="desktop-user">
            <div className="desktop-user-avatar">{userInitials}</div>

            <div>
              <strong>{session.user.display_name}</strong>
              <span>{session.user.roles.some((role) => role.role_id === 'workflow_coordinator') ? 'Administrator' : 'ETOP User'}</span>
            </div>
            <button type="button" className="desktop-user-signout" onClick={() => void signOut()}>Sign out</button>
          </div>
        </div>
      </header>

      <aside className="desktop-sidebar">
        <div className="sidebar-workspace-label">
          <span>Workspace</span>

          {!sidebarCollapsed && (
            <strong>Enterprise Operations</strong>
          )}
        </div>

        <nav className="desktop-navigation">
          {navigationGroups.map((group) => {
            const groupModules = availableModules.filter(
              (module) =>
                module.group === group && module.showInSidebar !== false,
            )
            const uncategorized: WorkbenchModule[] = []
            const categoryOrder: string[] = []
            const byCategory = new Map<string, WorkbenchModule[]>()
            for (const module of groupModules) {
              if (!module.category) {
                uncategorized.push(module)
                continue
              }
              if (!byCategory.has(module.category)) {
                byCategory.set(module.category, [])
                categoryOrder.push(module.category)
              }
              byCategory.get(module.category)?.push(module)
            }

            return (
              <div className="navigation-group" key={group}>
                {!sidebarCollapsed && (
                  <div className="navigation-group-title">
                    {group}
                  </div>
                )}

                {uncategorized.map((module) => renderModuleButton(module))}

                {categoryOrder.map((category) => {
                  const categoryModules = byCategory.get(category) ?? []
                  const isCollapsed = collapsedCategories[category] === true

                  return (
                    <div className="navigation-category" key={category}>
                      {!sidebarCollapsed && (
                        <button
                          type="button"
                          className="navigation-category-header"
                          aria-expanded={!isCollapsed}
                          onClick={() =>
                            setCollapsedCategories((current) => ({
                              ...current,
                              [category]: !isCollapsed,
                            }))
                          }
                        >
                          <span
                            className={
                              isCollapsed
                                ? 'navigation-category-chevron collapsed'
                                : 'navigation-category-chevron'
                            }
                          >
                            ▾
                          </span>
                          <span className="navigation-category-label">
                            {category}
                          </span>
                          <span className="navigation-category-count">
                            {categoryModules.length}
                          </span>
                        </button>
                      )}

                      {(sidebarCollapsed || !isCollapsed) && (
                        <div className="navigation-category-items">
                          {categoryModules.map((module) =>
                            renderModuleButton(module))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )
          })}
        </nav>

        <div className="sidebar-system-card">
          <span className="status-dot" />

          {!sidebarCollapsed && (
            <div>
              <strong>Local Mode</strong>
              <span>127.0.0.1 only</span>
            </div>
          )}
        </div>
      </aside>

      <main className="desktop-workspace">
        <div className="workspace-toolbar">
          <div className="workspace-context">
            <div className="workspace-breadcrumbs">
              <span>{currentModule.group}</span>
              <b>/</b>
              <strong>{currentModule.shortTitle}</strong>
            </div>
            <small>{currentModule.description}</small>
          </div>

          <div className="workspace-toolbar-actions">
            {canAccess('dashboard') && <button
              type="button"
              onClick={() => openModule('Dashboard')}
            >
              Home
            </button>}

            {canAccess('lockbox') && <button
              type="button"
              onClick={() => openModule('Lockbox Automation')}
            >
              Lockbox
            </button>}

            {canAccess('ai_assistant') && <button
              type="button"
              onClick={() => openModule('AI Assistant')}
            >
              Ask AI
            </button>}
          </div>
        </div>

        <div className="workspace-content">
          <WorkspaceErrorBoundary
            key={selectedModule}
            workspaceName={currentModule.shortTitle}
            onReturnHome={() => openModule('Dashboard')}
          >
          {selectedModule === 'Dashboard' && (
            <EnterpriseDashboard
              displayName={session.user.display_name}
              systemReady={systemReady}
              knowledgeDocuments={knowledgeStatus?.documents ?? null}
              searchableChunks={knowledgeStatus?.chunks ?? null}
              moduleCount={availableModules.filter(
                (module) =>
                  module.title !== 'Dashboard' &&
                  module.status === 'Ready',
              ).length}
              onOpenModule={openModule}
              canOpenModule={(moduleName) => {
                const module = modules.find((item) => item.title === moduleName)
                return Boolean(module?.moduleId && canAccess(module.moduleId))
              }}
            />
          )}

          {selectedModule === 'SQL Workspace' && (
            <SqlWorkspace />
          )}
         {selectedModule === 'Cash Application' && (
            <CashApplication />
          )} 

          {selectedModule === 'Payment Notes' && (
            <PaymentNotesWorkspace />
          )}

          {selectedModule === 'Customer 360' && (
            <Customer360
              key={`${customerWorkspaceView}:${
                enterpriseSearchTarget?.type === 'Customer'
                  ? String(
                      enterpriseSearchTarget.metadata
                        ?.customerNumber ?? '',
                    )
                  : ''
              }`}
              initialView={customerWorkspaceView}
              initialCustomerNumber={
                enterpriseSearchTarget?.type === 'Customer'
                  ? String(
                      enterpriseSearchTarget.metadata
                        ?.customerNumber ?? '',
                    )
                  : undefined
              }
            />
          )}

          {selectedModule === 'Credit Risk' && (
            <CreditRiskWorkspace />
          )}

          {selectedModule === 'Accounts Payable' && (
            <AccountsPayableWorkspace />
          )}

          {selectedModule === 'Vendor Intelligence' && (
            <VendorIntelligenceWorkspace />
          )}

          {selectedModule === 'AR Collections' && (
            <ARCollectionsWorkspace />
          )}

          {selectedModule === 'Freight & Logistics' && (
            <FreightLogisticsWorkspace />
          )}

          {selectedModule === 'Inventory & Purchasing' && (
            <InventoryPurchasingWorkspace />
          )}

          {selectedModule === 'Tax Compliance' && (
            <TaxComplianceWorkspace />
          )}

          {selectedModule === 'Sales Order Visibility' && (
            <SalesOrderVisibilityWorkspace />
          )}

          {selectedModule === 'Pricing & Contracts' && (
            <PricingContractsWorkspace />
          )}

          {selectedModule === 'General Ledger' && (
            <GeneralLedgerWorkspace />
          )}

          {selectedModule === 'Financial Close' && (
            <FinancialCloseWorkspace
              onOpenWorkManagement={() => openModule('Work Management')}
            />
          )}

          {selectedModule === 'Report Builder' && (
            <ReportBuilder
              initialReportId={
                enterpriseSearchTarget?.type === 'Report'
                  ? String(
                      enterpriseSearchTarget.metadata
                        ?.reportId ?? '',
                    )
                  : undefined
              }
            />
          )}

          {selectedModule === 'Automation Center' && (
            <AutomationCenter />
          )}

          {selectedModule === 'Work Management' && (
            <WorkflowFoundationWorkspace />
          )}

          {selectedModule === 'Security & Access' && (
            <SecurityAccessWorkspace />
          )}

          {selectedModule === 'Document Intelligence' && (
            <EnterpriseDocuments
              workspace="documents"
              initialJobId={
                enterpriseSearchTarget?.type === 'Document'
                  ? String(
                      enterpriseSearchTarget.metadata?.jobId ??
                        '',
                    )
                  : undefined
              }
            />
          )}

          {selectedModule === 'Lockbox Automation' && (
            <EnterpriseDocuments workspace="lockbox" />
          )}

          {selectedModule === 'Document AI Studio' && (
            <EnterpriseDocuments workspace="studio" />
          )}

          {selectedModule === 'AI Assistant' && (
            <section className="full-assistant-page">
              <div className="page-section-header">
                <div>
                  <span className="workspace-label">
                    LOCAL AI INTELLIGENCE
                  </span>

                  <h1>Enterprise AI Assistant</h1>

                  <p>
                    Search company knowledge or work directly
                    with the local Gemma model.
                  </p>
                </div>

                <button
                  type="button"
                  className="desktop-secondary-button"
                  onClick={clearChat}
                >
                  Clear conversation
                </button>
              </div>

              <div className="full-assistant-controls">
                <div className="desktop-segmented-control">
                  <button
                    type="button"
                    className={
                      assistantMode === 'knowledge'
                        ? 'active'
                        : ''
                    }
                    onClick={() =>
                      changeAssistantMode('knowledge')
                    }
                  >
                    Company Knowledge
                  </button>

                  <button
                    type="button"
                    className={
                      assistantMode === 'general'
                        ? 'active'
                        : ''
                    }
                    onClick={() =>
                      changeAssistantMode('general')
                    }
                  >
                    General Local AI
                  </button>
                </div>

                {assistantMode === 'knowledge' && (
                  <select
                    value={selectedDepartment}
                    onChange={(event) =>
                      setSelectedDepartment(
                        event.target.value,
                      )
                    }
                  >
                    <option value="">
                      All indexed departments
                    </option>

                    {knowledgeStatus?.departments?.map(
                      (department) => (
                        <option
                          key={department}
                          value={department}
                        >
                          {department}
                        </option>
                      ),
                    )}
                  </select>
                )}
              </div>

              <div className="full-chat-surface">
                <div className="full-chat-messages">
                  {messages.map((message, index) => (
                    <div
                      className={`desktop-chat-message ${message.role}`}
                      key={`${message.role}-${index}`}
                    >
                      <div className="desktop-chat-avatar">
                        {message.role === 'user' ? 'JC' : 'AI'}
                      </div>

                      <div className="desktop-chat-content">
                        <div className="desktop-chat-heading">
                          <strong>
                            {message.role === 'user'
                              ? 'You'
                              : 'Local Assistant'}
                          </strong>

                          {message.role === 'assistant' && (
                            <button
                              type="button"
                              onClick={() =>
                                void copyAnswer(
                                  message.content,
                                  index,
                                )
                              }
                            >
                              {copiedMessageIndex === index
                                ? 'Copied'
                                : 'Copy'}
                            </button>
                          )}
                        </div>

                        <p>{message.content}</p>

                        {message.sources &&
                          message.sources.length > 0 && (
                            <div className="desktop-source-list">
                              <strong>Supporting sources</strong>

                              {message.sources.map(
                                (source, sourceIndex) => (
                                  <details
                                    key={`${source.file_path}-${source.chunk_number}-${sourceIndex}`}
                                  >
                                    <summary>
                                      [{sourceIndex + 1}]{' '}
                                      {source.file_name}
                                      {source.page_number !== null
                                        ? ` · Page ${source.page_number}`
                                        : ''}
                                    </summary>

                                    <p>{source.excerpt}</p>
                                  </details>
                                ),
                              )}
                            </div>
                          )}
                      </div>
                    </div>
                  ))}

                  {isLoading && (
                    <div className="desktop-chat-message assistant">
                      <div className="desktop-chat-avatar">
                        AI
                      </div>

                      <div className="desktop-chat-content">
                        <strong>Local Assistant</strong>
                        <p>Thinking locally…</p>
                      </div>
                    </div>
                  )}

                  <div ref={messagesEndRef} />
                </div>

                {error && (
                  <div className="desktop-error-banner">
                    {error}
                  </div>
                )}

                <form
                  className="full-chat-composer"
                  onSubmit={sendMessage}
                >
                  <textarea
                    value={input}
                    onChange={(event) =>
                      setInput(event.target.value)
                    }
                    onKeyDown={handleChatKeyDown}
                    placeholder={
                      assistantMode === 'knowledge'
                        ? 'Ask about company SOPs, processes, or policies...'
                        : 'Ask the local AI assistant anything...'
                    }
                    disabled={isLoading}
                  />

                  <button
                    type="submit"
                    disabled={isLoading || !input.trim()}
                  >
                    {isLoading ? 'Generating…' : 'Send'}
                  </button>
                </form>
              </div>
            </section>
          )}

          {selectedModule === 'SOP Search' && (
            <section className="knowledge-desktop-page">
              <div className="page-section-header">
                <div>
                  <span className="workspace-label">
                    LOCAL DOCUMENT INTELLIGENCE
                  </span>

                  <h1>Knowledge Base</h1>

                  <p>
                    Manage the indexed SOP library used by the
                    local assistant.
                  </p>
                </div>

                <div className="page-header-actions">
                  <button
                    type="button"
                    className="desktop-secondary-button"
                    onClick={() =>
                      void loadKnowledgeStatus()
                    }
                    disabled={isRefreshingKnowledge}
                  >
                    {isRefreshingKnowledge
                      ? 'Refreshing…'
                      : 'Refresh Status'}
                  </button>

                  <button
                    type="button"
                    className="desktop-primary-button"
                    onClick={() => void updateAllSops()}
                    disabled={indexStatus?.running === true}
                  >
                    {indexStatus?.running
                      ? 'Indexing SOPs…'
                      : 'Update All SOPs'}
                  </button>
                </div>
              </div>

              {knowledgeError && (
                <div className="desktop-error-banner">
                  {knowledgeError}
                </div>
              )}

              <div className="knowledge-metric-grid">
                <div>
                  <span>Documents</span>
                  <strong>
                    {knowledgeStatus?.documents ?? '—'}
                  </strong>
                </div>

                <div>
                  <span>Searchable Chunks</span>
                  <strong>
                    {knowledgeStatus?.chunks ?? '—'}
                  </strong>
                </div>

                <div>
                  <span>Departments</span>
                  <strong>
                    {knowledgeStatus?.departments?.length ??
                      '—'}
                  </strong>
                </div>

                <div>
                  <span>Index Status</span>
                  <strong>
                    {indexStatus?.running
                      ? 'Updating'
                      : knowledgeStatus?.ready
                        ? 'Ready'
                        : 'Not Ready'}
                  </strong>
                </div>
              </div>

              <div className="knowledge-desktop-grid">
                <div className="desktop-panel-card">
                  <div className="desktop-panel-heading">
                    <div>
                      <strong>Indexing status</strong>
                      <span>
                        Current local document index state
                      </span>
                    </div>
                  </div>

                  <div
                    className={`desktop-index-status ${
                      indexStatus?.status ?? 'idle'
                    }`}
                  >
                    <span className="status-dot" />

                    <div>
                      <strong>
                        {indexStatus?.status ?? 'Idle'}
                      </strong>
                      <p>
                        {indexStatus?.message ??
                          'No indexing task is currently running.'}
                      </p>
                    </div>
                  </div>

                  <dl className="desktop-details-list">
                    <div>
                      <dt>Started</dt>
                      <dd>
                        {indexStatus?.started_at ?? '—'}
                      </dd>
                    </div>

                    <div>
                      <dt>Completed</dt>
                      <dd>
                        {indexStatus?.completed_at ?? '—'}
                      </dd>
                    </div>

                    <div>
                      <dt>Database</dt>
                      <dd>
                        {knowledgeStatus?.database ?? '—'}
                      </dd>
                    </div>
                  </dl>
                </div>

                <div className="desktop-panel-card">
                  <div className="desktop-panel-heading">
                    <div>
                      <strong>Indexed departments</strong>
                      <span>
                        Available department filters
                      </span>
                    </div>
                  </div>

                  <div className="desktop-department-grid">
                    {knowledgeStatus?.departments?.length ? (
                      knowledgeStatus.departments.map(
                        (department) => (
                          <button
                            type="button"
                            key={department}
                            onClick={() => {
                              setSelectedDepartment(department)
                              setAssistantMode('knowledge')
                              openModule('AI Assistant')
                            }}
                          >
                            <span>▤</span>
                            {department}
                          </button>
                        ),
                      )
                    ) : (
                      <p>No departments were found.</p>
                    )}
                  </div>
                </div>
              </div>

              {indexStatus?.output && (
                <details className="desktop-log-panel">
                  <summary>View latest indexing log</summary>
                  <pre>{indexStatus.output}</pre>
                </details>
              )}
            </section>
          )}

          {currentModule.status === 'Coming Soon' && (
            <section className="desktop-coming-soon">
              <div className="coming-soon-icon">
                {currentModule.icon}
              </div>

              <span className="workspace-label">
                MODULE ROADMAP
              </span>

              <h1>{currentModule.shortTitle}</h1>
              <p>{currentModule.description}</p>

              <div className="coming-soon-banner">
                This workspace is included in the application
                architecture and will be built in a future
                development phase.
              </div>

              <button
                type="button"
                className="desktop-primary-button"
                onClick={() => openModule('Dashboard')}
              >
                Return to Dashboard
              </button>
            </section>
          )}
          </WorkspaceErrorBoundary>
        </div>
      </main>

      {assistantPanelOpen && canAccess('ai_assistant') && (
        <aside className="desktop-assistant-panel">
          <div className="assistant-panel-header">
            <div>
              <span className="assistant-panel-icon">✦</span>

              <div>
                <strong>Local AI Assistant</strong>
                <span>Gemma 3:12B</span>
              </div>
            </div>

            <button
              type="button"
              onClick={() => setAssistantPanelOpen(false)}
              aria-label="Close assistant"
            >
              ×
            </button>
          </div>

          <div className="assistant-panel-context">
            <span>Current workspace</span>
            <strong>{currentModule.shortTitle}</strong>
          </div>

          <div className="assistant-panel-mode">
            <button
              type="button"
              className={
                assistantMode === 'knowledge' ? 'active' : ''
              }
              onClick={() =>
                changeAssistantMode('knowledge')
              }
            >
              Knowledge
            </button>

            <button
              type="button"
              className={
                assistantMode === 'general' ? 'active' : ''
              }
              onClick={() =>
                changeAssistantMode('general')
              }
            >
              General
            </button>
          </div>

          {assistantMode === 'knowledge' && (
            <div className="assistant-panel-department">
              <select
                value={selectedDepartment}
                onChange={(event) =>
                  setSelectedDepartment(event.target.value)
                }
              >
                <option value="">All departments</option>

                {knowledgeStatus?.departments?.map(
                  (department) => (
                    <option
                      key={department}
                      value={department}
                    >
                      {department}
                    </option>
                  ),
                )}
              </select>
            </div>
          )}

          <div className="assistant-panel-messages">
            {messages.slice(-8).map((message, index) => (
              <div
                className={`assistant-panel-message ${message.role}`}
                key={`${message.role}-${index}`}
              >
                <strong>
                  {message.role === 'user' ? 'You' : 'AI'}
                </strong>
                <p>{message.content}</p>
              </div>
            ))}

            {isLoading && (
              <div className="assistant-panel-message assistant">
                <strong>AI</strong>
                <p>Thinking locally…</p>
              </div>
            )}

            <div ref={assistantPanelEndRef} />
          </div>

          {error && (
            <div className="assistant-panel-error">
              {error}
            </div>
          )}

          <form
            className="assistant-panel-composer"
            onSubmit={sendMessage}
          >
            <textarea
              value={input}
              onChange={(event) =>
                setInput(event.target.value)
              }
              onKeyDown={handleChatKeyDown}
              placeholder="Ask the local assistant..."
              disabled={isLoading}
            />

            <div>
              <span>Enter to send</span>

              <button
                type="submit"
                disabled={isLoading || !input.trim()}
              >
                Send
              </button>
            </div>
          </form>

          <button
            type="button"
            className="open-full-assistant-button"
            onClick={() => openModule('AI Assistant')}
          >
            Open full assistant
          </button>
        </aside>
      )}

      {platformCenterMode && canAccess('dashboard') && (
        <PlatformCenter
          mode={platformCenterMode}
          onClose={closePlatformCenter}
          onOpenModule={openModule}
        />
      )}

      <footer className="desktop-statusbar">
        <div>
          <span className="status-dot" />
          Connected locally
        </div>

        <div>
          <span>Database</span>
          <strong>Read Only</strong>
        </div>

        <div>
          <span>AI</span>
          <strong>Gemma 3:12B</strong>
        </div>

        <div>
          <span>Knowledge</span>
          <strong>
            {knowledgeStatus?.chunks
              ? `${knowledgeStatus.chunks.toLocaleString()} chunks`
              : 'Checking'}
          </strong>
        </div>

        <div className="statusbar-spacer" />

        <div>
          <strong>Local Enterprise Platform</strong>
        </div>
      </footer>
    </div>
  )
}

export default App
