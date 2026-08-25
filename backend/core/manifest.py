"""Shared manifest contract every business module's `manifest.py` uses.

This is the Platform-Core-owned type consumed by `core.module_registry`,
so every module declares its identity/router/dependencies the same way
instead of each defining its own local dataclass.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter


@dataclass(frozen=True)
class ModuleManifest:
    key: str
    name: str
    version: str
    enabled: bool
    router: APIRouter
    dependencies: tuple[str, ...] = ()
