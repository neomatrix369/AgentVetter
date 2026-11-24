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
    """Scenario: an api_key assignment in evidence is masked.

    Slice: evidence redaction (PR #212 review follow-up).
    CONTRACT_SHAPE: bounded-change
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    ### Given
    value = "abc" + "def123456"
    text = 'api_key = "' + value + '"'

    ### When
    out = redact.redact_secrets(text)

    ### Then
    assert value not in out
    assert "api_key=[REDACTED]" in out


def test_given_github_aws_live_key_and_password_when_redacted_then_each_value_becomes_its_placeholder() -> (
    None
):
    """Scenario: common credential formats in evidence are replaced by placeholders.

    Slice: stored-evidence masking (PR #212 review follow-up).
    CONTRACT_SHAPE: bounded-change
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    ### Given
    cases = [
        ("gh" + "p_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4", "[REDACTED_TOKEN]"),
        ("AKIA" + "IOSFODNN7EXAMPLE", "[REDACTED_TOKEN]"),
        ("sk" + "_live_" + "abcdef12345678", "[REDACTED_KEY]"),
        ("pass" + "word=" + "hunter2secret", "password=[REDACTED]"),
    ]

    ### When / Then
    for raw, placeholder in cases:
        assert redact.redact_secrets(f"before {raw} after") == f"before {placeholder} after"


def test_given_quoted_multi_word_api_key_and_password_when_redacted_then_whole_value_is_masked() -> (
    None
):
    """Scenario: a quoted value with spaces is masked to its closing quote.

    Slice: stored-evidence masking (PR #212 review follow-up).
    CONTRACT_SHAPE: bounded-change
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    ### Given
    text = 'api_key = "alpha' + ' beta gamma" and password: "one' + ' two three"'

    ### When
    out = redact.redact_secrets(text)

    ### Then
    for word in ("alpha", "beta", "gamma", "one", "two", "three"):
        assert word not in out, word


def test_given_unterminated_quote_with_spaces_when_redacted_then_rest_of_line_is_masked() -> None:
    """Scenario: a password with no closing quote is masked to the end of its line.

    Slice: stored-evidence masking (PR #212 review follow-up).
    CONTRACT_SHAPE: bounded-change
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    ### Given
    text = 'password="correct horse battery'

    ### When / Then
    assert redact.redact_secrets(text) == "password=[REDACTED]"


def test_given_api_key_spanning_newline_when_redacted_then_whole_value_is_masked() -> None:
    """Scenario: a quoted value that spans lines is masked in full.

    Slice: stored-evidence masking (PR #212 review follow-up).
    CONTRACT_SHAPE: bounded-change
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    ### Given
    text = 'api_key="sk-part1\nsecret2"'

    ### When / Then
    assert redact.redact_secrets(text) == "api_key=[REDACTED]"


def test_given_key_after_non_ascii_letter_when_redacted_then_letter_is_kept_and_key_masked() -> (
    None
):
    """Scenario: ASCII word boundaries mask a key after a non-ASCII letter, as the CLI does.

    Slice: stored-evidence masking (PR #212 review follow-up).
    CONTRACT_SHAPE: bounded-change
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    ### Given
    text = "\u00e9sk-ant-" + "abcdefgh" + "12345678"

    ### When / Then
    assert redact.redact_secrets(text) == "\u00e9[REDACTED_KEY]"


def test_given_non_breaking_space_after_password_label_when_redacted_then_quoted_value_is_masked() -> (
    None
):
    """Scenario: Unicode whitespace after a label is matched the same way by the CLI and the sandbox.

    Slice: stored-evidence masking (PR #212 review follow-up).
    CONTRACT_SHAPE: bounded-change
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    ### Given
    text = 'password:\u00a0"correct horse"'

    ### When / Then
    assert redact.redact_secrets(text) == "password=[REDACTED]"


def test_given_byte_order_mark_as_separator_when_redacted_then_bearer_and_password_are_masked() -> (
    None
):
    """Scenario: a zero-width no-break space counts as whitespace in both the CLI and the sandbox.

    Slice: stored-evidence masking (PR #212 review follow-up).
    CONTRACT_SHAPE: bounded-change
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    ### Given / When / Then
    assert redact.redact_secrets("Bearer\ufefftok") == "Bearer [REDACTED]"
    assert redact.redact_secrets('password:\ufeff"correct horse"') == "password=[REDACTED]"


def test_given_control_and_zero_width_separators_when_redacted_then_bearer_tokens_are_masked() -> (
    None
):
    """Scenario: NEL, unit-separator and zero-width-space characters separate a Bearer token as whitespace.

    Slice: stored-evidence masking (PR #212 review follow-up).
    CONTRACT_SHAPE: bounded-change
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    ### Given / When / Then
    assert redact.redact_secrets("Bearer\x85tok") == "Bearer [REDACTED]"
    assert redact.redact_secrets("Bearer\x1ftok") == "Bearer [REDACTED]"
    assert redact.redact_secrets("Bearer\u200btok") == "Bearer [REDACTED]"


FAKE_JWT = "eyJ" + "hbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiIxMjMifQ" + "." + "c2lnbmF0dXJlMTIz"


def test_given_jwt_in_snippet_when_redacted_then_token_is_masked() -> None:
    """Scenario: a JSON Web Token in scanned output is masked before it is stored.

    Slice: 79 security hardening (GWT-62.1).
    CONTRACT_SHAPE: bounded-change
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    ### Given
    text = "auth=" + FAKE_JWT + " end"

    ### When
    out = redact.redact_secrets(text)

    ### Then
    assert FAKE_JWT not in out
    assert out == "auth=[REDACTED] end"


def test_given_database_connection_uris_when_redacted_then_whole_uri_is_masked() -> None:
    """Scenario: connection strings with embedded credentials are masked in full.

    Slice: 79 security hardening (GWT-62.2).
    CONTRACT_SHAPE: bounded-change
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    ### Given
    cases = [
        "postgresql://" + "app:hunter" + "2@db.internal:5432/app",
        "mongodb+srv://" + "svc:pw" + "@cluster0.example.net/prod",
        "mysql://" + "root:r00t" + "@127.0.0.1/shop",
    ]

    ### When / Then
    for uri in cases:
        assert redact.redact_secrets(f"dsn={uri} end") == "dsn=[REDACTED] end", uri


def test_given_non_prefix_service_tokens_when_redacted_then_each_token_is_masked() -> None:
    """Scenario: Cloudflare and Fly.io tokens in scanned output are masked.

    Slice: 79 security hardening (GWT-62.3).
    CONTRACT_SHAPE: bounded-change
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    ### Given
    cases = [
        "v1.0-" + "abcdef0123456789abcdef0123456789",
        "FlyV1 " + "fm2_" + "AbCdEf0123456789XyZ",
        "fo1_" + "AbCdEf0123456789XyZ0123",
    ]

    ### When / Then
    for token in cases:
        assert redact.redact_secrets(f"token {token} end") == "token [REDACTED] end", token


def test_given_commit_sha_and_dotted_identifiers_when_redacted_then_text_is_unchanged() -> None:
    """Scenario: new rules do not mask a git SHA or a dotted module path.

    Slice: 79 security hardening (regression guard for GWT-62.3).
    CONTRACT_SHAPE: bounded-change
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    ### Given
    text = "commit 3f786850e387550fdab836ed7e6dc881de23001b imports pkg.sub.module"

    ### When / Then
    assert redact.redact_secrets(text) == text


FAKE_NETLIFY = "abcdefghijklmnop" + "12345"


def test_given_labelled_netlify_token_when_redacted_then_value_is_masked() -> None:
    """Scenario: a Netlify token next to its label is masked; the label is normalised to netlify_token.

    Slice: 79 security hardening (GWT-62.3, Netlify).
    CONTRACT_SHAPE: bounded-change
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    ### Given
    text = "deploy NETLIFY_AUTH_TOKEN=" + FAKE_NETLIFY + " end"

    ### When
    out = redact.redact_secrets(text)

    ### Then
    assert FAKE_NETLIFY not in out
    assert out == "deploy netlify_token=[REDACTED] end"


def test_given_non_ascii_letter_before_netlify_label_when_redacted_then_value_is_masked() -> None:
    """Scenario: a Netlify label after a non-ASCII letter is still masked, as in the CLI.

    Slice: 79 security hardening (review follow-up, GWT-62.3).
    CONTRACT_SHAPE: bounded-change
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    ### Given
    text = "\u00e9" + "NETLIFY_AUTH_TOKEN=" + FAKE_NETLIFY

    ### When
    out = redact.redact_secrets(text)

    ### Then
    assert FAKE_NETLIFY not in out
    assert out == "\u00e9netlify_token=[REDACTED]"


def test_given_non_breaking_space_in_uri_and_fly_token_when_redacted_then_only_the_token_is_masked() -> (
    None
):
    """Scenario: Unicode spaces end a connection string and separate a Fly token label the same way in both languages.

    Slice: 79 security hardening (review follow-up, parity).
    CONTRACT_SHAPE: bounded-change
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    ### Given
    text = "dsn=postgresql://app:pw@h/x\u00a0end FlyV1\u00a0fm2_AbCdEf0123456789XyZ"

    ### When / Then
    assert redact.redact_secrets(text) == "dsn=[REDACTED]\u00a0end [REDACTED]"
