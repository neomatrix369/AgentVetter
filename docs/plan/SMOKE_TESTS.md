# Docs smoke tests

This runbook verifies that first-time readers can successfully progress from install to run, contribution, and maintenance without hidden gaps.

## How to run this smoke test

Run both simulation tracks for every meaningful onboarding or maintenance
documentation change:

1. **Documentation simulation:** follow the documented pages and commands from a
   clean, isolated clone. Use clearly invalid placeholder values only to expose
   hidden configuration gates, missing pages, incorrect routes, or unsafe
   assumptions. Do not call provider APIs, create resources, or count placeholder
   values, cached output, a pre-existing global CLI link, or existing provider
   authentication as a pass.
2. **Provider-fixture simulation:** model one clearly synthetic account and its
   setup path for each vendor: Supabase, Modal, Snyk, Tessl, and Cisco AI
   Defense. Follow each linked account, credential, and `.env` mapping path,
   without signing in, calling provider APIs, creating resources, or using real
   credentials.

Keep the two results separate. These simulations find documentation gaps and
demonstrate the intended provider journey; they do not prove a Live integration.
A command that reuses cached state or fails before its documented work begins
must not satisfy a scan, provider-coverage, or dashboard-result assertion.

## Current status

| Field | Value |
|---|---|
| Last run | 2026-08-03 (PR #41 evidence; current `main` includes the implementation) |
| Last result | Documentation, CLI, and dry-discovery checks passed; dashboard bind was `blocked-by-env`; Live providers were not exercised without disposable credentials |
| Scope | Fresh clone -> install -> local scan/dashboard -> Live setup -> maintenance -> contribution |
| Failure policy | Doc-flow breaks are hard fails. Environment constraints are recorded as blockers (`blocked-by-env`) |

## Test boundary and evidence

**Owner:** The slice executor runs this smoke test for every slice that changes
onboarding, setup, running, maintenance, or contribution guidance. The executor
records the evidence and fixes the gap or links the follow-up issue before handoff.

Run this from a fresh clone when practical. Record whether `agentvetter` was already
globally linked and whether `.env` already existed. Never record tokens,
service-role keys, or credential-bearing URLs.

| Field | Record |
|---|---|
| Date and commit | UTC date and tested commit SHA |
| Mode | `documentation-simulation` or `provider-fixture-simulation` |
| Provider fixtures | One synthetic account path each for Supabase, Modal, Snyk, Tessl, and Cisco AI Defense |
| Result | `pass` or `fail` |
| Evidence and follow-up | Command/output summary and linked issue, if needed |

## Rerun checklist (visitor-first)

### 1) Entry and map

- Start from [README.md](../../README.md).
- Open [docs/README.md](./README.md).

Checks:
- `README.md` opens with a plain metaphor and intent router (demo / Live / contribute / understand).
- `docs/README.md` is the deep task hub (including agent-hooks and tiered-router-setup).
- No dead/obvious broken links from these entry points to first-run docs.

Expected result:
- You can find the complete startup path without requiring extra source files.
- Demo (Recommended) is discoverable before Live (Advanced).

### 2) Local prerequisites

File: [docs/user-guide/prerequisites.md](./user-guide/prerequisites.md)

Run:

```bash
cd /path/to/repo

git --version
git -C . rev-parse --show-toplevel
node -v
npm -v
python3 -V
```

Checks:
- Node 22, npm, and Python 3.12 are available or clearly documented as required.
- Prereq page points next steps to existing setup docs.

Expected result:
- Local checks pass.
- No extra dependency not listed in the page.

### 3) One-off install/setup command flow

File: [docs/user-guide/setup-commands.md](./user-guide/setup-commands.md)

Run (per section order):

```bash
cd /path/to/repo

git clone https://github.com/neomatrix369/AgentVetter.git
after_dir=$PWD
cd AgentVetter
cd cli
npm install
npm link
cd ..
```

Checks:
- Bootstrapping commands are executable.
- Shared setup catalog is complete for one-off setup.

Expected result:
- CLI is linkable; user can follow to next section without missing commands.

### 3a) Installed CLI proof

Run:

```bash
agentvetter --help
agentvetter scan --help
```

Checks:
- The linked CLI is available in a new shell and exposes the documented scan command.
- Any Python or other runtime dependency required by the CLI is either installed
  by the documented flow or reported with an actionable error.

### 4) First-run local validation (no live keys)

File: [QUICKSTART.md](../QUICKSTART.md)

Run:

```bash
cd /path/to/repo/agentvetter

git --version
node -v
npm -v
agentvetter scan --dry-discover ./fixtures/skills/safe-csv-cleaner
agentvetter scan --dry-discover ./fixtures/mcp/mcp_manifest.json
node scripts/serve-dashboard.mjs
```

Checks:
- `--dry-discover` returns fixture targets.
- Dashboard starts in Mock mode path and displays demo path in docs guidance.

Environment caveat:
- Port binding can fail in restricted sandboxes (`127.0.0.1:8765`), classify as `blocked-by-env` and continue smoke run.

Expected result:
- Local validation commands are clear and discoverable.
- No doc-flow breakage; sandbox limits are explicitly identified.

### 5) Five-vendor onboarding fixture order

Files:
- [supabase-setup.md](./user-guide/supabase-setup.md)
- [modal-setup.md](./user-guide/modal-setup.md)
- [env-vars.md](./user-guide/env-vars.md)

Run (read/sequence check; no provider access):

```bash
# Use one clearly synthetic account fixture per vendor.
# Confirm the linked account, credential, and .env paths before copying .env.example.
```

Checks:
- Provision all five vendors, then complete Supabase setup -> Modal setup -> `.env`.
- All five vendor setup paths are explicit: Supabase, Modal, Snyk, Tessl, and
  Cisco AI Defense.
- Each provider has a documented account/key source and `.env` mapping.
- Missing scanner credentials are documented as a separate degraded diagnostic:
  `skipped_missing_credential` applies to that engine and does not prove
  complete Live coverage.

Expected result:
- A new operator can provision live capabilities by following documented order.

### 5a) Live bootstrap proof (test resources only)

Run only with disposable accounts/resources for Supabase, Modal, Snyk, Tessl,
and Cisco AI Defense. Do not paste credentials into this document or command
output.

```bash
agentvetter setup
./scripts/setup-modal.sh --secrets-only
./scripts/setup-modal.sh --deploy-only
```

Checks:
- Platform setup completes without exposing credentials.
- Modal receives only non-empty scanner credentials from the documented allowlist.
- As a separate degraded diagnostic, verify that no scanner credentials preserves
  the existing scanner secret.
- Authentication or cloud-account restrictions are recorded as `blocked-by-env`,
  with the documented recovery path noted.

### 5b) Scan-to-dashboard round trip

Run a fixture scan using the available mode, then start the dashboard:

```bash
agentvetter scan ./fixtures/skills/safe-csv-cleaner
node scripts/serve-dashboard.mjs
```

Checks:
- A complete Live scan produces results with all five vendor paths configured.
- Local no-key validation is limited to dry discovery and Mock dashboard checks.
- Mock and Live dashboard modes are visibly distinct and the selected source is clear.
- In Live mode, the expected result is visible after the scan; otherwise record the
  exact dependency that blocked it.

Expected result:
- The documented path proves the product journey from scan to result review.

### 5c) Degraded mode and recovery

Checks:
- A deliberately removed scanner credential reports `skipped_missing_credential`
  for that engine. Record this as degraded diagnostic evidence, not a passing
  complete-Live result.
- Modal authentication failures point to the documented login/setup path.
- Supabase connection or schema failures point to the documented setup or
  `agentvetter setup --force` recovery path.
- A failure is recorded as `fail` or `blocked-by-env`; do not mask it with `|| true`.

### 5d) Optional tiered router docs

Files:
- [tiered-router-setup.md](./user-guide/tiered-router-setup.md)
- [reading-router-results.md](./user-guide/reading-router-results.md)

Checks:
- SIE + Model Studio live on one page; glossary terms are plain.
- Hub links resolve; no references to deleted `sie-setup.md` / `model-studio-setup.md`.

### 6) Contributor path

File: [CONTRIBUTING.md](../CONTRIBUTING.md)

Run:

```bash
cd /path/to/repo/agentvetter

./scripts/quality-gates.sh --quick
```

Checks:
- Shared path from `README.md` to CONTRIBUTING is explicit.
- Contributor flow references onboarding before dev work.
- Test locations, quality gates, and PR expectations are discoverable without a
  second installation route.

Expected result:
- Contributor path and quality-gate command map are discoverable and executable in context.

#### 6a) Keep onboarding docs in sync with code changes

If project behavior, setup flow, or maintenance flow changes, run this additional check:

- update docs linked from `README.md`, `docs/README.md`, and `CONTRIBUTING.md` first;
- update workflow/governance guidance files when behavior changed:
  - [AGENTS.md](../AGENTS.md)
  - [CLAUDE.md](../CLAUDE.md)
- review other likely impacted docs in this sequence:
  - `QUICKSTART.md`
  - `docs/user-guide/{prerequisites,setup-commands,supabase-setup,modal-setup,env-vars,tiered-router-setup,reading-router-results}.md`
  - `agent-hooks/README.md` (if hooks install path changed)
  - `fixtures/OPTIONAL_SCANNER_KEYS.md`
  - `docs/STATUS.md`
  - `docs/ARCHITECTURE.md` (if architecture/deployment flow changed)
  - `docs/plan/{PROGRESS.md,TRAIL.md,gate-evidence/slice-44.json}` (if scope/status changed)
- re-run this docs smoke test before merge.

### 7) Maintenance / re-run path

File: [docs/user-guide/setup-commands.md](./user-guide/setup-commands.md)

Run:

```bash
cd /path/to/repo/agentvetter

agentvetter setup --force
./scripts/setup-modal.sh --secrets-only
./scripts/setup-modal.sh --deploy-only
./scripts/quality-gates.sh
```

Checks:
- Maintenance commands are separated from one-off setup.
- Optional flags are documented with expected behavior.
- Re-running setup does not duplicate or unexpectedly remove platform resources.
- Secret synchronization preserves scanner secrets when no scanner key is configured.
- Any command that changes cloud state or may incur provider cost is identified before execution.

Expected result:
- Rerun/maintenance flow is complete and not coupled to first-time onboarding.

Re-run this checklist after documentation changes that touch onboarding, running,
contributing, or maintenance guidance. Record environment constraints as
`blocked-by-env` rather than treating them as documentation failures.
