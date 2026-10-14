"""
Tests for the Ossprey adapter (RESEARCH-grade malicious-package / malware
detection via the ossprey CLI).

Author: devansh
Created: 2026-08-15
Scope: credential gate (skipped_missing_credential — the DEFAULT runtime path
       today, access provisioning OPEN), generic API_KEY ignored, missing-binary
       unreachable, exit-code disambiguation (0=clean / 1=malware vs failure),
       OSSBOM parsing for list + {"components":[...]} shapes and a missing file,
       stdout verdict-line detection with negation guard, temp OSSBOM cleanup,
       operator-facing unreachable/not_applicable detail (timeout, No SBOM,
       Cargo-only), and registry integration (Ossprey appended last, both item
       types). NO network — the CLI is stubbed by patching _run / _which /
       os.environ.

RESEARCH label: the OSSBOM schema and verdict wording are UNVERIFIED (taken from
vendor docs, not a live CLI), so these tests lock the adapter's *contract*
(never-crash, disambiguation, credential gate) rather than a real fixture. They
must be re-reconciled against the pinned ossprey-cli --json output (ADR-0005).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import scanners

# ---------------------------------------------------------------------------
# Helpers: stub the ossprey subprocess without spawning it or hitting a network
# ---------------------------------------------------------------------------


def _fake_run(code, ossbom_obj=None, stdout="", stderr=""):
    """Build a _run side_effect: optionally write *ossbom_obj* to the -o path,
    then return the given (code, stdout, stderr) — no real subprocess."""

    def _side_effect(cmd, timeout=None):
        if ossbom_obj is not None:
            out_path = cmd[cmd.index("-o") + 1]
            Path(out_path).write_text(json.dumps(ossbom_obj), encoding="utf-8")
        return code, stdout, stderr

    return _side_effect


# ---------------------------------------------------------------------------
# Credential gate — the DEFAULT runtime path today (no key provisioned)
# ---------------------------------------------------------------------------


def test_given_no_key_when_run_ossprey_then_skipped_missing_credential_default() -> None:
    """
    Scenario: With no Ossprey key, the adapter skips before doing anything else.
    Slice: run_ossprey — credential gate (default path)

    Given neither OSSPREY_API_KEY nor a generic API_KEY is set (the real state today —
    provisioning is OPEN),
    When run_ossprey runs,
    Then it returns skipped_missing_credential, spawns no subprocess, and never
    probes for the binary.
    """
    ### Given
    run_mock = MagicMock()
    which_mock = MagicMock()

    ### When
    with (
        patch.dict(scanners.os.environ, {}, clear=True),
        patch.object(scanners, "_run", run_mock),
        patch.object(scanners, "_which", which_mock),
    ):
        findings, rows = scanners.run_ossprey("/tmp/scan", "mcp_server")

    ### Then
    assert findings == []
    assert len(rows) == 1
    assert rows[0]["scanner_source"] == "Ossprey"
    assert rows[0]["status"] == "skipped_missing_credential"
    assert rows[0]["checks_run"] == 0
    assert "provisioning is OPEN" in rows[0]["detail"]
    run_mock.assert_not_called()
    which_mock.assert_not_called()


def test_given_api_key_only_when_run_ossprey_then_still_skipped() -> None:
    """
    Scenario: Generic API_KEY must not activate the adapter (OSSPREY_API_KEY only).
    Slice: run_ossprey — credential gate

    Given only API_KEY is set (no OSSPREY_API_KEY),
    When run_ossprey runs,
    Then the adapter skips with skipped_missing_credential and never probes the binary.
    """
    ### Given
    run_mock = MagicMock()
    which_mock = MagicMock()

    ### When
    with (
        patch.dict(scanners.os.environ, {"API_KEY": "ospy_fallback"}, clear=True),
        patch.object(scanners, "_run", run_mock),
        patch.object(scanners, "_which", which_mock),
    ):
        findings, rows = scanners.run_ossprey("/tmp/scan", "skill")

    ### Then
    assert findings == []
    assert rows[0]["status"] == "skipped_missing_credential"
    assert "OSSPREY_API_KEY" in rows[0]["detail"]
    run_mock.assert_not_called()
    which_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Binary gate
# ---------------------------------------------------------------------------


def test_given_key_but_no_binary_when_run_ossprey_then_unreachable() -> None:
    """
    Scenario: Key present but the ossprey CLI is missing → unreachable.
    Slice: run_ossprey — binary gate
    """
    ### Given
    run_mock = MagicMock()

    ### When
    with (
        patch.dict(scanners.os.environ, {"OSSPREY_API_KEY": "ospy_test"}, clear=True),
        patch.object(scanners, "_which", return_value=False),
        patch.object(scanners, "_run", run_mock),
    ):
        findings, rows = scanners.run_ossprey("/tmp/scan", "mcp_server")

    ### Then
    assert findings == []
    assert rows[0]["status"] == "unreachable"
    assert "ossprey CLI not installed" in rows[0]["detail"]
    run_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Exit-code disambiguation (0 = clean / skipped, 1 = malware OR failure)
# ---------------------------------------------------------------------------


def test_given_exit0_and_empty_ossbom_when_run_ossprey_then_completed_zero(tmp_path: Path) -> None:
    """
    Scenario: Clean scan (exit 0, empty OSSBOM) → completed with no findings.
    Slice: run_ossprey — clean

    Given the CLI exits 0 and writes no OSSBOM content,
    When run_ossprey runs,
    Then a completed row carries zero findings (exit 0 is authoritative).
    """
    ### Given / When
    with (
        patch.dict(scanners.os.environ, {"OSSPREY_API_KEY": "ospy_test"}, clear=True),
        patch.object(scanners, "_which", return_value=True),
        patch.object(scanners, "_run", side_effect=_fake_run(0, stdout="No malicious packages")),
    ):
        findings, rows = scanners.run_ossprey(str(tmp_path), "mcp_server")

    ### Then
    assert findings == []
    assert rows[0]["status"] == "completed"
    assert rows[0]["checks_run"] == 1  # no OSSBOM → falls back to 1 (a scan ran)


def test_given_exit0_with_packages_when_run_ossprey_then_checks_from_ossbom(
    tmp_path: Path,
) -> None:
    """
    Scenario: checks_run reflects the OSSBOM package count on a clean scan.
    Slice: run_ossprey — checks_run from OSSBOM

    Given exit 0 and an OSSBOM listing three (benign) components,
    When run_ossprey runs,
    Then checks_run is 3 and there are no findings.
    """
    ### Given
    ossbom = {"components": [{"name": "a"}, {"name": "b"}, {"name": "c"}]}

    ### When
    with (
        patch.dict(scanners.os.environ, {"OSSPREY_API_KEY": "ospy_test"}, clear=True),
        patch.object(scanners, "_which", return_value=True),
        patch.object(scanners, "_run", side_effect=_fake_run(0, ossbom_obj=ossbom)),
    ):
        findings, rows = scanners.run_ossprey(str(tmp_path), "skill")

    ### Then
    assert findings == []
    assert rows[0]["status"] == "completed"
    assert rows[0]["checks_run"] == 3


def test_given_exit1_with_malicious_ossbom_when_run_ossprey_then_one_red_finding(
    tmp_path: Path,
) -> None:
    """
    Scenario: Real malware verdict (exit 1 + malicious OSSBOM entry) → red finding.
    Slice: run_ossprey — malware verdict

    Given exit 1 and an OSSBOM with a component flagged malicious,
    When run_ossprey runs,
    Then a single red 'malware' finding carries the package name/version and the
    row is completed (not unreachable) with the malicious count.
    """
    ### Given
    ossbom = {
        "components": [
            {"name": "evil-pkg", "version": "6.6.6", "malicious": True},
            {"name": "safe-pkg", "version": "1.0.0"},
        ]
    }

    ### When
    with (
        patch.dict(scanners.os.environ, {"OSSPREY_API_KEY": "ospy_test"}, clear=True),
        patch.object(scanners, "_which", return_value=True),
        patch.object(
            scanners, "_run", side_effect=_fake_run(1, ossbom_obj=ossbom, stdout="malware found")
        ),
    ):
        findings, rows = scanners.run_ossprey(str(tmp_path), "mcp_server")

    ### Then
    assert len(findings) == 1
    f = findings[0]
    assert f["severity"] == "red"
    assert f["category"] == "malware"
    assert f["scanner_source"] == "Ossprey"
    assert f["package_name"] == "evil-pkg"
    assert f["package_version"] == "6.6.6"
    assert "evil-pkg@6.6.6" in f["message"]
    assert rows[0]["status"] == "completed"
    assert rows[0]["checks_run"] == 2  # both components counted as checks


def test_given_exit1_no_signal_when_run_ossprey_then_unreachable_not_finding(
    tmp_path: Path,
) -> None:
    """
    Scenario: THE disambiguation — exit 1 that is a scan FAILURE, not malware.
    Slice: run_ossprey — exit-1 failure vs malware

    Given exit 1 with an empty OSSBOM and stderr describing a scan error (no
    malware/malicious signal anywhere),
    When run_ossprey runs,
    Then the row is unreachable and NO phantom red finding is emitted.
    """
    ### Given / When
    with (
        patch.dict(scanners.os.environ, {"OSSPREY_API_KEY": "ospy_test"}, clear=True),
        patch.object(scanners, "_which", return_value=True),
        patch.object(
            scanners,
            "_run",
            side_effect=_fake_run(1, stdout="scanning...", stderr="fatal: network unreachable"),
        ),
    ):
        findings, rows = scanners.run_ossprey(str(tmp_path), "skill")

    ### Then
    assert findings == []
    assert rows[0]["status"] == "unreachable"
    assert "network unreachable" in rows[0]["detail"]


def test_given_exit1_stdout_verdict_only_when_run_ossprey_then_red_from_line(
    tmp_path: Path,
) -> None:
    """
    Scenario: Malware verdict via stdout line only (no structured OSSBOM entry).
    Slice: run_ossprey — stdout verdict fallback

    Given exit 1, an empty OSSBOM, and an unambiguous 'MALWARE DETECTED' stdout
    line,
    When run_ossprey runs,
    Then a red 'malware' finding is emitted carrying the verdict line as message.
    """
    ### Given / When
    with (
        patch.dict(scanners.os.environ, {"OSSPREY_API_KEY": "ospy_test"}, clear=True),
        patch.object(scanners, "_which", return_value=True),
        patch.object(
            scanners,
            "_run",
            side_effect=_fake_run(1, stdout="MALWARE DETECTED in requests-evil@9.9.9"),
        ),
    ):
        findings, rows = scanners.run_ossprey(str(tmp_path), "mcp_server")

    ### Then
    assert len(findings) == 1
    assert findings[0]["severity"] == "red"
    assert findings[0]["category"] == "malware"
    assert "MALWARE DETECTED" in findings[0]["message"]
    assert rows[0]["status"] == "completed"


def test_given_exit1_positive_line_with_not_false_positive_when_run_ossprey_then_red(
    tmp_path: Path,
) -> None:
    """
    Scenario: A positive verdict line containing 'not a false positive' is kept.
    Slice: run_ossprey — negation guard (no bare 'not' suppression)

    Given exit 1, empty OSSBOM, and stdout naming a malicious package while
    disclaiming a false positive,
    When run_ossprey runs,
    Then a red malware finding is emitted (narrow clean-summary patterns only).
    """
    ### Given / When
    stdout = "pkg@1.0 is malicious — this is not a false positive"
    with (
        patch.dict(scanners.os.environ, {"OSSPREY_API_KEY": "ospy_test"}, clear=True),
        patch.object(scanners, "_which", return_value=True),
        patch.object(scanners, "_run", side_effect=_fake_run(1, stdout=stdout)),
    ):
        findings, rows = scanners.run_ossprey(str(tmp_path), "mcp_server")

    ### Then
    assert len(findings) == 1
    assert findings[0]["severity"] == "red"
    assert "malicious" in findings[0]["message"].lower()
    assert rows[0]["status"] == "completed"


def test_given_exit1_negated_verdict_line_when_run_ossprey_then_unreachable(
    tmp_path: Path,
) -> None:
    """
    Scenario: A negated 'no malicious packages' line is not a phantom positive.
    Slice: run_ossprey — negation guard

    Given exit 1, empty OSSBOM, and stdout 'No malicious packages found',
    When run_ossprey runs,
    Then the negation is skipped and the row is unreachable (scan failure).
    """
    ### Given / When
    with (
        patch.dict(scanners.os.environ, {"OSSPREY_API_KEY": "ospy_test"}, clear=True),
        patch.object(scanners, "_which", return_value=True),
        patch.object(
            scanners, "_run", side_effect=_fake_run(1, stdout="No malicious packages found")
        ),
    ):
        findings, rows = scanners.run_ossprey(str(tmp_path), "skill")

    ### Then
    assert findings == []
    assert rows[0]["status"] == "unreachable"


def test_given_timeout_when_run_ossprey_then_unreachable(tmp_path: Path) -> None:
    """
    Scenario: A timed-out scan (code None) with no signal → unreachable.
    Slice: run_ossprey — timeout

    Given Ossprey hits the wall-clock budget on an npm tree,
    When run_ossprey finishes,
    Then the row is unreachable with an operator-facing timeout explanation.
    """
    ### Given
    (tmp_path / "package.json").write_text('{"name":"demo"}', encoding="utf-8")

    ### When
    with (
        patch.dict(scanners.os.environ, {"OSSPREY_API_KEY": "ospy_test"}, clear=True),
        patch.object(scanners, "_which", return_value=True),
        patch.object(scanners, "_run", side_effect=_fake_run(None, stderr="timeout after 100s")),
    ):
        findings, rows = scanners.run_ossprey(str(tmp_path), "mcp_server")

    ### Then
    assert findings == []
    assert rows[0]["status"] == "unreachable"
    detail = rows[0]["detail"]
    assert "timed out after 100s" in detail
    assert "OSSPREY_TIMEOUT" in detail
    assert "package.json" in detail


def test_given_no_sbom_cargo_only_when_run_ossprey_then_not_applicable(
    tmp_path: Path,
) -> None:
    """
    Scenario: Cargo-only tree yields No SBOM → not_applicable, not unreachable.
    Slice: run_ossprey — ecosystem-aware No SBOM

    Given a Rust-only workdir and Ossprey API error 'No SBOM provided',
    When run_ossprey runs,
    Then the row is not_applicable with a Rust/Cargo ecosystem explanation.
    """
    ### Given
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "demo"\n', encoding="utf-8")
    stderr = (
        'error: submit failed (status 400): {"status": "FAILED", '
        '"error": "No SBOM provided", "message": "No SBOM provided"}'
    )

    ### When
    with (
        patch.dict(scanners.os.environ, {"OSSPREY_API_KEY": "ospy_test"}, clear=True),
        patch.object(scanners, "_which", return_value=True),
        patch.object(scanners, "_run", side_effect=_fake_run(1, stderr=stderr)),
    ):
        findings, rows = scanners.run_ossprey(str(tmp_path), "package")

    ### Then
    assert findings == []
    assert rows[0]["status"] == "not_applicable"
    detail = rows[0]["detail"]
    assert "no sbom" in detail.lower()
    assert "Rust/Cargo" in detail
    assert "Python and JavaScript" in detail


def test_given_no_sbom_with_package_json_when_run_ossprey_then_unreachable(
    tmp_path: Path,
) -> None:
    """
    Scenario: No SBOM despite JS manifests stays unreachable (unexpected failure).
    Slice: run_ossprey — No SBOM with catalogueable manifests

    Given package.json is present but Ossprey still returns No SBOM,
    When run_ossprey runs,
    Then the row is unreachable (not not_applicable) with a clear explanation.
    """
    ### Given
    (tmp_path / "package.json").write_text('{"name":"demo"}', encoding="utf-8")
    stderr = 'error: submit failed (status 400): {"message": "No SBOM provided"}'

    ### When
    with (
        patch.dict(scanners.os.environ, {"OSSPREY_API_KEY": "ospy_test"}, clear=True),
        patch.object(scanners, "_which", return_value=True),
        patch.object(scanners, "_run", side_effect=_fake_run(1, stderr=stderr)),
    ):
        findings, rows = scanners.run_ossprey(str(tmp_path), "package")

    ### Then
    assert findings == []
    assert rows[0]["status"] == "unreachable"
    detail = rows[0]["detail"]
    assert "no sbom" in detail.lower()
    assert "package.json" in detail


def test_given_run_ossprey_when_finished_then_temp_ossbom_removed(tmp_path: Path) -> None:
    """
    Scenario: The temp OSSBOM file is always cleaned up in finally.
    Slice: run_ossprey — temp file cleanup

    Given a scan that writes an OSSBOM to the -o path,
    When run_ossprey returns,
    Then that temp file no longer exists on disk.
    """
    ### Given
    captured: dict[str, str] = {}

    def _capture(cmd, timeout=None):
        captured["path"] = cmd[cmd.index("-o") + 1]
        Path(captured["path"]).write_text('{"components": []}', encoding="utf-8")
        return 0, "", ""

    ### When
    with (
        patch.dict(scanners.os.environ, {"OSSPREY_API_KEY": "ospy_test"}, clear=True),
        patch.object(scanners, "_which", return_value=True),
        patch.object(scanners, "_run", side_effect=_capture),
    ):
        scanners.run_ossprey(str(tmp_path), "skill")

    ### Then
    assert captured["path"]
    assert not Path(captured["path"]).exists()


def test_given_cleanup_oserror_when_run_ossprey_then_still_returns(tmp_path: Path) -> None:
    """
    Scenario: A failing temp-file cleanup is swallowed (never crashes the scan).
    Slice: run_ossprey — finally cleanup OSError guard

    Given os.remove raises OSError in the finally block,
    When run_ossprey runs a clean scan,
    Then it still returns a completed row (ADR-0005 never-crash).
    """
    ### Given / When
    with (
        patch.dict(scanners.os.environ, {"OSSPREY_API_KEY": "ospy_test"}, clear=True),
        patch.object(scanners, "_which", return_value=True),
        patch.object(scanners, "_run", side_effect=_fake_run(0)),
        patch.object(scanners.os, "remove", side_effect=OSError("cannot delete")),
    ):
        findings, rows = scanners.run_ossprey(str(tmp_path), "skill")

    ### Then
    assert findings == []
    assert rows[0]["status"] == "completed"


# ---------------------------------------------------------------------------
# OSSBOM parser — both shapes + missing file (pure, no subprocess)
# ---------------------------------------------------------------------------


def test_given_components_envelope_when_parsed_then_finding_and_count() -> None:
    """
    Scenario: The {"components":[...]} shape parses to findings + package count.
    Slice: _parse_ossprey_ossbom — dict envelope
    """
    ### Given
    ossbom = {
        "components": [
            {"name": "mal", "version": "1.2.3", "verdict": "malicious"},
            {"name": "ok", "version": "2.0.0"},
        ]
    }

    ### When
    findings, n = scanners._parse_ossprey_ossbom(ossbom)

    ### Then
    assert n == 2
    assert len(findings) == 1
    assert findings[0]["package_name"] == "mal"
    assert findings[0]["message"] == "mal@1.2.3: malicious"
    assert findings[0]["severity"] == "red"


def test_given_bare_list_ossbom_when_parsed_then_same_contract() -> None:
    """
    Scenario: A bare list-of-components OSSBOM is tolerated identically.
    Slice: _parse_ossprey_ossbom — list shape
    """
    ### Given
    ossbom = [
        {"package": "evil", "version": "9", "malware": True},
        {"name": "fine", "version": "1"},
    ]

    ### When
    findings, n = scanners._parse_ossprey_ossbom(ossbom)

    ### Then
    assert n == 2
    assert len(findings) == 1
    assert findings[0]["package_name"] == "evil"
    assert findings[0]["package_version"] == "9"


def test_given_packages_key_when_parsed_then_also_supported() -> None:
    """
    Scenario: The alternative {"packages":[...]} envelope is tolerated.
    Slice: _parse_ossprey_ossbom — packages key
    """
    ### Given / When
    findings, n = scanners._parse_ossprey_ossbom({"packages": [{"name": "x", "status": "malware"}]})

    ### Then
    assert n == 1
    assert len(findings) == 1
    assert findings[0]["message"] == "x: malware"  # no version → bare name label


@pytest.mark.parametrize("obj", [None, {}, {"components": None}, {"components": 5}, "garbage", 42])
def test_given_missing_or_degenerate_ossbom_when_parsed_then_empty(obj) -> None:
    """
    Scenario: Missing / degenerate OSSBOM shapes parse to (no findings, 0).
    Slice: _parse_ossprey_ossbom — defensive shapes
    """
    ### Given / When / Then
    assert scanners._parse_ossprey_ossbom(obj) == ([], 0)


def test_given_missing_file_when_read_ossbom_then_none() -> None:
    """
    Scenario: A missing OSSBOM path reads back as None (no crash).
    Slice: _read_ossprey_ossbom — missing file
    """
    ### Given / When / Then
    assert scanners._read_ossprey_ossbom("/nonexistent/does-not-exist.json") is None


def test_given_ossbom_file_roundtrip_when_read_then_parses(tmp_path: Path) -> None:
    """
    Scenario: A written OSSBOM file reads + JSON-parses back to its object.
    Slice: _read_ossprey_ossbom — happy path
    """
    ### Given
    path = tmp_path / "ossbom.json"
    path.write_text('{"components": [{"name": "z", "malicious": true}]}', encoding="utf-8")

    ### When
    findings, n = scanners._parse_ossprey_ossbom(scanners._read_ossprey_ossbom(str(path)))

    ### Then
    assert n == 1
    assert findings[0]["package_name"] == "z"


# ---------------------------------------------------------------------------
# Malicious-signal + verdict-line unit coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("comp", "expected"),
    [
        ({"malicious": True}, True),
        ({"malware": True}, True),
        ({"verdict": "MALICIOUS"}, True),
        ({"status": "malware"}, True),
        ({"classification": "  Malicious  "}, True),
        ({"result": "malicious"}, True),
        ({"malicious": False}, False),
        ({"verdict": "clean"}, False),
        ({"verdict": 123}, False),
        ({}, False),
    ],
)
def test_given_component_when_checked_then_malicious_flag(comp, expected) -> None:
    """
    Scenario: Several plausible malicious-flag shapes are recognized (RESEARCH).
    Slice: _ossprey_component_is_malicious
    """
    ### Given / When / Then
    assert scanners._ossprey_component_is_malicious(comp) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("MALWARE DETECTED: evil", "MALWARE DETECTED: evil"),
        ("line one\nmalicious package: bad\nline three", "malicious package: bad"),
        ("No malicious packages found", None),
        ("0 malicious packages", None),
        ("not malicious: all packages verified", None),
        (
            "pkg@1.0 is malicious — this is not a false positive",
            "pkg@1.0 is malicious — this is not a false positive",
        ),
        ("all good here", None),
        ("", None),
        (None, None),
    ],
)
def test_given_stdout_when_scanned_then_verdict_line_or_none(text, expected) -> None:
    """
    Scenario: The verdict-line scan returns the first positive line, skipping
    negations, else None.
    Slice: _ossprey_malware_verdict_line
    """
    ### Given / When / Then
    assert scanners._ossprey_malware_verdict_line(text) == expected


# ---------------------------------------------------------------------------
# Registry integration — Ossprey appended last, both item types
# ---------------------------------------------------------------------------


def test_given_registry_when_inspected_then_ossprey_is_last_and_both() -> None:
    """
    Scenario: Ossprey joins via a registry entry appended after DepShield.
    Slice: registry — Ossprey entry
    """
    ### Given / When
    last = scanners.SCANNER_GROUPS[-1]

    ### Then
    assert last["sources"] == scanners.OSSPREY_SOURCES == ["Ossprey"]
    assert last["applies_to"] == "both"
    assert last["runner"] is scanners._run_ossprey_group


def test_given_group_runner_when_called_then_normalized_triple() -> None:
    """
    Scenario: _run_ossprey_group normalizes to (findings, rows, None).
    Slice: registry — runner adapter
    """
    ### Given / When
    with patch.object(scanners, "run_ossprey", return_value=(["f"], ["r"])) as ossprey:
        result = scanners._run_ossprey_group("/w", "skill", "/w")

    ### Then
    assert result == (["f"], ["r"], None)
    ossprey.assert_called_once_with("/w", "skill")


@pytest.mark.parametrize(("item_type", "target"), [("skill", "/w"), ("mcp_server", "https://x")])
def test_given_any_item_type_when_run_all_then_ossprey_runs_last(
    item_type: str, target: str
) -> None:
    """
    Scenario: Ossprey runs for both item types, always as the final group.
    Slice: registry — dispatch

    Given all other runners mocked,
    When run_all_scanners runs for either item type,
    Then Ossprey is the last start-signalled group and its runner is called with
    (workdir, item_type).
    """
    ### Given
    started: list[list[str]] = []
    ossprey_rows = [{"scanner_source": "Ossprey", "status": "completed", "checks_run": 1}]

    ### When
    with (
        patch.object(scanners, "run_cisco_skill_scanner", return_value=([], [])),
        patch.object(scanners, "run_tessl", return_value=(None, [])),
        patch.object(scanners, "run_cisco_mcp_scanner", return_value=([], [])),
        patch.object(scanners, "run_snyk", return_value=([], [])),
        patch.object(scanners, "run_depshield", return_value=([], [])),
        patch.object(scanners, "run_cargo_audit", return_value=([], [])),
        patch.object(scanners, "run_presend", return_value=([], [])),
        patch.object(scanners, "run_ossprey", return_value=([], ossprey_rows)) as ossprey,
    ):
        result = scanners.run_all_scanners(
            "/w", item_type, target, on_scanner_start=lambda s: started.append(list(s))
        )

    ### Then
    assert started[-1] == ["Ossprey"]
    ossprey.assert_called_once_with("/w", item_type)
    assert result["scanner_rows"] == ossprey_rows
    assert result["overall_status"] == "complete"
