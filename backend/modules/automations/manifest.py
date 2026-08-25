from fastapi import APIRouter

from core import module_config
from core.manifest import ModuleManifest

from .router import router as automations_router

module_router = APIRouter(prefix="/api/v1")
module_router.include_router(automations_router)

manifest = ModuleManifest(
    key="automations",
    name="Automation Center",
    version="0.1.0",
    enabled=module_config.is_enabled("automations"),
    router=module_router,
    dependencies=(),
)
