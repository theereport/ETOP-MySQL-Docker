import type { Monaco } from '@monaco-editor/react'
import type { SchemaCatalog } from '../types'

const SQL_KEYWORDS = [
  'SELECT',
  'FROM',
  'WHERE',
  'JOIN',
  'LEFT JOIN',
  'RIGHT JOIN',
  'INNER JOIN',
  'GROUP BY',
  'ORDER BY',
  'HAVING',
  'LIMIT',
  'WITH',
  'AS',
  'CASE',
  'WHEN',
  'THEN',
  'ELSE',
  'END',
  'DISTINCT',
  'COUNT',
  'SUM',
  'AVG',
  'MIN',
  'MAX',
  'COALESCE',
  'IFNULL',
  'CONCAT',
  'DATE',
  'DATE_FORMAT',
  'CURRENT_DATE',
  'CURRENT_TIMESTAMP',
  'BETWEEN',
  'IN',
  'NOT IN',
  'LIKE',
  'IS NULL',
  'IS NOT NULL',
  'AND',
  'OR',
  'NOT',
  'ASC',
  'DESC',
  'UNION',
  'UNION ALL',
  'EXPLAIN',
  'SHOW',
  'DESCRIBE',
]

function quoteIdentifier(value: string): string {
  return `\`${value.replaceAll('`', '``')}\``
}

function formatColumnDocumentation(
  objectName: string,
  column: SchemaCatalog['objects'][number]['columns'][number],
): string {
  const lines = [
    `**${objectName}.${column.name}**`,
    '',
    `Type: \`${column.column_type}\``,
    `Nullable: ${column.nullable ? 'Yes' : 'No'}`,
  ]

  if (column.key) {
    lines.push(`Key: \`${column.key}\``)
  }

  if (column.comment) {
    lines.push('', column.comment)
  }

  return lines.join('\n')
}

export function registerSchemaIntellisense(
  monaco: Monaco,
  catalog: SchemaCatalog,
): () => void {
  const completionProvider =
  monaco.languages.registerCompletionItemProvider('sql', {
    triggerCharacters: ['.', '`'],

    provideCompletionItems(
      model: import('monaco-editor').editor.ITextModel,
      position: import('monaco-editor').Position,
    ) {
      const word = model.getWordUntilPosition(position)

      const range = {
        startLineNumber: position.lineNumber,
        endLineNumber: position.lineNumber,
        startColumn: word.startColumn,
        endColumn: word.endColumn,
      }

        const suggestions: import('monaco-editor').languages.CompletionItem[] =
          []

        for (const keyword of SQL_KEYWORDS) {
          suggestions.push({
            label: keyword,
            kind: monaco.languages.CompletionItemKind.Keyword,
            insertText: keyword,
            range,
            sortText: `3-${keyword}`,
          })
        }

        for (const schemaObject of catalog.objects) {
          suggestions.push({
            label: schemaObject.name,
            detail: `${schemaObject.type} · ${catalog.database}`,
            documentation:
              schemaObject.comment ||
              `${schemaObject.columns.length} columns`,
            kind:
              schemaObject.type === 'view'
                ? monaco.languages.CompletionItemKind.Interface
                : monaco.languages.CompletionItemKind.Class,
            insertText: quoteIdentifier(schemaObject.name),
            range,
            sortText: `1-${schemaObject.name}`,
          })

          for (const column of schemaObject.columns) {
            suggestions.push({
              label: column.name,
              detail: `${schemaObject.name} · ${column.column_type}`,
              documentation: {
                value: formatColumnDocumentation(
                  schemaObject.name,
                  column,
                ),
              },
              kind: monaco.languages.CompletionItemKind.Field,
              insertText: quoteIdentifier(column.name),
              range,
              sortText: `2-${column.name}`,
            })
          }
        }

        return { suggestions }
      },
    })

  const hoverProvider =
    monaco.languages.registerHoverProvider('sql', {
      provideHover(
  model: import('monaco-editor').editor.ITextModel,
  position: import('monaco-editor').Position,
) {
        const word = model.getWordAtPosition(position)

        if (!word) {
          return null
        }

        const lookup = word.word.toLowerCase()

        const schemaObject = catalog.objects.find(
          (item) => item.name.toLowerCase() === lookup,
        )

        if (schemaObject) {
          return {
            range: new monaco.Range(
              position.lineNumber,
              word.startColumn,
              position.lineNumber,
              word.endColumn,
            ),
            contents: [
              {
                value: `**${schemaObject.type.toUpperCase()} ${schemaObject.name}**`,
              },
              {
                value:
                  schemaObject.comment ||
                  `${schemaObject.columns.length} columns in ${catalog.database}`,
              },
            ],
          }
        }

        for (const object of catalog.objects) {
          const column = object.columns.find(
            (item) => item.name.toLowerCase() === lookup,
          )

          if (!column) {
            continue
          }

          return {
            range: new monaco.Range(
              position.lineNumber,
              word.startColumn,
              position.lineNumber,
              word.endColumn,
            ),
            contents: [
              {
                value: formatColumnDocumentation(
                  object.name,
                  column,
                ),
              },
            ],
          }
        }

        return null
      },
    })

  return () => {
    completionProvider.dispose()
    hoverProvider.dispose()
  }
}
