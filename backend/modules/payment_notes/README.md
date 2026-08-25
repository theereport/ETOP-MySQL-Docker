# Payment Notes

R73 Payment Notes evidence and reconciliation workspace: route references,
run history, and review workflow.

- `router.py` — HTTP surface.
- `service.py` — reconciliation/review logic; depends on
  `workflow_foundation`'s `WorkflowFoundationService` singleton as a service
  contract for identity/session data.
- `remote_capture.py`, `route_reference.py`, `repository.py` — supporting
  persistence/capture logic.
- `manifest.py` — registration entry point
  (`modules.payment_notes.manifest.manifest`).

Importing the bare package (`modules.payment_notes`) stays side-effect and
web-dependency free by design — only `manifest.py` (and the modules it pulls
in) require FastAPI. Authentication comes from `core.auth`, not directly
from `modules.workflow_foundation`.
