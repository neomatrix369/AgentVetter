"""
Tests for sandbox.scanners overall status, unreachable detail, console capture,
and incremental callback relay.

Author: swami
Created: 2026-08-01
Scope: run_all_scanners overall_status; _unreachable detail truncation;
       _build_console / _truncate_console; on_scanner_done callback relay;
       _completed console_output passthrough;
       Tessl ID context seed after Review Quality (GWT-47.5);
       Tessl Scenario Generation + resume_checkpoint (GWT-49.*);
       Tessl Eval auto-chain + stale + resume (GWT-50.*);
       Tessl Review (Security) adapter (GWT-51.*)
"""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import scanners

# Satisfies whoami + workspace list for Tessl CLI mocks (engteam personal workspace).
_TESSL_WS_RESOLVE_OK = [
    (0, '{"authenticated": true, "user": {"username": "engteam"}}', ""),
    (
        0,
        '{"workspaces": [{"name": "engteam", "id": "ws_eng", '
        '"allowedActions": ["generate_eval_scenarios", "run_review"]}]}',
        "",
    ),
]


def _tessl_workspace_cli_ok(cmd, timeout=None, cwd=None):
    """Satisfy whoami + workspace list for Tessl CLI mocks (engteam personal workspace)."""
    del timeout, cwd
    if len(cmd) > 3 and cmd[3] == "whoami":
        return _TESSL_WS_RESOLVE_OK[0]
    if cmd[3:5] == ["workspace", "list"]:
        return _TESSL_WS_RESOLVE_OK[1]
    return None


def test_given_unreachable_stderr_when_building_row_then_detail_is_capped() -> None:
    """
    Scenario: Unreachable scanner rows carry truncated stderr for the dashboard.
    Slice: _unreachable — detail persistence

    Given a long stderr string from a failed scanner subprocess,
    When _unreachable builds the scan_run_scanners row,
    Then status is unreachable and detail is present and capped at 4000 chars.
    """
    ### Given
    stderr = "x" * 5000

    ### When
    row = scanners._unreachable("Snyk", stderr)

    ### Then
    assert row["status"] == "unreachable"
    assert row["checks_run"] == 0
    assert row["detail"] == "x" * 4000


def test_given_unreachable_with_console_when_building_row_then_console_output_present() -> None:
    """
    Scenario: Unreachable scanner rows also carry raw console output.
    Slice: _unreachable — console_output relay

    Given a stderr and console_output,
    When _unreachable builds the row,
    Then console_output is included in the row.
    """
    ### Given / When
    row = scanners._unreachable("Snyk", "exit 1", console_output="full raw output here")

    ### Then
    assert row["console_output"] == "full raw output here"


def test_given_stdout_and_stderr_when_build_console_then_combined_output() -> None:
    """
    Scenario: _build_console combines stdout and stderr with a separator.
    Slice: _build_console — concatenation

    Given stdout with JSON and stderr with warnings,
    When _build_console is called,
    Then output contains both sections with stderr separator.
    """
    ### Given
    stdout = '{"findings": []}'
    stderr = "npm warn deprecated"

    ### When
    result = scanners._build_console(stdout, stderr)

    ### Then
    assert '{"findings": []}' in result
    assert "--- stderr ---" in result
    assert "npm warn deprecated" in result


def test_given_only_stdout_when_build_console_then_no_stderr_label() -> None:
    """
    Scenario: _build_console with only stdout omits stderr separator.
    Slice: _build_console — stdout-only

    Given stdout text and empty stderr,
    When _build_console is called,
    Then result contains stdout without any stderr label.
    """
    ### Given / When
    result = scanners._build_console("scan complete", "")

    ### Then
    assert result == "scan complete"
    assert "stderr" not in result


def test_given_empty_output_when_build_console_then_none() -> None:
    """
    Scenario: _build_console with empty/whitespace returns None.
    Slice: _build_console — empty input

    Given empty stdout and stderr,
    When _build_console is called,
    Then result is None.
    """
    ### Given / When / Then
    assert scanners._build_console("", "") is None
    assert scanners._build_console("  ", "  ") is None
    assert scanners._build_console(None, None) is None


def test_given_long_text_when_truncate_console_then_head_tail_preserved() -> None:
    """
    Scenario: _truncate_console preserves head and tail of long output.
    Slice: _truncate_console — truncation

    Given text longer than MAX_CONSOLE_CHARS,
    When _truncate_console is called,
    Then head and tail are preserved with an omission marker.
    """
    ### Given
    text = "A" * 1000 + "MIDDLE" + "Z" * 3000

    ### When
    result = scanners._truncate_console(text, max_chars=200)

    ### Then
    assert result is not None
    assert len(result) <= 250, "truncated result should be bounded"
    assert result.startswith("A"), "head must be preserved"
    assert result.endswith("Z"), "tail must be preserved"
    assert "omitted" in result, "must include omission marker"


def test_given_short_text_when_truncate_console_then_unchanged() -> None:
    """
    Scenario: _truncate_console returns short text as-is.
    Slice: _truncate_console — passthrough

    Given text shorter than max,
    When _truncate_console is called,
    Then result is the original text.
    """
    ### Given / When / Then
    assert scanners._truncate_console("short", max_chars=3000) == "short"
    assert scanners._truncate_console(None) is None


def test_given_completed_with_console_when_building_row_then_console_output_in_row() -> None:
    """
    Scenario: Completed scanner rows carry console_output when provided.
    Slice: _completed — console_output relay

    Given findings and console output,
    When _completed builds the row,
    Then detail has the summary and console_output has the raw text.
    """
    ### Given
    findings = [{"severity": "red", "message": "injection"}]
    console = '{"findings": [{"severity": "red"}]}'

    ### When
    row = scanners._completed("Snyk", 1, findings, console_output=console)

    ### Then
    assert row["status"] == "completed"
    assert "1 finding" in row["detail"]
    assert row["console_output"] == console


def test_given_completed_without_console_when_building_row_then_no_console_key() -> None:
    """
    Scenario: Completed scanner rows omit console_output when not provided.
    Slice: _completed — no console_output

    Given no console output,
    When _completed builds the row,
    Then console_output key is absent.
    """
    ### Given / When
    row = scanners._completed("Snyk", 5, [])

    ### Then
    assert "console_output" not in row


def test_given_callback_when_run_all_then_callback_called_per_scanner_group() -> None:
    """
    Scenario: on_scanner_done is called after each scanner group finishes.
    Slice: run_all_scanners — incremental relay

    Given mocked scanners and an on_scanner_done callback,
    When run_all_scanners runs for a skill,
    Then the callback is called once per scanner group with findings+rows.
    """
    ### Given
    cisco_findings = [{"severity": "red", "message": "test", "scanner_source": "Cisco"}]
    cisco_rows = [{"scanner_source": "Cisco", "status": "completed", "checks_run": 1}]
    tessl_rows = [{"scanner_source": "Tessl", "status": "completed", "checks_run": 1}]
    snyk_rows = [{"scanner_source": "Snyk", "status": "completed", "checks_run": 1}]
    depshield_rows = [{"scanner_source": "DepShield", "status": "completed", "checks_run": 1}]
    cargo_rows = [{"scanner_source": "Cargo Audit", "status": "completed", "checks_run": 1}]
    ossprey_rows = [{"scanner_source": "Ossprey", "status": "completed", "checks_run": 1}]
    callback_calls = []

    def on_done(findings, rows, quality_score=None):
        callback_calls.append({"findings": findings, "rows": rows, "quality_score": quality_score})

    ### When
    with (
        patch.object(
            scanners, "run_cisco_skill_scanner", return_value=(cisco_findings, cisco_rows)
        ),
        patch.object(scanners, "run_tessl", return_value=(85.0, tessl_rows)),
        patch.object(scanners, "run_snyk", return_value=([], snyk_rows)),
        patch.object(scanners, "run_depshield", return_value=([], depshield_rows)),
        patch.object(scanners, "run_cargo_audit", return_value=([], cargo_rows)),
        patch.object(scanners, "run_presend", return_value=([], [])),
        patch.object(scanners, "run_ossprey", return_value=([], ossprey_rows)),
    ):
        result = scanners.run_all_scanners(
            "/tmp/skill", "skill", "/tmp/skill", on_scanner_done=on_done
        )

    ### Then
    assert len(callback_calls) == 7, (
        "must call back once per scanner group "
        "(Cisco, Tessl, Snyk, DepShield, Cargo Audit, Presend, Ossprey)"
    )

    assert callback_calls[0]["findings"] == cisco_findings
    assert callback_calls[0]["rows"] == cisco_rows
    assert callback_calls[0]["quality_score"] is None

    assert callback_calls[1]["rows"] == tessl_rows
    assert callback_calls[1]["quality_score"] == 85.0

    assert callback_calls[2]["rows"] == snyk_rows

    assert callback_calls[3]["rows"] == depshield_rows

    assert callback_calls[4]["rows"] == cargo_rows

    assert callback_calls[5]["rows"] == []

    assert callback_calls[6]["rows"] == ossprey_rows

    assert result["overall_status"] == "complete"
    assert result["quality_score"] == 85.0


def test_given_no_callback_when_run_all_then_works_unchanged() -> None:
    """
    Scenario: run_all_scanners without callback preserves backward compat.
    Slice: run_all_scanners — no callback

    Given mocked scanners and no callback,
    When run_all_scanners runs,
    Then results are returned normally without error.
    """
    ### Given / When
    with (
        patch.object(
            scanners,
            "run_cisco_mcp_scanner",
            return_value=([], [{"scanner_source": "YARA", "status": "completed", "checks_run": 1}]),
        ),
        patch.object(
            scanners,
            "run_snyk",
            return_value=([], [{"scanner_source": "Snyk", "status": "completed", "checks_run": 1}]),
        ),
        patch.object(scanners, "run_depshield", return_value=([], [])),
        patch.object(scanners, "run_cargo_audit", return_value=([], [])),
        patch.object(scanners, "run_presend", return_value=([], [])),
        patch.object(scanners, "run_ossprey", return_value=([], [])),
    ):
        result = scanners.run_all_scanners("/tmp/mcp", "mcp_server", "https://example.com")

    ### Then
    assert result["overall_status"] == "complete"
    assert len(result["scanner_rows"]) == 2


def test_given_cisco_complete_and_tessl_unreachable_when_run_all_then_partial_failed() -> None:
    """
    Scenario: Any unreachable engine yields partial-failed overall status.
    Slice: run_all_scanners — overall_status

    Given Cisco completed and Tessl/Snyk unreachable for a skill,
    When run_all_scanners aggregates results,
    Then overall_status is partial-failed and findings from Cisco are retained.
    """
    ### Given
    cisco_findings = [
        {
            "severity": "red",
            "category": "prompt_injection",
            "message": "injection",
            "scanner_source": "Cisco Skill Scanner: static/bytecode/pipeline",
        }
    ]
    cisco_rows = [
        {
            "scanner_source": "Cisco Skill Scanner: static/bytecode/pipeline",
            "status": "completed",
            "checks_run": 3,
        }
    ]

    ### When
    with (
        patch.object(
            scanners, "run_cisco_skill_scanner", return_value=(cisco_findings, cisco_rows)
        ),
        patch.object(
            scanners,
            "run_tessl",
            return_value=(None, [scanners._unreachable("Tessl: Review (Quality)", "node too old")]),
        ),
        patch.object(
            scanners,
            "run_snyk",
            return_value=([], [scanners._unreachable("Snyk", "cold install failed")]),
        ),
        patch.object(scanners, "run_depshield", return_value=([], [])),
        patch.object(scanners, "run_ossprey", return_value=([], [])),
    ):
        result = scanners.run_all_scanners("/tmp/skill", "skill", "/tmp/skill")

    ### Then
    assert result["overall_status"] == "partial-failed"
    assert len(result["findings"]) == 1
    assert result["findings"][0]["severity"] == "red"
    tessl = next(
        r for r in result["scanner_rows"] if r["scanner_source"] == "Tessl: Review (Quality)"
    )
    assert tessl["detail"] == "node too old"


def test_given_all_engines_completed_when_run_all_then_complete() -> None:
    """
    Scenario: All engines completed → overall_status complete.
    Slice: run_all_scanners — happy path

    Given every scanner row is completed,
    When run_all_scanners aggregates,
    Then overall_status is complete.
    """
    ### Given / When
    with (
        patch.object(
            scanners,
            "run_cisco_skill_scanner",
            return_value=(
                [],
                [{"scanner_source": "Cisco", "status": "completed", "checks_run": 1}],
            ),
        ),
        patch.object(
            scanners,
            "run_tessl",
            return_value=(
                0.9,
                [{"scanner_source": "Tessl", "status": "completed", "checks_run": 1}],
            ),
        ),
        patch.object(
            scanners,
            "run_snyk",
            return_value=([], [{"scanner_source": "Snyk", "status": "completed", "checks_run": 1}]),
        ),
        patch.object(
            scanners,
            "run_depshield",
            return_value=(
                [],
                [{"scanner_source": "DepShield", "status": "completed", "checks_run": 1}],
            ),
        ),
        patch.object(
            scanners,
            "run_ossprey",
            return_value=(
                [],
                [{"scanner_source": "Ossprey", "status": "completed", "checks_run": 1}],
            ),
        ),
    ):
        result = scanners.run_all_scanners("/tmp/skill", "skill", "/tmp/skill")

    ### Then
    assert result["overall_status"] == "complete"
    assert result["quality_score"] == 0.9


# --- slice-42 A4: Tessl quality_score parsing and diagnostic logging ---


def test_tessl_quality_score_known_shapes_return_float() -> None:
    """
    Scenario: _tessl_quality_score extracts a float from each supported CLI output shape.
      Given a parsed JSON object in the "score" shape, "reviewScore" shape, or "normalizedScore" shape
      When _tessl_quality_score is called
      Then a non-None float is returned for each known shape

    Slice: 42 / A4 — Tessl quality_score extraction coverage
    """
    ### Given / When / Then — score key
    assert scanners._tessl_quality_score({"score": 72}) == 72

    ### Given / When / Then — reviewScore inside "review" object
    assert scanners._tessl_quality_score({"review": {"reviewScore": 68.5}}) == 68.5

    ### Given / When / Then — normalizedScore averaged across judge keys
    result = scanners._tessl_quality_score(
        {
            "descriptionJudge": {"normalizedScore": 0.8},
            "contentJudge": {"normalizedScore": 0.6},
        }
    )
    assert result is not None
    assert abs(result - 70.0) < 0.001, f"Expected 70.0 got {result}"


def test_tessl_quality_score_unknown_shape_returns_none() -> None:
    """
    Scenario: _tessl_quality_score returns None (no crash) for an unknown JSON shape.
      Given a parsed JSON object with none of the recognised score keys
      When _tessl_quality_score is called
      Then None is returned

    Slice: 42 / A4 — Tessl quality_score unknown shape guard
    """
    ### Given
    unknown_shape = {"someOtherKey": 99, "nested": {"value": 42}}

    ### When
    result = scanners._tessl_quality_score(unknown_shape)

    ### Then
    assert result is None


def test_run_tessl_logs_diagnostic_when_score_is_none(capsys) -> None:
    """
    Scenario: run_tessl prints a diagnostic line when _tessl_quality_score returns None.
      Given TESSL_TOKEN set, npx available, lint exits 0, review exits 0 with unknown JSON
      When run_tessl is called
      Then a [tessl] diagnostic line is printed containing the raw output prefix
      And the function returns (None, [lint_completed, review_unreachable]) without crashing

    Slice: 42 / A4 — Tessl diagnostic logging on score extraction failure
    """
    ### Given
    lint_output = "12 checks — 0 findings"
    unknown_json_output = '{"unexpectedKey": "no score here"}'

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "fake-token"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(
            scanners,
            "_run",
            side_effect=[
                (0, lint_output, ""),
                (0, unknown_json_output, ""),
                (0, '{"id": "sec_from_run"}', ""),
                (0, '{"id": "sec_rev_def456"}', ""),
            ],
        ),
    ):
        score, rows = scanners.run_tessl("/tmp/fake-skill")

    ### Then
    assert score is None
    assert len(rows) == 5
    lint_row, review_row, scenario_row, eval_row, _security_row = rows
    assert lint_row["scanner_source"] == "Tessl: Lint"
    assert lint_row["status"] == "completed"
    assert review_row["scanner_source"] == "Tessl: Review (Quality)"
    assert review_row["status"] == "unreachable"
    assert scenario_row["scanner_source"] == "Tessl: Scenario Generation"
    assert scenario_row["status"] == "failed"
    assert eval_row["scanner_source"] == "Tessl: Eval"
    assert eval_row["status"] == "blocked"
    captured = capsys.readouterr()
    assert "[tessl]" in captured.out
    assert "quality_score extraction failed" in captured.out


# --- slice-46: Tessl Lint Adapter (Row 1) ---


def test_run_tessl_without_token_emits_lint_completed_and_review_needs_setup() -> None:
    """
    Scenario: TESSL_TOKEN absent — Lint runs, Review (Quality) is needs_setup.
      Given TESSL_TOKEN is absent from the environment
      When run_tessl is called with npx available and lint exits 0
      Then a Tessl: Lint row with status completed is returned
      And a Tessl: Review (Quality) row with status needs_setup is returned
      And quality_score is None

    Slice: 46 — GWT-46.2 lint auth-free / review needs_setup
    """
    ### Given
    lint_output = "12 checks — 0 findings"

    ### When
    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", return_value=(0, lint_output, "")),
    ):
        score, rows = scanners.run_tessl("/tmp/fake-skill")

    ### Then
    assert score is None
    assert len(rows) == 5
    lint_row, review_row, scenario_row, eval_row, security_row = rows
    assert lint_row["scanner_source"] == "Tessl: Lint"
    assert lint_row["status"] == "completed"
    assert lint_row["checks_run"] == 12
    assert "12 checks" in lint_row["detail"]
    assert lint_row.get("tessl_run_id") is None
    assert review_row["scanner_source"] == "Tessl: Review (Quality)"
    assert review_row["status"] == "needs_setup"
    assert scenario_row["scanner_source"] == "Tessl: Scenario Generation"
    assert scenario_row["status"] == "needs_setup"
    assert eval_row["scanner_source"] == "Tessl: Eval"
    assert eval_row["status"] == "blocked"
    assert security_row["scanner_source"] == "Tessl: Review (Security)"
    assert security_row["status"] == "needs_setup"


def test_run_tessl_with_token_emits_lint_and_review_rows() -> None:
    """
    Scenario: TESSL_TOKEN present — both Lint and Review (Quality) rows returned.
      Given TESSL_TOKEN is present and both subprocess calls succeed
      When run_tessl is called
      Then lint row is completed at position 0
      And review row is completed at position 1 with quality_score extracted
      And quality_score is returned as a float

    Slice: 46 — GWT-46.1 lint row present with token
    """
    ### Given
    lint_output = "8 checks — 2 findings"
    review_json = '{"score": 75}'

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "tok-abc"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(
            scanners,
            "_run",
            side_effect=[
                (0, lint_output, ""),
                (0, review_json, ""),
                (0, '{"id": "rev_abc123", "score": 75}', ""),
                (0, '{"id": "sec_from_run"}', ""),
                (0, '{"id": "sec_rev_def456"}', ""),
            ],
        ),
    ):
        score, rows = scanners.run_tessl("/tmp/fake-skill")

    ### Then
    assert score == 75
    assert len(rows) == 5
    lint_row, review_row, scenario_row, eval_row, security_row = rows
    assert lint_row["scanner_source"] == "Tessl: Lint"
    assert lint_row["status"] == "completed"
    assert lint_row.get("tessl_run_id") is None
    assert review_row["scanner_source"] == "Tessl: Review (Quality)"
    assert review_row["status"] == "completed"
    assert review_row["tessl_run_id"] == "rev_abc123"
    assert review_row["tessl_run_id_at"]
    assert scenario_row["scanner_source"] == "Tessl: Scenario Generation"
    assert scenario_row["status"] == "failed"
    assert eval_row["scanner_source"] == "Tessl: Eval"
    assert eval_row["status"] == "blocked"
    assert security_row["scanner_source"] == "Tessl: Review (Security)"
    assert security_row["status"] == "completed"
    sources = {row["scanner_source"] for row in rows}
    assert "Tessl: Eval" in sources
    assert "Tessl: Review (Security)" in sources


def test_run_tessl_lint_failure_emits_failed_row() -> None:
    """
    Scenario: Lint subprocess exits non-zero — row status is failed.
      Given TESSL_TOKEN absent (so only lint runs), npx available, lint exits 1
      When run_tessl is called
      Then the Tessl: Lint row has status failed
      And the review row has status needs_setup

    Slice: 46 — GWT-46.1 lint failed row
    """
    ### Given / When
    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", return_value=(1, "", "lint process crashed")),
    ):
        score, rows = scanners.run_tessl("/tmp/fake-skill")

    ### Then
    assert score is None
    lint_row, review_row, scenario_row, eval_row, security_row = rows
    assert lint_row["scanner_source"] == "Tessl: Lint"
    assert lint_row["status"] == "failed"
    assert review_row["scanner_source"] == "Tessl: Review (Quality)"
    assert review_row["status"] == "needs_setup"
    assert scenario_row["scanner_source"] == "Tessl: Scenario Generation"
    assert scenario_row["status"] == "needs_setup"
    assert eval_row["scanner_source"] == "Tessl: Eval"
    assert eval_row["status"] == "blocked"
    assert security_row["scanner_source"] == "Tessl: Review (Security)"
    assert security_row["status"] == "needs_setup"


def test_run_tessl_no_npx_emits_lint_unreachable() -> None:
    """
    Scenario: npx missing — Lint row is unreachable.
      Given npx is not on PATH and TESSL_TOKEN absent
      When run_tessl is called
      Then the Tessl: Lint row has status unreachable
      And the review row has status needs_setup

    Slice: 46 — GWT-46.1 lint unreachable when npx absent
    """
    ### Given / When
    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(scanners, "_which", return_value=None),
    ):
        score, rows = scanners.run_tessl("/tmp/fake-skill")

    ### Then
    assert score is None
    assert len(rows) == 5
    lint_row, review_row, scenario_row, eval_row, security_row = rows
    assert lint_row["scanner_source"] == "Tessl: Lint"
    assert lint_row["status"] == "unreachable"
    assert review_row["scanner_source"] == "Tessl: Review (Quality)"
    assert review_row["status"] == "needs_setup"
    assert scenario_row["scanner_source"] == "Tessl: Scenario Generation"
    assert scenario_row["status"] == "needs_setup"
    assert eval_row["scanner_source"] == "Tessl: Eval"
    assert eval_row["status"] == "blocked"
    assert security_row["scanner_source"] == "Tessl: Review (Security)"
    assert security_row["status"] == "needs_setup"


def test_parse_tessl_lint_detail_extracts_count_from_text() -> None:
    """
    Scenario: _parse_tessl_lint_detail extracts check count from common output patterns.
      Given lint output containing "12 checks", "3 warnings", or "0 findings"
      When _parse_tessl_lint_detail is called
      Then checks_run is the leading digit and detail is the first 500 chars

    Slice: 46 — GWT-46.3 lint counts parsed
    """
    ### Given / When / Then
    checks_run, detail = scanners._parse_tessl_lint_detail("12 checks — 0 findings")
    assert checks_run == 12
    assert "12 checks" in detail

    checks_run2, _ = scanners._parse_tessl_lint_detail("3 warnings found")
    assert checks_run2 == 3

    checks_run3, detail3 = scanners._parse_tessl_lint_detail("")
    assert checks_run3 is None
    assert detail3 == "lint completed — no output"


def test_parse_tessl_lint_detail_live_valid_plugin_counts_one_check() -> None:
    """
    Scenario: live tessl skill lint success has no numeric count.
      Given stdout captured 2026-08-24 from `tessl skill lint` on a plugin package
      When _parse_tessl_lint_detail is called
      Then checks_run is 1 (one package validation ran) and detail keeps the valid line

    Slice: 46 — GWT-46.3 live completed path (plugin-is-valid stdout)
    """
    ### Given
    live_stdout = "✔ Plugin tripwire/safe-changelog-writer@0.0.1 is valid"

    ### When
    checks_run, detail = scanners._parse_tessl_lint_detail(live_stdout)

    ### Then
    assert checks_run == 1
    assert "is valid" in detail.lower()


def test_parse_tessl_run_id_from_common_json_shapes() -> None:
    """
    Scenario: _parse_tessl_run_id reads id / runId / nested review.id.
    Slice: 47 — GWT-47.1 tessl_run_id capture

    Given Tessl --json objects with drifting id keys,
    When _parse_tessl_run_id is called,
    Then the run id string is returned (or None when absent).
    """
    ### Given / When / Then
    assert scanners._parse_tessl_run_id({"id": "rev_abc123"}) == "rev_abc123"
    assert scanners._parse_tessl_run_id({"runId": "rev_xyz"}) == "rev_xyz"
    assert scanners._parse_tessl_run_id({"run_id": "rev_under"}) == "rev_under"
    assert scanners._parse_tessl_run_id({"review": {"id": "rev_nested"}}) == "rev_nested"
    assert scanners._parse_tessl_run_id({"score": 70}) is None
    assert scanners._parse_tessl_run_id(None) is None


def test_run_tessl_review_quality_invokes_review_run_quality() -> None:
    """
    Scenario: Quality review uses tessl review run quality, not skill review.
    Slice: 47 — GWT-47.4 parameterised judge_type=quality

    Given TESSL_TOKEN is set,
    When run_tessl is called,
    Then the review subprocess is tessl review run quality --json --workspace,
    And the row is Tessl: Review (Quality) only.
    """
    ### Given
    captured: list[list[str]] = []

    def _capture_run(cmd, timeout=None, cwd=None):
        resolved = _tessl_workspace_cli_ok(cmd, timeout, cwd)
        if resolved is not None:
            return resolved
        captured.append(cmd)
        if cmd[3:5] == ["skill", "lint"]:
            return 0, "1 check", ""
        if cmd[3:6] == ["review", "run", "quality"]:
            return 0, '{"score": 80, "id": "rev_from_run"}', ""
        if cmd[3:6] == ["review", "view", "--last"]:
            return 0, '{"id": "rev_from_view", "score": 80}', ""
        eval_handled = _eval_ok(cmd, timeout, cwd)
        if eval_handled is not None:
            return eval_handled
        raise AssertionError(f"unexpected cmd: {cmd}")

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_capture_run),
    ):
        score, rows = scanners.run_tessl("/tmp/fake-skill")

    ### Then
    assert score == 80
    quality_cmds = [c for c in captured if c[3:6] == ["review", "run", "quality"]]
    assert len(quality_cmds) == 1, f"Quality review should run once; got {quality_cmds!r}"
    assert quality_cmds[0][5] == "quality"
    assert "--workspace" in quality_cmds[0]
    assert "engteam" in quality_cmds[0]
    assert rows[1]["scanner_source"] == "Tessl: Review (Quality)"
    assert rows[4]["scanner_source"] == "Tessl: Review (Security)"


def test_run_tessl_captures_run_id_from_view_last_json() -> None:
    """
    Scenario: tessl_run_id comes from tessl review view --last --json.
    Slice: 47 — GWT-47.1

    Given review run JSON has a different id than view --last,
    When run_tessl completes,
    Then tessl_run_id is the view --last id and tessl_run_id_at is set.
    """
    ### Given
    lint_output = "4 checks"
    run_json = '{"score": 64, "id": "rev_from_run"}'
    view_json = '{"score": 64, "id": "rev_from_view"}'

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(
            scanners,
            "_run",
            side_effect=[
                (0, lint_output, ""),
                (0, run_json, ""),
                (0, view_json, ""),
                (0, '{"id": "sec_from_run"}', ""),
                (0, '{"id": "sec_rev_def456"}', ""),
            ],
        ),
    ):
        _score, rows = scanners.run_tessl("/tmp/fake-skill")

    ### Then
    review_row = rows[1]
    assert review_row["scanner_source"] == "Tessl: Review (Quality)"
    assert review_row["tessl_run_id"] == "rev_from_view"
    assert review_row["tessl_run_id_at"]
    assert "T" in review_row["tessl_run_id_at"]


def test_run_tessl_falls_back_to_run_json_id_when_view_last_fails() -> None:
    """
    Scenario: view --last failure still stamps tessl_run_id from run --json.
    Slice: 47 — GWT-47.1 fallback

    Given review run JSON includes id and view --last exits non-zero,
    When run_tessl completes,
    Then tessl_run_id is the run JSON id.
    """
    ### Given / When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(
            scanners,
            "_run",
            side_effect=[
                (0, "1 check", ""),
                (0, '{"score": 50, "id": "rev_run_only"}', ""),
                (1, "", "view failed"),
                (0, '{"id": "sec_from_run"}', ""),
                (0, '{"id": "sec_rev_def456"}', ""),
            ],
        ),
    ):
        _score, rows = scanners.run_tessl("/tmp/fake-skill")

    ### Then
    assert rows[1]["tessl_run_id"] == "rev_run_only"


def test_run_tessl_without_workspace_emits_review_needs_setup() -> None:
    """
    Scenario: Workspace unresolved — Review (Quality) and Scenario Gen are needs_setup.
    Slice: 47 — GWT-47.3 needs_setup when workspace cannot be resolved
    Slice: 49/50 — scenario generate also needs a resolved --workspace

    Given TESSL_TOKEN is set and workspace list fails,
    When run_tessl is called,
    Then Review (Quality) and Scenario Generation are needs_setup and no review/generate runs.
    """
    ### Given
    ran: list[list[str]] = []

    def _record(cmd, timeout=None, cwd=None):
        ran.append(cmd)
        if cmd[3] == "whoami" or cmd[3:5] == ["workspace", "list"]:
            return 1, "", "not authenticated"
        return 0, "1 check", ""

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}, clear=True),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_record),
    ):
        score, rows = scanners.run_tessl("/tmp/fake-skill")

    ### Then
    assert score is None
    assert rows[1]["scanner_source"] == "Tessl: Review (Quality)"
    assert rows[1]["status"] == "needs_setup"
    assert rows[2]["scanner_source"] == "Tessl: Scenario Generation"
    assert rows[2]["status"] == "needs_setup"
    assert rows[4]["scanner_source"] == "Tessl: Review (Security)"
    assert rows[4]["status"] == "needs_setup"
    assert all(c[3:5] != ["review", "run"] for c in ran)
    assert all(c[3:5] != ["scenario", "generate"] for c in ran)


def test_run_tessl_resolves_workspace_from_whoami_when_env_unset(tmp_path) -> None:
    """
    Scenario: Resolve personal workspace via whoami + list.
    Given TESSL_TOKEN only and CLI returns username-matching workspace,
    When run_tessl runs Review,
    Then --workspace uses the username from whoami (not an env var).
    """
    ### Given
    workdir = _make_tessl_plugin(tmp_path)
    captured: list[list[str]] = []

    def _run(cmd, timeout=None, cwd=None):
        captured.append(cmd)
        if cmd[3] == "whoami":
            return 0, '{"authenticated": true, "user": {"username": "neomatrix369"}}', ""
        if cmd[3:5] == ["workspace", "list"]:
            return (
                0,
                json.dumps(
                    {
                        "workspaces": [
                            {"name": "other", "allowedActions": ["view"]},
                            {
                                "name": "neomatrix369",
                                "allowedActions": [
                                    "generate_eval_scenarios",
                                    "run_review",
                                ],
                            },
                        ]
                    }
                ),
                "",
            )
        if cmd[3:5] in (["skill", "lint"],) or cmd[3:5] == ["review", "run"]:
            return _lint_and_quality_ok(cmd, timeout)
        if len(cmd) > 5 and cmd[3:5] == ["review", "view"]:
            return _lint_and_quality_ok(cmd, timeout)
        if cmd[3:5] == ["scenario", "generate"]:
            assert cmd[cmd.index("--workspace") + 1] == "neomatrix369"
            return 0, '{"id": "gen_ws", "status": "completed", "scenarioCount": 1}', ""
        if cmd[3:5] == ["scenario", "download"]:
            out_dir = cmd[cmd.index("-o") + 1]
            os.makedirs(os.path.join(out_dir, "s1"), exist_ok=True)
            return 0, "ok", ""
        eval_handled = _eval_ok(cmd, timeout, cwd)
        if eval_handled is not None:
            return eval_handled
        raise AssertionError(f"unexpected cmd: {cmd}")

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}, clear=True),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
    ):
        score, rows = scanners.run_tessl(workdir)

    ### Then
    assert score == 80
    review_cmds = [c for c in captured if c[3:5] == ["review", "run"]]
    assert review_cmds
    assert review_cmds[0][review_cmds[0].index("--workspace") + 1] == "neomatrix369"
    assert rows[2]["status"] == "completed"


def test_given_quality_review_completes_when_run_tessl_then_ctx_review_quality_is_stamped_id() -> (
    None
):
    """
    Scenario: Quality Review run ID seeds in-process Tessl ID context.
    Slice: 47 — GWT-47.5 _TesslIdContext after Quality stamp

    Given run_tessl initialises ctx with review_quality and scenario_gen as None,
    When Quality Review completes and stamps tessl_run_id,
    Then ctx["review_quality"] is that run ID for downstream steps in this invocation,
    And Lint stays outside the ID chain (no tessl_run_id; no ctx update from Lint).
    """
    ### Given
    ctx = scanners._new_tessl_id_context()
    lint_output = "4 checks"
    run_json = '{"score": 64, "id": "rev_from_run"}'
    view_json = '{"score": 64, "id": "rev_from_view"}'

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(
            scanners,
            "_run",
            side_effect=[
                (0, lint_output, ""),
                (0, run_json, ""),
                (0, view_json, ""),
                (0, '{"id": "sec_from_run"}', ""),
                (0, '{"id": "sec_rev_def456"}', ""),
            ],
        ),
    ):
        _score, rows = scanners.run_tessl("/tmp/fake-skill", id_context=ctx)

    ### Then
    expected_run_id = "rev_from_view"
    actual_ctx_quality = ctx["review_quality"]
    assert actual_ctx_quality == expected_run_id, (
        f"ctx['review_quality'] should carry the stamped Quality run ID; got {actual_ctx_quality!r}"
    )
    assert ctx["scenario_gen"] is None, (
        "scenario_gen stays None without a successful Scenario Generation stamp"
    )
    lint_row = rows[0]
    assert lint_row["scanner_source"] == "Tessl: Lint"
    assert lint_row.get("tessl_run_id") is None, (
        "Lint is outside the Tessl ID chain — tessl_run_id must stay unset"
    )


def test_given_review_needs_setup_when_run_tessl_then_ctx_review_quality_stays_none() -> None:
    """
    Scenario: Missing Review credentials leave Tessl ID context unseeded for Quality.
    Slice: 47 — GWT-47.5 ctx stays null when Quality does not stamp

    Given TESSL_TOKEN is absent,
    When run_tessl runs Lint then marks Review needs_setup,
    Then ctx["review_quality"] stays None,
    And Lint still has no tessl_run_id.
    """
    ### Given
    ctx = scanners._new_tessl_id_context()

    ### When
    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", return_value=(0, "1 check", "")),
    ):
        _score, rows = scanners.run_tessl("/tmp/fake-skill", id_context=ctx)

    ### Then
    assert ctx["review_quality"] is None, (
        "Quality run ID must not be invented when Review is needs_setup"
    )
    assert ctx["scenario_gen"] is None, (
        "scenario_gen stays None when Scenario Generation is needs_setup"
    )
    assert rows[0].get("tessl_run_id") is None, (
        "Lint remains outside the ID chain when Review is skipped"
    )


def test_given_empty_state_when_new_tessl_id_context_then_quality_and_scenario_keys_are_none() -> (
    None
):
    """
    Scenario: Tessl ID context starts with Quality and scenario_gen unset.
    Slice: 47 — GWT-47.5 _TesslIdContext seed shape

    Given no prior Tessl step has run,
    When _new_tessl_id_context is called,
    Then review_quality and scenario_gen are present and None.
    """
    ### Given / When
    actual_ctx = scanners._new_tessl_id_context()

    ### Then
    expected_ctx = {"review_quality": None, "scenario_gen": None}
    assert actual_ctx == expected_ctx, f"Seed ctx must be {expected_ctx!r}, got {actual_ctx!r}"


# --- slice-49: Tessl Scenario Generation + Resume Checkpoint (Row 3) ---


def _make_tessl_plugin(tmp_path) -> str:
    plugin_dir = tmp_path / "plugin"
    plugin_dir.mkdir()
    manifest_dir = plugin_dir / ".tessl-plugin"
    manifest_dir.mkdir()
    (manifest_dir / "plugin.json").write_text('{"name":"demo","version":"0.0.1"}')
    (plugin_dir / "tessl.json").write_text('{"project":"demo"}')
    return str(plugin_dir)


def _lint_and_quality_ok(cmd, timeout=None, cwd=None):
    resolved = _tessl_workspace_cli_ok(cmd, timeout, cwd)
    if resolved is not None:
        return resolved
    del timeout, cwd
    if cmd[3:5] == ["skill", "lint"]:
        return 0, "1 check", ""
    if cmd[3:6] == ["review", "run", "quality"]:
        return 0, '{"score": 80, "id": "rev_from_run"}', ""
    if cmd[3:6] == ["review", "run", "security"]:
        return 0, '{"id": "sec_from_run"}', ""
    if cmd[3:6] == ["review", "view", "--last"]:
        return 0, '{"id": "rev_abc123", "score": 80}', ""
    raise AssertionError(f"unexpected cmd before scenario: {cmd}")


def _security_review_ok(cmd, timeout=None, cwd=None):
    """Handle tessl review run security so existing dispatchers keep working."""
    del timeout, cwd
    if cmd[3:6] == ["review", "run", "security"]:
        assert "--workspace" in cmd
        return 0, '{"id": "sec_from_run"}', ""
    return None


def _eval_ok(cmd, timeout=None, cwd=None):
    """Handle Tessl project repair + eval run/view for auto-chain tests.

    Falls through to security review so existing dispatchers keep working
    after slice 51 appends the Security step.
    """
    del timeout, cwd
    if cmd[3:5] == ["project", "repair"]:
        return 0, '{"ok": true}', ""
    if cmd[3:5] == ["project", "create"]:
        return 0, '{"ok": true}', ""
    if cmd[3:5] == ["eval", "run"]:
        assert "--runs" in cmd and "3" in cmd
        assert "-y" in cmd
        return 0, '{"id": "eval_xyz789", "status": "pending"}', ""
    if cmd[3:5] == ["eval", "view"]:
        return (
            0,
            (
                '{"id": "eval_xyz789", "status": "completed", "scenarioCount": 3, '
                '"baselineAvg": 0.4, "withContextAvg": 0.7, "delta": 0.3, "runs": 3}'
            ),
            "",
        )
    return _security_review_ok(cmd)


def test_given_plugin_when_scenario_gen_succeeds_then_download_stamps_and_clears_checkpoint(
    tmp_path,
) -> None:
    """
    Scenario: Successful generate + download stamps tessl_run_id and clears checkpoint.
    Slice: 49 — GWT-49.1

    Given Quality Review completed and a Tessl plugin directory,
    When Scenario Generation runs,
    Then generate --count 3, view/download use gen_id, row completes with checks_run,
    And resume_checkpoint is cleared to null.
    """
    ### Given
    workdir = _make_tessl_plugin(tmp_path)
    ctx = scanners._new_tessl_id_context()
    progress: list[dict] = []
    captured: list[list[str]] = []

    def _run(cmd, timeout=None, cwd=None):
        resolved = _tessl_workspace_cli_ok(cmd, timeout, cwd)
        if resolved is not None:
            return resolved
        captured.append(cmd)
        if (
            cmd[3:5] in (["skill", "lint"],)
            or cmd[3:5] == ["review", "run"]
            or (len(cmd) > 5 and cmd[3:5] == ["review", "view"])
        ):
            return _lint_and_quality_ok(cmd, timeout)
        if cmd[3:5] == ["scenario", "generate"]:
            assert "--count" in cmd and "3" in cmd
            assert workdir in cmd
            assert "--workspace" in cmd
            assert cmd[cmd.index("--workspace") + 1] == "engteam"
            return 0, '{"id": "gen_abc123", "status": "completed", "scenarioCount": 3}', ""
        if cmd[3:5] == ["scenario", "view"]:
            return 0, '{"id": "gen_abc123", "status": "completed", "scenarioCount": 3}', ""
        if cmd[3:5] == ["scenario", "download"]:
            assert "gen_abc123" in cmd
            assert "-o" in cmd
            out_dir = cmd[cmd.index("-o") + 1]
            assert out_dir.endswith("evals")
            os.makedirs(os.path.join(out_dir, "s1"), exist_ok=True)
            os.makedirs(os.path.join(out_dir, "s2"), exist_ok=True)
            os.makedirs(os.path.join(out_dir, "s3"), exist_ok=True)
            return 0, "downloaded 3", ""
        eval_handled = _eval_ok(cmd, timeout, cwd)
        if eval_handled is not None:
            return eval_handled
        raise AssertionError(f"unexpected cmd: {cmd}")

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
    ):
        score, rows = scanners.run_tessl(workdir, id_context=ctx, on_row_progress=progress.append)

    ### Then
    assert score == 80
    scenario_row = rows[2]
    assert scenario_row["scanner_source"] == "Tessl: Scenario Generation"
    assert scenario_row["status"] == "completed"
    assert scenario_row["tessl_run_id"] == "gen_abc123"
    assert scenario_row["tessl_run_id_at"]
    assert scenario_row["checks_run"] == 3
    assert scenario_row["resume_checkpoint"] is None
    assert scenario_row["upstream_run_ids"] == {"review_quality": "rev_abc123"}
    assert ctx["scenario_gen"] == "gen_abc123"
    assert any(p.get("resume_checkpoint", {}).get("stage") == "generated" for p in progress)
    generate_cmds = [c for c in captured if c[3:5] == ["scenario", "generate"]]
    download_cmds = [c for c in captured if c[3:5] == ["scenario", "download"]]
    assert len(generate_cmds) == 1
    assert len(download_cmds) == 1


def test_given_resume_generated_when_run_tessl_then_skips_generate_and_downloads(
    tmp_path,
) -> None:
    """
    Scenario: Resume after generate skips generate and retries download only.
    Slice: 49 — GWT-49.2

    Given resume_checkpoint.stage is generated with a gen_id,
    When Scenario Generation resumes,
    Then generate is not invoked and download uses the checkpoint gen_id.
    """
    ### Given
    workdir = _make_tessl_plugin(tmp_path)
    captured: list[list[str]] = []

    def _run(cmd, timeout=None, cwd=None):
        resolved = _tessl_workspace_cli_ok(cmd, timeout, cwd)
        if resolved is not None:
            return resolved
        captured.append(cmd)
        if (
            cmd[3:5] in (["skill", "lint"],)
            or cmd[3:5] == ["review", "run"]
            or (len(cmd) > 5 and cmd[3:5] == ["review", "view"])
        ):
            return _lint_and_quality_ok(cmd, timeout)
        if cmd[3:5] == ["scenario", "view"]:
            return 0, '{"id": "gen_resume", "status": "completed", "scenarioCount": 2}', ""
        if cmd[3:5] == ["scenario", "download"]:
            assert "gen_resume" in cmd
            out_dir = cmd[cmd.index("-o") + 1]
            os.makedirs(os.path.join(out_dir, "a"), exist_ok=True)
            os.makedirs(os.path.join(out_dir, "b"), exist_ok=True)
            return 0, "ok", ""
        eval_handled = _eval_ok(cmd, timeout, cwd)
        if eval_handled is not None:
            return eval_handled
        raise AssertionError(f"unexpected cmd: {cmd}")

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
        patch.object(scanners, "_TESSL_SCENARIO_POLL_SLEEP_S", 0),
    ):
        _score, rows = scanners.run_tessl(
            workdir,
            resume_checkpoint={"stage": "generated", "gen_id": "gen_resume"},
        )

    ### Then
    assert all(c[3:5] != ["scenario", "generate"] for c in captured)
    assert rows[2]["status"] == "completed"
    assert rows[2]["tessl_run_id"] == "gen_resume"
    assert rows[2]["checks_run"] == 2
    assert rows[2]["resume_checkpoint"] is None


def test_given_in_progress_checkpoint_when_resumed_then_polls_before_download(
    tmp_path,
) -> None:
    """
    Scenario: Detached in-progress generation is polled until completed before download.
    Slice: 49 — GWT-49.2b

    Given resume_checkpoint has gen_id while server status is still in_progress,
    When the runner resumes,
    Then view is polled until completed and download is not called early.
    """
    ### Given
    workdir = _make_tessl_plugin(tmp_path)
    views = [
        (0, '{"id": "gen_poll", "status": "in_progress"}', ""),
        (0, '{"id": "gen_poll", "status": "completed", "scenarioCount": 1}', ""),
    ]
    captured: list[list[str]] = []

    def _run(cmd, timeout=None, cwd=None):
        resolved = _tessl_workspace_cli_ok(cmd, timeout, cwd)
        if resolved is not None:
            return resolved
        captured.append(cmd)
        if (
            cmd[3:5] in (["skill", "lint"],)
            or cmd[3:5] == ["review", "run"]
            or (len(cmd) > 5 and cmd[3:5] == ["review", "view"])
        ):
            return _lint_and_quality_ok(cmd, timeout)
        if cmd[3:5] == ["scenario", "view"]:
            return views.pop(0)
        if cmd[3:5] == ["scenario", "download"]:
            assert not views, "download must wait until view reports completed"
            out_dir = cmd[cmd.index("-o") + 1]
            os.makedirs(os.path.join(out_dir, "only"), exist_ok=True)
            return 0, "ok", ""
        eval_handled = _eval_ok(cmd, timeout, cwd)
        if eval_handled is not None:
            return eval_handled
        raise AssertionError(f"unexpected cmd: {cmd}")

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
        patch.object(scanners, "_TESSL_SCENARIO_POLL_SLEEP_S", 0),
    ):
        _score, rows = scanners.run_tessl(
            workdir,
            resume_checkpoint={"stage": "generated", "gen_id": "gen_poll"},
        )

    ### Then
    assert rows[2]["status"] == "completed"
    assert sum(1 for c in captured if c[3:5] == ["scenario", "view"]) >= 2
    assert sum(1 for c in captured if c[3:5] == ["scenario", "download"]) == 1


def test_given_quality_id_in_ctx_when_scenario_starts_then_upstream_run_ids_attached(
    tmp_path,
) -> None:
    """
    Scenario: upstream_run_ids.review_quality is written before scenario generate.
    Slice: 49 — GWT-49.3

    Given ctx review_quality is rev_abc123,
    When Scenario Generation starts,
    Then upstream_run_ids is attached before generate is invoked.
    """
    ### Given
    workdir = _make_tessl_plugin(tmp_path)
    ctx = {"review_quality": "rev_abc123", "scenario_gen": None}
    progress: list[dict] = []

    def _run(cmd, timeout=None, cwd=None):
        resolved = _tessl_workspace_cli_ok(cmd, timeout, cwd)
        if resolved is not None:
            return resolved
        if cmd[3:5] == ["scenario", "generate"]:
            return 0, '{"id": "gen_x", "status": "completed", "scenarioCount": 1}', ""
        if cmd[3:5] == ["scenario", "download"]:
            out_dir = cmd[cmd.index("-o") + 1]
            os.makedirs(os.path.join(out_dir, "s"), exist_ok=True)
            return 0, "ok", ""
        eval_handled = _eval_ok(cmd, timeout, cwd)
        if eval_handled is not None:
            return eval_handled
        return _lint_and_quality_ok(cmd, timeout, cwd)

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
    ):
        _score, rows = scanners.run_tessl(workdir, id_context=ctx, on_row_progress=progress.append)

    ### Then
    scenario_progress = [
        p for p in progress if p.get("scanner_source") == "Tessl: Scenario Generation"
    ]
    assert scenario_progress[0]["upstream_run_ids"] == {"review_quality": "rev_abc123"}
    assert rows[2]["upstream_run_ids"] == {"review_quality": "rev_abc123"}
    assert ctx["scenario_gen"] == "gen_x"


def test_given_null_quality_id_when_scenario_starts_then_upstream_key_is_null(
    tmp_path,
) -> None:
    """
    Scenario: Missing Quality ID still proceeds with null upstream key.
    Slice: 49 — GWT-49.3b

    Given Quality Review did not produce a tessl_run_id,
    When Scenario Generation starts,
    Then upstream_run_ids.review_quality is null and generate still runs.
    """
    ### Given
    workdir = _make_tessl_plugin(tmp_path)
    captured: list[list[str]] = []

    def _run(cmd, timeout=None, cwd=None):
        captured.append(cmd)
        if cmd[3:5] == ["skill", "lint"]:
            return 0, "1 check", ""
        if cmd[3:6] == ["review", "run", "quality"]:
            return 0, '{"score": 70}', ""
        if cmd[3:6] == ["review", "view", "--last"]:
            return 1, "", "no runs"
        if cmd[3:5] == ["scenario", "generate"]:
            return 0, '{"id": "gen_null_up", "status": "completed", "scenarioCount": 1}', ""
        if cmd[3:5] == ["scenario", "download"]:
            out_dir = cmd[cmd.index("-o") + 1]
            os.makedirs(os.path.join(out_dir, "s"), exist_ok=True)
            return 0, "ok", ""
        eval_handled = _eval_ok(cmd, timeout, cwd)
        if eval_handled is not None:
            return eval_handled
        raise AssertionError(f"unexpected cmd: {cmd}")

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
    ):
        _score, rows = scanners.run_tessl(workdir)

    ### Then
    assert rows[2]["upstream_run_ids"] == {"review_quality": None}
    assert any(c[3:5] == ["scenario", "generate"] for c in captured)
    assert rows[2]["status"] == "completed"


def test_given_scenario_generate_fails_when_run_tessl_then_row_is_failed(tmp_path) -> None:
    """
    Scenario: Non-zero scenario generate marks Scenario Generation failed.
    Slice: 49 — GWT-49.4

    Given tessl scenario generate exits non-zero,
    When Scenario Generation completes,
    Then the row status is failed and no download is attempted.
    """
    ### Given
    workdir = _make_tessl_plugin(tmp_path)
    captured: list[list[str]] = []

    def _run(cmd, timeout=None, cwd=None):
        resolved = _tessl_workspace_cli_ok(cmd, timeout, cwd)
        if resolved is not None:
            return resolved
        captured.append(cmd)
        if (
            cmd[3:5] in (["skill", "lint"],)
            or cmd[3:5] == ["review", "run"]
            or (len(cmd) > 5 and cmd[3:5] == ["review", "view"])
        ):
            return _lint_and_quality_ok(cmd, timeout)
        if cmd[3:5] == ["scenario", "generate"]:
            return 1, "", "Failed to generate scenarios\nWorkspace not found"
        eval_handled = _eval_ok(cmd, timeout, cwd)
        if eval_handled is not None:
            return eval_handled
        raise AssertionError(f"unexpected cmd: {cmd}")

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
    ):
        _score, rows = scanners.run_tessl(workdir)

    ### Then
    assert rows[2]["status"] == "failed"
    assert "Workspace not found" in rows[2]["detail"]
    assert "workspace=engteam" in rows[2]["detail"]
    assert all(c[3:5] != ["scenario", "download"] for c in captured)


def test_given_missing_token_when_scenario_would_run_then_needs_setup() -> None:
    """
    Scenario: Missing TESSL_TOKEN yields needs_setup for Scenario Generation.
    Slice: 49 — GWT-49.5

    Given TESSL_TOKEN is absent,
    When Scenario Generation would run,
    Then the row status is needs_setup.
    """
    ### Given / When
    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", return_value=(0, "1 check", "")),
    ):
        _score, rows = scanners.run_tessl("/tmp/fake-skill")

    ### Then
    assert rows[2]["scanner_source"] == "Tessl: Scenario Generation"
    assert rows[2]["status"] == "needs_setup"
    assert rows[2]["upstream_run_ids"] == {"review_quality": None}


def test_given_missing_plugin_manifest_when_scenario_runs_then_failed(tmp_path) -> None:
    """
    Scenario: Missing plugin manifest fails Scenario Generation with actionable detail.
    Slice: 49 — GWT-49.5

    Given TESSL_TOKEN is set but .tessl-plugin/plugin.json is absent,
    When Scenario Generation runs,
    Then status is failed and detail mentions the missing plugin manifest.
    """
    ### Given
    workdir = str(tmp_path / "no-plugin")
    os.makedirs(workdir)

    def _run(cmd, timeout=None, cwd=None):
        resolved = _tessl_workspace_cli_ok(cmd, timeout, cwd)
        if resolved is not None:
            return resolved
        return _lint_and_quality_ok(cmd, timeout)

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
    ):
        _score, rows = scanners.run_tessl(workdir)

    ### Then
    assert rows[2]["status"] == "failed"
    assert "plugin.json" in rows[2]["detail"]


def test_attach_upstream_run_ids_copies_selected_keys_with_nulls() -> None:
    """
    Scenario: _attach_upstream_run_ids copies ctx keys including explicit nulls.
    Slice: 49 — ID carry-forward helper

    Given a Tessl ID context with review_quality set and scenario_gen None,
    When _attach_upstream_run_ids selects both keys,
    Then the row upstream_run_ids map matches exactly.
    """
    ### Given
    row: dict = {}
    ctx = {"review_quality": "rev_1", "scenario_gen": None}

    ### When
    scanners._attach_upstream_run_ids(row, ctx, "review_quality", "scenario_gen")

    ### Then
    assert row["upstream_run_ids"] == {"review_quality": "rev_1", "scenario_gen": None}


def test_parse_scenario_gen_id_and_status_from_json_shapes() -> None:
    """
    Scenario: Scenario JSON helpers read id/status/count from common shapes.
    Slice: 49 — GWT-49.1 parse helpers

    Given generate/view JSON variants,
    When parsers run,
    Then id, status, and count are extracted.
    """
    ### Given / When / Then
    assert scanners._parse_scenario_gen_id({"id": "gen_1"}) == "gen_1"
    assert scanners._parse_scenario_gen_id({"generation": {"id": "gen_2"}}) == "gen_2"
    assert scanners._parse_scenario_status({"status": "COMPLETED"}) == "completed"
    assert scanners._parse_scenario_status({"generation": {"state": "Failed"}}) == "failed"
    assert scanners._parse_scenario_count({"scenarioCount": 4}) == 4
    assert scanners._parse_scenario_count({"scenarios": [{}, {}]}) == 2
    assert scanners._parse_scenario_count({"generation": {"count": 7}}) == 7
    assert scanners._parse_scenario_gen_id({"score": 1}) is None
    assert scanners._parse_scenario_status(None) is None
    assert scanners._parse_scenario_count("nope") is None
    assert scanners._tessl_scenario_view_argv(None)[-3:] == ["--last", "--mine", "--json"]
    gen_argv = scanners._tessl_scenario_generate_argv("/plugin", "acme", count=3)
    assert gen_argv[3:6] == ["scenario", "generate", "/plugin"]
    assert gen_argv[gen_argv.index("--workspace") + 1] == "acme"
    assert gen_argv[gen_argv.index("--count") + 1] == "3"
    assert (
        scanners._pick_tessl_workspace(
            [{"name": "other"}, {"name": "neomatrix369"}],
            "neomatrix369",
        )
        == "neomatrix369"
    )
    assert scanners._parse_tessl_whoami_username({"user": {"username": "alice"}}) == "alice"


def test_given_generate_timeout_when_scenario_runs_then_interrupted_with_checkpoint(
    tmp_path,
) -> None:
    """
    Scenario: Modal/CLI timeout on generate persists resume_checkpoint.
    Slice: 49 — GWT-49.2b interrupt path

    Given scenario generate times out,
    When Scenario Generation finishes,
    Then status is interrupted and resume_checkpoint holds gen_id from view --last.
    """
    ### Given
    workdir = _make_tessl_plugin(tmp_path)

    def _run(cmd, timeout=None, cwd=None):
        if cmd[3:5] == ["scenario", "generate"]:
            return None, "", "timeout after 240s"
        if cmd[3:5] == ["scenario", "view"]:
            return 0, '{"id": "gen_detached", "status": "in_progress"}', ""
        return _lint_and_quality_ok(cmd, timeout)

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
    ):
        _score, rows = scanners.run_tessl(workdir)

    ### Then
    assert rows[2]["status"] == "interrupted"
    assert rows[2]["resume_checkpoint"] == {
        "stage": "generated",
        "gen_id": "gen_detached",
    }
    assert rows[2]["tessl_run_id"] == "gen_detached"


def test_given_resume_failed_status_when_polled_then_download_is_skipped(tmp_path) -> None:
    """
    Scenario: Resume poll that reports failed does not call download.
    Slice: 49 — GWT-49.2b failed terminal

    Given resume_checkpoint gen_id whose view status is failed,
    When Scenario Generation resumes,
    Then row is failed and download is not invoked.
    """
    ### Given
    workdir = _make_tessl_plugin(tmp_path)
    captured: list[list[str]] = []

    def _run(cmd, timeout=None, cwd=None):
        captured.append(cmd)
        if cmd[3:5] == ["scenario", "view"]:
            return 0, '{"id": "gen_fail", "status": "failed"}', "server failed"
        return _lint_and_quality_ok(cmd, timeout)

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
        patch.object(scanners, "_TESSL_SCENARIO_POLL_SLEEP_S", 0),
    ):
        _score, rows = scanners.run_tessl(
            workdir, resume_checkpoint={"stage": "generated", "gen_id": "gen_fail"}
        )

    ### Then
    assert rows[2]["status"] == "failed"
    assert all(c[3:5] != ["scenario", "download"] for c in captured)


def test_given_download_fails_when_scenario_completes_then_checkpoint_retained(
    tmp_path,
) -> None:
    """
    Scenario: Failed download retains generated checkpoint for retry.
    Slice: 49 — GWT-49.1 download failure

    Given generate succeeds and download exits non-zero,
    When Scenario Generation finishes,
    Then status is failed and resume_checkpoint.stage remains generated.
    """
    ### Given
    workdir = _make_tessl_plugin(tmp_path)

    def _run(cmd, timeout=None, cwd=None):
        if cmd[3:5] == ["scenario", "generate"]:
            return 0, '{"id": "gen_dl", "status": "completed"}', ""
        if cmd[3:5] == ["scenario", "download"]:
            return 1, "", "still in_progress"
        return _lint_and_quality_ok(cmd, timeout)

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
    ):
        _score, rows = scanners.run_tessl(workdir)

    ### Then
    assert rows[2]["status"] == "failed"
    assert rows[2]["resume_checkpoint"] == {"stage": "generated", "gen_id": "gen_dl"}


def test_given_empty_evals_when_download_succeeds_then_count_comes_from_view(
    tmp_path,
) -> None:
    """
    Scenario: Empty evals/ after download falls back to scenario view count.
    Slice: 49 — GWT-49.1 checks_run from view

    Given download succeeds but creates no scenario directories,
    When Scenario Generation finishes,
    Then checks_run is taken from scenario view JSON.
    """
    ### Given
    workdir = _make_tessl_plugin(tmp_path)

    def _run(cmd, timeout=None, cwd=None):
        if cmd[3:5] == ["scenario", "generate"]:
            return 0, '{"id": "gen_view_count"}', ""
        if cmd[3:5] == ["scenario", "download"]:
            return 0, "ok", ""
        if cmd[3:5] == ["scenario", "view"]:
            return 0, '{"id": "gen_view_count", "scenarioCount": 5}', "view ok"
        return _lint_and_quality_ok(cmd, timeout)

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
    ):
        _score, rows = scanners.run_tessl(workdir)

    ### Then
    assert rows[2]["status"] == "completed"
    assert rows[2]["checks_run"] == 5
    assert rows[2]["resume_checkpoint"] is None
    assert rows[3]["scanner_source"] == "Tessl: Eval"
    assert rows[3]["status"] == "blocked"


# --- slice-50: Tessl Eval + Scenario→Eval Auto-Chain (Row 4) ---


def test_given_lint_review_when_run_tessl_then_eval_emitted_blocked_before_scenario(
    tmp_path,
) -> None:
    """
    Scenario: Eval row is emitted blocked before Scenario Generation starts.
    Slice: 50 — GWT-50.0

    Given Tessl group runner begins for a skill scan,
    When Lint and Review rows are emitted,
    Then an Eval row is inserted with status blocked and no tessl_run_id,
    And Eval stays blocked while Scenario Generation is still running.
    """
    ### Given
    workdir = _make_tessl_plugin(tmp_path)
    progress: list[dict] = []

    def _run(cmd, timeout=None, cwd=None):
        if cmd[3:5] == ["scenario", "generate"]:
            eval_snapshots = [p for p in progress if p.get("scanner_source") == "Tessl: Eval"]
            assert eval_snapshots, "Eval blocked row must be emitted before generate"
            assert eval_snapshots[0]["status"] == "blocked"
            assert eval_snapshots[0].get("tessl_run_id") is None
            return 1, "", "scenario failed intentionally"
        return _lint_and_quality_ok(cmd, timeout, cwd)

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
    ):
        _score, rows = scanners.run_tessl(workdir, on_row_progress=progress.append)

    ### Then
    assert rows[3]["scanner_source"] == "Tessl: Eval"
    assert rows[3]["status"] == "blocked"
    assert rows[3].get("tessl_run_id") is None


def test_given_scenario_completed_with_evals_when_run_tessl_then_eval_auto_chains(
    tmp_path,
) -> None:
    """
    Scenario: First-run auto-chain from Scenario Generation into Eval.
    Slice: 50 — GWT-50.1 / GWT-50.2 / GWT-50.4 / GWT-50.5

    Given Scenario Generation completed and evals/ has scenarios,
    When the auto-chain check runs,
    Then Eval transitions queued→running, invokes eval run --runs 3 -y,
    stamps tessl_run_id, upstream_run_ids, and score detail without failing on variance.
    """
    ### Given
    workdir = _make_tessl_plugin(tmp_path)
    ctx = scanners._new_tessl_id_context()
    progress: list[dict] = []
    captured: list[list[str]] = []

    def _run(cmd, timeout=None, cwd=None):
        captured.append(cmd)
        if (
            cmd[3:5] in (["skill", "lint"],)
            or cmd[3:5] == ["review", "run"]
            or (len(cmd) > 5 and cmd[3:5] == ["review", "view"])
        ):
            return _lint_and_quality_ok(cmd, timeout, cwd)
        if cmd[3:5] == ["scenario", "generate"]:
            return 0, '{"id": "gen_for_eval", "status": "completed", "scenarioCount": 2}', ""
        if cmd[3:5] == ["scenario", "download"]:
            out_dir = cmd[cmd.index("-o") + 1]
            os.makedirs(os.path.join(out_dir, "s1"), exist_ok=True)
            os.makedirs(os.path.join(out_dir, "s2"), exist_ok=True)
            return 0, "ok", ""
        eval_handled = _eval_ok(cmd, timeout, cwd)
        if eval_handled is not None:
            return eval_handled
        raise AssertionError(f"unexpected cmd: {cmd}")

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
        patch.object(scanners, "_TESSL_EVAL_POLL_SLEEP_S", 0),
    ):
        score, rows = scanners.run_tessl(workdir, id_context=ctx, on_row_progress=progress.append)

    ### Then
    assert score == 80
    eval_row = rows[3]
    assert eval_row["scanner_source"] == "Tessl: Eval"
    assert eval_row["status"] == "completed"
    assert eval_row["tessl_run_id"] == "eval_xyz789"
    assert eval_row["tessl_run_id_at"]
    assert eval_row["checks_run"] == 3
    assert eval_row["upstream_run_ids"] == {
        "review_quality": "rev_abc123",
        "scenario_gen": "gen_for_eval",
    }
    assert "baseline avg" in eval_row["detail"]
    assert "with-context avg" in eval_row["detail"]
    assert "delta=" in eval_row["detail"]
    eval_statuses = [p["status"] for p in progress if p.get("scanner_source") == "Tessl: Eval"]
    assert "blocked" in eval_statuses
    assert "queued" in eval_statuses
    assert "running" in eval_statuses
    eval_cmds = [c for c in captured if c[3:5] == ["eval", "run"]]
    assert len(eval_cmds) == 1
    assert "--runs" in eval_cmds[0] and "3" in eval_cmds[0]
    assert "-y" in eval_cmds[0]


def test_given_scenario_failed_when_run_tessl_then_eval_stays_blocked(tmp_path) -> None:
    """
    Scenario: Failed Scenario Generation leaves Eval blocked (partial ctx).
    Slice: 50 — GWT-50.4b

    Given Scenario Generation failed and ctx scenario_gen is still null,
    When Eval auto-chain gate runs,
    Then Eval remains blocked with no eval invocation.
    """
    ### Given
    workdir = _make_tessl_plugin(tmp_path)
    ctx = scanners._new_tessl_id_context()
    captured: list[list[str]] = []

    def _run(cmd, timeout=None, cwd=None):
        captured.append(cmd)
        if cmd[3:5] == ["scenario", "generate"]:
            return 1, "", "boom"
        return _lint_and_quality_ok(cmd, timeout, cwd)

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
    ):
        _score, rows = scanners.run_tessl(workdir, id_context=ctx)

    ### Then
    assert rows[3]["status"] == "blocked"
    assert ctx["scenario_gen"] is None
    assert not any(c[3:5] == ["eval", "run"] for c in captured)


def test_given_prior_completed_eval_when_scenario_rerun_then_eval_is_stale(
    tmp_path,
) -> None:
    """
    Scenario: Scenario Generation re-run marks prior completed Eval as stale.
    Slice: 50 — GWT-50.3

    Given Eval previously completed with a tessl_run_id,
    When Scenario Generation is re-run with a new gen id,
    Then Eval status becomes stale and no new eval run is triggered.
    """
    ### Given
    workdir = _make_tessl_plugin(tmp_path)
    prior_eval = {
        "scanner_source": "Tessl: Eval",
        "status": "completed",
        "tessl_run_id": "eval_old",
        "tessl_run_id_at": "2026-08-24T10:00:00+00:00",
        "completed_at": "2026-08-24T10:05:00+00:00",
        "checks_run": 2,
        "detail": "baseline avg=0.5",
        "upstream_run_ids": {
            "review_quality": "rev_abc123",
            "scenario_gen": "gen_old",
        },
    }
    captured: list[list[str]] = []

    def _run(cmd, timeout=None, cwd=None):
        captured.append(cmd)
        if cmd[3:5] == ["scenario", "generate"]:
            return 0, '{"id": "gen_new", "status": "completed", "scenarioCount": 1}', ""
        if cmd[3:5] == ["scenario", "download"]:
            out_dir = cmd[cmd.index("-o") + 1]
            os.makedirs(os.path.join(out_dir, "s"), exist_ok=True)
            return 0, "ok", ""
        return _lint_and_quality_ok(cmd, timeout, cwd)

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
    ):
        _score, rows = scanners.run_tessl(workdir, prior_eval=prior_eval)

    ### Then
    assert rows[3]["status"] == "stale"
    assert rows[3]["tessl_run_id"] == "eval_old"
    assert not any(c[3:5] == ["eval", "run"] for c in captured)


def test_given_interrupted_eval_when_resumed_then_polls_view_without_resubmit(
    tmp_path,
) -> None:
    """
    Scenario: Modal timeout resume polls eval view without re-submitting eval run.
    Slice: 50 — GWT-50.2b

    Given eval run was detached with an eval_id while pending,
    When the runner resumes,
    Then it polls eval view until completed and does not call eval run again.
    """
    ### Given
    workdir = _make_tessl_plugin(tmp_path)
    prior_eval = {
        "scanner_source": "Tessl: Eval",
        "status": "interrupted",
        "tessl_run_id": "eval_resume_me",
        "upstream_run_ids": {
            "review_quality": "rev_abc123",
            "scenario_gen": "gen_x",
        },
    }
    # Pre-populate evals so auto-chain gate would otherwise fire a new run.
    os.makedirs(os.path.join(workdir, "evals", "s1"), exist_ok=True)
    captured: list[list[str]] = []

    def _run(cmd, timeout=None, cwd=None):
        captured.append(cmd)
        if cmd[3:5] == ["scenario", "generate"]:
            return 0, '{"id": "gen_x", "status": "completed"}', ""
        if cmd[3:5] == ["scenario", "download"]:
            return 0, "ok", ""
        if cmd[3:5] == ["project", "repair"]:
            return 0, "{}", ""
        if cmd[3:5] == ["eval", "run"]:
            raise AssertionError("must not re-submit eval run while prior pending")
        if cmd[3:5] == ["eval", "view"]:
            assert "eval_resume_me" in cmd
            return (
                0,
                '{"id": "eval_resume_me", "status": "completed", "scenarioCount": 1, '
                '"baselineAvg": 0.2, "withContextAvg": 0.5, "delta": 0.3}',
                "",
            )
        return _lint_and_quality_ok(cmd, timeout, cwd)

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
        patch.object(scanners, "_TESSL_EVAL_POLL_SLEEP_S", 0),
    ):
        _score, rows = scanners.run_tessl(workdir, prior_eval=prior_eval)

    ### Then
    assert rows[3]["status"] == "completed"
    assert rows[3]["tessl_run_id"] == "eval_resume_me"
    assert not any(c[3:5] == ["eval", "run"] for c in captured)
    assert any(c[3:5] == ["eval", "view"] for c in captured)


def test_given_missing_tessl_json_when_eval_chains_then_project_create_or_needs_setup(
    tmp_path,
) -> None:
    """
    Scenario: Eval preflight creates Tessl project or reports needs_setup.
    Slice: 50 — GWT-50.6

    Given plugin directory has no tessl.json,
    When Eval auto-chain attempts to run,
    Then project create is invoked; on failure Eval is needs_setup with actionable detail.
    """
    ### Given
    workdir = _make_tessl_plugin(tmp_path)
    os.remove(os.path.join(workdir, "tessl.json"))
    captured: list[list[str]] = []

    def _run(cmd, timeout=None, cwd=None):
        captured.append(cmd)
        if cmd[3:5] == ["scenario", "generate"]:
            return 0, '{"id": "gen_proj", "status": "completed"}', ""
        if cmd[3:5] == ["scenario", "download"]:
            out_dir = cmd[cmd.index("-o") + 1]
            os.makedirs(os.path.join(out_dir, "s"), exist_ok=True)
            return 0, "ok", ""
        if cmd[3:5] == ["project", "create"]:
            assert cwd == workdir
            return 1, "", "cannot create project headlessly"
        return _lint_and_quality_ok(cmd, timeout, cwd)

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
    ):
        _score, rows = scanners.run_tessl(workdir)

    ### Then
    assert rows[3]["status"] == "needs_setup"
    assert "project" in rows[3]["detail"].lower()
    assert any(c[3:5] == ["project", "create"] for c in captured)
    assert not any(c[3:5] == ["eval", "run"] for c in captured)


def test_parse_eval_id_and_detail_from_json_shapes() -> None:
    """
    Scenario: Eval JSON parsers accept nested id/score shapes.
    Slice: 50 — parser helpers

    Given common Tessl eval --json envelopes,
    When parsers extract id/status/checks/detail,
    Then nested and list forms resolve correctly.
    """
    ### Given / When / Then
    assert scanners._parse_eval_id({"id": "e1"}) == "e1"
    assert scanners._parse_eval_id({"eval": {"runId": "e2"}}) == "e2"
    assert scanners._parse_eval_id({"evals": [{"id": "e3"}]}) == "e3"
    assert scanners._parse_eval_id({"evals": ["skip"]}) is None
    assert scanners._parse_eval_id("bad") is None
    assert scanners._parse_eval_status({"status": "Completed"}) == "completed"
    assert scanners._parse_eval_status("bad") is None
    assert scanners._parse_eval_status({"eval": {}}) is None
    assert scanners._parse_eval_checks_run({"scenarioCount": 4}) == 4
    assert scanners._parse_eval_checks_run("bad") is None
    detail = scanners._format_eval_detail(
        {"baselineAvg": 0.1, "withContextAvg": 0.4, "delta": 0.3, "runs": 3}
    )
    assert "baseline avg=0.1" in detail
    assert "with-context avg=0.4" in detail
    assert "delta=0.3" in detail
    assert "runs=3" in detail
    assert scanners._eval_should_mark_stale({"status": "running"}, {"status": "completed"}) is False
    assert scanners._eval_should_mark_stale({"status": "completed"}, {"status": "failed"}) is False


def test_eval_should_mark_stale_by_timestamp_when_gen_id_unchanged() -> None:
    """
    Scenario: Stale when scenario tessl_run_id_at is newer than eval completed_at.
    Slice: 50 — stale timestamp path

    Given prior Eval completed with same scenario_gen id,
    When scenario_gen tessl_run_id_at is newer than eval completed_at,
    Then _eval_should_mark_stale is True.
    """
    ### Given
    prior = {
        "status": "completed",
        "completed_at": "2026-08-24T10:00:00+00:00",
        "upstream_run_ids": {"scenario_gen": "gen_same"},
    }
    scenario = {
        "status": "completed",
        "tessl_run_id": "gen_same",
        "tessl_run_id_at": "2026-08-24T12:00:00+00:00",
    }

    ### When / Then
    assert scanners._eval_should_mark_stale(prior, scenario) is True
    assert (
        scanners._eval_should_mark_stale(
            prior,
            {
                "status": "completed",
                "tessl_run_id": "gen_same",
                "tessl_run_id_at": "2026-08-24T09:00:00+00:00",
            },
        )
        is False
    )


def test_given_prior_completed_unchanged_when_run_tessl_then_eval_kept(
    tmp_path,
) -> None:
    """
    Scenario: Unchanged Scenario Gen keeps prior completed Eval (no stale, no re-run).
    Slice: 50 — keep completed

    Given prior Eval completed for the same scenario_gen id,
    When Scenario Generation completes again with the same id,
    Then Eval stays completed and eval run is not invoked.
    """
    ### Given
    workdir = _make_tessl_plugin(tmp_path)
    prior_eval = {
        "scanner_source": "Tessl: Eval",
        "status": "completed",
        "tessl_run_id": "eval_keep",
        "checks_run": 2,
        "detail": "kept",
        "upstream_run_ids": {
            "review_quality": "rev_abc123",
            "scenario_gen": "gen_same",
        },
    }
    captured: list[list[str]] = []

    def _run(cmd, timeout=None, cwd=None):
        captured.append(cmd)
        if cmd[3:5] == ["scenario", "generate"]:
            return 0, '{"id": "gen_same", "status": "completed"}', ""
        if cmd[3:5] == ["scenario", "view"]:
            return 0, '{"id": "gen_same", "status": "completed", "scenarioCount": 1}', ""
        if cmd[3:5] == ["scenario", "download"]:
            out_dir = cmd[cmd.index("-o") + 1]
            os.makedirs(os.path.join(out_dir, "s"), exist_ok=True)
            return 0, "ok", ""
        return _lint_and_quality_ok(cmd, timeout, cwd)

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
    ):
        _score, rows = scanners.run_tessl(
            workdir,
            prior_eval=prior_eval,
            resume_checkpoint={"stage": "generated", "gen_id": "gen_same"},
        )

    ### Then
    assert rows[3]["status"] == "completed"
    assert rows[3]["tessl_run_id"] == "eval_keep"
    assert not any(c[3:5] == ["eval", "run"] for c in captured)


def test_given_eval_run_timeout_with_id_when_chained_then_interrupted(tmp_path) -> None:
    """
    Scenario: Eval run timeout with captured id marks interrupted.
    Slice: 50 — detach with id

    Given eval run --json times out after emitting an id,
    When auto-chain finishes,
    Then status is interrupted and tessl_run_id is stamped.
    """
    ### Given
    workdir = _make_tessl_plugin(tmp_path)

    def _run(cmd, timeout=None, cwd=None):
        if cmd[3:5] == ["scenario", "generate"]:
            return 0, '{"id": "gen_to", "status": "completed"}', ""
        if cmd[3:5] == ["scenario", "download"]:
            out_dir = cmd[cmd.index("-o") + 1]
            os.makedirs(os.path.join(out_dir, "s"), exist_ok=True)
            return 0, "ok", ""
        if cmd[3:5] == ["project", "repair"]:
            return 0, "{}", ""
        if cmd[3:5] == ["eval", "run"]:
            return None, '{"id": "eval_detached"}', "timeout after 240s"
        return _lint_and_quality_ok(cmd, timeout, cwd)

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
    ):
        _score, rows = scanners.run_tessl(workdir)

    ### Then
    assert rows[3]["status"] == "interrupted"
    assert rows[3]["tessl_run_id"] == "eval_detached"


def test_given_eval_run_timeout_without_id_when_chained_then_timed_out(tmp_path) -> None:
    """
    Scenario: Eval run timeout without id marks timed_out.
    Slice: 50 — detach without id
    """
    ### Given
    workdir = _make_tessl_plugin(tmp_path)

    def _run(cmd, timeout=None, cwd=None):
        if cmd[3:5] == ["scenario", "generate"]:
            return 0, '{"id": "gen_to2", "status": "completed"}', ""
        if cmd[3:5] == ["scenario", "download"]:
            out_dir = cmd[cmd.index("-o") + 1]
            os.makedirs(os.path.join(out_dir, "s"), exist_ok=True)
            return 0, "ok", ""
        if cmd[3:5] == ["project", "repair"]:
            return 0, "{}", ""
        if cmd[3:5] == ["eval", "run"]:
            return None, "still starting", "timeout after 240s"
        return _lint_and_quality_ok(cmd, timeout, cwd)

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
    ):
        _score, rows = scanners.run_tessl(workdir)

    ### Then
    assert rows[3]["status"] == "timed_out"


def test_given_eval_run_nonzero_when_chained_then_failed(tmp_path) -> None:
    """
    Scenario: Non-zero eval run without id marks failed.
    Slice: 50 — eval CLI failure
    """
    ### Given
    workdir = _make_tessl_plugin(tmp_path)

    def _run(cmd, timeout=None, cwd=None):
        if cmd[3:5] == ["scenario", "generate"]:
            return 0, '{"id": "gen_fail", "status": "completed"}', ""
        if cmd[3:5] == ["scenario", "download"]:
            out_dir = cmd[cmd.index("-o") + 1]
            os.makedirs(os.path.join(out_dir, "s"), exist_ok=True)
            return 0, "ok", ""
        if cmd[3:5] == ["project", "repair"]:
            return 0, "{}", ""
        if cmd[3:5] == ["eval", "run"]:
            return 1, "", "eval exploded"
        return _lint_and_quality_ok(cmd, timeout, cwd)

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
    ):
        _score, rows = scanners.run_tessl(workdir)

    ### Then
    assert rows[3]["status"] == "failed"
    assert "exploded" in rows[3]["detail"]


def test_given_eval_view_failed_when_chained_then_row_failed(tmp_path) -> None:
    """
    Scenario: eval view status failed marks Eval failed (not score variance).
    Slice: 50 — GWT-50.5 failure path
    """
    ### Given
    workdir = _make_tessl_plugin(tmp_path)

    def _run(cmd, timeout=None, cwd=None):
        if cmd[3:5] == ["scenario", "generate"]:
            return 0, '{"id": "gen_vf", "status": "completed"}', ""
        if cmd[3:5] == ["scenario", "download"]:
            out_dir = cmd[cmd.index("-o") + 1]
            os.makedirs(os.path.join(out_dir, "s"), exist_ok=True)
            return 0, "ok", ""
        if cmd[3:5] == ["project", "repair"]:
            return 0, "{}", ""
        if cmd[3:5] == ["eval", "run"]:
            return 0, '{"id": "eval_fail_view"}', ""
        if cmd[3:5] == ["eval", "view"]:
            return 0, '{"id": "eval_fail_view", "status": "failed"}', ""
        return _lint_and_quality_ok(cmd, timeout, cwd)

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
        patch.object(scanners, "_TESSL_EVAL_POLL_SLEEP_S", 0),
    ):
        _score, rows = scanners.run_tessl(workdir)

    ### Then
    assert rows[3]["status"] == "failed"
    assert rows[3]["tessl_run_id"] == "eval_fail_view"


def test_given_eval_run_ok_without_id_when_chained_then_completed(tmp_path) -> None:
    """
    Scenario: Eval run exits 0 without parseable id still completes.
    Slice: 50 — no-id success path
    """
    ### Given
    workdir = _make_tessl_plugin(tmp_path)

    def _run(cmd, timeout=None, cwd=None):
        if cmd[3:5] == ["scenario", "generate"]:
            return 0, '{"id": "gen_noid", "status": "completed"}', ""
        if cmd[3:5] == ["scenario", "download"]:
            out_dir = cmd[cmd.index("-o") + 1]
            os.makedirs(os.path.join(out_dir, "s"), exist_ok=True)
            return 0, "ok", ""
        if cmd[3:5] == ["project", "repair"]:
            return 0, "{}", ""
        if cmd[3:5] == ["eval", "run"]:
            return 0, "eval finished without json id", ""
        return _lint_and_quality_ok(cmd, timeout, cwd)

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
    ):
        _score, rows = scanners.run_tessl(workdir)

    ### Then
    assert rows[3]["status"] == "completed"
    assert rows[3].get("tessl_run_id") is None


def test_ensure_tessl_project_create_writes_link(tmp_path) -> None:
    """
    Scenario: Missing tessl.json — project create success returns ok.
    Slice: 50 — project create happy path
    """
    ### Given
    workdir = str(tmp_path / "plugin")
    os.makedirs(workdir)

    def _run(cmd, timeout=None, cwd=None):
        assert cmd[3:5] == ["project", "create"]
        assert cwd == workdir
        (tmp_path / "plugin" / "tessl.json").write_text("{}")
        return 0, "created", ""

    ### When
    with patch.object(scanners, "_run", side_effect=_run):
        ok, detail = scanners._ensure_tessl_project(workdir, "engteam")

    ### Then
    assert ok is True
    assert detail == ""


def test_poll_eval_until_terminal_fails_on_nonzero_without_status() -> None:
    """
    Scenario: eval view non-zero exit without status maps to failed.
    Slice: 50 — poll failure path
    """
    ### Given / When
    with (
        patch.object(scanners, "_run", return_value=(1, "not json", "boom")),
        patch.object(scanners, "_TESSL_EVAL_POLL_SLEEP_S", 0),
    ):
        status, _parsed, console = scanners._poll_eval_until_terminal("eval_x")

    ### Then
    assert status == "failed"
    assert "boom" in console or "not json" in console


def test_run_tessl_eval_without_token_returns_needs_setup(tmp_path) -> None:
    """
    Scenario: Direct _run_tessl_eval without credentials is needs_setup.
    Slice: 50 — credential gate on eval helper
    """
    ### Given
    row = scanners._new_blocked_eval_row()
    ctx = {"review_quality": None, "scenario_gen": "gen_1"}

    ### When
    with patch.dict("os.environ", {}, clear=True):
        result = scanners._run_tessl_eval(str(tmp_path), ctx, row)

    ### Then
    assert result["status"] == "needs_setup"
    assert "TESSL_TOKEN" in result["detail"]


def test_run_tessl_eval_without_workspace_returns_needs_setup(tmp_path) -> None:
    """
    Scenario: Eval with token but unresolved workspace is needs_setup.
    Slice: 50 — workspace gate on eval helper
    """
    ### Given
    row = scanners._new_blocked_eval_row()
    ctx = {"review_quality": "rev_1", "scenario_gen": "gen_1"}

    ### When
    with patch.dict("os.environ", {"TESSL_TOKEN": "t"}, clear=True):
        result = scanners._run_tessl_eval(str(tmp_path), ctx, row, workspace=None)

    ### Then
    assert result["status"] == "needs_setup"
    assert "workspace" in result["detail"].lower()


def test_resolve_tessl_workspace_helpers_cover_fallback_paths() -> None:
    """
    Scenario: Workspace resolve helpers handle list shapes and action fallback.
    Slice: 50 — whoami/list parsing coverage
    """
    ### Given / When / Then
    assert scanners._parse_tessl_whoami_username(None) is None
    assert scanners._parse_tessl_whoami_username({"username": "top"}) == "top"
    assert scanners._parse_tessl_whoami_username({"user": {"username": "  "}}) is None
    assert scanners._parse_tessl_workspace_list([{"name": "a"}, "skip"]) == [{"name": "a"}]
    assert scanners._parse_tessl_workspace_list({"workspaces": [{"name": "b"}]}) == [{"name": "b"}]
    assert scanners._parse_tessl_workspace_list({"workspaces": "bad"}) == []
    assert scanners._parse_tessl_workspace_list("nope") == []
    assert scanners._pick_tessl_workspace([], None) is None
    assert (
        scanners._pick_tessl_workspace(
            [{"name": "team", "allowedActions": ["run_review"]}],
            "missing",
        )
        == "team"
    )
    assert (
        scanners._pick_tessl_workspace(
            [{"name": "first"}, {"name": "second"}],
            None,
        )
        == "first"
    )
    assert scanners._pick_tessl_workspace([{"name": "  "}, {}], "x") is None

    with patch.dict("os.environ", {"TESSL_WORKSPACE": "from-env"}, clear=True):
        # Env-only short-circuit removed — resolve always lists; mock list membership.
        def _run_env_ok(cmd, timeout=None, cwd=None):
            if cmd[3] == "whoami":
                return 0, '{"user": {"username": "from-env"}}', ""
            return 0, '{"workspaces": [{"name": "from-env"}]}', ""

        with patch.object(scanners, "_run", side_effect=_run_env_ok):
            assert scanners._resolve_tessl_workspace() == ("from-env", "")

    def _run_empty(cmd, timeout=None, cwd=None):
        if cmd[3] == "whoami":
            return 0, '{"authenticated": true}', ""
        return 0, '{"workspaces": []}', ""

    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(scanners, "_run", side_effect=_run_empty),
    ):
        ws, detail = scanners._resolve_tessl_workspace()
    assert ws is None
    assert "no Tessl workspaces" in detail

    def _run_action_pick(cmd, timeout=None, cwd=None):
        if cmd[3] == "whoami":
            return 1, "", "whoami failed"
        return (
            0,
            json.dumps(
                {
                    "workspaces": [
                        {"name": "view-only", "allowedActions": ["view"]},
                        {
                            "name": "publisher",
                            "allowedActions": ["generate_eval_scenarios"],
                        },
                    ]
                }
            ),
            "",
        )

    with (
        patch.dict("os.environ", {}, clear=True),
        patch.object(scanners, "_run", side_effect=_run_action_pick),
    ):
        ws, detail = scanners._resolve_tessl_workspace()
    assert ws == "publisher"
    assert detail == ""

    def _run_ignore_bad_env(cmd, timeout=None, cwd=None):
        if cmd[3] == "whoami":
            return 0, '{"user": {"username": "neomatrix369"}}', ""
        return (
            0,
            json.dumps(
                {
                    "workspaces": [
                        {
                            "name": "neomatrix369",
                            "id": "019c-ws",
                            "allowedActions": ["generate_eval_scenarios"],
                        }
                    ]
                }
            ),
            "",
        )

    with (
        patch.dict("os.environ", {"TESSL_WORKSPACE": "engteam"}, clear=True),
        patch.object(scanners, "_run", side_effect=_run_ignore_bad_env),
    ):
        ws, detail = scanners._resolve_tessl_workspace()
    assert ws == "neomatrix369"
    assert detail == ""
    assert (
        scanners._match_tessl_workspace([{"name": "neomatrix369", "id": "019c-ws"}], "019c-ws")
        == "neomatrix369"
    )


def test_annotate_tessl_cli_detail_adds_user_and_workspace() -> None:
    """
    Scenario: Tessl identity errors include attempted user/workspace in detail.
    Slice: 50 — workspace/user not found diagnostics
    """
    assert (
        scanners._annotate_tessl_cli_detail(
            "Failed to generate scenarios\nWorkspace not found",
            workspace="engteam",
            username="neomatrix369",
        )
        == "Failed to generate scenarios\nWorkspace not found "
        "(user=neomatrix369, workspace=engteam)"
    )
    assert (
        scanners._annotate_tessl_cli_detail(
            "User not found",
            workspace="acme",
            username="alice",
        )
        == "User not found (user=alice, workspace=acme)"
    )
    assert scanners._annotate_tessl_cli_detail("generation exploded", workspace="engteam") == (
        "generation exploded"
    )
    assert scanners._annotate_tessl_cli_detail("") == ""
    scanners._tessl_last_username = None
    scanners._tessl_last_workspace = None
    assert scanners._annotate_tessl_cli_detail("Workspace not found") == "Workspace not found"
    assert scanners._match_tessl_workspace([{"name": "a"}], "  ") is None
    assert scanners._match_tessl_workspace([{"id": "id-1"}], "id-1") == "id-1"


def test_ensure_tessl_project_create_timeout_returns_false(tmp_path) -> None:
    """
    Scenario: project create timeout yields actionable failure detail.
    Slice: 50 — project create timeout
    """
    ### Given
    workdir = str(tmp_path / "bare")
    os.makedirs(workdir)

    ### When
    with patch.object(scanners, "_run", return_value=(None, "", "timeout after 240s")):
        ok, detail = scanners._ensure_tessl_project(workdir, "engteam")

    ### Then
    assert ok is False
    assert "timed out" in detail.lower() or "timeout" in detail.lower()


def test_format_eval_detail_uses_run_count_and_fallback() -> None:
    """
    Scenario: Detail formatter uses runCount and falls back when empty.
    Slice: 50 — detail edge paths
    """
    ### Given / When / Then
    assert "runs=5" in scanners._format_eval_detail({"runCount": 5})
    assert scanners._format_eval_detail({}) == "eval completed"
    assert scanners._parse_eval_score_field({"scores": {"delta": 0.2}}, "delta") == 0.2
    assert scanners._parse_eval_checks_run({"results": [1, 2]}) == 2
    assert scanners._parse_eval_status({"evaluation": {"state": "Failed"}}) == "failed"


def test_poll_eval_until_terminal_returns_pending_after_max_attempts() -> None:
    """
    Scenario: Exhausted eval poll returns last non-terminal status.
    Slice: 50 — poll max attempts
    """
    ### Given / When
    with (
        patch.object(
            scanners,
            "_run",
            return_value=(0, '{"id": "e", "status": "pending"}', ""),
        ),
        patch.object(scanners, "_TESSL_EVAL_POLL_SLEEP_S", 0),
        patch.object(scanners, "_TESSL_EVAL_POLL_MAX", 2),
    ):
        status, parsed, _console = scanners._poll_eval_until_terminal("e")

    ### Then
    assert status == "pending"
    assert parsed is not None


def test_given_eval_view_pending_exhausted_when_chained_then_interrupted(
    tmp_path,
) -> None:
    """
    Scenario: Eval view never reaches terminal → interrupted for resume.
    Slice: 50 — poll interrupted
    """
    ### Given
    workdir = _make_tessl_plugin(tmp_path)

    def _run(cmd, timeout=None, cwd=None):
        if cmd[3:5] == ["scenario", "generate"]:
            return 0, '{"id": "gen_pend", "status": "completed"}', ""
        if cmd[3:5] == ["scenario", "download"]:
            out_dir = cmd[cmd.index("-o") + 1]
            os.makedirs(os.path.join(out_dir, "s"), exist_ok=True)
            return 0, "ok", ""
        if cmd[3:5] == ["project", "repair"]:
            return 0, "{}", ""
        if cmd[3:5] == ["eval", "run"]:
            return 0, '{"id": "eval_pend"}', ""
        if cmd[3:5] == ["eval", "view"]:
            return 0, '{"id": "eval_pend", "status": "pending"}', ""
        return _lint_and_quality_ok(cmd, timeout, cwd)

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
        patch.object(scanners, "_TESSL_EVAL_POLL_SLEEP_S", 0),
        patch.object(scanners, "_TESSL_EVAL_POLL_MAX", 2),
    ):
        _score, rows = scanners.run_tessl(workdir)

    ### Then
    assert rows[3]["status"] == "interrupted"
    assert rows[3]["tessl_run_id"] == "eval_pend"


# --- slice-51: Tessl Review (Security) Adapter (Row 5) ---


def _tessl_cli_quality_then_security(cmd, timeout=None, cwd=None, *, security_started):
    """Lint + quality, then security with a distinct view --last id."""
    resolved = _tessl_workspace_cli_ok(cmd, timeout, cwd)
    if resolved is not None:
        return resolved
    if cmd[3:5] == ["skill", "lint"]:
        return 0, "1 check", ""
    if cmd[3:6] == ["review", "run", "quality"]:
        return 0, '{"score": 80, "id": "rev_from_run"}', ""
    if cmd[3:6] == ["review", "run", "security"]:
        security_started.append(True)
        return 0, '{"id": "sec_from_run"}', ""
    if cmd[3:6] == ["review", "view", "--last"]:
        if security_started:
            return 0, '{"id": "sec_rev_def456"}', ""
        return 0, '{"id": "rev_abc123", "score": 80}', ""
    eval_handled = _eval_ok(cmd, timeout, cwd)
    if eval_handled is not None:
        return eval_handled
    raise AssertionError(f"unexpected cmd: {cmd}")


def test_given_quality_row_when_security_runs_then_separate_security_row_written() -> None:
    """
    Scenario: Security review is a separate scan_run_scanners row from Quality.
    Slice: 51 — GWT-51.1

    Given a scan_run has a completed Tessl: Review (Quality) row,
    When the Tessl runner executes the Security Review step,
    Then a Tessl: Review (Security) row is written,
    And the Quality Review row is unchanged.
    """
    ### Given
    security_started: list[bool] = []

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(
            scanners,
            "_run",
            side_effect=lambda cmd, timeout=None, cwd=None: _tessl_cli_quality_then_security(
                cmd, timeout, cwd, security_started=security_started
            ),
        ),
    ):
        score, rows = scanners.run_tessl("/tmp/fake-skill")

    ### Then
    expected_sources = [
        "Tessl: Lint",
        "Tessl: Review (Quality)",
        "Tessl: Scenario Generation",
        "Tessl: Eval",
        "Tessl: Review (Security)",
    ]
    actual_sources = [row["scanner_source"] for row in rows]
    assert actual_sources == expected_sources, (
        f"Expected 5 Tessl rows including Security; got {actual_sources!r}"
    )
    quality_row = rows[1]
    security_row = rows[4]
    assert score == 80, f"Quality score must stay 80; got {score!r}"
    assert quality_row["status"] == "completed", (
        f"Quality row must stay completed; got {quality_row['status']!r}"
    )
    assert quality_row["tessl_run_id"] == "rev_abc123", (
        f"Quality tessl_run_id must stay rev_abc123; got {quality_row.get('tessl_run_id')!r}"
    )
    assert security_row["status"] == "completed", (
        f"Security row should complete; got {security_row['status']!r}"
    )
    assert security_row["tessl_run_id"] == "sec_rev_def456", (
        f"Security tessl_run_id should be its own view --last id; "
        f"got {security_row.get('tessl_run_id')!r}"
    )


def test_given_security_review_when_invoked_then_cli_is_review_run_security() -> None:
    """
    Scenario: Shared adapter is parameterised with judge_type=security.
    Slice: 51 — GWT-51.2

    Given _run_tessl_review(judge_type="security") is called,
    When the underlying CLI invocation runs,
    Then the command is tessl review run security --json --workspace,
    And the result is written to the Security row only.
    """
    ### Given
    captured: list[list[str]] = []
    security_started: list[bool] = []

    def _run(cmd, timeout=None, cwd=None):
        captured.append(cmd)
        return _tessl_cli_quality_then_security(
            cmd, timeout, cwd, security_started=security_started
        )

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
    ):
        _score, rows = scanners.run_tessl("/tmp/fake-skill")

    ### Then
    security_cmds = [c for c in captured if c[3:6] == ["review", "run", "security"]]
    quality_cmds = [c for c in captured if c[3:6] == ["review", "run", "quality"]]
    assert len(quality_cmds) == 1, f"Quality should run once; got {quality_cmds!r}"
    assert len(security_cmds) == 1, f"Security should run once; got {security_cmds!r}"
    assert "--workspace" in security_cmds[0], "Security CLI must pass --workspace"
    assert "engteam" in security_cmds[0], "Security CLI must pass the resolved workspace"
    assert "/tmp/fake-skill" in security_cmds[0], "Security CLI must pass the skill path"
    assert rows[4]["scanner_source"] == "Tessl: Review (Security)"
    assert rows[1]["scanner_source"] == "Tessl: Review (Quality)"


def test_given_quality_id_in_ctx_when_security_starts_then_upstream_run_ids_attached() -> None:
    """
    Scenario: upstream_run_ids.review_quality is written before review run security.
    Slice: 51 — GWT-51.3

    Given ctx review_quality is rev_abc123 from the same run_tessl() invocation,
    When Security Review starts,
    Then upstream_run_ids is attached before review run security,
    And after Security completes, tessl_run_id is Security's own review run ID.
    """
    ### Given
    ctx = {"review_quality": "rev_abc123", "scenario_gen": None}
    progress: list[dict] = []
    security_started: list[bool] = []
    captured: list[list[str]] = []

    def _run(cmd, timeout=None, cwd=None):
        if cmd[3:6] == ["review", "run", "security"]:
            security_progress = [
                p for p in progress if p.get("scanner_source") == "Tessl: Review (Security)"
            ]
            assert security_progress, "Security row must be emitted before CLI invoke"
            assert security_progress[0]["upstream_run_ids"] == {"review_quality": "rev_abc123"}, (
                "upstream_run_ids.review_quality must be attached before "
                f"review run security; got {security_progress[0]!r}"
            )
        captured.append(cmd)
        return _tessl_cli_quality_then_security(
            cmd, timeout, cwd, security_started=security_started
        )

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
    ):
        _score, rows = scanners.run_tessl(
            "/tmp/fake-skill", id_context=ctx, on_row_progress=progress.append
        )

    ### Then
    security_row = rows[4]
    expected_upstream = {"review_quality": "rev_abc123"}
    assert security_row["upstream_run_ids"] == expected_upstream, (
        f"Expected {expected_upstream!r}; got {security_row.get('upstream_run_ids')!r}"
    )
    assert security_row["tessl_run_id"] == "sec_rev_def456", (
        f"Security tessl_run_id should be sec_rev_def456; got {security_row.get('tessl_run_id')!r}"
    )


def test_given_quality_id_missing_when_security_runs_then_upstream_review_quality_is_null() -> None:
    """
    Scenario: Security review proceeds when Quality did not produce a run ID.
    Slice: 51 — GWT-51.4

    Given Quality Review did not produce a run ID (ctx review_quality is null),
    When Security Review runs,
    Then Security Review proceeds without the cross-read,
    And upstream_run_ids.review_quality is null before invocation.
    """
    ### Given
    progress: list[dict] = []
    security_started: list[bool] = []

    def _run(cmd, timeout=None, cwd=None):
        resolved = _tessl_workspace_cli_ok(cmd, timeout, cwd)
        if resolved is not None:
            return resolved
        if cmd[3:5] == ["skill", "lint"]:
            return 0, "1 check", ""
        if cmd[3:6] == ["review", "run", "quality"]:
            return 0, '{"unexpectedKey": "no score here"}', ""
        if cmd[3:6] == ["review", "run", "security"]:
            security_progress = [
                p for p in progress if p.get("scanner_source") == "Tessl: Review (Security)"
            ]
            assert security_progress, "Security row must be emitted before CLI invoke"
            assert security_progress[0]["upstream_run_ids"] == {"review_quality": None}, (
                "upstream_run_ids.review_quality must be explicit null; "
                f"got {security_progress[0].get('upstream_run_ids')!r}"
            )
            security_started.append(True)
            return 0, '{"id": "sec_from_run"}', ""
        if cmd[3:6] == ["review", "view", "--last"]:
            return 0, '{"id": "sec_rev_def456"}', ""
        eval_handled = _eval_ok(cmd, timeout, cwd)
        if eval_handled is not None:
            return eval_handled
        raise AssertionError(f"unexpected cmd: {cmd}")

    ### When
    with (
        patch.dict("os.environ", {"TESSL_TOKEN": "t"}),
        patch.object(scanners, "_resolve_tessl_workspace", return_value=("engteam", "")),
        patch.object(scanners, "_which", return_value="/usr/bin/npx"),
        patch.object(scanners, "_run", side_effect=_run),
    ):
        _score, rows = scanners.run_tessl("/tmp/fake-skill", on_row_progress=progress.append)

    ### Then
    quality_row = rows[1]
    security_row = rows[4]
    assert quality_row["status"] == "unreachable", (
        f"Quality should be unreachable without a score; got {quality_row['status']!r}"
    )
    assert quality_row.get("tessl_run_id") is None, (
        f"Quality must not stamp a run ID; got {quality_row.get('tessl_run_id')!r}"
    )
    assert security_row["scanner_source"] == "Tessl: Review (Security)"
    assert security_row["status"] == "completed"
    assert security_row["upstream_run_ids"] == {"review_quality": None}, (
        f"Expected explicit null review_quality; got {security_row.get('upstream_run_ids')!r}"
    )
    assert security_started, "Security CLI must still be invoked without a Quality ID"
