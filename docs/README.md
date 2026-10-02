# Documentation index

Use this map to move from a first look to the setup or project detail you need.

Start here: [QUICKSTART](../QUICKSTART.md) · Repo entry: [README](../README.md)

[![CI](https://img.shields.io/github/actions/workflow/status/neomatrix369/agentvetter/ci.yml?branch=main&label=CI)](https://github.com/neomatrix369/AgentVetter/actions/workflows/ci.yml)
[![Nightly](https://img.shields.io/github/actions/workflow/status/neomatrix369/agentvetter/nightly.yml?branch=main&label=Nightly)](https://github.com/neomatrix369/AgentVetter/actions/workflows/nightly.yml)
[![Complexity](https://img.shields.io/github/actions/workflow/status/neomatrix369/agentvetter/complexity-report.yml?branch=main&label=Complexity)](https://github.com/neomatrix369/AgentVetter/actions/workflows/complexity-report.yml)

## Choose a task

| Your task | Start here | Then |
|---|---|---|
| Browse hosted dashboard (no clone) | [GitHub Pages demo](https://neomatrix369.github.io/demos/agentvetter-dashboard/) | [Demo video](https://youtu.be/omGOw9ruN3Y) · [QUICKSTART](../QUICKSTART.md) |
| Watch demo walkthrough (no clone) | [YouTube tour](https://youtu.be/omGOw9ruN3Y) | [Hosted dashboard](https://neomatrix369.github.io/demos/agentvetter-dashboard/) · [screenshots](./screenshots/README.md) |
| Try demo (no accounts) | [QUICKSTART — demo](../QUICKSTART.md#try-the-demo-recommended) | [Setup commands](./user-guide/setup-commands.md) · [screenshots](./screenshots/README.md) |
| Check tools and fit | [Prerequisites](./user-guide/prerequisites.md) | [QUICKSTART](../QUICKSTART.md) |
| Create accounts (Setup) | [Supabase setup](./user-guide/supabase-setup.md) | [Modal setup](./user-guide/modal-setup.md) → optional scanners via [env-vars](./user-guide/env-vars.md#vendor-procurement-quick-steps) |
| Configure keys | [Environment keys](./user-guide/env-vars.md) | [`.env.example`](../.env.example) → [setup commands](./user-guide/setup-commands.md) |
| Minimum Live (2 accounts) | [QUICKSTART — Live](../QUICKSTART.md#live-advanced) (MVP: Supabase + Modal) | [Setup commands](./user-guide/setup-commands.md#live-environment-bootstrap) |
| Run a first Live scan | [QUICKSTART — Live](../QUICKSTART.md#live-advanced) | [Setup commands](./user-guide/setup-commands.md) |
| Maintain Live / re-run | [Setup commands — re-run](./user-guide/setup-commands.md#re-run-and-maintenance-commands) | [When it fails](./user-guide/setup-commands.md#when-it-fails) |
| Enable optional tiered routing | [Tiered router setup](./user-guide/tiered-router-setup.md) | [`agentvetter route`](./user-guide/setup-commands.md#tiered-router-optional) → [read router results](./user-guide/reading-router-results.md) |
| Understand results, services, and system shape | [Architecture](./ARCHITECTURE.md) | [Capability status](./STATUS.md) · [ADRs](./adr/README.md) · [router UI](./user-guide/reading-router-results.md) |
| Claude Code agent hooks | [agent-hooks README](../agent-hooks/README.md) | [frontline output contract](./user-guide/frontline-output-contract.md) · [CONTRIBUTING](../CONTRIBUTING.md) |
| Contribute | [Contributing](../CONTRIBUTING.md) | [Setup and maintenance commands](./user-guide/setup-commands.md) |
| Report a vulnerability | [SECURITY](../SECURITY.md) | — |
| Migrate from Tripwire | [MIGRATION-AGENTVETTER.md](./MIGRATION-AGENTVETTER.md) | [ADR-0018](./adr/0018-agentvetter-rebrand.md) |

## Setup and operation

| Guide | What it covers |
|---|---|
| [QUICKSTART.md](../QUICKSTART.md) | Demo (Recommended) then Live (Advanced); [hosted dashboard](https://neomatrix369.github.io/demos/agentvetter-dashboard/) · [demo video](https://youtu.be/omGOw9ruN3Y) |
| [user-guide/prerequisites.md](./user-guide/prerequisites.md) | Required tools, technical fit, capability prerequisites |
| [user-guide/setup-commands.md](./user-guide/setup-commands.md) | Command SSOT: bootstrap, flags, fails, maintenance |
| [user-guide/env-vars.md](./user-guide/env-vars.md) | Configure (keys): procurement SSOT for `.env` |
| [user-guide/supabase-setup.md](./user-guide/supabase-setup.md) | Supabase project, API keys, schema bootstrap, Data API max rows |
| [user-guide/modal-setup.md](./user-guide/modal-setup.md) | Modal auth, secrets sync, scan app deploy |
| [user-guide/tiered-router-setup.md](./user-guide/tiered-router-setup.md) | Optional SIE + Model Studio routing |
| [user-guide/reading-router-results.md](./user-guide/reading-router-results.md) | Pathway strips, Escalated / SIE-only filters, glossary |
| [user-guide/frontline-output-contract.md](./user-guide/frontline-output-contract.md) | `/av-verify` dual-output table (alias `/tw-verify`; Quality `N/100` + blocked footer + Sources: Tessl / Cisco+Snyk) |
| [STATUS.md](./STATUS.md) | Evidence-labelled capability claims |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Services inventory, C4, operator journey + dependency diagrams, key flows |
| [adr/README.md](./adr/README.md) | Formal architecture decision records |
| [screenshots/](./screenshots/README.md) | CLI + dashboard + Workflow gallery |
| [agent-hooks/README.md](../agent-hooks/README.md) | Claude Code hooks + `/av-*` skills (aliases `/tw-*`) |
| [SECURITY.md](../SECURITY.md) | Vulnerability reporting |

## Project records

| Need | Reference |
|---|---|
| Contribute code or documentation | [CONTRIBUTING.md](../CONTRIBUTING.md) |
| Run the documentation smoke path | [SMOKE_TESTS.md](./plan/SMOKE_TESTS.md) |
| Review CI and Nightly workflows | [CI workflows](#ci-workflows) |
| Inspect project planning | [plan README](./plan/README.md) · [progress](./plan/PROGRESS.md) |
| LLM usage metering (DECIDED plan — not shipped) | [design/llm-usage-tracking.md](./design/llm-usage-tracking.md) · Wave M in [STATUS](./STATUS.md) |
| Monk Kit Live packaging (ADR Proposed; Wave O plan-only) | [ADR-0001](./adr/0001-monk-deployment-and-packaging.md) · [TRAIL Wave 15-O](./plan/TRAIL.md) · [STATUS](./STATUS.md) |
| Git repo skill+MCP fan-out + package/DepShield/Ossprey + CLI scanner inventory (IMPLEMENTED on branch — not on `main`) | [slice 62](./plan/slices/16-P-git-repo-scan/slice-62-git-repo-discover-fanout.md) · [slice 63](./plan/slices/16-P-git-repo-scan/slice-63-cli-scanner-inventory.md) · [slice 64](./plan/slices/16-P-git-repo-scan/slice-64-git-repo-package-scan.md) · Wave P in [STATUS](./STATUS.md) · [prerequisites](./user-guide/prerequisites.md#what-can-agentvetter-scan) |
| Check scanner adapter research | [scanner output adapters](./research/adapters/scanner-output-adapters.md) |

## CI workflows

| Workflow | Cadence | Jobs / role |
|---|---|---|
| [CI](../.github/workflows/ci.yml) | PR + push(`main`) + dispatch | Ultra-minimal: lint · static · ship-path coverage · OSV · Trivy (targeted) · gitleaks/TruffleHog incremental |
| [Nightly](../.github/workflows/nightly.yml) | **A** daily **02:00 UTC** (`0 2 * * *`) + dispatch | Semgrep · CodeQL · full secrets/Trivy · dashboard tests · cov snapshots · complexity · dep audit |
| [Supply chain](../.github/workflows/supply-chain.yml) | **B** weekly **Mon 03:00 UTC** (`0 3 * * 1`) + dispatch | SBOM · Meterian strict · Chalk (warn-only) |
| [Mutation](../.github/workflows/mutation.yml) | **C** **1st+15th 04:00 UTC** (`0 4 1,15 * *`) + dispatch | Stryker · advisory mutmut (**non-gating**) |
| [Complexity](../.github/workflows/complexity-report.yml) | PR (path-filtered) | Xenon/complexity evidence on changed `sandbox/` / `cli/` paths |
| [Code Review Graph](../.github/workflows/code-review-graph.yml) | **A** daily **02:00 UTC** + dispatch | Knowledge-graph analysis (nightly; PR sticky comments dormant) |
| [Code Review Graph Comment](../.github/workflows/code-review-graph-comment.yml) | `workflow_run` | Dormant while CRG has no `pull_request` trigger |

T4 A/B/C are separate workflows (split 2026-09-09; A expanded 2026-09-11).
Meterian runs only on **B** (not PR CI). Details: [CONTRIBUTING](../CONTRIBUTING.md)
· [ADR-0013](./adr/0013-ship-path-quality-gates.md).
