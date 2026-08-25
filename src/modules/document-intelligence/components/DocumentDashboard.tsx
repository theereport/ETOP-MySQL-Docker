import type {
  DocumentHealth,
  DocumentJob,
} from '../types'

import {
  confidencePercent,
  formatDocumentType,
} from '../utils'

type Props = {
  health: DocumentHealth | null
  jobs: DocumentJob[]
  reviewCount: number
  completedCount: number
  failedCount: number
  averageConfidence: number
  onOpen: (
    job: DocumentJob,
  ) => void
  onViewAll: () => void
}

export default function DocumentDashboard({
  health,
  jobs,
  reviewCount,
  completedCount,
  failedCount,
  averageConfidence,
  onOpen,
  onViewAll,
}: Props) {
  return (
    <>
      <section className="ed-metrics">
        <article>
          <span>
            Total Documents
          </span>
          <strong>
            {health?.job_count ??
              jobs.length}
          </strong>
          <small>
            Stored locally
          </small>
        </article>

        <article>
          <span>
            Awaiting Review
          </span>
          <strong>
            {reviewCount}
          </strong>
          <small>
            Low confidence or unknown
          </small>
        </article>

        <article>
          <span>Completed</span>
          <strong>
            {completedCount}
          </strong>
          <small>
            Structured results
          </small>
        </article>

        <article>
          <span>Failed</span>
          <strong>
            {failedCount}
          </strong>
          <small>
            Requires attention
          </small>
        </article>

        <article>
          <span>
            Avg. Confidence
          </span>
          <strong>
            {confidencePercent(
              averageConfidence,
            )}
          </strong>
          <small>
            Completed documents
          </small>
        </article>
      </section>

      <section className="ed-dashboard-grid">
        <article className="ed-card">
          <div className="ed-card-heading">
            <div>
              <strong>
                Recent Documents
              </strong>
              <span>
                Latest processing activity
              </span>
            </div>

            <button
              type="button"
              onClick={onViewAll}
            >
              View all
            </button>
          </div>

          <div className="ed-job-list">
            {jobs
              .slice(0, 7)
              .map(
                (job) => (
                  <button
                    type="button"
                    key={job.job_id}
                    onClick={() =>
                      onOpen(job)
                    }
                  >
                    <span className="ed-file-icon">
                      PDF
                    </span>

                    <span className="ed-job-copy">
                      <strong>
                        {
                          job.original_file_name
                        }
                      </strong>
                      <small>
                        {formatDocumentType(
                          job.document_type,
                        )}{' '}
                        ·{' '}
                        {new Date(
                          job.created_at,
                        ).toLocaleString()}
                      </small>
                    </span>

                    <span
                      className={`ed-status ${job.status}`}
                    >
                      {job.status}
                    </span>
                  </button>
                ),
              )}

            {jobs.length === 0 && (
              <div className="ed-empty">
                No documents have been
                uploaded.
              </div>
            )}
          </div>
        </article>

        <article className="ed-card">
          <div className="ed-card-heading">
            <div>
              <strong>
                Platform Capabilities
              </strong>
              <span>
                Current backend features
              </span>
            </div>
          </div>

          <div className="ed-capability-grid">
            {Object.entries(
              health?.capabilities ??
                {},
            ).map(
              ([
                capability,
                enabled,
              ]) => (
                <div key={capability}>
                  <span
                    className={
                      enabled
                        ? 'enabled'
                        : ''
                    }
                  />
                  <strong>
                    {formatDocumentType(
                      capability,
                    )}
                  </strong>
                </div>
              ),
            )}
          </div>
        </article>

        <article className="ed-card ed-workflow-card">
          <div className="ed-card-heading">
            <div>
              <strong>
                Intelligent Workflow
              </strong>
              <span>
                Current document
                processing path
              </span>
            </div>
          </div>

          <div className="ed-workflow">
            {[
              'Upload',
              'Extract',
              'Classify',
              'Parse',
              'Validate',
              'Review',
              'Route',
            ].map(
              (
                step,
                index,
              ) => (
                <div key={step}>
                  <span>
                    {index + 1}
                  </span>
                  <strong>
                    {step}
                  </strong>
                </div>
              ),
            )}
          </div>
        </article>
      </section>
    </>
  )
}
