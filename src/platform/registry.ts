import type { PlatformModule } from './types'

export const platformModules: PlatformModule[] = [
  {
    id: 'dashboard',
    title: 'Dashboard',
    shortTitle: 'Dashboard',
    description: 'Enterprise command center and system overview.',
    icon: '⌂',
    group: 'Core',
    version: '2.0.0',
    status: 'Ready',
    capabilities: ['search', 'timeline', 'health', 'recommendations', 'ai'],
    keywords: ['home', 'command center', 'overview', 'health'],
  },
  {
    id: 'assistant',
    title: 'AI Assistant',
    shortTitle: 'AI Assistant',
    description: 'Local AI and indexed enterprise knowledge.',
    icon: '✦',
    group: 'Core',
    version: '1.1.0',
    status: 'Ready',
    capabilities: ['search', 'timeline', 'ai'],
    keywords: ['ai', 'knowledge', 'chat', 'ollama', 'gemma'],
  },
  {
    id: 'sql',
    title: 'SQL Workspace',
    shortTitle: 'SQL Studio',
    description: 'Read-only enterprise SQL workspace.',
    icon: '⌘',
    group: 'Data',
    version: '1.2.0',
    status: 'Ready',
    capabilities: ['search', 'timeline', 'ai'],
    keywords: ['query', 'database', 'mysql', 'table', 'product', 'inventory'],
  },
  {
    id: 'knowledge',
    title: 'SOP Search',
    shortTitle: 'Knowledge Base',
    description: 'Search indexed company procedures and supporting documents.',
    icon: '▤',
    group: 'Data',
    version: '1.1.0',
    status: 'Ready',
    capabilities: ['search', 'timeline', 'ai'],
    keywords: ['sop', 'procedure', 'policy', 'knowledge', 'document'],
  },
  {
    id: 'customer',
    title: 'Customer 360',
    shortTitle: 'Customer 360',
    description: 'Customer, credit, aging, sales, and relationship intelligence.',
    icon: '👥',
    group: 'Operations',
    version: '1.1.0',
    status: 'Ready',
    capabilities: ['search', 'timeline', 'health', 'recommendations', 'ai'],
    keywords: [
      'customer',
      'account',
      'credit',
      'aging',
      'sales',
      'route',
      'store',
      'risk',
      'high risk',
      'past due',
    ],
  },
  {
    id: 'cash-application',
    title: 'Cash Application',
    shortTitle: 'Cash Application',
    description: 'Payment matching and invoice allocation review.',
    icon: '$',
    group: 'Operations',
    version: '1.0.0',
    status: 'Ready',
    capabilities: ['search', 'timeline', 'recommendations'],
    keywords: ['cash', 'payment', 'invoice', 'remittance'],
  },
  {
    id: 'payment-notes',
    title: 'Payment Notes',
    shortTitle: 'Payment Notes',
    description:
      'Reconcile PNC remote-capture checks to expected Payment Notes with explainable matching and durable review.',
    icon: '▨',
    group: 'Operations',
    version: '0.1.0',
    status: 'Ready',
    capabilities: ['search', 'timeline', 'recommendations'],
    keywords: [
      'payment notes',
      'warehouse deposit',
      'remote capture',
      'virtual credit',
      'check reconciliation',
      'signature evidence',
    ],
  },
  {
    id: 'credit-risk',
    title: 'Credit Risk',
    shortTitle: 'Credit Risk',
    description:
      'Source-grounded credit evidence and append-only manual risk assessments.',
    icon: '◫',
    group: 'Operations',
    version: '0.2.0',
    status: 'Ready',
    capabilities: ['search', 'timeline'],
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
  {
    id: 'accounts-payable',
    title: 'Accounts Payable',
    shortTitle: 'Accounts Payable',
    description:
      'Imported vendor-invoice evidence, OCR review, exceptions, and duplicate candidates.',
    icon: '▧',
    group: 'Operations',
    version: '0.1.0',
    status: 'Ready',
    capabilities: ['search', 'timeline'],
    keywords: [
      'accounts payable',
      'ap invoice',
      'vendor invoice',
      'ocr review',
      'duplicate invoice',
      'exception review',
    ],
  },
  {
    id: 'financial-close',
    title: 'Financial Close',
    shortTitle: 'Financial Close',
    description:
      'Local close-cycle controls, verified preparation ownership, and evidence-readiness review.',
    icon: '▣',
    group: 'Operations',
    version: '0.1.0',
    status: 'Ready',
    capabilities: ['search', 'timeline', 'health'],
    keywords: [
      'financial close',
      'close calendar',
      'close cycle',
      'control item',
      'preparer',
      'reviewer',
      'evidence readiness',
      'controller',
    ],
  },
  {
    id: 'reports',
    title: 'Report Builder',
    shortTitle: 'Reports',
    description: 'Reusable reports, parameters, exports, and previews.',
    icon: '▥',
    group: 'Reporting',
    version: '1.0.0',
    status: 'Ready',
    capabilities: ['search', 'timeline'],
    keywords: ['report', 'export', 'csv', 'excel'],
  },
  {
    id: 'automation',
    title: 'Automation Center',
    shortTitle: 'Automation',
    description: 'Scheduled reports, scripts, run history, and delivery.',
    icon: '⚙',
    group: 'Operations',
    version: '1.0.0',
    status: 'Ready',
    capabilities: ['search', 'timeline', 'recommendations'],
    keywords: ['schedule', 'job', 'script', 'email'],
  },
  {
    id: 'work-management',
    title: 'Work Management',
    shortTitle: 'Work Management',
    description:
      'Authenticated local identities, durable role queues, verified assignments, notifications, and audit evidence.',
    icon: '◉',
    group: 'Operations',
    version: '0.1.0',
    status: 'Ready',
    capabilities: ['search', 'timeline', 'health'],
    keywords: [
      'identity',
      'user',
      'assignment',
      'task',
      'queue',
      'workflow',
      'notification',
      'audit',
      'work management',
    ],
  },
  {
    id: 'documents',
    title: 'Document Intelligence',
    shortTitle: 'Enterprise Documents',
    description: 'Classify, extract, review, train, and route enterprise documents.',
    icon: '▦',
    group: 'Operations',
    version: '1.0.0',
    status: 'Ready',
    capabilities: ['search', 'timeline', 'recommendations', 'ai'],
    keywords: [
      'document',
      'pdf',
      'ocr',
      'invoice',
      'lockbox',
      'pnc',
      'accounts payable',
      'training',
    ],
  },
  {
    id: 'projects',
    title: 'Project Tracker',
    shortTitle: 'Projects',
    description: 'Track transformation and technology projects.',
    icon: '◇',
    group: 'Operations',
    version: '0.1.0',
    status: 'Coming Soon',
    capabilities: ['search', 'timeline'],
    keywords: ['project', 'initiative', 'transformation', 'roadmap'],
  },
]

export function getPlatformModules(): PlatformModule[] {
  return platformModules
}

function tokenMatches(
  searchable: string,
  token: string,
): boolean {
  if (searchable.includes(token)) {
    return true
  }

  if (token.endsWith('ies') && token.length > 4) {
    return searchable.includes(`${token.slice(0, -3)}y`)
  }

  if (token.endsWith('s') && token.length > 3) {
    return searchable.includes(token.slice(0, -1))
  }

  return false
}

export function findPlatformModules(query: string): PlatformModule[] {
  const normalized = query.trim().toLowerCase()

  if (!normalized) {
    return []
  }

  const tokens = normalized.split(/\s+/).filter(Boolean)

  return platformModules
    .map((module) => {
      const title = `${module.title} ${module.shortTitle}`.toLowerCase()
      const searchable = [
        title,
        module.description,
        module.group,
        ...module.keywords,
      ]
        .join(' ')
        .toLowerCase()

      if (
        !tokens.every((token) =>
          tokenMatches(searchable, token),
        )
      ) {
        return null
      }

      const score =
        title.includes(normalized)
          ? 3
          : module.keywords.some((keyword) =>
              keyword.toLowerCase().includes(normalized),
            )
            ? 2
            : 1

      return { module, score }
    })
    .filter(
      (
        match,
      ): match is {
        module: PlatformModule
        score: number
      } => match !== null,
    )
    .sort(
      (left, right) =>
        right.score - left.score ||
        left.module.shortTitle.localeCompare(
          right.module.shortTitle,
        ),
    )
    .map((match) => match.module)
}
