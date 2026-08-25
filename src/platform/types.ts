export type PlatformCenterMode =
  | 'search'
  | 'notifications'
  | 'tasks'
  | 'timeline'

export type ModuleCapability =
  | 'search'
  | 'timeline'
  | 'health'
  | 'recommendations'
  | 'ai'

export type PlatformModule = {
  id: string
  title: string
  shortTitle: string
  description: string
  icon: string
  group: string
  version: string
  status: 'Ready' | 'Coming Soon' | 'Degraded'
  capabilities: ModuleCapability[]
  keywords: string[]
}

export type SearchResult = {
  id: string
  type: string
  title: string
  subtitle: string
  module: string
  score?: number
  icon?: string
  keywords?: string[]
  action?: string
  metadata?: Record<string, string | number | boolean | null>
}

export type PlatformSearchResult =
  SearchResult

export type PlatformNotification = {
  id: string
  title: string
  message: string
  createdAt: string
  severity: 'info' | 'success' | 'warning' | 'critical'
  read: boolean
  module?: string
}

export type PlatformTask = {
  id: string
  title: string
  description?: string
  status: 'Open' | 'In Progress' | 'Completed'
  priority: 'Low' | 'Medium' | 'High' | 'Critical'
  dueDate?: string
  module?: string
}

export type TimelineEvent = {
  id: string
  title: string
  description: string
  timestamp: string
  module: string
  category: string
  entityType?: string
  entityId?: string
  severity:
    | 'info'
    | 'success'
    | 'warning'
    | 'critical'
}


export type PlatformTimelineEvent =
  TimelineEvent
