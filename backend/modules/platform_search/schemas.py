from typing import Any, Literal

from pydantic import BaseModel, Field


class Metadata(BaseModel):
    source: str = "ETOP Platform Core"
    version: str = "0.6.0"


class SearchResult(BaseModel):
    id: str
    type: str
    title: str
    subtitle: str
    module: str
    score: float = Field(ge=0, le=1)
    action: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchData(BaseModel):
    query: str
    count: int
    results: list[SearchResult]


class SearchResponse(BaseModel):
    success: bool = True
    data: SearchData
    errors: list[dict[str, Any]] = Field(default_factory=list)
    metadata: Metadata = Field(default_factory=Metadata)


class ModuleRecord(BaseModel):
    id: str
    title: str
    version: str
    status: Literal["Ready", "Coming Soon", "Degraded"]
    capabilities: list[str]


class RegistryData(BaseModel):
    platform_version: str
    release: str
    modules: list[ModuleRecord]


class RegistryResponse(BaseModel):
    success: bool = True
    data: RegistryData
    errors: list[dict[str, Any]] = Field(default_factory=list)
    metadata: Metadata = Field(default_factory=Metadata)


class HealthData(BaseModel):
    status: Literal["healthy", "degraded"]
    local_only: bool
    read_only_erp: bool
    capabilities: list[str]


class HealthResponse(BaseModel):
    success: bool = True
    data: HealthData
    errors: list[dict[str, Any]] = Field(default_factory=list)
    metadata: Metadata = Field(default_factory=Metadata)
