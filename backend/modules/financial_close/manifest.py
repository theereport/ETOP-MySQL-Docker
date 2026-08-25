from core import module_config
from core.manifest import ModuleManifest

from .router import router

manifest = ModuleManifest(
    key="financial_close",
    name="Financial Close",
    version="0.1.0",
    enabled=module_config.is_enabled("financial_close"),
    router=router,
    dependencies=("workflow_foundation",),
)
