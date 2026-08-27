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

## ADR-007 — Manual enterprise-customer linking merges with, never replaces, ERP CUNUMENT grouping

**Status:** Approved

`TMCUST.CUNUMENT` is the ERP's own evidence that two customer accounts pay together, but K&M reviewers know of joint-payment relationships the ERP never recorded (no CUNUMENT set), and an ERP-linked account can *also* turn out to jointly pay with a third, non-ERP-linked customer. Rather than treat "has a CUNUMENT group" and "reviewer manually linked" as mutually exclusive, `customer_match.linked_customer_accounts` computes both sets independently and unions them; the response discloses which evidence contributed via `source: "erp" | "manual" | "mixed"`. The manual side is a small local SQLite table (`manual_enterprise_group_repository.py`) that only ever *adds* candidate accounts to toggle through — it carries no authority to remove or override an ERP CUNUMENT relationship, and unlinking a customer only ever removes its own manual-group row.

## ADR-008 — Misc G/L Entry participates in balance math but never becomes an allocation row

**Status:** Approved

A waived service charge or similar write-off needs to close the gap between a check's amount and its ERP invoice allocations, but it is not itself an ERP open-item allocation and must never be persisted or exported as one. `lockbox_review` therefore tracks it as a distinct `misc_gl` field on the transaction record — reason (from a fixed, server-validated `MISC_GL_REASON_CODES` map, never a client-submitted GL code), location, department, amount — and subtracts its amount when computing `difference`/`balanced` alongside `allocation_total`, without adding a row to `allocations`. It exports to its own `misc_gl` workbook tab rather than the invoice-allocation detail sheet, so downstream posting never mistakes a write-off for an invoice.
