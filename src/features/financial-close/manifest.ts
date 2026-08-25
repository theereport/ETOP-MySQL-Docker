import type { ModuleManifestEntry } from '../../platform/registry/moduleManifest'

export const manifests: ModuleManifestEntry[] = [
  {
    moduleId: 'financial_close',
    title: 'Financial Close',
    shortTitle: 'Financial Close',
    description:
      'Coordinate local close cycles, control ownership, and append-only evidence-readiness review.',
    hint: 'Close controls & evidence',
    icon: '▣',
    status: 'Ready',
    group: 'Workspaces',
    category: 'Finance & Compliance',
    search: {
      id: 'financial-close',
      subtitle: 'Close cycles, control ownership, and evidence-readiness review',
      keywords: ['financial close', 'controls', 'readiness', 'evidence'],
    },
  },
]
