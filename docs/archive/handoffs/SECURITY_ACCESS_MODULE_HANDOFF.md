# Security & User Access Module Handoff

**Date:** August 13, 2026  
**Baseline:** R6 candidate `ebc8ac664305b2895c005ea15181c52265776f914e0aebfca6044922fa9095e4`  
**Lockbox evaluation overlay:** `cc039d8debe3099a370748d3156248f90862bc1b0c3397e4ba8d5bedd01a3059`

## Delivered behavior

- Extends Workflow Foundation accounts, roles, credentials, and sessions; no
  parallel authentication implementation.
- First bootstrap administrator receives every currently registered module.
- Security administrators create expiring single-use invitation links, revoke
  pending invitations, view users, suspend/reactivate accounts, and toggle all
  current ETOP modules per person.
- Only a Workflow Coordinator with explicit `security_administration` access
  can perform security administration, including the legacy direct user route.
- Effective permissions are exposed on login/current-session responses and
  drive shell navigation, commands, dashboard launchers, and protected routes.
- Backend middleware independently enforces all current FastAPI routes (174 in
  the isolated verification snapshot). Unknown application routes and newly
  registered modules fail closed.
- Invitation tokens are shown once and stored only as SHA-256 hashes. Session
  tokens are hashed at rest; test instances may HMAC them with an ephemeral
  `ETOP_SESSION_SIGNING_SECRET` and `ETOP_SESSION_NAMESPACE`.
- Access/lifecycle/invitation evidence is append-only and included in the
  existing hash-chained audit. Module access grants no financial authority.

## Test-environment configuration

Set `ETOP_APP_URL` to the exact frontend URL. Optional isolation controls are
`ETOP_COOKIE_NAME`, `ETOP_COOKIE_DOMAIN`, `ETOP_SESSION_SIGNING_SECRET` (at
least 32 characters), and `ETOP_SESSION_NAMESPACE`. When `VITE_API_BASE_URL` is
configured, the browser attaches the bearer token only to that origin and
rewrites legacy hard-coded local port-8000 calls to that configured backend.

## Known bounded gaps

- Local-first credentials are not enterprise SSO or account recovery.
- Shared Document Intelligence routes use an any-consuming-module admission
  rule; per-document/job authorization is not implemented.
- Roles are chosen at invitation/account creation; effective-dated role-change
  administration remains deferred.
- This source increment does not create an installer/release artifact or claim
  production acceptance. Merge and full retained release verification remain
  integration-owner steps.
