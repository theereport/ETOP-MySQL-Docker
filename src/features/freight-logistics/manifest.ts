import type { ModuleManifestEntry } from '../../platform/registry/moduleManifest'

export const manifests: ModuleManifestEntry[] = [
  {
    moduleId: 'freight_logistics',
    title: 'Freight & Logistics',
    shortTitle: 'Freight',
    description:
      'Route schedule, load manifest, COD payments, and delivery exception evidence from MaddenCo.',
    hint: 'Route delivery evidence',
    icon: '🚚',
    status: 'Ready',
    group: 'Workspaces',
    category: 'Inventory & Supply Chain',
    search: {
      id: 'freight-logistics',
      subtitle: 'Route schedule, load manifest, COD payments, and delivery exceptions',
      keywords: [
        'freight',
        'logistics',
        'route',
        'delivery',
        'load',
        'manifest',
        'cod',
        'payment',
        'signature',
        'exception',
      ],
    },
  },
]
