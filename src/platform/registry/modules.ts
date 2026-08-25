import type { PlatformSearchResult } from '../types'
import { moduleManifests } from './manifests'

// Derived from each module's own manifest.ts instead of a second
// hand-maintained list — this used to drift out of sync with App.tsx's
// module array (three modules were missing entirely).
export const platformSearchSeed: PlatformSearchResult[] = moduleManifests
  .filter((entry) => entry.search)
  .map((entry) => {
    const search = entry.search!
    return {
      id: search.id,
      type: 'module',
      title: search.title ?? entry.title,
      subtitle: search.subtitle,
      icon: typeof entry.icon === 'string' ? entry.icon : undefined,
      module: entry.title,
      keywords: search.keywords,
    }
  })
