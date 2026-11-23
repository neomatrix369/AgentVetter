"""Scenario: scanner subprocesses never inherit Supabase service-role or Modal secrets.

Slice: scanner env filter (security review finding, PR #211).
"""

import sys

import scanners


def test_given_supabase_and_modal_secrets_when_env_built_then_they_are_removed(monkeypatch) -> None:
    ### Given
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")
    monkeypatch.setenv("MODAL_TOKEN_SECRET", "modal-secret")
    monkeypatch.setenv("SNYK_TOKEN", "snyk-token")

    ### When
    env = scanners.scanner_subprocess_env()

    ### Then
    assert "SUPABASE_SERVICE_ROLE_KEY" not in env
    assert "MODAL_TOKEN_SECRET" not in env
    assert env["SNYK_TOKEN"] == "snyk-token"


def test_given_child_process_when_run_then_it_cannot_read_service_key(monkeypatch) -> None:
    ### Given
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")
    probe = "import os; print(os.environ.get('SUPABASE_SERVICE_ROLE_KEY', 'absent'))"

    ### When
    _code, stdout, _err = scanners._run([sys.executable, "-c", probe])

    ### Then
    assert stdout.strip() == "absent"
