import type {
  ETOPModuleId,
  EffectivePermissions,
  WorkflowRoleId,
  WorkflowUser,
} from '../workflow-foundation/types'

export type SecurityModule = {
  module_id: ETOPModuleId
  name: string
  description: string
  group: 'Overview' | 'Workspaces' | 'Tools' | 'System'
  default_access: false
  status: 'active'
  authority_effect: 'none'
}

export type SecurityUser = {
  user: WorkflowUser
  configured_module_ids: ETOPModuleId[]
  permissions: EffectivePermissions
  access_version: number
  status_version: number
}

export type SecurityUserList = {
  users: SecurityUser[]
  modules: SecurityModule[]
  authority_boundary: string
}

export type SecurityInvitation = {
  invitation_id: string
  username: string
  display_name: string
  role_ids: WorkflowRoleId[]
  module_ids: ETOPModuleId[]
  status: 'pending' | 'activated' | 'revoked' | 'expired'
  created_by_user_id: string
  created_at: string
  expires_at: string
  activated_at: string | null
  activated_user_id: string | null
}

export type SecurityInvitationCreateResponse = SecurityInvitation & {
  invitation_link: string
  link_displayed_once: true
}

export type SecurityInvitationPreview = {
  username: string
  display_name: string
  expires_at: string
  status: 'pending'
}

export type SecurityInvitationCreate = {
  username: string
  display_name: string
  role_ids: WorkflowRoleId[]
  module_ids: ETOPModuleId[]
  expires_in_hours: number
}
