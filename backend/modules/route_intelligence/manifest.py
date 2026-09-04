from core import module_config
from core.manifest import ModuleManifest

from .router import router

manifest = ModuleManifest(
    key="route_intelligence",
    name="Route Intelligence",
    version="0.1.0",
    enabled=module_config.is_enabled("route_intelligence"),
    router=router,
    dependencies=("freight_logistics",),
)
