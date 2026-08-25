from dataclasses import asdict, dataclass
from importlib import import_module
from typing import Any

from fastapi import Depends, FastAPI

from core import module_config


@dataclass
class ModuleStatus:
    key: str
    name: str
    version: str
    enabled: bool
    state: str
    message: str
    dependencies: tuple[str, ...] = ()


class ModuleRegistry:
    def __init__(self) -> None:
        self._statuses: dict[str, ModuleStatus] = {}

    def register(self, app: FastAPI, module_path: str) -> None:
        try:
            # Import the `manifest` submodule directly rather than the
            # package's `__init__.py` — several modules (e.g. payment_notes)
            # deliberately keep their package import side-effect/web-dependency
            # free, so the manifest (which needs FastAPI to build its router)
            # is only pulled in here, where it's actually needed.
            manifest_module = import_module(f"{module_path}.manifest")
            manifest = manifest_module.manifest

            # The manifest's `enabled` value only seeds the first-ever
            # startup default; the live on/off state lives in module_config
            # from then on, so a later toggle doesn't need a restart.
            module_config.ensure_default(manifest.key, manifest.enabled)

            app.include_router(
                manifest.router,
                dependencies=[
                    Depends(module_config.require_module_enabled(manifest.key)),
                ],
            )

            enabled = module_config.is_enabled(manifest.key)

            self._statuses[manifest.key] = ModuleStatus(
                key=manifest.key,
                name=manifest.name,
                version=manifest.version,
                enabled=enabled,
                state="healthy" if enabled else "disabled",
                message=(
                    "Module loaded successfully."
                    if enabled
                    else "Module is disabled."
                ),
                dependencies=manifest.dependencies,
            )

        except Exception as exc:
            fallback_key = module_path.rsplit(".", 1)[-1]
            self._statuses[fallback_key] = ModuleStatus(
                key=fallback_key,
                name=fallback_key.replace("_", " ").title(),
                version="unknown",
                enabled=True,
                state="failed",
                message=f"Module failed to load: {exc}",
            )

    def list_statuses(self) -> list[dict[str, Any]]:
        return [asdict(status) for status in self._statuses.values()]

    def summary(self) -> dict[str, int]:
        values = list(self._statuses.values())
        return {
            "total": len(values),
            "healthy": sum(x.state == "healthy" for x in values),
            "degraded": sum(x.state == "degraded" for x in values),
            "failed": sum(x.state == "failed" for x in values),
            "disabled": sum(x.state == "disabled" for x in values),
        }


module_registry = ModuleRegistry()
