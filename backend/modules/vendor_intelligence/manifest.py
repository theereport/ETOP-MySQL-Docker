from core import module_config
from core.manifest import ModuleManifest

from .router import router

manifest = ModuleManifest(
    key="vendor_intelligence",
    name="Vendor Intelligence",
    version="0.1.0",
    enabled=module_config.is_enabled("vendor_intelligence"),
    router=router,
    dependencies=(),
)
