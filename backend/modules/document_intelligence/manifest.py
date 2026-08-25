from fastapi import APIRouter

from core import module_config
from core.manifest import ModuleManifest

from .phase3.router import router as phase3_router
from .router import router as document_router
from .settings import settings
from .cash_application.router import router as cash_application_router
from .lockbox_review.router import router as lockbox_review_router
from .lockbox_preparation.router import router as lockbox_preparation_router

module_router = APIRouter()

module_router.include_router(document_router)
module_router.include_router(phase3_router)
module_router.include_router(cash_application_router)
module_router.include_router(lockbox_review_router)
module_router.include_router(lockbox_preparation_router)

manifest = ModuleManifest(
    key=settings.module_key,
    name="Document Intelligence",
    version=settings.module_version,
    enabled=module_config.is_enabled(settings.module_key),
    router=module_router,
    dependencies=("core",),
)
