"""
Acceptance tests for /av-verify (slice 28; primary brand AgentVetter).

Author: slice-28
Created: 2026-08-15
Updated: 2026-08-25 — Quality column (N/100) + blocked footer de-dupe
Scope: multi-name; six states; Quality; footer; unscanned→scan; not-found; SKILL.md
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
AV_VERIFY_SKILL = REPO_ROOT / "agent-hooks" / "skills" / "av-verify" / "SKILL.md"
BLOCKED_FOOTER = "Will be blocked when AgentVetter is enabled"
NOW = datetime(2026, 8, 15, 12, 0, 0, tzinfo=UTC)


def _resolved(name: str, artifact_type: str = "skill") -> Any:
    from guard.verify import ResolvedArtifact

    return ResolvedArtifact(
        name=name,
        artifact_type=artifact_type,
        resolved_path=f"/tmp/{name}",
    )


def _status(
    *,
    heatmap: str | None = "green",
    scanned_at: datetime | None = None,
    run_status: str | None = "complete",
    quality_score: float | None = None,
) -> Any:
    from guard.verify import StatusRecord

    return StatusRecord(
        heatmap_status=heatmap,
        scanned_at=scanned_at if scanned_at is not None else NOW - timedelta(days=1),
        run_status=run_status,
        quality_score=quality_score,
    )


def test_given_two_names_when_verify_then_one_pass_table_and_json() -> None:
    """
    Scenario: Multi-name verify reports every name in one Markdown table and JSON.
    Slice: 28 — multi-name one-pass

    Given two resolvable names with distinct statuses,
    When verify_artifacts runs,
    Then both names appear as table rows and in artifacts[] without stopping early.
    """
    from guard.verify import verify_artifacts

    ### Given
    names = ["safe-skill", "vuln-skill"]

    def resolve(name: str):
        return _resolved(name)

    def fetch_status(resolved):
        if resolved.name == "safe-skill":
            return _status(heatmap="green", quality_score=91)
        return _status(heatmap="red", quality_score=12)

    ### When
    actual = verify_artifacts(
        names,
        resolve=resolve,
        threshold="red",
        fetch_status=fetch_status,
        validity_days=14,
        now=lambda: NOW,
    )

    ### Then
    assert len(actual.artifacts) == 2, "must report both names in one pass"
    assert [row.name for row in actual.artifacts] == names
    machine = actual.to_machine()
    assert len(machine["artifacts"]) == 2
    markdown = actual.to_markdown()
    assert "| Name | Type | Status | Quality | Note |" in markdown
    assert "safe-skill" in markdown
    assert "vuln-skill" in markdown


SIX_STATE_CASES = [
    ("fresh-green", "fresh", "green"),
    ("stale-skill", "stale", "green"),
    ("new-skill", "unscanned", None),
    ("pending-skill", "scanning", None),
    ("missing-skill", "not-found", None),
    ("vuln-skill", "red", "red"),
]


@pytest.mark.parametrize(("name", "expected_state", "expected_rag"), SIX_STATE_CASES)
def test_given_state_fixture_when_verify_then_contract_state(
    name: str,
    expected_state: str,
    expected_rag: str | None,
) -> None:
    """
    Scenario: Each of the six UI states renders per the slice-26 contract.
    Slice: 28 — state coverage

    Given a fixture for one UI state,
    When verify runs,
    Then artifact.state (and rag when applicable) matches the contract.
    """
    from guard.verify import StatusRecord, verify_artifacts

    ### Given
    def resolve(query: str):
        if query == "missing-skill":
            return None
        return _resolved(query)

    def fetch_status(resolved):
        if resolved.name == "fresh-green":
            return _status(heatmap="green")
        if resolved.name == "stale-skill":
            return _status(
                heatmap="green",
                scanned_at=NOW - timedelta(days=30),
            )
        if resolved.name == "new-skill":
            return StatusRecord(heatmap_status="grey", scanned_at=None, run_status=None)
        if resolved.name == "pending-skill":
            return StatusRecord(
                heatmap_status="grey",
                scanned_at=None,
                run_status="running",
            )
        if resolved.name == "vuln-skill":
            return _status(heatmap="red")
        return _status(heatmap="green")

    ### When
    actual = verify_artifacts(
        [name],
        resolve=resolve,
        threshold="red",
        fetch_status=fetch_status,
        validity_days=14,
        now=lambda: NOW,
    )

    ### Then
    assert len(actual.artifacts) == 1
    row = actual.artifacts[0]
    assert row.state == expected_state, f"expected state {expected_state} for {name}"
    assert row.rag == expected_rag
    assert "Quality" in actual.to_markdown()


QUALITY_CASES = [
    ("skill", "green", 91.0, "fresh", "91/100"),
    ("skill", "green", None, "fresh", "—"),
    ("mcp", "green", 88.0, "fresh", "—"),
    ("skill", "grey", 70.0, "unscanned", "—"),
]


@pytest.mark.parametrize(
    ("artifact_type", "heatmap", "score", "expected_state", "expected_cell"),
    QUALITY_CASES,
)
def test_given_quality_score_when_verify_then_cell_is_n_over_100_or_emdash(
    artifact_type: str,
    heatmap: str,
    score: float | None,
    expected_state: str,
    expected_cell: str,
) -> None:
    """
    Scenario: Quality cell shows N/100 for scored skills; — otherwise.
    Slice: 28 — Quality column

    Given a found artifact with optional items.quality_score,
    When verify reports it,
    Then Quality is N/100 (never bare int / Q N) or — for MCP/null/unscanned.
    """
    from guard.verify import StatusRecord, verify_artifacts

    ### Given
    def resolve(name: str):
        return _resolved(name, artifact_type=artifact_type)

    def fetch_status(_resolved):
        if heatmap == "grey":
            return StatusRecord(
                heatmap_status="grey",
                scanned_at=None,
                run_status=None,
                quality_score=score,
            )
        return _status(heatmap=heatmap, quality_score=score)

    ### When
    actual = verify_artifacts(
        ["artifact"],
        resolve=resolve,
        threshold="red",
        fetch_status=fetch_status,
        validity_days=14,
        now=lambda: NOW,
    )

    ### Then
    row = actual.artifacts[0]
    assert row.state == expected_state
    assert row.quality_display() == expected_cell
    assert "quality_score" in actual.to_machine()["artifacts"][0]
    if expected_cell != "—":
        assert "/100" in expected_cell
        assert expected_cell in actual.to_markdown()
        assert "Q " not in expected_cell


def test_given_blocked_rows_when_verify_then_footer_once_not_in_notes() -> None:
    """
    Scenario: Shared blocked phrase is a single table footer, not per-row Notes.
    Slice: 28 — blocked footer de-dupe

    Given one or more will_be_blocked rows,
    When verify renders Markdown,
    Then the blocked phrase appears once under the table; Notes stay distinct.
    """
    from guard.verify import verify_artifacts

    ### Given
    def resolve(name: str):
        return _resolved(name)

    def fetch_status(resolved):
        if resolved.name == "vuln-skill":
            return _status(heatmap="red")
        return _status(heatmap="grey")

    ### When
    actual = verify_artifacts(
        ["vuln-skill", "new-skill"],
        resolve=resolve,
        threshold="red",
        fetch_status=fetch_status,
        validity_days=14,
        now=lambda: NOW,
    )

    ### Then
    from guard.verify import SOURCES_FOOTER

    markdown = actual.to_markdown()
    assert markdown.count(BLOCKED_FOOTER) == 1
    for row in actual.artifacts:
        assert row.will_be_blocked is True
        assert BLOCKED_FOOTER not in row.note
    assert f"**{BLOCKED_FOOTER}**" in markdown
    assert SOURCES_FOOTER in markdown
    assert markdown.strip().endswith(f"*{SOURCES_FOOTER}*")


def test_given_unscanned_when_verify_then_offers_av_scan() -> None:
    """
    Scenario: Unscanned artifacts offer /av-scan for that name.
    Slice: 28 — unscanned offers scan

    Given an unscanned artifact,
    When verify reports it,
    Then the Note offers /av-scan for that name.
    """
    from guard.verify import StatusRecord, verify_artifacts

    ### Given
    name = "new-skill"

    def resolve(query: str):
        return _resolved(query)

    def fetch_status(_resolved):
        return StatusRecord(heatmap_status="grey", scanned_at=None, run_status=None)

    ### When
    actual = verify_artifacts(
        [name],
        resolve=resolve,
        threshold="red",
        fetch_status=fetch_status,
        validity_days=14,
        now=lambda: NOW,
    )

    ### Then
    row = actual.artifacts[0]
    assert row.state == "unscanned"
    assert "/av-scan" in row.note
    assert name in row.note


def test_given_unresolved_name_when_verify_then_human_not_found_message() -> None:
    """
    Scenario: Not-found names get a useful human message, not a bare error.
    Slice: 28 — not-found human-readable

    Given a name with no resolution match,
    When verify runs,
    Then the response includes a useful human message (not a bare error),
    and fetch_status is never invoked for missing names.
    """
    from guard.verify import verify_artifacts

    ### Given
    name = "unknown-skill"

    def resolve(_query: str):
        return None

    def fetch_status(_resolved):
        raise AssertionError("fetch_status must not run for not-found")

    ### When
    actual = verify_artifacts(
        [name],
        resolve=resolve,
        threshold="red",
        fetch_status=fetch_status,
        validity_days=14,
        now=lambda: NOW,
    )

    ### Then
    row = actual.artifacts[0]
    assert row.state == "not-found"
    assert row.name == name
    assert row.resolved_path is None
    assert row.will_be_blocked is True
    assert "No match" in row.note
    assert BLOCKED_FOOTER not in row.note
    assert "Traceback" not in row.note
    assert "Exception" not in row.note
    assert "❓" in actual.to_markdown() or "NOT FOUND" in actual.to_markdown()
    assert BLOCKED_FOOTER in actual.to_markdown()


def test_given_repo_when_skill_looked_up_then_agent_hooks_skill_md_exists() -> None:
    """
    Scenario: /av-verify ships at the agent-hooks skill layout path.
    Slice: 28 — skill installed via setup-agent-hooks

    Given the repo checkout,
    When an operator looks for /av-verify,
    Then SKILL.md exists with Quality column, quality_score driver, and footer.
    """
    ### Given / When
    text = AV_VERIFY_SKILL.read_text(encoding="utf-8")

    ### Then
    assert AV_VERIFY_SKILL.is_file(), f"missing {AV_VERIFY_SKILL}"
    assert "Name | Type | Status | Quality | Note" in text
    assert "quality_score" in text
    assert "N/100" in text or "/100" in text
    assert BLOCKED_FOOTER in text
    assert "footer" in text.lower() or "under the table" in text.lower()
    assert "Tessl" in text
    assert "Cisco" in text and "Snyk" in text
    assert "Sources:" in text
