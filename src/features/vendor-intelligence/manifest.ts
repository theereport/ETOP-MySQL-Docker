import type { ModuleManifestEntry } from '../../platform/registry/moduleManifest'

export const manifests: ModuleManifestEntry[] = [
  {
    moduleId: 'vendor_intelligence',
    title: 'Vendor Intelligence',
    shortTitle: 'Vendors',
    description:
      'Vendor identity, purchase orders, receiving, and payables evidence from MaddenCo.',
    hint: 'Vendor evidence',
    icon: '◫',
    status: 'Ready',
    group: 'Workspaces',
    category: 'AP / Vendor',
    search: {
      id: 'vendor-intelligence',
      subtitle: 'Vendor identity, open POs, receiving, and payables evidence',
      keywords: [
        'vendor',
        'supplier',
        'purchase order',
        'receiving',
        'payables',
        'cost variance',
      ],
    },
  },
]
