export type PlatformSeverity = 'info' | 'success' | 'warning' | 'critical'

export type PlatformSearchResult = {
  id: string
  type: 'module' | 'customer' | 'document' | 'task' | 'command'
  title: string
  subtitle: string
  icon: string
  module?: string
  keywords?: string[]
}

export type PlatformNotification = {
  id: string
  title: string
  message: string
  severity: PlatformSeverity
  createdAt: string
  read: boolean
  module?: string
}

export type PlatformTask = {
  id: string
  title: string
  description: string
  dueDate: string
  priority: 'Low' | 'Medium' | 'High' | 'Critical'
  status: 'Open' | 'In Progress' | 'Completed'
  module?: string
}

export type PlatformTimelineEvent = {
  id: string
  title: string
  description: string
  timestamp: string
  category: string
  severity: PlatformSeverity
  module?: string
}
