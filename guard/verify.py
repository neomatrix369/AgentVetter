"""Dual-output /av-verify helpers (slice 28).

Classifies resolved artifacts into the six UI states from the Frontline
dual-output contract and renders human Markdown + machine JSON in one pass.
Name resolution and Supabase status lookup are injectable seams so Claude
skills and tests stay free of live I/O.

Delta (2026-08-25): Quality column (``N/100`` from ``items.quality_score``)
and a single blocked-message table footer when any row is ``will_be_blocked``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

UiState = Literal["fresh", "stale", "unscanned", "scanning", "not-found", "red"]

BLOCKED_FOOTER = "Will be blocked when AgentVetter is enabled"
SOURCES_FOOTER = (
    "Sources: Quality is from Tessl (Review Quality). "
    "Security-related Status (GREEN/AMBER/RED) is from Cisco AI Defense and Snyk."
)
NOT_FOUND_NOTE = (
    "No match in ~/.claude/skills, .claude/skills, .mcp.json, ~/.claude.json, "
    "~/.agentvetter/demo-mcp.json, fixtures manifest"
)
TABLE_HEADER = "| Name | Type | Status | Quality | Note |"
TABLE_SEP = "|------|------|--------|---------|------|"

_STATUS_DISPLAY: dict[UiState, str] = {
    "fresh": "🟢 GREEN (fresh)",
    "stale": "⚠️ STALE",
    "unscanned": "🚫 UNSCANNED",
    "scanning": "⏳ SCANNING",
    "not-found": "❓ NOT FOUND",
    "red": "🔴 RED",
}

_FRESH_RAG_DISPLAY = {
    "green": "🟢 GREEN (fresh)",
    "amber": "🟠 AMBER (fresh)",
    "red": "🔴 RED",
}


@dataclass(frozen=True)
class ResolvedArtifact:
    """Resolved name from Claude/agent visibility (or a test double)."""

    name: str
    artifact_type: str | None
    resolved_path: str | None


@dataclass(frozen=True)
class StatusRecord:
    """Supabase-shaped status for one resolved artifact."""

    heatmap_status: str | None
    scanned_at: datetime | None
    run_status: str | None
    quality_score: float | None = None


@dataclass(frozen=True)
class ArtifactRow:
    """One dual-output artifact row (human + machine share these facts)."""

    name: str
    resolved_path: str | None
    type: str | None
    state: UiState
    rag: str | None
    scanned_at: str | None
    stale: bool
    will_be_blocked: bool
    quality_score: float | None
    note: str

    def status_display(self) -> str:
        if self.state == "fresh" and self.rag in _FRESH_RAG_DISPLAY:
            return _FRESH_RAG_DISPLAY[self.rag]
        return _STATUS_DISPLAY[self.state]

    def quality_display(self) -> str:
        return format_quality_cell(
            self.quality_score,
            artifact_type=self.type,
            state=self.state,
        )


@dataclass(frozen=True)
class VerifyResult:
    """One-pass verify result for all requested names."""

    artifacts: list[ArtifactRow]

    def to_machine(self) -> dict[str, Any]:
        return {"artifacts": [asdict(row) for row in self.artifacts]}

    def to_markdown(self) -> str:
        lines = [TABLE_HEADER, TABLE_SEP]
        for row in self.artifacts:
            type_cell = row.type or "—"
            lines.append(
                f"| `{row.name}` | {type_cell} | {row.status_display()} "
                f"| {row.quality_display()} | {row.note} |"
            )
        if any(row.will_be_blocked for row in self.artifacts):
            lines.append("")
            lines.append(f"**{BLOCKED_FOOTER}**")
        lines.append("")
        lines.append(f"*{SOURCES_FOOTER}*")
        return "\n".join(lines)


ResolveFn = Callable[[str], ResolvedArtifact | None]
FetchStatusFn = Callable[[ResolvedArtifact], StatusRecord]
NowFn = Callable[[], datetime]


def format_quality_cell(
    score: float | None,
    *,
    artifact_type: str | None,
    state: UiState,
) -> str:
    """Human Quality cell: ``N/100`` when a skill score exists; else ``—``."""
    if state in ("unscanned", "not-found", "scanning"):
        return "—"
    if artifact_type == "mcp":
        return "—"
    if score is None:
        return "—"
    return f"{int(round(score))}/100"


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_stale(scanned_at: datetime | None, validity_days: int, now: datetime) -> bool:
    if scanned_at is None:
        # Unknown age: fail closed, the same as guard/status.py.
        return True
    point = scanned_at if scanned_at.tzinfo else scanned_at.replace(tzinfo=UTC)
    return point < now - timedelta(days=validity_days)


def _row(
    *,
    name: str,
    resolved_path: str | None,
    artifact_type: str | None,
    state: UiState,
    rag: str | None,
    scanned_at: str | None,
    stale: bool,
    will_be_blocked: bool,
    quality_score: float | None,
    note: str,
) -> ArtifactRow:
    return ArtifactRow(
        name=name,
        resolved_path=resolved_path,
        type=artifact_type,
        state=state,
        rag=rag,
        scanned_at=scanned_at,
        stale=stale,
        will_be_blocked=will_be_blocked,
        quality_score=quality_score,
        note=note,
    )


def _at_or_above(rag: str, threshold: str) -> bool:
    """Same rule the guard applies: red always blocks; amber blocks unless the threshold is red."""
    # Same as guard_hook: any threshold other than "red" (i.e. "red_and_amber") also blocks amber.
    return rag == "red" or (threshold != "red" and rag == "amber")


def _running_blocks(
    status: StatusRecord, *, validity_days: int, now: datetime, threshold: str
) -> bool:
    """A running scan is blocked unless its prior verdict is fresh and passes the threshold."""
    heatmap = (status.heatmap_status or "").lower()
    has_prior = heatmap in ("green", "amber", "red")
    if not has_prior or _is_stale(status.scanned_at, validity_days, now):
        return True
    return _at_or_above(heatmap, threshold)


def _classify(
    name: str,
    resolved: ResolvedArtifact | None,
    status: StatusRecord | None,
    *,
    validity_days: int,
    now: datetime,
    threshold: str = "red",
) -> ArtifactRow:
    if resolved is None:
        return _row(
            name=name,
            resolved_path=None,
            artifact_type=None,
            state="not-found",
            rag=None,
            scanned_at=None,
            stale=False,
            will_be_blocked=True,
            quality_score=None,
            note=NOT_FOUND_NOTE,
        )

    assert status is not None
    score = status.quality_score
    if status.run_status == "running":
        return _row(
            name=resolved.name,
            resolved_path=resolved.resolved_path,
            artifact_type=resolved.artifact_type,
            state="scanning",
            rag=None,
            scanned_at=_iso(status.scanned_at),
            stale=False,
            will_be_blocked=_running_blocks(
                status, validity_days=validity_days, now=now, threshold=threshold
            ),
            quality_score=score,
            note="Scan in progress — check back shortly",
        )

    heatmap = (status.heatmap_status or "").lower()
    if heatmap in ("", "grey", "error") or status.heatmap_status is None:
        return _row(
            name=resolved.name,
            resolved_path=resolved.resolved_path,
            artifact_type=resolved.artifact_type,
            state="unscanned",
            rag=None,
            scanned_at=_iso(status.scanned_at),
            stale=False,
            will_be_blocked=True,
            quality_score=None,
            note=f"Never scanned — offer `/av-scan {resolved.name}`",
        )

    stale = _is_stale(status.scanned_at, validity_days, now)
    if stale:
        return _row(
            name=resolved.name,
            resolved_path=resolved.resolved_path,
            artifact_type=resolved.artifact_type,
            state="stale",
            rag=heatmap if heatmap in ("green", "amber", "red") else None,
            scanned_at=_iso(status.scanned_at),
            stale=True,
            will_be_blocked=True,
            quality_score=score,
            note=(
                f"Last scanned >{validity_days} days ago — "
                f"blocked until rescanned (run /av-scan {resolved.name})"
            ),
        )

    if heatmap == "red":
        return _row(
            name=resolved.name,
            resolved_path=resolved.resolved_path,
            artifact_type=resolved.artifact_type,
            state="red",
            rag="red",
            scanned_at=_iso(status.scanned_at),
            stale=False,
            will_be_blocked=True,
            quality_score=score,
            note="rated red — at/above threshold",
        )

    rag = heatmap if heatmap in ("green", "amber") else None
    blocked = _at_or_above(heatmap, threshold)
    if blocked:
        note = f"rated {heatmap} — at/above threshold"
    else:
        note = "—" if heatmap == "green" else "Reported but not blocked at current threshold"
    return _row(
        name=resolved.name,
        resolved_path=resolved.resolved_path,
        artifact_type=resolved.artifact_type,
        state="fresh",
        rag=rag,
        scanned_at=_iso(status.scanned_at),
        stale=False,
        will_be_blocked=blocked,
        quality_score=score,
        note=note,
    )


def verify_artifacts(
    names: Sequence[str],
    *,
    resolve: ResolveFn,
    fetch_status: FetchStatusFn,
    validity_days: int = 14,
    threshold: str,
    now: NowFn | None = None,
) -> VerifyResult:
    """Verify every name in one pass; never stop at the first issue.

    Pass the guard's configured ``threshold`` so the blocked column matches enforcement.
    """
    clock = now or (lambda: datetime.now(UTC))
    current = clock()
    rows: list[ArtifactRow] = []
    for name in names:
        resolved = resolve(name)
        status = fetch_status(resolved) if resolved is not None else None
        rows.append(
            _classify(
                name,
                resolved,
                status,
                validity_days=validity_days,
                now=current,
                threshold=threshold,
            )
        )
    return VerifyResult(artifacts=rows)
