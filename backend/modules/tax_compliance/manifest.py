from core import module_config
from core.manifest import ModuleManifest

from .router import router

manifest = ModuleManifest(
    key="tax_compliance",
    name="Tax Compliance",
    version="0.1.0",
    enabled=module_config.is_enabled("tax_compliance"),
    router=router,
    dependencies=(),
)
