"""
Unit coverage for guard.verify edge paths (slice 28).

Author: slice-28
Created: 2026-08-15
Updated: 2026-08-25 — format_quality_cell
Scope: naive datetime ISO/stale helpers; default now clock; quality cell
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from guard.verify import (
    ResolvedArtifact,
    StatusRecord,
    _is_stale,
    _iso,
    format_quality_cell,
    verify_artifacts,
)


def test_given_naive_datetime_when_iso_then_utc_z_suffix() -> None:
    """Scenario: Naive scanned_at is treated as UTC for machine JSON."""
    ### Given
    naive = datetime(2026, 8, 1, 10, 0, 0)

    ### When
    actual = _iso(naive)

    ### Then
    assert actual == "2026-08-01T10:00:00Z"


def test_given_none_scanned_at_when_stale_checked_then_true() -> None:
    """Scenario: A verdict with no timestamp has unknown age, so it is stale (fail closed)."""
    ### Given / When
    actual = _is_stale(None, 14, datetime(2026, 8, 15, tzinfo=UTC))

    ### Then
    assert actual is True


def test_given_naive_old_scan_when_stale_checked_then_true() -> None:
    """Scenario: Naive old scanned_at compares correctly against aware now."""
    ### Given
    naive_old = datetime(2026, 1, 1, 0, 0, 0)
    now = datetime(2026, 8, 15, tzinfo=UTC)

    ### When
    actual = _is_stale(naive_old, 14, now)

    ### Then
    assert actual is True


def test_given_no_now_inject_when_verify_then_uses_clock() -> None:
    """Scenario: Default now() path remains callable without injection."""

    ### Given
    def resolve(name: str) -> ResolvedArtifact:
        return ResolvedArtifact(name=name, artifact_type="skill", resolved_path="/tmp/x")

    def fetch_status(_resolved: ResolvedArtifact) -> StatusRecord:
        return StatusRecord(
            heatmap_status="green",
            scanned_at=datetime.now(UTC) - timedelta(days=1),
            run_status="complete",
            quality_score=80,
        )

    ### When
    actual = verify_artifacts(["x"], resolve=resolve, fetch_status=fetch_status)

    ### Then
    assert actual.artifacts[0].state == "fresh"
    assert actual.artifacts[0].quality_display() == "80/100"


@pytest.mark.parametrize(
    ("score", "artifact_type", "state", "expected"),
    [
        (91.4, "skill", "fresh", "91/100"),
        (None, "skill", "fresh", "—"),
        (88.0, "mcp", "fresh", "—"),
        (70.0, "skill", "unscanned", "—"),
        (70.0, "skill", "not-found", "—"),
        (70.0, "skill", "scanning", "—"),
    ],
)
def test_given_score_inputs_when_format_quality_then_n_over_100_or_emdash(
    score: float | None,
    artifact_type: str,
    state: str,
    expected: str,
) -> None:
    """Scenario: format_quality_cell owns the /100 display contract."""
    ### Given / When
    actual = format_quality_cell(score, artifact_type=artifact_type, state=state)  # type: ignore[arg-type]

    ### Then
    assert actual == expected


def test_given_running_scan_without_prior_verdict_when_classified_then_blocked() -> None:
    """Scenario: A running scan with no prior verdict is blocked, matching guard/status.py."""
    ### Given
    from guard.verify import StatusRecord, _running_blocks

    status = StatusRecord(heatmap_status="grey", scanned_at=None, run_status="running")

    ### When / Then
    assert (
        _running_blocks(
            status, validity_days=14, now=datetime(2026, 8, 15, tzinfo=UTC), threshold="red"
        )
        is True
    )


def test_given_amber_verdict_and_amber_threshold_when_at_or_above_then_true() -> None:
    """Scenario: At an amber threshold an amber verdict is blocked, as the guard blocks it."""
    ### Given / When / Then
    from guard.verify import _at_or_above

    assert _at_or_above("amber", "amber") is True
    assert _at_or_above("amber", "red") is False
    assert _at_or_above("red", "red") is True
