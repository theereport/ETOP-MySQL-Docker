from fastapi import APIRouter, Query

from .registry import MODULES
from .schemas import (
    HealthData,
    HealthResponse,
    ModuleRecord,
    RegistryData,
    RegistryResponse,
    SearchData,
    SearchResponse,
)
from .service import search_registry

router = APIRouter(
    prefix="/api/v1/platform",
    tags=["ETOP Platform"],
)

# The main ETOP application already owns /api/v1/platform/health.
# Register this focused router there so Enterprise Search is added
# without creating a second health route.
search_router = APIRouter(
    prefix="/api/v1/platform",
    tags=["ETOP Platform Search"],
)


@router.get("/health", response_model=HealthResponse)
def platform_health() -> HealthResponse:
    return HealthResponse(
        data=HealthData(
            status="healthy",
            local_only=True,
            read_only_erp=True,
            capabilities=[
                "global-search",
                "registry-v2",
                "shared-intelligence-ui",
                "universal-entity-framework",
            ],
        )
    )


@router.get("/registry", response_model=RegistryResponse)
def platform_registry() -> RegistryResponse:
    return RegistryResponse(
        data=RegistryData(
            platform_version="0.6.0",
            release="Sprint 4A — Platform Core",
            modules=[
                ModuleRecord(
                    id=module["id"],
                    title=module["title"],
                    version=module["version"],
                    status=module["status"],
                    capabilities=module["capabilities"],
                )
                for module in MODULES
            ],
        )
    )


@router.get("/search", response_model=SearchResponse)
@search_router.get("/search", response_model=SearchResponse)
def enterprise_search(
    q: str = Query(min_length=1, max_length=200),
) -> SearchResponse:
    results = search_registry(q)

    return SearchResponse(
        data=SearchData(
            query=q,
            count=len(results),
            results=results,
        )
    )
