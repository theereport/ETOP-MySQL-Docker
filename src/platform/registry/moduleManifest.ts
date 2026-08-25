import type { ReactNode } from 'react'

export type ModuleGroup = 'Overview' | 'Workspaces' | 'Tools' | 'System'
export type ModuleStatus = 'Ready' | 'Coming Soon'

/**
 * Single source of truth for a module's nav/sidebar metadata and (optionally)
 * its search-index entry. Each feature module owns one of these in its own
 * `manifest.ts` instead of App.tsx and platform/registry/modules.ts each
 * hand-maintaining a separate, independently-drifting copy.
 */
export type ModuleManifestEntry = {
  moduleId?: string
  title: string
  shortTitle: string
  description: string
  hint: string
  group: ModuleGroup
  /**
   * Optional sub-heading within `group` for the sidebar (e.g. "AR /
   * Receivables"). Modules sharing a category render under one collapsible
   * header instead of the group's flat list. Omit to keep a module directly
   * under its group with no sub-heading.
   */
  category?: string
  status: ModuleStatus
  icon: ReactNode
  showInSidebar?: boolean
  /** Omit if this module isn't (yet) surfaced in command search. */
  search?: {
    id: string
    title?: string
    subtitle: string
    keywords: string[]
  }
}
