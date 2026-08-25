import type { ModuleManifestEntry } from '../../platform/registry/moduleManifest'

export const manifests: ModuleManifestEntry[] = [
  {
    moduleId: 'work_management',
    title: 'Work Management',
    shortTitle: 'Work Management',
    description:
      'Authenticate local users, coordinate durable role queues, and preserve governed assignment and audit evidence.',
    hint: 'Identity, tasks & audit',
    icon: '◉',
    status: 'Ready',
    group: 'Workspaces',
    category: 'Operations',
    search: {
      id: 'work-management',
      subtitle: 'Identity, role queues, assignment, and audit evidence',
      keywords: ['work management', 'tasks', 'assignment', 'audit', 'identity'],
    },
  },
]
