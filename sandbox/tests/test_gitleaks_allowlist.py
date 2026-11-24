"""Scenario: the .omc/ secrets-scan allowlist never hides tracked files.

Slice: 79 security hardening (review follow-up, allowlist tripwire).
@contract-shape:pure-function
Outcome anchor: Stored evidence never carries raw secret-looking values
"""

import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def test_given_gitleaks_config_when_reading_allowlist_then_omc_state_path_is_excluded() -> None:
    """Scenario: the gitleaks allowlist excludes the .omc/ state path, as recorded in DECISIONS.md (2026-11-24).

    Slice: 79 security hardening (gitleaks allowlist).
    @contract-shape:pure-function
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    ### Given / When
    allowlist = tomllib.loads((REPO / ".gitleaks.toml").read_text(encoding="utf-8"))["allowlist"]

    ### Then
    assert r"\.omc/" in allowlist["paths"]


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_given_repository_when_listing_tracked_files_then_no_omc_state_is_tracked() -> None:
    """Scenario: .omc/ session state is git-ignored and never committed.

    Slice: 79 security hardening (review follow-up, allowlist tripwire).
    @contract-shape:pure-function
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    ### Given / When
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=False
    ).stdout.splitlines()

    ### Then
    leaked = [path for path in tracked if "/.omc/" in f"/{path}"]
    assert leaked == [], f".omc/ state must not be tracked: {leaked[:5]}"
