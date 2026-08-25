from __future__ import annotations

import os
from http.cookies import SimpleCookie
from typing import Any

from starlette.responses import JSONResponse

from .access_policy import required_modules_for_path
from .service import (
    WorkflowAuthenticationRequired,
    WorkflowPermissionDenied,
    workflow_foundation_service,
)


def _session_token_from_scope(scope: dict[str, Any]) -> str | None:
    cookie_header: str | None = None
    for raw_name, raw_value in scope.get("headers", []):
        name = raw_name.lower()
        value = raw_value.decode("latin-1")
        if name == b"authorization":
            if not value.startswith("Bearer "):
                return None
            token = value.removeprefix("Bearer ").strip()
            return token or None
        if name == b"cookie":
            cookie_header = value
    if cookie_header:
        cookies = SimpleCookie()
        cookies.load(cookie_header)
        morsel = cookies.get(os.getenv("ETOP_COOKIE_NAME", "etop_local_session"))
        if morsel is not None:
            return morsel.value or None
    return None


class ModuleAccessMiddleware:
    """Server-side module authorization for every current ETOP API surface."""

    def __init__(self, app: Any, authorization_service: Any = None) -> None:
        self.app = app
        self.authorization_service = (
            authorization_service or workflow_foundation_service
        )

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        required = required_modules_for_path(str(scope.get("path", "/")))
        if required is None:
            await self.app(scope, receive, send)
            return
        if not required:
            response = JSONResponse(
                status_code=403,
                content={
                    "detail": {
                        "code": "module_access_unmapped",
                        "message": (
                            "This API route is not registered to an ETOP module. "
                            "Access is denied by default."
                        ),
                    }
                },
            )
            await response(scope, receive, send)
            return

        token = _session_token_from_scope(scope)
        if not token:
            response = JSONResponse(
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
                content={
                    "detail": {
                        "code": "workflow_authentication_required",
                        "message": "Sign in to this local ETOP instance.",
                    }
                },
            )
            await response(scope, receive, send)
            return
        try:
            self.authorization_service.authorize_module_access(token, required)
        except WorkflowAuthenticationRequired as exc:
            response = JSONResponse(
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
                content={
                    "detail": {
                        "code": "workflow_authentication_required",
                        "message": str(exc),
                    }
                },
            )
            await response(scope, receive, send)
            return
        except WorkflowPermissionDenied as exc:
            response = JSONResponse(
                status_code=403,
                content={
                    "detail": {
                        "code": "module_access_denied",
                        "message": str(exc),
                        "required_any": list(required),
                    }
                },
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


__all__ = ["ModuleAccessMiddleware", "required_modules_for_path"]
