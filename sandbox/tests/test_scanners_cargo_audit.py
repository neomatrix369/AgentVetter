"""Tests for the Cargo Audit (RustSec) adapter."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import scanners

SAMPLE_VULN_JSON = json.dumps(
    {
        "vulnerabilities": {
            "found": True,
            "count": 1,
            "list": [
                {
                    "advisory": {
                        "id": "RUSTSEC-2022-0051",
                        "package": "lz4-sys",
                        "title": "Memory corruption in liblz4",
                        "url": "https://rustsec.org/advisories/RUSTSEC-2022-0051",
                        "severity": "high",
                    },
                    "package": {"name": "lz4-sys", "version": "1.9.3"},
                }
            ],
        }
    }
)


def test_given_no_cargo_when_run_cargo_audit_then_not_applicable(tmp_path: Path) -> None:
    findings, rows = scanners.run_cargo_audit(str(tmp_path), "package")
    assert findings == []
    assert len(rows) == 1
    assert rows[0]["status"] == "not_applicable"
    assert "Cargo" in rows[0]["detail"]


def test_given_cargo_lock_and_vuln_json_when_run_then_completed_with_finding(
    tmp_path: Path,
) -> None:
    (tmp_path / "Cargo.lock").write_text("# lock\n", encoding="utf-8")
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\n', encoding="utf-8")

    def _fake_run(cmd, timeout=None, cwd=None):
        assert "--json" in cmd
        return 1, SAMPLE_VULN_JSON, ""

    with (
        patch.object(scanners, "_which", return_value=True),
        patch.object(scanners, "_run", side_effect=_fake_run),
    ):
        findings, rows = scanners.run_cargo_audit(str(tmp_path), "package")

    assert len(findings) == 1
    assert findings[0]["cve_ids"] == ["RUSTSEC-2022-0051"]
    assert findings[0]["file_path"] == "Cargo.lock"
    assert findings[0]["package_name"]
    assert findings[0]["severity"] == "red"
    assert rows[0]["status"] == "completed"
    assert rows[0]["scanner_source"] == "Cargo Audit"


def test_given_clean_json_when_run_then_completed_zero_findings(tmp_path: Path) -> None:
    (tmp_path / "Cargo.lock").write_text("# lock\n", encoding="utf-8")
    clean = json.dumps({"vulnerabilities": {"found": False, "count": 0, "list": []}})

    with (
        patch.object(scanners, "_which", side_effect=lambda b: b == "cargo-audit"),
        patch.object(scanners, "_run", return_value=(0, clean, "")),
    ):
        findings, rows = scanners.run_cargo_audit(str(tmp_path), "package")

    assert findings == []
    assert rows[0]["status"] == "completed"


def test_given_missing_binary_when_run_then_unreachable(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\n', encoding="utf-8")

    with patch.object(scanners, "_which", return_value=False):
        findings, rows = scanners.run_cargo_audit(str(tmp_path), "package")

    assert findings == []
    assert rows[0]["status"] == "unreachable"


def test_given_registry_when_list_groups_then_cargo_audit_between_depshield_ossprey() -> None:
    sources = [tuple(g["sources"]) for g in scanners.SCANNER_GROUPS]
    assert ("Cargo Audit",) in sources
    dep_i = next(i for i, s in enumerate(sources) if s == ("DepShield",))
    cargo_i = next(i for i, s in enumerate(sources) if s == ("Cargo Audit",))
    oss_i = next(i for i, s in enumerate(sources) if s == ("Ossprey",))
    assert dep_i < cargo_i < oss_i


def test_given_tail_timeouts_when_summed_then_within_scan_timeout() -> None:
    tail = (
        scanners.DEPSHIELD_TIMEOUT
        + scanners.CARGO_AUDIT_TIMEOUT
        + scanners.PRESEND_TIMEOUT
        + scanners.OSSPREY_TIMEOUT
    )
    assert tail <= scanners.SCAN_TIMEOUT


def test_given_cargo_only_when_which_cargo_then_uses_cargo_audit_subcommand(
    tmp_path: Path,
) -> None:
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\n', encoding="utf-8")
    clean = json.dumps({"vulnerabilities": {"found": False, "count": 0, "list": []}})
    seen: list[list[str]] = []

    def _fake_run(cmd, timeout=None, cwd=None):
        seen.append(list(cmd))
        return 0, clean, ""

    with (
        patch.object(scanners, "_which", side_effect=lambda b: b == "cargo"),
        patch.object(scanners, "_run", side_effect=_fake_run),
    ):
        _, rows = scanners.run_cargo_audit(str(tmp_path), "package")

    assert seen and seen[0][:2] == ["cargo", "audit"]
    assert rows[0]["status"] == "completed"


def test_given_nested_lock_when_run_then_passes_file_flag(tmp_path: Path) -> None:
    nested = tmp_path / "crates" / "inner"
    nested.mkdir(parents=True)
    (nested / "Cargo.lock").write_text("# lock\n", encoding="utf-8")
    clean = json.dumps({"vulnerabilities": {"found": False, "count": 0, "list": []}})
    seen: list[list[str]] = []

    def _fake_run(cmd, timeout=None, cwd=None):
        seen.append(list(cmd))
        return 0, clean, ""

    with (
        patch.object(scanners, "_which", return_value=True),
        patch.object(scanners, "_run", side_effect=_fake_run),
    ):
        _, rows = scanners.run_cargo_audit(str(tmp_path), "package")

    assert rows[0]["status"] == "completed"
    assert any("--file" in c for c in seen)


def test_given_timeout_when_run_then_unreachable(tmp_path: Path) -> None:
    (tmp_path / "Cargo.lock").write_text("# lock\n", encoding="utf-8")

    with (
        patch.object(scanners, "_which", return_value=True),
        patch.object(
            scanners,
            "_run",
            side_effect=subprocess.TimeoutExpired(cmd="cargo-audit", timeout=1),
        ),
    ):
        findings, rows = scanners.run_cargo_audit(str(tmp_path), "package")

    assert findings == []
    assert rows[0]["status"] == "unreachable"
    assert "timed out" in rows[0]["detail"]


def test_given_oserror_when_run_then_unreachable(tmp_path: Path) -> None:
    (tmp_path / "Cargo.lock").write_text("# lock\n", encoding="utf-8")

    with (
        patch.object(scanners, "_which", return_value=True),
        patch.object(scanners, "_run", side_effect=OSError("boom")),
    ):
        findings, rows = scanners.run_cargo_audit(str(tmp_path), "package")

    assert findings == []
    assert rows[0]["status"] == "unreachable"
    assert "failed to start" in rows[0]["detail"]


def test_given_exit_2_when_run_then_unreachable(tmp_path: Path) -> None:
    (tmp_path / "Cargo.lock").write_text("# lock\n", encoding="utf-8")

    with (
        patch.object(scanners, "_which", return_value=True),
        patch.object(scanners, "_run", return_value=(2, "", "tool error")),
    ):
        findings, rows = scanners.run_cargo_audit(str(tmp_path), "package")

    assert findings == []
    assert rows[0]["status"] == "unreachable"


def test_given_bad_json_when_run_then_unreachable(tmp_path: Path) -> None:
    (tmp_path / "Cargo.lock").write_text("# lock\n", encoding="utf-8")

    with (
        patch.object(scanners, "_which", return_value=True),
        patch.object(scanners, "_run", return_value=(0, "not-json{{{", "")),
    ):
        findings, rows = scanners.run_cargo_audit(str(tmp_path), "package")

    assert findings == []
    assert rows[0]["status"] == "unreachable"
    assert "JSON" in rows[0]["detail"]


def test_given_cvss_score_when_finding_then_severity_red() -> None:
    entry = {
        "advisory": {"id": "RUSTSEC-1", "cvss": {"score": "9.1"}, "title": "x"},
        "package": {"name": "crate", "version": "1.0"},
    }
    finding = scanners._cargo_audit_finding(entry, "Cargo.lock")
    assert finding["severity"] == "red"


def test_given_cvss_low_score_when_finding_then_amber() -> None:
    entry = {
        "advisory": {"id": "RUSTSEC-2", "cvss": {"score": "3.1"}, "title": "low"},
        "package": {"name": "crate", "version": "1.0"},
    }
    assert scanners._cargo_audit_finding(entry, "Cargo.lock")["severity"] == "amber"


def test_given_bad_cvss_when_severity_then_amber() -> None:
    assert scanners._cargo_audit_severity({"cvss": {"score": "nope"}}) == "amber"


def test_given_non_dict_advisory_when_severity_then_amber() -> None:
    assert scanners._cargo_audit_severity("high") == "amber"


def test_given_malformed_entry_when_finding_then_defaults() -> None:
    finding = scanners._cargo_audit_finding({"advisory": "x", "package": None}, "Cargo.lock")
    assert finding["cve_ids"] == ["RUSTSEC-unknown"]
    assert finding["package_name"] == "unknown"
    assert finding["package_version"] is None
    assert finding["severity"] == "amber"
    assert finding["file_path"] == "Cargo.lock"
    assert finding["advisory_provider"] == "rustsec"
    # Must not emit schema-invalid keys (would fail findings INSERT → run failed).
    assert "rule_id" not in finding
    assert "file" not in finding
    assert "line" not in finding
    assert "entity_kind" not in finding


def test_given_vulns_not_dict_when_parse_then_empty() -> None:
    findings, checks, err = scanners._parse_cargo_audit_json('{"vulnerabilities":[]}', "Cargo.lock")
    assert findings == []
    assert checks == 0
    assert err is None


def test_given_list_not_list_when_parse_then_empty_findings() -> None:
    text = json.dumps({"vulnerabilities": {"count": 0, "list": {"bad": True}}})
    findings, checks, err = scanners._parse_cargo_audit_json(text, "Cargo.lock")
    assert findings == []
    assert checks == 1
    assert err is None


def test_given_empty_stdout_parse_err_exit0_when_run_then_completed(
    tmp_path: Path,
) -> None:
    (tmp_path / "Cargo.lock").write_text("# lock\n", encoding="utf-8")

    with (
        patch.object(scanners, "_which", return_value=True),
        patch.object(scanners, "_run", return_value=(0, "", "")),
        patch.object(
            scanners,
            "_parse_cargo_audit_json",
            return_value=([], 0, "cargo-audit JSON parse failed"),
        ),
    ):
        findings, rows = scanners.run_cargo_audit(str(tmp_path), "package")

    assert findings == []
    assert rows[0]["status"] == "completed"


def test_given_toml_only_completed_when_run_then_detail_mentions_toml(
    tmp_path: Path,
) -> None:
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\n', encoding="utf-8")
    clean = json.dumps({"vulnerabilities": {"found": False, "count": 0, "list": []}})

    with (
        patch.object(scanners, "_which", return_value=True),
        patch.object(scanners, "_run", return_value=(0, clean, "")),
    ):
        _, rows = scanners.run_cargo_audit(str(tmp_path), "package")

    assert rows[0]["status"] == "completed"
    assert "Cargo.toml" in (rows[0].get("detail") or "")


def test_given_group_runner_when_invoked_then_returns_triple(tmp_path: Path) -> None:
    findings, rows, quality = scanners._run_cargo_audit_group(str(tmp_path), "package", None)
    assert findings == []
    assert rows[0]["status"] == "not_applicable"
    assert quality is None


def test_given_only_cargo_binary_when_cmd_then_cargo_audit_subcommand() -> None:
    with patch.object(scanners, "_which", side_effect=lambda b: b == "cargo"):
        assert scanners._cargo_audit_cmd() == ["cargo", "audit"]


def test_given_cargo_audit_binary_when_cmd_then_includes_audit_token() -> None:
    """Direct cargo-audit invoke must pass 'audit' or --json is eaten by cargo clap."""
    with patch.object(scanners, "_which", side_effect=lambda b: b == "cargo-audit"):
        assert scanners._cargo_audit_cmd() == ["cargo-audit", "audit"]


def test_given_cargo_audit_binary_when_run_then_argv_is_audit_then_json(
    tmp_path: Path,
) -> None:
    (tmp_path / "Cargo.lock").write_text("# lock\n", encoding="utf-8")
    captured: dict = {}

    def _fake_run(cmd, timeout=None, cwd=None):
        captured["cmd"] = list(cmd)
        return 0, json.dumps({"vulnerabilities": {"found": False, "count": 0, "list": []}}), ""

    with (
        patch.object(scanners, "_which", side_effect=lambda b: b == "cargo-audit"),
        patch.object(scanners, "_run", side_effect=_fake_run),
    ):
        scanners.run_cargo_audit(str(tmp_path), "package")

    assert captured["cmd"][:3] == ["cargo-audit", "audit", "--json"]


def test_given_cvss_and_malformed_when_severity_then_maps() -> None:
    assert scanners._cargo_audit_severity("x") == "amber"
    assert scanners._cargo_audit_severity({"severity": "medium"}) == "amber"
    assert scanners._cargo_audit_severity({"cvss": {"score": 9.1}}) == "red"
    assert scanners._cargo_audit_severity({"cvss": {"score": 3.2}}) == "amber"
    assert scanners._cargo_audit_severity({"cvss": {"score": "bad"}}) == "amber"
    assert scanners._cargo_audit_severity({}) == "amber"


def test_given_nested_cargo_lock_when_run_then_passes_file_flag(tmp_path: Path) -> None:
    nested = tmp_path / "crates" / "lib"
    nested.mkdir(parents=True)
    (nested / "Cargo.lock").write_text("# lock\n", encoding="utf-8")
    (nested / "Cargo.toml").write_text('[package]\nname = "lib"\n', encoding="utf-8")
    captured: dict = {}

    def _fake_run(cmd, timeout=None, cwd=None):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        return 0, json.dumps({"vulnerabilities": {"found": False, "count": 0, "list": []}}), ""

    with (
        patch.object(scanners, "_which", side_effect=lambda b: b == "cargo-audit"),
        patch.object(scanners, "_run", side_effect=_fake_run),
    ):
        findings, rows = scanners.run_cargo_audit(str(tmp_path), "package")

    assert findings == []
    assert rows[0]["status"] == "completed"
    assert "--file" in captured["cmd"]
    assert captured["cwd"] == str(tmp_path)


def test_given_cargo_toml_only_when_run_then_detail_notes_toml(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\n', encoding="utf-8")
    clean = json.dumps({"vulnerabilities": {"found": False, "count": 0, "list": []}})

    with (
        patch.object(scanners, "_which", side_effect=lambda b: b == "cargo-audit"),
        patch.object(scanners, "_run", return_value=(0, clean, "")),
    ):
        findings, rows = scanners.run_cargo_audit(str(tmp_path), "package")

    assert findings == []
    assert "Cargo.toml" in rows[0].get("detail", "")


def test_given_empty_stdout_exit0_when_run_then_completed(tmp_path: Path) -> None:
    (tmp_path / "Cargo.lock").write_text("# lock\n", encoding="utf-8")

    with (
        patch.object(scanners, "_which", return_value=True),
        patch.object(scanners, "_run", return_value=(0, "", "")),
    ):
        findings, rows = scanners.run_cargo_audit(str(tmp_path), "package")

    assert findings == []
    assert rows[0]["status"] == "completed"


def test_given_non_dict_entry_when_finding_then_defaults() -> None:
    finding = scanners._cargo_audit_finding("not-a-dict", "Cargo.lock")
    assert finding["cve_ids"] == ["RUSTSEC-unknown"]
    assert finding["package_name"] == "unknown"
    finding2 = scanners._cargo_audit_finding({"advisory": "x", "package": "y"}, "Cargo.lock")
    assert finding2["severity"] == "amber"


def test_given_non_list_vulns_when_parse_then_empty() -> None:
    findings, checks, err = scanners._parse_cargo_audit_json(
        json.dumps({"vulnerabilities": {"count": 0, "list": "x"}}), "Cargo.lock"
    )
    assert findings == []
    assert err is None
    assert checks >= 1
