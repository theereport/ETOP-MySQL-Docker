import {
  FormEvent,
  KeyboardEvent,
  useEffect,
  useRef,
  useState,
} from 'react'
import './App.css'

type ModuleStatus = 'Ready' | 'Coming Soon'

type AssistantMode = 'knowledge' | 'general'

type WorkbenchModule = {
  title: string
  description: string
  icon: string
  status: ModuleStatus
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

const modules: WorkbenchModule[] = [
  {
    title: 'AI Assistant',
    description: 'Chat with local AI or search company knowledge.',
    icon: '🤖',
    status: 'Ready',
  },
  {
    title: 'SQL Workspace',
    description: 'Create, save, and organize SQL queries.',
    icon: '🗄️',
    status: 'Coming Soon',
  },
  {
    title: 'Report Builder',
    description: 'Build accounting and operational reports.',
    icon: '📊',
    status: 'Coming Soon',
  },
  {
    title: 'SOP Search',
    description: 'Manage and search company procedures and documentation.',
    icon: '📄',
    status: 'Ready',
  },
  {
    title: 'Automation Center',
    description: 'Manage PowerShell and Python automations.',
    icon: '⚙️',
    status: 'Coming Soon',
  },
  {
    title: 'Project Tracker',
    description: 'Track ERP modernization and improvement projects.',
    icon: '📁',
    status: 'Coming Soon',
  },
]

function App() {
  const [selectedModule, setSelectedModule] = useState('Dashboard')

  const [assistantMode, setAssistantMode] =
    useState<AssistantMode>('knowledge')

  const [selectedDepartment, setSelectedDepartment] =
    useState('')

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      content:
        'I am your local Enterprise AI Assistant. Company Knowledge mode searches your indexed SOPs. General Local AI mode uses Gemma without searching company documents.',
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

  async function loadKnowledgeStatus() {
    setIsRefreshingKnowledge(true)
    setKnowledgeError('')

    try {
      const [knowledgeResponse, jobResponse] = await Promise.all([
        fetch('http://127.0.0.1:8000/knowledge/status'),
        fetch(
          'http://127.0.0.1:8000/knowledge/reindex/status',
        ),
      ])

      if (!knowledgeResponse.ok || !jobResponse.ok) {
        throw new Error(
          'Unable to load the local knowledge-base status.',
        )
      }

      const knowledgeData: KnowledgeStatus =
        await knowledgeResponse.json()

      const jobData: IndexJobStatus =
        await jobResponse.json()

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
          ? 'http://127.0.0.1:8000/knowledge/chat'
          : 'http://127.0.0.1:8000/chat'

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

      if (!response.ok) {
        const errorData = await response
          .json()
          .catch(() => null)

        throw new Error(
          errorData?.detail ??
            `Backend request failed: ${response.status}`,
        )
      }

      if (assistantMode === 'knowledge') {
        const data: {
          response: string
          model: string
          search_mode: string
          sources: ChatSource[]
        } = await response.json()

        setMessages((currentMessages) => [
          ...currentMessages,
          {
            role: 'assistant',
            content: data.response,
            sources: data.sources,
          },
        ])
      } else {
        const data: {
          response: string
          model: string
        } = await response.json()

        setMessages((currentMessages) => [
          ...currentMessages,
          {
            role: 'assistant',
            content: data.response,
          },
        ])
      }
    } catch (requestError) {
      const message =
        requestError instanceof Error
          ? requestError.message
          : 'Unable to reach the local AI backend.'

      setError(message)
    } finally {
      setIsLoading(false)
    }
  }

  function clearChat() {
    const openingMessage =
      assistantMode === 'knowledge'
        ? 'Chat cleared. I am ready to search your local company SOPs.'
        : 'Chat cleared. I am ready to help using the local Gemma model.'

    setMessages([
      {
        role: 'assistant',
        content: openingMessage,
      },
    ])

    setError('')
    setCopiedMessageIndex(null)
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
            ? 'Company Knowledge mode is active. I will answer using only your indexed local SOPs and display supporting sources.'
            : 'General Local AI mode is active. I will answer using Gemma running locally without searching company SOPs.',
      },
    ])
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
      }, 2000)
    } catch {
      setError('Unable to copy the answer.')
    }
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

  async function updateAllSops() {
    setKnowledgeError('')

    try {
      const response = await fetch(
        'http://127.0.0.1:8000/knowledge/reindex',
        {
          method: 'POST',
        },
      )

      if (!response.ok) {
        const errorData = await response
          .json()
          .catch(() => null)

        throw new Error(
          errorData?.detail ??
            'Unable to start local SOP indexing.',
        )
      }

      await loadKnowledgeStatus()
    } catch (updateError) {
      setKnowledgeError(
        updateError instanceof Error
          ? updateError.message
          : 'Unable to start local SOP indexing.',
      )
    }
  }

  useEffect(() => {
    if (
      selectedModule !== 'SOP Search' &&
      selectedModule !== 'AI Assistant'
    ) {
      return
    }

    void loadKnowledgeStatus()
  }, [selectedModule])

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
  }, [messages, isLoading])

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">AI</div>

          <div>
            <h1>Enterprise AI</h1>
            <p>Workbench</p>
          </div>
        </div>

        <nav className="navigation">
          <button
            className={
              selectedModule === 'Dashboard'
                ? 'nav-item active'
                : 'nav-item'
            }
            onClick={() => setSelectedModule('Dashboard')}
          >
            <span>🏠</span>
            Dashboard
          </button>

          {modules.map((module) => (
            <button
              key={module.title}
              className={
                selectedModule === module.title
                  ? 'nav-item active'
                  : 'nav-item'
              }
              onClick={() =>
                setSelectedModule(module.title)
              }
            >
              <span>{module.icon}</span>
              {module.title}
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="system-status">
            <span className="status-dot" />

            <div>
              <strong>Local System</strong>
              <p>127.0.0.1 only</p>
            </div>
          </div>
        </div>
      </aside>

      <main className="main-content">
        <header className="top-bar">
          <div>
            <p className="eyebrow">
              LOCAL ENTERPRISE PLATFORM
            </p>
            <h2>{selectedModule}</h2>
          </div>

          <div className="user-card">
            <div className="user-avatar">JC</div>

            <div>
              <strong>Josh Corbit</strong>
              <p>Administrator</p>
            </div>
          </div>
        </header>

        {selectedModule === 'Dashboard' && (
          <>
            <section className="hero">
              <div>
                <span className="hero-label">
                  Enterprise AI Workbench
                </span>

                <h3>
                  Your local command center for AI, reporting,
                  and automation.
                </h3>

                <p>
                  Search company knowledge, generate SQL,
                  manage reports, build internal tools, and
                  automate repetitive work from one secure local
                  platform.
                </p>

                <button
                  className="primary-button"
                  onClick={() =>
                    setSelectedModule('AI Assistant')
                  }
                >
                  Open AI Assistant
                </button>
              </div>

              <div className="hero-stat">
                <span>Privacy status</span>
                <strong>Local Only</strong>

                <p>
                  React, FastAPI, SQLite, document embeddings,
                  and Ollama are configured for local access.
                </p>
              </div>
            </section>

            <section className="section-heading">
              <div>
                <p className="eyebrow">WORKSPACE</p>
                <h3>Applications</h3>
              </div>

              <span>{modules.length} modules</span>
            </section>

            <section className="module-grid">
              {modules.map((module) => (
                <button
                  className="module-card"
                  key={module.title}
                  onClick={() =>
                    setSelectedModule(module.title)
                  }
                >
                  <div className="module-card-header">
                    <div className="module-icon">
                      {module.icon}
                    </div>

                    <span
                      className={
                        module.status === 'Ready'
                          ? 'module-status ready'
                          : 'module-status'
                      }
                    >
                      {module.status}
                    </span>
                  </div>

                  <h4>{module.title}</h4>
                  <p>{module.description}</p>

                  <div className="module-link">
                    Open module <span>→</span>
                  </div>
                </button>
              ))}
            </section>
          </>
        )}

        {selectedModule === 'AI Assistant' && (
          <section className="chat-page">
            <div className="chat-header">
              <div>
                <p className="eyebrow">
                  LOCAL AI INTELLIGENCE
                </p>

                <h3>Enterprise AI Assistant</h3>

                <p>
                  Model: gemma3:12b · Connection:
                  127.0.0.1
                </p>
              </div>

              <button
                className="secondary-button"
                onClick={clearChat}
              >
                Clear chat
              </button>
            </div>

            <div className="assistant-controls">
              <div className="assistant-mode-group">
                <span className="control-label">
                  Assistant mode
                </span>

                <div className="mode-selector">
                  <button
                    type="button"
                    className={
                      assistantMode === 'knowledge'
                        ? 'mode-button active'
                        : 'mode-button'
                    }
                    onClick={() =>
                      changeAssistantMode('knowledge')
                    }
                  >
                    <span>📚</span>
                    Company Knowledge
                  </button>

                  <button
                    type="button"
                    className={
                      assistantMode === 'general'
                        ? 'mode-button active'
                        : 'mode-button'
                    }
                    onClick={() =>
                      changeAssistantMode('general')
                    }
                  >
                    <span>🤖</span>
                    General Local AI
                  </button>
                </div>
              </div>

              {assistantMode === 'knowledge' && (
                <label className="department-filter">
                  <span className="control-label">
                    Department
                  </span>

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
                </label>
              )}
            </div>

            <div
              className={
                assistantMode === 'knowledge'
                  ? 'assistant-mode-notice knowledge'
                  : 'assistant-mode-notice general'
              }
            >
              <strong>
                {assistantMode === 'knowledge'
                  ? 'Company Knowledge mode'
                  : 'General Local AI mode'}
              </strong>

              <span>
                {assistantMode === 'knowledge'
                  ? selectedDepartment
                    ? `Searching only the ${selectedDepartment} SOP index.`
                    : 'Searching all indexed company SOP departments.'
                  : 'Using the local Gemma model without searching company SOPs.'}
              </span>
            </div>

            <div className="chat-messages">
              {messages.map((message, index) => (
                <div
                  className={`chat-row ${message.role}`}
                  key={`${message.role}-${index}`}
                >
                  <div className="chat-avatar">
                    {message.role === 'user' ? 'JC' : 'AI'}
                  </div>

                  <div className="chat-bubble">
                    <div className="chat-bubble-header">
                      <strong>
                        {message.role === 'user'
                          ? 'You'
                          : 'Local Assistant'}
                      </strong>

                      {message.role === 'assistant' && (
                        <button
                          type="button"
                          className="copy-answer-button"
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
                        <div className="source-list">
                          <strong>Local sources</strong>

                          {message.sources.map(
                            (source, sourceIndex) => (
                              <details
                                className="source-item source-details"
                                key={`${source.file_path}-${source.chunk_number}-${sourceIndex}`}
                              >
                                <summary>
                                  <span>
                                    [{sourceIndex + 1}]{' '}
                                    {source.file_path}
                                    {source.page_number !== null
                                      ? ` · Page ${source.page_number}`
                                      : ''}
                                  </span>

                                  <small>
                                    Match:{' '}
                                    {(
                                      source.similarity * 100
                                    ).toFixed(1)}
                                    %
                                  </small>
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
                <div className="chat-row assistant">
                  <div className="chat-avatar">AI</div>

                  <div className="chat-bubble">
                    <strong>Local Assistant</strong>

                    <p>
                      {assistantMode === 'knowledge'
                        ? 'Searching local SOPs and thinking…'
                        : 'Thinking locally…'}
                    </p>
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {error && (
              <div className="chat-error">{error}</div>
            )}

            <form
              className="chat-form"
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
                    ? 'Ask a question about your company SOPs...'
                    : 'Ask the local Gemma model anything...'
                }
                rows={3}
                disabled={isLoading}
              />

              <button
                className="send-button"
                type="submit"
                disabled={isLoading || !input.trim()}
              >
                {isLoading ? 'Generating…' : 'Send'}
              </button>
            </form>

            <p className="chat-keyboard-note">
              Press Enter to send. Press Shift + Enter for a
              new line.
            </p>

            <p className="privacy-note">
              {assistantMode === 'knowledge'
                ? 'Local path: Browser → FastAPI → SQLite SOP index → Ollama.'
                : 'Local path: Browser → FastAPI → Ollama.'}{' '}
              No cloud AI API is configured.
            </p>
          </section>
        )}

        {selectedModule === 'SOP Search' && (
          <section className="knowledge-page">
            <div className="knowledge-header">
              <div>
                <p className="eyebrow">
                  LOCAL DOCUMENT INTELLIGENCE
                </p>

                <h3>Knowledge Base</h3>

                <p>
                  Manage the company SOP index stored locally on
                  this computer.
                </p>
              </div>

              <div className="knowledge-actions">
                <button
                  className="secondary-button"
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
                  className="primary-button"
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
              <div className="chat-error">
                {knowledgeError}
              </div>
            )}

            <div className="knowledge-stats">
              <div className="knowledge-stat-card">
                <span>Documents</span>
                <strong>
                  {knowledgeStatus?.documents ?? '—'}
                </strong>
              </div>

              <div className="knowledge-stat-card">
                <span>Searchable chunks</span>
                <strong>
                  {knowledgeStatus?.chunks ?? '—'}
                </strong>
              </div>

              <div className="knowledge-stat-card">
                <span>Departments</span>
                <strong>
                  {knowledgeStatus?.departments?.length ??
                    '—'}
                </strong>
              </div>

              <div className="knowledge-stat-card">
                <span>Status</span>
                <strong>
                  {indexStatus?.running
                    ? 'Updating'
                    : knowledgeStatus?.ready
                      ? 'Ready'
                      : 'Not Ready'}
                </strong>
              </div>
            </div>

            <div className="knowledge-grid">
              <div className="knowledge-panel">
                <h4>Indexing status</h4>

                <div
                  className={`index-status ${
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
                        'Load the current indexing status.'}
                    </p>
                  </div>
                </div>

                <dl className="knowledge-details">
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

              <div className="knowledge-panel">
                <h4>Indexed departments</h4>

                <div className="department-list">
                  {knowledgeStatus?.departments?.length ? (
                    knowledgeStatus.departments.map(
                      (department) => (
                        <span key={department}>
                          {department}
                        </span>
                      ),
                    )
                  ) : (
                    <p>
                      No indexed departments were found.
                    </p>
                  )}
                </div>
              </div>
            </div>

            {indexStatus?.output && (
              <details className="index-output">
                <summary>
                  View latest indexing log
                </summary>

                <pre>{indexStatus.output}</pre>
              </details>
            )}
          </section>
        )}

        {selectedModule !== 'Dashboard' &&
          selectedModule !== 'AI Assistant' &&
          selectedModule !== 'SOP Search' && (
            <section className="module-page">
              <div className="large-icon">
                {
                  modules.find(
                    (module) =>
                      module.title === selectedModule,
                  )?.icon
                }
              </div>

              <p className="eyebrow">MODULE</p>
              <h3>{selectedModule}</h3>

              <p>
                This module has been added to the application
                shell. Its working functionality will be built
                in a later phase.
              </p>

              <button
                className="secondary-button"
                onClick={() =>
                  setSelectedModule('Dashboard')
                }
              >
                Return to dashboard
              </button>
            </section>
          )}
      </main>
    </div>
  )
}

export default App