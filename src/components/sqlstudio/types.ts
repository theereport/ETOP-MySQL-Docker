export type ConnectionStatus = {
  connected: boolean
  database: string
  user: string
  server: string
  version: string
  default_limit: number
  maximum_limit: number
}

export type SqlResult = {
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

export type SavedQuery = {
  id: number
  title: string
  category: string
  description: string
  sql: string
  created_at: string
  updated_at: string
}

export type QueryHistoryItem = {
  id: number
  sql: string
  success: boolean
  row_count: number
  execution_ms: number
  error_message: string | null
  executed_at: string
}

export type QueryTab = {
  id: string
  title: string
  sql: string
  savedQueryId: number | null
  category: string
  description: string
  isDirty: boolean
}

export type SchemaCatalogColumn = {
  name: string
  position: number
  column_type: string
  nullable: boolean
  key: string
  comment: string
}

export type SchemaCatalogObject = {
  name: string
  type: 'table' | 'view'
  comment: string
  columns: SchemaCatalogColumn[]
}

export type SchemaCatalog = {
  database: string
  objects: SchemaCatalogObject[]
  object_count: number
  column_count: number
}

export type GeneratedSqlSchemaObject = {
  name: string
  type: 'table' | 'view'
  column_count: number
}

export type GeneratedSqlResponse = {
  success: boolean
  sql: string
  explanation: string
  database: string
  model: string
  schema_objects_used: GeneratedSqlSchemaObject[]
}

export type BottomPanel = 'results' | 'messages' | 'history'

export type SidePanel =
  | 'database'
  | 'saved'
  | 'history'
  | 'ai'

export type StoredSqlWorkspace = {
  tabs: QueryTab[]
  activeTabId: string
}
