# Phase 4 router integration

Add the router next to the existing Document Intelligence routers:

```python
from .cash_application.router import router as cash_application_router
```

Then include it through the module's existing registration mechanism.

Example parent-router approach:

```python
parent_router.include_router(cash_application_router)
```

Do not remove the Phase 1, Phase 2, or Phase 3 routers.
