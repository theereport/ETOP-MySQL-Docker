import {
  type FormEvent,
  type KeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

import './App.css'
import './DesktopShell.css'
import SqlWorkspace from './components/SqlWorkspace'

type ModuleStatus = 'Ready' | 'Coming Soon'
type AssistantMode = 'knowledge' | 'general'

type WorkbenchModule = {
  title: string
  shortTitle: string
  description: string
  icon: string
  status: ModuleStatus
  group: 'Core' | 'Data' | 'Operations'
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

const modules: WorkbenchModule[] = [
  {
    title: 'Dashboard',
    shortTitle: 'Dashboard',
    description: 'Enterprise command center and system overview.',
    icon: '⌂',
    status: 'Ready',
    group: 'Core',
  },
  {
    title: 'AI Assistant',
    shortTitle: 'AI Assistant',
    description: 'Use local AI and indexed company knowledge.',
    icon: '✦',
    status: 'Ready',
    group: 'Core',
  },
  {
    title: 'SQL Workspace',
    shortTitle: 'SQL Studio',
    description: 'Create, execute, save, and organize SQL queries.',
    icon: '⌘',
    status: 'Ready',
    group: 'Data',
  },
  {
    title: 'SOP Search',
    shortTitle: 'Knowledge Base',
    description: 'Manage and search indexed company procedures.',
    icon: '▤',
    status: 'Ready',
    group: 'Data',
  },
  {
    title: 'Report Builder',
    shortTitle: 'Report Builder',
    description: 'Create accounting and operational reports.',
    icon: '▥',
    status: 'Coming Soon',
    group: 'Data',
  },
  {
    title: 'Automation Center',
    shortTitle: 'Automation',
    description: 'Manage PowerShell and Python automations.',
    icon: '⚙',
    status: 'Coming Soon',
    group: 'Operations',
  },
  {
    title: 'Project Tracker',
    shortTitle: 'Projects',
    description: 'Track transformation and technology projects.',
    icon: '◇',
    status: 'Coming Soon',
    group: 'Operations',
  },
]

const navigationGroups = ['Core', 'Data', 'Operations'] as const

function App() {
  const [selectedModule, setSelectedModule] =
    useState<string>('Dashboard')

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [assistantPanelOpen, setAssistantPanelOpen] = useState(true)
  const [commandSearch, setCommandSearch] = useState('')

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

  const currentModule = useMemo(() => {
    return (
      modules.find((module) => module.title === selectedModule) ??
      modules[0]
    )
  }, [selectedModule])

  const commandMatches = useMemo(() => {
    const search = commandSearch.trim().toLowerCase()

    if (!search) {
      return []
    }

    return modules.filter((module) => {
      return (
        module.title.toLowerCase().includes(search) ||
        module.shortTitle.toLowerCase().includes(search) ||
        module.description.toLowerCase().includes(search)
      )
    })
  }, [commandSearch])

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

  function openModule(moduleName: string) {
    setSelectedModule(moduleName)
    setCommandSearch('')
  }

  useEffect(() => {
    void loadKnowledgeStatus()
  }, [])

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

          <div className="desktop-brand-mark">AI</div>

          <div className="desktop-brand-copy">
            <strong>Enterprise AI Workbench</strong>
            <span>Local Operations Platform</span>
          </div>
        </div>

        <div className="command-center">
          <span className="command-search-icon">⌕</span>

          <input
            value={commandSearch}
            onChange={(event) =>
              setCommandSearch(event.target.value)
            }
            placeholder="Search modules and commands..."
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

          <button
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
          </button>

          <div className="desktop-user">
            <div className="desktop-user-avatar">JC</div>

            <div>
              <strong>Josh Corbit</strong>
              <span>Administrator</span>
            </div>
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
          {navigationGroups.map((group) => (
            <div className="navigation-group" key={group}>
              {!sidebarCollapsed && (
                <div className="navigation-group-title">
                  {group}
                </div>
              )}

              {modules
                .filter((module) => module.group === group)
                .map((module) => (
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
                    <span className="desktop-nav-icon">
                      {module.icon}
                    </span>

                    {!sidebarCollapsed && (
                      <>
                        <span className="desktop-nav-copy">
                          <strong>{module.shortTitle}</strong>

                          {module.status === 'Coming Soon' && (
                            <small>Coming soon</small>
                          )}
                        </span>

                        {selectedModule === module.title && (
                          <span className="nav-active-marker" />
                        )}
                      </>
                    )}
                  </button>
                ))}
            </div>
          ))}
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
          <div className="workspace-breadcrumbs">
            <span>Enterprise AI</span>
            <b>/</b>
            <strong>{currentModule.shortTitle}</strong>
          </div>

          <div className="workspace-toolbar-actions">
            <button
              type="button"
              onClick={() => openModule('Dashboard')}
            >
              Home
            </button>

            <button
              type="button"
              onClick={() => openModule('SQL Workspace')}
            >
              SQL Studio
            </button>

            <button
              type="button"
              onClick={() => openModule('AI Assistant')}
            >
              Full Assistant
            </button>
          </div>
        </div>

        <div className="workspace-content">
          {selectedModule === 'Dashboard' && (
            <section className="desktop-dashboard">
              <div className="desktop-hero">
                <div className="desktop-hero-copy">
                  <span className="workspace-label">
                    ENTERPRISE OPERATIONS WORKBENCH
                  </span>

                  <h1>
                    One local workspace for data, AI, reporting,
                    and process improvement.
                  </h1>

                  <p>
                    Run read-only SQL, search company knowledge,
                    build reports, manage automations, and use
                    local AI without sending company information
                    to a cloud AI service.
                  </p>

                  <div className="desktop-hero-actions">
                    <button
                      type="button"
                      className="desktop-primary-button"
                      onClick={() =>
                        openModule('SQL Workspace')
                      }
                    >
                      Open SQL Studio
                    </button>

                    <button
                      type="button"
                      className="desktop-secondary-button"
                      onClick={() =>
                        openModule('AI Assistant')
                      }
                    >
                      Open AI Assistant
                    </button>
                  </div>
                </div>

                <div className="system-overview-card">
                  <div className="system-overview-header">
                    <span>System status</span>
                    <strong>
                      {systemReady ? 'Operational' : 'Checking'}
                    </strong>
                  </div>

                  <div className="system-overview-grid">
                    <div>
                      <span>AI Model</span>
                      <strong>Gemma 3:12B</strong>
                    </div>

                    <div>
                      <span>Knowledge Documents</span>
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
                      <span>Data Access</span>
                      <strong>Read Only</strong>
                    </div>
                  </div>
                </div>
              </div>

              <div className="dashboard-section-heading">
                <div>
                  <span className="workspace-label">
                    APPLICATIONS
                  </span>
                  <h2>Enterprise modules</h2>
                </div>

                <span>{modules.length - 1} available modules</span>
              </div>

              <div className="desktop-module-grid">
                {modules
                  .filter((module) => module.title !== 'Dashboard')
                  .map((module) => (
                    <button
                      type="button"
                      className="desktop-module-card"
                      key={module.title}
                      onClick={() => openModule(module.title)}
                    >
                      <div className="desktop-module-card-top">
                        <div className="desktop-module-icon">
                          {module.icon}
                        </div>

                        <span
                          className={
                            module.status === 'Ready'
                              ? 'desktop-module-status ready'
                              : 'desktop-module-status'
                          }
                        >
                          {module.status}
                        </span>
                      </div>

                      <strong>{module.shortTitle}</strong>
                      <p>{module.description}</p>

                      <span className="desktop-module-open">
                        Open workspace →
                      </span>
                    </button>
                  ))}
              </div>
            </section>
          )}

          {selectedModule === 'SQL Workspace' && (
            <SqlWorkspace />
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

          {selectedModule !== 'Dashboard' &&
            selectedModule !== 'AI Assistant' &&
            selectedModule !== 'SQL Workspace' &&
            selectedModule !== 'SOP Search' && (
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
        </div>
      </main>

      {assistantPanelOpen && (
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