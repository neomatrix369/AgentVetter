"""Scenario: the .omc/ secrets-scan allowlist never hides tracked files.

Slice: 79 security hardening (review follow-up, allowlist tripwire).
@contract-shape:pure-function
Outcome anchor: Stored evidence never carries raw secret-looking values
"""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


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
