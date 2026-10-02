# Setup command catalog

> Canonical command list for one-off setup and maintenance tasks.

Start here: [QUICKSTART](../../QUICKSTART.md) · Hub: [docs/README](../README.md)

Use this page as the single source for shared setup, validation, scan, and
maintenance commands.

**No clone:** [hosted dashboard](https://neomatrix369.github.io/demos/agentvetter-dashboard/) (Mock on GitHub Pages) · [demo walkthrough video](https://youtu.be/omGOw9ruN3Y).

## CLI flags (reference)

| Command / flag | What it does |
|---|---|
| `agentvetter setup [--force]` | Apply schema to Supabase if tables missing (`SUPABASE_DB_URL`) |
| `agentvetter scan [targets…]` | Discover and scan (default command) |
| `agentvetter scan --dry-discover` | Print discovered targets; spawn nothing |
| `agentvetter scan --reveal-secrets` | Show secret-like tokens in evidence/logs (masked by default) |
| `agentvetter scan --type skill\|mcp` | Restrict discovery to one artifact category |
| `agentvetter scan --force` | Re-run scanners even if content hash is unchanged (card `name` still refreshes on a normal re-scan) |
| `agentvetter scan --concurrency <n>` | Max concurrent sandboxes (default 5) |
| `agentvetter scan --targets <file>` | JSON file with a `targets` array |
| `agentvetter scan --no-defaults` | Error instead of machine defaults on empty args |
| `agentvetter route --batch-id <id>` | Re-run tiered router for a completed batch |
| `agentvetter setup-agent-hooks` | Install Claude Code hooks + `/av-*` skills (`tw-*` aliases) |
| `tripwire` (deprecated shim) | Warns on stderr and execs `agentvetter` with the same argv (one minor) |

Full help: `agentvetter --help` · `agentvetter scan --help`. Shim policy:
[MIGRATION-AGENTVETTER.md](../MIGRATION-AGENTVETTER.md) · [ADR-0018](../adr/0018-agentvetter-rebrand.md).

## When it fails

| Symptom | What to try |
|---|---|
| Live dashboard blank or stale | Switch Mock ↔ Live in Guard; keep `serve-dashboard.mjs` running; run `./scripts/check-supabase.sh` |
| Cards show bare GitHub repo name after fan-out | Re-run `agentvetter scan https://github.com/org/repo` (name refreshes without `--force`; use `--force` only to re-run scanners). Path-only SQL fallback: set `name` from `identifier` when `name` equals the repo segment — see ADR-0010 |
| Scanner outputs (0) with recent last-scan | PostgREST **Max rows** default 1000 — raise on [Data API settings](./supabase-setup.md#6-data-api-max-rows-live-dashboard-fleet-size) |
| Missing scanner output | Confirm vendor keys in [env-vars](./env-vars.md); absent keys → `skipped_missing_credential` |
| `dry-discover` / `agentvetter` not found | Finish [CLI bootstrap](#repository-and-cli-bootstrap) (`npm link`) |
| Port / bind errors on dashboard | Another process may hold `8765`; stop it or note the printed port |
| Auto-route skipped | Missing `SIE_*` → warn and skip (scan still OK). See [tiered-router-setup](./tiered-router-setup.md) |

## 1) One-off setup commands

### Repository and CLI bootstrap

```bash
git clone https://github.com/neomatrix369/AgentVetter.git
cd AgentVetter
cd cli
npm install
npm link
cd ..
```

## 2) Local validation (Node 22 + Mock dashboard)

Use Node 22 for local validation:

```bash
node --version
npm --version
python3 -V
```

```bash
agentvetter scan --dry-discover ./fixtures/skills/safe-csv-cleaner
agentvetter scan --dry-discover ./fixtures/mcp/mcp_manifest.json

# Restrict discovery to one artifact category (--type skill | mcp):
agentvetter scan --type skill --dry-discover   # machine defaults, skills only
agentvetter scan --type mcp   --dry-discover   # machine defaults, MCP servers only

node scripts/serve-dashboard.mjs
```

Use **Mock (demo data)** on Guard during local validation.

## 3) Live environment bootstrap

Before running these commands, complete in order:

- [supabase-setup.md](./supabase-setup.md)
- [modal-setup.md](./modal-setup.md)
- [env-vars.md](./env-vars.md)

Create `.env`, then fill its values using [env-vars.md](./env-vars.md).
That page is the single source for vendor accounts, key procurement, and
key-to-feature mapping. Provision Supabase, Modal, Snyk, Tessl, and Cisco AI
Defense before this step for the recommended complete Live setup. DepShield needs
no keys; add `OSSPREY_API_KEY` when Ossprey access is available.

```bash
cp .env.example .env
agentvetter setup
# optional: ./scripts/setup-supabase.sh
```

### Verify Supabase access

After `agentvetter setup`, confirm the anon key (what the browser dashboard uses)
can read all tables. Run this whenever you change RLS settings or hit a
"Connection error" in the dashboard:

```bash
./scripts/check-supabase.sh
```

### Live dashboard

The dashboard needs a local proxy to talk to Supabase. Start it before opening
the dashboard in Live mode — it must stay running while you use the dashboard:

```bash
node scripts/serve-dashboard.mjs
# Open: http://127.0.0.1:8765/AgentVetter.dc.html → select Live (Supabase)
```

The proxy writes `prototypes/dc-dashboard/agentvetter-dashboard.config.js` on
startup. If you restart the proxy on a different port, reload the dashboard so
it picks up the new config.

### Modal bootstrap

```bash
pip install modal
./scripts/setup-modal.sh
# Optional
./scripts/setup-modal.sh --secrets-only
./scripts/setup-modal.sh --deploy-only
```

## 4) Re-run and maintenance commands

### Schema refresh / redeploy

```bash
agentvetter setup --force
./scripts/setup-modal.sh --secrets-only
./scripts/setup-modal.sh --deploy-only
```

### Maintenance checks

```bash
./scripts/quality-gates.sh --quick
./scripts/quality-gates.sh
```

### Monitoring / health check

```bash
agentvetter status                # human-readable report
agentvetter status --json         # one machine-readable JSON object instead
agentvetter status --limit 50     # inspect the last 50 scan runs (default 20, max 200)
```

`agentvetter status` is **read-only**: it never changes PreToolUse enforcement,
Supabase rows, or local files. It reports:

- **Hooks** — `~/.agentvetter/config.json` (`enable`, `scan_validity_days`,
  `repo_root`), whether `~/.claude/settings.json` registers the AgentVetter
  PreToolUse hook, and the Supabase platform switch
  (`config.monitoring_enabled` + `threshold`). A warning prints when the local
  and platform switches disagree — effective enforcement is their AND.
- **Items** — `heatmap_status` distribution (red/amber/green/grey/error).
- **Recent scan runs** — status counts for the last `--limit` runs, the newest
  few lines, and any `running` rows older than 30 minutes (STRANDED — remedy:
  `node scripts/reconcile-stuck-scan-runs.mjs`).
- **Scanners** — latest status per scanner source across those runs, with
  `unreachable` / `skipped_missing_credential` counts.

Troubleshooting empty/disabled states:

- `not installed (~/.agentvetter/config.json missing)` — run
  `agentvetter setup-agent-hooks` first.
- `Supabase unreachable — set SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY` — the
  local hooks section still prints (exit 0); fill `.env` per
  [env-vars.md](./env-vars.md) to get scan/dispatch health too.
- `no items recorded yet` / `no scan runs recorded yet` — run `agentvetter scan`.
- Invalid flags (for example `--limit notanumber`) exit nonzero with an
  actionable message.

### Tiered router (optional)

> **Missing credentials → warn and skip.** Scans still complete. Without
> `SIE_ENDPOINT` / `SIE_API_KEY`, auto-route and `agentvetter route` log a warning
> and leave scanner findings unchanged. Model Studio keys are needed only when
> SIE escalates.

After a Live scan, AgentVetter auto-routes the batch when **SIE** keys are set.
Provision accounts with [tiered-router-setup.md](./tiered-router-setup.md); key map:
[env-vars.md](./env-vars.md#optional--tiered-router-sie--model-studio).
Design: [ADR-0016](../adr/0016-tiered-router-sie-model-studio.md). UI:
[reading-router-results.md](./reading-router-results.md).

| Keys present | Behaviour |
|---|---|
| Neither SIE nor Model Studio | Warn + skip routing |
| SIE only | Every item assessed; `routing_review` when not escalated; escalate paths that need Model Studio soft-fail with a failure note in `routing_review` |
| SIE + Model Studio | Full path: review, arbitration (`routing_decision`), or triage (`routing_triage`) |

**Idempotency:** replace-on-success per item — the prior `tiered_router` row for
that scan_run is replaced only after a successful SIE decision. There is no
batch-wide DELETE first, so a SIE outage cannot wipe existing dashboard strips.

Re-run routing manually:

```bash
agentvetter route --batch-id <batch_id>
# optional overrides (CLI → env → code default):
# agentvetter route --batch-id <batch_id> --sie-model gen-4b --model-studio-model qwen3.8-max
```

Defaults: `SIE_MODEL=gen-4b`, `MODEL_STUDIO_MODEL=qwen3.8-max`. The finding
`message` is a JSON envelope (`signals`, `models`, `reasoning`) — see ADR-0016.

Dashboard Mock fixtures include `tiered_router` findings. To seed Live conflict /
timeout fixtures for UI checks (requires Supabase service-role in `.env`):

```bash
node scripts/seed-router-fixtures.js
```

Then open the Live dashboard and use Escalated / SIE-only filters — details in
[reading-router-results.md](./reading-router-results.md).

## 5) Test commands (when needed)

```bash
cd cli && npm test
pytest                              # sandbox/tests via pyproject testpaths
pytest sandbox/tests/test_acquire_target.py
cd prototypes/dc-dashboard && npm test
```

### Test command for full stack (optional)

See the contributor workflow in [../CONTRIBUTING.md](../../CONTRIBUTING.md) for the full checklist and command expectations.
