import type { ModuleManifestEntry } from '../../platform/registry/moduleManifest'

export const manifests: ModuleManifestEntry[] = [
  {
    moduleId: 'tax_compliance',
    title: 'Tax Compliance',
    shortTitle: 'Tax Compliance',
    description:
      'Tax authority rates, exemption codes, and customer exemption-code verification from MaddenCo.',
    hint: 'Tax evidence',
    icon: '§',
    status: 'Ready',
    group: 'Workspaces',
    category: 'Finance & Compliance',
    search: {
      id: 'tax-compliance',
      subtitle: 'Tax authority rates, exemption codes, and customer exemption checks',
      keywords: [
        'tax',
        'exemption',
        'exempt',
        'certificate',
        'fet',
        'compliance',
        'nexus',
      ],
    },
  },
]
