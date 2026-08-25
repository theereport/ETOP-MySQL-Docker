from core import module_config
from core.manifest import ModuleManifest

from .router import router

manifest = ModuleManifest(
    key="sales_order_visibility",
    name="Sales Order Visibility",
    version="0.1.0",
    enabled=module_config.is_enabled("sales_order_visibility"),
    router=router,
    dependencies=(),
)
