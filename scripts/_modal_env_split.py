#!/usr/bin/env python3
"""Split a Tripwire .env into filtered dotenv files for Modal secret sync.

Writes two files and prints a JSON summary of key *names* only (never values)
to stdout:

  {
    "supabase_path": "...",
    "scan_path": "...",
    "supabase_keys": ["SUPABASE_URL", ...],
    "scan_keys": ["SNYK_TOKEN", ...]
  }

Exit 1 if SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are missing or blank.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SUPABASE_KEYS = (
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
)

SCAN_KEYS = (
    "SNYK_TOKEN",
    "TESSL_TOKEN",
    "TESSL_WORKSPACE",
    "SKILL_SCANNER_LLM_API_KEY",
    "SKILL_SCANNER_LLM_MODEL",
    "SKILL_SCANNER_LLM_PROVIDER",
    "SKILL_SCANNER_LLM_BASE_URL",
    "SKILL_SCANNER_LLM_API_VERSION",
    "MCP_SCANNER_LLM_API_KEY",
    "MCP_SCANNER_LLM_MODEL",
    "MCP_SCANNER_LLM_BASE_URL",
    "MCP_SCANNER_LLM_API_VERSION",
    "AI_DEFENSE_API_KEY",
    "AI_DEFENSE_API_URL",
    "MCP_SCANNER_API_KEY",
    "MCP_SCANNER_ENDPOINT",
    "OSSPREY_API_KEY",
    "PRESEND_API_URL",
)


def parse_dotenv(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines; ignore comments/blank; last wins; no expansion."""
    result: dict[str, str] = {}
    text = path.read_text(encoding="utf-8")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        result[key] = value
    return result


def pick_nonempty(env: dict[str, str], keys: tuple[str, ...]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in keys:
        value = env.get(key, "")
        if value.strip():
            out[key] = value
    return out


def write_dotenv(path: Path, pairs: dict[str, str]) -> None:
    lines = [f"{k}={v}" for k, v in pairs.items()]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    path.chmod(0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True, type=Path)
    parser.add_argument("--supabase-out", required=True, type=Path)
    parser.add_argument("--scan-out", required=True, type=Path)
    args = parser.parse_args()

    if not args.env_file.is_file():
        print(f"error: env file not found: {args.env_file}", file=sys.stderr)
        return 1

    env = parse_dotenv(args.env_file)
    supabase = pick_nonempty(env, SUPABASE_KEYS)
    missing = [k for k in SUPABASE_KEYS if k not in supabase]
    if missing:
        print(
            "error: required Supabase keys missing or empty: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 1

    scan = pick_nonempty(env, SCAN_KEYS)

    write_dotenv(args.supabase_out, supabase)
    write_dotenv(args.scan_out, scan)

    summary = {
        "supabase_path": str(args.supabase_out),
        "scan_path": str(args.scan_out),
        "supabase_keys": list(supabase.keys()),
        "scan_keys": list(scan.keys()),
    }
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
