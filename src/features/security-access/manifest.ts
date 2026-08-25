import type { ModuleManifestEntry } from '../../platform/registry/moduleManifest'

export const manifests: ModuleManifestEntry[] = [
  {
    moduleId: 'security_administration',
    title: 'Security & Access',
    shortTitle: 'Security & Access',
    description:
      'Invite local users, suspend or reactivate accounts, and control module access.',
    hint: 'Users & module access',
    icon: '◈',
    status: 'Ready',
    group: 'System',
    search: {
      id: 'security-access',
      subtitle: 'User invitations, account status, and module access control',
      keywords: ['security', 'access', 'users', 'invite', 'permissions'],
    },
  },
]
