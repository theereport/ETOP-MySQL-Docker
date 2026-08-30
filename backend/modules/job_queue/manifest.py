from core import module_config
from core.manifest import ModuleManifest

from .router import router

manifest = ModuleManifest(
    key="job_queue",
    name="Job Queue",
    version="0.1.0",
    enabled=module_config.is_enabled("job_queue"),
    router=router,
    dependencies=(),
)
