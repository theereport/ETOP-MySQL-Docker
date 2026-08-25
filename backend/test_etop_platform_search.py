from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.platform_search.router import search_router
from modules.platform_search.service import search_registry


def test_registry_search_handles_multi_word_queries() -> None:
    results = search_registry("high risk customers")

    assert results
    assert results[0].action == "Customer 360"


def test_registry_search_opens_dedicated_credit_risk_module() -> None:
    results = search_registry("credit risk")

    assert results
    assert results[0].action == "Credit Risk"
    assert not any(
        result.action == "Credit Risk"
        for result in search_registry("high risk customers")
    )


def test_registry_search_includes_document_intelligence() -> None:
    results = search_registry("lockbox")

    assert any(
        result.action == "Document Intelligence"
        for result in results
    )


def test_registry_search_opens_payment_notes_module() -> None:
    results = search_registry("payment notes")

    assert results
    assert results[0].action == "Payment Notes"


def test_search_router_is_registered_without_health_duplicate() -> None:
    app = FastAPI()
    app.include_router(search_router)

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/platform/search",
            params={"q": "SOP"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["count"] >= 1
    assert any(
        result["action"] == "SOP Search"
        for result in payload["data"]["results"]
    )
    route_paths = [
        route.path
        for route in app.routes
        if hasattr(route, "path")
    ]
    assert "/api/v1/platform/health" not in route_paths
