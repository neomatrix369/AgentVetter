# Contributing

This is the contributor path for people who use AgentVetter and also develop, test,
or share improvements. Complete the shared [QUICKSTART.md](QUICKSTART.md) flow
before following these development instructions.

[![Cursor](https://img.shields.io/badge/Cursor-000000?style=flat)](https://cursor.com)
[![Modal](https://img.shields.io/badge/Modal-7C5CFF?style=flat)](https://modal.com)
[![Supabase](https://img.shields.io/badge/Supabase-3ECF8E?style=flat&logo=supabase&logoColor=white)](https://supabase.com)
[![AgentVetter](https://img.shields.io/badge/AgentVetter-1a1a2e?style=flat)](https://github.com/neomatrix369/AgentVetter)
[![Cisco](https://img.shields.io/badge/Cisco-1BA0D7?style=flat)](https://developer.cisco.com)
[![Snyk](https://img.shields.io/badge/Snyk-4C4A73?style=flat&logo=snyk&logoColor=white)](https://snyk.io)
[![Tessl](https://img.shields.io/badge/Tessl-111111?style=flat)](https://tessl.io)
[![DepShield](https://img.shields.io/badge/DepShield-2F6F4E?style=flat)](https://www.npmjs.com/package/depshield-mcp)
[![Ossprey](https://img.shields.io/badge/Ossprey-1A1A2E?style=flat)](https://ossprey.com)

[![Test coverage](https://img.shields.io/badge/Test_coverage-enforced-2ea44f)](#dev-hygiene)
[![Static analysis](https://img.shields.io/badge/Static_analysis-enforced-0969da)](#dev-hygiene)
[![Security scanning](https://img.shields.io/badge/Security_scanning-active-8250df)](#dev-hygiene)
[![Complexity checks](https://img.shields.io/badge/Complexity-checks-9a6700)](#dev-hygiene)
[![Git hooks](https://img.shields.io/badge/Git_hooks-available-57606a)](#dev-hygiene)

## Dev setup

0. Tools + versions: [docs/user-guide/prerequisites.md](docs/user-guide/prerequisites.md)
   (Node 22 / npm / Python 3.12). Live capabilities require provisioning and
   setting up platform vendors before copying `.env` (scanners optional):
   [supabase-setup](docs/user-guide/supabase-setup.md) →
   [modal-setup](docs/user-guide/modal-setup.md) →
   [Snyk procurement](docs/user-guide/env-vars.md#vendor-procurement-quick-steps) →
   [Tessl procurement](docs/user-guide/env-vars.md#vendor-procurement-quick-steps) →
   [Cisco AI Defense procurement](docs/user-guide/env-vars.md#vendor-procurement-quick-steps)
   (DepShield: no keys; Ossprey: `OSSPREY_API_KEY` when access available).
   Use [env-vars](docs/user-guide/env-vars.md) to collect the resulting values,
   then copy and populate `.env`.

Then use this guide for development, quality checks, and sharing changes back. Short version:

1. Copy `.env.example` → `.env` using [env-vars.md](docs/user-guide/env-vars.md)
   (`fixtures/OPTIONAL_SCANNER_KEYS.md` for Modal allowlist).
2. `cd cli && npm install && npm link`
3. `agentvetter setup` (needs `SUPABASE_DB_URL`) and `./scripts/setup-modal.sh`
4. Run checks below.

Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Decisions:
[docs/adr/README.md](docs/adr/README.md). Scanner output notes:
[docs/research/adapters/scanner-output-adapters.md](docs/research/adapters/scanner-output-adapters.md).
Claude Code hooks / `/av-*` skills (aliases `/tw-*`): [agent-hooks/README.md](agent-hooks/README.md).

## Dev hygiene

```bash
./scripts/install-git-hooks.sh      # pre-commit + pre-push
pre-commit run --all-files          # lint, mypy, bandit, xenon, vulture, pylint-duplication, eslint-cli, eslint-dashboard, gitleaks, fast tests
./scripts/quality-gates.sh --quick  # T1 static analysis only
./scripts/quality-gates.sh          # T1 + coverage + cli tests + pip-audit
./scripts/quality-gates.sh --full   # above + scripts/security-scan.sh
./scripts/pip-audit.sh              # Python dep audit with project-specific ignores
```

- **Commit:** ruff, mypy, bandit, xenon (complexity; split C/D ceiling), vulture (dead code), pylint duplicate-code, gitleaks, pytest-testmon (`sandbox/tests/`); `cli` ESLint + unit tests when `cli/` JS files staged; `prototypes/dc-dashboard` ESLint when dashboard JS files staged
- **Push:** full pytest + coverage floor (when Python changed); `cli` unit tests + coverage (c8 ≥60% lines, 80% branches) when `cli/` changed; conditional `pip-audit --skip-editable` / npm audit;
  T3 gitleaks commit-range scan (only pushed commits, fast) runs warn-only —
  findings print but do not block the push; heavy SAST/SCA runs on Nightly **A** /
  Supply chain **B** (PR CI stays ultra-minimal — see below)
- **CI** (`.github/workflows/ci.yml`, ultra-minimal): lint · static · ship-path
  coverage · OSV · Trivy (targeted) · gitleaks incremental · TruffleHog
  incremental. Semgrep / CodeQL / Meterian / dashboard tests deferred off PR.
- **T4 cloud cadences** (A/B/C split 2026-09-09; A expanded 2026-09-11, USER-CONFIRMED):

  | WF | File | Cadence | Jobs |
  |---|---|---|---|
  | **A** | `nightly.yml` | daily **02:00 UTC** (`0 2 * * *`) + dispatch | Semgrep · CodeQL · full secrets/Trivy · dashboard tests · cov snapshots · complexity · dep audit |
  | **B** | `supply-chain.yml` | weekly **Mon 03:00 UTC** (`0 3 * * 1`) + dispatch | SBOM + Trivy license · Meterian strict 95/95 · Chalk (warn-only ⚠) |
  | **C** | `mutation.yml` | **1st+15th 04:00 UTC** (`0 4 1,15 * *`) + dispatch | Stryker (CLI) · advisory mutmut (Python); **non-gating** (`break: 0`) |

**Coverage today (VERIFIED config):** Python `sandbox/` `fail_under=95` via
`pytest` / `testpaths = ["sandbox/tests"]` (guard omitted); CLI
`npm run test:coverage` ≥60% lines / 80% branches (cli/package.json); Live ACL
`prototypes/dc-dashboard` `npm run test:coverage` ≥95% lines on the four ACL
modules (`support.js` out of bar). Local editable `agentvetter` is skipped by
`pip-audit --skip-editable` (not a PyPI package). Track
[docs/plan/PROGRESS.md](docs/plan/PROGRESS.md); close per
[docs/plan/GATE_CONTRACT.md](docs/plan/GATE_CONTRACT.md).

Intentional vuln fixtures under `fixtures/` and mock data under `prototypes/`
are excluded from secrets scanners.

## PR conventions

- Prefer small, focused PRs; include tests when behaviour changes.
- Do not commit secrets.
- Keep capability claims labelled (RESEARCH / DECIDED / IMPLEMENTED / VERIFIED) —
  see [docs/STATUS.md](docs/STATUS.md).

## CI

- [CI](https://github.com/neomatrix369/AgentVetter/actions/workflows/ci.yml) — PR/main ultra-minimal gates (ship-path coverage + OSV + targeted scans)
- [Nightly](https://github.com/neomatrix369/AgentVetter/actions/workflows/nightly.yml) — **A** comprehensive T4 (daily 02:00 UTC)
- [Supply chain](https://github.com/neomatrix369/AgentVetter/actions/workflows/supply-chain.yml) — **B** (weekly Mon 03:00 UTC)
- [Mutation](https://github.com/neomatrix369/AgentVetter/actions/workflows/mutation.yml) — **C** (1st+15th 04:00 UTC; non-gating)
- Workflow map: [docs/README.md § CI workflows](docs/README.md#ci-workflows)
