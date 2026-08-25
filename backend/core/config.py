from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PlatformSettings:
    app_name: str = "Enterprise AI Workbench API"
    app_version: str = "0.3.0"
    api_prefix: str = "/api/v1"

    project_root: Path = Path(__file__).resolve().parents[2]
    backend_root: Path = Path(__file__).resolve().parents[1]

    @property
    def data_root(self) -> Path:
        return self.project_root / "data"


settings = PlatformSettings()
