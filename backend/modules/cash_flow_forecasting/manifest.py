from core import module_config
from core.manifest import ModuleManifest

from .router import router

manifest = ModuleManifest(
    key="cash_flow_forecasting",
    name="Cash Flow Forecasting",
    version="0.1.0",
    enabled=module_config.is_enabled("cash_flow_forecasting"),
    router=router,
    dependencies=(),
)
