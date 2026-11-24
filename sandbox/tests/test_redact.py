"""Scenario: secret-looking values are masked before evidence is stored.

Slice: evidence redaction (open-item follow-up to the anon-exposure review).
@contract-shape:pure-function
Outcome anchor: Stored evidence never carries raw secret-looking values

The fake credentials are split across string literals so gitleaks does not
flag this file. The redacted text still contains the joined value at runtime.
"""

import pytest
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
    @contract-shape:pure-function
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
    @contract-shape:pure-function
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
    @contract-shape:pure-function
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
    @contract-shape:pure-function
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    ### Given
    text = 'password="correct horse battery'

    ### When / Then
    assert redact.redact_secrets(text) == "password=[REDACTED]"


def test_given_api_key_spanning_newline_when_redacted_then_whole_value_is_masked() -> None:
    """Scenario: a quoted value that spans lines is masked in full.

    Slice: stored-evidence masking (PR #212 review follow-up).
    @contract-shape:pure-function
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
    @contract-shape:pure-function
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
    @contract-shape:pure-function
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
    @contract-shape:pure-function
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
    @contract-shape:pure-function
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    ### Given / When / Then
    assert redact.redact_secrets("Bearer\x85tok") == "Bearer [REDACTED]"
    assert redact.redact_secrets("Bearer\x1ftok") == "Bearer [REDACTED]"
    assert redact.redact_secrets("Bearer\u200btok") == "Bearer [REDACTED]"


JWT = "eyJ" + "hbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiIxMjMifQ" + "." + "c2lnbmF0dXJlMTIz"
CF_BODY = "a1B2c3D4e5F6g7H8i9J0" * 2
FAKE_NETLIFY = "abcdefghijklmnop" + "12345"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (JWT, "[REDACTED]"),
        ("auth=" + JWT + " end", "auth=[REDACTED] end"),
        ("x-auth-" + JWT, "x-auth-[REDACTED]"),
        ("jwt_" + JWT, "jwt_[REDACTED]"),
    ],
    ids=["plain", "after-equals", "after-dash", "after-underscore"],
)
def test_given_jwt_in_any_position_when_redacted_then_token_is_masked(
    text: str, expected: str
) -> None:
    """Scenario: a JWT is masked wherever it appears in scanned text.

    Slice: 79 security hardening (GWT-62.1).
    @contract-shape:pure-function
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    ### Given / When / Then
    assert redact.redact_secrets(text) == expected


@pytest.mark.parametrize(
    "scheme_and_creds",
    [
        "postgresql://" + "app:hunter" + "2@db.internal:5432/app",
        "postgres://" + "app:pw" + "@db/x",
        "mysql://" + "root:r00t" + "@127.0.0.1/shop",
        "mariadb://" + "u:p" + "@db/x",
        "mongodb+srv://" + "svc:pw" + "@cluster0.example.net/prod",
        "redis://" + ":pw" + "@cache:6379/0",
        "amqp://" + "guest:g" + "@broker/vhost",
    ],
)
def test_given_connection_uri_when_redacted_then_whole_uri_is_masked(scheme_and_creds: str) -> None:
    """Scenario: connection strings with embedded credentials are masked in full.

    Slice: 79 security hardening (GWT-62.2).
    @contract-shape:pure-function
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    ### Given / When / Then
    assert redact.redact_secrets(f"dsn={scheme_and_creds} end") == "dsn=[REDACTED] end"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("token cfut_" + CF_BODY + "k1l2m3 end", "token [REDACTED] end"),
        ("token cfat_" + CF_BODY + "k1l2m3 end", "token [REDACTED] end"),
        ("token cfk_" + CF_BODY + "k1l2m3 end", "token [REDACTED] end"),
        ("token FlyV1 fm2_AbCdEf0123456789XyZ end", "token [REDACTED] end"),
        ("token fo1_AbCdEf0123456789XyZ0123 end", "token [REDACTED] end"),
        (
            "deploy NETLIFY_AUTH_TOKEN=" + FAKE_NETLIFY + " end",
            "deploy netlify_token=[REDACTED] end",
        ),
        (
            "deploy DEPLOY_NETLIFY_AUTH_TOKEN=" + FAKE_NETLIFY + " end",
            "deploy DEPLOY_netlify_token=[REDACTED] end",
        ),
        ("tag X_fm2_AbCdEf0123456789XyZ end", "tag X_[REDACTED] end"),
        ("tag X_cfut_" + CF_BODY + "k1l2m3 end", "tag X_[REDACTED] end"),
    ],
    ids=[
        "cf-user",
        "cf-account",
        "cf-global",
        "fly-fm2",
        "fly-fo1",
        "netlify-labelled",
        "netlify-underscore-prefix",
        "fly-underscore-prefix",
        "cf-underscore-prefix",
    ],
)
def test_given_service_token_in_amended_format_when_redacted_then_token_is_masked(
    text: str, expected: str
) -> None:
    """Scenario: service tokens in the amended formats are masked (fo1_ kept by operator decision); a labelled Netlify value keeps only its label name.

    Slice: 79 security hardening (GWT-62.3, amended).
    @contract-shape:pure-function
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    ### Given / When / Then
    assert redact.redact_secrets(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "commit 3f786850e387550fdab836ed7e6dc881de23001b imports pkg.sub.module",
        "release v1.0-release-20241231 shipped",
        "token cfut_" + CF_BODY[:39] + " end",
        "token " + CF_BODY + " end",
        "token abcdefghijklmnop12345 end",
    ],
    ids=[
        "git-sha-and-dotted",
        "v1-release",
        "cf-39-chars",
        "cf-legacy-unprefixed",
        "netlify-unlabelled",
    ],
)
def test_given_shape_outside_the_rules_when_redacted_then_text_is_unchanged(text: str) -> None:
    """Scenario: hashes, release identifiers, short or legacy Cloudflare strings and unlabelled Netlify tokens are left unchanged.

    Slice: 79 security hardening (GWT-62.3 negatives, amended).
    @contract-shape:pure-function
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    ### Given / When / Then
    assert redact.redact_secrets(text) == text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("\u00e9NETLIFY_AUTH_TOKEN=" + FAKE_NETLIFY, "\u00e9netlify_token=[REDACTED]"),
        (
            "dsn=postgresql://app:pw@h/x\u00a0end FlyV1\u00a0fm2_AbCdEf0123456789XyZ",
            "dsn=[REDACTED]\u00a0end [REDACTED]",
        ),
    ],
    ids=["non-ascii-before-label", "nbsp-separators"],
)
def test_given_unicode_boundary_and_spacing_when_redacted_then_masking_matches_cli(
    text: str, expected: str
) -> None:
    """Scenario: non-ASCII letters and Unicode spaces are handled the same way in the sandbox and the CLI.

    Slice: 79 security hardening (review follow-up, parity).
    @contract-shape:pure-function
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    ### Given / When / Then
    assert redact.redact_secrets(text) == expected


def test_given_jwt_in_evidence_row_when_redact_row_then_snippet_is_masked() -> None:
    """Scenario: a JWT in an evidence row's snippet is masked by the write-path helper.

    Slice: 79 security hardening (GWT-62.1, write path).
    @contract-shape:pure-function
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    ### Given
    row = {"snippet": "auth=" + JWT, "scanner_source": "Snyk"}

    ### When
    out = redact.redact_row(row)

    ### Then
    assert out["snippet"] == "auth=[REDACTED]"
    assert out["scanner_source"] == "Snyk"


def test_given_adversarial_jwt_like_run_when_redacted_then_it_finishes_quickly() -> None:
    """Scenario: a long run of JWT-like fragments is scanned within a bounded time (per-start cost is capped, not linear).

    Slice: 79 security hardening (review follow-up, JWT rule).
    @contract-shape:pure-function
    Outcome anchor: Stored evidence never carries raw secret-looking values
    """
    import time

    ### Given
    text = "eyJ-" * 5000
    dotted = ("eyJ" + "a" * 50 + ".") * 400

    ### When
    started = time.perf_counter()
    redact.redact_secrets(text)
    redact.redact_secrets(dotted)
    elapsed = time.perf_counter() - started

    ### Then
    assert elapsed < 2.0, f"redaction took {elapsed:.2f}s"
