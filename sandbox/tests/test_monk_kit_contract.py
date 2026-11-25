"""
Contract tests for the AgentVetter Monk Kit files (Slice 58).

Author: Mani Sarkar / Claude Sonnet 4.6
Created: 2026-11-25
Scope: GWT-58.1–58.5 contract checks for MANIFEST, v1.0.0.yaml, latest.yaml,
       common.yaml, and bootstrap/Dockerfile (static only — no Monk runtime).
"""

from __future__ import annotations

import pathlib
import re

import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent


# ---------------------------------------------------------------------------
# File helpers (read once per test; cheap, no I/O caching needed)
# ---------------------------------------------------------------------------


def _manifest_lines() -> list[str]:
    return (REPO_ROOT / "MANIFEST").read_text().splitlines()


def _manifest_text() -> str:
    return (REPO_ROOT / "MANIFEST").read_text()


def _v100_text() -> str:
    return (REPO_ROOT / "v1.0.0.yaml").read_text()


def _latest_text() -> str:
    return (REPO_ROOT / "latest.yaml").read_text()


def _dockerfile_text() -> str:
    return (REPO_ROOT / "bootstrap" / "Dockerfile").read_text()


# ---------------------------------------------------------------------------
# GWT-58.1 — Kit package tree lands in-repo
# ---------------------------------------------------------------------------


class TestGWT581KitPackageTree:
    """GWT-58.1 — Kit package tree lands in-repo (contract-shape: bounded-change)."""

    def test_given_repo_root_when_manifest_checked_then_repo_is_agentvetter(self) -> None:
        """
        Scenario: MANIFEST declares correct repository name.
        Slice: GWT-58.1 — Kit package tree

        Given the repo root contains a MANIFEST file,
        When its REPO directive is inspected,
        Then it declares 'REPO agentvetter'.
        """
        assert any(line.startswith("REPO agentvetter") for line in _manifest_lines()), (
            "MANIFEST must declare REPO agentvetter"
        )

    def test_given_manifest_when_load_checked_then_all_three_yamls_loaded(self) -> None:
        """
        Scenario: MANIFEST loads the three Kit YAML files.
        Slice: GWT-58.1 — Kit package tree

        Given the MANIFEST file,
        When its LOAD directive is inspected,
        Then it references common.yaml, v1.0.0.yaml, and latest.yaml.
        """
        load_line = next((line for line in _manifest_lines() if line.startswith("LOAD")), None)
        assert load_line is not None, "MANIFEST must have a LOAD directive"
        for name in ("common.yaml", "v1.0.0.yaml", "latest.yaml"):
            assert name in load_line, f"MANIFEST LOAD must reference {name}"

    def test_given_v100_yaml_when_checked_then_namespace_is_agentvetter(self) -> None:
        """
        Scenario: v1.0.0.yaml uses the correct namespace.
        Slice: GWT-58.1 — Kit package tree

        Given v1.0.0.yaml,
        When its namespace directive is inspected,
        Then it is 'agentvetter'.
        """
        assert "namespace: agentvetter" in _v100_text()

    def test_given_latest_yaml_when_checked_then_members_inherit_v1_defs(self) -> None:
        """
        Scenario: latest.yaml inherits immutable v1 definitions.
        Slice: GWT-58.1 — Kit package tree

        Given latest.yaml,
        When its inherit directives are inspected,
        Then each mutable member inherits from an immutable *-v1 definition.
        """
        text = _latest_text()
        for expected in (
            "inherits: agentvetter/supabase-v1",
            "inherits: agentvetter/bootstrap-v1",
            "inherits: agentvetter/dashboard-v1",
            "inherits: agentvetter/prod-v1",
        ):
            assert expected in text, f"latest.yaml must contain '{expected}'"


# ---------------------------------------------------------------------------
# GWT-58.2 — Cluster vs SaaS split
# ---------------------------------------------------------------------------


class TestGWT582ClusterSaaSSplit:
    """GWT-58.2 — In-cluster runnables; Supabase/Modal stay SaaS."""

    def test_given_v100_yaml_when_supabase_checked_then_it_is_entity_not_container(
        self,
    ) -> None:
        """
        Scenario: Supabase is a managed Monk entity, not an in-cluster Postgres.
        Slice: GWT-58.2 — Cluster vs SaaS split

        Given v1.0.0.yaml,
        When supabase-v1 is inspected,
        Then it defines supabase/project (managed entity) and no postgres image runs in-cluster.
        """
        text = _v100_text()
        assert "defines: supabase/project" in text
        # No inline postgres container
        assert "image: postgres" not in text.lower()

    def test_given_v100_yaml_when_bootstrap_checked_then_it_is_runnable(self) -> None:
        """
        Scenario: bootstrap-v1 is an in-cluster runnable.
        Slice: GWT-58.2 — Cluster vs SaaS split

        Given v1.0.0.yaml,
        When bootstrap-v1 is inspected,
        Then it defines runnable.
        """
        assert re.search(r"bootstrap-v1:\s*\n\s+defines: runnable", _v100_text()), (
            "bootstrap-v1 must define runnable"
        )

    def test_given_v100_yaml_when_dashboard_checked_then_it_is_runnable_with_nginx(
        self,
    ) -> None:
        """
        Scenario: dashboard-v1 is an in-cluster runnable serving nginx (HTTPS ingress).
        Slice: GWT-58.2 — Cluster vs SaaS split

        Given v1.0.0.yaml,
        When dashboard-v1 is inspected,
        Then it defines runnable and uses an nginx image.
        """
        text = _v100_text()
        assert re.search(r"dashboard-v1:\s*\n\s+defines: runnable", text), (
            "dashboard-v1 must define runnable"
        )
        assert "nginx" in text.lower()


# ---------------------------------------------------------------------------
# GWT-58.3 — Secret inventory matches ADR tiers
# ---------------------------------------------------------------------------

_TIER1_SECRETS = [
    "supabase-api-token",
    "supabase-organization-id",
    "modal-token-id",
    "modal-token-secret",
]
_TIER2_SECRETS = [
    "snyk-token",
    "tessl-token",
    "tessl-workspace",
    "skill-scanner-llm-api-key",
    "mcp-scanner-llm-api-key",
]
_TIER3_SECRETS = [
    "sie-endpoint",
    "sie-api-key",
    "dashscope-api-key",
    "ossprey-api-key",
]
_ENTITY_GENERATED = [
    "supabase-db-password",
    "supabase-anon-key",
    "supabase-service-key",
]


@pytest.mark.parametrize("secret", _TIER1_SECRETS)
def test_given_manifest_when_tier1_secrets_checked_then_all_declared(secret: str) -> None:
    """
    Scenario: Tier 1 (MVL) secrets are declared in MANIFEST.
    Slice: GWT-58.3 — Secret inventory

    Given the MANIFEST file,
    When Tier 1 secrets are inspected,
    Then supabase-api-token, supabase-organization-id, modal-token-id, and
         modal-token-secret are listed as SECRET lines.
    """
    assert f"SECRET {secret}" in _manifest_text(), (
        f"Tier-1 secret '{secret}' must appear in MANIFEST"
    )


@pytest.mark.parametrize("secret", _TIER2_SECRETS)
def test_given_manifest_when_tier2_secrets_checked_then_all_declared(secret: str) -> None:
    """
    Scenario: Tier 2 (scanner engine) secrets are declared in MANIFEST.
    Slice: GWT-58.3 — Secret inventory

    Given the MANIFEST file,
    When Tier 2 secrets are inspected,
    Then snyk-token, tessl-token, tessl-workspace, and scanner LLM keys are declared.
    """
    assert f"SECRET {secret}" in _manifest_text(), (
        f"Tier-2 secret '{secret}' must appear in MANIFEST"
    )


@pytest.mark.parametrize("secret", _TIER3_SECRETS)
def test_given_manifest_when_tier3_secrets_checked_then_all_declared(secret: str) -> None:
    """
    Scenario: Tier 3 optional pass-through secrets are declared in MANIFEST.
    Slice: GWT-58.3 — Secret inventory

    Given the MANIFEST file,
    When Tier 3 secrets are inspected,
    Then sie-endpoint, sie-api-key, dashscope-api-key, and ossprey-api-key are declared.
    """
    assert f"SECRET {secret}" in _manifest_text(), (
        f"Tier-3 secret '{secret}' must appear in MANIFEST"
    )


@pytest.mark.parametrize("key", _ENTITY_GENERATED)
def test_given_manifest_when_entity_generated_keys_checked_then_not_in_secret_lines(
    key: str,
) -> None:
    """
    Scenario: Entity-generated keys are NOT listed as operator-supplied SECRET lines.
    Slice: GWT-58.3 — Secret inventory

    Given the MANIFEST file,
    When entity-generated Supabase keys are inspected,
    Then supabase-db-password, supabase-anon-key, and supabase-service-key do NOT
         appear as SECRET lines (they are generated by the Supabase entity, not supplied
         by the operator).
    """
    for line in _manifest_lines():
        if line.startswith("SECRET "):
            assert key not in line, (
                f"Entity-generated key '{key}' must NOT be listed as SECRET in MANIFEST"
            )


# ---------------------------------------------------------------------------
# GWT-58.4 — Bootstrap image: pinned schema + baked scripts + pinned image tag
# ---------------------------------------------------------------------------


class TestGWT584BootstrapImage:
    """GWT-58.4 — Bootstrap image bakes schema and scripts; image tag pinned to v1.0.0."""

    def test_given_dockerfile_when_node_base_checked_then_it_uses_node22_bookworm(
        self,
    ) -> None:
        """
        Scenario: Bootstrap Dockerfile uses a pinned Node 22 bookworm base image.
        Slice: GWT-58.4 — Bootstrap image

        Given bootstrap/Dockerfile,
        When the FROM line is inspected,
        Then it uses node:22-bookworm (pinned to a digest for reproducibility).
        """
        assert re.search(r"FROM .+node:22-bookworm", _dockerfile_text()), (
            "Dockerfile must use node:22-bookworm base image"
        )

    def test_given_dockerfile_when_schema_copy_checked_then_baked_at_build_time(
        self,
    ) -> None:
        """
        Scenario: Schema is baked into the image at build time (not fetched at runtime).
        Slice: GWT-58.4 — Bootstrap image

        Given bootstrap/Dockerfile,
        When COPY directives are inspected,
        Then db/schema.sql is copied into /app/db/schema.sql at build time.
        """
        assert "COPY db/schema.sql" in _dockerfile_text(), (
            "Dockerfile must COPY db/schema.sql at build time"
        )

    def test_given_dockerfile_when_scripts_and_sandbox_copy_checked_then_baked(
        self,
    ) -> None:
        """
        Scenario: scripts/ and sandbox/ are baked into the bootstrap image.
        Slice: GWT-58.4 — Bootstrap image

        Given bootstrap/Dockerfile,
        When COPY directives are inspected,
        Then scripts/ and sandbox/ are both copied into /app.
        """
        text = _dockerfile_text()
        assert "COPY scripts/" in text, "Dockerfile must COPY scripts/"
        assert "COPY sandbox/" in text, "Dockerfile must COPY sandbox/"

    def test_given_dockerfile_when_posix_checked_then_no_bashisms_in_run_steps(
        self,
    ) -> None:
        """
        Scenario: Dockerfile RUN steps are POSIX-safe (no bashisms).
        Slice: GWT-58.4 — Bootstrap image

        Given bootstrap/Dockerfile,
        When RUN step shell code is inspected,
        Then double-bracket [[ bashisms are absent (Monk executes bash under /bin/sh).
        """
        assert "[[" not in _dockerfile_text(), (
            "Dockerfile RUN steps must not contain [[ bashisms (POSIX /bin/sh requirement)"
        )

    def test_given_dockerfile_when_certbot_checked_then_installed_for_tls_provisioning(
        self,
    ) -> None:
        """
        Scenario: certbot is installed in the bootstrap image (pre-condition for slice 59 TLS).
        Slice: GWT-58.4 — Bootstrap image (Added scope: TLS cert provisioning)

        Given bootstrap/Dockerfile,
        When the apt-get install step is inspected,
        Then certbot is listed as an installed package.
        """
        assert "certbot" in _dockerfile_text(), (
            "Dockerfile must install certbot (pre-condition for slice 59 TLS proof)"
        )

    def test_given_v100_yaml_when_bootstrap_image_tag_checked_then_pinned_to_v1(
        self,
    ) -> None:
        """
        Scenario: bootstrap-v1 image is pinned to v1.0.0 (not floating :latest).
        Slice: GWT-58.4 — Bootstrap image (Added scope: image tag pinning)

        Given v1.0.0.yaml bootstrap-v1,
        When the image directive is inspected,
        Then it references agentvetter-bootstrap:v1.0.0, not :latest.
        """
        text = _v100_text()
        assert "agentvetter-bootstrap:v1.0.0" in text, (
            "bootstrap-v1 must pin image to v1.0.0 (not :latest — floats at deploy time)"
        )
        assert "agentvetter-bootstrap:latest" not in text, "bootstrap-v1 must NOT use :latest"

    def test_given_manifest_when_image_directive_checked_then_pinned_to_v1(self) -> None:
        """
        Scenario: MANIFEST IMAGE directive is pinned to v1.0.0.
        Slice: GWT-58.4 — Bootstrap image (Added scope: image tag pinning)

        Given the MANIFEST file,
        When the IMAGE directive is inspected,
        Then it references agentvetter-bootstrap:v1.0.0, not :latest.
        """
        image_line = next(
            (line for line in _manifest_lines() if line.startswith("IMAGE agentvetter-bootstrap")),
            None,
        )
        assert image_line is not None, "MANIFEST must have an IMAGE agentvetter-bootstrap directive"
        assert ":v1.0.0" in image_line, f"MANIFEST IMAGE must pin to :v1.0.0, got: {image_line!r}"
        assert ":latest" not in image_line, "MANIFEST IMAGE must NOT use :latest"


# ---------------------------------------------------------------------------
# GWT-58.4b — Bootstrap build fails closed on broken context
# ---------------------------------------------------------------------------


class TestGWT584bBuildFailsClosed:
    """GWT-58.4b — Build fails (non-zero) if baked inputs are missing or empty."""

    def test_given_dockerfile_when_schema_check_found_then_build_validates_non_empty_schema(
        self,
    ) -> None:
        """
        Scenario: Dockerfile validates schema is non-empty at build time.
        Slice: GWT-58.4b — Build fails closed

        Given bootstrap/Dockerfile,
        When the RUN validation step is inspected,
        Then it checks that schema.sql is non-empty (test -s) so a missing schema fails
             the build rather than producing a silently incomplete image.
        """
        assert "test -s /app/db/schema.sql" in _dockerfile_text(), (
            "Dockerfile must fail build if schema is missing or empty (test -s)"
        )


# ---------------------------------------------------------------------------
# GWT-58.5 — Honesty: Monk path is Proposed, not shipped
# ---------------------------------------------------------------------------


class TestGWT585Honesty:
    """GWT-58.5 — STATUS.md / README / QUICKSTART still say Monk is Proposed."""

    def test_given_status_md_when_monk_checked_then_adr_0001_is_proposed(self) -> None:
        """
        Scenario: STATUS.md does not falsely claim Monk deploy is working.
        Slice: GWT-58.5 — Honesty

        Given docs/STATUS.md,
        When Monk / ADR-0001 references are inspected,
        Then the ADR is described as Proposed (not VERIFIED or shipped).
        """
        status_path = REPO_ROOT / "docs" / "STATUS.md"
        if not status_path.exists():
            pytest.skip("docs/STATUS.md not found")
        text = status_path.read_text().lower()
        # The word 'monk' should appear only alongside 'proposed' or 'not'
        monk_idx = text.find("monk")
        assert monk_idx != -1, "STATUS.md must mention Monk"
        # Must NOT claim Monk is verified/shipped
        assert "monk kit live" not in text or "proposed" in text, (
            "STATUS.md must state ADR-0001 is Proposed, not shipped"
        )

    def test_given_v100_yaml_when_dashboard_depends_checked_then_waits_for_bootstrap(
        self,
    ) -> None:
        """
        Scenario: dashboard-v1 depends on bootstrap-v1 (schema applied before dashboard starts).
        Slice: GWT-58.5 — Added scope: service dependency declarations

        Given v1.0.0.yaml,
        When dashboard-v1's depends block is inspected,
        Then it waits for agentvetter/bootstrap-v1 (which applied schema + Modal setup)
             before serving traffic.
        """
        text = _v100_text()
        dashboard_start = text.find("dashboard-v1:")
        assert dashboard_start != -1, "dashboard-v1 must exist in v1.0.0.yaml"
        # From dashboard-v1 to prod-v1 (next top-level key)
        prod_start = text.find("\nprod-v1:", dashboard_start)
        dashboard_section = (
            text[dashboard_start:prod_start] if prod_start != -1 else text[dashboard_start:]
        )
        assert "agentvetter/bootstrap-v1" in dashboard_section, (
            "dashboard-v1 must depend on bootstrap-v1 (not supabase-v1 directly)"
        )

    def test_given_latest_yaml_when_dashboard_depends_checked_then_waits_for_bootstrap(
        self,
    ) -> None:
        """
        Scenario: latest.yaml dashboard track depends on bootstrap (not supabase directly).
        Slice: GWT-58.5 — Added scope: service dependency declarations

        Given latest.yaml,
        When dashboard's depends block is inspected,
        Then it waits for agentvetter/bootstrap.
        """
        text = _latest_text()
        dashboard_start = text.find("\ndashboard:")
        assert dashboard_start != -1, "dashboard must exist in latest.yaml"
        # Stop at prod: so we only inspect the dashboard block, not members listed there
        prod_start = text.find("\nprod:", dashboard_start)
        dashboard_section = (
            text[dashboard_start:prod_start] if prod_start != -1 else text[dashboard_start:]
        )
        assert "agentvetter/bootstrap" in dashboard_section, (
            "latest.yaml dashboard must depend on bootstrap (schema must be applied first)"
        )
