import type { ModuleManifestEntry } from '../../platform/registry/moduleManifest'

export const manifests: ModuleManifestEntry[] = [
  {
    moduleId: 'cash_flow_forecasting',
    title: 'Cash Flow Forecasting',
    shortTitle: 'Cash Flow',
    description:
      '14-week rolling cash flow projection with a prior-year backtest and accuracy history.',
    hint: '13-week cash forecast',
    icon: '💵',
    status: 'Ready',
    group: 'Workspaces',
    category: 'Finance & Compliance',
    search: {
      id: 'cash-flow-forecasting',
      subtitle: 'Rolling cash flow projection, prior-year backtest, and accuracy history',
      keywords: [
        'cash flow',
        'cash forecast',
        'treasury',
        'bank balance',
        'line of credit',
        '13 week',
        '14 week',
      ],
    },
  },
]
