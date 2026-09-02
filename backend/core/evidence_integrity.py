"""Shared verification for the "stored evidence snapshot + its own SHA-256"
pattern repeated across this codebase's notes/assessment repositories: a row
carries a JSON blob and a hash computed over it at write time; reading it
back recomputes the hash and raises a module-specific integrity error on
mismatch (append-only evidence must never be silently corrupted).

This only ever recomputes a hash over the JSON text already stored in the
row - it never re-serializes the original Python value - so it is safe to
use regardless of which json.dumps() parameters a given module's write path
happens to use; those don't need to match across modules for this check to
be correct.
"""

from __future__ import annotations

import hashlib


def verify_snapshot_hash(
    snapshot_json: str,
    expected_hash: str,
    *,
    error: type[Exception],
    message: str,
) -> None:
    """Raises `error(message)` if `expected_hash` doesn't match the SHA-256
    of `snapshot_json` as stored."""

    actual_hash = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
    if actual_hash != expected_hash:
        raise error(message)
