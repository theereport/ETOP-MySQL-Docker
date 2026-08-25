from core import module_config
from core.manifest import ModuleManifest

from .router import search_router

manifest = ModuleManifest(
    key="platform_search",
    name="Platform Search",
    version="0.1.0",
    enabled=module_config.is_enabled("platform_search"),
    router=search_router,
    dependencies=(),
)
