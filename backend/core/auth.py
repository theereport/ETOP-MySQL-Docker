"""Platform-Core auth contract.

Business modules that need to authenticate a caller depend on this module,
not on `modules.workflow_foundation` directly — `workflow_foundation` owns
the actual session/user implementation, but other modules should couple to
Platform Core, not to a sibling module's internals (Module Rule 2).
"""

from __future__ import annotations

from typing import Any

from modules.workflow_foundation.router import Token as Token
from modules.workflow_foundation.service import (
    WorkflowAuthenticationRequired as AuthenticationRequired,
)
from modules.workflow_foundation.service import (
    WorkflowPermissionDenied as PermissionDenied,
)
from modules.workflow_foundation.service import workflow_foundation_service

__all__ = [
    "AuthenticationRequired",
    "PermissionDenied",
    "Token",
    "actor_for_token",
    "session_for_token",
]


def session_for_token(token: str) -> dict[str, Any]:
    """Resolve the workflow session for an authenticated bearer token."""

    return workflow_foundation_service.session_for_token(token)


def actor_for_token(token: str) -> str:
    """Resolve the acting username for an authenticated bearer token."""

    user = session_for_token(token)["user"]
    return str(user.get("username") or user["user_id"])
