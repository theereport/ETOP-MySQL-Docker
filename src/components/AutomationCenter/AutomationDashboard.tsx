import type {
  AutomationDefinition,
  AutomationExecution,
} from './AutomationCenter'

type Props = {
  automations: AutomationDefinition[]
  executions: AutomationExecution[]
  isRunning: boolean

  onCreate: () => void
  onOpenAutomation: (
    automation: AutomationDefinition,
  ) => void

  onOpenExecution: (
    execution: AutomationExecution,
  ) => void

  onRunNow: (
    automation: AutomationDefinition,
  ) => void

  onViewAll: () => void
  onViewHistory: () => void
}

function AutomationDashboard({
  automations,
  executions,
  isRunning,

  onCreate,
  onOpenAutomation,
  onOpenExecution,
  onRunNow,
  onViewAll,
  onViewHistory,
}: Props) {
  const active =
    automations.filter(
      a => a.status === 'active',
    ).length

  const paused =
    automations.filter(
      a => a.status === 'paused',
    ).length

  const drafts =
    automations.filter(
      a => a.status === 'draft',
    ).length

  const failed =
    executions.filter(
      e => e.status === 'failed',
    ).length

  const recentExecutions =
    executions.slice(0, 10)

  const recentAutomations =
    automations.slice(0, 6)

  return (
    <div className="automation-dashboard">

      <section className="automation-stat-grid">

        <div className="automation-stat-card">
          <span>Active</span>
          <strong>{active}</strong>
        </div>

        <div className="automation-stat-card">
          <span>Paused</span>
          <strong>{paused}</strong>
        </div>

        <div className="automation-stat-card">
          <span>Drafts</span>
          <strong>{drafts}</strong>
        </div>

        <div className="automation-stat-card">
          <span>Failed Today</span>
          <strong>{failed}</strong>
        </div>

      </section>

      <section className="automation-dashboard-actions">

        <button
          className="automation-primary-button"
          onClick={onCreate}
        >
          + New Automation
        </button>

        <button
          className="automation-secondary-button"
          onClick={onViewAll}
        >
          View All Automations
        </button>

        <button
          className="automation-secondary-button"
          onClick={onViewHistory}
        >
          Execution History
        </button>

      </section>

      <section className="automation-dashboard-section">

        <div className="automation-section-header">

          <h2>
            Recent Automations
          </h2>

          <button
            onClick={onViewAll}
          >
            View All
          </button>

        </div>

        {recentAutomations.length === 0 ? (

          <div className="automation-empty">

            No automations created.

          </div>

        ) : (

          <table className="automation-table">

            <thead>

              <tr>

                <th>Name</th>
                <th>Status</th>
                <th>Next Run</th>
                <th></th>

              </tr>

            </thead>

            <tbody>

              {recentAutomations.map(a => (

                <tr key={a.id}>

                  <td>{a.name}</td>

                  <td>

                    <span
                      className={`automation-status ${a.status}`}
                    >
                      {a.status}
                    </span>

                  </td>

                  <td>

                    {a.nextRunAt ?? '-'}

                  </td>

                  <td>

                    <button
                      onClick={() =>
                        onRunNow(a)
                      }
                      disabled={isRunning}
                    >
                      Run

                    </button>

                    <button
                      onClick={() =>
                        onOpenAutomation(a)
                      }
                    >
                      Open
                    </button>

                  </td>

                </tr>

              ))}

            </tbody>

          </table>

        )}

      </section>

      <section className="automation-dashboard-section">

        <div className="automation-section-header">

          <h2>

            Recent Executions

          </h2>

        </div>

        {recentExecutions.length === 0 ? (

          <div className="automation-empty">

            Nothing has been executed yet.

          </div>

        ) : (

          <table className="automation-table">

            <thead>

              <tr>

                <th>Automation</th>

                <th>Status</th>

                <th>Started</th>

                <th>Rows</th>

                <th></th>

              </tr>

            </thead>

            <tbody>

              {recentExecutions.map(e => (

                <tr key={e.id}>

                  <td>

                    {e.automationName}

                  </td>

                  <td>

                    <span
                      className={`automation-status ${e.status}`}
                    >
                      {e.status}
                    </span>

                  </td>

                  <td>

                    {new Date(
                      e.startedAt,
                    ).toLocaleString()}

                  </td>

                  <td>

                    {e.rowCount ?? '-'}

                  </td>

                  <td>

                    <button
                      onClick={() =>
                        onOpenExecution(e)
                      }
                    >
                      Details
                    </button>

                  </td>

                </tr>

              ))}

            </tbody>

          </table>

        )}

      </section>

    </div>
  )
}

export default AutomationDashboard