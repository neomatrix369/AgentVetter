"""Redact secret-looking values from evidence text before it is stored.

Scanned third-party code can contain real credentials. Finding snippets and
scanner console output are written to Supabase, where the dashboard's anon key
can read them. The CLI masks these values only when printing, so the sandbox
masks them at write time too. The rules mirror ``cli/src/evidenceVerify.js``
(``SECRET_RULES``); keep the two lists in step.
"""

from __future__ import annotations

import re
from typing import Any

# Evidence columns that can carry raw scanned text.
EVIDENCE_FIELDS: tuple[str, ...] = ("snippet", "console_output", "detail", "message")

_SECRET_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"Bearer\s+\S+", re.IGNORECASE), "Bearer [REDACTED]"),
    (
        re.compile(r"\b(sk-|sk-ant-|ospy_|tsi_|dashscope)[A-Za-z0-9_-]{8,}\b", re.IGNORECASE),
        "[REDACTED_KEY]",
    ),
    (
        re.compile(r"api[_-]?key[\"']?\s*[:=]\s*[\"']?[^\"'&\s]+", re.IGNORECASE),
        "api_key=[REDACTED]",
    ),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "[REDACTED_TOKEN]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED_TOKEN]"),
    (re.compile(r"\b(sk|rk)[_-](live|test)[_-][A-Za-z0-9]{8,}\b", re.IGNORECASE), "[REDACTED_KEY]"),
    (re.compile(r"password[\"']?\s*[:=]\s*[\"']?[^\"'&\s]+", re.IGNORECASE), "password=[REDACTED]"),
)


def redact_secrets(text: str) -> str:
    """Return *text* with secret-looking values replaced by placeholders."""
    out = text
    for pattern, replacement in _SECRET_RULES:
        out = pattern.sub(replacement, out)
    return out


def redact_row(row: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *row* with every evidence field redacted (non-strings untouched)."""
    redacted = dict(row)
    for field in EVIDENCE_FIELDS:
        value = redacted.get(field)
        if isinstance(value, str):
            redacted[field] = redact_secrets(value)
    return redacted
