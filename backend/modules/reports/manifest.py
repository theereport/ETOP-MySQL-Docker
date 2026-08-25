from fastapi import APIRouter

from core import module_config
from core.manifest import ModuleManifest

from .router import router as reports_router

module_router = APIRouter(prefix="/api/v1")
module_router.include_router(reports_router)

manifest = ModuleManifest(
    key="reports",
    name="Reports",
    version="0.1.0",
    enabled=module_config.is_enabled("reports"),
    router=module_router,
    dependencies=(),
)
