# Reports

Saved SQL report definitions (name, category, SQL text, output format) with
CRUD endpoints under `/api/v1/reports`.

- `router.py` — HTTP surface.
- `service.py` — persistence logic, including `initialize_reports_database()`,
  the module's own DDL (owns the `reports` table and its indexes).
- `schemas.py` — request/response models.
- `manifest.py` — registration entry point (`modules.reports.manifest.manifest`),
  consumed by `core.module_registry`.
