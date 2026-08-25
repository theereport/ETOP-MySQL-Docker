# Sprint 1 — Platform Foundation

## Objective

Introduce modular infrastructure without breaking existing endpoints.

## Work items

- Add `backend/core/config.py`
- Add `backend/core/module_registry.py`
- Add `backend/core/health.py`
- Add Document Intelligence manifest and router
- Register modules from the existing `main.py`
- Confirm all legacy endpoints still work
- Confirm startup succeeds when Document Intelligence is disabled

## Acceptance checks

- `/health` still works
- `/knowledge/status` still works
- Existing SQL endpoints still work
- `/api/v1/modules` returns module status
- `/api/v1/documents/health` returns healthy
