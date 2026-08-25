# Workflow Foundation

Owns local identity, sessions, roles, task assignment, and audit for the
platform — the module every other module depends on for authentication.

- `router.py` — HTTP surface (bootstrap, sessions, users, roles, tasks,
  notifications, audit).
- `service.py` — `WorkflowFoundationService`; session/token verification,
  user/role/task/notification/audit logic.
- `access_control.py` / `access_policy.py` — the platform-wide
  `ModuleAccessMiddleware`, mapping every API path to the module grant(s)
  required to call it.
- `manifest.py` — registration entry point
  (`modules.workflow_foundation.manifest.manifest`).

Other modules that need to authenticate a caller should depend on
`core.auth` (a Platform-Core facade over this module), not import
`modules.workflow_foundation` internals directly — see
`docs/Architecture/Architecture Decisions.md` ADR-005/006.
