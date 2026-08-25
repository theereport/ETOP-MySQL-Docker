import type { ModuleManifestEntry } from '../../platform/registry/moduleManifest'

// This module's <EnterpriseDocuments workspace="..."/> component backs three
// distinct nav entries via its `workspace` prop, so it contributes three
// manifest entries rather than one.
export const manifests: ModuleManifestEntry[] = [
  {
    moduleId: 'document_intelligence',
    title: 'Document Intelligence',
    shortTitle: 'Documents',
    description: 'Upload, classify, review, and route operational documents.',
    hint: 'Intake, review & AP',
    icon: '▤',
    status: 'Ready',
    group: 'Workspaces',
    category: 'Operations',
    search: {
      id: 'documents',
      title: 'Document Operations',
      subtitle: 'Document intake, extraction, queues, review, and AP',
      keywords: ['document', 'invoice', 'ap', 'pdf', 'ocr', 'review'],
    },
  },
  {
    moduleId: 'lockbox',
    title: 'Lockbox Automation',
    shortTitle: 'Lockbox',
    description: 'Process PNC lockbox PDFs from upload through review, export, and training.',
    hint: 'PNC PDF workflow',
    icon: '▦',
    status: 'Ready',
    group: 'Workspaces',
    category: 'AR / Receivables',
    search: {
      id: 'lockbox',
      subtitle: 'PNC PDF upload, review, export, and training',
      keywords: ['lockbox', 'pnc', 'check', 'remittance', 'pdf'],
    },
  },
  {
    moduleId: 'document_ai_studio',
    title: 'Document AI Studio',
    shortTitle: 'AI Studio',
    description:
      'Improve document extraction through training, quality review, profiles, templates, and parsers.',
    hint: 'Train & configure',
    icon: '◇',
    status: 'Ready',
    group: 'System',
    search: {
      id: 'document-ai-studio',
      subtitle: 'Training, quality, profiles, templates, and parsers',
      keywords: ['ai studio', 'training', 'profile', 'template', 'parser', 'learning'],
    },
  },
]
