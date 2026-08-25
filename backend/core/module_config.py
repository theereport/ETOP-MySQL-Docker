"""Runtime enable/disable state for business modules.

Modules are enabled by default. Disabling a module is a live, per-request
toggle (via `require_module_enabled`) rather than a boot-time-only flag, so
turning a module off does not require restarting the platform. State is
persisted to a small JSON file so a disabled module stays disabled across
restarts until re-enabled.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from fastapi import HTTPException

from core.config import settings

_CONFIG_PATH = settings.data_root / "module_config.json"
_lock = threading.Lock()
_state: dict[str, bool] | None = None


def _load() -> dict[str, bool]:
    if not _CONFIG_PATH.exists():
        return {}

    try:
        raw = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    return {str(key): bool(value) for key, value in raw.items()}


def _save(state: dict[str, bool]) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def _get_state() -> dict[str, bool]:
    global _state

    if _state is None:
        _state = _load()

    return _state


def is_enabled(module_key: str) -> bool:
    """Modules default to enabled unless explicitly turned off."""

    with _lock:
        return _get_state().get(module_key, True)


def ensure_default(module_key: str, default: bool) -> None:
    """Seed a module's initial enabled state the first time it registers.
    A no-op once an explicit choice (via set_enabled) has been persisted, so
    a manifest's default never overwrites an operator's later decision."""

    with _lock:
        state = _get_state()
        if module_key not in state:
            state[module_key] = default
            _save(state)


def set_enabled(module_key: str, enabled: bool) -> None:
    with _lock:
        state = _get_state()
        state[module_key] = enabled
        _save(state)


def all_states() -> dict[str, bool]:
    with _lock:
        return dict(_get_state())


def require_module_enabled(module_key: str):
    """FastAPI dependency factory: gate every request to a module's router
    on its live enabled/disabled state, so toggling takes effect immediately
    rather than only at the next restart."""

    def _check() -> None:
        if not is_enabled(module_key):
            raise HTTPException(
                status_code=503,
                detail=f"Module '{module_key}' is disabled.",
            )

    return _check
