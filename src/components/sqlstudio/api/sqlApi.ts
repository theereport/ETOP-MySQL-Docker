import type {
  ConnectionStatus,
  GeneratedSqlResponse,
  QueryHistoryItem,
  SavedQuery,
  SchemaCatalog,
  SqlResult,
} from '../types'

export const API_BASE = 'http://127.0.0.1:8000'

type ErrorPayload = {
  detail?: string
}

async function parseError(
  response: Response,
  fallback: string,
): Promise<Error> {
  const payload = (await response
    .json()
    .catch(() => null)) as ErrorPayload | null

  return new Error(payload?.detail ?? fallback)
}

export async function getSqlConnection(): Promise<ConnectionStatus> {
  const response = await fetch(`${API_BASE}/sql/connection`)

  if (!response.ok) {
    throw await parseError(
      response,
      'Unable to connect to MySQL.',
    )
  }

  return (await response.json()) as ConnectionStatus
}

export async function executeSql(
  sql: string,
  rowLimit: number,
): Promise<SqlResult> {
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

  if (!response.ok) {
    throw await parseError(
      response,
      'The SQL query failed.',
    )
  }

  return (await response.json()) as SqlResult
}

export async function exportSqlResults(
  sql: string,
  rowLimit: number,
): Promise<Blob> {
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
    throw await parseError(
      response,
      'Unable to export the results.',
    )
  }

  return response.blob()
}

export async function getSavedQueries(): Promise<SavedQuery[]> {
  const response = await fetch(`${API_BASE}/sql/saved`)

  if (!response.ok) {
    throw await parseError(
      response,
      'Unable to load saved queries.',
    )
  }

  const payload = (await response.json()) as {
    queries: SavedQuery[]
  }

  return payload.queries
}

export async function createSavedQuery(input: {
  title: string
  category: string
  description: string
  sql: string
}): Promise<number> {
  const response = await fetch(`${API_BASE}/sql/saved`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(input),
  })

  if (!response.ok) {
    throw await parseError(
      response,
      'Unable to save the query.',
    )
  }

  const payload = (await response.json()) as {
    id: number | string
  }

  return Number(payload.id)
}

export async function updateSavedQuery(
  id: number,
  input: {
    title: string
    category: string
    description: string
    sql: string
  },
): Promise<void> {
  const response = await fetch(
    `${API_BASE}/sql/saved/${id}`,
    {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(input),
    },
  )

  if (!response.ok) {
    throw await parseError(
      response,
      'Unable to update the query.',
    )
  }
}

export async function deleteSavedQueryById(
  id: number,
): Promise<void> {
  const response = await fetch(
    `${API_BASE}/sql/saved/${id}`,
    {
      method: 'DELETE',
    },
  )

  if (!response.ok) {
    throw await parseError(
      response,
      'Unable to delete the query.',
    )
  }
}

export async function getQueryHistory(
  limit = 100,
): Promise<QueryHistoryItem[]> {
  const response = await fetch(
    `${API_BASE}/sql/history?limit=${limit}`,
  )

  if (!response.ok) {
    throw await parseError(
      response,
      'Unable to load query history.',
    )
  }

  const payload = (await response.json()) as {
    history: QueryHistoryItem[]
  }

  return payload.history
}

export async function clearQueryHistory(): Promise<void> {
  const response = await fetch(`${API_BASE}/sql/history`, {
    method: 'DELETE',
  })

  if (!response.ok) {
    throw await parseError(
      response,
      'Unable to clear query history.',
    )
  }
}

export async function getSchemaCatalog(): Promise<SchemaCatalog> {
  const response = await fetch(`${API_BASE}/sql/ai/catalog`)

  if (!response.ok) {
    throw await parseError(
      response,
      'Unable to load the schema catalog.',
    )
  }

  return (await response.json()) as SchemaCatalog
}

export async function generateSql(input: {
  prompt: string
  currentSql?: string
  selectedTables?: string[]
}): Promise<GeneratedSqlResponse> {
  const response = await fetch(`${API_BASE}/sql/ai/generate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      prompt: input.prompt,
      current_sql: input.currentSql ?? '',
      selected_tables: input.selectedTables ?? [],
    }),
  })

  if (!response.ok) {
    throw await parseError(
      response,
      'Unable to generate SQL.',
    )
  }

  return (await response.json()) as GeneratedSqlResponse
}

export async function explainSqlWithLocalAi(
  sql: string,
): Promise<string> {
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
2. How each join works
3. How filters and date logic work
4. What calculated fields do
5. Possible logic or data-quality issues
6. Performance concerns
7. Suggested improvements, without changing the original SQL unless you clearly label a revised version

SQL:

${sql}`,
        },
      ],
    }),
  })

  if (!response.ok) {
    throw await parseError(
      response,
      'Unable to explain the SQL.',
    )
  }

  const payload = (await response.json()) as {
    response: string
  }

  return payload.response
}
