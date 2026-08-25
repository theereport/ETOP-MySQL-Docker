from __future__ import annotations

import re


PNC_LOCKBOX_HEADER_RULE_VERSION = (
    "pnc-lockbox-site-header@0.7.0-wave2-increment3y"
)
PNC_LOCKBOX_IDENTIFIER_PATTERN = r"[A-Z]{3}-\d+"
PNC_LOCKBOX_IDENTIFIER_RE = re.compile(
    rf"\b{PNC_LOCKBOX_IDENTIFIER_PATTERN}\b",
    re.IGNORECASE,
)
