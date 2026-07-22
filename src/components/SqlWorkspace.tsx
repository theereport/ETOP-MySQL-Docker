import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react'

type ConnectionStatus = {
  connected: boolean
  database: string
  user: string
  server: string
  version: string
  default_limit: number
  maximum_limit: number
}

type SqlResult = {
  success: boolean
  sql: string
  executed_sql: string
  columns: string[]
  rows: Record<string, unknown>[]
  row_count: number
  row_limit: number
  limit_applied: boolean
  execution_ms: number
}

type SavedQuery = {
  id: number
  title: string
  category: string
  description: string
  sql: string
  created_at: string
  updated_at: string
}

type QueryHistoryItem = {
  id: number
  sql: string
  success: boolean
  row_count: number
  execution_ms: number
  error_message: string | null
  executed_at: string
}

const API_BASE = 'http://127.0.0.1:8000'

const STARTER_SQL = `SELECT
    1 AS TestValue;`

function displayCellValue(value: unknown): string {
  if (value === null || value === undefined) {
    return ''
  }

  if (typeof value === 'object') {
    return JSON.stringify(value)
  }

  return String(value)
}

function downloadBlob(blob: Blob, fileName: string) {
  const downloadUrl = URL.createObjectURL(blob)
  const anchor = document.createElement('a')

  anchor.href = downloadUrl
  anchor.download = fileName
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()

  URL.revokeObjectURL(downloadUrl)
}

export default function SqlWorkspace() {
  const [sql, setSql] = useState(STARTER_SQL)
  const [rowLimit, setRowLimit] = useState(500)

  const [connection, setConnection] =
    useState<ConnectionStatus | null>(null)

  const [result, setResult] = useState<SqlResult | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const [isExecuting, setIsExecuting] = useState(false)
  const [isExporting, setIsExporting] = useState(false)
  const [isExplaining, setIsExplaining] = useState(false)

  const [savedQueries, setSavedQueries] = useState<SavedQuery[]>([])
  const [history, setHistory] = useState<QueryHistoryItem[]>([])

  const [selectedSavedQueryId, setSelectedSavedQueryId] =
    useState<number | null>(null)

  const [title, setTitle] = useState('')
  const [category, setCategory] = useState('General')
  const [description, setDescription] = useState('')
  const [librarySearch, setLibrarySearch] = useState('')

  const [activePanel, setActivePanel] =
    useState<'library' | 'history' | 'ai'>('library')

  const [aiResponse, setAiResponse] = useState('')

  const filteredSavedQueries = useMemo(() => {
    const search = librarySearch.trim().toLowerCase()

    if (!search) {
      return savedQueries
    }

    return savedQueries.filter((query) => {
      return (
        query.title.toLowerCase().includes(search) ||
        query.category.toLowerCase().includes(search) ||
        query.description.toLowerCase().includes(search) ||
        query.sql.toLowerCase().includes(search)
      )
    })
  }, [librarySearch, savedQueries])

  const loadConnection = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/sql/connection`)

      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw new Error(
          body?.detail ?? 'Unable to connect to MySQL.',
        )
      }

      const data: ConnectionStatus = await response.json()

      setConnection(data)
      setRowLimit(data.default_limit)
    } catch (requestError) {
      setConnection(null)
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Unable to connect to MySQL.',
      )
    }
  }, [])

  const loadSavedQueries = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/sql/saved`)

      if (!response.ok) {
        throw new Error('Unable to load saved queries.')
      }

      const data: { queries: SavedQuery[] } =
        await response.json()

      setSavedQueries(data.queries)
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Unable to load saved queries.',
      )
    }
  }, [])

  const loadHistory = useCallback(async () => {
    try {
      const response = await fetch(
        `${API_BASE}/sql/history?limit=100`,
      )

      if (!response.ok) {
        throw new Error('Unable to load query history.')
      }

      const data: { history: QueryHistoryItem[] } =
        await response.json()

      setHistory(data.history)
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Unable to load query history.',
      )
    }
  }, [])

  useEffect(() => {
    void loadConnection()
    void loadSavedQueries()
    void loadHistory()
  }, [loadConnection, loadHistory, loadSavedQueries])

  async function executeQuery() {
    if (!sql.trim() || isExecuting) {
      return
    }

    setIsExecuting(true)
    setError('')
    setNotice('')
    setResult(null)

    try {
      const response = await fetch(`${API_BASE}/sql/execute`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          sql,
          row_limit: rowLimit,
        }),
      })

      const body = await response.json().catch(() => null)

      if (!response.ok) {
        throw new Error(
          body?.detail ?? 'The SQL query failed.',
        )
      }

      const queryResult = body as SqlResult

      setResult(queryResult)
      setNotice(
        `Query completed: ${queryResult.row_count.toLocaleString()} rows in ${queryResult.execution_ms.toLocaleString()} ms.`,
      )

      await loadHistory()
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'The SQL query failed.',
      )

      await loadHistory()
    } finally {
      setIsExecuting(false)
    }
  }

  async function exportResults() {
    if (!sql.trim() || isExporting) {
      return
    }

    setIsExporting(true)
    setError('')

    try {
      const response = await fetch(`${API_BASE}/sql/export`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          sql,
          row_limit: rowLimit,
        }),
      })

      if (!response.ok) {
        const body = await response.json().catch(() => null)

        throw new Error(
          body?.detail ?? 'Unable to export the results.',
        )
      }

      const blob = await response.blob()

      downloadBlob(
        blob,
        `sql-results-${new Date()
          .toISOString()
          .replaceAll(':', '-')
          .slice(0, 19)}.csv`,
      )
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Unable to export the results.',
      )
    } finally {
      setIsExporting(false)
    }
  }

  async function saveQuery() {
    if (!title.trim() || !sql.trim()) {
      setError('Enter a query title and SQL before saving.')
      return
    }

    setError('')
    setNotice('')

    try {
      const isUpdating = selectedSavedQueryId !== null

      const response = await fetch(
        isUpdating
          ? `${API_BASE}/sql/saved/${selectedSavedQueryId}`
          : `${API_BASE}/sql/saved`,
        {
          method: isUpdating ? 'PUT' : 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            title,
            category,
            description,
            sql,
          }),
        },
      )

      const body = await response.json().catch(() => null)

      if (!response.ok) {
        throw new Error(
          body?.detail ?? 'Unable to save the query.',
        )
      }

      setNotice(
        isUpdating
          ? 'Saved query updated.'
          : 'Query saved locally.',
      )

      await loadSavedQueries()
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Unable to save the query.',
      )
    }
  }

  function loadSavedQuery(query: SavedQuery) {
    setSelectedSavedQueryId(query.id)
    setTitle(query.title)
    setCategory(query.category)
    setDescription(query.description)
    setSql(query.sql)
    setResult(null)
    setError('')
    setNotice(`Loaded saved query: ${query.title}`)
  }

  async function deleteSavedQuery(query: SavedQuery) {
    const confirmed = window.confirm(
      `Delete the saved query "${query.title}"?`,
    )

    if (!confirmed) {
      return
    }

    try {
      const response = await fetch(
        `${API_BASE}/sql/saved/${query.id}`,
        {
          method: 'DELETE',
        },
      )

      if (!response.ok) {
        const body = await response.json().catch(() => null)

        throw new Error(
          body?.detail ?? 'Unable to delete the query.',
        )
      }

      if (selectedSavedQueryId === query.id) {
        createNewQuery()
      }

      setNotice('Saved query deleted.')
      await loadSavedQueries()
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Unable to delete the query.',
      )
    }
  }

  function duplicateCurrentQuery() {
    setSelectedSavedQueryId(null)
    setTitle(title ? `${title} Copy` : 'Query Copy')
    setNotice(
      'A new unsaved copy was created. Change the title and save it.',
    )
  }

  function createNewQuery() {
    setSelectedSavedQueryId(null)
    setTitle('')
    setCategory('General')
    setDescription('')
    setSql(STARTER_SQL)
    setResult(null)
    setError('')
    setNotice('New query started.')
    setAiResponse('')
  }

  async function copySql() {
    try {
      await navigator.clipboard.writeText(sql)
      setNotice('SQL copied to the clipboard.')
    } catch {
      setError('Unable to copy the SQL.')
    }
  }

  async function explainSql() {
    if (!sql.trim() || isExplaining) {
      return
    }

    setActivePanel('ai')
    setIsExplaining(true)
    setError('')
    setAiResponse('')

    try {
      const response = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          messages: [
            {
              role: 'user',
              content: `Explain the following MySQL query clearly.

Include:
1. What the query does
2. How its joins work
3. How its filters work
4. What each calculated field does
5. Any possible logic, performance, or data-quality concerns
6. Do not change the SQL unless explaining a suggested improvement

SQL:

${sql}`,
            },
          ],
        }),
      })

      const body = await response.json().catch(() => null)

      if (!response.ok) {
        throw new Error(
          body?.detail ?? 'Unable to explain the SQL.',
        )
      }

      setAiResponse(body.response)
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Unable to explain the SQL.',
      )
    } finally {
      setIsExplaining(false)
    }
  }

  async function clearHistory() {
    const confirmed = window.confirm(
      'Clear all locally stored SQL query history?',
    )

    if (!confirmed) {
      return
    }

    try {
      const response = await fetch(`${API_BASE}/sql/history`, {
        method: 'DELETE',
      })

      if (!response.ok) {
        throw new Error('Unable to clear query history.')
      }

      setNotice('Query history cleared.')
      await loadHistory()
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Unable to clear query history.',
      )
    }
  }

  return (
    <section className="sql-workspace">
      <div className="sql-workspace-header">
        <div>
          <p className="eyebrow">READ-ONLY DATA WORKSPACE</p>
          <h3>SQL Workspace</h3>
          <p>
            Write, execute, save, explain, and export MySQL
            queries locally.
          </p>
        </div>

        <div
          className={
            connection?.connected
              ? 'sql-connection connected'
              : 'sql-connection disconnected'
          }
        >
          <span className="status-dot" />

          <div>
            <strong>
              {connection?.connected
                ? 'MySQL Connected'
                : 'MySQL Not Connected'}
            </strong>

            <p>
              {connection?.connected
                ? `${connection.database} · ${connection.user}`
                : 'Check the backend .env settings'}
            </p>
          </div>

          <button
            type="button"
            onClick={() => void loadConnection()}
          >
            Retest
          </button>
        </div>
      </div>

      {error && <div className="chat-error">{error}</div>}

      {notice && <div className="sql-notice">{notice}</div>}

      <div className="sql-layout">
        <div className="sql-main-column">
          <div className="sql-editor-card">
            <div className="sql-query-details">
              <label>
                <span>Query title</span>
                <input
                  value={title}
                  onChange={(event) =>
                    setTitle(event.target.value)
                  }
                  placeholder="Example: Weekly Credit Review"
                />
              </label>

              <label>
                <span>Category</span>
                <input
                  value={category}
                  onChange={(event) =>
                    setCategory(event.target.value)
                  }
                  placeholder="Credit, Sales, Cost, AR..."
                />
              </label>

              <label className="sql-description-field">
                <span>Description</span>
                <input
                  value={description}
                  onChange={(event) =>
                    setDescription(event.target.value)
                  }
                  placeholder="What is this query used for?"
                />
              </label>
            </div>

            <div className="sql-editor-toolbar">
              <div>
                <strong>
                  {selectedSavedQueryId
                    ? `Saved Query #${selectedSavedQueryId}`
                    : 'Unsaved Query'}
                </strong>

                <span>
                  Read-only statements are enforced by the
                  backend.
                </span>
              </div>

              <div className="sql-toolbar-actions">
                <button
                  type="button"
                  className="secondary-button"
                  onClick={createNewQuery}
                >
                  New
                </button>

                <button
                  type="button"
                  className="secondary-button"
                  onClick={duplicateCurrentQuery}
                >
                  Duplicate
                </button>

                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => void copySql()}
                >
                  Copy SQL
                </button>

                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => void saveQuery()}
                >
                  {selectedSavedQueryId ? 'Update' : 'Save'}
                </button>
              </div>
            </div>

            <textarea
              className="sql-editor"
              value={sql}
              onChange={(event) => setSql(event.target.value)}
              spellCheck={false}
              placeholder="Enter a read-only MySQL query..."
            />

            <div className="sql-run-bar">
              <label>
                Row limit
                <input
                  type="number"
                  min={1}
                  max={connection?.maximum_limit ?? 5000}
                  value={rowLimit}
                  onChange={(event) =>
                    setRowLimit(
                      Math.max(
                        1,
                        Number(event.target.value) || 1,
                      ),
                    )
                  }
                />
              </label>

              <div>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => void explainSql()}
                  disabled={isExplaining || !sql.trim()}
                >
                  {isExplaining
                    ? 'Explaining…'
                    : 'Explain with AI'}
                </button>

                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => void exportResults()}
                  disabled={isExporting || !sql.trim()}
                >
                  {isExporting
                    ? 'Exporting…'
                    : 'Export CSV'}
                </button>

                <button
                  type="button"
                  className="primary-button"
                  onClick={() => void executeQuery()}
                  disabled={
                    isExecuting ||
                    !sql.trim() ||
                    !connection?.connected
                  }
                >
                  {isExecuting
                    ? 'Running Query…'
                    : 'Run Query'}
                </button>
              </div>
            </div>
          </div>

          <div className="sql-results-card">
            <div className="sql-results-header">
              <div>
                <h4>Query Results</h4>

                <p>
                  {result
                    ? `${result.row_count.toLocaleString()} rows · ${result.execution_ms.toLocaleString()} ms`
                    : 'Run a query to display results.'}
                </p>
              </div>

              {result?.limit_applied && (
                <span className="sql-limit-badge">
                  LIMIT {result.row_limit} applied
                </span>
              )}
            </div>

            {!result && (
              <div className="sql-empty-results">
                Results will appear here.
              </div>
            )}

            {result && result.columns.length === 0 && (
              <div className="sql-empty-results">
                The query completed but returned no columns.
              </div>
            )}

            {result && result.columns.length > 0 && (
              <div className="sql-table-wrapper">
                <table className="sql-results-table">
                  <thead>
                    <tr>
                      <th>#</th>

                      {result.columns.map((column) => (
                        <th key={column}>{column}</th>
                      ))}
                    </tr>
                  </thead>

                  <tbody>
                    {result.rows.map((row, rowIndex) => (
                      <tr key={rowIndex}>
                        <td>{rowIndex + 1}</td>

                        {result.columns.map((column) => (
                          <td key={`${rowIndex}-${column}`}>
                            {displayCellValue(row[column])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        <aside className="sql-side-panel">
          <div className="sql-panel-tabs">
            <button
              type="button"
              className={
                activePanel === 'library' ? 'active' : ''
              }
              onClick={() => setActivePanel('library')}
            >
              Saved
            </button>

            <button
              type="button"
              className={
                activePanel === 'history' ? 'active' : ''
              }
              onClick={() => setActivePanel('history')}
            >
              History
            </button>

            <button
              type="button"
              className={activePanel === 'ai' ? 'active' : ''}
              onClick={() => setActivePanel('ai')}
            >
              AI
            </button>
          </div>

          {activePanel === 'library' && (
            <div className="sql-panel-content">
              <input
                className="sql-library-search"
                value={librarySearch}
                onChange={(event) =>
                  setLibrarySearch(event.target.value)
                }
                placeholder="Search saved queries..."
              />

              <div className="sql-library-list">
                {filteredSavedQueries.map((query) => (
                  <div
                    className={
                      selectedSavedQueryId === query.id
                        ? 'sql-library-item selected'
                        : 'sql-library-item'
                    }
                    key={query.id}
                  >
                    <button
                      type="button"
                      className="sql-library-load"
                      onClick={() => loadSavedQuery(query)}
                    >
                      <strong>{query.title}</strong>
                      <span>{query.category}</span>
                      <p>
                        {query.description ||
                          'No description entered.'}
                      </p>
                    </button>

                    <button
                      type="button"
                      className="sql-delete-button"
                      onClick={() =>
                        void deleteSavedQuery(query)
                      }
                    >
                      Delete
                    </button>
                  </div>
                ))}

                {filteredSavedQueries.length === 0 && (
                  <p className="sql-panel-empty">
                    No saved queries found.
                  </p>
                )}
              </div>
            </div>
          )}

          {activePanel === 'history' && (
            <div className="sql-panel-content">
              <button
                type="button"
                className="secondary-button sql-clear-history"
                onClick={() => void clearHistory()}
              >
                Clear History
              </button>

              <div className="sql-history-list">
                {history.map((item) => (
                  <button
                    type="button"
                    className="sql-history-item"
                    key={item.id}
                    onClick={() => {
                      setSql(item.sql)
                      setResult(null)
                      setNotice(
                        'Loaded SQL from local query history.',
                      )
                    }}
                  >
                    <div>
                      <strong>
                        {item.success ? 'Successful' : 'Failed'}
                      </strong>

                      <span>{item.executed_at}</span>
                    </div>

                    <p>{item.sql}</p>

                    <small>
                      {item.success
                        ? `${item.row_count} rows · ${item.execution_ms} ms`
                        : item.error_message}
                    </small>
                  </button>
                ))}

                {history.length === 0 && (
                  <p className="sql-panel-empty">
                    No query history has been recorded.
                  </p>
                )}
              </div>
            </div>
          )}

          {activePanel === 'ai' && (
            <div className="sql-panel-content sql-ai-panel">
              <h4>Local SQL Assistant</h4>

              <p>
                Uses your locally running Gemma model. It does
                not execute or modify the query.
              </p>

              {isExplaining && (
                <div className="sql-ai-loading">
                  Analyzing the SQL locally…
                </div>
              )}

              {!isExplaining && aiResponse && (
                <div className="sql-ai-response">
                  {aiResponse}
                </div>
              )}

              {!isExplaining && !aiResponse && (
                <p className="sql-panel-empty">
                  Click Explain with AI to analyze the current
                  SQL.
                </p>
              )}
            </div>
          )}
        </aside>
      </div>
    </section>
  )
}