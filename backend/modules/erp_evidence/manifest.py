from core import module_config
from core.manifest import ModuleManifest

from .router import router

manifest = ModuleManifest(
    key="erp_evidence",
    name="ERP Evidence Gateway",
    version="0.1.0",
    enabled=module_config.is_enabled("erp_evidence"),
    router=router,
    dependencies=("accounts_payable", "customer_360"),
)
