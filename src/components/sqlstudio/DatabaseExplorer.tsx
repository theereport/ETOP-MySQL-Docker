import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react'

type SchemaSummary = {
  database: string
  tables: number
  views: number
  columns: number
}

type SchemaObject = {
  name: string
  type: 'table' | 'view'
  engine: string | null
  estimated_rows: number | null
  comment: string
  column_count: number
}

type SchemaColumn = {
  name: string
  ordinal_position: number
  default: unknown
  nullable: boolean
  data_type: string
  column_type: string
  character_length: number | null
  numeric_precision: number | null
  numeric_scale: number | null
  key: string
  extra: string
  comment: string
}

type SchemaIndexColumn = {
  name: string | null
  sequence: number
  descending: boolean
  nullable: boolean
}

type SchemaIndex = {
  name: string
  unique: boolean
  primary: boolean
  type: string
  cardinality: number | null
  comment: string
  columns: SchemaIndexColumn[]
}

type ObjectDetails = {
  columns: SchemaColumn[]
  indexes: SchemaIndex[]
}

type DatabaseExplorerProps = {
  onOpenTableQuery: (
    tableName: string,
    columns: string[],
  ) => void
  onInsertText: (text: string) => void
}

const API_BASE = 'http://127.0.0.1:8000'

function quoteIdentifier(identifier: string): string {
  return `\`${identifier.replaceAll('`', '``')}\``
}

function formatEstimatedRows(value: number | null): string {
  if (value === null) {
    return 'Unknown rows'
  }

  return `${value.toLocaleString()} estimated rows`
}

export default function DatabaseExplorer({
  onOpenTableQuery,
  onInsertText,
}: DatabaseExplorerProps) {
  const [summary, setSummary] =
    useState<SchemaSummary | null>(null)

  const [objects, setObjects] = useState<SchemaObject[]>([])
  const [details, setDetails] = useState<
    Record<string, ObjectDetails>
  >({})

  const [expandedObjects, setExpandedObjects] = useState<
    Set<string>
  >(new Set())

  const [activeDetailTabs, setActiveDetailTabs] = useState<
    Record<string, 'columns' | 'indexes'>
  >({})

  const [search, setSearch] = useState('')
  const [objectType, setObjectType] =
    useState<'all' | 'tables' | 'views'>('all')

  const [isLoading, setIsLoading] = useState(false)
  const [loadingObject, setLoadingObject] =
    useState<string | null>(null)

  const [error, setError] = useState('')

  const filteredObjects = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase()

    return objects.filter((object) => {
      if (
        objectType === 'tables' &&
        object.type !== 'table'
      ) {
        return false
      }

      if (
        objectType === 'views' &&
        object.type !== 'view'
      ) {
        return false
      }

      if (!normalizedSearch) {
        return true
      }

      if (
        object.name.toLowerCase().includes(normalizedSearch)
      ) {
        return true
      }

      const objectDetails = details[object.name]

      return objectDetails?.columns.some((column) =>
        column.name.toLowerCase().includes(normalizedSearch),
      )
    })
  }, [details, objectType, objects, search])

  const loadSchema = useCallback(async () => {
    setIsLoading(true)
    setError('')

    try {
      const [summaryResponse, objectsResponse] =
        await Promise.all([
          fetch(`${API_BASE}/sql/schema/summary`),
          fetch(
            `${API_BASE}/sql/schema/objects?object_type=all&limit=5000`,
          ),
        ])

      const summaryBody = await summaryResponse
        .json()
        .catch(() => null)

      const objectsBody = await objectsResponse
        .json()
        .catch(() => null)

      if (!summaryResponse.ok) {
        throw new Error(
          summaryBody?.detail ??
            'Unable to load schema summary.',
        )
      }

      if (!objectsResponse.ok) {
        throw new Error(
          objectsBody?.detail ??
            'Unable to load database objects.',
        )
      }

      setSummary(summaryBody as SchemaSummary)
      setObjects(objectsBody.objects as SchemaObject[])
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'Unable to load database schema.',
      )
    } finally {
      setIsLoading(false)
    }
  }, [])

  const loadObjectDetails = useCallback(
    async (objectName: string) => {
      if (details[objectName]) {
        return details[objectName]
      }

      setLoadingObject(objectName)
      setError('')

      try {
        const encodedName = encodeURIComponent(objectName)

        const [columnsResponse, indexesResponse] =
          await Promise.all([
            fetch(
              `${API_BASE}/sql/schema/objects/${encodedName}/columns`,
            ),
            fetch(
              `${API_BASE}/sql/schema/objects/${encodedName}/indexes`,
            ),
          ])

        const columnsBody = await columnsResponse
          .json()
          .catch(() => null)

        const indexesBody = await indexesResponse
          .json()
          .catch(() => null)

        if (!columnsResponse.ok) {
          throw new Error(
            columnsBody?.detail ??
              `Unable to load columns for ${objectName}.`,
          )
        }

        if (!indexesResponse.ok) {
          throw new Error(
            indexesBody?.detail ??
              `Unable to load indexes for ${objectName}.`,
          )
        }

        const loadedDetails: ObjectDetails = {
          columns: columnsBody.columns as SchemaColumn[],
          indexes: indexesBody.indexes as SchemaIndex[],
        }

        setDetails((currentDetails) => ({
          ...currentDetails,
          [objectName]: loadedDetails,
        }))

        return loadedDetails
      } catch (requestError) {
        setError(
          requestError instanceof Error
            ? requestError.message
            : `Unable to load ${objectName}.`,
        )

        return null
      } finally {
        setLoadingObject(null)
      }
    },
    [details],
  )

  useEffect(() => {
    void loadSchema()
  }, [loadSchema])

  async function toggleObject(objectName: string) {
    if (expandedObjects.has(objectName)) {
      setExpandedObjects((currentObjects) => {
        const updatedObjects = new Set(currentObjects)
        updatedObjects.delete(objectName)
        return updatedObjects
      })

      return
    }

    await loadObjectDetails(objectName)

    setExpandedObjects((currentObjects) => {
      const updatedObjects = new Set(currentObjects)
      updatedObjects.add(objectName)
      return updatedObjects
    })
  }

  async function openObjectQuery(objectName: string) {
    const objectDetails = await loadObjectDetails(objectName)

    if (!objectDetails) {
      return
    }

    onOpenTableQuery(
      objectName,
      objectDetails.columns.map((column) => column.name),
    )
  }

  async function copyObjectName(objectName: string) {
    try {
      await navigator.clipboard.writeText(objectName)
    } catch {
      setError('Unable to copy the object name.')
    }
  }

  return (
    <div className="database-explorer">
      <div className="database-explorer-header">
        <div>
          <strong>{summary?.database ?? 'Database'}</strong>

          <span>
            {summary
              ? `${summary.tables} tables · ${summary.views} views · ${summary.columns} columns`
              : 'Loading schema metadata…'}
          </span>
        </div>

        <button
          type="button"
          onClick={() => void loadSchema()}
          disabled={isLoading}
          title="Refresh database schema"
        >
          {isLoading ? '…' : '↻'}
        </button>
      </div>

      <input
        className="database-explorer-search"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
        placeholder="Search tables or loaded columns..."
      />

      <div className="database-object-filters">
        <button
          type="button"
          className={objectType === 'all' ? 'active' : ''}
          onClick={() => setObjectType('all')}
        >
          All
        </button>

        <button
          type="button"
          className={
            objectType === 'tables' ? 'active' : ''
          }
          onClick={() => setObjectType('tables')}
        >
          Tables
        </button>

        <button
          type="button"
          className={
            objectType === 'views' ? 'active' : ''
          }
          onClick={() => setObjectType('views')}
        >
          Views
        </button>
      </div>

      {error && (
        <div className="database-explorer-error">
          {error}
        </div>
      )}

      <div className="database-object-list">
        {filteredObjects.map((object) => {
          const isExpanded = expandedObjects.has(object.name)
          const objectDetails = details[object.name]
          const activeDetailTab =
            activeDetailTabs[object.name] ?? 'columns'

          return (
            <div
              className="database-object"
              key={object.name}
            >
              <div className="database-object-row">
                <button
                  type="button"
                  className="database-object-toggle"
                  onClick={() =>
                    void toggleObject(object.name)
                  }
                  onDoubleClick={() =>
                    void openObjectQuery(object.name)
                  }
                  title="Click to expand. Double-click to create a SELECT query."
                >
                  <span className="database-chevron">
                    {isExpanded ? '▾' : '▸'}
                  </span>

                  <span
                    className={
                      object.type === 'table'
                        ? 'database-object-icon table'
                        : 'database-object-icon view'
                    }
                  >
                    {object.type === 'table' ? 'T' : 'V'}
                  </span>

                  <span className="database-object-name">
                    <strong>{object.name}</strong>

                    <small>
                      {object.column_count} columns
                    </small>
                  </span>
                </button>

                <button
                  type="button"
                  className="database-object-menu"
                  onClick={() =>
                    void copyObjectName(object.name)
                  }
                  title="Copy table or view name"
                >
                  ⧉
                </button>
              </div>

              {isExpanded && (
                <div className="database-object-details">
                  <div className="database-object-summary">
                    <span>
                      {object.type === 'table'
                        ? object.engine || 'Table'
                        : 'View'}
                    </span>

                    <span>
                      {formatEstimatedRows(
                        object.estimated_rows,
                      )}
                    </span>
                  </div>

                  <div className="database-detail-tabs">
                    <button
                      type="button"
                      className={
                        activeDetailTab === 'columns'
                          ? 'active'
                          : ''
                      }
                      onClick={() =>
                        setActiveDetailTabs(
                          (currentTabs) => ({
                            ...currentTabs,
                            [object.name]: 'columns',
                          }),
                        )
                      }
                    >
                      Columns
                    </button>

                    <button
                      type="button"
                      className={
                        activeDetailTab === 'indexes'
                          ? 'active'
                          : ''
                      }
                      onClick={() =>
                        setActiveDetailTabs(
                          (currentTabs) => ({
                            ...currentTabs,
                            [object.name]: 'indexes',
                          }),
                        )
                      }
                    >
                      Indexes
                    </button>

                    <button
                      type="button"
                      onClick={() =>
                        void openObjectQuery(object.name)
                      }
                    >
                      SELECT
                    </button>
                  </div>

                  {loadingObject === object.name && (
                    <div className="database-detail-loading">
                      Loading metadata…
                    </div>
                  )}

                  {objectDetails &&
                    activeDetailTab === 'columns' && (
                      <div className="database-column-list">
                        {objectDetails.columns.map(
                          (column) => (
                            <button
                              type="button"
                              className="database-column-row"
                              key={column.name}
                              onDoubleClick={() =>
                                onInsertText(
                                  quoteIdentifier(
                                    column.name,
                                  ),
                                )
                              }
                              onClick={() =>
                                onInsertText(
                                  quoteIdentifier(
                                    column.name,
                                  ),
                                )
                              }
                              title={
                                column.comment ||
                                `${column.column_type}${
                                  column.nullable
                                    ? ' · Nullable'
                                    : ' · Not Null'
                                }`
                              }
                            >
                              <span
                                className={
                                  column.key === 'PRI'
                                    ? 'database-column-key primary'
                                    : column.key
                                      ? 'database-column-key indexed'
                                      : 'database-column-key'
                                }
                              >
                                {column.key === 'PRI'
                                  ? 'PK'
                                  : column.key || '·'}
                              </span>

                              <span className="database-column-name">
                                <strong>{column.name}</strong>
                                <small>
                                  {column.column_type}
                                </small>
                              </span>

                              <span className="database-nullable">
                                {column.nullable ? 'NULL' : ''}
                              </span>
                            </button>
                          ),
                        )}
                      </div>
                    )}

                  {objectDetails &&
                    activeDetailTab === 'indexes' && (
                      <div className="database-index-list">
                        {objectDetails.indexes.map(
                          (index) => (
                            <div
                              className="database-index-row"
                              key={index.name}
                            >
                              <span
                                className={
                                  index.primary
                                    ? 'database-index-icon primary'
                                    : index.unique
                                      ? 'database-index-icon unique'
                                      : 'database-index-icon'
                                }
                              >
                                {index.primary
                                  ? 'PK'
                                  : index.unique
                                    ? 'UQ'
                                    : 'IX'}
                              </span>

                              <span>
                                <strong>{index.name}</strong>

                                <small>
                                  {index.columns
                                    .map(
                                      (column) =>
                                        column.name,
                                    )
                                    .join(', ')}
                                </small>
                              </span>
                            </div>
                          ),
                        )}

                        {objectDetails.indexes.length ===
                          0 && (
                          <p className="database-detail-empty">
                            No indexes were returned.
                          </p>
                        )}
                      </div>
                    )}
                </div>
              )}
            </div>
          )
        })}

        {!isLoading && filteredObjects.length === 0 && (
          <p className="database-detail-empty">
            No matching tables or views found.
          </p>
        )}
      </div>
    </div>
  )
}