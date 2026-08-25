import { useState } from 'react'

import { generateSql } from './api/sqlApi'
import type {
  GeneratedSqlResponse,
  SchemaCatalog,
} from './types'

type SqlAiPanelProps = {
  currentSql: string
  schemaCatalog: SchemaCatalog | null
  selectedTables?: string[]
  onGenerated: (response: GeneratedSqlResponse) => void
  onError?: (message: string) => void
}

export default function SqlAiPanel({
  currentSql,
  schemaCatalog,
  selectedTables = [],
  onGenerated,
  onError,
}: SqlAiPanelProps) {
  const [prompt, setPrompt] = useState('')
  const [isGenerating, setIsGenerating] = useState(false)
  const [lastResponse, setLastResponse] =
    useState<GeneratedSqlResponse | null>(null)

  async function handleGenerate() {
    const trimmedPrompt = prompt.trim()

    if (trimmedPrompt.length < 3 || isGenerating) {
      return
    }

    setIsGenerating(true)
    onError?.('')

    try {
      const response = await generateSql({
        prompt: trimmedPrompt,
        currentSql,
        selectedTables,
      })

      setLastResponse(response)
      onGenerated(response)
    } catch (requestError) {
      const message =
        requestError instanceof Error
          ? requestError.message
          : 'Unable to generate SQL.'

      onError?.(message)
    } finally {
      setIsGenerating(false)
    }
  }

  function handleKeyDown(
    event: React.KeyboardEvent<HTMLTextAreaElement>,
  ) {
    if (
      (event.ctrlKey || event.metaKey) &&
      event.key === 'Enter'
    ) {
      event.preventDefault()
      void handleGenerate()
    }
  }

  return (
    <div className="sql-ai-panel">
      <div className="sql-ai-panel-header">
        <div>
          <strong>Schema-Aware SQL AI</strong>

          <p>
            Describe the report or query you need. Gemma will
            use only the schema objects returned by your local
            MySQL catalog.
          </p>
        </div>

        <span className="sql-ai-local-badge">LOCAL</span>
      </div>

      <label className="sql-ai-prompt">
        <span>Request</span>

        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Example: Show customers above 75% of their credit limit, including past-due balances and annualized sales."
          rows={7}
          maxLength={20_000}
        />
      </label>

      <div className="sql-ai-actions">
        <button
          type="button"
          className="sql-ai-generate-button"
          onClick={() => void handleGenerate()}
          disabled={
            isGenerating ||
            prompt.trim().length < 3 ||
            !schemaCatalog
          }
        >
          {isGenerating
            ? 'Generating SQL…'
            : 'Generate SQL'}
        </button>

        <span>
          Ctrl+Enter to generate
        </span>
      </div>

      {!schemaCatalog && (
        <p className="sql-ai-status">
          Loading the database schema catalog…
        </p>
      )}

      {schemaCatalog && (
        <div className="sql-ai-catalog-summary">
          <strong>{schemaCatalog.database}</strong>

          <span>
            {schemaCatalog.object_count.toLocaleString()} objects
          </span>

          <span>
            {schemaCatalog.column_count.toLocaleString()} columns
          </span>
        </div>
      )}

      {lastResponse && (
        <div className="sql-ai-generation-details">
          <div className="sql-ai-generation-heading">
            <strong>Last generation</strong>

            <span>
              {lastResponse.model} · {lastResponse.database}
            </span>
          </div>

          {lastResponse.explanation && (
            <div className="sql-ai-explanation">
              {lastResponse.explanation}
            </div>
          )}

          <div className="sql-ai-schema-objects">
            {lastResponse.schema_objects_used.map((item) => (
              <span
                className="sql-ai-schema-chip"
                key={`${item.type}-${item.name}`}
                title={`${item.column_count} columns`}
              >
                {item.type === 'view' ? 'VIEW' : 'TABLE'}{' '}
                {item.name}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
