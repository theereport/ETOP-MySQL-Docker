import type { ModuleManifestEntry } from '../../platform/registry/moduleManifest'

export const manifests: ModuleManifestEntry[] = [
  {
    moduleId: 'credit_risk',
    title: 'Credit Risk',
    shortTitle: 'Credit Risk',
    description:
      'Review source-grounded exposure, aging, payment evidence, and append-only manual assessments.',
    hint: 'Evidence & assessments',
    icon: '◫',
    status: 'Ready',
    group: 'Workspaces',
    category: 'AR / Receivables',
    search: {
      id: 'credit-risk',
      subtitle:
        'Assessed-customer priority, alerts, evidence, and manual assessment history',
      keywords: [
        'credit risk',
        'manual rating',
        'assessment',
        'exposure',
        'review date',
        'priority alerts',
        'deterioration',
      ],
    },
  },
]
