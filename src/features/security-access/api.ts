import {
  workflowRequest,
} from '../workflow-foundation/api'
import type {
  ETOPModuleId,
  WorkflowAuthResponse,
} from '../workflow-foundation/types'
import type {
  SecurityInvitation,
  SecurityInvitationCreate,
  SecurityInvitationCreateResponse,
  SecurityInvitationPreview,
  SecurityUser,
  SecurityUserList,
} from './types'

export function getSecurityUsers(signal?: AbortSignal): Promise<SecurityUserList> {
  return workflowRequest('/security/users', { signal })
}

export async function getSecurityInvitations(
  signal?: AbortSignal,
): Promise<SecurityInvitation[]> {
  const result = await workflowRequest<{ items: SecurityInvitation[] }>(
    '/security/invitations',
    { signal },
  )
  return result.items
}

export function createSecurityInvitation(
  payload: SecurityInvitationCreate,
): Promise<SecurityInvitationCreateResponse> {
  return workflowRequest('/security/invitations', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function revokeSecurityInvitation(
  invitationId: string,
): Promise<SecurityInvitation> {
  return workflowRequest(
    `/security/invitations/${encodeURIComponent(invitationId)}/revoke`,
    {
      method: 'POST',
      body: JSON.stringify({ expected_status: 'pending' }),
    },
  )
}

export function replaceSecurityUserModules(
  userId: string,
  moduleIds: ETOPModuleId[],
  expectedVersion: number,
): Promise<SecurityUser> {
  return workflowRequest(
    `/security/users/${encodeURIComponent(userId)}/modules`,
    {
      method: 'PUT',
      body: JSON.stringify({
        module_ids: moduleIds,
        expected_version: expectedVersion,
      }),
    },
  )
}

export function changeSecurityUserStatus(
  userId: string,
  status: 'active' | 'inactive',
  expectedVersion: number,
): Promise<SecurityUser> {
  return workflowRequest(
    `/security/users/${encodeURIComponent(userId)}/status`,
    {
      method: 'PATCH',
      body: JSON.stringify({ status, expected_version: expectedVersion }),
    },
  )
}

export function previewSecurityInvitation(
  token: string,
  signal?: AbortSignal,
): Promise<SecurityInvitationPreview> {
  return workflowRequest(
    '/invitations/preview',
    {
      method: 'POST',
      body: JSON.stringify({ token }),
      signal,
    },
    null,
  )
}

export function activateSecurityInvitation(
  token: string,
  password: string,
): Promise<WorkflowAuthResponse> {
  return workflowRequest(
    '/invitations/activate',
    {
      method: 'POST',
      body: JSON.stringify({ token, password }),
    },
    null,
  )
}
