"""Authenticated, test-only filesystem overrides for import-time path owners."""

from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path


_PACKAGE_ID = "ETOP-0.7.0-TEST-ENVIRONMENT-LIFECYCLE-1"


def _absolute_lexical(path: Path) -> Path:
    return Path(os.path.abspath(os.path.normpath(os.fspath(path))))


def _is_reparse(path: Path, metadata: os.stat_result) -> bool:
    attributes = int(getattr(metadata, "st_file_attributes", 0))
    reparse_attribute = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))
    is_junction = getattr(path, "is_junction", lambda: False)
    return stat.S_ISLNK(metadata.st_mode) or bool(
        attributes & reparse_attribute
    ) or bool(is_junction())


def _assert_existing_chain_has_no_reparse(path: Path, *, require_all: bool) -> None:
    absolute = _absolute_lexical(path)
    current = Path(absolute.anchor)
    parts = absolute.parts[1:] if absolute.anchor else absolute.parts
    for part in parts:
        current /= part
        if not os.path.lexists(current):
            if require_all:
                raise RuntimeError(f"Required isolated path is missing: {current}")
            return
        metadata = os.lstat(current)
        if _is_reparse(current, metadata):
            raise RuntimeError(f"Reparse path is forbidden in ETOP test paths: {current}")


def _strict_marker_json(marker_path: Path) -> dict:
    metadata = os.lstat(marker_path)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or _is_reparse(marker_path, metadata)
        or int(getattr(metadata, "st_nlink", 1)) > 1
    ):
        raise RuntimeError("ETOP test marker is not an ordinary unique file.")

    def unique_object(pairs: list[tuple[str, object]]) -> dict:
        value: dict = {}
        for key, item in pairs:
            if key in value:
                raise RuntimeError(f"Duplicate ETOP marker key: {key}")
            value[key] = item
        return value

    return json.loads(
        marker_path.read_text(encoding="utf-8"),
        object_pairs_hook=unique_object,
        parse_constant=lambda value: (_ for _ in ()).throw(
            RuntimeError(f"Non-finite ETOP marker value: {value}")
        ),
    )


def resolve_test_path_override(
    environment_name: str,
    default: str | Path,
    *,
    kind: str = "file",
) -> Path:
    raw = os.getenv(environment_name, "").strip()
    if not raw:
        return Path(default).expanduser()
    if kind not in {"file", "directory"}:
        raise RuntimeError(f"Unknown ETOP test path kind: {kind}")

    environment_id = os.getenv("ETOP_TEST_ENVIRONMENT_ID", "").strip()
    root_raw = os.getenv("ETOP_TEST_ROOT", "").strip()
    if not root_raw or not re.fullmatch(r"ETOP-TEST-[0-9a-f]{32}", environment_id):
        raise RuntimeError(
            f"{environment_name} requires an exact ETOP isolated environment identity."
        )

    test_root = Path(root_raw).expanduser()
    candidate = Path(raw).expanduser()
    if not test_root.is_absolute() or not candidate.is_absolute():
        raise RuntimeError(f"{environment_name} must be an absolute test path.")
    test_root = _absolute_lexical(test_root)
    candidate = _absolute_lexical(candidate)
    _assert_existing_chain_has_no_reparse(test_root, require_all=True)
    marker_path = test_root / ".etop-test-environment.json"
    if not os.path.lexists(marker_path):
        raise RuntimeError(f"{environment_name} requires the ETOP test marker.")
    _assert_existing_chain_has_no_reparse(marker_path, require_all=True)
    marker = _strict_marker_json(marker_path)
    if not isinstance(marker, dict):
        raise RuntimeError("ETOP test marker must be a JSON object.")
    marker_root_raw = marker.get("test_root")
    marker_root_valid = (
        isinstance(marker_root_raw, str)
        and bool(marker_root_raw.strip())
        and Path(marker_root_raw).is_absolute()
    )
    if (
        type(marker.get("schema_version")) is not int
        or marker.get("schema_version") != 1
        or marker.get("package_id") != _PACKAGE_ID
        or marker.get("environment_id") != environment_id
        or not marker_root_valid
        or _absolute_lexical(Path(marker_root_raw)) != test_root
    ):
        raise RuntimeError(f"{environment_name} test marker identity differs.")

    try:
        candidate.relative_to(test_root)
    except ValueError as exc:
        raise RuntimeError(
            f"{environment_name} escapes ETOP_TEST_ROOT: {candidate}"
        ) from exc
    if candidate == test_root:
        raise RuntimeError(f"{environment_name} cannot bind the ETOP test root itself.")
    _assert_existing_chain_has_no_reparse(candidate.parent, require_all=False)
    if os.path.lexists(candidate):
        _assert_existing_chain_has_no_reparse(candidate, require_all=True)
        metadata = os.lstat(candidate)
        expected_type = (
            stat.S_ISREG(metadata.st_mode)
            if kind == "file"
            else stat.S_ISDIR(metadata.st_mode)
        )
        if not expected_type or (
            kind == "file" and int(getattr(metadata, "st_nlink", 1)) > 1
        ):
            raise RuntimeError(
                f"{environment_name} existing target has an unsafe file identity."
            )
    if kind == "file":
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = Path(str(candidate) + suffix)
            if not os.path.lexists(sidecar):
                continue
            _assert_existing_chain_has_no_reparse(sidecar, require_all=True)
            metadata = os.lstat(sidecar)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or int(getattr(metadata, "st_nlink", 1)) > 1
            ):
                raise RuntimeError(
                    f"{environment_name} SQLite sidecar has an unsafe file identity."
                )
    return candidate
