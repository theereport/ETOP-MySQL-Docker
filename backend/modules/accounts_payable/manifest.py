from core import module_config
from core.manifest import ModuleManifest

from .router import router

manifest = ModuleManifest(
    key="accounts_payable",
    name="Accounts Payable",
    version="0.1.0",
    enabled=module_config.is_enabled("accounts_payable"),
    router=router,
    dependencies=("document_intelligence",),
)
