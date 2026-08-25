# Financial Close

Controller intelligence readiness: close cycles, templates, controls, and
manual planning operations.

- `router.py` — HTTP surface.
- `service.py` — close-cycle/control/template logic; depends on
  `workflow_foundation`'s `WorkflowFoundationService` singleton as a service
  contract for identity/session data.
- `repository.py` — persistence.
- `manifest.py` — registration entry point
  (`modules.financial_close.manifest.manifest`).

Authentication (`Token`, auth exceptions) comes from `core.auth`, not
directly from `modules.workflow_foundation` — see
`docs/Architecture/Architecture Decisions.md` ADR-005/006.
