import './EnterpriseDashboard.css'

type DashboardProps = {
  displayName: string
  systemReady: boolean
  knowledgeDocuments: number | null
  searchableChunks: number | null
  moduleCount: number
  onOpenModule: (
    moduleName: string,
    options?: { customerView?: 'risk-review' },
  ) => void
  canOpenModule: (moduleName: string) => boolean
}

type HealthTile = {
  label: string
  value: string
  detail: string
  status: 'good' | 'watch' | 'neutral'
  module?: string
}

const healthTiles: HealthTile[] = [
  {
    label: 'Customer Intelligence',
    value: 'Ready',
    detail: 'Health, credit, sales, timeline, and AI insights',
    status: 'good',
    module: 'Customer 360',
  },
  {
    label: 'Document Operations',
    value: 'Ready',
    detail: 'Local intake, extraction, review, and AP workspace',
    status: 'good',
    module: 'Document Intelligence',
  },
  {
    label: 'Data Access',
    value: 'Read Only',
    detail: 'Protected MySQL query execution',
    status: 'good',
    module: 'SQL Workspace',
  },
  {
    label: 'Automation',
    value: 'Active',
    detail: 'Scheduled reporting and execution monitoring',
    status: 'neutral',
    module: 'Automation Center',
  },
]

const workQueue = [
  {
    priority: 'High',
    title: 'Review customers above credit thresholds',
    detail: 'Load the live priority queue in Customer Intelligence.',
    module: 'Customer 360',
    customerView: 'risk-review' as const,
  },
  {
    priority: 'High',
    title: 'Process the next PNC lockbox',
    detail: 'Upload the PDF, review exceptions, export, and save approved training.',
    module: 'Lockbox Automation',
  },
  {
    priority: 'Medium',
    title: 'Resolve document review items',
    detail: 'Open the review queue for unknown or low-confidence documents.',
    module: 'Document Intelligence',
  },
]

const recentActivity = [
  {
    time: 'Navigation',
    title: 'Lockbox is now a first-class operational workspace',
    detail: 'The full PNC workflow is available directly from Daily Work.',
  },
  {
    time: 'Data',
    title: 'SQL Studio and read-only database access are available',
    detail: 'Users can explore, validate, and export operational data safely.',
  },
  {
    time: 'Documents',
    title: 'Document operations and AI configuration are separated',
    detail: 'Daily review work stays focused while training tools live in AI Studio.',
  },
]

export default function EnterpriseDashboard({
  displayName,
  systemReady,
  knowledgeDocuments,
  searchableChunks,
  moduleCount,
  onOpenModule,
  canOpenModule,
}: DashboardProps) {
  const firstName = displayName.trim().split(/\s+/)[0] || 'there'
  const availableHealthTiles = healthTiles.filter((tile) => (
    !tile.module || canOpenModule(tile.module)
  ))
  const availableWorkQueue = workQueue.filter((item) => canOpenModule(item.module))

  return (
    <section className="enterprise-dashboard">
      <header className="enterprise-dashboard-hero">
        <div>
          <span className="enterprise-dashboard-eyebrow">ETOP ENTERPRISE COMMAND CENTER</span>
          <h1>Good evening, {firstName}.</h1>
          <p>
            See the health of the local platform, open the work that needs attention,
            and move directly into the right enterprise workspace.
          </p>
        </div>

        <div className="enterprise-dashboard-status-card">
          <div className="enterprise-dashboard-status-heading">
            <span>Platform status</span>
            <strong className={systemReady ? 'is-ready' : 'is-checking'}>
              {systemReady ? 'Operational' : 'Checking'}
            </strong>
          </div>
          <dl>
            <div>
              <dt>Available modules</dt>
              <dd>{moduleCount}</dd>
            </div>
            <div>
              <dt>Knowledge documents</dt>
              <dd>{knowledgeDocuments ?? '—'}</dd>
            </div>
            <div>
              <dt>Searchable chunks</dt>
              <dd>{searchableChunks ?? '—'}</dd>
            </div>
            <div>
              <dt>AI environment</dt>
              <dd>Local</dd>
            </div>
          </dl>
        </div>
      </header>

      <div className="enterprise-dashboard-quick-actions" aria-label="Quick actions">
        {canOpenModule('Customer 360') && <button type="button" onClick={() => onOpenModule('Customer 360')}>
          <span>👥</span>
          <strong>Find Customer</strong>
          <small>Open Customer Intelligence</small>
        </button>}
        {canOpenModule('Cash Application') && <button type="button" onClick={() => onOpenModule('Cash Application')}>
          <span>$</span>
          <strong>Apply Payment</strong>
          <small>Review matching recommendations</small>
        </button>}
        {canOpenModule('Lockbox Automation') && <button type="button" onClick={() => onOpenModule('Lockbox Automation')}>
          <span>▦</span>
          <strong>Process Lockbox</strong>
          <small>Run the guided PNC workflow</small>
        </button>}
        {canOpenModule('Document Intelligence') && <button type="button" onClick={() => onOpenModule('Document Intelligence')}>
          <span>▤</span>
          <strong>Review Documents</strong>
          <small>Open intake and review queues</small>
        </button>}
        {canOpenModule('Report Builder') && <button type="button" onClick={() => onOpenModule('Report Builder')}>
          <span>▥</span>
          <strong>Build Report</strong>
          <small>Create a reusable business report</small>
        </button>}
        {canOpenModule('AI Assistant') && <button type="button" onClick={() => onOpenModule('AI Assistant')}>
          <span>✦</span>
          <strong>Ask ETOP AI</strong>
          <small>Use local AI and company knowledge</small>
        </button>}
      </div>

      <div className="enterprise-dashboard-section-heading">
        <div>
          <span>ENTERPRISE HEALTH</span>
          <h2>Platform capabilities</h2>
        </div>
        <p>Live platform status combined with configured ETOP capabilities.</p>
      </div>

      <div className="enterprise-health-grid">
        {availableHealthTiles.map((tile) => (
          <button
            type="button"
            key={tile.label}
            className="enterprise-health-tile"
            onClick={() => tile.module && onOpenModule(tile.module)}
          >
            <div className="enterprise-health-tile-top">
              <span>{tile.label}</span>
              <i className={`health-indicator ${tile.status}`} />
            </div>
            <strong>{tile.value}</strong>
            <p>{tile.detail}</p>
            <small>Open workspace →</small>
          </button>
        ))}
      </div>

      <div className="enterprise-dashboard-main-grid">
        <article className="enterprise-dashboard-panel morning-brief-panel">
          <div className="enterprise-panel-heading">
            <div>
              <span>AI COMMAND CENTER</span>
              <h2>Morning brief</h2>
            </div>
            {canOpenModule('AI Assistant') && <button type="button" onClick={() => onOpenModule('AI Assistant')}>
              Open assistant
            </button>}
          </div>

          <div className="morning-brief-summary">
            <strong>ETOP is ready for operational use.</strong>
            <p>
              Customer Intelligence is working, the company knowledge base is available,
              and your read-only data tools are connected. Lockbox, document review, and
              cash application now open as focused operational workspaces instead of being
              buried inside a general document area.
            </p>
          </div>

          <div className="morning-brief-signals">
            <div><span>Customer workspace</span><strong>Ready</strong></div>
            <div><span>Local knowledge</span><strong>{systemReady ? 'Available' : 'Checking'}</strong></div>
            <div><span>Database protection</span><strong>Read only</strong></div>
            <div><span>Document AI</span><strong>Separated</strong></div>
          </div>
        </article>

        <article className="enterprise-dashboard-panel work-queue-panel">
          <div className="enterprise-panel-heading">
            <div>
              <span>WORK QUEUE</span>
              <h2>Needs attention</h2>
            </div>
            <b>{availableWorkQueue.length}</b>
          </div>

          <div className="enterprise-work-queue">
            {availableWorkQueue.map((item) => (
              <button
                type="button"
                key={item.title}
                onClick={() =>
                  onOpenModule(
                    item.module,
                    item.customerView
                      ? { customerView: item.customerView }
                      : undefined,
                  )
                }
              >
                <span className={`queue-priority ${item.priority.toLowerCase()}`}>{item.priority}</span>
                <div>
                  <strong>{item.title}</strong>
                  <p>{item.detail}</p>
                </div>
                <i>→</i>
              </button>
            ))}
          </div>
        </article>

        <article className="enterprise-dashboard-panel activity-panel">
          <div className="enterprise-panel-heading">
            <div>
              <span>ENTERPRISE TIMELINE</span>
              <h2>Recent platform activity</h2>
            </div>
          </div>

          <div className="enterprise-activity-list">
            {recentActivity.map((item) => (
              <div key={item.title}>
                <span>{item.time}</span>
                <i />
                <section>
                  <strong>{item.title}</strong>
                  <p>{item.detail}</p>
                </section>
              </div>
            ))}
          </div>
        </article>

        <article className="enterprise-dashboard-panel launch-panel">
          <div className="enterprise-panel-heading">
            <div>
              <span>CORE WORKSPACES</span>
              <h2>Launch center</h2>
            </div>
          </div>

          <div className="enterprise-launch-list">
            {canOpenModule('Customer 360') && <button type="button" onClick={() => onOpenModule('Customer 360')}>
              <span>Customer Intelligence</span><small>Health, credit, sales, timeline, and AI</small>
            </button>}
            {canOpenModule('Cash Application') && <button type="button" onClick={() => onOpenModule('Cash Application')}>
              <span>Cash Application</span><small>Payment matching and decision trace</small>
            </button>}
            {canOpenModule('Lockbox Automation') && <button type="button" onClick={() => onOpenModule('Lockbox Automation')}>
              <span>Lockbox Automation</span><small>PNC upload, review, export, and training</small>
            </button>}
            {canOpenModule('Document Intelligence') && <button type="button" onClick={() => onOpenModule('Document Intelligence')}>
              <span>Document Operations</span><small>Intake, queues, review, and AP documents</small>
            </button>}
            {canOpenModule('Report Builder') && <button type="button" onClick={() => onOpenModule('Report Builder')}>
              <span>Report Builder</span><small>Reusable reports and large exports</small>
            </button>}
            {canOpenModule('Automation Center') && <button type="button" onClick={() => onOpenModule('Automation Center')}>
              <span>Automation Center</span><small>Schedules, runs, and delivery</small>
            </button>}
          </div>
        </article>
      </div>
    </section>
  )
}
