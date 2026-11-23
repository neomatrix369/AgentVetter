"""Modal sandbox entrypoint. Deploy with: modal deploy sandbox/scan_app.py

Each scan_run gets its own ephemeral sandbox. Disk here is scratch only —
findings/logs are written directly to Supabase, never relayed through the CLI.

Local directory targets are packed on the host by ``main`` (local_entrypoint)
and shipped as a gzipped tar to ``scan_item`` — host paths are not visible on
Modal's remote filesystem (see Modal guide: pass local data as function args).
"""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import modal

# Sibling modules live in sandbox/; ensure they are importable when this file is
# loaded from repo root (modal deploy/run sandbox/scan_app.py).
_SANDBOX_DIR = Path(__file__).resolve().parent
if str(_SANDBOX_DIR) not in sys.path:
    sys.path.insert(0, str(_SANDBOX_DIR))

from scanners import TESSL_SOURCES, run_all_scanners  # noqa: E402

app = modal.App("agentvetter-scan")

# Bake scanners.py into the image (copy=True). Mount-only defaults leave remote
# workers without the sibling module → ModuleNotFoundError: scanners.
#
# Node 20+ from official tarball (Debian apt nodejs is still 18; Tessl needs ≥20).
# Preinstall snyk-agent-scan via uv tool so cold `uvx …@latest` is not the path.
_NODE_VERSION = "20.18.1"
# Ossprey CLI (Go) — malicious-package / malware detection. RESEARCH: the exact
# release tag needs confirming when Ossprey access provisioning lands (ADR-0005);
# this is a best-effort placeholder, NOT a verified tag. The install line is
# guarded with `|| true`, so a 404 leaves the binary absent and run_ossprey
# reports `unreachable` — the acceptable degraded path while provisioning is OPEN
# (slice 35 BLOCKED). Provisioning also gates the credential, so today the
# adapter short-circuits to skipped_missing_credential before the binary matters.
_OSSPREY_VERSION = "v0.12.0"  # verified OSSPREY/ossprey-cli release (linux-amd64 asset)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git", "curl", "ca-certificates", "xz-utils")
    .run_commands(
        f"curl -fsSL https://nodejs.org/dist/v{_NODE_VERSION}/node-v{_NODE_VERSION}-linux-x64.tar.xz "
        f"| tar -xJ -C /usr/local --strip-components=1",
        "curl -LsSf https://astral.sh/uv/install.sh | sh",
        "ln -sf /root/.local/bin/uv /usr/local/bin/uv",
        "ln -sf /root/.local/bin/uvx /usr/local/bin/uvx",
        "uv tool install snyk-agent-scan",
        "ln -sf /root/.local/bin/snyk-agent-scan /usr/local/bin/snyk-agent-scan",
        # Snyk SCA CLI for package targets (`snyk test`). Agent Scan does not audit manifests.
        "npm install -g snyk",
        "ln -sf /usr/local/lib/node_modules/snyk/bin/snyk /usr/local/bin/snyk || true",
        # DepShield stdio MCP server (npm/PyPI dependency audit) — pinned so cold `npx` is not the path.
        "npm install -g depshield-mcp@1.0.0",
        # RustSec cargo-audit — Cargo.lock / Cargo.toml SCA (prefer over LLM for Rust).
        # Modal caches this layer; on install failure the adapter reports unreachable.
        "curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | "
        "sh -s -- -y --profile minimal --default-toolchain stable && "
        ". /root/.cargo/env && cargo install cargo-audit --locked && "
        "ln -sf /root/.cargo/bin/cargo-audit /usr/local/bin/cargo-audit && "
        "test -x /usr/local/bin/cargo-audit "
        '|| echo "WARNING: cargo-audit install failed — run_cargo_audit will report unreachable" >&2',
        # Ossprey CLI (linux amd64 release binary; sudo-less). Warn loudly when the
        # pinned release asset is missing so operators do not confuse unreachable
        # with a clean malware scan once credentials land.
        f"(curl -fsSL https://github.com/OSSPREY/ossprey-cli/releases/download/{_OSSPREY_VERSION}/ossprey-linux-amd64 "
        "-o /usr/local/bin/ossprey && chmod +x /usr/local/bin/ossprey && test -x /usr/local/bin/ossprey) "
        f'|| echo "WARNING: Ossprey {_OSSPREY_VERSION} binary missing — run_ossprey will report unreachable" >&2',
        "node --version && test -x /usr/local/bin/snyk-agent-scan && command -v snyk",
    )
    .pip_install(
        "supabase",
        "cisco-ai-skill-scanner",
        "cisco-ai-mcp-scanner",
    )
    .add_local_python_source("scanners", copy=True)
)

TIMEOUT_SECONDS = (
    300  # hard sandbox-level timeout (spec Phase 1): kill whole sandbox, mark scan_run failed
)

_PGRST_COLUMN_RE = re.compile(
    r"PGRST204|could not find the .* column .* in the schema cache", re.IGNORECASE
)

_LEGACY_SCANNER_KEYS = frozenset({"scan_run_id", "scanner_source", "status", "checks_run"})

# Tessl rows are inserted/updated step-by-step via on_scanner_progress — not bulk
# "running" placeholders (which made all five look frozen for the whole group).
_TESSL_SOURCE_SET = frozenset(TESSL_SOURCES)


def _is_column_error(exc: Exception) -> bool:
    return bool(_PGRST_COLUMN_RE.search(str(exc)))


def _to_runtime_error(exc: Exception, context: str) -> RuntimeError:
    """Convert any Supabase/PostgREST exception to a plain RuntimeError.

    Modal's local client may not have ``postgrest`` installed; deserializing a
    ``postgrest.exceptions.APIError`` then fails with a confusing
    ``ExecutionError``.  Plain ``RuntimeError`` always deserializes cleanly.
    """
    return RuntimeError(f"{context}: {exc}")


def _safe_insert(supabase, table: str, row: dict, context: str) -> None:
    """Insert *row* into *table*, falling back to legacy-safe columns on PGRST204.

    If the first attempt fails because PostgREST can't find a column (the DB
    hasn't had ``db/schema.sql`` migration applied), retry with only the
    columns that existed in every schema version.  ``detail`` data is folded
    into the ``detail`` field (truncated) so scan context survives the fallback.
    """
    try:
        supabase.table(table).insert(row).execute()
    except Exception as exc:
        if not _is_column_error(exc):
            raise _to_runtime_error(exc, context) from exc
        print(
            f"[agentvetter] WARN column-missing ({exc}); retrying {table} "
            f"insert with legacy columns — apply db/schema.sql to fix"
        )
        fallback = {k: v for k, v in row.items() if k in _LEGACY_SCANNER_KEYS}
        console = row.get("console_output", "")
        detail = row.get("detail", "")
        merged = f"{detail}\n---\n{console}".strip(" \n-") if console else detail
        if merged:
            fallback["detail"] = merged[:4000]
        try:
            supabase.table(table).insert(fallback).execute()
        except Exception as inner:
            raise _to_runtime_error(
                inner,
                f"Supabase {table} insert failed even with legacy columns. "
                "Apply db/schema.sql migration (agentvetter setup --force)",
            ) from inner


def _safe_update(supabase, table: str, data: dict, eq_col: str, eq_val: str, context: str) -> None:
    """Wrap a Supabase update, converting PostgREST errors to RuntimeError."""
    try:
        supabase.table(table).update(data).eq(eq_col, eq_val).execute()
    except Exception as exc:
        raise _to_runtime_error(exc, context) from exc


def _safe_rpc(supabase, fn: str, params: dict, context: str) -> None:
    try:
        supabase.rpc(fn, params).execute()
    except Exception as exc:
        raise _to_runtime_error(exc, context) from exc


@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("agentvetter-supabase"),
        modal.Secret.from_name("agentvetter-scan-secrets"),
    ],
    timeout=TIMEOUT_SECONDS,
)
def scan_item(
    target: str,
    item_type: str,
    scan_run_id: str,
    item_id: str,
    target_archive: bytes | None = None,
):
    import os

    from supabase import create_client

    supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

    try:
        _scan_item_inner(supabase, target, item_type, scan_run_id, item_id, target_archive)
    except RuntimeError:
        raise
    except Exception as exc:
        raise _to_runtime_error(exc, "scan_item unexpected error") from exc

    # scratch disk teardown is implicit — the Modal sandbox itself is ephemeral and discarded here.


def _scan_item_inner(
    supabase,
    target: str,
    item_type: str,
    scan_run_id: str,
    item_id: str,
    target_archive: bytes | None,
) -> None:
    def _mark_failed() -> None:
        _safe_update(
            supabase,
            "scan_runs",
            {"status": "failed", "completed_at": datetime.now(UTC).isoformat()},
            "id",
            scan_run_id,
            "mark scan_run failed",
        )
        _safe_rpc(
            supabase, "agentvetter_rollup_item", {"p_item_id": item_id}, "rollup after failure"
        )

    workdir = "/tmp/scan-target"
    try:
        _acquire_target(target, item_type, workdir, target_archive=target_archive)
    except Exception:
        _mark_failed()
        raise

    def _on_scanner_start(sources):
        """Insert running placeholder rows so the dashboard shows progress."""
        now = datetime.now(UTC).isoformat()
        for source in sources:
            if source in _TESSL_SOURCE_SET:
                continue
            try:
                supabase.table("scan_run_scanners").insert(
                    {
                        "scan_run_id": scan_run_id,
                        "scanner_source": source,
                        "status": "running",
                        "started_at": now,
                    }
                ).execute()
            except Exception as exc:
                print(f"[scan] warning: could not insert running row for {source}: {exc}")

    def _persist_scanner_row(row: dict, *, completed: bool = False) -> None:
        """Upsert one scan_run_scanners row (supports mid-group Tessl progress)."""
        now = datetime.now(UTC).isoformat()
        payload = {**row, "scan_run_id": scan_run_id}
        if completed:
            payload["completed_at"] = now
        try:
            resp = (
                supabase.table("scan_run_scanners")
                .update(payload)
                .eq("scan_run_id", scan_run_id)
                .eq("scanner_source", row["scanner_source"])
                .execute()
            )
            if not resp.data:
                _safe_insert(
                    supabase,
                    "scan_run_scanners",
                    payload,
                    "scan_run_scanners insert",
                )
        except Exception:
            try:
                _safe_insert(
                    supabase,
                    "scan_run_scanners",
                    payload,
                    "scan_run_scanners insert (update-fallback)",
                )
            except Exception as exc:
                print(
                    f"[scan] warning: scanner row write failed for {row.get('scanner_source')}: {exc}"
                )

    def _on_scanner_done(findings, scanner_rows, quality_score=None):
        """Write results — update existing running row or insert fresh."""
        for row in scanner_rows:
            _persist_scanner_row(row, completed=True)
        for finding in findings:
            _safe_insert(
                supabase,
                "findings",
                {**finding, "scan_run_id": scan_run_id, "item_id": item_id},
                "findings insert",
            )
        if quality_score is not None:
            _safe_update(
                supabase,
                "items",
                {"quality_score": quality_score},
                "id",
                item_id,
                "update quality_score",
            )

    def _on_scanner_progress(row: dict) -> None:
        """Persist Tessl mid-group rows (scenario checkpoint, Eval blocked→running)."""
        _persist_scanner_row(row, completed=False)

    tessl_scenario_resume = None
    tessl_prior_eval = None
    try:
        resume_resp = (
            supabase.table("scan_run_scanners")
            .select("resume_checkpoint")
            .eq("scan_run_id", scan_run_id)
            .eq("scanner_source", "Tessl: Scenario Generation")
            .limit(1)
            .execute()
        )
        if resume_resp.data:
            tessl_scenario_resume = resume_resp.data[0].get("resume_checkpoint")
    except Exception as exc:
        print(f"[scan] warning: could not load Tessl scenario resume_checkpoint: {exc}")

    try:
        eval_resp = (
            supabase.table("scan_run_scanners")
            .select(
                "status,tessl_run_id,tessl_run_id_at,completed_at,"
                "upstream_run_ids,detail,checks_run"
            )
            .eq("scan_run_id", scan_run_id)
            .eq("scanner_source", "Tessl: Eval")
            .limit(1)
            .execute()
        )
        if eval_resp.data:
            tessl_prior_eval = eval_resp.data[0]
    except Exception as exc:
        print(f"[scan] warning: could not load Tessl Eval prior row: {exc}")

    try:
        results = run_all_scanners(
            workdir=workdir,
            item_type=item_type,
            target=target,
            on_scanner_done=_on_scanner_done,
            on_scanner_start=_on_scanner_start,
            on_scanner_progress=_on_scanner_progress,
            tessl_scenario_resume=tessl_scenario_resume,
            tessl_prior_eval=tessl_prior_eval,
        )
    except Exception:
        _mark_failed()
        raise

    _safe_update(
        supabase,
        "scan_runs",
        {"status": results["overall_status"], "completed_at": datetime.now(UTC).isoformat()},
        "id",
        scan_run_id,
        "mark scan_run completed",
    )
    _safe_rpc(supabase, "agentvetter_rollup_item", {"p_item_id": item_id}, "rollup after scan")


@app.local_entrypoint()
def main(
    target: str,
    item_type: str,
    item_id: str,
    scan_run_id: str,
    pack_path: str = "",
):
    """Host-side wrapper: pack local dirs, then invoke the remote sandbox.

    Invoked by the CLI via ``modal run sandbox/scan_app.py`` (not ``::scan_item``)
    so this code runs where the fixture filesystem is visible.

    ``pack_path`` is optional: for manifest MCP keys, ``target`` is the config
    key (item identity) while ``pack_path`` is the host directory to tar.
    """
    pack_root = pack_path or target
    archive = _maybe_pack_local_target(pack_root)
    if archive is not None:
        print(f"[acquire] packed local target ({len(archive)} bytes) → remote sandbox")
    scan_item.remote(
        target=target,
        item_type=item_type,
        scan_run_id=scan_run_id,
        item_id=item_id,
        target_archive=archive,
    )


_CLONE_TIMEOUT = int(os.environ.get("AGENTVETTER_CLONE_TIMEOUT") or 120)


def _is_git_url(target: str) -> bool:
    """True when *target* looks like a clonable git repository URL.

    Unambiguous schemes (git://, git@, ssh://) and a trailing .git are always git.
    http(s) is git only for known forges (GitHub, GitLab, Bitbucket, Codeberg).
    Other http(s) URLs are live MCP endpoints (SSE or streamable HTTP) and must
    not be cloned.
    """
    if target.startswith(("git://", "git@", "ssh://")):
        return True
    if target.rstrip("/").endswith(".git"):
        return True
    return _is_git_forge_url(target)


def _is_git_forge_url(target: str) -> bool:
    """True when an http(s) URL's host is a git forge AgentVetter clones."""
    parsed = urlsplit(target)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    if host == "github.com" or host.endswith(".github.com"):
        return True
    if "gitlab" in host:
        return True
    return host in {"bitbucket.org", "codeberg.org"}


def _normalize_github_clone_url(target: str) -> str:
    """Remove GitHub tree/blob browse paths while preserving other targets."""
    parsed = urlsplit(target)
    if parsed.scheme not in {"http", "https"} or parsed.netloc != "github.com":
        return target
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or (len(parts) > 2 and parts[2] not in {"tree", "blob"}):
        return target.rstrip("/")
    return f"{parsed.scheme}://github.com/{parts[0]}/{parts[1]}"


def _looks_like_filesystem_path(target: str) -> bool:
    """True for host paths that should have been uploaded or copied, not protocol URLs."""
    if "://" in target or target.startswith("git@"):
        return False
    return True


def _maybe_pack_local_target(target: str) -> bytes | None:
    """On the host: tar a local directory so the remote sandbox can extract it.

    Returns None for git URLs, protocol targets, and missing paths (remote
    acquire will either clone, introspect, or raise).
    """
    if _is_git_url(target):
        return None
    if not os.path.isdir(target):
        return None
    return _pack_local_dir(target)


def _is_tessl_plugin_root(src: str) -> bool:
    """True when the directory is a Tessl plugin (omit host evals/ on upload)."""
    root = Path(src)
    return (root / "tessl.json").is_file() or (root / ".tessl-plugin").exists()


def _is_root_evals_tar_member(name: str) -> bool:
    rel = name.lstrip("./")
    return rel == "evals" or rel.startswith("evals/")


def _pack_local_dir(src: str) -> bytes:
    skip_evals = _is_tessl_plugin_root(src)

    def _filter(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo | None:
        if skip_evals and _is_root_evals_tar_member(tarinfo.name):
            return None
        return tarinfo

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        tar.add(src, arcname=".", filter=_filter)
    return buf.getvalue()


def _extract_archive(archive: bytes, workdir: str) -> None:
    buf = io.BytesIO(archive)
    with tarfile.open(fileobj=buf, mode="r:gz") as tar:
        # filter="data" blocks path traversal (PEP 706); rule misses the kwarg.
        tar.extractall(
            workdir, filter="data"
        )  # nosemgrep: trailofbits.python.tarfile-extractall-traversal.tarfile-extractall-traversal


def _acquire_target(
    target: str,
    item_type: str,
    workdir: str,
    target_archive: bytes | None = None,
):
    """Dispatch on target shape to populate *workdir* with scannable content.

    • Git URL  → shallow clone (depth=1, single-branch).
    • Uploaded archive (bytes from local_entrypoint) → extract into workdir.
    • Local path (directory on disk — same machine only) → recursive copy.
    • Filesystem-looking path with no archive and not on disk → raise
      (prevents silent empty workdir when CLI forgot to pack).
    • Anything else (MCP server URL, stdio transport, etc.) → introspection-only:
      create an empty workdir and let scanners use *target* directly via protocol.

    Raises on clone / copy / missing-upload failure so scan_item marks the run as failed.
    """
    os.makedirs(workdir, exist_ok=True)

    if _is_git_url(target):
        _clone_repo(_normalize_github_clone_url(target), workdir)
        return

    if target_archive is not None:
        _extract_archive(target_archive, workdir)
        return

    if os.path.isdir(target):
        _copy_local(target, workdir)
        return

    if _looks_like_filesystem_path(target):
        raise RuntimeError(
            f"local target not available in sandbox and no archive uploaded: {target}"
        )

    # Introspection-only: empty workdir is intentional — scanners that need
    # source on disk will report not_applicable; protocol scanners use `target`.


def _clone_repo(url: str, workdir: str):
    result = subprocess.run(
        # "--" stops a target that starts with "-" being parsed as a git option.
        ["git", "clone", "--depth", "1", "--single-branch", "--", url, workdir],
        capture_output=True,
        text=True,
        timeout=_CLONE_TIMEOUT,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git clone failed (exit {result.returncode}): {result.stderr[:500]}")


def _copy_local(src: str, workdir: str):
    def _ignore(directory: str, contents: list[str]) -> list[str]:
        if not _is_tessl_plugin_root(src):
            return []
        if Path(directory).resolve() == Path(src).resolve() and "evals" in contents:
            return ["evals"]
        return []

    shutil.copytree(src, workdir, dirs_exist_ok=True, ignore=_ignore)
