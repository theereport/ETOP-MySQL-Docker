import type { ModuleManifestEntry } from '../../platform/registry/moduleManifest'

export const manifests: ModuleManifestEntry[] = [
  {
    moduleId: 'sales_order_visibility',
    title: 'Sales Order Visibility',
    shortTitle: 'Sales Orders',
    description:
      'Invoice history, line items, memos, credit authorizations, and delivery cross-reference from MaddenCo. Invoice-forward only — no open order queue exists in this schema.',
    hint: 'Invoice evidence',
    icon: '⛁',
    status: 'Ready',
    group: 'Workspaces',
    category: 'Customer & Sales',
    search: {
      id: 'sales-order-visibility',
      subtitle: 'Invoice history, line items, authorizations, and delivery evidence',
      keywords: [
        'sales order',
        'invoice',
        'order history',
        'line item',
        'delivery',
        'credit authorization',
        'sales summary',
      ],
    },
  },
]
