import type { OnMount } from '@monaco-editor/react'

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'

import DatabaseExplorer from './sqlstudio/DatabaseExplorer'
import SqlAiPanel from './sqlstudio/SqlAiPanel'
import SqlEditor from './sqlstudio/SqlEditor'
import { getSchemaCatalog } from './sqlstudio/api/sqlApi'
import './sqlstudio/SqlStudio.css'

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

type QueryTab = {
  id: string
  title: string
  sql: string
  savedQueryId: number | null
  category: string
  description: string
  isDirty: boolean
}

type SchemaCatalogColumn = {
  name: string
  position: number
  column_type: string
  nullable: boolean
  key: string
  comment: string
}

type SchemaCatalogObject = {
  name: string
  type: 'table' | 'view'
  comment: string
  columns: SchemaCatalogColumn[]
}

type SchemaCatalog = {
  database: string
  objects: SchemaCatalogObject[]
  object_count: number
  column_count: number
}

type GeneratedSqlResponse = {
  success: boolean
  sql: string
  explanation: string
  database: string
  model: string
  schema_objects_used: {
    name: string
    type: 'table' | 'view'
    column_count: number
  }[]
}

type BottomPanel = 'results' | 'messages' | 'history'

type SidePanel =
  | 'database'
  | 'saved'
  | 'history'
  | 'ai'

type StoredSqlWorkspace = {
  tabs: QueryTab[]
  activeTabId: string
}

const API_BASE = 'http://127.0.0.1:8000'

const TAB_STORAGE_KEY = 'enterprise-ai-sql-tabs'
const ACTIVE_TAB_STORAGE_KEY =
  'enterprise-ai-active-sql-tab'

const STARTER_SQL = `SELECT
    1 AS TestValue,
    CURRENT_DATE() AS Today,
    CURRENT_USER() AS ConnectedUser;`

function createTab(
  title = 'Untitled Query',
  sql = STARTER_SQL,
): QueryTab {
  return {
    id: crypto.randomUUID(),
    title,
    sql,
    savedQueryId: null,
    category: 'General',
    description: '',
    isDirty: false,
  }
}

function loadStoredWorkspace(): StoredSqlWorkspace {
  try {
    const rawTabs = localStorage.getItem(TAB_STORAGE_KEY)
    const storedActiveTabId = localStorage.getItem(
      ACTIVE_TAB_STORAGE_KEY,
    )

    if (!rawTabs) {
      const initialTab = createTab('Query 1')

      return {
        tabs: [initialTab],
        activeTabId: initialTab.id,
      }
    }

    const parsedTabs = JSON.parse(rawTabs) as QueryTab[]

    if (!Array.isArray(parsedTabs) || parsedTabs.length === 0) {
      const initialTab = createTab('Query 1')

      return {
        tabs: [initialTab],
        activeTabId: initialTab.id,
      }
    }

    const normalizedTabs = parsedTabs.map((tab) => ({
      ...tab,
      savedQueryId: tab.savedQueryId ?? null,
      category: tab.category || 'General',
      description: tab.description || '',
      isDirty: Boolean(tab.isDirty),
    }))

    const validActiveTabId =
      storedActiveTabId &&
      normalizedTabs.some(
        (tab) => tab.id === storedActiveTabId,
      )
        ? storedActiveTabId
        : normalizedTabs[0].id

    return {
      tabs: normalizedTabs,
      activeTabId: validActiveTabId,
    }
  } catch {
    const initialTab = createTab('Query 1')

    return {
      tabs: [initialTab],
      activeTabId: initialTab.id,
    }
  }
}

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

function formatDateTime(value: string): string {
  const parsed = new Date(value)

  if (Number.isNaN(parsed.getTime())) {
    return value
  }

  return parsed.toLocaleString()
}

function quoteIdentifier(identifier: string): string {
  return `\`${identifier.replaceAll('`', '``')}\``
}

export default function SqlWorkspace() {
  const initialWorkspaceRef = useRef<StoredSqlWorkspace | null>(
    null,
  )

  if (!initialWorkspaceRef.current) {
    initialWorkspaceRef.current = loadStoredWorkspace()
  }

  const [tabs, setTabs] = useState<QueryTab[]>(
    initialWorkspaceRef.current.tabs,
  )

  const [activeTabId, setActiveTabId] = useState(
    initialWorkspaceRef.current.activeTabId,
  )

  const [rowLimit, setRowLimit] = useState(500)

  const [connection, setConnection] =
    useState<ConnectionStatus | null>(null)

  const [result, setResult] = useState<SqlResult | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const [executionMessage, setExecutionMessage] = useState(
    'Run a query to display execution details.',
  )

  const [isExecuting, setIsExecuting] = useState(false)
  const [isExporting, setIsExporting] = useState(false)
  const [isExplaining, setIsExplaining] = useState(false)

  const [savedQueries, setSavedQueries] = useState<
    SavedQuery[]
  >([])

  const [history, setHistory] = useState<
    QueryHistoryItem[]
  >([])

  const [librarySearch, setLibrarySearch] = useState('')

  const [activeSidePanel, setActiveSidePanel] =
    useState<SidePanel>('database')

  const [activeBottomPanel, setActiveBottomPanel] =
    useState<BottomPanel>('results')

  const [aiResponse, setAiResponse] = useState('')

  const [schemaCatalog, setSchemaCatalog] =
    useState<SchemaCatalog | null>(null)

  const [isLoadingSchema, setIsLoadingSchema] =
    useState(false)

  const editorRef =
    useRef<Parameters<OnMount>[0] | null>(null)

  const executeQueryRef =
    useRef<() => Promise<void>>(async () => {})

  const saveQueryRef =
    useRef<() => Promise<void>>(async () => {})

  const activeTab = useMemo(() => {
    return (
      tabs.find((tab) => tab.id === activeTabId) ??
      tabs[0]
    )
  }, [activeTabId, tabs])

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

  const updateActiveTab = useCallback(
    (updates: Partial<QueryTab>) => {
      setTabs((currentTabs) =>
        currentTabs.map((tab) =>
          tab.id === activeTabId
            ? {
                ...tab,
                ...updates,
              }
            : tab,
        ),
      )
    },
    [activeTabId],
  )

  const loadConnection = useCallback(async () => {
    setError('')

    try {
      const response = await fetch(
        `${API_BASE}/sql/connection`,
      )

      const body = await response.json().catch(() => null)

      if (!response.ok) {
        throw new Error(
          body?.detail ?? 'Unable to connect to MySQL.',
        )
      }

      const data = body as ConnectionStatus

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
      const body = await response.json().catch(() => null)

      if (!response.ok) {
        throw new Error(
          body?.detail ?? 'Unable to load saved queries.',
        )
      }

      setSavedQueries(body.queries as SavedQuery[])
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

      const body = await response.json().catch(() => null)

      if (!response.ok) {
        throw new Error(
          body?.detail ?? 'Unable to load query history.',
        )
      }

      setHistory(body.history as QueryHistoryItem[])
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Unable to load query history.',
      )
    }
  }, [])

  const loadSchemaCatalog = useCallback(async () => {
    setIsLoadingSchema(true)

    try {
      const catalog = await getSchemaCatalog()
      setSchemaCatalog(catalog)
    } catch (requestError) {
      setSchemaCatalog(null)

      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Unable to load the schema catalog.',
      )
    } finally {
      setIsLoadingSchema(false)
    }
  }, [])

  useEffect(() => {
    void loadConnection()
    void loadSavedQueries()
    void loadHistory()
    void loadSchemaCatalog()
  }, [
    loadConnection,
    loadHistory,
    loadSavedQueries,
    loadSchemaCatalog,
  ])

  useEffect(() => {
    localStorage.setItem(
      TAB_STORAGE_KEY,
      JSON.stringify(tabs),
    )
  }, [tabs])

  useEffect(() => {
    localStorage.setItem(
      ACTIVE_TAB_STORAGE_KEY,
      activeTabId,
    )
  }, [activeTabId])

  function handleEditorReady(
    editor: Parameters<OnMount>[0],
  ) {
    editorRef.current = editor
  }

  function updateSql(nextSql: string | undefined) {
    updateActiveTab({
      sql: nextSql ?? '',
      isDirty: true,
    })
  }

  function createNewTab() {
    const nextNumber = tabs.length + 1
    const newTab = createTab(`Query ${nextNumber}`)

    setTabs((currentTabs) => [
      ...currentTabs,
      newTab,
    ])

    setActiveTabId(newTab.id)
    setResult(null)
    setError('')
    setNotice('New SQL tab created.')

    setExecutionMessage(
      'Run a query to display execution details.',
    )
  }

  function duplicateTab() {
    const duplicatedTab: QueryTab = {
      ...activeTab,
      id: crypto.randomUUID(),
      title: `${activeTab.title} Copy`,
      savedQueryId: null,
      isDirty: true,
    }

    setTabs((currentTabs) => [
      ...currentTabs,
      duplicatedTab,
    ])

    setActiveTabId(duplicatedTab.id)
    setResult(null)
    setNotice('Query tab duplicated.')
  }

  function closeTab(tabId: string) {
    const tabToClose = tabs.find(
      (tab) => tab.id === tabId,
    )

    if (!tabToClose) {
      return
    }

    if (
      tabToClose.isDirty &&
      !window.confirm(
        `Close "${tabToClose.title}" without saving its latest changes?`,
      )
    ) {
      return
    }

    if (tabs.length === 1) {
      const replacementTab = createTab('Query 1')

      setTabs([replacementTab])
      setActiveTabId(replacementTab.id)
      setResult(null)

      return
    }

    const closingIndex = tabs.findIndex(
      (tab) => tab.id === tabId,
    )

    const remainingTabs = tabs.filter(
      (tab) => tab.id !== tabId,
    )

    setTabs(remainingTabs)

    if (activeTabId === tabId) {
      const nextActiveTab =
        remainingTabs[
          Math.min(
            closingIndex,
            remainingTabs.length - 1,
          )
        ]

      setActiveTabId(nextActiveTab.id)
      setResult(null)
    }
  }

  function renameTab(tabId: string) {
    const tab = tabs.find(
      (currentTab) => currentTab.id === tabId,
    )

    if (!tab) {
      return
    }

    const nextTitle = window.prompt(
      'Enter the query tab name:',
      tab.title,
    )

    if (!nextTitle?.trim()) {
      return
    }

    setTabs((currentTabs) =>
      currentTabs.map((currentTab) =>
        currentTab.id === tabId
          ? {
              ...currentTab,
              title: nextTitle.trim(),
              isDirty: true,
            }
          : currentTab,
      ),
    )
  }

  async function executeQuery() {
    if (!activeTab.sql.trim() || isExecuting) {
      return
    }

    setIsExecuting(true)
    setError('')
    setNotice('')
    setResult(null)
    setActiveBottomPanel('messages')

    setExecutionMessage(
      'Executing query against MySQL…',
    )

    const startedAt = performance.now()

    try {
      const response = await fetch(
        `${API_BASE}/sql/execute`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            sql: activeTab.sql,
            row_limit: rowLimit,
          }),
        },
      )

      const body = await response.json().catch(() => null)

      if (!response.ok) {
        throw new Error(
          body?.detail ?? 'The SQL query failed.',
        )
      }

      const queryResult = body as SqlResult

      setResult(queryResult)

      setExecutionMessage(
        [
          'Query completed successfully.',
          `${queryResult.row_count.toLocaleString()} rows returned.`,
          `${queryResult.execution_ms.toLocaleString()} ms database execution time.`,
          queryResult.limit_applied
            ? `A LIMIT ${queryResult.row_limit} safeguard was applied.`
            : 'The query supplied its own limit or did not require one.',
        ].join('\n'),
      )

      setNotice(
        `Query completed: ${queryResult.row_count.toLocaleString()} rows in ${queryResult.execution_ms.toLocaleString()} ms.`,
      )

      setActiveBottomPanel('results')

      await loadHistory()
    } catch (requestError) {
      const totalMilliseconds = Math.round(
        performance.now() - startedAt,
      )

      const message =
        requestError instanceof Error
          ? requestError.message
          : 'The SQL query failed.'

      setError(message)

      setExecutionMessage(
        `Query failed after ${totalMilliseconds.toLocaleString()} ms.\n\n${message}`,
      )

      setActiveBottomPanel('messages')

      await loadHistory()
    } finally {
      setIsExecuting(false)
    }
  }

  async function exportResults() {
    if (!activeTab.sql.trim() || isExporting) {
      return
    }

    setIsExporting(true)
    setError('')

    try {
      const response = await fetch(
        `${API_BASE}/sql/export`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            sql: activeTab.sql,
            row_limit: rowLimit,
          }),
        },
      )

      if (!response.ok) {
        const body = await response.json().catch(() => null)

        throw new Error(
          body?.detail ??
            'Unable to export the results.',
        )
      }

      const blob = await response.blob()

      const safeTitle =
        activeTab.title
          .replace(/[^a-z0-9-_]+/gi, '-')
          .replace(/^-+|-+$/g, '') || 'sql-results'

      downloadBlob(
        blob,
        `${safeTitle}-${new Date()
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
    if (
      !activeTab.title.trim() ||
      !activeTab.sql.trim()
    ) {
      setError(
        'Enter a query title and SQL before saving.',
      )

      return
    }

    setError('')
    setNotice('')

    try {
      const isUpdating =
        activeTab.savedQueryId !== null

      const response = await fetch(
        isUpdating
          ? `${API_BASE}/sql/saved/${activeTab.savedQueryId}`
          : `${API_BASE}/sql/saved`,
        {
          method: isUpdating ? 'PUT' : 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            title: activeTab.title,
            category: activeTab.category,
            description: activeTab.description,
            sql: activeTab.sql,
          }),
        },
      )

      const body = await response.json().catch(() => null)

      if (!response.ok) {
        throw new Error(
          body?.detail ?? 'Unable to save the query.',
        )
      }

      updateActiveTab({
        savedQueryId: isUpdating
          ? activeTab.savedQueryId
          : Number(body.id),
        isDirty: false,
      })

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

  function openSavedQuery(query: SavedQuery) {
    const existingTab = tabs.find(
      (tab) => tab.savedQueryId === query.id,
    )

    if (existingTab) {
      setActiveTabId(existingTab.id)
      return
    }

    const queryTab: QueryTab = {
      id: crypto.randomUUID(),
      title: query.title,
      sql: query.sql,
      savedQueryId: query.id,
      category: query.category,
      description: query.description,
      isDirty: false,
    }

    setTabs((currentTabs) => [
      ...currentTabs,
      queryTab,
    ])

    setActiveTabId(queryTab.id)
    setResult(null)

    setNotice(
      `Opened saved query: ${query.title}`,
    )
  }

  async function deleteSavedQuery(query: SavedQuery) {
    if (
      !window.confirm(
        `Delete the saved query "${query.title}"?`,
      )
    ) {
      return
    }

    try {
      const response = await fetch(
        `${API_BASE}/sql/saved/${query.id}`,
        {
          method: 'DELETE',
        },
      )

      const body = await response.json().catch(() => null)

      if (!response.ok) {
        throw new Error(
          body?.detail ??
            'Unable to delete the query.',
        )
      }

      setTabs((currentTabs) =>
        currentTabs.map((tab) =>
          tab.savedQueryId === query.id
            ? {
                ...tab,
                savedQueryId: null,
                isDirty: true,
              }
            : tab,
        ),
      )

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

  async function copySql() {
    try {
      await navigator.clipboard.writeText(
        activeTab.sql,
      )

      setNotice('SQL copied to the clipboard.')
    } catch {
      setError('Unable to copy the SQL.')
    }
  }

  async function explainSql() {
    if (!activeTab.sql.trim() || isExplaining) {
      return
    }

    setActiveSidePanel('ai')
    setIsExplaining(true)
    setError('')
    setAiResponse('')

    try {
      const response = await fetch(
        `${API_BASE}/chat`,
        {
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
2. How each join works
3. How filters and date logic work
4. What calculated fields do
5. Possible logic or data-quality issues
6. Performance concerns
7. Suggested improvements, without changing the original SQL unless you clearly label a revised version

SQL:

${activeTab.sql}`,
              },
            ],
          }),
        },
      )

      const body = await response.json().catch(() => null)

      if (!response.ok) {
        throw new Error(
          body?.detail ??
            'Unable to explain the SQL.',
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

  function openHistoryQuery(
    item: QueryHistoryItem,
  ) {
    const queryTab: QueryTab = {
      id: crypto.randomUUID(),
      title: `History ${item.id}`,
      sql: item.sql,
      savedQueryId: null,
      category: 'History',
      description: `Loaded from query history on ${formatDateTime(
        item.executed_at,
      )}`,
      isDirty: true,
    }

    setTabs((currentTabs) => [
      ...currentTabs,
      queryTab,
    ])

    setActiveTabId(queryTab.id)
    setResult(null)

    setNotice(
      'Query opened from local history.',
    )
  }

  async function clearHistory() {
    if (
      !window.confirm(
        'Clear all locally stored SQL query history?',
      )
    ) {
      return
    }

    try {
      const response = await fetch(
        `${API_BASE}/sql/history`,
        {
          method: 'DELETE',
        },
      )

      if (!response.ok) {
        throw new Error(
          'Unable to clear query history.',
        )
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

  function insertTextIntoEditor(text: string) {
    const editor = editorRef.current

    if (!editor) {
      updateActiveTab({
        sql: `${activeTab.sql}${text}`,
        isDirty: true,
      })

      return
    }

    const selection = editor.getSelection()

    if (!selection) {
      return
    }

    editor.executeEdits('database-explorer', [
      {
        range: selection,
        text,
        forceMoveMarkers: true,
      },
    ])

    editor.focus()
  }

  function openTableQuery(
    tableName: string,
    columns: string[],
  ) {
    const quotedTable = quoteIdentifier(tableName)

    const selectedColumns =
      columns.length > 0 && columns.length <= 40
        ? columns
            .map(
              (column) =>
                `    ${quoteIdentifier(column)}`,
            )
            .join(',\n')
        : '    *'

    const generatedSql = `SELECT
${selectedColumns}
FROM ${quotedTable}
LIMIT 100;`

    const newTab: QueryTab = {
      id: crypto.randomUUID(),
      title: tableName,
      sql: generatedSql,
      savedQueryId: null,
      category: 'Schema Explorer',
      description: `Generated from database object ${tableName}.`,
      isDirty: true,
    }

    setTabs((currentTabs) => [
      ...currentTabs,
      newTab,
    ])

    setActiveTabId(newTab.id)
    setResult(null)

    setExecutionMessage(
      `Generated a read-only SELECT query for ${tableName}.`,
    )

    setNotice(
      `Opened ${tableName} in a new SQL tab.`,
    )
  }

  function openGeneratedSql(
    response: GeneratedSqlResponse,
  ) {
    const nextNumber = tabs.length + 1

    const generatedTab: QueryTab = {
      id: crypto.randomUUID(),
      title: `AI Query ${nextNumber}`,
      sql: response.sql,
      savedQueryId: null,
      category: 'AI Generated',
      description:
        response.explanation ||
        `Generated locally with ${response.model}.`,
      isDirty: true,
    }

    setTabs((currentTabs) => [
      ...currentTabs,
      generatedTab,
    ])

    setActiveTabId(generatedTab.id)
    setResult(null)
    setActiveBottomPanel('messages')

    setExecutionMessage(
      [
        `Generated read-only SQL with ${response.model}.`,
        `${response.schema_objects_used.length} schema objects were supplied to the model.`,
        response.explanation ||
          'Review the generated SQL before running it.',
      ].join('\n\n'),
    )

    setNotice(
      'AI-generated SQL opened in a new query tab.',
    )
  }

  executeQueryRef.current = executeQuery
  saveQueryRef.current = saveQuery

  return (
    <section className="sql-studio">
      <div className="sql-studio-commandbar">
        <div className="sql-studio-connection">
          <span
            className={
              connection?.connected
                ? 'sql-connection-light connected'
                : 'sql-connection-light'
            }
          />

          <div>
            <strong>
              {connection?.connected
                ? connection.database
                : 'MySQL disconnected'}
            </strong>

            <span>
              {connection?.connected
                ? `${connection.user} · Read Only`
                : 'Check backend connection settings'}
            </span>
          </div>
        </div>

        <div className="sql-studio-command-actions">
          <button
            type="button"
            onClick={createNewTab}
            title="New Query"
          >
            ＋ New Query
          </button>

          <button
            type="button"
            onClick={() => void saveQuery()}
            title="Save Query (Ctrl+S)"
          >
            Save
          </button>

          <button
            type="button"
            onClick={() => void copySql()}
          >
            Copy SQL
          </button>

          <button
            type="button"
            onClick={() => void explainSql()}
            disabled={isExplaining}
          >
            {isExplaining
              ? 'Explaining…'
              : 'Explain'}
          </button>

          <label className="sql-row-limit-control">
            Rows

            <input
              type="number"
              min={1}
              max={
                connection?.maximum_limit ?? 5000
              }
              value={rowLimit}
              onChange={(event) =>
                setRowLimit(
                  Math.min(
                    connection?.maximum_limit ??
                      5000,
                    Math.max(
                      1,
                      Number(event.target.value) ||
                        1,
                    ),
                  ),
                )
              }
            />
          </label>

          <button
            type="button"
            className="sql-run-command"
            onClick={() => void executeQuery()}
            disabled={
              isExecuting ||
              !activeTab.sql.trim() ||
              !connection?.connected
            }
            title="Run Query (Ctrl+Enter or F5)"
          >
            {isExecuting ? 'Running…' : '▶ Run'}
          </button>
        </div>
      </div>

      {error && (
        <div className="sql-studio-error">
          {error}
        </div>
      )}

      {notice && (
        <div className="sql-studio-notice">
          {notice}
        </div>
      )}

      <div className="sql-studio-layout">
        <aside className="sql-studio-left-panel">
          <div className="sql-studio-panel-title">
            <strong>Explorer</strong>

            {isLoadingSchema && (
              <span>Loading schema…</span>
            )}
          </div>

          <div className="sql-studio-side-tabs four-tabs">
            <button
              type="button"
              className={
                activeSidePanel === 'database'
                  ? 'active'
                  : ''
              }
              onClick={() =>
                setActiveSidePanel('database')
              }
            >
              Database
            </button>

            <button
              type="button"
              className={
                activeSidePanel === 'saved'
                  ? 'active'
                  : ''
              }
              onClick={() =>
                setActiveSidePanel('saved')
              }
            >
              Saved
            </button>

            <button
              type="button"
              className={
                activeSidePanel === 'history'
                  ? 'active'
                  : ''
              }
              onClick={() =>
                setActiveSidePanel('history')
              }
            >
              History
            </button>

            <button
              type="button"
              className={
                activeSidePanel === 'ai'
                  ? 'active'
                  : ''
              }
              onClick={() =>
                setActiveSidePanel('ai')
              }
            >
              AI
            </button>
          </div>

          {activeSidePanel === 'database' && (
            <DatabaseExplorer
              onOpenTableQuery={openTableQuery}
              onInsertText={insertTextIntoEditor}
            />
          )}

          {activeSidePanel === 'saved' && (
            <div className="sql-studio-side-content">
              <input
                className="sql-studio-search"
                value={librarySearch}
                onChange={(event) =>
                  setLibrarySearch(
                    event.target.value,
                  )
                }
                placeholder="Search saved queries..."
              />

              <div className="sql-studio-query-list">
                {filteredSavedQueries.map(
                  (query) => (
                    <div
                      className="sql-studio-query-item"
                      key={query.id}
                    >
                      <button
                        type="button"
                        className="sql-studio-query-open"
                        onClick={() =>
                          openSavedQuery(query)
                        }
                      >
                        <span className="sql-file-icon">
                          SQL
                        </span>

                        <span>
                          <strong>
                            {query.title}
                          </strong>

                          <small>
                            {query.category}
                          </small>
                        </span>
                      </button>

                      <button
                        type="button"
                        className="sql-query-delete"
                        onClick={() =>
                          void deleteSavedQuery(
                            query,
                          )
                        }
                        title="Delete saved query"
                      >
                        ×
                      </button>
                    </div>
                  ),
                )}

                {filteredSavedQueries.length ===
                  0 && (
                  <p className="sql-studio-empty">
                    No saved queries found.
                  </p>
                )}
              </div>
            </div>
          )}

          {activeSidePanel === 'history' && (
            <div className="sql-studio-side-content">
              <button
                type="button"
                className="sql-studio-clear-history"
                onClick={() =>
                  void clearHistory()
                }
              >
                Clear History
              </button>

              <div className="sql-studio-history-list">
                {history.map((item) => (
                  <button
                    type="button"
                    key={item.id}
                    className="sql-studio-history-item"
                    onClick={() =>
                      openHistoryQuery(item)
                    }
                  >
                    <span
                      className={
                        item.success
                          ? 'history-state successful'
                          : 'history-state failed'
                      }
                    />

                    <span>
                      <strong>
                        {item.success
                          ? `${item.row_count} rows`
                          : 'Failed'}
                      </strong>

                      <small>
                        {formatDateTime(
                          item.executed_at,
                        )}
                      </small>

                      <p>{item.sql}</p>
                    </span>
                  </button>
                ))}

                {history.length === 0 && (
                  <p className="sql-studio-empty">
                    No query history recorded.
                  </p>
                )}
              </div>
            </div>
          )}

          {activeSidePanel === 'ai' && (
            <div className="sql-studio-side-content sql-studio-ai">
              <SqlAiPanel
                currentSql={activeTab.sql}
                schemaCatalog={schemaCatalog}
                onGenerated={openGeneratedSql}
                onError={(message) => setError(message)}
              />

              <div className="sql-ai-existing-query">
                <strong>Explain Active Query</strong>

                <p>
                  Analyze the SQL currently open in the editor
                  using Gemma running locally.
                </p>

                <button
                  type="button"
                  onClick={() => void explainSql()}
                  disabled={isExplaining}
                >
                  {isExplaining
                    ? 'Analyzing SQL…'
                    : 'Explain Active Query'}
                </button>

                {aiResponse && (
                  <div className="sql-studio-ai-response">
                    {aiResponse}
                  </div>
                )}
              </div>
            </div>
          )}
        </aside>

        <div className="sql-studio-center">
          <div className="sql-editor-tabs">
            <div className="sql-editor-tab-list">
              {tabs.map((tab) => (
                <button
                  type="button"
                  key={tab.id}
                  className={
                    tab.id === activeTabId
                      ? 'sql-editor-tab active'
                      : 'sql-editor-tab'
                  }
                  onClick={() => {
                    setActiveTabId(tab.id)
                    setResult(null)
                  }}
                  onDoubleClick={() =>
                    renameTab(tab.id)
                  }
                >
                  <span className="sql-tab-file-icon">
                    SQL
                  </span>

                  <span className="sql-tab-title">
                    {tab.title}
                  </span>

                  {tab.isDirty && (
                    <span
                      className="sql-tab-dirty"
                      title="Unsaved changes"
                    >
                      ●
                    </span>
                  )}

                  <span
                    role="button"
                    tabIndex={0}
                    className="sql-tab-close"
                    onClick={(event) => {
                      event.stopPropagation()
                      closeTab(tab.id)
                    }}
                    onKeyDown={(event) => {
                      if (
                        event.key === 'Enter' ||
                        event.key === ' '
                      ) {
                        event.preventDefault()
                        event.stopPropagation()
                        closeTab(tab.id)
                      }
                    }}
                  >
                    ×
                  </span>
                </button>
              ))}
            </div>

            <button
              type="button"
              className="sql-new-tab-button"
              onClick={createNewTab}
              title="New query tab"
            >
              ＋
            </button>
          </div>

          <div className="sql-active-query-details">
            <label>
              <span>Title</span>

              <input
                value={activeTab.title}
                onChange={(event) =>
                  updateActiveTab({
                    title: event.target.value,
                    isDirty: true,
                  })
                }
              />
            </label>

            <label>
              <span>Category</span>

              <input
                value={activeTab.category}
                onChange={(event) =>
                  updateActiveTab({
                    category:
                      event.target.value,
                    isDirty: true,
                  })
                }
              />
            </label>

            <label>
              <span>Description</span>

              <input
                value={activeTab.description}
                onChange={(event) =>
                  updateActiveTab({
                    description:
                      event.target.value,
                    isDirty: true,
                  })
                }
              />
            </label>

            <button
              type="button"
              onClick={duplicateTab}
            >
              Duplicate
            </button>
          </div>

          <SqlEditor
            activeTab={activeTab}
            schemaCatalog={schemaCatalog}
            onChange={updateSql}
            onRun={executeQuery}
            onSave={saveQuery}
            onEditorReady={handleEditorReady}
          />

          <div className="sql-bottom-panel">
            <div className="sql-bottom-tabs">
              <button
                type="button"
                className={
                  activeBottomPanel ===
                  'results'
                    ? 'active'
                    : ''
                }
                onClick={() =>
                  setActiveBottomPanel(
                    'results',
                  )
                }
              >
                Results

                {result && (
                  <span>
                    {result.row_count}
                  </span>
                )}
              </button>

              <button
                type="button"
                className={
                  activeBottomPanel ===
                  'messages'
                    ? 'active'
                    : ''
                }
                onClick={() =>
                  setActiveBottomPanel(
                    'messages',
                  )
                }
              >
                Messages
              </button>

              <button
                type="button"
                className={
                  activeBottomPanel ===
                  'history'
                    ? 'active'
                    : ''
                }
                onClick={() =>
                  setActiveBottomPanel(
                    'history',
                  )
                }
              >
                History
              </button>

              <div className="sql-bottom-tab-spacer" />

              {result && (
                <>
                  <span>
                    {result.execution_ms.toLocaleString()}{' '}
                    ms
                  </span>

                  <button
                    type="button"
                    className="sql-export-button"
                    onClick={() =>
                      void exportResults()
                    }
                    disabled={isExporting}
                  >
                    {isExporting
                      ? 'Exporting…'
                      : 'Export CSV'}
                  </button>
                </>
              )}
            </div>

            <div className="sql-bottom-content">
              {activeBottomPanel ===
                'results' && (
                <>
                  {!result && (
                    <div className="sql-studio-empty-panel">
                      Run the active query to
                      display results.
                    </div>
                  )}

                  {result &&
                    result.columns.length ===
                      0 && (
                      <div className="sql-studio-empty-panel">
                        The query completed but
                        returned no columns.
                      </div>
                    )}

                  {result &&
                    result.columns.length >
                      0 && (
                      <div className="sql-studio-table-wrapper">
                        <table className="sql-studio-results-table">
                          <thead>
                            <tr>
                              <th>#</th>

                              {result.columns.map(
                                (column) => (
                                  <th
                                    key={
                                      column
                                    }
                                  >
                                    {column}
                                  </th>
                                ),
                              )}
                            </tr>
                          </thead>

                          <tbody>
                            {result.rows.map(
                              (
                                row,
                                rowIndex,
                              ) => (
                                <tr
                                  key={
                                    rowIndex
                                  }
                                >
                                  <td>
                                    {rowIndex +
                                      1}
                                  </td>

                                  {result.columns.map(
                                    (
                                      column,
                                    ) => (
                                      <td
                                        key={`${rowIndex}-${column}`}
                                        title={displayCellValue(
                                          row[
                                            column
                                          ],
                                        )}
                                      >
                                        {displayCellValue(
                                          row[
                                            column
                                          ],
                                        )}
                                      </td>
                                    ),
                                  )}
                                </tr>
                              ),
                            )}
                          </tbody>
                        </table>
                      </div>
                    )}
                </>
              )}

              {activeBottomPanel ===
                'messages' && (
                <pre className="sql-execution-messages">
                  {executionMessage}
                </pre>
              )}

              {activeBottomPanel ===
                'history' && (
                <div className="sql-bottom-history">
                  {history
                    .slice(0, 30)
                    .map((item) => (
                      <button
                        type="button"
                        key={item.id}
                        onClick={() =>
                          openHistoryQuery(
                            item,
                          )
                        }
                      >
                        <span
                          className={
                            item.success
                              ? 'history-state successful'
                              : 'history-state failed'
                          }
                        />

                        <strong>
                          {item.success
                            ? `${item.row_count} rows`
                            : 'Failed'}
                        </strong>

                        <span>
                          {
                            item.execution_ms
                          }{' '}
                          ms
                        </span>

                        <span>
                          {formatDateTime(
                            item.executed_at,
                          )}
                        </span>

                        <code>
                          {item.sql}
                        </code>
                      </button>
                    ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <footer className="sql-studio-statusbar">
        <div>
          <span
            className={
              connection?.connected
                ? 'sql-connection-light connected'
                : 'sql-connection-light'
            }
          />

          {connection?.connected
            ? `${connection.server} · ${connection.database}`
            : 'MySQL disconnected'}
        </div>

        <div>READ ONLY</div>

        <div>
          {activeTab.savedQueryId
            ? `Saved Query #${activeTab.savedQueryId}`
            : 'Local Query Tab'}
        </div>

        <div className="sql-statusbar-spacer" />

        <div>Ctrl+Enter / F5: Run</div>
        <div>Ctrl+S: Save</div>

        {result && (
          <div>
            {result.row_count.toLocaleString()}{' '}
            rows ·{' '}
            {result.execution_ms.toLocaleString()}{' '}
            ms
          </div>
        )}
      </footer>
    </section>
  )
}