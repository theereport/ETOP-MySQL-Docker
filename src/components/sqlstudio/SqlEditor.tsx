import Editor, {
  type BeforeMount,
  type Monaco,
  type OnMount,
} from '@monaco-editor/react'
import { useEffect, useRef } from 'react'

import { registerSchemaIntellisense } from './monaco/monacoIntellisense'
import type { QueryTab, SchemaCatalog } from './types'

type SqlEditorProps = {
  activeTab: QueryTab
  schemaCatalog: SchemaCatalog | null
  onChange: (value: string | undefined) => void
  onRun: () => Promise<void> | void
  onSave: () => Promise<void> | void
  onEditorReady?: (
    editor: Parameters<OnMount>[0],
    monaco: Parameters<OnMount>[1],
  ) => void
}

export default function SqlEditor({
  activeTab,
  schemaCatalog,
  onChange,
  onRun,
  onSave,
  onEditorReady,
}: SqlEditorProps) {
  const editorRef =
    useRef<Parameters<OnMount>[0] | null>(null)

  const monacoRef = useRef<Monaco | null>(null)
  const disposeIntellisenseRef =
    useRef<(() => void) | null>(null)

  const onRunRef = useRef(onRun)
  const onSaveRef = useRef(onSave)

  useEffect(() => {
    onRunRef.current = onRun
  }, [onRun])

  useEffect(() => {
    onSaveRef.current = onSave
  }, [onSave])

  useEffect(() => {
    disposeIntellisenseRef.current?.()
    disposeIntellisenseRef.current = null

    if (!monacoRef.current || !schemaCatalog) {
      return
    }

    disposeIntellisenseRef.current =
      registerSchemaIntellisense(
        monacoRef.current,
        schemaCatalog,
      )

    return () => {
      disposeIntellisenseRef.current?.()
      disposeIntellisenseRef.current = null
    }
  }, [schemaCatalog])

  useEffect(() => {
    return () => {
      disposeIntellisenseRef.current?.()
    }
  }, [])

  function handleEditorBeforeMount(
    monaco: Parameters<BeforeMount>[0],
  ) {
    monaco.editor.defineTheme('enterprise-sql-dark', {
      base: 'vs-dark',
      inherit: true,
      rules: [
        {
          token: 'keyword.sql',
          foreground: '8B80FF',
          fontStyle: 'bold',
        },
        {
          token: 'string.sql',
          foreground: '9ED6A5',
        },
        {
          token: 'number.sql',
          foreground: 'F1C77A',
        },
        {
          token: 'comment.sql',
          foreground: '65758B',
          fontStyle: 'italic',
        },
        {
          token: 'operator.sql',
          foreground: 'A8B8CB',
        },
      ],
      colors: {
        'editor.background': '#080E18',
        'editor.foreground': '#D9E4F2',
        'editorLineNumber.foreground': '#4D5B70',
        'editorLineNumber.activeForeground': '#A6B3C4',
        'editorCursor.foreground': '#8B80FF',
        'editor.selectionBackground': '#3D356F88',
        'editor.inactiveSelectionBackground': '#302B5066',
        'editor.lineHighlightBackground': '#101827',
        'editorIndentGuide.background1': '#1E2A3C',
        'editorIndentGuide.activeBackground1': '#394A63',
        'editorWidget.background': '#111A29',
        'editorWidget.border': '#263349',
        'editorSuggestWidget.background': '#111A29',
        'editorSuggestWidget.border': '#263349',
        'editorSuggestWidget.selectedBackground': '#27334A',
        'input.background': '#0D1522',
        'input.border': '#263349',
      },
    })
  }

  function handleEditorMount(
    editor: Parameters<OnMount>[0],
    monaco: Parameters<OnMount>[1],
  ) {
    editorRef.current = editor
    monacoRef.current = monaco

    editor.addAction({
      id: 'run-sql-query',
      label: 'Run SQL Query',
      keybindings: [
        monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter,
        monaco.KeyCode.F5,
      ],
      run: () => onRunRef.current(),
    })

    editor.addAction({
      id: 'save-sql-query',
      label: 'Save SQL Query',
      keybindings: [
        monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS,
      ],
      run: () => onSaveRef.current(),
    })

    if (schemaCatalog) {
      disposeIntellisenseRef.current?.()

      disposeIntellisenseRef.current =
        registerSchemaIntellisense(
          monaco,
          schemaCatalog,
        )
    }

    onEditorReady?.(editor, monaco)
    editor.focus()
  }

  return (
    <div className="sql-monaco-editor">
      <Editor
        height="100%"
        language="sql"
        theme="enterprise-sql-dark"
        value={activeTab.sql}
        beforeMount={handleEditorBeforeMount}
        onMount={handleEditorMount}
        onChange={onChange}
        path={`${activeTab.id}.sql`}
        options={{
          automaticLayout: true,
          minimap: {
            enabled: true,
            side: 'right',
            showSlider: 'mouseover',
          },
          fontFamily:
            'Consolas, "Cascadia Code", "Courier New", monospace',
          fontSize: 13,
          lineHeight: 21,
          lineNumbers: 'on',
          glyphMargin: true,
          folding: true,
          foldingHighlight: true,
          bracketPairColorization: {
            enabled: true,
          },
          guides: {
            bracketPairs: true,
            indentation: true,
          },
          renderLineHighlight: 'all',
          scrollBeyondLastLine: false,
          wordWrap: 'off',
          tabSize: 4,
          insertSpaces: true,
          formatOnPaste: false,
          formatOnType: false,
          suggestOnTriggerCharacters: true,
          quickSuggestions: {
            other: true,
            comments: false,
            strings: false,
          },
          cursorBlinking: 'smooth',
          smoothScrolling: true,
          padding: {
            top: 12,
            bottom: 12,
          },
        }}
      />
    </div>
  )
}
