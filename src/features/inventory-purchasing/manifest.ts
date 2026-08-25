import type { ModuleManifestEntry } from '../../platform/registry/moduleManifest'

export const manifests: ModuleManifestEntry[] = [
  {
    moduleId: 'inventory_purchasing',
    title: 'Inventory & Purchasing',
    shortTitle: 'Inventory',
    description:
      'Item identity, month-end inventory valuation, open purchase-order exposure, and receiving evidence from MaddenCo.',
    hint: 'Inventory & PO evidence',
    icon: '📦',
    status: 'Ready',
    group: 'Workspaces',
    category: 'Inventory & Supply Chain',
    search: {
      id: 'inventory-purchasing',
      subtitle: 'Item identity, inventory valuation, open POs, and receiving evidence',
      keywords: [
        'inventory',
        'purchasing',
        'product',
        'item',
        'stock',
        'purchase order',
        'receiving',
        'on hand',
      ],
    },
  },
]
