import type { ReactNode } from 'react'
import './intelligence.css'

export function IntelligenceCard({
  title,
  eyebrow,
  action,
  children,
}: {
  title: string
  eyebrow?: string
  action?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="intelligence-card">
      <header>
        <div>
          {eyebrow && <span>{eyebrow}</span>}
          <h3>{title}</h3>
        </div>
        {action}
      </header>
      <div className="intelligence-card-body">{children}</div>
    </section>
  )
}

export function MetricCard({
  label,
  value,
  detail,
  trend,
}: {
  label: string
  value: ReactNode
  detail?: string
  trend?: 'up' | 'down' | 'flat'
}) {
  return (
    <article className="intelligence-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>
        {trend === 'up' && '↑ '}
        {trend === 'down' && '↓ '}
        {trend === 'flat' && '→ '}
        {detail}
      </small>
    </article>
  )
}

export function HealthGauge({
  score,
  label,
  reasons = [],
}: {
  score: number
  label: string
  reasons?: string[]
}) {
  const bounded = Math.max(0, Math.min(100, score))

  return (
    <div className="health-gauge">
      <div
        className="health-gauge-ring"
        style={{
          background: `conic-gradient(currentColor ${bounded * 3.6}deg, rgba(148,163,184,.18) 0deg)`,
        }}
      >
        <div>
          <strong>{bounded}</strong>
          <span>{label}</span>
        </div>
      </div>
      {reasons.length > 0 && (
        <ul>
          {reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function RecommendationCard({
  title,
  reason,
  priority,
  action,
}: {
  title: string
  reason: string
  priority: 'Low' | 'Medium' | 'High' | 'Critical'
  action?: ReactNode
}) {
  return (
    <article className="recommendation-card">
      <div>
        <span>{priority}</span>
        <strong>{title}</strong>
        <p>{reason}</p>
      </div>
      {action}
    </article>
  )
}

export function EntityHeader({
  eyebrow,
  title,
  subtitle,
  status,
  actions,
}: {
  eyebrow: string
  title: string
  subtitle?: string
  status?: string
  actions?: ReactNode
}) {
  return (
    <header className="entity-header">
      <div>
        <span>{eyebrow}</span>
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      <div className="entity-header-actions">
        {status && <em>{status}</em>}
        {actions}
      </div>
    </header>
  )
}
