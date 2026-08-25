import type { ModuleManifestEntry } from '../../platform/registry/moduleManifest'

export const manifests: ModuleManifestEntry[] = [
  {
    moduleId: 'payment_notes',
    title: 'Payment Notes',
    shortTitle: 'Payment Notes',
    description:
      'Reconcile PNC remote-capture checks to expected Payment Notes with explainable matching and durable review.',
    hint: 'Warehouse deposits & review',
    icon: '▨',
    status: 'Ready',
    group: 'Workspaces',
    category: 'AR / Receivables',
    search: {
      id: 'payment-notes',
      subtitle: 'Warehouse remote-capture reconciliation and durable review',
      keywords: [
        'payment notes',
        'warehouse deposit',
        'remote capture',
        'virtual credit',
        'check reconciliation',
        'signature evidence',
      ],
    },
  },
]
