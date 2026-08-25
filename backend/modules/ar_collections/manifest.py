from core import module_config
from core.manifest import ModuleManifest

from .router import router

manifest = ModuleManifest(
    key="ar_collections",
    name="AR Collections",
    version="0.1.0",
    enabled=module_config.is_enabled("ar_collections"),
    router=router,
    dependencies=("customer_360",),
)
