import type {
  DocumentJob,
  DocumentResult,
} from '../types'

import {
  confidencePercent,
  formatBytes,
  formatDocumentType,
  objectEntries,
} from '../utils'

type Props = {
  job: DocumentJob
  result: DocumentResult | null
}

export default function DocumentResultView({
  job,
  result,
}: Props) {
  const parsedEntries =
    objectEntries(
      result?.parsed,
    )

  return (
    <section className="ed-result-layout">
      <article className="ed-card ed-document-summary">
        <div className="ed-card-heading">
          <div>
            <strong>
              {job.original_file_name}
            </strong>
            <span>{job.message}</span>
          </div>

          <span
            className={`ed-status ${job.status}`}
          >
            {job.status}
          </span>
        </div>

        <dl>
          <div>
            <dt>Document Type</dt>
            <dd>
              {formatDocumentType(
                job.document_type,
              )}
            </dd>
          </div>
          <div>
            <dt>Confidence</dt>
            <dd>
              {confidencePercent(
                job.confidence,
              )}
            </dd>
          </div>
          <div>
            <dt>Classifier</dt>
            <dd>
              {result?.classifier ??
                '—'}
            </dd>
          </div>
          <div>
            <dt>File Size</dt>
            <dd>
              {formatBytes(
                job.file_size_bytes,
              )}
            </dd>
          </div>
          <div>
            <dt>Managed File</dt>
            <dd title={job.stored_file_name}>
              {job.stored_file_name}
              {' (local document storage)'}
            </dd>
          </div>
        </dl>

        <div className="ed-evidence">
          <strong>
            Classification Evidence
          </strong>

          {result
            ?.classification_evidence
            .map(
              (evidence) => (
                <span key={evidence}>
                  {evidence}
                </span>
              ),
            )}

          {!result
            ?.classification_evidence
            .length && (
            <small>
              No evidence was returned.
            </small>
          )}
        </div>
      </article>

      <article className="ed-card ed-result-card">
        <div className="ed-card-heading">
          <div>
            <strong>
              Parsed Fields
            </strong>
            <span>
              Structured parser output
            </span>
          </div>
        </div>

        <div className="ed-field-grid">
          {parsedEntries.map(
            ([
              field,
              value,
            ]) => (
              <div key={field}>
                <span>
                  {formatDocumentType(
                    field,
                  )}
                </span>
                <strong>
                  {typeof value ===
                  'object'
                    ? JSON.stringify(
                        value,
                      )
                    : String(
                        value ?? '',
                      )}
                </strong>
              </div>
            ),
          )}

          {parsedEntries.length ===
            0 && (
            <div className="ed-empty">
              The parser returned no
              top-level fields.
            </div>
          )}
        </div>
      </article>

      <article className="ed-card ed-json-card">
        <div className="ed-card-heading">
          <div>
            <strong>
              Full Structured Result
            </strong>
            <span>
              Extraction and parsed JSON
            </span>
          </div>
        </div>

        <details open>
          <summary>
            Parsed Output
          </summary>
          <pre>
            {JSON.stringify(
              result?.parsed ?? {},
              null,
              2,
            )}
          </pre>
        </details>

        <details>
          <summary>
            Extraction Output
          </summary>
          <pre>
            {JSON.stringify(
              result?.extraction ?? {},
              null,
              2,
            )}
          </pre>
        </details>
      </article>
    </section>
  )
}
