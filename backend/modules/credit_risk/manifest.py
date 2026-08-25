from core import module_config
from core.manifest import ModuleManifest

from .router import router

manifest = ModuleManifest(
    key="credit_risk",
    name="Credit Risk",
    version="0.1.0",
    enabled=module_config.is_enabled("credit_risk"),
    router=router,
    dependencies=("customer_360", "document_intelligence"),
)
