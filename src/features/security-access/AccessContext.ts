import { createContext, useContext } from 'react'
import type {
  ETOPModuleId,
  WorkflowSession,
} from '../workflow-foundation/types'

export type AccessContextValue = {
  session: WorkflowSession
  canAccess: (moduleId: ETOPModuleId) => boolean
  refreshAccess: () => Promise<void>
  signOut: () => Promise<void>
}

export const AccessContext = createContext<AccessContextValue | null>(null)

export function useAccess(): AccessContextValue {
  const value = useContext(AccessContext)
  if (!value) throw new Error('useAccess must be used inside AccessProvider.')
  return value
}
