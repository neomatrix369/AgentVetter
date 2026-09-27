"""
Tests for the DepShield adapter (depshield-mcp stdio MCP server).

Author: devansh
Created: 2026-08-15
Scope: report parsing (verbatim lodash 4.17.15 sample), severity/advisory-url
       mapping, manifest discovery, newline-JSON-RPC framing against a scripted
       fake MCP server (real subprocess, NO network), unreachable paths
       (missing binary / handshake garbage / EOF / deadline), isError results,
       not_applicable, and registry integration (DepShield last, both types).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import scanners

# ---------------------------------------------------------------------------
# Fixtures: verbatim report + scripted fake MCP server
# ---------------------------------------------------------------------------

# Verbatim depshield-mcp v1.0.0 audit_project report (lodash 4.17.15, probed
# live 2026-08-15) with all six advisory bullets.
REPORT = """🔍 DEPENDENCY AUDIT REPORT

📁 File: /abs/path/package.json
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 Summary: 1 dependencies scanned
   ✅ Clean: 0
   ⚠️  Vulnerable: 1

📈 Severity Breakdown:
   UNKNOWN: 6

🚨 VULNERABLE DEPENDENCIES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📦 lodash@4.17.15
   • GHSA-29mw-wpgm-hmr9 (UNKNOWN): No summary
   • GHSA-35jh-r3h4-6jhm (UNKNOWN): No summary
   • GHSA-4xc9-xhrj-v574 (UNKNOWN): No summary
   • GHSA-jf85-cpcp-j695 (UNKNOWN): No summary
   • GHSA-p6mc-m468-83gw (UNKNOWN): No summary
   • GHSA-x5rq-j2xg-h7qm (UNKNOWN): No summary

🟡 VERDICT: MODERATE RISK — 1 vulnerable dependencies found. Review and upgrade when possible.
"""

# Scripted fake MCP server: newline-delimited JSON-RPC over stdio, canned
# replies, zero network. Modes: ok | iserror | first_error | hang_calls |
# echo | init_error | call_error. Every initialize response is preceded by a
# log notification so the client's skip-unrelated-messages loop is exercised.
_FAKE_SERVER = r"""
import json, sys, time
mode = sys.argv[1]
report = sys.argv[2] if len(sys.argv) > 2 else ""
calls = 0
for line in sys.stdin:
    msg = json.loads(line)
    if "id" not in msg:
        continue
    if mode == "init_error" or (mode == "call_error" and msg.get("method") != "initialize"):
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg["id"],
                                     "error": {"code": -32603, "message": "boom"}}) + "\n")
        sys.stdout.flush()
        continue
    if msg.get("method") == "initialize":
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/message",
                                     "params": {"level": "info", "data": "booted"}}) + "\n")
        result = {"protocolVersion": "2024-11-05", "capabilities": {},
                  "serverInfo": {"name": "depshield", "version": "0.1.0"}}
    else:
        calls += 1
        if mode == "hang_calls":
            sys.stdout.flush()
            time.sleep(30)
        if mode == "echo":
            args = msg.get("params", {}).get("arguments", {})
            result = {"content": [{"type": "text",
                                   "text": "Summary: 0 dependencies scanned\n" + json.dumps(args)}]}
        elif mode == "malformed_content":
            result = {"content": 5}
        elif mode == "malformed_text":
            result = {"content": [{"type": "text", "text": 42}]}
        elif mode == "empty_result":
            result = {}
        elif mode == "second_garbage" and calls >= 2:
            result = {"content": [{"type": "text", "text": "plain nonsense output"}]}
        elif mode == "iserror" or (mode == "first_error" and calls == 1):
            result = {"isError": True,
                      "content": [{"type": "text",
                                   "text": "MCP error -32602: Invalid arguments"}]}
        else:
            result = {"content": [{"type": "text", "text": report}]}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}) + "\n")
    sys.stdout.flush()
"""


def _fake_cmd(mode: str, report: str = REPORT) -> list[str]:
    return [sys.executable, "-c", _FAKE_SERVER, mode, report]


def _write_package_json(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    manifest = directory / "package.json"
    manifest.write_text('{"dependencies": {"lodash": "4.17.15"}}')
    return manifest


# ---------------------------------------------------------------------------
# Report parsing (pure, no subprocess)
# ---------------------------------------------------------------------------


def test_given_verbatim_report_when_parsed_then_six_amber_findings_and_one_check() -> None:
    """
    Scenario: The real lodash 4.17.15 report maps to 6 amber findings.
    Slice: _parse_depshield_report — verbatim sample

    Given the verbatim depshield-mcp report,
    When it is parsed for manifest fixtures/package.json,
    Then 6 findings carry lodash/4.17.15, UNKNOWN→amber, GHSA advisory URLs,
    and checks_run comes from the Summary line.
    """
    ### Given / When
    findings, checks = scanners._parse_depshield_report(REPORT, "fixtures/package.json")

    ### Then
    assert checks == 1
    assert len(findings) == 6
    first = findings[0]
    assert first["severity"] == "amber", "UNKNOWN advisories must not vanish"
    assert first["category"] == "dependency_vulnerability"
    assert first["scanner_source"] == "DepShield"
    assert first["file_path"] == "fixtures/package.json"
    assert first["package_name"] == "lodash"
    assert first["package_version"] == "4.17.15"
    assert first["cve_ids"] == ["GHSA-29mw-wpgm-hmr9"]
    assert first["advisory_url"] == "https://github.com/advisories/GHSA-29mw-wpgm-hmr9"
    assert first["advisory_provider"] == "osv.dev"
    assert first["message"] == "lodash@4.17.15: GHSA-29mw-wpgm-hmr9 (UNKNOWN): No summary"
    assert {f["severity"] for f in findings} == {"amber"}
    assert [f["cve_ids"][0] for f in findings] == [
        "GHSA-29mw-wpgm-hmr9",
        "GHSA-35jh-r3h4-6jhm",
        "GHSA-4xc9-xhrj-v574",
        "GHSA-jf85-cpcp-j695",
        "GHSA-p6mc-m468-83gw",
        "GHSA-x5rq-j2xg-h7qm",
    ]


def test_given_non_ghsa_and_rated_advisories_when_parsed_then_osv_url_and_red() -> None:
    """
    Scenario: Non-GHSA ids link to osv.dev; CRITICAL/HIGH collapse to red.
    Slice: _parse_depshield_report — severity + advisory url

    Given a report with PYSEC/CVE bullets rated HIGH and LOW,
    When parsed,
    Then HIGH→red with an osv.dev URL and LOW→amber.
    """
    ### Given
    report = (
        "📊 Summary: 2 dependencies scanned\n"
        "📦 requests@2.19.0\n"
        "   • PYSEC-2018-28 (HIGH): Insufficient certificate verification\n"
        "   • CVE-2024-35195 (LOW): Session verify bypass\n"
    )

    ### When
    findings, checks = scanners._parse_depshield_report(report, "requirements.txt")

    ### Then
    assert checks == 2
    assert [f["severity"] for f in findings] == ["red", "amber"]
    assert findings[0]["advisory_url"] == "https://osv.dev/vulnerability/PYSEC-2018-28"
    assert findings[1]["advisory_url"] == "https://osv.dev/vulnerability/CVE-2024-35195"
    assert findings[0]["message"].startswith("requests@2.19.0: PYSEC-2018-28 (HIGH):")


def test_given_drifty_or_degenerate_report_when_parsed_then_tolerant() -> None:
    """
    Scenario: Parsing survives emoji drift, orphan bullets, and no summary.
    Slice: _parse_depshield_report — malformed input

    Given a report with no Summary line and an advisory bullet before any
    package block,
    When parsed,
    Then the orphan bullet is dropped and checks_run falls back to 0.
    """
    ### Given
    orphan = "• GHSA-aaaa-bbbb-cccc (HIGH): orphan before any package\n"
    drift = (
        "SUMMARY: 3 dependencies scanned\n📦 left-pad@1.0.0\n- GHSA-dddd-eeee-ffff (Medium): x\n"
    )

    ### When
    orphan_findings, orphan_checks = scanners._parse_depshield_report(orphan, "package.json")
    drift_findings, drift_checks = scanners._parse_depshield_report(drift, "package.json")

    ### Then
    assert (orphan_findings, orphan_checks) == ([], 0)
    assert drift_checks == 3, "Summary token must match case-insensitively"
    assert len(drift_findings) == 1, "hyphen bullets and mixed-case severities still parse"
    assert drift_findings[0]["severity"] == "amber"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("CRITICAL", "red"),
        ("HIGH", "red"),
        ("high", "red"),
        ("MEDIUM", "amber"),
        ("LOW", "amber"),
        ("UNKNOWN", "amber"),
        ("SOMETHING_ELSE", "amber"),
        ("", "amber"),
        (None, "amber"),
    ],
)
def test_given_severity_token_when_collapsed_then_red_or_amber(raw, expected) -> None:
    """
    Scenario: DepShield severities collapse to red/amber only (never dropped).
    Slice: _depshield_severity
    """
    ### Given / When / Then
    assert scanners._depshield_severity(raw) == expected


# ---------------------------------------------------------------------------
# Manifest discovery
# ---------------------------------------------------------------------------


def test_given_nested_tree_when_discovering_then_skips_vendor_dirs(tmp_path: Path) -> None:
    """
    Scenario: Discovery walks recursively but skips vendor/VCS/venv dirs.
    Slice: _find_manifests — skip dirs

    Given manifests at the root, in a nested dir, and inside skip dirs,
    When _find_manifests walks the tree,
    Then only the root and nested manifests are returned (relative paths).
    """
    ### Given
    _write_package_json(tmp_path)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "requirements.txt").write_text("requests==2.19.0\n")
    (tmp_path / "sub" / "pyproject.toml").write_text("[project]\n")  # unsupported: excluded
    for skip in ("node_modules", ".git", "venv", ".venv", "__pycache__"):
        _write_package_json(tmp_path / skip)

    ### When
    kept, total = scanners._find_manifests(str(tmp_path))

    ### Then
    assert kept == ["package.json", "sub/requirements.txt"]
    assert total == 2


def test_given_more_than_cap_when_discovering_then_capped_with_total(tmp_path: Path) -> None:
    """
    Scenario: Discovery caps the audited list but reports the true total.
    Slice: _find_manifests — cap

    Given 12 manifests spread across subdirectories,
    When _find_manifests walks the tree,
    Then 10 are kept and total_found is 12 so callers can log the truncation.
    """
    ### Given
    for i in range(12):
        _write_package_json(tmp_path / f"pkg{i:02d}")

    ### When
    kept, total = scanners._find_manifests(str(tmp_path))

    ### Then
    assert len(kept) == scanners.DEPSHIELD_MAX_MANIFESTS == 10
    assert total == 12


# ---------------------------------------------------------------------------
# run_depshield against the scripted fake MCP server (real subprocess)
# ---------------------------------------------------------------------------


def test_given_fake_server_when_auditing_one_manifest_then_completed_row(tmp_path: Path) -> None:
    """
    Scenario: Happy path — handshake, audit_project, parsed report.
    Slice: run_depshield — completed

    Given a workdir with one package.json and a fake server replaying the
    verbatim report,
    When run_depshield runs,
    Then a completed row carries checks_run=1, six amber findings with the
    manifest relpath, and console capture of the report.
    """
    ### Given
    _write_package_json(tmp_path)

    ### When
    with patch.object(scanners, "_depshield_cmd", return_value=_fake_cmd("ok")):
        findings, rows = scanners.run_depshield(str(tmp_path), "skill")

    ### Then
    assert len(rows) == 1
    row = rows[0]
    assert row["scanner_source"] == "DepShield"
    assert row["status"] == "completed"
    assert row["checks_run"] == 1
    assert "DEPENDENCY AUDIT REPORT" in row["console_output"]
    assert len(findings) == 6
    assert all(f["file_path"] == "package.json" for f in findings)
    assert all(f["severity"] == "amber" for f in findings)


def test_given_two_manifests_when_auditing_then_checks_summed(tmp_path: Path) -> None:
    """
    Scenario: checks_run is the sum of per-manifest 'dependencies scanned'.
    Slice: run_depshield — multi-manifest

    Given package.json and a nested requirements.txt,
    When run_depshield audits both via the fake server,
    Then checks_run is 2 and findings carry each manifest's relpath.
    """
    ### Given
    _write_package_json(tmp_path)
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "requirements.txt").write_text("requests==2.19.0\n")

    ### When
    with patch.object(scanners, "_depshield_cmd", return_value=_fake_cmd("ok")):
        findings, rows = scanners.run_depshield(str(tmp_path), "mcp_server")

    ### Then
    assert rows[0]["status"] == "completed"
    assert rows[0]["checks_run"] == 2
    assert len(findings) == 12
    assert {f["file_path"] for f in findings} == {"package.json", "api/requirements.txt"}


def test_given_truncated_manifest_list_when_auditing_then_detail_logs_cap(tmp_path: Path) -> None:
    """
    Scenario: Manifest cap is never silent — the row detail names it.
    Slice: run_depshield — truncation detail

    Given 11 manifests (one over the cap),
    When run_depshield completes via the fake server,
    Then the completed row's detail records '10 of 11'.
    """
    ### Given
    for i in range(11):
        _write_package_json(tmp_path / f"pkg{i:02d}")

    ### When
    with patch.object(scanners, "_depshield_cmd", return_value=_fake_cmd("ok")):
        findings, rows = scanners.run_depshield(str(tmp_path), "skill")

    ### Then
    assert rows[0]["status"] == "completed"
    assert rows[0]["checks_run"] == 10
    assert "truncated to 10 of 11" in rows[0]["detail"]
    assert len(findings) == 60


def test_given_echo_server_when_auditing_then_args_match_live_contract(tmp_path: Path) -> None:
    """
    Scenario: audit_project receives filePath (absolute FILE) + dev deps flag.
    Slice: run_depshield — tools/call arguments

    Given a fake server that echoes the received arguments as its report,
    When run_depshield audits one manifest,
    Then the echoed console shows the absolute manifest path under filePath
    and includeDevDependencies=true.
    """
    ### Given
    manifest = _write_package_json(tmp_path)

    ### When
    with patch.object(scanners, "_depshield_cmd", return_value=_fake_cmd("echo")):
        findings, rows = scanners.run_depshield(str(tmp_path), "skill")

    ### Then
    assert rows[0]["status"] == "completed"
    echoed = json.loads(rows[0]["console_output"].splitlines()[-1])
    assert echoed == {"filePath": str(manifest), "includeDevDependencies": True}
    assert findings == []


def test_given_iserror_results_when_all_audits_fail_then_unreachable(tmp_path: Path) -> None:
    """
    Scenario: isError:true on every audit → unreachable, never a crash.
    Slice: run_depshield — isError

    Given a fake server answering every tools/call with isError:true,
    When run_depshield runs,
    Then the row is unreachable and its detail carries the MCP error text.
    """
    ### Given
    _write_package_json(tmp_path)

    ### When
    with patch.object(scanners, "_depshield_cmd", return_value=_fake_cmd("iserror")):
        findings, rows = scanners.run_depshield(str(tmp_path), "skill")

    ### Then
    assert findings == []
    assert rows[0]["status"] == "unreachable"
    assert "MCP error -32602" in rows[0]["detail"]


def test_given_one_bad_manifest_when_others_succeed_then_completed_with_errors(
    tmp_path: Path,
) -> None:
    """
    Scenario: A single failed audit degrades the detail, not the whole row.
    Slice: run_depshield — partial audit errors

    Given two manifests where the first tools/call returns isError,
    When run_depshield runs,
    Then the row completes with the surviving report's findings and the detail
    notes one audit error.
    """
    ### Given
    _write_package_json(tmp_path)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "requirements.txt").write_text("requests==2.19.0\n")

    ### When
    with patch.object(scanners, "_depshield_cmd", return_value=_fake_cmd("first_error")):
        findings, rows = scanners.run_depshield(str(tmp_path), "skill")

    ### Then
    assert rows[0]["status"] == "completed"
    assert rows[0]["checks_run"] == 1
    assert len(findings) == 6
    assert "1 manifest audit error(s)" in rows[0]["detail"]
    assert "MCP error -32602" in rows[0]["detail"]


def test_given_jsonrpc_error_replies_when_running_then_unreachable(tmp_path: Path) -> None:
    """
    Scenario: JSON-RPC error objects (no result) → unreachable, never a crash.
    Slice: run_depshield — error envelopes

    Given fake servers that answer initialize (or tools/call) with an error
    object instead of a result,
    When run_depshield runs,
    Then both shapes map to an unreachable row naming the failing call.
    """
    ### Given
    _write_package_json(tmp_path)

    ### When
    with patch.object(scanners, "_depshield_cmd", return_value=_fake_cmd("init_error")):
        _, init_rows = scanners.run_depshield(str(tmp_path), "skill")
    with patch.object(scanners, "_depshield_cmd", return_value=_fake_cmd("call_error")):
        _, call_rows = scanners.run_depshield(str(tmp_path), "skill")

    ### Then
    assert init_rows[0]["status"] == "unreachable"
    assert "initialize failed" in init_rows[0]["detail"]
    assert call_rows[0]["status"] == "unreachable"
    assert "audit_project failed: boom" in call_rows[0]["detail"]


def test_given_missing_binary_when_running_then_unreachable(tmp_path: Path) -> None:
    """
    Scenario: No depshield-mcp binary and no npx → unreachable row.
    Slice: run_depshield — missing binary
    """
    ### Given
    _write_package_json(tmp_path)

    ### When
    with patch.object(scanners, "_depshield_cmd", return_value=None):
        findings, rows = scanners.run_depshield(str(tmp_path), "skill")

    ### Then
    assert findings == []
    assert rows[0]["status"] == "unreachable"
    assert "not installed" in rows[0]["detail"]


def test_given_no_manifests_when_running_then_not_applicable_without_spawn(
    tmp_path: Path,
) -> None:
    """
    Scenario: Nothing to scan → not_applicable and no child process at all.
    Slice: run_depshield — not_applicable
    """
    ### Given
    cmd_mock = MagicMock()

    ### When
    with patch.object(scanners, "_depshield_cmd", cmd_mock):
        findings, rows = scanners.run_depshield(str(tmp_path), "mcp_server")

    ### Then
    assert findings == []
    assert rows[0]["status"] == "not_applicable"
    assert rows[0]["checks_run"] == 0
    assert "no dependency manifests" in rows[0]["detail"]
    cmd_mock.assert_not_called()


def test_given_garbage_handshake_when_running_then_unreachable(tmp_path: Path) -> None:
    """
    Scenario: Non-JSON stdout during handshake → unreachable.
    Slice: run_depshield — malformed protocol
    """
    ### Given
    _write_package_json(tmp_path)
    garbage_cmd = [
        sys.executable,
        "-c",
        "import sys, time; print('npm WARN this is not json'); sys.stdout.flush(); time.sleep(10)",
    ]

    ### When
    with patch.object(scanners, "_depshield_cmd", return_value=garbage_cmd):
        findings, rows = scanners.run_depshield(str(tmp_path), "skill")

    ### Then
    assert findings == []
    assert rows[0]["status"] == "unreachable"
    assert "non-JSON" in rows[0]["detail"]


def test_given_child_exits_immediately_when_running_then_unreachable(tmp_path: Path) -> None:
    """
    Scenario: Child closes stdout before responding → unreachable, not a hang.
    Slice: run_depshield — EOF during handshake
    """
    ### Given
    _write_package_json(tmp_path)

    ### When
    with patch.object(scanners, "_depshield_cmd", return_value=[sys.executable, "-c", "pass"]):
        findings, rows = scanners.run_depshield(str(tmp_path), "skill")

    ### Then
    assert findings == []
    assert rows[0]["status"] == "unreachable"
    # Either the EOF sentinel (closed stdout) or a broken stdin pipe wins the
    # race with the dying child — both must map to unreachable.
    assert "closed" in rows[0]["detail"]


def test_given_silent_child_when_handshaking_then_deadline_kills_it(tmp_path: Path) -> None:
    """
    Scenario: A hung server hits the handshake deadline; the child is reaped.
    Slice: run_depshield — deadline (no zombie)

    Given a child that sleeps forever and a 1s budget,
    When run_depshield runs,
    Then it returns unreachable within a few seconds instead of hanging.
    """
    ### Given
    _write_package_json(tmp_path)
    sleeper = [sys.executable, "-c", "import time; time.sleep(30)"]

    ### When
    start = time.monotonic()
    with (
        patch.object(scanners, "_depshield_cmd", return_value=sleeper),
        patch.object(scanners, "DEPSHIELD_TIMEOUT", 1),
        patch.object(scanners, "DEPSHIELD_HANDSHAKE_TIMEOUT", 1),
    ):
        findings, rows = scanners.run_depshield(str(tmp_path), "skill")
    elapsed = time.monotonic() - start

    ### Then
    assert findings == []
    assert rows[0]["status"] == "unreachable"
    assert "deadline exceeded" in rows[0]["detail"]
    assert elapsed < 10, "close() must terminate the child, not wait out its sleep"


def test_given_server_hangs_mid_audit_when_deadline_hits_then_unreachable(
    tmp_path: Path,
) -> None:
    """
    Scenario: Handshake succeeds but tools/call hangs → per-call deadline trips.
    Slice: run_depshield — deadline after handshake

    Given a fake server that answers initialize then sleeps on tools/call,
    When the 2s group budget expires,
    Then the row is unreachable, remaining manifests are skipped, and the
    detail says so.
    """
    ### Given
    _write_package_json(tmp_path)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "requirements.txt").write_text("requests==2.19.0\n")

    ### When
    start = time.monotonic()
    with (
        patch.object(scanners, "_depshield_cmd", return_value=_fake_cmd("hang_calls")),
        patch.object(scanners, "DEPSHIELD_TIMEOUT", 2),
    ):
        findings, rows = scanners.run_depshield(str(tmp_path), "skill")
    elapsed = time.monotonic() - start

    ### Then
    assert findings == []
    assert rows[0]["status"] == "unreachable"
    assert "deadline exceeded" in rows[0]["detail"]
    assert "remaining manifests skipped" in rows[0]["detail"]
    assert elapsed < 10


# ---------------------------------------------------------------------------
# _depshield_cmd resolution + client close() edge branches
# ---------------------------------------------------------------------------


def test_given_binary_availability_when_resolving_cmd_then_path_then_npx_then_none() -> None:
    """
    Scenario: Spawn prefers the PATH binary, falls back to npx -y, else None.
    Slice: _depshield_cmd
    """
    ### Given / When / Then
    with patch.object(scanners, "_which", side_effect=lambda b: b == "depshield-mcp"):
        assert scanners._depshield_cmd() == ["depshield-mcp"]
    with patch.object(scanners, "_which", side_effect=lambda b: b == "npx"):
        assert scanners._depshield_cmd() == [
            "npx",
            "-y",
            f"depshield-mcp@{scanners.DEPSHIELD_VERSION}",
        ]
    with patch.object(scanners, "_which", return_value=False):
        assert scanners._depshield_cmd() is None


def test_given_stubborn_child_when_closing_then_killed_after_terminate() -> None:
    """
    Scenario: close() escalates terminate → kill and survives stdin errors.
    Slice: _MCPStdioClient.close — kill escalation
    """
    ### Given — a client shell around a mocked process that ignores terminate
    client = object.__new__(scanners._MCPStdioClient)
    proc = MagicMock()
    proc.stdin.close.side_effect = OSError("already closed")
    proc.wait.side_effect = [subprocess.TimeoutExpired(cmd="fake", timeout=5), None]
    client._proc = proc

    ### When
    client.close()

    ### Then
    proc.terminate.assert_called_once()
    proc.kill.assert_called_once()
    assert proc.wait.call_count == 2


def test_given_expired_deadline_or_dead_stdin_when_client_io_then_mapped_errors() -> None:
    """
    Scenario: Client I/O primitives fail loudly with the mapped error types.
    Slice: _MCPStdioClient — _read_message pre-check + _send broken pipe
    """
    ### Given — a client shell with an empty queue and a dead stdin
    import queue as queue_mod

    client = object.__new__(scanners._MCPStdioClient)
    client._lines = queue_mod.Queue()
    proc = MagicMock()
    proc.stdin.write.side_effect = BrokenPipeError("child died")
    client._proc = proc

    ### When / Then — deadline already in the past → TimeoutError before any read
    with pytest.raises(TimeoutError, match="deadline exceeded"):
        client._read_message(time.monotonic() - 1)

    ### When / Then — writes onto a dead pipe → RuntimeError, never BrokenPipeError
    with pytest.raises(RuntimeError, match="stdin closed"):
        client._send({"jsonrpc": "2.0", "method": "ping"})


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------


def test_given_registry_when_inspected_then_depshield_is_both_before_cargo_audit() -> None:
    """
    Scenario: DepShield joins via a both-type registry entry before Cargo Audit
    and Ossprey.
    Slice: registry — DepShield entry
    """
    ### Given / When
    dep = next(g for g in scanners.SCANNER_GROUPS if g["sources"] == scanners.DEPSHIELD_SOURCES)

    ### Then
    assert dep["sources"] == ["DepShield"]
    assert dep["applies_to"] == "both"
    assert dep["runner"] is scanners._run_depshield_group
    assert scanners.SCANNER_GROUPS[-4] is dep
    assert scanners.SCANNER_GROUPS[-3]["sources"] == scanners.CARGO_AUDIT_SOURCES
    assert scanners.SCANNER_GROUPS[-2]["sources"] == scanners.PRESEND_SOURCES
    assert scanners.SCANNER_GROUPS[-1]["sources"] == scanners.OSSPREY_SOURCES


@pytest.mark.parametrize(("item_type", "target"), [("skill", "/w"), ("mcp_server", "https://x")])
def test_given_any_item_type_when_run_all_then_depshield_before_cargo_and_ossprey(
    item_type: str, target: str
) -> None:
    """
    Scenario: DepShield runs for both item types before Cargo Audit and Ossprey.
    Slice: registry — dispatch

    Given all other runners mocked,
    When run_all_scanners runs for either item type,
    Then DepShield is start-signalled before Cargo Audit; Ossprey closes the list.
    """
    ### Given
    started: list[list[str]] = []
    dep_rows = [{"scanner_source": "DepShield", "status": "completed", "checks_run": 1}]

    ### When
    with (
        patch.object(scanners, "run_cisco_skill_scanner", return_value=([], [])),
        patch.object(scanners, "run_tessl", return_value=(None, [])),
        patch.object(scanners, "run_cisco_mcp_scanner", return_value=([], [])),
        patch.object(scanners, "run_snyk", return_value=([], [])),
        patch.object(scanners, "run_depshield", return_value=([], dep_rows)) as dep,
        patch.object(scanners, "run_cargo_audit", return_value=([], [])),
        patch.object(scanners, "run_presend", return_value=([], [])),
        patch.object(scanners, "run_ossprey", return_value=([], [])),
    ):
        result = scanners.run_all_scanners(
            "/w", item_type, target, on_scanner_start=lambda s: started.append(list(s))
        )

    ### Then
    assert started[-4] == ["DepShield"]
    assert started[-3] == ["Cargo Audit"]
    assert started[-2] == ["Presend"]
    assert started[-1] == ["Ossprey"]
    dep.assert_called_once_with("/w", item_type)
    assert result["scanner_rows"] == dep_rows
    assert result["overall_status"] == "complete"


# ---------------------------------------------------------------------------
# Verifier regression tests (post-review hardening, 2026-08-15)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["malformed_content", "malformed_text", "empty_result"])
def test_given_malformed_result_shapes_when_running_then_unreachable_not_crash(
    tmp_path: Path, mode: str
) -> None:
    """
    Scenario: drifted/buggy server envelopes must degrade, never raise.
    Slice: run_depshield — ADR-0005 never-crash + false-clean rejection

    Given a fake server returning content=5 / text=42 / an empty result,
    When run_depshield runs against one manifest,
    Then it returns an unreachable row (no exception, no completed-0-checks
    false clean) and never a green rollup on zero evidence.
    """
    ### Given
    _write_package_json(tmp_path)

    ### When
    with patch.object(scanners, "_depshield_cmd", return_value=_fake_cmd(mode)):
        findings, rows = scanners.run_depshield(str(tmp_path), "skill")

    ### Then
    assert findings == []
    assert len(rows) == 1
    assert rows[0]["status"] == "unreachable"


def test_given_unparseable_second_report_when_running_then_completed_with_error_note(
    tmp_path: Path,
) -> None:
    """
    Scenario: partial format drift is surfaced, not silently counted clean.
    Slice: run_depshield — false-clean rejection (partial)

    Given two manifests where the second audit returns prose with neither the
    summary token nor a package block,
    When run_depshield runs,
    Then the row is completed with checks from the first manifest only and the
    detail notes one 'unrecognized report format' audit error.
    """
    ### Given
    _write_package_json(tmp_path / "a")
    _write_package_json(tmp_path / "b")

    ### When
    with patch.object(scanners, "_depshield_cmd", return_value=_fake_cmd("second_garbage")):
        findings, rows = scanners.run_depshield(str(tmp_path), "skill")

    ### Then
    row = rows[0]
    assert row["status"] == "completed"
    assert row["checks_run"] == 1
    assert "unrecognized report format" in row["detail"]
    assert len(findings) == 6


def test_given_no_binary_when_falling_back_to_npx_then_version_pinned() -> None:
    """
    Scenario: the npx fallback must not float to latest.
    Slice: _depshield_cmd — version pinning
    """
    ### Given / When
    with patch.object(scanners, "_which", side_effect=lambda name: name == "npx"):
        cmd = scanners._depshield_cmd()

    ### Then
    assert cmd == ["npx", "-y", f"depshield-mcp@{scanners.DEPSHIELD_VERSION}"]


def test_given_image_install_line_when_compared_then_version_matches_constant() -> None:
    """
    Scenario: scan_app.py's baked image and the npx fallback share one version.
    Slice: DEPSHIELD_VERSION — single source of truth
    """
    ### Given
    source = (Path(scanners.__file__).parent / "scan_app.py").read_text()

    ### Then
    assert f"npm install -g depshield-mcp@{scanners.DEPSHIELD_VERSION}" in source


def test_given_eof_sentinel_when_read_repeatedly_then_fails_fast_every_time() -> None:
    """
    Scenario: EOF must not be a one-shot signal; later reads fail fast instead
    of blocking on the drained queue until the group deadline.
    Slice: _MCPStdioClient._read_message — sentinel re-put
    """
    ### Given a child that exits immediately (stdout EOF, generous deadline)
    client = scanners._MCPStdioClient([sys.executable, "-c", "pass"], time.monotonic() + 30)
    try:
        deadline = time.monotonic() + 30

        ### When / Then — both reads raise RuntimeError quickly, not TimeoutError at deadline
        start = time.monotonic()
        with pytest.raises(RuntimeError, match="closed stdout"):
            client._read_message(deadline)
        with pytest.raises(RuntimeError, match="closed stdout"):
            client._read_message(deadline)
        assert time.monotonic() - start < 5
    finally:
        client.close()
