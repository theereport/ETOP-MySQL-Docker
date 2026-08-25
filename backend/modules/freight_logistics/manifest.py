from core import module_config
from core.manifest import ModuleManifest

from .router import router

manifest = ModuleManifest(
    key="freight_logistics",
    name="Freight & Logistics",
    version="0.1.0",
    enabled=module_config.is_enabled("freight_logistics"),
    router=router,
    dependencies=(),
)
