"""AgentVetter guard package: enforcement primitives + the Claude Code hook entry.

Supabase imports are lazy throughout, so importing ``guard.*`` works without
the optional ``guard`` dependency group installed.
"""

from guard.entry import decide, extract_target, main, resolve_artifact, resolve_operator_name
from guard.guard_hook import check_call_by_identifier
from guard.status import (
    DEFAULT_VALIDITY_DAYS,
    get_item_status,
    hash_local_path,
    make_client,
)

__all__ = [
    "DEFAULT_VALIDITY_DAYS",
    "check_call_by_identifier",
    "decide",
    "extract_target",
    "get_item_status",
    "hash_local_path",
    "main",
    "make_client",
    "resolve_artifact",
    "resolve_operator_name",
]
