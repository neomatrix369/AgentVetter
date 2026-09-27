"""Scanner adapters — real subprocess invocations of the upstream CLIs.

Evidence labels (matching docs/research/adapters/scanner-output-adapters.md convention):
RESEARCH = shape taken from primary docs, not yet round-tripped through Supabase on a
real fixture. Everything below is RESEARCH — reconcile against the pinned CLI version's
--help / --json output before this blocks a merge.

mcp-scanner CLI (cisco-ai-mcp-scanner ≥4.x, VERIFIED against upstream README 2026-08-01):
global flags (--format / --analyzers / --log-level) MUST precede a mode subcommand
(remote | stdio | behavioral | …). A bare path/URL as a positional between flags makes
argparse print usage and exit nonzero — Tripwire maps that stderr to status=unreachable.
"""

import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

SCAN_TIMEOUT = 240  # leaves headroom under the sandbox's 300s hard timeout
MAX_CONSOLE_CHARS = 3000  # per-scanner console capture limit for Supabase detail

# Severity collapse (docs/research/adapters/scanner-output-adapters.md §1, PROPOSED)
_SNYK_CODE_CATEGORY = {
    "E004": "prompt_injection",
    "W008": "hardcoded_secrets",
    # Open: full E*/W* -> Tripwire category table (adapters doc §2 "Open")
}


def _which(binary):
    return shutil.which(binary) is not None


def _run(cmd, timeout=SCAN_TIMEOUT, cwd=None):
    """Never raises on nonzero exit or timeout — callers map that to a
    scan_run_scanners status (unreachable) rather than a crash."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        return None, exc.stdout or "", f"timeout after {timeout}s"
    except FileNotFoundError:
        return None, "", f"binary not found: {cmd[0]}"


def _skipped(source, reason="skipped_missing_credential", detail=None, console_output=None):
    row = {"scanner_source": source, "status": reason, "checks_run": 0}
    if detail:
        row["detail"] = str(detail).strip()[:4000]
    if console_output:
        row["console_output"] = console_output
    return row


def _snyk_collect_errors(path_result):
    """Gather path-level and per-component errors from a Snyk path envelope.

    Supports v0.5 (`servers`) and v0.6 (`server_risks` / `skill_risks`).
    """
    errors = []
    path_err = path_result.get("error")
    if path_err:
        errors.append(path_err)
    for server in path_result.get("servers") or []:
        if isinstance(server, dict) and server.get("error"):
            errors.append(server["error"])
    for component in (path_result.get("server_risks") or []) + (
        path_result.get("skill_risks") or []
    ):
        if isinstance(component, dict) and component.get("error"):
            errors.append(component["error"])
    return errors


def _snyk_iter_path_results(root):
    """Yield path-result dicts from v0.5 path-keyed maps or v0.6 envelopes."""
    responses = root.get("scan_path_responses")
    if isinstance(responses, list):
        for item in responses:
            if isinstance(item, dict):
                yield item
        return
    for _abs_path, path_result in root.items():
        if isinstance(path_result, dict):
            yield path_result


def _snyk_severity_from_score(score):
    """Map Agent Scan v0.6 risk score (0–1000) to Tripwire red/amber."""
    try:
        numeric = int(score)
    except (TypeError, ValueError):
        return "amber"
    return "red" if numeric >= 600 else "amber"


def _snyk_findings_from_path(path_result, source):
    """Extract findings + check count from one path result (v0.5 issues or v0.6 risks)."""
    findings = []
    checks = 0
    for issue in path_result.get("issues") or []:
        if not isinstance(issue, dict):
            continue
        checks += 1
        code_ = issue.get("code", "")
        severity = "red" if code_.startswith("E") else ("amber" if code_.startswith("W") else None)
        if severity is None:
            continue
        findings.append(
            {
                "severity": severity,
                "category": _SNYK_CODE_CATEGORY.get(code_, "unknown"),
                "message": issue.get("message"),
                "scanner_source": source,
            }
        )
    for component in (path_result.get("server_risks") or []) + (
        path_result.get("skill_risks") or []
    ):
        if not isinstance(component, dict):
            continue
        risk_indexes = component.get("risk_indexes") or {}
        if not isinstance(risk_indexes, dict):
            continue
        for risk_name, risk in risk_indexes.items():
            if not isinstance(risk, dict):
                continue
            checks += 1
            findings.append(
                {
                    "severity": _snyk_severity_from_score(risk.get("score")),
                    "category": str(risk_name),
                    "message": risk.get("evidence") or str(risk_name),
                    "scanner_source": source,
                }
            )
    return findings, checks


def _snyk_error_is_auth(err):
    """True when Snyk rejected credentials (401 / Unauthorized / SNYK_TOKEN hint)."""
    if isinstance(err, dict):
        msg = str(err.get("message") or "")
        exc = str(err.get("exception") or "")
        return "Unauthorized" in msg or "Unauthorized" in exc or "401" in exc
    text = str(err)
    return "Unauthorized" in text and ("401" in text or "SNYK_TOKEN" in text)


def _snyk_error_message(err):
    if isinstance(err, dict) and err.get("message"):
        return str(err["message"])
    return str(err)


def _unreachable(source, stderr, console_output=None):
    detail = (stderr or "").strip()
    print(f"[{source}] unreachable: {detail[:400]}")
    row = {"scanner_source": source, "status": "unreachable", "checks_run": 0}
    if detail:
        row["detail"] = detail[:4000]
    if console_output:
        row["console_output"] = console_output
    return row


def _safe_json(text):
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    # CLIs sometimes prefix progress/npm notices before the JSON object.
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def _truncate_console(text, max_chars=MAX_CONSOLE_CHARS):
    """Truncate raw console text, preserving head and tail for context."""
    if not text or len(text) <= max_chars:
        return text or None
    half = max_chars // 2 - 30
    omitted = len(text) - 2 * half
    return f"{text[:half]}\n…[{omitted} chars omitted]…\n{text[-half:]}"


def _build_console(stdout, stderr):
    """Build a truncated console capture from scanner subprocess output."""
    parts = []
    if stdout and stdout.strip():
        parts.append(stdout.strip())
    if stderr and stderr.strip():
        prefix = "--- stderr ---\n" if parts else ""
        parts.append(f"{prefix}{stderr.strip()}")
    return _truncate_console("\n".join(parts)) if parts else None


# ---- Cisco Skill Scanner ----------------------------------------------------
# docs/research/adapters/scanner-output-adapters.md §3
# Capture: skill-scanner scan <path> --format json  (avoid --output: flaky on a tested build)


def _completed(source, checks_run, findings_for_scanner, console_output=None):
    """Build a completed scanner row with a human-readable detail summary."""
    n_findings = len(findings_for_scanner)
    if n_findings == 0:
        detail = f"{checks_run} checks passed — no findings"
    else:
        severities = [f.get("severity", "unknown") for f in findings_for_scanner]
        worst = (
            "red" if "red" in severities else ("amber" if "amber" in severities else severities[0])
        )
        brief = findings_for_scanner[0].get("message", "flagged")
        if len(brief) > 80:
            brief = brief[:77] + "…"
        detail = f"{checks_run} checks — {n_findings} finding{'s' if n_findings != 1 else ''} ({worst}): {brief}"
    row = {
        "scanner_source": source,
        "status": "completed",
        "checks_run": checks_run,
        "detail": detail,
    }
    if console_output:
        row["console_output"] = console_output
    return row


def run_cisco_skill_scanner(workdir):
    source_static = "Cisco Skill Scanner: static/bytecode/pipeline"
    if not _which("skill-scanner"):
        return [], [_unreachable(source_static, "skill-scanner not installed in image")]

    rows, findings = [], []

    def _invoke(extra_flags, source):
        code, out, err = _run(["skill-scanner", "scan", workdir, "--format", "json", *extra_flags])
        console = _build_console(out, err)
        if code != 0:
            return [_unreachable(source, err, console_output=console)], []
        parsed = _safe_json(out)
        if not isinstance(parsed, dict) or not parsed:
            return [
                _unreachable(
                    source, "scanner returned no parseable JSON results", console_output=console
                )
            ], []
        mapped = _map_skill_findings(parsed, source)
        checks = parsed.get("findings_count", len(parsed.get("findings", [])) or 1)
        return [_completed(source, checks, mapped, console_output=console)], mapped

    r, f = _invoke([], source_static)
    rows += r
    findings += f

    if os.environ.get("SKILL_SCANNER_LLM_API_KEY"):
        r, f = _invoke(["--use-llm"], "Cisco Skill Scanner: LLM-judge")
        rows += r
        findings += f
    else:
        rows.append(_skipped("Cisco Skill Scanner: LLM-judge"))

    if os.environ.get("AI_DEFENSE_API_KEY"):
        r, f = _invoke(["--use-aidefense"], "Cisco Skill Scanner: AI Defense")
        rows += r
        findings += f
    else:
        rows.append(_skipped("Cisco Skill Scanner: AI Defense"))

    return findings, rows


def _map_skill_findings(parsed, source):
    out = []
    for f in parsed.get("findings", []) or []:
        out.append(
            {
                "severity": _collapse_severity(f.get("severity")),
                "category": f.get("category", "unknown"),
                "file_path": f.get("file_path"),
                "location": str(f.get("line_number")) if f.get("line_number") is not None else None,
                "message": (f.get("title", "") + " — " + f.get("description", "")).strip(" —"),
                "snippet": f.get("snippet"),
                "scanner_source": source,
            }
        )
    return out


# ---- Cisco MCP Scanner ------------------------------------------------------
# docs/research/adapters/scanner-output-adapters.md §4
# Live engines:  mcp-scanner --format raw --analyzers yara[,llm][,api] <mode> …
#   remote → remote --server-url <url>
#   local  → stdio --stdio-command … --stdio-arg …
# Source tier: mcp-scanner --format raw behavioral <workdir>  (needs LLM key)

_MCP_ANALYZER_LABEL = {
    "yara_analyzer": "Cisco MCP Scanner: YARA",
    "llm_analyzer": "Cisco MCP Scanner: LLM-judge",
    "api_analyzer": "Cisco MCP Scanner: AI Defense",
    "behavioral_analyzer": "Cisco MCP Scanner: Behavioral Code Scanning",
}

_MCP_LIVE_KEYS = ("yara_analyzer", "llm_analyzer", "api_analyzer")


def _has_workdir_source(workdir):
    return os.path.isdir(workdir) and any(os.scandir(workdir))


def _mcp_live_analyzers():
    analyzers = ["yara"]
    if os.environ.get("MCP_SCANNER_LLM_API_KEY"):
        analyzers.append("llm")
    if os.environ.get("MCP_SCANNER_API_KEY") and os.environ.get("MCP_SCANNER_ENDPOINT"):
        analyzers.append("api")
    return analyzers


def _mcp_stdio_mode_args(workdir):
    """Return stdio subcommand argv for a local MCP server tree, or None."""
    run_sh = os.path.join(workdir, "run.sh")
    if os.path.isfile(run_sh):
        return ["stdio", "--stdio-command", "bash", "--stdio-arg", run_sh]
    for name, cmd in (
        ("server.py", "python"),
        ("main.py", "python"),
        ("server.js", "node"),
        ("index.js", "node"),
    ):
        path = os.path.join(workdir, name)
        if os.path.isfile(path):
            return ["stdio", "--stdio-command", cmd, "--stdio-arg", path]
    return None


def _mcp_mode_args(workdir, target):
    """Pick remote vs stdio mode. Prefer stdio when the sandbox has source on disk."""
    has_source = _has_workdir_source(workdir)
    if isinstance(target, str) and target.startswith(("http://", "https://")) and not has_source:
        return ["remote", "--server-url", target]
    return _mcp_stdio_mode_args(workdir)


def build_mcp_live_cmd(analyzers, mode_args):
    """Global flags before mode — required by mcp-scanner argparse."""
    return [
        "mcp-scanner",
        "--log-level",
        "error",
        "--format",
        "raw",
        "--analyzers",
        ",".join(analyzers),
        *mode_args,
    ]


def build_mcp_behavioral_cmd(workdir):
    return [
        "mcp-scanner",
        "--log-level",
        "error",
        "--format",
        "raw",
        "behavioral",
        workdir,
    ]


def _normalize_analyzer_key(name):
    if not name:
        return name
    return name if name.endswith("_analyzer") else f"{name}_analyzer"


def _taxonomy_category(entry):
    tax = entry.get("mcp_taxonomies") or []
    if not tax:
        return "unknown"
    first = tax[0]
    if isinstance(first, dict):
        return first.get("scanner_category") or "unknown"
    if isinstance(first, str):
        return first
    return "unknown"


def _map_mcp_envelope(envelope, analyzers_fallback):
    findings, checks = [], {}
    for result in envelope.get("scan_results", []) or []:
        entity_kind = result.get("item_type")
        entity_name = (
            result.get("tool_name") or result.get("prompt_name") or result.get("resource_uri")
        )
        for analyzer_key, entry in (result.get("findings") or {}).items():
            if not isinstance(entry, dict):
                continue
            key = _normalize_analyzer_key(analyzer_key)
            checks[key] = checks.get(key, 0) + 1
            severity = _collapse_severity(entry.get("severity"))
            if severity is None:  # SAFE — no finding row
                continue
            findings.append(
                {
                    "severity": severity,
                    "category": _taxonomy_category(entry),
                    "entity_kind": entity_kind,
                    "entity_name": entity_name,
                    "message": entry.get("threat_summary")
                    or ", ".join(entry.get("threat_names", []))
                    or "flagged",
                    "scanner_source": _MCP_ANALYZER_LABEL.get(key, key),
                }
            )

    raw_requested = envelope.get("requested_analyzers") or analyzers_fallback
    requested = [_normalize_analyzer_key(a) for a in raw_requested]
    rows = []
    for key in requested:
        if key not in _MCP_ANALYZER_LABEL:
            continue
        source = _MCP_ANALYZER_LABEL[key]
        scanner_findings = [f for f in findings if f.get("scanner_source") == source]
        rows.append(_completed(source, checks.get(key, 1), scanner_findings))
    return findings, rows, requested


def run_cisco_mcp_scanner(workdir, target):
    if not _which("mcp-scanner"):
        return [], [
            _unreachable(
                _MCP_ANALYZER_LABEL["yara_analyzer"],
                "mcp-scanner not installed in image",
            )
        ]

    findings, rows = [], []
    live = _mcp_live_analyzers()
    has_source = _has_workdir_source(workdir)
    mode_args = _mcp_mode_args(workdir, target)

    if mode_args is None:
        detail = (
            "no mcp-scanner mode: need remote --server-url or stdio launch "
            "(run.sh / server.py / main.py / server.js / index.js in workdir)"
        )
        for name in live:
            rows.append(_unreachable(_MCP_ANALYZER_LABEL[_normalize_analyzer_key(name)], detail))
    else:
        code, out, err = _run(build_mcp_live_cmd(live, mode_args))
        console = _build_console(out, err)
        if code != 0:
            for name in live:
                rows.append(
                    _unreachable(
                        _MCP_ANALYZER_LABEL[_normalize_analyzer_key(name)],
                        err,
                        console_output=console,
                    )
                )
        else:
            envelope = _safe_json(out)
            if not isinstance(envelope, dict) or not isinstance(envelope.get("scan_results"), list):
                for name in live:
                    rows.append(
                        _unreachable(
                            _MCP_ANALYZER_LABEL[_normalize_analyzer_key(name)],
                            "scanner returned no parseable scan_results",
                            console_output=console,
                        )
                    )
            else:
                f, r, _requested = _map_mcp_envelope(envelope, live)
                for row in r:
                    row["console_output"] = console
                findings += f
                rows += r

    reported = {row["scanner_source"] for row in rows}
    for key in _MCP_LIVE_KEYS:
        label = _MCP_ANALYZER_LABEL[key]
        if label not in reported:
            rows.append(_skipped(label))

    beh_label = _MCP_ANALYZER_LABEL["behavioral_analyzer"]
    if not has_source:
        rows.append(_skipped(beh_label, "not_applicable"))
    elif not os.environ.get("MCP_SCANNER_LLM_API_KEY"):
        rows.append(_skipped(beh_label))
    else:
        code, out, err = _run(build_mcp_behavioral_cmd(workdir))
        beh_console = _build_console(out, err)
        if code != 0:
            rows.append(_unreachable(beh_label, err, console_output=beh_console))
        else:
            envelope = _safe_json(out)
            if not isinstance(envelope, dict) or not isinstance(envelope.get("scan_results"), list):
                rows.append(
                    _unreachable(
                        beh_label,
                        "scanner returned no parseable scan_results",
                        console_output=beh_console,
                    )
                )
            else:
                if not envelope.get("requested_analyzers"):
                    envelope = {**envelope, "requested_analyzers": ["behavioral"]}
                f, r, _ = _map_mcp_envelope(envelope, ["behavioral"])
                findings += f
                beh_rows = [row for row in r if row["scanner_source"] == beh_label]
                for row in beh_rows:
                    row["console_output"] = beh_console
                rows += beh_rows or [_completed(beh_label, 1, [], console_output=beh_console)]

    return findings, rows


# ---- Snyk Agent Scan ---------------------------------------------------------
# docs/research/adapters/scanner-output-adapters.md §2
# Prefer image-preinstalled `snyk-agent-scan` (uv tool install); fall back to uvx.
# JSON: Agent Scan v0.6+ uses scan_path_responses / risk_indexes; v0.5 path-keyed
# issues[] remains supported (see docs/research/adapters/scanner-output-adapters.md §2).
# Package targets use `snyk test` SCA — Agent Scan does not audit manifests.

_SNYK_SCA_NO_SUPPORTED_PROJECTS = 3

# Manifests `snyk test` can audit. Rust/Cargo is intentionally absent — Snyk Open
# Source documents Rust as SBOM/API-only (not `snyk test` / `snyk monitor`).
_SNYK_SCA_SUPPORTED_MARKERS = frozenset(
    {
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "requirements.txt",
        "Pipfile",
        "Pipfile.lock",
        "poetry.lock",
        "pyproject.toml",
        "go.mod",
        "go.sum",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "build.sbt",
        "Gemfile",
        "Gemfile.lock",
        "composer.json",
        "composer.lock",
        "Package.swift",
        "Package.resolved",
    }
)
_SNYK_SCA_UNSUPPORTED_LABELS = (
    ("Cargo.toml", "Rust/Cargo"),
    ("Cargo.lock", "Rust/Cargo"),
)


def _snyk_detect_sca_ecosystems(workdir):
    """Return ``(supported_names, unsupported_labels)`` under *workdir* for SCA."""
    skip_dirs = frozenset({"node_modules", ".git", "venv", ".venv", "__pycache__"})
    supported = set()
    unsupported = set()
    if not workdir or not os.path.isdir(workdir):
        return (), ()
    for _root, dirnames, filenames in os.walk(workdir):
        dirnames[:] = sorted(d for d in dirnames if d not in skip_dirs)
        for name in filenames:
            if name in _SNYK_SCA_SUPPORTED_MARKERS:
                supported.add(name)
            for marker, label in _SNYK_SCA_UNSUPPORTED_LABELS:
                if name == marker:
                    unsupported.add(label)
    return tuple(sorted(supported)), tuple(sorted(unsupported))


def _snyk_package_na_detail(workdir, vendor_detail=None):
    """Operator-facing detail when `snyk test` has nothing it can audit."""
    supported, unsupported = _snyk_detect_sca_ecosystems(workdir)
    if unsupported and not supported:
        labels = ", ".join(unsupported)
        return (
            f"Snyk `snyk test` does not support {labels} manifests "
            "(Rust requires SBOM/API testing). "
            f"No SCA-supported manifests found under {workdir or 'workdir'}."
        )
    if vendor_detail:
        return str(vendor_detail).strip()
    if supported:
        return "Snyk reported no supported projects despite catalogueable manifests: " + ", ".join(
            supported
        )
    return (
        "No Snyk SCA-supported manifests found "
        "(needs package.json / requirements / pyproject / go.mod / …)."
    )


def _snyk_sca_severity(raw):
    return "red" if (raw or "").lower() in ("critical", "high") else "amber"


def _snyk_sca_projects(root):
    if isinstance(root, list):
        return [item for item in root if isinstance(item, dict)]
    if isinstance(root, dict):
        return [root]
    return []


def _snyk_sca_finding(vuln, target_file, source):
    name = vuln.get("packageName") or vuln.get("name") or "package"
    version = vuln.get("version") or ""
    vid = vuln.get("id") or "SNYK"
    title = vuln.get("title") or ""
    sev_raw = vuln.get("severity") or "medium"
    ident = vuln.get("identifiers") if isinstance(vuln.get("identifiers"), dict) else {}
    cves = ident.get("CVE") or []
    label = f"{name}@{version}" if version else name
    return {
        "severity": _snyk_sca_severity(sev_raw),
        "category": "dependency_vulnerability",
        "message": f"{label}: {vid} ({sev_raw}): {title}".strip(),
        "scanner_source": source,
        "file_path": target_file,
        "package_name": name,
        "package_version": version or None,
        "cve_ids": cves or [vid],
    }


def _snyk_parse_sca(root, source):
    findings, checks = [], 0
    for project in _snyk_sca_projects(root):
        target_file = project.get("displayTargetFile") or project.get("path") or ""
        deps = project.get("dependencyCount")
        vulns = project.get("vulnerabilities") or []
        if isinstance(deps, int):
            checks += deps
        elif isinstance(vulns, list):
            checks += len(vulns)
        if not isinstance(vulns, list):
            continue
        for vuln in vulns:
            if isinstance(vuln, dict):
                findings.append(_snyk_sca_finding(vuln, target_file, source))
    return findings, checks


def _snyk_package_result(source, code, out, err, console, workdir=""):
    root = _safe_json(out) or _safe_json(err)
    if code == _SNYK_SCA_NO_SUPPORTED_PROJECTS:
        vendor = root.get("error") if isinstance(root, dict) else None
        detail = _snyk_package_na_detail(workdir, vendor_detail=vendor or err or out)
        return [], [
            _skipped(
                source,
                "not_applicable",
                detail=detail,
                console_output=console,
            )
        ]
    if not isinstance(root, dict | list) or not root:
        return [], [_unreachable(source, err or out or f"exit {code}", console_output=console)]
    findings, checks = _snyk_parse_sca(root, source)
    if code not in (0, 1, None) and not findings:
        detail = root.get("error") if isinstance(root, dict) else None
        return [], [
            _unreachable(source, detail or err or out or f"exit {code}", console_output=console)
        ]
    return findings, [_completed(source, checks or 1, findings, console_output=console)]


def _snyk_cmd(workdir, item_type):
    # Package targets need SCA (`snyk test`). Agent Scan only inspects skills/MCP
    # (empty skill_risks/server_risks on application repos — live 2026-09-20).
    if item_type == "package":
        if _which("snyk"):
            return ["snyk", "test", "--json", "--all-projects", workdir]
        return None
    # --ci always requires --dangerously-run-mcp-servers (Snyk Agent Scan policy).
    # Skills additionally need --skills so the path is treated as SKILL.md, not MCP config.
    flags = ["--ci", "--dangerously-run-mcp-servers", "--json", workdir]
    if item_type == "skill":
        flags = ["--ci", "--dangerously-run-mcp-servers", "--skills", "--json", workdir]
    if _which("snyk-agent-scan"):
        return ["snyk-agent-scan", *flags]
    if _which("uvx"):
        return ["uvx", "snyk-agent-scan@latest", *flags]
    return None


def run_snyk(workdir, item_type="mcp_server"):
    source = "Snyk"
    if not os.environ.get("SNYK_TOKEN"):
        return [], [_skipped(source)]
    if item_type == "package":
        supported, unsupported = _snyk_detect_sca_ecosystems(workdir)
        # Only skip the CLI when we positively see unsupported-only trees
        # (e.g. Cargo.toml). Empty/missing workdirs still invoke snyk so exit-3
        # mapping and tests with mocked paths keep working.
        if not supported and unsupported:
            detail = _snyk_package_na_detail(workdir)
            return [], [_skipped(source, "not_applicable", detail=detail)]
    cmd = _snyk_cmd(workdir, item_type)
    if cmd is None:
        missing = (
            "snyk CLI not installed in image"
            if item_type == "package"
            else "snyk-agent-scan not installed and uvx missing from image"
        )
        return [], [_unreachable(source, missing)]

    code, out, err = _run(cmd, cwd=workdir)
    console = _build_console(out, err)
    if item_type == "package":
        return _snyk_package_result(source, code, out, err, console, workdir=workdir)

    root = _safe_json(out) or _safe_json(err) or {}
    if not isinstance(root, dict) or not root:
        return [], [_unreachable(source, err or out or f"exit {code}", console_output=console)]

    findings, checks = [], 0
    collected_errors = []
    paths_seen = 0
    for path_result in _snyk_iter_path_results(root):
        paths_seen += 1
        path_errs = _snyk_collect_errors(path_result)
        if path_errs:
            collected_errors.extend(path_errs)
        path_findings, path_checks = _snyk_findings_from_path(path_result, source)
        findings.extend(path_findings)
        checks += path_checks

    if collected_errors:
        detail = "; ".join(_snyk_error_message(e) for e in collected_errors)
        auth_only = all(_snyk_error_is_auth(e) for e in collected_errors) and not findings
        if auth_only:
            return [], [_skipped(source, detail=detail, console_output=console)]
        return findings, [_unreachable(source, detail, console_output=console)]
    # Valid path envelope with zero issues is a completed clean scan (auth + parse OK).
    if findings or checks or paths_seen:
        return findings, [
            _completed(source, checks or max(paths_seen, 1), findings, console_output=console)
        ]
    return findings, [
        _unreachable(
            source,
            err or out or f"exit {code}",
            console_output=console,
        )
    ]


# ---- Tessl (skills quality axis only, never findings) -----------------------

# Patterns that tessl skill lint may print; captures the leading digit group.
_TESSL_LINT_COUNT_RE = re.compile(r"(\d+)\s+(?:check|issue|error|warning|finding)", re.IGNORECASE)


def _tessl_quality_score(parsed):
    """Extract Tessl quality score (0–100) from current CLI --json shape."""
    if not isinstance(parsed, dict):
        return None
    if isinstance(parsed.get("score"), int | float):
        return parsed["score"]
    review = parsed.get("review")
    if isinstance(review, dict) and isinstance(review.get("reviewScore"), int | float):
        return review["reviewScore"]
    scores = []
    for key in ("descriptionJudge", "contentJudge"):
        node = parsed.get(key)
        if isinstance(node, dict) and isinstance(node.get("normalizedScore"), int | float):
            scores.append(float(node["normalizedScore"]) * 100.0)
    if scores:
        return sum(scores) / len(scores)
    return None


_TESSL_REVIEW_SOURCES = {
    "quality": "Tessl: Review (Quality)",
    "security": "Tessl: Review (Security)",
}


def _parse_tessl_run_id(parsed) -> str | None:
    """Extract Tessl review run ID from CLI --json (id / runId / run_id)."""
    if not isinstance(parsed, dict):
        return None
    for key in ("id", "runId", "run_id"):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    nested = parsed.get("review")
    if isinstance(nested, dict):
        return _parse_tessl_run_id(nested)
    return None


def _parse_tessl_whoami_username(parsed) -> str | None:
    """Extract username from ``tessl whoami --json`` (usually the personal workspace)."""
    if not isinstance(parsed, dict):
        return None
    user = parsed.get("user")
    if isinstance(user, dict):
        username = user.get("username")
        if isinstance(username, str) and username.strip():
            return username.strip()
    username = parsed.get("username")
    if isinstance(username, str) and username.strip():
        return username.strip()
    return None


# Last identity seen by ``_resolve_tessl_workspace`` — used to annotate CLI errors.
_tessl_last_username: str | None = None
_tessl_last_workspace: str | None = None

_TESSL_IDENTITY_ERROR_RE = re.compile(
    r"(?:workspace|user)\s+not\s+found",
    re.IGNORECASE,
)


def _remember_tessl_identity(*, username: str | None = None, workspace: str | None = None) -> None:
    """Cache Tessl whoami/workspace for identity-error annotations."""
    global _tessl_last_username, _tessl_last_workspace
    if username is not None:
        _tessl_last_username = username or None
    if workspace is not None:
        _tessl_last_workspace = workspace or None


def _annotate_tessl_cli_detail(
    detail: str,
    *,
    workspace: str | None = None,
    username: str | None = None,
) -> str:
    """Append user=/workspace= when Tessl reports user/workspace not found.

    Also prints the annotated line so Modal/container logs show which identity
    was attempted (raw Tessl stderr often omits the name).
    """
    text = (detail or "").strip()
    if not text:
        return ""
    if not _TESSL_IDENTITY_ERROR_RE.search(text):
        return text[:4000]
    user = (username if username is not None else _tessl_last_username) or None
    ws = (workspace if workspace is not None else _tessl_last_workspace) or None
    bits: list[str] = []
    if user:
        bits.append(f"user={user}")
    if ws:
        bits.append(f"workspace={ws}")
    if not bits:
        return text[:4000]
    annotated = f"{text} ({', '.join(bits)})"
    print(f"[tessl] {annotated}", flush=True)
    return annotated[:4000]


def _parse_tessl_workspace_list(parsed) -> list[dict]:
    """Normalize ``tessl workspace list --json`` to a list of workspace dicts."""
    if isinstance(parsed, list):
        return [ws for ws in parsed if isinstance(ws, dict)]
    if isinstance(parsed, dict):
        workspaces = parsed.get("workspaces")
        if isinstance(workspaces, list):
            return [ws for ws in workspaces if isinstance(ws, dict)]
    return []


def _pick_tessl_workspace(workspaces: list[dict], username: str | None) -> str | None:
    """Prefer username-named workspace, then one with scenario/review actions, else first."""
    named: list[dict] = []
    for ws in workspaces:
        name = ws.get("name")
        if isinstance(name, str) and name.strip():
            named.append(ws)
    if not named:
        return None
    if username:
        for ws in named:
            if ws["name"].strip() == username:
                return username
    for action in ("generate_eval_scenarios", "run_review"):
        for ws in named:
            actions = ws.get("allowedActions") or []
            if isinstance(actions, list) and action in actions:
                # named entries always carry a non-empty str name (filtered above).
                return str(ws["name"]).strip()
    return str(named[0]["name"]).strip()


def _match_tessl_workspace(workspaces: list[dict], needle: str) -> str | None:
    """Return canonical workspace name (or id) if *needle* matches a list entry name or id."""
    want = needle.strip()
    if not want:
        return None
    for ws in workspaces:
        name = ws.get("name")
        wid = ws.get("id")
        name_ok = isinstance(name, str) and name.strip() == want
        id_ok = isinstance(wid, str) and wid.strip() == want
        if name_ok or id_ok:
            if isinstance(name, str) and name.strip():
                return name.strip()
            if isinstance(wid, str) and wid.strip():
                return wid.strip()
    return None


def _resolve_tessl_workspace() -> tuple[str | None, str]:
    """Resolve Tessl workspace for ``--workspace``.

    Optional ``TESSL_WORKSPACE`` is an override only when it matches a workspace
    the authenticated account can see (name or id). Invalid overrides are ignored
    so Modal secrets with stale example values (e.g. ``engteam``) do not produce
    ``Workspace not found``. Otherwise resolve via ``tessl whoami`` +
    ``tessl workspace list`` (personal workspace is usually the username).
    """
    global _tessl_last_username, _tessl_last_workspace
    _tessl_last_username = None
    _tessl_last_workspace = None

    env_ws = (os.environ.get("TESSL_WORKSPACE") or "").strip()

    username = None
    who_code, who_out, who_err = _run(["npx", "--yes", "tessl@latest", "whoami", "--json"])
    if who_code == 0:
        username = _parse_tessl_whoami_username(_safe_json(who_out))
    _remember_tessl_identity(username=username)

    list_code, list_out, list_err = _run(
        ["npx", "--yes", "tessl@latest", "workspace", "list", "--json"]
    )
    if list_code != 0:
        # Cannot validate membership — honour env override if present.
        if env_ws:
            _remember_tessl_identity(workspace=env_ws)
            return env_ws, ""
        detail = (list_err or list_out or who_err or who_out or "workspace list failed").strip()
        return None, _annotate_tessl_cli_detail(detail[:4000], username=username)

    workspaces = _parse_tessl_workspace_list(_safe_json(list_out))
    available = [
        ws["name"].strip()
        for ws in workspaces
        if isinstance(ws.get("name"), str) and ws["name"].strip()
    ]

    if env_ws:
        matched = _match_tessl_workspace(workspaces, env_ws)
        if matched:
            _remember_tessl_identity(workspace=matched)
            return matched, ""
        print(
            f"[tessl] ignoring TESSL_WORKSPACE={env_ws!r} — not in workspace list "
            f"(available: {', '.join(available) or 'none'}); falling back to auto-resolve",
            flush=True,
        )

    picked = _pick_tessl_workspace(workspaces, username)
    if not picked:
        detail = "no Tessl workspaces available for this account"
        if env_ws:
            detail = (
                f"TESSL_WORKSPACE={env_ws!r} not found and no fallback workspace "
                f"(available: {', '.join(available) or 'none'})"
            )
        return None, _annotate_tessl_cli_detail(detail, workspace=env_ws or None, username=username)
    _remember_tessl_identity(workspace=picked)
    return picked, ""


def _tessl_review_run_argv(judge_type: str, workdir: str, workspace: str, force: bool) -> list[str]:
    argv = [
        "npx",
        "--yes",
        "tessl@latest",
        "review",
        "run",
        judge_type,
        "--json",
        "--workspace",
        workspace,
    ]
    if force:
        argv.append("--force")
    argv.append(workdir)
    return argv


def _capture_review_run_id(workspace: str, run_parsed) -> str | None:
    """Prefer tessl review view --last --json; fall back to run --json id."""
    _code, out, _err = _run(
        [
            "npx",
            "--yes",
            "tessl@latest",
            "review",
            "view",
            "--last",
            "--json",
            "--workspace",
            workspace,
        ]
    )
    view_id = _parse_tessl_run_id(_safe_json(out))
    if view_id:
        return view_id
    return _parse_tessl_run_id(run_parsed)


def _stamp_tessl_run_id(row: dict, run_id: str | None) -> None:
    if not run_id:
        return
    row["tessl_run_id"] = run_id
    row["tessl_run_id_at"] = datetime.now(UTC).isoformat()


def _new_tessl_id_context() -> dict[str, str | None]:
    """Seed in-process Tessl ID carry-forward (design § ID carry-forward)."""
    return {"review_quality": None, "scenario_gen": None}


def _update_tessl_id_context(ctx: dict[str, str | None], key: str, run_id: str | None) -> None:
    """Record a step's Tessl run ID for later steps in the same run_tessl() call."""
    ctx[key] = run_id


def _attach_upstream_run_ids(row: dict, ctx: dict[str, str | None], *keys: str) -> None:
    """Copy selected Tessl ID-context keys onto the row before CLI invoke."""
    row["upstream_run_ids"] = {key: ctx.get(key) for key in keys}


_TESSL_SCENARIO_SOURCE = "Tessl: Scenario Generation"
_TESSL_SCENARIO_COUNT = 3
_TESSL_SCENARIO_POLL_SLEEP_S = 2
_TESSL_SCENARIO_POLL_MAX = 90


def _has_tessl_plugin_manifest(workdir: str) -> bool:
    return os.path.isfile(os.path.join(workdir, ".tessl-plugin", "plugin.json"))


def _parse_scenario_status(parsed) -> str | None:
    if not isinstance(parsed, dict):
        return None
    for key in ("status", "state"):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    nested = parsed.get("generation")
    if isinstance(nested, dict):
        return _parse_scenario_status(nested)
    return None


def _parse_scenario_count(parsed) -> int | None:
    if not isinstance(parsed, dict):
        return None
    for key in ("scenarioCount", "scenario_count", "count", "checks_run"):
        value = parsed.get(key)
        if isinstance(value, int) and value >= 0:
            return value
    scenarios = parsed.get("scenarios")
    if isinstance(scenarios, list):
        return len(scenarios)
    nested = parsed.get("generation")
    if isinstance(nested, dict):
        return _parse_scenario_count(nested)
    return None


def _parse_scenario_gen_id(parsed) -> str | None:
    """Extract scenario generation ID from generate/view --json."""
    if not isinstance(parsed, dict):
        return None
    for key in ("id", "runId", "run_id", "generationId", "generation_id"):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    nested = parsed.get("generation")
    if isinstance(nested, dict):
        return _parse_scenario_gen_id(nested)
    return _parse_tessl_run_id(parsed)


def _tessl_scenario_generate_argv(
    workdir: str,
    workspace: str,
    count: int = _TESSL_SCENARIO_COUNT,
) -> list[str]:
    """Build ``tessl scenario generate`` argv (plugin path requires ``--workspace``)."""
    return [
        "npx",
        "--yes",
        "tessl@latest",
        "scenario",
        "generate",
        workdir,
        "--workspace",
        workspace,
        "--count",
        str(count),
    ]


def _tessl_scenario_view_argv(gen_id: str | None) -> list[str]:
    argv = ["npx", "--yes", "tessl@latest", "scenario", "view"]
    if gen_id:
        argv.append(gen_id)
    else:
        argv.extend(["--last", "--mine"])
    argv.append("--json")
    return argv


def _tessl_scenario_download_argv(gen_id: str, workdir: str) -> list[str]:
    return [
        "npx",
        "--yes",
        "tessl@latest",
        "scenario",
        "download",
        gen_id,
        "-o",
        os.path.join(workdir, "evals"),
    ]


def _emit_tessl_row_progress(on_progress, row: dict) -> None:
    if on_progress is None:
        return
    on_progress(dict(row))


def _count_evals_scenarios(workdir: str) -> int:
    evals_dir = os.path.join(workdir, "evals")
    if not os.path.isdir(evals_dir):
        return 0
    count = 0
    for name in os.listdir(evals_dir):
        path = os.path.join(evals_dir, name)
        if os.path.isdir(path) and not name.startswith("."):
            count += 1
    return count


def _poll_scenario_until_terminal(
    gen_id: str | None,
    *,
    max_attempts: int = _TESSL_SCENARIO_POLL_MAX,
    sleep_s: float = _TESSL_SCENARIO_POLL_SLEEP_S,
) -> tuple[str | None, dict | None, str]:
    """Poll scenario view until completed/failed. Returns (status, parsed, console)."""
    last_console = ""
    last_parsed = None
    for _ in range(max_attempts):
        code, out, err = _run(_tessl_scenario_view_argv(gen_id))
        last_console = _build_console(out, err) or last_console
        parsed = _safe_json(out)
        last_parsed = parsed if isinstance(parsed, dict) else last_parsed
        status = _parse_scenario_status(parsed)
        if status in {"completed", "failed"}:
            return status, last_parsed, last_console
        if code not in (0, None) and status is None:
            return "failed", last_parsed, last_console
        if sleep_s > 0:
            time.sleep(sleep_s)
    return _parse_scenario_status(last_parsed), last_parsed, last_console


def _capture_scenario_gen_id(generate_out: str, known_id: str | None = None) -> str | None:
    if known_id:
        return known_id
    from_generate = _parse_scenario_gen_id(_safe_json(generate_out))
    if from_generate:
        return from_generate
    _code, out, _err = _run(_tessl_scenario_view_argv(None))
    return _parse_scenario_gen_id(_safe_json(out))


def _scenario_row_with_console(row: dict, consoles: list[str]) -> dict:
    if consoles:
        row["console_output"] = "\n".join(consoles)[:MAX_CONSOLE_CHARS]
    return row


def _scenario_checkpoint_row(
    row: dict,
    *,
    status: str,
    detail: str,
    gen_id: str | None,
    consoles: list[str],
    on_progress,
) -> dict:
    row["status"] = status
    row["detail"] = detail[:4000]
    if gen_id:
        row["resume_checkpoint"] = {"stage": "generated", "gen_id": gen_id}
        _stamp_tessl_run_id(row, gen_id)
    _scenario_row_with_console(row, consoles)
    _emit_tessl_row_progress(on_progress, row)
    return row


def _scenario_gen_preflight(
    workdir: str, upstream_run_ids: dict, workspace: str | None
) -> dict | None:
    """Return an early terminal row when token/workspace/plugin prerequisites fail."""
    if not os.environ.get("TESSL_TOKEN"):
        skipped: dict = _skipped(
            _TESSL_SCENARIO_SOURCE, reason="needs_setup", detail="TESSL_TOKEN required"
        )
        skipped["upstream_run_ids"] = upstream_run_ids
        return skipped
    if not workspace:
        skipped = _skipped(
            _TESSL_SCENARIO_SOURCE,
            reason="needs_setup",
            detail="Tessl workspace unresolved — set TESSL_WORKSPACE or ensure tessl login",
        )
        skipped["upstream_run_ids"] = upstream_run_ids
        return skipped
    if _has_tessl_plugin_manifest(workdir):
        return None
    return {
        "scanner_source": _TESSL_SCENARIO_SOURCE,
        "status": "failed",
        "checks_run": 0,
        "detail": (
            "missing .tessl-plugin/plugin.json — import via `tessl skill import` "
            "or add a plugin manifest before scenario generation"
        ),
        "upstream_run_ids": upstream_run_ids,
    }


def _ensure_scenario_generated(
    workdir: str,
    row: dict,
    gen_id: str | None,
    stage: str | None,
    consoles: list[str],
    on_progress,
    workspace: str,
) -> tuple[str | None, dict | None]:
    """Ensure generation completed. Returns (gen_id, early_row_or_None)."""
    if stage == "generated" and gen_id:
        status, view_parsed, view_console = _poll_scenario_until_terminal(gen_id)
        if view_console:
            consoles.append(view_console)
        if status != "completed":
            early = _scenario_checkpoint_row(
                row,
                status="failed" if status == "failed" else "interrupted",
                detail=f"scenario generation status={status or 'unknown'} — download deferred",
                gen_id=gen_id,
                consoles=consoles,
                on_progress=on_progress,
            )
            return gen_id, early
        count_hint = _parse_scenario_count(view_parsed)
        if count_hint is not None:
            row["checks_run"] = count_hint
        return gen_id, None

    code, out, err = _run(_tessl_scenario_generate_argv(workdir, workspace))
    console = _build_console(out, err)
    if console:
        consoles.append(console)
    if code is None:
        timed_out_id = _capture_scenario_gen_id(out, gen_id)
        early = _scenario_checkpoint_row(
            row,
            status="interrupted",
            detail=_annotate_tessl_cli_detail(
                (err or out or "scenario generate timed out").strip(),
                workspace=workspace,
            ),
            gen_id=timed_out_id,
            consoles=consoles,
            on_progress=on_progress,
        )
        return timed_out_id, early
    if code != 0:
        row["status"] = "failed"
        row["detail"] = _annotate_tessl_cli_detail(
            (err or out or "scenario generate exited non-zero").strip(),
            workspace=workspace,
        )[:4000]
        return None, _scenario_row_with_console(row, consoles)
    captured_id = _capture_scenario_gen_id(out, gen_id)
    if not captured_id:
        row["status"] = "failed"
        row["detail"] = "scenario generate succeeded but no generation id was captured"
        return None, _scenario_row_with_console(row, consoles)
    row["resume_checkpoint"] = {"stage": "generated", "gen_id": captured_id}
    _stamp_tessl_run_id(row, captured_id)
    _emit_tessl_row_progress(on_progress, row)
    return captured_id, None


def _scenario_download_and_finish(
    workdir: str,
    ctx: dict[str, str | None],
    row: dict,
    gen_id: str,
    consoles: list[str],
    on_progress,
) -> dict:
    code, out, err = _run(_tessl_scenario_download_argv(gen_id, workdir))
    console = _build_console(out, err)
    if console:
        consoles.append(console)
    if code != 0:
        return _scenario_checkpoint_row(
            row,
            status="failed",
            detail=(err or out or "scenario download exited non-zero").strip(),
            gen_id=gen_id,
            consoles=consoles,
            on_progress=on_progress,
        )

    row["resume_checkpoint"] = {"stage": "moved"}
    _emit_tessl_row_progress(on_progress, row)

    checks = _count_evals_scenarios(workdir)
    if checks == 0:
        view_code, view_out, view_err = _run(_tessl_scenario_view_argv(gen_id))
        view_console = _build_console(view_out, view_err)
        if view_console:
            consoles.append(view_console)
        if view_code == 0:
            parsed_count = _parse_scenario_count(_safe_json(view_out))
            if parsed_count is not None:
                checks = parsed_count

    row["status"] = "completed"
    row["checks_run"] = checks
    row["detail"] = f"{checks} scenario{'s' if checks != 1 else ''} downloaded to evals/"
    row["resume_checkpoint"] = None
    _stamp_tessl_run_id(row, gen_id)
    _update_tessl_id_context(ctx, "scenario_gen", gen_id)
    _scenario_row_with_console(row, consoles)
    _emit_tessl_row_progress(on_progress, row)
    return row


def _run_tessl_scenario_gen(
    workdir: str,
    ctx: dict[str, str | None],
    *,
    workspace: str | None = None,
    resume_checkpoint: dict | None = None,
    on_progress=None,
) -> dict:
    """Run plugin-path scenario generate → download with resume_checkpoint support."""
    row: dict = {
        "scanner_source": _TESSL_SCENARIO_SOURCE,
        "status": "running",
        "checks_run": 0,
    }
    _attach_upstream_run_ids(row, ctx, "review_quality")
    _emit_tessl_row_progress(on_progress, row)

    gated = _scenario_gen_preflight(workdir, row["upstream_run_ids"], workspace)
    if gated is not None:
        return gated

    checkpoint = dict(resume_checkpoint) if isinstance(resume_checkpoint, dict) else {}
    gen_id = checkpoint.get("gen_id") if isinstance(checkpoint.get("gen_id"), str) else None
    stage = checkpoint.get("stage") if isinstance(checkpoint.get("stage"), str) else None
    consoles: list[str] = []

    gen_id, early = _ensure_scenario_generated(
        workdir, row, gen_id, stage, consoles, on_progress, workspace or ""
    )
    if early is not None:
        return early
    if not gen_id:
        row["status"] = "failed"
        row["detail"] = "scenario generation id missing after generate"
        return _scenario_row_with_console(row, consoles)
    return _scenario_download_and_finish(workdir, ctx, row, gen_id, consoles, on_progress)


_TESSL_EVAL_SOURCE = "Tessl: Eval"
_TESSL_EVAL_RUNS = 3
_TESSL_EVAL_POLL_SLEEP_S = 2
_TESSL_EVAL_POLL_MAX = 90


def _new_blocked_eval_row() -> dict:
    return {
        "scanner_source": _TESSL_EVAL_SOURCE,
        "status": "blocked",
        "checks_run": 0,
        "detail": "waiting for Scenario Generation to complete and populate evals/",
    }


def _has_tessl_project_link(workdir: str) -> bool:
    return os.path.isfile(os.path.join(workdir, "tessl.json"))


def _tessl_project_create_argv(workspace: str, project_name: str) -> list[str]:
    return [
        "npx",
        "--yes",
        "tessl@latest",
        "project",
        "create",
        "--workspace",
        workspace,
        project_name,
    ]


def _tessl_project_repair_argv() -> list[str]:
    return ["npx", "--yes", "tessl@latest", "project", "repair", "--yes"]


def _tessl_eval_run_argv(workdir: str, *, as_json: bool = False) -> list[str]:
    argv = [
        "npx",
        "--yes",
        "tessl@latest",
        "eval",
        "run",
        workdir,
        "--runs",
        str(_TESSL_EVAL_RUNS),
        "-y",
    ]
    if as_json:
        argv.append("--json")
    return argv


def _tessl_eval_view_argv(eval_id: str) -> list[str]:
    return ["npx", "--yes", "tessl@latest", "eval", "view", eval_id, "--json"]


def _parse_eval_status(parsed) -> str | None:
    if not isinstance(parsed, dict):
        return None
    for key in ("status", "state"):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    nested = parsed.get("eval") or parsed.get("evaluation")
    if isinstance(nested, dict):
        return _parse_eval_status(nested)
    return None


def _parse_eval_id(parsed) -> str | None:
    if not isinstance(parsed, dict):
        return None
    for key in ("id", "runId", "run_id", "evalId", "eval_id"):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for list_key in ("evals", "runs", "evalRuns", "eval_runs"):
        items = parsed.get(list_key)
        if isinstance(items, list) and items:
            first = _parse_eval_id(items[0]) if isinstance(items[0], dict) else None
            if first:
                return first
    nested = parsed.get("eval") or parsed.get("evaluation")
    if isinstance(nested, dict):
        return _parse_eval_id(nested)
    return _parse_tessl_run_id(parsed)


def _parse_eval_checks_run(parsed) -> int | None:
    if not isinstance(parsed, dict):
        return None
    for key in ("scenarioCount", "scenario_count", "checks_run", "count"):
        value = parsed.get(key)
        if isinstance(value, int) and value >= 0:
            return value
    scenarios = parsed.get("scenarios")
    if isinstance(scenarios, list):
        return len(scenarios)
    results = parsed.get("results")
    if isinstance(results, list):
        return len(results)
    nested = parsed.get("eval") or parsed.get("evaluation")
    if isinstance(nested, dict):
        return _parse_eval_checks_run(nested)
    return None


def _parse_eval_score_field(parsed, *keys: str) -> float | None:
    if not isinstance(parsed, dict):
        return None
    for key in keys:
        value = parsed.get(key)
        if isinstance(value, int | float):
            return float(value)
    nested = parsed.get("eval") or parsed.get("evaluation") or parsed.get("scores")
    if isinstance(nested, dict):
        return _parse_eval_score_field(nested, *keys)
    return None


def _format_eval_detail(parsed, fallback: str = "eval completed") -> str:
    baseline = _parse_eval_score_field(
        parsed, "baselineAvg", "baseline_avg", "baseline", "withoutContextAvg"
    )
    with_ctx = _parse_eval_score_field(
        parsed, "withContextAvg", "with_context_avg", "withContext", "contextAvg"
    )
    delta = _parse_eval_score_field(parsed, "delta", "deltaAvg", "delta_avg")
    parts: list[str] = []
    if baseline is not None:
        parts.append(f"baseline avg={baseline:g}")
    if with_ctx is not None:
        parts.append(f"with-context avg={with_ctx:g}")
    if delta is not None:
        parts.append(f"delta={delta:g}")
    runs = parsed.get("runs") if isinstance(parsed, dict) else None
    if isinstance(runs, int):
        parts.append(f"runs={runs}")
    elif isinstance(parsed, dict) and isinstance(parsed.get("runCount"), int):
        parts.append(f"runs={parsed['runCount']}")
    if not parts:
        return fallback
    return "; ".join(parts)


def _ensure_tessl_project(workdir: str, workspace: str) -> tuple[bool, str]:
    """Ensure tessl.json project link exists. Returns (ok, detail_on_failure)."""
    if _has_tessl_project_link(workdir):
        code, out, err = _run(_tessl_project_repair_argv(), cwd=workdir)
        if code not in (0, None) and not _has_tessl_project_link(workdir):
            return False, _annotate_tessl_cli_detail(
                (err or out or "tessl project repair failed").strip(),
                workspace=workspace,
            )
        return True, ""

    project_name = os.path.basename(os.path.abspath(workdir)) or "tripwire-scan"
    code, out, err = _run(_tessl_project_create_argv(workspace, project_name), cwd=workdir)
    if code == 0 and _has_tessl_project_link(workdir):
        return True, ""
    if code is None:
        return False, _annotate_tessl_cli_detail(
            (err or out or "tessl project create timed out").strip(),
            workspace=workspace,
        )
    detail = (err or out or "tessl project create failed").strip()
    return False, _annotate_tessl_cli_detail(
        detail or "tessl.json missing — project create/repair required before eval",
        workspace=workspace,
    )


def _eval_should_mark_stale(prior_eval: dict, scenario_row: dict) -> bool:
    # Stale when upstream gen id changed, or gen stamp is newer than eval completion.
    if prior_eval.get("status") != "completed":
        return False
    if scenario_row.get("status") != "completed":
        return False
    upstream = prior_eval.get("upstream_run_ids") or {}
    old_gen = upstream.get("scenario_gen") if isinstance(upstream, dict) else None
    new_gen = scenario_row.get("tessl_run_id")
    if old_gen and new_gen and old_gen != new_gen:
        return True
    scenario_at = scenario_row.get("tessl_run_id_at")
    eval_done = prior_eval.get("completed_at")
    if scenario_at and eval_done and str(scenario_at) > str(eval_done):
        return True
    return False


def _poll_eval_until_terminal(
    eval_id: str,
    *,
    max_attempts: int | None = None,
    sleep_s: float | None = None,
) -> tuple[str | None, dict | None, str]:
    attempts = _TESSL_EVAL_POLL_MAX if max_attempts is None else max_attempts
    pause = _TESSL_EVAL_POLL_SLEEP_S if sleep_s is None else sleep_s
    last_console = ""
    last_parsed = None
    for _ in range(attempts):
        code, out, err = _run(_tessl_eval_view_argv(eval_id))
        last_console = _build_console(out, err) or last_console
        parsed = _safe_json(out)
        last_parsed = parsed if isinstance(parsed, dict) else last_parsed
        status = _parse_eval_status(parsed)
        if status in {"completed", "failed"}:
            return status, last_parsed, last_console
        if code not in (0, None) and status is None:
            return "failed", last_parsed, last_console
        if pause > 0:
            time.sleep(pause)
    return _parse_eval_status(last_parsed), last_parsed, last_console


def _finish_eval_row(
    row: dict,
    *,
    status: str,
    eval_id: str | None,
    parsed: dict | None,
    consoles: list[str],
    detail: str | None = None,
    on_progress=None,
) -> dict:
    row["status"] = status
    if detail:
        row["detail"] = detail[:4000]
    elif parsed is not None:
        row["detail"] = _format_eval_detail(parsed)[:4000]
    checks = _parse_eval_checks_run(parsed) if parsed else None
    if checks is not None:
        row["checks_run"] = checks
    if eval_id:
        _stamp_tessl_run_id(row, eval_id)
    if consoles:
        row["console_output"] = "\n".join(consoles)[:MAX_CONSOLE_CHARS]
    _emit_tessl_row_progress(on_progress, row)
    return row


def _run_tessl_eval(
    workdir: str,
    ctx: dict[str, str | None],
    row: dict,
    *,
    workspace: str | None = None,
    resume_eval_id: str | None = None,
    on_progress=None,
) -> dict:
    """Auto-chain Eval: project preflight → eval run → stamp tessl_run_id."""
    _attach_upstream_run_ids(row, ctx, "review_quality", "scenario_gen")
    row["status"] = "queued"
    _emit_tessl_row_progress(on_progress, row)

    if not os.environ.get("TESSL_TOKEN"):
        row["status"] = "needs_setup"
        row["detail"] = "TESSL_TOKEN required for eval"
        _emit_tessl_row_progress(on_progress, row)
        return row
    if not workspace:
        row["status"] = "needs_setup"
        row["detail"] = "Tessl workspace unresolved — set TESSL_WORKSPACE or ensure tessl login"
        _emit_tessl_row_progress(on_progress, row)
        return row

    ok, project_detail = _ensure_tessl_project(workdir, workspace)
    if not ok:
        row["status"] = "needs_setup"
        row["detail"] = project_detail[:4000]
        _emit_tessl_row_progress(on_progress, row)
        return row

    row["status"] = "running"
    _emit_tessl_row_progress(on_progress, row)
    consoles: list[str] = []
    eval_id = resume_eval_id

    if not eval_id:
        # --json returns IDs immediately (Modal-friendly); then poll via eval view.
        code, out, err = _run(_tessl_eval_run_argv(workdir, as_json=True))
        console = _build_console(out, err)
        if console:
            consoles.append(console)
        parsed_run = _safe_json(out)
        eval_id = _parse_eval_id(parsed_run) if isinstance(parsed_run, dict) else None
        if code is None:
            return _finish_eval_row(
                row,
                status="interrupted" if eval_id else "timed_out",
                eval_id=eval_id,
                parsed=parsed_run if isinstance(parsed_run, dict) else None,
                consoles=consoles,
                detail=_annotate_tessl_cli_detail(
                    (err or out or "eval run timed out").strip(),
                    workspace=workspace,
                ),
                on_progress=on_progress,
            )
        if code != 0 and not eval_id:
            return _finish_eval_row(
                row,
                status="failed",
                eval_id=None,
                parsed=None,
                consoles=consoles,
                detail=_annotate_tessl_cli_detail(
                    (err or out or "eval run exited non-zero").strip(),
                    workspace=workspace,
                ),
                on_progress=on_progress,
            )
        if not eval_id:
            return _finish_eval_row(
                row,
                status="completed",
                eval_id=None,
                parsed=parsed_run if isinstance(parsed_run, dict) else None,
                consoles=consoles,
                detail=_format_eval_detail(
                    parsed_run if isinstance(parsed_run, dict) else {},
                    fallback="eval completed (no run id captured)",
                ),
                on_progress=on_progress,
            )
        _stamp_tessl_run_id(row, eval_id)
        _emit_tessl_row_progress(on_progress, row)

    status, view_parsed, view_console = _poll_eval_until_terminal(eval_id)
    if view_console:
        consoles.append(view_console)
    if status == "completed":
        return _finish_eval_row(
            row,
            status="completed",
            eval_id=eval_id,
            parsed=view_parsed,
            consoles=consoles,
            on_progress=on_progress,
        )
    if status == "failed":
        return _finish_eval_row(
            row,
            status="failed",
            eval_id=eval_id,
            parsed=view_parsed,
            consoles=consoles,
            detail=_format_eval_detail(view_parsed or {}, fallback="eval failed"),
            on_progress=on_progress,
        )
    return _finish_eval_row(
        row,
        status="interrupted",
        eval_id=eval_id,
        parsed=view_parsed,
        consoles=consoles,
        detail=f"eval status={status or 'unknown'} — resume via eval view",
        on_progress=on_progress,
    )


def _resolve_tessl_eval_row(
    workdir: str,
    ctx: dict[str, str | None],
    eval_row: dict,
    scenario_row: dict,
    *,
    workspace: str | None = None,
    prior_eval: dict | None = None,
    on_progress=None,
) -> dict:
    """Apply stale / resume / auto-chain rules after Scenario Generation."""
    prior = dict(prior_eval) if isinstance(prior_eval, dict) else None

    if prior and prior.get("status") == "completed":
        if _eval_should_mark_stale(prior, scenario_row):
            stale = {
                **prior,
                "scanner_source": _TESSL_EVAL_SOURCE,
                "status": "stale",
                "detail": (
                    prior.get("detail") or "Scenario Generation re-run — eval result is stale"
                ),
            }
            _emit_tessl_row_progress(on_progress, stale)
            return stale
        kept = {**prior, "scanner_source": _TESSL_EVAL_SOURCE}
        _emit_tessl_row_progress(on_progress, kept)
        return kept

    resume_id = None
    if prior and isinstance(prior.get("tessl_run_id"), str):
        if prior.get("status") in {"interrupted", "running", "queued", "timed_out"}:
            resume_id = prior["tessl_run_id"]
            eval_row = {
                **eval_row,
                **{
                    k: prior[k]
                    for k in (
                        "upstream_run_ids",
                        "tessl_run_id",
                        "tessl_run_id_at",
                    )
                    if k in prior
                },
            }

    if resume_id:
        return _run_tessl_eval(
            workdir,
            ctx,
            eval_row,
            workspace=workspace,
            resume_eval_id=resume_id,
            on_progress=on_progress,
        )

    scenario_ok = scenario_row.get("status") == "completed"
    has_scenarios = _count_evals_scenarios(workdir) > 0
    if scenario_ok and has_scenarios and eval_row.get("status") in {"blocked", "not_started"}:
        return _run_tessl_eval(workdir, ctx, eval_row, workspace=workspace, on_progress=on_progress)

    _emit_tessl_row_progress(on_progress, eval_row)
    return eval_row


def _finish_tessl_review(
    judge_type: str, source: str, workspace: str, code, out: str, err: str
) -> tuple[float | None, dict]:
    console = _build_console(out, err)
    if code != 0:
        return None, _unreachable(
            source,
            _annotate_tessl_cli_detail(err or out, workspace=workspace),
            console_output=console,
        )
    parsed = _safe_json(out)
    score = _tessl_quality_score(parsed) if judge_type == "quality" else None
    if judge_type == "quality" and score is None:
        print(f"[tessl] quality_score extraction failed — raw output: {out[:500]!r}")
        return None, _unreachable(
            source,
            "scanner returned no parseable quality score",
            console_output=console,
        )
    detail = f"quality_score = {score}" if judge_type == "quality" else "review completed"
    row = {
        "scanner_source": source,
        "status": "completed",
        "checks_run": 1,
        "detail": detail,
    }
    _stamp_tessl_run_id(row, _capture_review_run_id(workspace, parsed))
    if console:
        row["console_output"] = console
    return score, row


def _run_tessl_review(
    judge_type: str,
    workdir: str,
    workspace: str,
    prior_run_id: str | None = None,
    force: bool = False,
) -> tuple[float | None, dict]:
    """Run tessl review run <judge_type> and capture tessl_run_id via view --last.

    prior_run_id is reserved for cache-hit (design § Shared Review Mechanic);
    unused in slice 47.
    """
    del prior_run_id
    source = _TESSL_REVIEW_SOURCES[judge_type]
    if not _which("npx"):
        return None, _unreachable(source, "npx not available (node/npm missing from image)")
    code, out, err = _run(_tessl_review_run_argv(judge_type, workdir, workspace, force))
    return _finish_tessl_review(judge_type, source, workspace, code, out, err)


def _security_review_preflight(source: str, workspace: str | None, upstream: dict) -> dict | None:
    """needs_setup when token or workspace is missing; keep upstream snapshot."""
    if os.environ.get("TESSL_TOKEN") and workspace:
        return None
    detail = None
    if os.environ.get("TESSL_TOKEN"):
        detail = "Tessl workspace unresolved — set TESSL_WORKSPACE or ensure tessl login"
    skipped: dict = _skipped(source, reason="needs_setup", detail=detail)
    skipped["upstream_run_ids"] = upstream
    return skipped


def _run_tessl_security_review(
    workdir: str,
    ctx: dict[str, str | None],
    workspace: str | None,
    *,
    on_progress=None,
) -> dict:
    """Security review: attach Quality ID, then reuse _run_tessl_review."""
    source = _TESSL_REVIEW_SOURCES["security"]
    pending: dict = {"scanner_source": source, "status": "running", "checks_run": 0}
    _attach_upstream_run_ids(pending, ctx, "review_quality")
    _emit_tessl_row_progress(on_progress, pending)
    upstream = pending["upstream_run_ids"]
    gated = _security_review_preflight(source, workspace, upstream)
    if gated is not None:
        _emit_tessl_row_progress(on_progress, gated)
        return gated
    assert workspace is not None
    _score, finished = _run_tessl_review("security", workdir, workspace)
    finished["upstream_run_ids"] = upstream
    _emit_tessl_row_progress(on_progress, finished)
    return finished


def _parse_tessl_lint_detail(output: str) -> tuple[int | None, str]:
    """Extract check count and summary from tessl skill lint text output.

    Returns (checks_run, detail). checks_run is None when the output contains
    no recognisable count pattern and is not a package-valid success line.
    Live CLI (2026-08-24) prints ``✔ Plugin <name>@<ver> is valid`` with no
    numeric count — that is one package-level check. detail is capped at 500 chars.
    """
    text = output.strip()
    match = _TESSL_LINT_COUNT_RE.search(text)
    checks_run = int(match.group(1)) if match else None
    if checks_run is None and re.search(r"\bis valid\b", text, re.IGNORECASE):
        checks_run = 1
    detail = text[:500] if text else "lint completed — no output"
    return checks_run, detail


def run_tessl(
    workdir,
    id_context: dict[str, str | None] | None = None,
    *,
    resume_checkpoint: dict | None = None,
    prior_eval: dict | None = None,
    on_row_progress=None,
):
    """Run Tessl Lint, Review Quality, Scenario Generation, Eval, then Security.

    Lint is synchronous and never requires TESSL_TOKEN; it always runs when npx
    is available.  Review Quality, Scenario Generation, Eval, and Security need
    ``TESSL_TOKEN``. Workspace for ``--workspace`` comes from optional
    ``TESSL_WORKSPACE`` or is resolved via ``tessl whoami`` + ``workspace list``
    (personal workspace is usually the authenticated username). Scenario
    Generation also needs ``.tessl-plugin/plugin.json``. Eval starts ``blocked``
    and auto-chains after Scenario Generation completes with scenarios in
    ``evals/`` (first run only; re-runs mark prior completed Eval as ``stale``).
    Security Review shares ``_run_tessl_review(judge_type="security")`` and
    snapshots ``upstream_run_ids.review_quality`` before invoke.

    Returns (quality_score, [lint_row, review_row, scenario_row, eval_row, security_row]).
    quality_score is None when Review Quality did not complete successfully.

    id_context is the in-process Tessl ID bag for this invocation (GWT-47.5).
    Tests inject it to observe carry-forward; production seeds a fresh dict.
    resume_checkpoint resumes Scenario Generation after Modal detach/timeout.
    prior_eval rehydrates Eval for stale detection or eval-view resume.
    on_row_progress receives partial Tessl rows for mid-scan persist.
    """
    rows: list[dict] = []
    ctx = id_context if id_context is not None else _new_tessl_id_context()

    # --- Tessl: Lint (auth-free, synchronous) ---
    lint_source = "Tessl: Lint"
    if not _which("npx"):
        lint_row = _unreachable(lint_source, "npx not available (node/npm missing from image)")
        rows.append(lint_row)
        _emit_tessl_row_progress(on_row_progress, lint_row)
    else:
        _emit_tessl_row_progress(
            on_row_progress,
            {"scanner_source": lint_source, "status": "running", "checks_run": 0},
        )
        code, out, err = _run(["npx", "--yes", "tessl@latest", "skill", "lint", workdir])
        console = _build_console(out, err)
        if code != 0:
            lint_row = {
                "scanner_source": lint_source,
                "status": "failed",
                "checks_run": 0,
                "detail": (err or out or "lint subprocess exited non-zero").strip()[:4000],
            }
            if console:
                lint_row["console_output"] = console
        else:
            checks_run, detail = _parse_tessl_lint_detail(out)
            lint_row = {
                "scanner_source": lint_source,
                "status": "completed",
                "checks_run": checks_run,
                "detail": detail,
            }
            if console:
                lint_row["console_output"] = console
        rows.append(lint_row)
        _emit_tessl_row_progress(on_row_progress, lint_row)

    # --- Tessl: Review (Quality) (TESSL_TOKEN + resolved workspace) ---
    score = None
    workspace: str | None = None
    workspace_detail = ""
    review_source = "Tessl: Review (Quality)"
    if not os.environ.get("TESSL_TOKEN"):
        review_row = _skipped(review_source, reason="needs_setup")
        rows.append(review_row)
        _emit_tessl_row_progress(on_row_progress, review_row)
        _update_tessl_id_context(ctx, "review_quality", None)
    else:
        workspace, workspace_detail = _resolve_tessl_workspace()
        if not workspace:
            review_row = _skipped(
                review_source,
                reason="needs_setup",
                detail=workspace_detail
                or "Tessl workspace unresolved — set TESSL_WORKSPACE or ensure tessl login",
            )
            rows.append(review_row)
            _emit_tessl_row_progress(on_row_progress, review_row)
            _update_tessl_id_context(ctx, "review_quality", None)
        else:
            _emit_tessl_row_progress(
                on_row_progress,
                {"scanner_source": review_source, "status": "running", "checks_run": 0},
            )
            score, review_row = _run_tessl_review("quality", workdir, workspace)
            rows.append(review_row)
            _emit_tessl_row_progress(on_row_progress, review_row)
            _update_tessl_id_context(ctx, "review_quality", review_row.get("tessl_run_id"))

    # --- Tessl: Eval (blocked until Scenario Generation completes) ---
    eval_row = _new_blocked_eval_row()
    _emit_tessl_row_progress(on_row_progress, eval_row)

    # --- Tessl: Scenario Generation (token + plugin manifest + workspace) ---
    scenario_row = _run_tessl_scenario_gen(
        workdir,
        ctx,
        workspace=workspace,
        resume_checkpoint=resume_checkpoint,
        on_progress=on_row_progress,
    )
    rows.append(scenario_row)

    eval_row = _resolve_tessl_eval_row(
        workdir,
        ctx,
        eval_row,
        scenario_row,
        workspace=workspace,
        prior_eval=prior_eval,
        on_progress=on_row_progress,
    )
    rows.append(eval_row)

    rows.append(_run_tessl_security_review(workdir, ctx, workspace, on_progress=on_row_progress))
    return score, rows


# ---- DepShield (dependency vulnerability audit via depshield-mcp) -----------
# depshield-mcp v1.0.0 (VERIFIED against live server + npm tarball 2026-08-15):
# MCP JSON-RPC over stdio, newline-delimited (one JSON object per line, no
# Content-Length headers). audit_project takes filePath (ONE manifest FILE, not
# a directory) and supports package.json + requirements.txt only — its dispatch
# is `.json` → package.json parser, anything else → requirements format, so
# pyproject.toml is deliberately excluded from discovery. Data via OSV.dev /
# npm / PyPI over the network; zero credentials.

# Whole-group wall-clock budget. The sequential scanner chain must stay under
# SCAN_TIMEOUT=240s (sandbox hard-kills at 300s), so DepShield gets ~120s:
# handshake ≤20s + per-manifest audit calls against the shared deadline.
# Single source of truth for the pinned depshield-mcp version; the Modal image
# install line in scan_app.py must match (sync-checked by test_scanners_depshield).
DEPSHIELD_VERSION = "1.0.0"
DEPSHIELD_TIMEOUT = 110
DEPSHIELD_HANDSHAKE_TIMEOUT = 20
DEPSHIELD_MAX_MANIFESTS = 10
_DEPSHIELD_MANIFEST_NAMES = ("package.json", "requirements.txt")
_DEPSHIELD_SKIP_DIRS = frozenset({"node_modules", ".git", "venv", ".venv", "__pycache__"})

_DEPSHIELD_SUMMARY_RE = re.compile(
    r"summary:\s*(\d+)\s+dependenc(?:y|ies)\s+scanned", re.IGNORECASE
)
_DEPSHIELD_PACKAGE_RE = re.compile(r"📦\s*(\S+)@(\S+)")
_DEPSHIELD_ADVISORY_RE = re.compile(
    r"[•*-]\s*([A-Za-z]+-[A-Za-z0-9-]+)\s*\(([A-Za-z]+)\)\s*:\s*(.*)"
)


class _MCPStdioClient:
    """Minimal newline-delimited JSON-RPC 2.0 client over a child's stdio.

    A reader thread pumps stdout lines into a queue so every read honors the
    group deadline; callers must invoke :meth:`close` in a ``finally`` block so
    the child is terminated/killed even on timeout (no zombie processes).
    """

    def __init__(self, cmd, deadline):
        self._deadline = deadline
        self._next_id = 0
        self._lines = queue.Queue()
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            # Locale-independent: under a forced ASCII locale the emoji-laden
            # report bytes would raise UnicodeDecodeError in the reader thread
            # and masquerade as "closed stdout". Replacement chars keep the
            # stable ASCII parse tokens intact.
            encoding="utf-8",
            errors="replace",
        )
        threading.Thread(target=self._pump_stdout, daemon=True).start()

    def _pump_stdout(self):
        try:
            for line in self._proc.stdout:
                self._lines.put(line)
        except ValueError:  # stdout closed mid-iteration by close()
            pass
        self._lines.put(None)  # EOF sentinel

    def _send(self, message):
        try:
            self._proc.stdin.write(json.dumps(message) + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise RuntimeError(f"depshield-mcp stdin closed: {exc}") from exc

    def _read_message(self, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("depshield-mcp deadline exceeded")
        try:
            line = self._lines.get(timeout=remaining)
        except queue.Empty as exc:
            raise TimeoutError("depshield-mcp deadline exceeded") from exc
        if line is None:
            # Re-put the sentinel so every later read fails fast instead of
            # blocking on the drained queue until the group deadline.
            self._lines.put(None)
            raise RuntimeError("depshield-mcp closed stdout (process exited)")
        try:
            return json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"depshield-mcp sent a non-JSON line: {line.strip()[:200]}") from exc

    def notify(self, method):
        self._send({"jsonrpc": "2.0", "method": method})

    def request(self, method, params, call_timeout=None):
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params})
        deadline = self._deadline
        if call_timeout is not None:
            deadline = min(deadline, time.monotonic() + call_timeout)
        while True:  # skip notifications/other ids until our response arrives
            message = self._read_message(deadline)
            if isinstance(message, dict) and message.get("id") == self._next_id:
                return message

    def close(self):
        try:
            if self._proc.stdin:
                self._proc.stdin.close()
        except OSError:
            pass
        self._proc.terminate()
        try:
            self._proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Nothing left to escalate to after SIGKILL (D-state child);
                # close() runs in a finally block and must never raise.
                pass


def _depshield_cmd():
    if _which("depshield-mcp"):
        return ["depshield-mcp"]
    if _which("npx"):
        # Pinned: the interface contract (filePath arg, newline framing,
        # report wording) was verified against exactly this version; an
        # unpinned fallback would silently adopt future format drift.
        return ["npx", "-y", f"depshield-mcp@{DEPSHIELD_VERSION}"]
    return None


def _depshield_handshake(client):
    resp = client.request(
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "tripwire", "version": "0.4.0"},
        },
        call_timeout=DEPSHIELD_HANDSHAKE_TIMEOUT,
    )
    if not isinstance(resp.get("result"), dict):
        raise RuntimeError(f"initialize failed: {json.dumps(resp)[:300]}")
    client.notify("notifications/initialized")


def _depshield_audit(client, manifest_abspath):
    """Call audit_project for ONE manifest file; return the report text.

    Raises RuntimeError on JSON-RPC error / isError results, TimeoutError when
    the group deadline expires mid-call.
    """
    resp = client.request(
        "tools/call",
        {
            "name": "audit_project",
            "arguments": {"filePath": manifest_abspath, "includeDevDependencies": True},
        },
    )
    result = resp.get("result")
    if not isinstance(result, dict):
        error = resp.get("error") or {}
        raise RuntimeError(f"audit_project failed: {error.get('message') or 'no result'}")
    content = result.get("content") or []
    if not isinstance(content, list):
        raise RuntimeError(f"audit_project returned malformed content ({type(content).__name__})")
    text = "\n".join(str(c.get("text") or "") for c in content if isinstance(c, dict))
    if result.get("isError"):
        raise RuntimeError(f"audit_project isError: {text.strip()[:300] or 'no message'}")
    return text


def _find_manifests(workdir):
    """Relative paths of supported dependency manifests under *workdir*.

    Returns ``(kept, total_found)``; *kept* is capped at DEPSHIELD_MAX_MANIFESTS
    and callers must surface truncation in the row detail (no silent caps).
    """
    found = []
    for root, dirnames, filenames in os.walk(workdir):
        dirnames[:] = sorted(d for d in dirnames if d not in _DEPSHIELD_SKIP_DIRS)
        for name in sorted(filenames):
            if name in _DEPSHIELD_MANIFEST_NAMES:
                found.append(os.path.relpath(os.path.join(root, name), workdir))
    return found[:DEPSHIELD_MAX_MANIFESTS], len(found)


def _depshield_severity(raw):
    """CRITICAL/HIGH → red; MEDIUM/LOW/UNKNOWN/anything else → amber.

    UNKNOWN must not vanish: a confirmed advisory with unrated severity matches
    the tool's own MODERATE-risk verdict, so it stays visible as amber.
    """
    return "red" if (raw or "").upper() in ("CRITICAL", "HIGH") else "amber"


def _depshield_advisory_url(advisory_id):
    if advisory_id.upper().startswith("GHSA-"):
        return f"https://github.com/advisories/{advisory_id}"
    return f"https://osv.dev/vulnerability/{advisory_id}"


def _depshield_finding(package, version, advisory_id, severity_raw, summary, manifest_relpath):
    sev = severity_raw.upper()
    return {
        "severity": _depshield_severity(sev),
        "category": "dependency_vulnerability",
        "message": f"{package}@{version}: {advisory_id} ({sev}): {summary.strip() or 'No summary'}",
        "scanner_source": "DepShield",
        "file_path": manifest_relpath,
        "package_name": package,
        "package_version": version,
        "cve_ids": [advisory_id],
        "advisory_url": _depshield_advisory_url(advisory_id),
        "advisory_provider": "osv.dev",
    }


def _parse_depshield_report(text, manifest_relpath):
    """Parse the human-readable audit report → (findings, checks_run).

    Matches stable tokens only ("Summary: N dependencies scanned", 📦 package
    blocks, • advisory bullets) so emoji/whitespace drift stays harmless.
    """
    summary = _DEPSHIELD_SUMMARY_RE.search(text)
    checks = int(summary.group(1)) if summary else 0
    findings = []
    package = version = None
    for line in text.splitlines():
        pkg = _DEPSHIELD_PACKAGE_RE.search(line)
        if pkg:
            package, version = pkg.group(1), pkg.group(2)
            continue
        adv = _DEPSHIELD_ADVISORY_RE.search(line)
        if adv and package:
            findings.append(
                _depshield_finding(
                    package, version, adv.group(1), adv.group(2), adv.group(3), manifest_relpath
                )
            )
    return findings, checks


def _depshield_audit_all(client, workdir, manifests):
    """Audit each manifest; never raises. Returns (findings, checks, reports, errors)."""
    findings, checks, reports, errors = [], 0, [], []
    for manifest in manifests:
        try:
            text = _depshield_audit(client, os.path.abspath(os.path.join(workdir, manifest)))
        except TimeoutError as exc:
            errors.append(f"{manifest}: {exc} — remaining manifests skipped")
            break
        except RuntimeError as exc:
            errors.append(f"{manifest}: {exc}")
            continue
        # A "successful" response whose text carries neither the summary token
        # nor a package block is format drift, not a clean audit — counting it
        # as a report would roll the item up green on zero evidence.
        if not (_DEPSHIELD_SUMMARY_RE.search(text) or _DEPSHIELD_PACKAGE_RE.search(text)):
            errors.append(f"{manifest}: unrecognized report format — treated as audit error")
            continue
        reports.append(text)
        f, c = _parse_depshield_report(text, manifest)
        findings += f
        checks += c
    return findings, checks, reports, errors


def run_depshield(workdir, item_type="mcp_server"):
    """Audit npm/PyPI dependency manifests via the depshield-mcp stdio server.

    includeDevDependencies is always true — a vulnerable dev dependency in an
    agent skill still executes on the user's machine. *item_type* does not
    change behavior (same manifests audited for skills and MCP servers).
    """
    source = "DepShield"
    manifests, total = _find_manifests(workdir)
    if not manifests:
        return [], [
            _skipped(
                source,
                "not_applicable",
                detail="no dependency manifests (package.json / requirements.txt) in workdir",
            )
        ]
    cmd = _depshield_cmd()
    if cmd is None:
        return [], [_unreachable(source, "depshield-mcp not installed and npx missing from image")]

    client = None
    try:
        client = _MCPStdioClient(cmd, time.monotonic() + DEPSHIELD_TIMEOUT)
        _depshield_handshake(client)
        findings, checks, reports, errors = _depshield_audit_all(client, workdir, manifests)
    except (OSError, RuntimeError, TimeoutError, TypeError, ValueError) as exc:
        # TypeError/ValueError backstop: malformed JSON-RPC envelopes from a
        # drifted server version must degrade to unreachable, never crash the
        # scan run (ADR-0005 never-crash contract).
        return [], [_unreachable(source, f"depshield-mcp session failed: {exc}")]
    finally:
        if client is not None:
            client.close()

    console = _build_console("\n\n".join(reports), "\n".join(errors))
    if not reports:
        return [], [
            _unreachable(
                source,
                "; ".join(errors) or "no manifest produced a report",
                console_output=console,
            )
        ]
    row = _completed(source, checks, findings, console_output=console)
    notes = []
    if total > len(manifests):
        notes.append(f"manifest list truncated to {len(manifests)} of {total} found")
    if errors:
        notes.append(f"{len(errors)} manifest audit error(s): " + "; ".join(errors)[:500])
    if notes:
        row["detail"] = f"{row['detail']} — {'; '.join(notes)}"[:4000]
    return findings, [row]


# ---- Cargo Audit (RustSec advisory DB via cargo-audit) ----------------------
# Prefer real RustSec SCA over LLM source review when Cargo.lock/Cargo.toml is
# present (Wave R slice 72 gap fill; DECISIONS 2026-09-20). LLM Rust analysis
# stays deferred while cargo-audit covers package advisories.
# Exit codes (cargo-audit): 0 = clean, 1 = vulns/warnings denied, 2 = error.
# Tail budget: DEPSHIELD + CARGO_AUDIT + OSSPREY <= SCAN_TIMEOUT.

CARGO_AUDIT_TIMEOUT = 40
CARGO_AUDIT_SOURCES = ["Cargo Audit"]
_CARGO_AUDIT_SKIP_DIRS = frozenset(
    {"node_modules", ".git", "venv", ".venv", "__pycache__", "target"}
)


def _cargo_audit_find_lockfile(workdir):
    """Prefer Cargo.lock; fall back to a directory that has Cargo.toml only."""
    locks = []
    tomls = []
    for root, dirnames, filenames in os.walk(workdir):
        dirnames[:] = sorted(d for d in dirnames if d not in _CARGO_AUDIT_SKIP_DIRS)
        rel_root = os.path.relpath(root, workdir)
        if "Cargo.lock" in filenames:
            locks.append("." if rel_root == "." else rel_root)
        elif "Cargo.toml" in filenames:
            tomls.append("." if rel_root == "." else rel_root)
    if locks:
        return locks[0], "Cargo.lock"
    if tomls:
        return tomls[0], "Cargo.toml"
    return None, None


def _cargo_audit_cmd():
    """Return argv prefix for RustSec cargo-audit.

    The ``cargo-audit`` binary is a Cargo plugin: clap's bin_name is ``cargo``,
    so a direct invoke still needs the ``audit`` subcommand token first.
    ``cargo-audit --json`` is parsed as ``cargo --json`` → unexpected argument.
    Correct forms: ``cargo-audit audit --json`` or ``cargo audit --json``.
    """
    if _which("cargo-audit"):
        return ["cargo-audit", "audit"]
    if _which("cargo"):
        return ["cargo", "audit"]
    return None


def _cargo_audit_severity(advisory):
    """Map RustSec advisory severity / CVSS to Tripwire red|amber."""
    if not isinstance(advisory, dict):
        return "amber"
    raw = advisory.get("severity")
    if isinstance(raw, str):
        collapsed = _collapse_severity(raw)
        if collapsed in ("red", "amber"):
            return collapsed
    cvss = advisory.get("cvss")
    if isinstance(cvss, dict):
        score = cvss.get("score")
        try:
            n = float(score)
        except (TypeError, ValueError):
            n = None
        if n is not None:
            if n >= 7.0:
                return "red"
            return "amber"
    # Known advisory without a score is still actionable.
    return "amber"


def _cargo_audit_finding(entry, lock_relpath):
    advisory = entry.get("advisory") if isinstance(entry, dict) else {}
    package = entry.get("package") if isinstance(entry, dict) else {}
    if not isinstance(advisory, dict):
        advisory = {}
    if not isinstance(package, dict):
        package = {}
    adv_id = advisory.get("id") or "RUSTSEC-unknown"
    title = advisory.get("title") or advisory.get("description") or "RustSec advisory"
    pkg_name = package.get("name") or advisory.get("package") or "unknown"
    pkg_ver = package.get("version") or "?"
    url = advisory.get("url") or f"https://rustsec.org/advisories/{adv_id}"
    # Shape must match findings schema (DepShield/Snyk SCA). Unknown columns or
    # entity_kind='package' (CHECK allows tool|prompt|resource|server only) make
    # PostgREST insert raise → scan_app marks the whole run failed despite a
    # completed Cargo Audit row (dashboard ERROR with empty findings).
    return {
        "severity": _cargo_audit_severity(advisory),
        "category": "dependency_vulnerability",
        "message": f"{pkg_name}@{pkg_ver}: {title}",
        "scanner_source": "Cargo Audit",
        "file_path": lock_relpath,
        "package_name": pkg_name,
        "package_version": None if pkg_ver == "?" else pkg_ver,
        "cve_ids": [str(adv_id)],
        "advisory_url": url,
        "advisory_provider": "rustsec",
    }


def _parse_cargo_audit_json(text, lock_relpath):
    """Parse `cargo audit --json` report into findings + check count."""
    try:
        root = json.loads(text or "{}")
    except json.JSONDecodeError:
        return [], 0, "cargo-audit JSON parse failed"
    vulns = root.get("vulnerabilities") if isinstance(root, dict) else None
    if not isinstance(vulns, dict):
        return [], 0, None
    entries = vulns.get("list") or []
    if not isinstance(entries, list):
        entries = []
    findings = []
    for entry in entries:
        if isinstance(entry, dict):
            findings.append(_cargo_audit_finding(entry, lock_relpath))
    checks = max(int(vulns.get("count") or 0), len(findings), 1)
    return findings, checks, None


def run_cargo_audit(workdir, item_type="package"):
    """Audit Cargo.lock / Cargo.toml trees via RustSec cargo-audit.

    *item_type* does not change behaviour — N/A when no Cargo manifests exist.
    """
    source = "Cargo Audit"
    crate_dir, kind = _cargo_audit_find_lockfile(workdir)
    if crate_dir is None:
        return [], [
            _skipped(
                source,
                "not_applicable",
                detail="no Cargo.toml / Cargo.lock in workdir",
            )
        ]
    cmd = _cargo_audit_cmd()
    if cmd is None:
        return [], [
            _unreachable(
                source,
                "cargo-audit not installed (and cargo missing from image)",
            )
        ]

    abs_dir = workdir if crate_dir == "." else os.path.join(workdir, crate_dir)
    lock_rel = "Cargo.lock" if kind == "Cargo.lock" else os.path.join(crate_dir, "Cargo.toml")
    if crate_dir != "." and kind == "Cargo.lock":
        lock_rel = os.path.join(crate_dir, "Cargo.lock")
    elif crate_dir == "." and kind == "Cargo.toml":
        lock_rel = "Cargo.toml"

    argv = [*cmd, "--json"]
    if kind == "Cargo.lock" and crate_dir != ".":
        argv.extend(["--file", os.path.join(abs_dir, "Cargo.lock")])
        run_cwd = workdir
    else:
        run_cwd = abs_dir

    try:
        code, out, err = _run(argv, timeout=CARGO_AUDIT_TIMEOUT, cwd=run_cwd)
    except subprocess.TimeoutExpired:
        return [], [
            _unreachable(
                source,
                f"cargo-audit timed out after {CARGO_AUDIT_TIMEOUT}s",
            )
        ]
    except OSError as exc:
        return [], [_unreachable(source, f"cargo-audit failed to start: {exc}")]

    console = _build_console(out, err)
    # Exit 2 = tool/error; exit 1 = vulns found (still a completed scan).
    if code not in (0, 1):
        detail = (err or out or f"cargo-audit exit {code}").strip()[:4000]
        return [], [_unreachable(source, detail, console_output=console)]

    findings, checks, parse_err = _parse_cargo_audit_json(out, lock_rel)
    if parse_err and code == 0 and not (out or "").strip():
        # Clean scan sometimes prints little JSON — treat as completed zero vulns.
        return [], [_completed(source, 1, [], console_output=console)]
    if parse_err and not findings:
        return [], [_unreachable(source, parse_err, console_output=console)]

    row = _completed(source, checks, findings, console_output=console)
    if kind == "Cargo.toml":
        row["detail"] = (
            f"{row.get('detail', '')} — audited via Cargo.toml "
            "(cargo-audit may generate/locate Cargo.lock)"
        ).strip(" —")[:4000]
    return findings, [row]


def _run_cargo_audit_group(workdir, item_type, target):
    """Cargo Audit group — RustSec SCA for skill/mcp/package when Cargo present."""
    findings, rows = run_cargo_audit(workdir, item_type)
    return findings, rows, None


# ---- Ossprey (malicious-package / malware detection) ------------------------
# RESEARCH-grade adapter (ADR-0005): the shape below is taken from ossprey.com
# and the OSSPREY GitHub org docs, NOT round-tripped against a live ossprey-cli.
# The OSSBOM JSON schema and the malware-verdict wording are UNVERIFIED —
# reconcile against the pinned CLI version's --help / --json before this blocks a
# merge; it cannot claim VERIFIED. Ossprey detects MALICIOUS code (static +
# behavioural) in open-source packages — distinct from DepShield's dependency-CVE
# audit.
#
# Runtime state TODAY: access provisioning is OPEN (no ospy_ key in this
# environment, repo marks slice 35 BLOCKED), so the credential gate is the first
# branch and the default path is skipped_missing_credential. The adapter becomes
# active the moment a key is supplied.
#
# Exit-code contract (docs): 0 = clean/skipped, 1 = malware OR scan failure. The
# adapter MUST disambiguate — a finding is emitted only on a POSITIVE malware
# signal (a malicious OSSBOM entry, or an unambiguous verdict line). exit 1 with
# no such signal is a scan failure → unreachable, never a phantom red finding.
# Tail budget: DEPSHIELD_TIMEOUT + CARGO_AUDIT_TIMEOUT + PRESEND_TIMEOUT +
# OSSPREY_TIMEOUT must stay <= SCAN_TIMEOUT; see scripts/check-scanner-timeout-budget.sh and
# docs/ARCHITECTURE.md.
OSSPREY_TIMEOUT = 70  # was 90; 20s moved to PRESEND_TIMEOUT (issue #143)

# RESEARCH: verdict wording UNVERIFIED. Match malware/malicious lines but skip
# known clean-summary phrases only — never bare "not"/"clean" (false negatives).
_OSSPREY_CLEAN_SUMMARY_RES = (
    re.compile(r"\bno\s+mal(?:ware|icious)\b"),
    re.compile(r"\bnot\s+mal(?:ware|icious)\b"),
    re.compile(r"\bzero\s+mal(?:ware|icious)\b"),
    re.compile(r"\bnone\s+mal(?:ware|icious)\b"),
    re.compile(r"\b0\s+mal(?:ware|icious)\b"),
    re.compile(r"\bclean\s+(?:scan|result)\b"),
)
_OSSPREY_MALICIOUS_VERDICTS = ("malicious", "malware")


def _ossprey_component_is_malicious(comp):
    """True when an OSSBOM component carries a positive malicious signal.

    RESEARCH — the flag key is UNVERIFIED, so several plausible shapes are
    tolerated: a boolean ``malicious``/``malware`` flag, or a verdict / status /
    classification / result string equal to 'malicious' or 'malware'.
    """
    if comp.get("malicious") is True or comp.get("malware") is True:
        return True
    for key in ("verdict", "status", "classification", "result"):
        val = comp.get(key)
        if isinstance(val, str) and val.strip().lower() in _OSSPREY_MALICIOUS_VERDICTS:
            return True
    return False


def _ossprey_finding(comp):
    """Build a red 'malware' finding row from a malicious OSSBOM component."""
    name = comp.get("name") or comp.get("package") or comp.get("package_name")
    version = comp.get("version") or comp.get("package_version")
    verdict = comp.get("verdict") or comp.get("classification") or comp.get("status") or "malicious"
    label = f"{name}@{version}" if name and version else (name or "package")
    return {
        "severity": "red",  # malware is always red
        "category": "malware",
        "message": f"{label}: {verdict}",
        "scanner_source": "Ossprey",
        "package_name": name,
        "package_version": version,
    }


def _parse_ossprey_ossbom(json_obj):
    """Parse an OSSBOM object → ``(malware_findings, package_count)``.

    RESEARCH — the OSSBOM schema is UNVERIFIED and needs live reconciliation.
    Tolerates both a bare list of components and a ``{"components": [...]}`` (or
    ``{"packages": [...]}``) envelope, with defensive ``.get()`` throughout. A
    finding is emitted only for a component flagged malicious.
    """
    if isinstance(json_obj, list):
        components = json_obj
    elif isinstance(json_obj, dict):
        components = json_obj.get("components") or json_obj.get("packages") or []
    else:
        components = []
    if not isinstance(components, list):
        components = []
    findings = [
        _ossprey_finding(c)
        for c in components
        if isinstance(c, dict) and _ossprey_component_is_malicious(c)
    ]
    return findings, len(components)


def _ossprey_malware_verdict_line(text):
    """First unambiguous malware/malicious verdict line in stdout, else None.

    RESEARCH — wording UNVERIFIED. Negated lines ('no malicious packages',
    'clean') are skipped so a clean-scan summary is never a phantom positive.
    """
    for line in (text or "").splitlines():
        low = line.lower()
        if "malware" not in low and "malicious" not in low:
            continue
        if any(p.search(low) for p in _OSSPREY_CLEAN_SUMMARY_RES):
            continue
        return line.strip()[:200]
    return None


def _read_ossprey_ossbom(path):
    """Read + JSON-parse the OSSBOM file written by ``-o``; None if absent/bad."""
    try:
        with open(path, encoding="utf-8") as fh:
            return _safe_json(fh.read())
    except OSError:
        return None


# Ossprey catalogues Python + JavaScript only (vendor README). Markers below
# drive operator-facing detail and not_applicable when the tree has nothing
# Ossprey can turn into an SBOM.
_OSSPREY_SUPPORTED_MARKERS = frozenset(
    {
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "requirements.txt",
        "Pipfile",
        "Pipfile.lock",
        "poetry.lock",
        "pyproject.toml",
    }
)
_OSSPREY_UNSUPPORTED_LABELS = (
    ("Cargo.toml", "Rust/Cargo"),
    ("Cargo.lock", "Rust/Cargo"),
    ("go.mod", "Go"),
    ("go.sum", "Go"),
)
_OSSPREY_NO_SBOM_RE = re.compile(r"no\s+sbom", re.IGNORECASE)
_OSSPREY_TIMEOUT_RE = re.compile(r"timeout after\s+(\d+)s", re.IGNORECASE)


def _ossprey_detect_ecosystems(workdir):
    """Return ``(supported_names, unsupported_labels)`` found under *workdir*."""
    supported = set()
    unsupported = set()
    if not workdir or not os.path.isdir(workdir):
        return (), ()
    for root, dirnames, filenames in os.walk(workdir):
        dirnames[:] = sorted(d for d in dirnames if d not in _DEPSHIELD_SKIP_DIRS)
        for name in filenames:
            if name in _OSSPREY_SUPPORTED_MARKERS:
                supported.add(name)
            for marker, label in _OSSPREY_UNSUPPORTED_LABELS:
                if name == marker:
                    unsupported.add(label)
    return tuple(sorted(supported)), tuple(sorted(unsupported))


def _ossprey_raw_failure_text(out, err, code):
    return (err or out or (f"exit {code}" if code is not None else "scan failed")).strip()


def _ossprey_is_no_sbom_failure(raw):
    return bool(_OSSPREY_NO_SBOM_RE.search(raw or ""))


def _ossprey_timeout_seconds(raw):
    match = _OSSPREY_TIMEOUT_RE.search(raw or "")
    return int(match.group(1)) if match else None


def _ossprey_ecosystem_hint(supported, unsupported):
    if unsupported and not supported:
        labels = ", ".join(unsupported)
        return (
            f"This workdir looks {labels}-only — Ossprey catalogues Python and "
            "JavaScript manifests only (package.json / requirements / pyproject / locks)."
        )
    if unsupported and supported:
        return (
            f"Also found unsupported markers ({', '.join(unsupported)}); "
            "Ossprey ignores those ecosystems."
        )
    if not supported and not unsupported:
        return (
            "No Python/JavaScript manifests found for Ossprey to catalogue "
            "(needs package.json / requirements / pyproject / locks)."
        )
    return f"Detected catalogueable manifests: {', '.join(supported)}."


def _ossprey_operator_failure(raw, workdir):
    """Map raw CLI/API failure text → ``(status, detail)`` for operators.

    ``not_applicable`` when Ossprey reports no SBOM and the tree has no
    catalogueable Python/JS manifests (Cargo/Go-only or empty). Timeouts and
    other failures stay ``unreachable`` with a plain-language lead-in.
    """
    supported, unsupported = _ossprey_detect_ecosystems(workdir)
    hint = _ossprey_ecosystem_hint(supported, unsupported)
    seconds = _ossprey_timeout_seconds(raw)
    if seconds is not None:
        detail = (
            f"Ossprey timed out after {seconds}s while cataloguing or submitting "
            f"the SBOM (OSSPREY_TIMEOUT={OSSPREY_TIMEOUT}). Large npm/Python trees "
            f"often need a longer budget. {hint}"
        )
        return "unreachable", detail
    if _ossprey_is_no_sbom_failure(raw):
        detail = (
            "Ossprey produced no SBOM — it only catalogues Python and JavaScript "
            f"dependency manifests. {hint}"
        )
        if not supported:
            return "not_applicable", detail
        return "unreachable", detail
    lead = "Ossprey scan failed."
    clipped = (raw or "").strip()
    if clipped:
        lead = f"{lead} Vendor detail: {clipped[:500]}"
    return "unreachable", f"{lead} {hint}".strip()


def _ossprey_verdict(source, code, out, err, findings, n_packages, console, workdir=""):
    """Disambiguate the exit code (0 = clean, 1 = malware OR failure) into a row.

    exit 0 → completed clean (the exit code is authoritative; parsed findings are
    surfaced only when the nonzero exit corroborates them). Nonzero with a
    positive malware signal → completed with the red finding(s). Nonzero with no
    signal → unreachable or not_applicable (operator-facing detail), never a
    phantom finding.
    """
    checks = n_packages or 1
    if code == 0:
        return [], [_completed(source, checks, [], console_output=console)]
    if not findings:
        verdict_line = _ossprey_malware_verdict_line(out)
        if verdict_line:
            findings = [
                {
                    "severity": "red",
                    "category": "malware",
                    "message": verdict_line,
                    "scanner_source": source,
                }
            ]
    if findings:
        return findings, [_completed(source, checks, findings, console_output=console)]
    raw = _ossprey_raw_failure_text(out, err, code)
    status, detail = _ossprey_operator_failure(raw, workdir)
    if status == "not_applicable":
        return [], [_skipped(source, "not_applicable", detail=detail, console_output=console)]
    return [], [_unreachable(source, detail, console_output=console)]


def run_ossprey(workdir, item_type="mcp_server"):
    """Scan *workdir* for malicious / malware packages via the ossprey CLI.

    Credential-gated: skipped_missing_credential is the default runtime path
    today because Ossprey access provisioning is OPEN (no key). *item_type* does
    not change behavior — the same manifests/lockfiles are scanned for skills and
    MCP servers.
    """
    source = "Ossprey"
    # Credential gate FIRST — the actual runtime state today (no ospy_ key).
    # Tripwire accepts OSSPREY_API_KEY only (not generic API_KEY) until the
    # vendor contract is VERIFIED — avoids accidental activation from unrelated keys.
    if not os.environ.get("OSSPREY_API_KEY"):
        return [], [
            _skipped(
                source,
                "skipped_missing_credential",
                detail=(
                    "OSSPREY_API_KEY not set — Ossprey access provisioning is OPEN "
                    "(set OSSPREY_API_KEY when access lands; generic API_KEY is ignored)"
                ),
            )
        ]
    if not _which("ossprey"):
        return [], [_unreachable(source, "ossprey CLI not installed in image")]

    # OSSBOM is written to a temp file via -o; cleaned up in finally regardless.
    fd, ossbom_path = tempfile.mkstemp(prefix="ossprey-", suffix=".json")
    os.close(fd)
    try:
        code, out, err = _run(
            ["ossprey", "scan", workdir, "-o", ossbom_path], timeout=OSSPREY_TIMEOUT
        )
        console = _build_console(out, err)
        findings, n_packages = _parse_ossprey_ossbom(_read_ossprey_ossbom(ossbom_path))
    finally:
        try:
            os.remove(ossbom_path)
        except OSError:
            pass

    return _ossprey_verdict(source, code, out, err, findings, n_packages, console, workdir=workdir)


def _collapse_severity(raw):
    if not raw:
        return None
    r = raw.upper()
    if r in ("CRITICAL", "HIGH"):
        return "red"
    # MEDIUM and LOW are actionable vulns → amber. INFO soft-findings → green.
    # Aggregate "green" (no vuln) is absence of red/amber findings, not a LOW row.
    if r in ("MEDIUM", "LOW"):
        return "amber"
    if r in ("INFO", "INFORMATIONAL"):
        return "green"
    return None  # SAFE / empty — no finding row


SKILL_SCANNER_SOURCES = [
    "Cisco Skill Scanner: static/bytecode/pipeline",
    "Cisco Skill Scanner: LLM-judge",
    "Cisco Skill Scanner: AI Defense",
]

MCP_SCANNER_SOURCES = list(_MCP_ANALYZER_LABEL.values())

TESSL_SOURCES = [
    "Tessl: Lint",
    "Tessl: Review (Quality)",
    "Tessl: Scenario Generation",
    "Tessl: Eval",
    "Tessl: Review (Security)",
]
SNYK_SOURCES = ["Snyk"]
DEPSHIELD_SOURCES = ["DepShield"]
OSSPREY_SOURCES = ["Ossprey"]


# ---- Scanner group registry --------------------------------------------------
# Pluggability seam for new subprocess adapters (ADR-0005 contract): a scanner
# joins the orchestration by appending a group entry to SCANNER_GROUPS — no
# edits to run_all_scanners. Each group runner normalizes its adapter's return
# shape to ``(findings, rows, quality_score)``; adapters that don't produce a
# quality axis return ``None`` for the third slot, and quality-only adapters
# (Tessl) return ``[]`` findings.


def _run_skill_scanner_group(workdir, item_type, target):
    """Cisco Skill Scanner group — (findings, rows) adapter, no quality axis."""
    findings, rows = run_cisco_skill_scanner(workdir)
    return findings, rows, None


def _run_tessl_group(
    workdir,
    item_type,
    target,
    *,
    resume_checkpoint: dict | None = None,
    prior_eval: dict | None = None,
    on_row_progress=None,
):
    """Tessl group — quality axis only: (quality_score, rows), never findings."""
    quality_score, rows = run_tessl(
        workdir,
        resume_checkpoint=resume_checkpoint,
        prior_eval=prior_eval,
        on_row_progress=on_row_progress,
    )
    return [], rows, quality_score


def _run_mcp_scanner_group(workdir, item_type, target):
    """Cisco MCP Scanner group — the only runner that consumes *target*."""
    findings, rows = run_cisco_mcp_scanner(workdir, target)
    return findings, rows, None


def _run_snyk_group(workdir, item_type, target):
    """Snyk group — runs for every item type; CLI flags vary per *item_type*."""
    findings, rows = run_snyk(workdir, item_type)
    return findings, rows, None


def _run_depshield_group(workdir, item_type, target):
    """DepShield group — dependency audit for both item types, no quality axis."""
    findings, rows = run_depshield(workdir, item_type)
    return findings, rows, None


def _run_ossprey_group(workdir, item_type, target):
    """Ossprey group — malicious-package detection for both item types, no quality axis."""
    findings, rows = run_ossprey(workdir, item_type)
    return findings, rows, None


# ---- Presend (typosquat + maintainer-change signals) ------------------------
# Opt-in adapter (issue #143). Unlike the CLI adapters above it calls a hosted
# HTTP API in-process (see the ADR-0005 note in scanner-output-adapters.md):
# manifests are read locally and only dependency NAMES are sent, never file
# contents, versions or paths. Disabled unless PRESEND_API_URL is set, so no
# name leaves the sandbox without an explicit operator decision. Both checks
# are heuristics for manual review, so findings are amber only. Fail closed
# (ADR-0009): any batch, package or manifest error -> unreachable, findings
# from the batches that did complete are kept.
PRESEND_TIMEOUT = 20  # wall clock for the whole group (tail budget)
PRESEND_REQUEST_TIMEOUT = 10
PRESEND_MAX_PACKAGES = 100  # per ecosystem; truncation is surfaced in detail
PRESEND_MAINTAINER_BATCH = 20  # server-side cap of maintainer-change-check
PRESEND_MAX_RESPONSE_BYTES = 2_000_000
# Cloudflare rejects urllib's default User-Agent (HTTP 403, error 1010).
PRESEND_USER_AGENT = "tripwire-presend-adapter"
PRESEND_SOURCES = ["Presend"]
_PRESEND_NPM_DEP_KEYS = (
    "dependencies",
    "optionalDependencies",
    "peerDependencies",
    "devDependencies",
)
# Specs that do not resolve to a registry package under that name.
_PRESEND_SKIP_SPEC_PREFIXES = (
    "file:",
    "link:",
    "workspace:",
    "portal:",
    "npm:",
    "git:",
    "git+",
    "github:",
    "http:",
    "https:",
)
_PRESEND_PYPI_NAME_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")
_PRESEND_REGISTRY_URL = {
    "npm": "https://www.npmjs.com/package/{}",
    "PyPI": "https://pypi.org/project/{}/",
}


class _PresendError(Exception):
    """One Presend batch could not be completed."""


def _presend_base_url():
    """PRESEND_API_URL -> (base_url, error). Unset -> (None, None)."""
    raw = (os.environ.get("PRESEND_API_URL") or "").strip()
    if not raw:
        return None, None
    if urllib.parse.urlsplit(raw).scheme not in ("http", "https"):
        return None, "PRESEND_API_URL must be an http(s) URL"
    return raw.rstrip("/"), None


def _presend_npm_names(text):
    """Registry dependency names from package.json (runtime first); None if invalid."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    names = []
    for key in _PRESEND_NPM_DEP_KEYS:
        deps = data.get(key)
        if not isinstance(deps, dict):
            continue
        for name, spec in deps.items():
            if isinstance(spec, str) and spec.startswith(_PRESEND_SKIP_SPEC_PREFIXES):
                continue
            names.append(name)
    return names


def _presend_pypi_names(text):
    """Project names from requirements.txt; options, URLs and paths are skipped."""
    names = []
    for raw in text.splitlines():
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith(("#", "-")) or "://" in line or " @ " in line:
            continue
        match = _PRESEND_PYPI_NAME_RE.match(line)
        if match:
            names.append(match.group(1))
    return names


def _presend_collect(workdir, manifests):
    """-> ({ecosystem: {name: manifest_relpath}}, errors); first manifest wins."""
    found = {"npm": {}, "PyPI": {}}
    errors = []
    for manifest in manifests:
        try:
            with open(os.path.join(workdir, manifest), encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, ValueError) as exc:
            errors.append(f"{manifest}: unreadable ({exc})")
            continue
        if os.path.basename(manifest) == "package.json":
            ecosystem, names = "npm", _presend_npm_names(text)
        else:
            ecosystem, names = "PyPI", _presend_pypi_names(text)
        if names is None:
            errors.append(f"{manifest}: invalid package.json")
            continue
        for name in names:
            found[ecosystem].setdefault(name, manifest)
    return found, errors


def _presend_post(base_url, endpoint, payload, deadline):
    """POST one batch; -> results list. Raises _PresendError, never anything else."""
    remaining = deadline - time.monotonic()
    if remaining < 1:
        raise _PresendError(f"{endpoint}: {PRESEND_TIMEOUT}s budget exhausted")
    request = urllib.request.Request(
        f"{base_url}/api/{endpoint}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": PRESEND_USER_AGENT},
        method="POST",
    )
    try:
        # Scheme restricted to http(s) by _presend_base_url.
        with urllib.request.urlopen(  # nosec B310
            request, timeout=min(PRESEND_REQUEST_TIMEOUT, remaining)
        ) as response:
            body = response.read(PRESEND_MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise _PresendError(f"{endpoint}: HTTP {exc.code}") from exc
    except (OSError, ValueError) as exc:
        raise _PresendError(f"{endpoint}: {exc}") from exc
    if len(body) > PRESEND_MAX_RESPONSE_BYTES:
        raise _PresendError(f"{endpoint}: response too large")
    try:
        parsed = json.loads(body)
    except ValueError as exc:
        raise _PresendError(f"{endpoint}: malformed JSON") from exc
    results = parsed.get("results") if isinstance(parsed, dict) else None
    if not isinstance(results, list) or len(results) != len(payload["packages"]):
        raise _PresendError(f"{endpoint}: unexpected response shape")
    return results


def _presend_finding(category, message, package, version, manifest, ecosystem):
    return {
        "severity": "amber",
        "category": category,
        "message": message,
        "scanner_source": "Presend",
        "file_path": manifest,
        "package_name": package,
        "package_version": version,
        "cve_ids": [],
        "advisory_url": _PRESEND_REGISTRY_URL[ecosystem].format(package),
        "advisory_provider": "presend",
    }


def _presend_typosquat_findings(result, ecosystem, manifest):
    if result.get("suspicious") is not True:
        return []
    package = str(result.get("package") or "unknown")
    similar = ", ".join(
        str(s.get("name")) for s in result.get("similar_to") or [] if isinstance(s, dict)
    )
    message = (
        f"{package}: name is close to popular {ecosystem} package(s) "
        f"{similar or 'on the curated list'}; confirm it is the intended dependency"
    )
    return [_presend_finding("dependency_typosquat", message, package, None, manifest, ecosystem)]


def _presend_maintainer_findings(result, ecosystem, manifest):
    package = str(result.get("package") or "unknown")
    findings = []
    for event in result.get("flagged_events") or []:
        if not isinstance(event, dict):
            continue
        version = event.get("version")
        message = (
            f"{package}@{version or '?'}: published by new publisher "
            f"{event.get('publisher', '?')} after {event.get('dormancy_days', '?')} days "
            f"without releases (previous: {event.get('previous_publisher', '?')}); "
            "review before upgrading"
        )
        if event.get("publisher_check") == "unavailable":
            message += " (publisher history lookup unavailable)"
        findings.append(
            _presend_finding(
                "dependency_maintainer_change",
                message,
                package,
                str(version) if version else None,
                manifest,
                ecosystem,
            )
        )
    return findings


def _presend_batches(ecosystem, names):
    batches = [("typosquat-check", names)]
    if ecosystem == "npm":  # maintainer-change-check is npm-only
        for start in range(0, len(names), PRESEND_MAINTAINER_BATCH):
            batches.append(
                ("maintainer-change-check", names[start : start + PRESEND_MAINTAINER_BATCH])
            )
    return batches


def _presend_run_batches(base_url, deadline, ecosystem, packages):
    """*packages*: {name: manifest}. -> (findings, checks, errors); never raises."""
    findings, checks, errors = [], 0, []
    fallback_manifest = next(iter(packages.values()))
    for endpoint, batch in _presend_batches(ecosystem, list(packages)):
        payload = {"ecosystem": ecosystem, "packages": batch}
        try:
            results = _presend_post(base_url, endpoint, payload, deadline)
        except _PresendError as exc:
            errors.append(f"{ecosystem} {exc}")
            continue
        for result in results:
            if not isinstance(result, dict) or result.get("error"):
                errors.append(f"{ecosystem} {endpoint}: {result}"[:300])
                continue
            checks += 1
            # typosquat-check may return the PEP 503 normalized PyPI name.
            manifest = packages.get(str(result.get("package")), fallback_manifest)
            if endpoint == "typosquat-check":
                findings += _presend_typosquat_findings(result, ecosystem, manifest)
            else:
                findings += _presend_maintainer_findings(result, ecosystem, manifest)
    return findings, checks, errors


def _presend_check_all(base_url, packages):
    """-> (findings, checks, errors, notes) across ecosystems; never raises."""
    deadline = time.monotonic() + PRESEND_TIMEOUT
    findings, checks, errors, notes = [], 0, [], []
    for ecosystem, found in packages.items():
        if not found:
            continue
        names = list(found)
        if len(names) > PRESEND_MAX_PACKAGES:
            notes.append(
                f"{ecosystem}: first {PRESEND_MAX_PACKAGES} of {len(names)} "
                "dependencies checked (runtime dependencies first)"
            )
        subset = {name: found[name] for name in names[:PRESEND_MAX_PACKAGES]}
        f, c, e = _presend_run_batches(base_url, deadline, ecosystem, subset)
        findings += f
        checks += c
        errors += e
    return findings, checks, errors, notes


def run_presend(workdir, item_type="package"):
    """Typosquat (npm, PyPI) and maintainer-change (npm) signals via Presend.

    *item_type* does not change behaviour; N/A when no npm/PyPI manifest exists.
    """
    source = "Presend"
    base_url, url_error = _presend_base_url()
    if url_error:
        return [], [_unreachable(source, url_error)]
    if base_url is None:
        return [], [
            _skipped(
                source,
                detail=(
                    "PRESEND_API_URL not set: opt-in adapter "
                    "(sends dependency names to a hosted API)"
                ),
            )
        ]
    manifests, total = _find_manifests(workdir)
    if not manifests:
        return [], [
            _skipped(
                source, "not_applicable", detail="no package.json / requirements.txt in workdir"
            )
        ]
    packages, errors = _presend_collect(workdir, manifests)
    findings, checks, batch_errors, notes = _presend_check_all(base_url, packages)
    errors += batch_errors
    if total > len(manifests):
        notes.append(f"first {len(manifests)} of {total} manifests read")
    if errors:
        return findings, [_unreachable(source, "; ".join(errors + notes))]
    if checks == 0:
        return [], [
            _skipped(source, "not_applicable", detail="manifests list no registry dependencies")
        ]
    row = _completed(source, checks, findings)
    if notes:
        row["detail"] = f"{row.get('detail', '')} — {'; '.join(notes)}"[:4000]
    return findings, [row]


def _run_presend_group(workdir, item_type, target):
    """Presend group — opt-in typosquat / maintainer-change signals, no quality axis."""
    findings, rows = run_presend(workdir, item_type)
    return findings, rows, None


# Ordered: skill-only groups (Cisco Skill Scanner, then Tessl), the mcp-only
# group (Cisco MCP Scanner), then both-type groups (Snyk, DepShield, Cargo Audit,
# Presend — opt-in via PRESEND_API_URL, the only in-process HTTP adapter, then
# Ossprey last — the RESEARCH-grade malicious-package adapter, credential-gated).
SCANNER_GROUPS = [
    {"sources": SKILL_SCANNER_SOURCES, "applies_to": "skill", "runner": _run_skill_scanner_group},
    {"sources": TESSL_SOURCES, "applies_to": "skill", "runner": _run_tessl_group},
    {"sources": MCP_SCANNER_SOURCES, "applies_to": "mcp_server", "runner": _run_mcp_scanner_group},
    {"sources": SNYK_SOURCES, "applies_to": "both", "runner": _run_snyk_group},
    {"sources": DEPSHIELD_SOURCES, "applies_to": "both", "runner": _run_depshield_group},
    {"sources": CARGO_AUDIT_SOURCES, "applies_to": "both", "runner": _run_cargo_audit_group},
    {"sources": PRESEND_SOURCES, "applies_to": "both", "runner": _run_presend_group},
    {"sources": OSSPREY_SOURCES, "applies_to": "both", "runner": _run_ossprey_group},
]


# Types that inherit ``applies_to: "both"`` groups (Snyk / DepShield / Cargo Audit /
# Presend / Ossprey).
_BOTH_ITEM_TYPES = frozenset({"skill", "mcp_server", "package"})


def _group_applies(applies_to, item_type):
    """True when a registry group should run for *item_type*.

    ``'both'`` → skill, mcp_server, and package (slice 64).
    ``'skill'`` / ``'mcp_server'`` / ``'package'`` → exact match only — MCP-only
    groups must not run on package targets.
    """
    if applies_to == "both":
        return item_type in _BOTH_ITEM_TYPES
    if applies_to == "skill":
        return item_type == "skill"
    if applies_to == "mcp_server":
        return item_type == "mcp_server"
    if applies_to == "package":
        return item_type == "package"
    return False


def run_all_scanners(
    workdir,
    item_type,
    target,
    on_scanner_done=None,
    on_scanner_start=None,
    on_scanner_progress=None,
    tessl_scenario_resume=None,
    tessl_prior_eval=None,
):
    """Run every applicable SCANNER_GROUPS entry, optionally relaying results.

    When *on_scanner_start* is provided it is called before each scanner group
    with the list of scanner_source names about to run.  This lets the caller
    insert ``status='running'`` placeholder rows so the dashboard has something
    to display immediately (within one poll cycle).

    When *on_scanner_done* is provided it is called after each scanner group
    finishes with ``(findings, scanner_rows, quality_score)``.  This lets the
    caller (scan_app) persist rows/findings to Supabase as they arrive so the
    dashboard shows progress scanner-by-scanner.

    When *on_scanner_progress* is provided it receives mid-group Tessl row
    updates (e.g. Scenario Generation ``resume_checkpoint``, Eval
    ``blocked``→``queued``→``running``) for partial persist.
    *tessl_scenario_resume* rehydrates Scenario Generation after Modal timeout.
    *tessl_prior_eval* rehydrates Eval for stale detection or eval-view resume.
    """
    findings, scanner_rows = [], []
    quality_score = None

    for group in SCANNER_GROUPS:
        if not _group_applies(group["applies_to"], item_type):
            continue
        if on_scanner_start:
            on_scanner_start(group["sources"])
        if group["runner"] is _run_tessl_group:
            f, r, qs = _run_tessl_group(
                workdir,
                item_type,
                target,
                resume_checkpoint=tessl_scenario_resume,
                prior_eval=tessl_prior_eval,
                on_row_progress=on_scanner_progress,
            )
        else:
            f, r, qs = group["runner"](workdir, item_type, target)
        findings += f
        scanner_rows += r
        if qs is not None:
            quality_score = qs
        if on_scanner_done:
            on_scanner_done(f, r, qs)

    any_unreachable = any(row["status"] == "unreachable" for row in scanner_rows)
    overall_status = "partial-failed" if any_unreachable else "complete"

    return {
        "findings": findings,
        "scanner_rows": scanner_rows,
        "quality_score": quality_score,
        "overall_status": overall_status,
    }
