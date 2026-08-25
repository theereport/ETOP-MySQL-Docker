import type { ModuleManifestEntry } from '../../platform/registry/moduleManifest'

export const manifests: ModuleManifestEntry[] = [
  {
    moduleId: 'customer_360',
    title: 'Customer 360',
    shortTitle: 'Customers',
    description:
      'Review customer accounts, credit, sales, aging, payment history, and recommendations.',
    hint: 'Accounts & credit',
    icon: '👥',
    status: 'Ready',
    group: 'Workspaces',
    search: {
      id: 'customer360',
      title: 'Customers',
      subtitle: 'Customer health, credit, sales, and activity',
      keywords: ['customer', 'credit', 'sales', 'aging'],
    },
  },
]
