import type {
  DocumentJob,
} from '../types'

import {
  confidencePercent,
  formatBytes,
  formatDocumentType,
} from '../utils'

type Props = {
  title: string
  subtitle: string
  jobs: DocumentJob[]
  onOpen: (
    job: DocumentJob,
  ) => void
  onProcess: (
    job: DocumentJob,
  ) => void
}

export default function DocumentQueue({
  title,
  subtitle,
  jobs,
  onOpen,
  onProcess,
}: Props) {
  return (
    <section className="ed-card">
      <div className="ed-card-heading">
        <div>
          <strong>{title}</strong>
          <span>{subtitle}</span>
        </div>
      </div>

      <div className="ed-table-wrap">
        <table className="ed-table">
          <thead>
            <tr>
              <th>Document</th>
              <th>Type</th>
              <th>Confidence</th>
              <th>Status</th>
              <th>Created</th>
              <th>Size</th>
              <th />
            </tr>
          </thead>

          <tbody>
            {jobs.map(
              (job) => (
                <tr key={job.job_id}>
                  <td>
                    <strong>
                      {
                        job.original_file_name
                      }
                    </strong>
                    <small>
                      {job.message}
                    </small>
                  </td>
                  <td>
                    {formatDocumentType(
                      job.document_type,
                    )}
                  </td>
                  <td>
                    <span className="ed-confidence">
                      <i
                        style={{
                          width:
                            confidencePercent(
                              job.confidence,
                            ),
                        }}
                      />
                    </span>
                    {confidencePercent(
                      job.confidence,
                    )}
                  </td>
                  <td>
                    <span
                      className={`ed-status ${job.status}`}
                    >
                      {job.status}
                    </span>
                  </td>
                  <td>
                    {new Date(
                      job.created_at,
                    ).toLocaleString()}
                  </td>
                  <td>
                    {formatBytes(
                      job.file_size_bytes,
                    )}
                  </td>
                  <td>
                    {job.status ===
                    'uploaded' ? (
                      <button
                        type="button"
                        onClick={() =>
                          onProcess(job)
                        }
                      >
                        Process
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() =>
                          onOpen(job)
                        }
                      >
                        Open
                      </button>
                    )}
                  </td>
                </tr>
              ),
            )}
          </tbody>
        </table>

        {jobs.length === 0 && (
          <div className="ed-empty">
            No matching documents.
          </div>
        )}
      </div>
    </section>
  )
}
