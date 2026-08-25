import type { ModuleManifestEntry } from '../../platform/registry/moduleManifest'

export const manifests: ModuleManifestEntry[] = [
  {
    moduleId: 'accounts_payable',
    title: 'Accounts Payable',
    shortTitle: 'Accounts Payable',
    description:
      'Review imported vendor-invoice evidence, OCR coverage, exceptions, and duplicate candidates.',
    hint: 'Invoice intelligence',
    icon: '▧',
    status: 'Ready',
    group: 'Workspaces',
    category: 'AP / Vendor',
    search: {
      id: 'accounts-payable',
      subtitle:
        'Imported invoice evidence, OCR review, exceptions, and duplicate candidates',
      keywords: [
        'accounts payable',
        'ap invoice',
        'vendor invoice',
        'ocr',
        'duplicate',
        'exception',
      ],
    },
  },
]
