from core import module_config
from core.manifest import ModuleManifest

from .router import router

manifest = ModuleManifest(
    key="general_ledger",
    name="General Ledger",
    version="0.1.0",
    enabled=module_config.is_enabled("general_ledger"),
    router=router,
    dependencies=(),
)
