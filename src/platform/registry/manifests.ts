import type { ModuleManifestEntry } from './moduleManifest'
import { manifests as dashboardManifests } from '../../features/enterprise-dashboard/manifest'
import { manifests as customer360Manifests } from '../../features/customer360/manifest'
import { manifests as creditRiskManifests } from '../../features/credit-risk/manifest'
import { manifests as accountsPayableManifests } from '../../features/accounts-payable/manifest'
import { manifests as vendorIntelligenceManifests } from '../../features/vendor-intelligence/manifest'
import { manifests as arCollectionsManifests } from '../../features/ar-collections/manifest'
import { manifests as freightLogisticsManifests } from '../../features/freight-logistics/manifest'
import { manifests as routeIntelligenceManifests } from '../../features/route-intelligence/manifest'
import { manifests as inventoryPurchasingManifests } from '../../features/inventory-purchasing/manifest'
import { manifests as taxComplianceManifests } from '../../features/tax-compliance/manifest'
import { manifests as salesOrderVisibilityManifests } from '../../features/sales-order-visibility/manifest'
import { manifests as pricingContractsManifests } from '../../features/pricing-contracts/manifest'
import { manifests as generalLedgerManifests } from '../../features/general-ledger/manifest'
import { manifests as cashFlowForecastingManifests } from '../../features/cash-flow-forecasting/manifest'
import { manifests as financialCloseManifests } from '../../features/financial-close/manifest'
import { manifests as paymentNotesManifests } from '../../features/payment-notes/manifest'
import { manifests as workflowFoundationManifests } from '../../features/workflow-foundation/manifest'
import { manifests as securityAccessManifests } from '../../features/security-access/manifest'
import { manifests as documentIntelligenceManifests } from '../../modules/document-intelligence/manifest'

// Views that don't have their own module/feature folder yet — their
// component lives directly under src/components/, or they're inline JSX in
// App.tsx. Extracting these into real modules is feature work, not a
// metadata-wiring fix, so they stay listed here explicitly rather than
// silently duplicated between App.tsx and the search registry.
const pendingExtractionManifests: ModuleManifestEntry[] = [
  {
    moduleId: 'cash_application',
    title: 'Cash Application',
    shortTitle: 'Cash Application',
    description: 'Match payments, review invoice allocations, and inspect the decision trace.',
    hint: 'Payments & invoices',
    icon: '$',
    status: 'Ready',
    group: 'Workspaces',
    category: 'AR / Receivables',
    search: {
      id: 'cash',
      subtitle: 'Payment matching, allocations, and decision trace',
      keywords: ['cash', 'payment', 'invoice', 'allocation'],
    },
  },
  {
    moduleId: 'automation_center',
    title: 'Automation Center',
    shortTitle: 'Automation',
    description:
      'Schedule reports, execute scripts, monitor run history, and manage automated delivery.',
    hint: 'Schedules & run history',
    icon: '⚙',
    status: 'Ready',
    group: 'Workspaces',
    category: 'Operations',
    search: {
      id: 'automation',
      subtitle: 'Schedules, runs, and execution history',
      keywords: ['schedule', 'job', 'task'],
    },
  },
  {
    moduleId: 'report_builder',
    title: 'Report Builder',
    shortTitle: 'Reports',
    description:
      'Design reusable SQL reports, define parameters, preview data, and export large result sets.',
    hint: 'Reusable outputs',
    icon: '▥',
    status: 'Ready',
    group: 'Tools',
    search: {
      id: 'reports',
      title: 'Report Builder',
      subtitle: 'Create and export reusable reports',
      keywords: ['report', 'export', 'csv', 'excel'],
    },
  },
  {
    moduleId: 'sql_workspace',
    title: 'SQL Workspace',
    shortTitle: 'SQL Studio',
    description: 'Create, execute, save, and organize read-only SQL queries.',
    hint: 'Query enterprise data',
    icon: '⌘',
    status: 'Ready',
    group: 'Tools',
    search: {
      id: 'sql',
      title: 'SQL Studio',
      subtitle: 'Query and explore enterprise data',
      keywords: ['query', 'database', 'mysql'],
    },
  },
  {
    moduleId: 'knowledge_base',
    title: 'SOP Search',
    shortTitle: 'Knowledge Base',
    description: 'Manage and search the indexed company procedure library.',
    hint: 'SOPs & procedures',
    icon: '⌕',
    status: 'Ready',
    group: 'Tools',
    search: {
      id: 'knowledge',
      title: 'Knowledge Base',
      subtitle: 'Search indexed SOPs and procedures',
      keywords: ['sop', 'procedure', 'knowledge'],
    },
  },
  {
    moduleId: 'ai_assistant',
    title: 'AI Assistant',
    shortTitle: 'AI Assistant',
    description: 'Use local AI with company knowledge or general assistance.',
    hint: 'Ask, explain & research',
    icon: '✦',
    status: 'Ready',
    group: 'Tools',
    search: {
      id: 'assistant',
      subtitle: 'Local enterprise AI',
      keywords: ['ai', 'ollama', 'gemma'],
    },
  },
  {
    title: 'Project Tracker',
    shortTitle: 'Projects',
    description: 'Track transformation and technology projects.',
    hint: 'Transformation roadmap',
    icon: '◆',
    status: 'Coming Soon',
    group: 'System',
    showInSidebar: false,
  },
]

/**
 * Single source of truth for every module's nav/sidebar/search metadata.
 * Sidebar order within a group follows array order here — this grouping
 * keeps each real module's entries together and the not-yet-extracted
 * views last within their group; it doesn't need to match the old
 * hand-written App.tsx order exactly.
 */
export const moduleManifests: ModuleManifestEntry[] = [
  ...dashboardManifests,
  ...customer360Manifests,
  ...creditRiskManifests,
  ...accountsPayableManifests,
  ...vendorIntelligenceManifests,
  ...arCollectionsManifests,
  ...freightLogisticsManifests,
  ...routeIntelligenceManifests,
  ...inventoryPurchasingManifests,
  ...taxComplianceManifests,
  ...salesOrderVisibilityManifests,
  ...pricingContractsManifests,
  ...generalLedgerManifests,
  ...cashFlowForecastingManifests,
  ...financialCloseManifests,
  ...paymentNotesManifests,
  ...documentIntelligenceManifests,
  ...workflowFoundationManifests,
  ...securityAccessManifests,
  ...pendingExtractionManifests,
]
