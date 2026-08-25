import { useMemo, useState } from 'react'
import type { LearningExample, LearningSummary } from '../types'
import { formatDocumentType } from '../utils'

type Props = {
  summary: LearningSummary
  examples: LearningExample[]
  isLoading: boolean
  errorMessage: string
  onRefresh: () => void
}

const show = (value: unknown) =>
  value == null
    ? '—'
    : typeof value === 'object'
      ? JSON.stringify(value)
      : String(value)

export default function LearningEngine({ summary, examples, isLoading, errorMessage, onRefresh }: Props) {
  const [search, setSearch] = useState('')
  const [fieldFilter, setFieldFilter] = useState('all')
  const [typeFilter, setTypeFilter] = useState('all')

  const fields = useMemo(() => Object.keys(summary.field_counts).sort(), [summary.field_counts])
  const types = useMemo(() => Object.keys(summary.document_type_counts).sort(), [summary.document_type_counts])
  const filtered = useMemo(() => examples.filter((item) => {
    const q = search.trim().toLowerCase()
    const text = [item.job_id, item.field_name, item.document_type, item.reviewer, show(item.original_value), show(item.corrected_value)].join(' ').toLowerCase()
    return (fieldFilter === 'all' || item.field_name === fieldFilter)
      && (typeFilter === 'all' || item.document_type === typeFilter)
      && (!q || text.includes(q))
  }), [examples, search, fieldFilter, typeFilter])

  const topFields = Object.entries(summary.field_counts).sort((a, b) => b[1] - a[1]).slice(0, 8)
  const max = topFields[0]?.[1] || 1

  return <>
    <section className="ed-metrics">
      <article><span>Learning Examples</span><strong>{summary.total_examples}</strong><small>Original-to-corrected pairs</small></article>
      <article><span>Trained Documents</span><strong>{summary.unique_documents}</strong><small>Documents contributing data</small></article>
      <article><span>Corrected Fields</span><strong>{summary.unique_fields}</strong><small>Distinct field names</small></article>
      <article><span>Document Types</span><strong>{Object.keys(summary.document_type_counts).length}</strong><small>Classification groups</small></article>
    </section>

    <section className="ed-learning-grid">
      <article className="ed-card">
        <div className="ed-card-heading"><div><strong>Correction Frequency</strong><span>Fields most often changed</span></div><button type="button" onClick={onRefresh} disabled={isLoading}>{isLoading ? 'Refreshing…' : 'Refresh'}</button></div>
        <div className="ed-learning-bars">
          {topFields.map(([field, count]) => <div key={field}><div><span>{formatDocumentType(field)}</span><strong>{count}</strong></div><i><b style={{ width: `${Math.max(6, Math.round((count / max) * 100))}%` }} /></i></div>)}
          {topFields.length === 0 && <div className="ed-empty">No learning examples have been created yet.</div>}
        </div>
      </article>

      <article className="ed-card">
        <div className="ed-card-heading"><div><strong>Learning Workflow</strong><span>Controlled improvement process</span></div></div>
        <div className="ed-learning-flow">
          {[
            ['Original Output', 'Parser output remains unchanged.'],
            ['Human Correction', 'A reviewer corrects the extracted value.'],
            ['Learning Example', 'ETOP stores the original and corrected pair.'],
            ['Pattern Analysis', 'Repeated corrections guide parser improvements.'],
          ].map(([title, copy], index) => <div key={title}><span>{index + 1}</span><div><strong>{title}</strong><p>{copy}</p></div></div>)}
        </div>
      </article>
    </section>

    <section className="ed-card">
      <div className="ed-card-heading"><div><strong>Training Examples</strong><span>Original versus corrected values</span></div></div>
      <div className="ed-learning-toolbar">
        <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search examples" />
        <select value={fieldFilter} onChange={(event) => setFieldFilter(event.target.value)}><option value="all">All fields</option>{fields.map((field) => <option key={field} value={field}>{formatDocumentType(field)}</option>)}</select>
        <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}><option value="all">All document types</option>{types.map((type) => <option key={type} value={type}>{formatDocumentType(type)}</option>)}</select>
      </div>
      {errorMessage && <div className="ed-banner error">{errorMessage}</div>}
      <div className="ed-table-wrap">
        <table className="ed-table"><thead><tr><th>Field</th><th>Original Value</th><th>Corrected Value</th><th>Document Type</th><th>Reviewer</th><th>Created</th></tr></thead><tbody>
          {filtered.map((item) => <tr key={item.id}><td><strong>{formatDocumentType(item.field_name)}</strong><small>{item.job_id}</small></td><td><code className="ed-learning-value original">{show(item.original_value)}</code></td><td><code className="ed-learning-value corrected">{show(item.corrected_value)}</code></td><td>{formatDocumentType(item.document_type)}</td><td>{item.reviewer || '—'}</td><td>{new Date(item.created_at).toLocaleString()}</td></tr>)}
        </tbody></table>
        {filtered.length === 0 && <div className="ed-empty">No learning examples match the current filters.</div>}
      </div>
    </section>
  </>
}
