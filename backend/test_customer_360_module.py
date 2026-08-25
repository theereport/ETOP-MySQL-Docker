def test_customer_360_routes_are_registered_once() -> None:
    with TestClient(app) as client:
        route_paths = [
            route.path
            for route in app.routes
            if hasattr(route, "path")
        ]

        assert route_paths.count("/api/v1/customers") == 1
        assert route_paths.count("/api/v1/customers/search") == 1
        assert (
            route_paths.count(
                "/api/v1/customers/{customer_number}"
            )
            == 1
        )

        response = client.get(
            "/api/v1/customers",
            params={
                "search": "",
                "limit": 1,
            },
        )

        assert response.status_code not in {
            404,
            405,
        }