import type { ModuleManifestEntry } from '../../platform/registry/moduleManifest'

export const manifests: ModuleManifestEntry[] = [
  {
    moduleId: 'ar_collections',
    title: 'AR Collections',
    shortTitle: 'AR Collections',
    description:
      'Itemized open A/R, payment history, GL reference, and aging trend evidence from MaddenCo.',
    hint: 'Open A/R & aging evidence',
    icon: '⏳',
    status: 'Ready',
    group: 'Workspaces',
    category: 'AR / Receivables',
    search: {
      id: 'ar-collections',
      subtitle: 'Open A/R items, transaction history, GL lines, and aging trend',
      keywords: [
        'ar',
        'accounts receivable',
        'collections',
        'aging',
        'past due',
        'open invoice',
      ],
    },
  },
]
