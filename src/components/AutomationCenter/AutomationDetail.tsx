import type {
  AutomationDefinition,
  AutomationExecution,
} from './AutomationCenter'

type Props = {
  automation: AutomationDefinition

  executions: AutomationExecution[]

  isRunning: boolean

  onEdit: () => void

  onRunNow: () => void

  onToggleStatus: () => void

  onOpenExecution: (
    execution: AutomationExecution,
  ) => void

  onBack: () => void
}

function formatDate(
  value: string | null,
) {
  if (!value) return 'Never'

  return new Date(value).toLocaleString()
}

function AutomationDetail({
  automation,
  executions,

  isRunning,

  onEdit,
  onRunNow,
  onToggleStatus,
  onOpenExecution,
  onBack,
}: Props) {
  return (
    <div className="automation-detail">

      <div className="automation-detail-header">

        <div>

          <span className="automation-eyebrow">

            Automation

          </span>

          <h2>

            {automation.name}

          </h2>

          <p>

            {automation.description}

          </p>

        </div>

        <div className="automation-detail-actions">

          <button
            className="automation-secondary-button"
            onClick={onBack}
          >
            Back
          </button>

          <button
            className="automation-secondary-button"
            onClick={onEdit}
          >
            Edit
          </button>

          <button
            className="automation-primary-button"
            disabled={isRunning}
            onClick={onRunNow}
          >
            Run Now
          </button>

        </div>

      </div>

      <div className="automation-detail-grid">

        <section className="automation-card">

          <h3>

            General

          </h3>

          <table>

            <tbody>

              <tr>

                <td>Status</td>

                <td>

                  <span
                    className={`automation-status ${automation.status}`}
                  >
                    {automation.status}
                  </span>

                </td>

              </tr>

              <tr>

                <td>Category</td>

                <td>

                  {automation.category}

                </td>

              </tr>

              <tr>

                <td>Created</td>

                <td>

                  {formatDate(
                    automation.createdAt,
                  )}

                </td>

              </tr>

              <tr>

                <td>Updated</td>

                <td>

                  {formatDate(
                    automation.updatedAt,
                  )}

                </td>

              </tr>

            </tbody>

          </table>

        </section>

        <section className="automation-card">

          <h3>

            Source

          </h3>

          <table>

            <tbody>

              <tr>

                <td>Type</td>

                <td>

                  {automation.sourceType}

                </td>

              </tr>

              <tr>

                <td>Report</td>

                <td>

                  {automation.reportName ||
                    '-'}

                </td>

              </tr>

              <tr>

                <td>Script</td>

                <td>

                  {automation.scriptPath ||
                    '-'}

                </td>

              </tr>

            </tbody>

          </table>

        </section>

        <section className="automation-card">

          <h3>

            Schedule

          </h3>

          <table>

            <tbody>

              <tr>

                <td>Frequency</td>

                <td>

                  {
                    automation.schedule
                      .frequency
                  }

                </td>

              </tr>

              <tr>

                <td>Time</td>

                <td>

                  {
                    automation.schedule
                      .time
                  }

                </td>

              </tr>

              <tr>

                <td>Timezone</td>

                <td>

                  {
                    automation.schedule
                      .timezone
                  }

                </td>

              </tr>

              <tr>

                <td>Next Run</td>

                <td>

                  {formatDate(
                    automation.nextRunAt,
                  )}

                </td>

              </tr>

            </tbody>

          </table>

        </section>

        <section className="automation-card">

          <h3>

            Delivery

          </h3>

          <table>

            <tbody>

              <tr>

                <td>Method</td>

                <td>

                  {
                    automation.delivery
                      .method
                  }

                </td>

              </tr>

              <tr>

                <td>Recipients</td>

                <td>

                  {automation.delivery.recipients.join(
                    ', ',
                  ) || '-'}

                </td>

              </tr>

              <tr>

                <td>Output</td>

                <td>

                  {
                    automation.outputFormat
                  }

                </td>

              </tr>

              <tr>

                <td>Filename</td>

                <td>

                  {
                    automation.fileNameTemplate
                  }

                </td>

              </tr>

            </tbody>

          </table>

        </section>

      </div>

      <section className="automation-card">

        <div className="automation-section-header">

          <h3>

            Recent Executions

          </h3>

          <button
            onClick={onToggleStatus}
          >
            {automation.status ===
            'active'
              ? 'Pause'
              : 'Activate'}
          </button>

        </div>

        {executions.length === 0 ? (

          <div className="automation-empty">

            No executions yet.

          </div>

        ) : (

          <table className="automation-table">

            <thead>

              <tr>

                <th>Status</th>

                <th>Started</th>

                <th>Duration</th>

                <th>Rows</th>

                <th></th>

              </tr>

            </thead>

            <tbody>

              {executions.map(
                execution => (

                  <tr
                    key={execution.id}
                  >

                    <td>

                      <span
                        className={`automation-status ${execution.status}`}
                      >
                        {
                          execution.status
                        }
                      </span>

                    </td>

                    <td>

                      {formatDate(
                        execution.startedAt,
                      )}

                    </td>

                    <td>

                      {execution.durationMs
                        ? `${(
                            execution.durationMs /
                            1000
                          ).toFixed(
                            2,
                          )} sec`
                        : '-'}

                    </td>

                    <td>

                      {execution.rowCount ??
                        '-'}

                    </td>

                    <td>

                      <button
                        onClick={() =>
                          onOpenExecution(
                            execution,
                          )
                        }
                      >
                        Details
                      </button>

                    </td>

                  </tr>

                ),
              )}

            </tbody>

          </table>

        )}

      </section>

    </div>
  )
}

export default AutomationDetail