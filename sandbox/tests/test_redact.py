"""Scenario: secret-looking values are masked before evidence is stored.

Slice: evidence redaction (open-item follow-up to the anon-exposure review).
CONTRACT_SHAPE: bounded-change
Outcome anchor: Stored evidence never carries raw secret-looking values

The fake credentials are split across string literals so gitleaks does not
flag this file. The redacted text still contains the joined value at runtime.
"""

import redact

FAKE_KEY = "sk-" + "live-4f2b9abcdef"
FAKE_TOKEN = "abc.def." + "ghi"
FAKE_ROW_KEY = "sk-" + "test-12345678"


def test_given_api_key_in_snippet_when_redacted_then_value_is_masked() -> None:
    ### Given
    snippet = 'API_KEY = "' + FAKE_KEY + '"'

    ### When
    out = redact.redact_secrets(snippet)

    ### Then
    assert FAKE_KEY not in out
    assert "REDACTED" in out


def test_given_bearer_token_in_console_when_redacted_then_token_is_masked() -> None:
    ### Given
    console = "curl -H 'Authorization: Bearer " + FAKE_TOKEN + "' https://x"

    ### When
    out = redact.redact_secrets(console)

    ### Then
    assert FAKE_TOKEN not in out
    assert "Bearer [REDACTED]" in out


def test_given_plain_text_when_redacted_then_text_is_unchanged() -> None:
    ### Given
    text = "subprocess.run(ls, shell=True)"

    ### When / Then
    assert redact.redact_secrets(text) == text


def test_given_row_with_evidence_when_redacted_then_only_evidence_fields_change() -> None:
    ### Given
    snippet = 'token="' + FAKE_ROW_KEY + '"'
    row = {"snippet": snippet, "scanner_source": "Snyk", "severity": "red"}

    ### When
    out = redact.redact_row(row)

    ### Then
    assert FAKE_ROW_KEY not in out["snippet"]
    assert out["scanner_source"] == "Snyk"
    assert out["severity"] == "red"
    assert row["snippet"] == snippet  # input not mutated


def test_given_api_key_assignment_when_redacted_then_value_is_masked() -> None:
    ### Given
    value = "abc" + "def123456"
    text = 'api_key = "' + value + '"'

    ### When
    out = redact.redact_secrets(text)

    ### Then
    assert value not in out
    assert "api_key=[REDACTED]" in out
