"""
Tests for the SCANNER_GROUPS registry seam in sandbox.scanners.

Author: devansh
Created: 2026-08-15
Scope: SCANNER_GROUPS ordering/shape; _group_applies routing; run_all_scanners
       registry iteration (start-signal order, runner dispatch, fake-group
       injection via a copied registry)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import scanners

# ---------------------------------------------------------------------------
# Registry shape + ordering
# ---------------------------------------------------------------------------


def test_given_registry_when_inspected_then_order_and_applicability_preserved() -> None:
    """
    Scenario: SCANNER_GROUPS keeps the historical orchestration order.
    Slice: registry — shape

    Given the module-level registry,
    When its entries are inspected,
    Then skill groups come first (Cisco Skill Scanner then Tessl), the MCP
    group follows, and the both-type groups close the list (Snyk, DepShield,
    Cargo Audit, Presend, then Ossprey last).
    """
    ### Given / When
    groups = scanners.SCANNER_GROUPS

    ### Then
    assert [g["sources"] for g in groups] == [
        scanners.SKILL_SCANNER_SOURCES,
        scanners.TESSL_SOURCES,
        scanners.MCP_SCANNER_SOURCES,
        scanners.SNYK_SOURCES,
        scanners.DEPSHIELD_SOURCES,
        scanners.CARGO_AUDIT_SOURCES,
        scanners.PRESEND_SOURCES,
        scanners.OSSPREY_SOURCES,
    ]
    assert [g["applies_to"] for g in groups] == [
        "skill",
        "skill",
        "mcp_server",
        "both",
        "both",
        "both",
        "both",
        "both",
    ]
    assert groups[-1]["sources"] == ["Ossprey"], "Ossprey must be the final group"
    assert all(callable(g["runner"]) for g in groups)


@pytest.mark.parametrize(
    ("applies_to", "item_type", "expected"),
    [
        ("both", "skill", True),
        ("both", "mcp_server", True),
        ("both", "package", True),
        ("both", "something_else", False),
        ("skill", "skill", True),
        ("skill", "mcp_server", False),
        ("skill", "package", False),
        ("mcp_server", "mcp_server", True),
        ("mcp_server", "skill", False),
        # Slice 64: mcp_server groups are exact-match — package must not inherit MCP scanners.
        ("mcp_server", "package", False),
        ("mcp_server", "something_else", False),
        ("package", "package", True),
        ("package", "skill", False),
    ],
)
def test_given_applies_to_when_routed_then_matches_legacy_branching(
    applies_to: str, item_type: str, expected: bool
) -> None:
    """
    Scenario: _group_applies routes skill / mcp_server / package / both correctly.
    Slice: registry — applies_to routing (slice 64 package)
    """
    ### Given / When / Then
    assert scanners._group_applies(applies_to, item_type) is expected


def test_given_package_when_run_all_then_both_groups_only_no_cisco() -> None:
    """
    Scenario: Package scans get Snyk/DepShield/Ossprey only (GWT-64.3).
    Slice: registry — package dispatch

    Given a package item with all runners mocked,
    When run_all_scanners runs,
    Then on_scanner_start sees Snyk → DepShield → Ossprey and skill/MCP runners
    are never invoked.
    """
    ### Given
    started: list[list[str]] = []
    skill_mock = MagicMock()
    tessl_mock = MagicMock()
    mcp_mock = MagicMock()

    ### When
    with (
        patch.object(scanners, "_run_skill_scanner_group", skill_mock),
        patch.object(scanners, "_run_tessl_group", tessl_mock),
        patch.object(scanners, "_run_mcp_scanner_group", mcp_mock),
        patch.object(
            scanners,
            "_run_snyk_group",
            return_value=([], [{"scanner_source": "Snyk", "status": "completed"}], None),
        ),
        patch.object(
            scanners,
            "_run_depshield_group",
            return_value=([], [{"scanner_source": "DepShield", "status": "completed"}], None),
        ),
        patch.object(
            scanners,
            "_run_cargo_audit_group",
            return_value=([], [{"scanner_source": "Cargo Audit", "status": "completed"}], None),
        ),
        patch.object(
            scanners,
            "_run_presend_group",
            return_value=([], [{"scanner_source": "Presend", "status": "completed"}], None),
        ),
        patch.object(
            scanners,
            "_run_ossprey_group",
            return_value=([], [{"scanner_source": "Ossprey", "status": "completed"}], None),
        ),
    ):
        scanners.run_all_scanners(
            "/w",
            "package",
            "/w",
            on_scanner_start=lambda s: started.append(list(s)),
        )

    ### Then
    assert started == [
        list(scanners.SNYK_SOURCES),
        list(scanners.DEPSHIELD_SOURCES),
        list(scanners.CARGO_AUDIT_SOURCES),
        list(scanners.PRESEND_SOURCES),
        list(scanners.OSSPREY_SOURCES),
    ]
    skill_mock.assert_not_called()
    tessl_mock.assert_not_called()
    mcp_mock.assert_not_called()


# ---------------------------------------------------------------------------
# run_all_scanners drives the registry
# ---------------------------------------------------------------------------


def test_given_skill_when_run_all_then_skill_groups_in_order_and_mcp_skipped() -> None:
    """
    Scenario: Skill scans signal skill groups in order and never touch MCP.
    Slice: registry — skill dispatch

    Given a skill item with all runners mocked,
    When run_all_scanners runs,
    Then on_scanner_start sees Cisco Skill → Tessl → Snyk → DepShield → Cargo Audit → Ossprey
    and the MCP runner is never invoked.
    """
    ### Given
    started: list[list[str]] = []
    mcp_mock = MagicMock()

    ### When
    with (
        patch.object(scanners, "run_cisco_skill_scanner", return_value=([], [])),
        patch.object(scanners, "run_tessl", return_value=(None, [])),
        patch.object(scanners, "run_cisco_mcp_scanner", mcp_mock),
        patch.object(scanners, "run_snyk", return_value=([], [])),
        patch.object(scanners, "run_depshield", return_value=([], [])),
        patch.object(scanners, "run_cargo_audit", return_value=([], [])),
        patch.object(scanners, "run_presend", return_value=([], [])),
        patch.object(scanners, "run_ossprey", return_value=([], [])),
    ):
        scanners.run_all_scanners(
            "/tmp/skill", "skill", "/tmp/skill", on_scanner_start=lambda s: started.append(list(s))
        )

    ### Then
    assert started == [
        list(scanners.SKILL_SCANNER_SOURCES),
        list(scanners.TESSL_SOURCES),
        list(scanners.SNYK_SOURCES),
        list(scanners.DEPSHIELD_SOURCES),
        list(scanners.CARGO_AUDIT_SOURCES),
        list(scanners.PRESEND_SOURCES),
        list(scanners.OSSPREY_SOURCES),
    ]
    mcp_mock.assert_not_called()


def test_given_mcp_server_when_run_all_then_mcp_group_then_snyk_and_skill_skipped() -> None:
    """
    Scenario: MCP scans signal the MCP group then Snyk, skipping skill groups.
    Slice: registry — mcp dispatch

    Given an mcp_server item with all runners mocked,
    When run_all_scanners runs,
    Then start order is MCP → Snyk → DepShield → Cargo Audit → Ossprey and neither skill runner
    is invoked.
    """
    ### Given
    started: list[list[str]] = []
    skill_mock = MagicMock()
    tessl_mock = MagicMock()

    ### When
    with (
        patch.object(scanners, "run_cisco_skill_scanner", skill_mock),
        patch.object(scanners, "run_tessl", tessl_mock),
        patch.object(scanners, "run_cisco_mcp_scanner", return_value=([], [])),
        patch.object(scanners, "run_snyk", return_value=([], [])),
        patch.object(scanners, "run_depshield", return_value=([], [])),
        patch.object(scanners, "run_cargo_audit", return_value=([], [])),
        patch.object(scanners, "run_presend", return_value=([], [])),
        patch.object(scanners, "run_ossprey", return_value=([], [])),
    ):
        scanners.run_all_scanners(
            "/tmp/mcp",
            "mcp_server",
            "https://example.invalid/sse",
            on_scanner_start=lambda s: started.append(list(s)),
        )

    ### Then
    assert started == [
        list(scanners.MCP_SCANNER_SOURCES),
        list(scanners.SNYK_SOURCES),
        list(scanners.DEPSHIELD_SOURCES),
        list(scanners.CARGO_AUDIT_SOURCES),
        list(scanners.PRESEND_SOURCES),
        list(scanners.OSSPREY_SOURCES),
    ]
    skill_mock.assert_not_called()
    tessl_mock.assert_not_called()


def test_given_fake_group_in_copied_registry_when_run_all_then_same_protocol() -> None:
    """
    Scenario: A new scanner plugs in by appending a registry entry only.
    Slice: registry — pluggability seam (Ossprey shape)

    Given a copy of SCANNER_GROUPS extended with a fake 'both' group whose
    runner returns the normalized (findings, rows, quality_score) triple,
    When run_all_scanners runs against the patched registry,
    Then the fake group is start-signalled, relayed through on_scanner_done,
    and aggregated into findings/rows/quality_score/overall_status.
    """
    ### Given
    fake_sources = ["Ossprey"]
    fake_findings = [{"severity": "red", "message": "CVE-XXXX", "scanner_source": "Ossprey"}]
    fake_rows = [{"scanner_source": "Ossprey", "status": "completed", "checks_run": 1}]
    fake_runner = MagicMock(return_value=(fake_findings, fake_rows, 42.0))
    patched_groups = [
        *scanners.SCANNER_GROUPS,
        {"sources": fake_sources, "applies_to": "both", "runner": fake_runner},
    ]
    started: list[list[str]] = []
    done: list[tuple] = []

    ### When
    with (
        patch.object(scanners, "SCANNER_GROUPS", patched_groups),
        patch.object(scanners, "run_cisco_skill_scanner", return_value=([], [])),
        patch.object(scanners, "run_tessl", return_value=(None, [])),
        patch.object(scanners, "run_snyk", return_value=([], [])),
        patch.object(scanners, "run_depshield", return_value=([], [])),
        patch.object(scanners, "run_cargo_audit", return_value=([], [])),
        patch.object(scanners, "run_presend", return_value=([], [])),
        patch.object(scanners, "run_ossprey", return_value=([], [])),
    ):
        result = scanners.run_all_scanners(
            "/tmp/skill",
            "skill",
            "/tmp/skill",
            on_scanner_start=lambda s: started.append(list(s)),
            on_scanner_done=lambda f, r, qs: done.append((f, r, qs)),
        )

    ### Then — same start/relay protocol as the built-in groups
    fake_runner.assert_called_once_with("/tmp/skill", "skill", "/tmp/skill")
    assert started[-1] == fake_sources
    assert done[-1] == (fake_findings, fake_rows, 42.0)
    assert result["findings"] == fake_findings
    assert result["scanner_rows"] == fake_rows
    assert result["quality_score"] == 42.0
    assert result["overall_status"] == "complete"


def test_given_fake_skill_only_group_when_mcp_scan_then_not_run() -> None:
    """
    Scenario: applies_to filtering also governs injected groups.
    Slice: registry — injected group routing

    Given a copied registry with a fake skill-only group,
    When run_all_scanners runs for an mcp_server item,
    Then the fake runner is never invoked.
    """
    ### Given
    fake_runner = MagicMock(return_value=([], [], None))
    patched_groups = [
        *scanners.SCANNER_GROUPS,
        {"sources": ["Ossprey"], "applies_to": "skill", "runner": fake_runner},
    ]

    ### When
    with (
        patch.object(scanners, "SCANNER_GROUPS", patched_groups),
        patch.object(scanners, "run_cisco_mcp_scanner", return_value=([], [])),
        patch.object(scanners, "run_snyk", return_value=([], [])),
        patch.object(scanners, "run_depshield", return_value=([], [])),
        patch.object(scanners, "run_cargo_audit", return_value=([], [])),
        patch.object(scanners, "run_presend", return_value=([], [])),
        patch.object(scanners, "run_ossprey", return_value=([], [])),
    ):
        result = scanners.run_all_scanners("/tmp/mcp", "mcp_server", "https://example.invalid")

    ### Then
    fake_runner.assert_not_called()
    assert result["overall_status"] == "complete"


def test_given_group_runners_when_called_directly_then_normalized_triples() -> None:
    """
    Scenario: Each built-in group runner normalizes its adapter return shape.
    Slice: registry — runner adapters

    Given the six adapters mocked with their native return shapes,
    When each group runner is called with the uniform signature,
    Then all return (findings, rows, quality_score) triples matching the
    legacy aggregation (Tessl contributes no findings, only the score).
    """
    ### Given
    with (
        patch.object(scanners, "run_cisco_skill_scanner", return_value=(["f1"], ["r1"])),
        patch.object(scanners, "run_tessl", return_value=(88.0, ["r2"])),
        patch.object(scanners, "run_cisco_mcp_scanner", return_value=(["f3"], ["r3"])) as mcp,
        patch.object(scanners, "run_snyk", return_value=(["f4"], ["r4"])) as snyk,
        patch.object(scanners, "run_depshield", return_value=(["f5"], ["r5"])) as dep,
        patch.object(scanners, "run_cargo_audit", return_value=(["f6"], ["r6"])) as cargo,
    ):
        ### When / Then
        assert scanners._run_skill_scanner_group("/w", "skill", "/w") == (["f1"], ["r1"], None)
        assert scanners._run_tessl_group("/w", "skill", "/w") == ([], ["r2"], 88.0)
        assert scanners._run_mcp_scanner_group("/w", "mcp_server", "url") == (["f3"], ["r3"], None)
        mcp.assert_called_once_with("/w", "url")
        assert scanners._run_snyk_group("/w", "mcp_server", "url") == (["f4"], ["r4"], None)
        snyk.assert_called_once_with("/w", "mcp_server")
        assert scanners._run_depshield_group("/w", "skill", "/w") == (["f5"], ["r5"], None)
        dep.assert_called_once_with("/w", "skill")
        assert scanners._run_cargo_audit_group("/w", "package", "/w") == (["f6"], ["r6"], None)
        cargo.assert_called_once_with("/w", "package")
