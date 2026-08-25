import type {
  DocumentJob,
} from '../types'

import {
  confidencePercent,
} from '../utils'

type Props = {
  jobs: DocumentJob[]
  onOpen: (
    job: DocumentJob,
  ) => void
}

export default function APDashboard({
  jobs,
  onOpen,
}: Props) {
  const completedCount = jobs.filter(
    (job) => job.status === 'completed',
  ).length
  const failedCount = jobs.filter(
    (job) => job.status === 'failed',
  ).length

  return (
    <>
      <section className="ed-metrics">
        <article>
          <span>AP Invoices</span>
          <strong>
            {jobs.length}
          </strong>
          <small>
            Classified vendor invoices
          </small>
        </article>

        <article>
          <span>
            Completed Extractions
          </span>
          <strong>
            {completedCount}
          </strong>
          <small>
            Machine evidence only
          </small>
        </article>

        <article>
          <span>Processing Attention</span>
          <strong>
            {failedCount}
          </strong>
          <small>
            Failed jobs; human action required
          </small>
        </article>
      </section>

      <section className="ed-card">
        <div className="ed-card-heading">
          <div>
            <strong>
              AP Document Intake
            </strong>
            <span>
              Foundation for the future
              AP workflow
            </span>
          </div>
        </div>

        <div className="ed-table-wrap">
          <table className="ed-table">
            <thead>
              <tr>
                <th>
                  Invoice File
                </th>
                <th>Classifier Confidence</th>
                <th>Received</th>
                <th>Status</th>
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
                    </td>
                    <td>
                      {job.confidence > 0
                        ? confidencePercent(job.confidence)
                        : 'Unavailable'}
                    </td>
                    <td>
                      {new Date(
                        job.created_at,
                      ).toLocaleString()}
                    </td>
                    <td>
                      <span
                        className={`ed-status ${job.status}`}
                      >
                        {job.status}
                      </span>
                    </td>
                    <td>
                      <button
                        type="button"
                        onClick={() =>
                          onOpen(job)
                        }
                      >
                        Review
                      </button>
                    </td>
                  </tr>
                ),
              )}
            </tbody>
          </table>

          {jobs.length === 0 && (
            <div className="ed-empty">
              No vendor invoices have
              been classified.
            </div>
          )}
        </div>
      </section>
    </>
  )
}
