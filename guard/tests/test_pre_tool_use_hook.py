"""Scenario: every Bash call reaches the guard, including the old marker-path shape.

Slice: Bash bypass regression (security review finding, PR #209).

The hook used to let a Bash call skip the guard when its text contained a
skills-path marker. ``cd $D/skills/x && bash install.sh`` slipped through that
substring test. The hook now sends every Bash call to the guard entry.
"""

import json
import os
import stat
import subprocess
from pathlib import Path

HOOK = Path(__file__).resolve().parents[2] / "agent-hooks" / "hooks" / "pre-tool-use.sh"


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run_hook(tmp_path: Path, command: str) -> tuple[str, str]:
    """Run the hook with a stub guard runner; return (stub_log, hook_stdout)."""
    home = tmp_path / "home"
    (home / ".agentvetter" / "hooks").mkdir(parents=True)
    log = tmp_path / "guard-calls.log"

    # Stub `uv`: record that the guard was invoked, then deny so the hook has a verdict.
    stub_uv = tmp_path / "uv"
    _write_executable(
        stub_uv,
        f'#!/bin/sh\necho "guard-invoked" >> "{log}"\n'
        'echo \'{"allow": false, "reason": "stub deny"}\'\n',
    )
    config = {
        "enable": True,
        "env_file": "",
        "repo_root": str(tmp_path),
        "uv_bin": str(stub_uv),
    }
    (home / ".agentvetter" / "config.json").write_text(json.dumps(config), encoding="utf-8")
    (home / ".agentvetter" / "hooks" / "_guard_entry.py").write_text("", encoding="utf-8")

    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    env = {**os.environ, "HOME": str(home), "TMPDIR": str(tmp_path)}
    proc = subprocess.run(
        ["bash", str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )
    stub_log = log.read_text(encoding="utf-8") if log.exists() else ""
    return stub_log, proc.stdout


def test_given_bash_call_with_skills_marker_when_hook_runs_then_guard_is_invoked(tmp_path) -> None:
    ### Given
    command = "cd ~/.claude/skills/demo && bash install.sh"

    ### When
    stub_log, _stdout = _run_hook(tmp_path, command)

    ### Then
    assert "guard-invoked" in stub_log


def test_given_plain_bash_call_when_hook_runs_then_guard_is_also_invoked(tmp_path) -> None:
    ### Given
    command = "ls -la"

    ### When
    stub_log, _stdout = _run_hook(tmp_path, command)

    ### Then
    assert "guard-invoked" in stub_log
