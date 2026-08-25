import { useMemo, useState } from 'react'
import { platformSearchSeed } from '../registry/modules'
import { getNotifications, getTasks, platformTimeline, saveNotifications, saveTasks } from '../services/platformStore'
import type { PlatformNotification, PlatformTask } from '../types'
import './PlatformCenter.css'

type Props = {
  mode: 'search' | 'notifications' | 'tasks' | 'timeline'
  onClose: () => void
  onOpenModule: (module: string) => void
}

export default function PlatformCenter({ mode, onClose, onOpenModule }: Props) {
  const [query, setQuery] = useState('')
  const [notifications, setNotifications] = useState<PlatformNotification[]>(getNotifications)
  const [tasks, setTasks] = useState<PlatformTask[]>(getTasks)

  const results = useMemo(() => {
    const value = query.trim().toLowerCase()
    if (!value) return platformSearchSeed
    return platformSearchSeed.filter((item) => [item.title, item.subtitle, ...(item.keywords ?? [])].join(' ').toLowerCase().includes(value))
  }, [query])

  function launch(module?: string) {
    if (module) onOpenModule(module)
    onClose()
  }

  function markAllRead() {
    const next = notifications.map((item) => ({ ...item, read: true }))
    setNotifications(next)
    saveNotifications(next)
  }

  function toggleTask(task: PlatformTask) {
    const next = tasks.map((item) => item.id === task.id ? { ...item, status: item.status === 'Completed' ? 'Open' as const : 'Completed' as const } : item)
    setTasks(next)
    saveTasks(next)
  }

  return (
    <div className="platform-center-backdrop" onMouseDown={onClose}>
      <section className="platform-center" onMouseDown={(event) => event.stopPropagation()}>
        <header>
          <div><span>ETOP PLATFORM</span><h2>{mode === 'search' ? 'Enterprise Search' : mode === 'notifications' ? 'Notification Center' : mode === 'tasks' ? 'My Tasks' : 'Enterprise Timeline'}</h2></div>
          <button type="button" onClick={onClose} aria-label="Close">×</button>
        </header>

        {mode === 'search' && <>
          <div className="platform-search-box"><span>⌕</span><input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search modules, customers, reports, documents, and commands..." /><kbd>Esc</kbd></div>
          <div className="platform-result-list">
            {results.map((item) => <button type="button" key={item.id} onClick={() => launch(item.module)}><b>{item.icon}</b><span><strong>{item.title}</strong><small>{item.subtitle}</small></span><em>{item.type}</em></button>)}
            {results.length === 0 && <div className="platform-empty">No matching ETOP capabilities were found.</div>}
          </div>
        </>}

        {mode === 'notifications' && <>
          <div className="platform-center-toolbar"><span>{notifications.filter((item) => !item.read).length} unread</span><button type="button" onClick={markAllRead}>Mark all read</button></div>
          <div className="platform-feed">{notifications.map((item) => <article key={item.id} className={`${item.severity} ${item.read ? 'read' : ''}`} onClick={() => launch(item.module)}><i /><div><strong>{item.title}</strong><p>{item.message}</p><small>{new Date(item.createdAt).toLocaleString()}</small></div></article>)}</div>
        </>}

        {mode === 'tasks' && <div className="platform-feed">{tasks.map((task) => <article key={task.id} className={task.status === 'Completed' ? 'read success' : task.priority === 'Critical' ? 'critical' : 'warning'}><button className="task-check" type="button" onClick={() => toggleTask(task)}>{task.status === 'Completed' ? '✓' : ''}</button><div onClick={() => launch(task.module)}><strong>{task.title}</strong><p>{task.description}</p><small>Due {task.dueDate} · {task.priority} · {task.status}</small></div></article>)}</div>}

        {mode === 'timeline' && <div className="platform-feed timeline">{platformTimeline.map((event) => <article key={event.id} className={event.severity} onClick={() => launch(event.module)}><i /><div><strong>{event.title}</strong><p>{event.description}</p><small>{event.category} · {new Date(event.timestamp).toLocaleString()}</small></div></article>)}</div>}
      </section>
    </div>
  )
}
