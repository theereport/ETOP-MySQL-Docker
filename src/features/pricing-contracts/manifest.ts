import type { ModuleManifestEntry } from '../../platform/registry/moduleManifest'

export const manifests: ModuleManifestEntry[] = [
  {
    moduleId: 'pricing_contracts',
    title: 'Pricing & Contracts',
    shortTitle: 'Pricing',
    description:
      'Customer/vendor/product pricing overrides from TMDISC, product-class labels, and a customer-class reference from MaddenCo.',
    hint: 'Pricing override evidence',
    icon: '⚖',
    status: 'Ready',
    group: 'Workspaces',
    category: 'Customer & Sales',
    search: {
      id: 'pricing-contracts',
      subtitle: 'TMDISC pricing overrides, product/customer classes, and rebate notes',
      keywords: [
        'pricing',
        'contract',
        'discount',
        'rebate',
        'override',
        'tmdisc',
        'product class',
        'customer class',
      ],
    },
  },
]
