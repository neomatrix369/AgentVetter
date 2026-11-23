"""PreToolUse-style guard hook (spec Phase 4).
Wire this into the agent runtime's pre-tool-call interception point; it must run
synchronously before the call executes and be able to block it.

Fails closed: unscanned or below-threshold => deny. Never triggers a synchronous scan
on a cache miss (a full Modal spin-up is too slow to sit inline)."""

import hashlib
import os
from collections.abc import Callable
from typing import Any

from guard.status import (
    DEFAULT_VALIDITY_DAYS,
    content_changed,
    get_item_status,
    hash_local_path,
    make_client,
)

_SEVERITY_ORDER = {"green": 0, "amber": 1, "red": 2, "grey": 3, "error": 3}


def _client():
    from supabase import create_client  # lazy: `import guard` must work without supabase

    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])


def hash_target(content_bytes: bytes) -> str:
    return hashlib.sha256(content_bytes).hexdigest()


def check_call_by_identifier(
    identifier: str,
    validity_days: int | None = None,
    content_path: str | None = None,
    *,
    client: Any = None,
    status_fn: Callable[..., dict[str, Any]] | None = None,
    hash_fn: Callable[[str], str] | None = None,
) -> dict:
    """Identifier-based guard verdict (plan T1). Same threshold semantics as
    the legacy content check plus, inside the primitive: staleness (stale ≡ unscanned),
    the error→unscanned fail-closed mapping, tamper evidence (recomputed
    CLI-compatible content hash vs the stored one), and the rescan-in-progress
    rule (a prior completed verdict stands while a rescan runs — but only
    while that prior verdict is itself inside the validity window, §6.1).

    Never raises: any internal error returns a fail-closed deny (T2).
    Returns ``{"allow": bool, "reason": str, "status": str|None}``.

    ``client`` / ``status_fn`` / ``hash_fn`` are injectable seams for tests;
    defaults hit Supabase via env credentials with a short timeout.
    """
    try:
        return _check_call_by_identifier(
            identifier,
            DEFAULT_VALIDITY_DAYS if validity_days is None else validity_days,
            content_path,
            client=client,
            status_fn=status_fn if status_fn is not None else get_item_status,
            hash_fn=hash_fn if hash_fn is not None else hash_local_path,
        )
    except Exception:
        return {"allow": False, "reason": "guard error — fail closed", "status": None}


def _check_call_by_identifier(
    identifier: str,
    validity_days: int,
    content_path: str | None,
    *,
    client: Any,
    status_fn: Callable[..., dict[str, Any]],
    hash_fn: Callable[[str], str],
) -> dict:
    if client is None:
        client = make_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

    status = status_fn(client, identifier, validity_days)
    if not status["monitoring_enabled"]:
        return {"allow": True, "reason": "monitoring disabled", "status": None}

    state = status["state"]
    item = status.get("item")

    if state == "unscanned":
        if item is not None and item.get("heatmap_status") == "error":
            return {
                "allow": False,
                "reason": "last scan errored — resubmit scan (guard fails closed)",
                "status": "error",
            }
        return {"allow": False, "reason": "never scanned — guard fails closed", "status": "grey"}

    if state == "stale":
        return {
            "allow": False,
            "reason": f"last scan older than {validity_days} days — stale, rescan required",
            "status": "stale",
        }

    rag = status.get("rag")
    if state == "scanning" and rag is None:
        # §6.1 scanning row: blocked when the prior verdict is none/stale/
        # at-threshold. A stale prior gets a distinct rescan-flavored reason —
        # a stuck 'running' row must not freeze enforcement on an old verdict.
        if status.get("prior_stale"):
            return {
                "allow": False,
                "reason": (
                    f"rescan in progress — prior verdict older than {validity_days} "
                    "days (stale), blocked until the rescan completes"
                ),
                "status": "scanning",
            }
        return {
            "allow": False,
            "reason": "scan in progress — no completed verdict yet (guard fails closed)",
            "status": "scanning",
        }

    # Here: state is 'fresh', or 'scanning' with a fresh prior completed
    # verdict (which stands until rollup — plan §6.1). Tamper check first via
    # the shared predicate: recompute the CLI-compatible hash and deny on
    # drift. `pending:` placeholders (manifest-only artifacts with no source
    # on disk — all MCP servers) are exempt inside content_changed.
    if content_changed(content_path, status.get("stored_content_hash"), hash_fn=hash_fn):
        return {
            "allow": False,
            "reason": "content changed since last scan — run /av-scan",
            "status": rag,
        }

    threshold_level = 2 if status["threshold"] == "red" else 1  # 'red' vs 'red_and_amber'
    item_level = _SEVERITY_ORDER.get(str(rag), 3)
    if item_level >= threshold_level:
        return {"allow": False, "reason": f"rated {rag} — at/above threshold", "status": rag}

    return {"allow": True, "reason": f"rated {rag} — below threshold", "status": rag}
