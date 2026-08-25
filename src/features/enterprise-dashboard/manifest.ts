import type { ModuleManifestEntry } from '../../platform/registry/moduleManifest'

export const manifests: ModuleManifestEntry[] = [
  {
    moduleId: 'dashboard',
    title: 'Dashboard',
    shortTitle: 'Home',
    description: 'Start work, review priorities, and see platform health.',
    hint: 'Priorities & status',
    icon: '⌂',
    status: 'Ready',
    group: 'Overview',
    search: {
      id: 'dashboard',
      title: 'Home',
      subtitle: 'Priorities, quick starts, and platform health',
      keywords: ['home', 'health', 'brief', 'start'],
    },
  },
]
