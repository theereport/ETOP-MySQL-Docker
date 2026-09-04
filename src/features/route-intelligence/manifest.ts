import type { ModuleManifestEntry } from '../../platform/registry/moduleManifest'

export const manifests: ModuleManifestEntry[] = [
  {
    moduleId: 'route_intelligence',
    title: 'Route Intelligence',
    shortTitle: 'Route Intel',
    description:
      'Data quality checks and master-data management for delivery routes, vehicles, drivers, and customer delivery constraints.',
    hint: 'Route capacity foundation',
    icon: '🧭',
    status: 'Ready',
    group: 'Workspaces',
    category: 'Inventory & Supply Chain',
    search: {
      id: 'route-intelligence',
      subtitle: 'Route data quality, vehicles, drivers, and customer profiles',
      keywords: [
        'route',
        'routing',
        'delivery',
        'capacity',
        'vehicle',
        'driver',
        'samsara',
        'data quality',
      ],
    },
  },
]
