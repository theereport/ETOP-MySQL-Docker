import type { PlatformNotification, PlatformTask, PlatformTimelineEvent } from '../types'

const NOTIFICATION_KEY = 'etop.platform.notifications.v1'
const TASK_KEY = 'etop.platform.tasks.v1'

const defaultNotifications: PlatformNotification[] = [
  { id: 'n1', title: 'Customer workspace ready', message: 'Customer Intelligence is available from the Operations group.', severity: 'success', createdAt: new Date().toISOString(), read: false, module: 'Customer 360' },
  { id: 'n2', title: 'Knowledge status', message: 'Review document indexing status from the Knowledge Base.', severity: 'info', createdAt: new Date(Date.now() - 3600000).toISOString(), read: false, module: 'SOP Search' },
  { id: 'n3', title: 'Platform foundation active', message: 'Global search, notifications, tasks, and timeline are enabled.', severity: 'success', createdAt: new Date(Date.now() - 7200000).toISOString(), read: true, module: 'Dashboard' },
]

const defaultTasks: PlatformTask[] = [
  { id: 't1', title: 'Validate Customer Intelligence data', description: 'Compare one customer workspace against the ERP source.', dueDate: new Date().toISOString().slice(0, 10), priority: 'High', status: 'Open', module: 'Customer 360' },
  { id: 't2', title: 'Review automation execution history', description: 'Confirm recent scheduled jobs completed successfully.', dueDate: new Date(Date.now() + 86400000).toISOString().slice(0, 10), priority: 'Medium', status: 'Open', module: 'Automation Center' },
]

export const platformTimeline: PlatformTimelineEvent[] = [
  { id: 'e1', title: 'Platform framework loaded', description: 'ETOP shared search, task, notification, and timeline services initialized.', timestamp: new Date().toISOString(), category: 'Platform', severity: 'success', module: 'Dashboard' },
  { id: 'e2', title: 'Customer Intelligence enabled', description: 'Customer workspace is registered as an enterprise capability.', timestamp: new Date(Date.now() - 5400000).toISOString(), category: 'Customer', severity: 'info', module: 'Customer 360' },
  { id: 'e3', title: 'Local AI available', description: 'Enterprise assistant is configured to use the local Ollama service.', timestamp: new Date(Date.now() - 10800000).toISOString(), category: 'AI', severity: 'success', module: 'AI Assistant' },
]

function read<T>(key: string, fallback: T): T {
  try {
    const value = window.localStorage.getItem(key)
    return value ? JSON.parse(value) as T : fallback
  } catch {
    return fallback
  }
}

function write<T>(key: string, value: T): void {
  window.localStorage.setItem(key, JSON.stringify(value))
}

export function getNotifications(): PlatformNotification[] { return read(NOTIFICATION_KEY, defaultNotifications) }
export function saveNotifications(value: PlatformNotification[]): void { write(NOTIFICATION_KEY, value) }
export function getTasks(): PlatformTask[] { return read(TASK_KEY, defaultTasks) }
export function saveTasks(value: PlatformTask[]): void { write(TASK_KEY, value) }
