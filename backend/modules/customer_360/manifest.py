from core import module_config
from core.manifest import ModuleManifest

from .router import router

manifest = ModuleManifest(
    key="customer_360",
    name="Customer 360",
    version="0.3.0",
    enabled=module_config.is_enabled("customer_360"),
    router=router,
    dependencies=(),
)
