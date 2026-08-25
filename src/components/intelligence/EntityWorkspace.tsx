import type { ReactNode } from 'react'
import { EntityHeader } from './IntelligenceComponents'
import './intelligence.css'

export type EntityTab =
  | 'Overview'
  | 'Health'
  | 'Financial'
  | 'Timeline'
  | 'Documents'
  | 'Notes'
  | 'Tasks'
  | 'Relationships'
  | 'Recommendations'
  | 'AI Summary'

export function EntityWorkspace({
  eyebrow,
  title,
  subtitle,
  status,
  activeTab,
  onTabChange,
  children,
  actions,
  tabs = [
    'Overview',
    'Health',
    'Financial',
    'Timeline',
    'Documents',
    'Notes',
    'Tasks',
    'Relationships',
    'Recommendations',
    'AI Summary',
  ],
}: {
  eyebrow: string
  title: string
  subtitle?: string
  status?: string
  activeTab: EntityTab
  onTabChange: (tab: EntityTab) => void
  children: ReactNode
  actions?: ReactNode
  tabs?: EntityTab[]
}) {
  return (
    <section className="entity-workspace">
      <EntityHeader
        eyebrow={eyebrow}
        title={title}
        subtitle={subtitle}
        status={status}
        actions={actions}
      />

      <nav className="entity-tabs">
        {tabs.map((tab) => (
          <button
            type="button"
            key={tab}
            className={activeTab === tab ? 'active' : ''}
            onClick={() => onTabChange(tab)}
          >
            {tab}
          </button>
        ))}
      </nav>

      <div className="entity-workspace-content">{children}</div>
    </section>
  )
}
