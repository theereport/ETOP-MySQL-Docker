from core import module_config
from core.manifest import ModuleManifest

from .router import router

manifest = ModuleManifest(
    key="payment_notes",
    name="Payment Notes",
    version="0.1.0",
    enabled=module_config.is_enabled("payment_notes"),
    router=router,
    dependencies=("workflow_foundation",),
)
