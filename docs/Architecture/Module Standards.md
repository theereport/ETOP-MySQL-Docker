# Module Standards

Each backend module should contain:

```text
module_name/
├── __init__.py       # kept import-side-effect-free where practical (no FastAPI
│                      # import at package level) — manifest.py is the one file
│                      # allowed to require web dependencies
├── manifest.py        # required — see below
├── router.py           # required — HTTP surface (not api.py)
├── schemas.py
├── service.py          # a module's *public* surface for other modules to depend
│                        # on (Module Rule 1) — cross-module imports should reach
│                        # here, not into repository.py/internal engine files
├── repository.py
├── settings.py         # only if the module needs configurable paths/limits
└── README.md
```

`models.py`, `migrations/`, `tests/`, and `internal/` are optional, not
required — no module in this codebase has ever used them in practice. Data
models live inline in `schemas.py`; tests live at `backend/test_<module>.py`
top-level (the established convention); a real migrations framework is a
deliberate future decision, not a folder to create ahead of need. Manufacturing
empty files/folders to satisfy this checklist is exactly the scaffolding
problem this doc should help avoid.

**Every module's `manifest.py`** exports a `manifest: core.manifest.ModuleManifest`
(`key`, `name`, `version`, `enabled`, `router`, `dependencies`). `enabled`
should read from `core.module_config.is_enabled(key)` so the module can be
turned on/off at runtime without a code change or restart (see ADR-006).
Registration happens once, in `main.py`, via
`core.module_registry.module_registry.register(app, "modules.<name>")` —
never `app.include_router(...)` directly for a business module (see ADR-005).

**Cross-module dependencies** (Module Rule 2) should reach a module's
`service.py` public singleton/functions, or a Platform-Core facade (like
`core.auth` for authentication) — never another module's `repository.py`,
internal engine files, or router-layer implementation details.

Each frontend module should contain:

```text
module-name/
├── manifest.ts
├── api.ts
├── types.ts
├── index.ts          # barrel: exports the top-level component + its props type
├── pages/
├── components/
└── tests/
```

`routes.tsx` is not part of the current pattern — there is no router library
in this frontend today (routing is manual state-based view-switching in
`App.tsx`); introducing one is a deliberate future decision, not assumed here.
