# Architecture Decision Log

## ADR-001 — Modular monolith

**Status:** Approved

The platform will use a modular monolith before considering microservices. This is appropriate for a local workstation deployment while preserving strong module boundaries.

## ADR-002 — Module registry

**Status:** Approved

Backend modules are registered through manifests. Import or startup failures are captured as module errors rather than crashing the entire application.

## ADR-003 — Backward-compatible migration

**Status:** Approved

Existing routes remain active until the frontend is migrated and smoke-tested.

## ADR-004 — Deterministic controls around AI

**Status:** Approved

AI may assist extraction, classification, and interpretation, but accounting totals, SQL execution, and document outputs require deterministic validation.

## ADR-005 — `module_registry` is the canonical registration mechanism, not `ModuleManager`/kernel

**Status:** Approved

A full `ETOPKernel` / `ModuleManager` / `PlatformModule` / `discover_platform_modules` stack exists in `core/`, but `ModuleManager.start()` is all-or-nothing: one module's startup failure rolls back and aborts every other module, which contradicts Module Rule 4 ("optional module failure must not stop platform startup"). The lighter `core.module_registry.ModuleRegistry.register(app, module_path)` already isolates failures per module and was proven in production for `document_intelligence`. It is now used for every business module (`main.py` loops over each `modules.<name>` path). The kernel/`ModuleManager` stack is left in place, dormant, as a candidate for future lifecycle/health/event work, not routing — `test_fastapi_lifecycle.py::test_fastapi_uses_etop_kernel_lifecycle` is marked skipped with this rationale rather than left silently failing.

## ADR-006 — Runtime module on/off toggle

**Status:** Approved

Each module's router carries a per-request dependency (`core.module_config.require_module_enabled`) checking a small JSON-backed enabled/disabled flag (`backend/data/module_config.json`, default enabled). `POST /api/v1/modules/{key}/enable` and `/disable` flip it immediately — no restart required — and the choice persists across restarts. A manifest's `enabled` value only seeds the very first startup default; after that, the persisted operator choice wins.
