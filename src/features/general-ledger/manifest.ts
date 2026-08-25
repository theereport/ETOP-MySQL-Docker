import type { ModuleManifestEntry } from '../../platform/registry/moduleManifest'

export const manifests: ModuleManifestEntry[] = [
  {
    moduleId: 'general_ledger',
    title: 'General Ledger',
    shortTitle: 'General Ledger',
    description:
      'Chart of accounts, period balances, and posted transaction evidence from MaddenCo.',
    hint: 'G/L accounts & balances',
    icon: '📒',
    status: 'Ready',
    group: 'Workspaces',
    category: 'Finance & Compliance',
    search: {
      id: 'general-ledger',
      subtitle: 'Chart of accounts, balances, and posted transaction evidence',
      keywords: [
        'general ledger',
        'gl',
        'chart of accounts',
        'account balance',
        'journal entry',
        'reconciliation',
      ],
    },
  },
]
