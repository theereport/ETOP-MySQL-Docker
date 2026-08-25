import type {
  PlatformNotification,
  PlatformTask,
  TimelineEvent,
} from './types'

const NOTIFICATION_KEY = 'etop.platform.notifications.v2'
const TASK_KEY = 'etop.platform.tasks.v2'
const TIMELINE_KEY = 'etop.platform.timeline.v2'

function readLocal<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

function writeLocal<T>(key: string, value: T): void {
  window.localStorage.setItem(key, JSON.stringify(value))
}

const defaultNotifications: PlatformNotification[] = [
  {
    id: 'platform-ready',
    title: 'Platform Core Ready',
    message: 'ETOP Sprint 4A enterprise platform services are available.',
    createdAt: new Date().toISOString(),
    severity: 'success',
    read: false,
    module: 'Platform',
  },
]

const defaultTasks: PlatformTask[] = [
  {
    id: 'verify-sprint4a',
    title: 'Verify Sprint 4A',
    description: 'Run the frontend build and verify platform health endpoints.',
    status: 'Open',
    priority: 'High',
    module: 'Platform',
  },
]

const defaultTimeline: TimelineEvent[] = [
  {
    id: 'sprint4a-installed',
    title: 'Sprint 4A platform initialized',
    description:
      'Global search, registry v2, and shared intelligence components loaded.',
    timestamp: new Date().toISOString(),
    module: 'Platform',
    category: 'Platform',
    severity: 'success',
  },
]

export function getNotifications(): PlatformNotification[] {
  return readLocal(NOTIFICATION_KEY, defaultNotifications)
}

export function saveNotifications(items: PlatformNotification[]): void {
  writeLocal(NOTIFICATION_KEY, items)
}

export function getTasks(): PlatformTask[] {
  return readLocal(TASK_KEY, defaultTasks)
}

export function saveTasks(items: PlatformTask[]): void {
  writeLocal(TASK_KEY, items)
}

export function getTimeline(): TimelineEvent[] {
  return readLocal(TIMELINE_KEY, defaultTimeline)
}

export function saveTimeline(items: TimelineEvent[]): void {
  writeLocal(TIMELINE_KEY, items)
}

export function addTimelineEvent(event: TimelineEvent): void {
  saveTimeline([event, ...getTimeline()].slice(0, 250))
}
