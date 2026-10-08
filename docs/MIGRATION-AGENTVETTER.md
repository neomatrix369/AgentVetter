# AgentVetter identity and cutover

**Status:** DECIDED / IMPLEMENTED (in-repo) · Modal + rollup **VERIFIED** (maintainer
workspace 2026-10-02) · Pages demo path live; sync-script casing follow-up
[neomatrix369.github.io#21](https://github.com/neomatrix369/neomatrix369.github.io/pull/21)
**ADR:** [ADR-0018](adr/0018-agentvetter-rebrand.md)

Live product identity is **AgentVetter** only. This guide covers clone URLs,
packages, CLI, skills, env vars, config home, Modal secrets, and Pages.

## Clone and remote

```bash
git remote set-url origin git@github.com:neomatrix369/AgentVetter.git
# or
git clone git@github.com:neomatrix369/AgentVetter.git
```

## Packages

| Ecosystem | Package |
|-----------|---------|
| PyPI | `agentvetter` |
| npm | `agentvetter-cli` |

Install these names only. Uninstall any prior-brand package names if still present.

## CLI

```bash
agentvetter --help
agentvetter scan …
```

There is a single npm bin: `agentvetter`.

## Skills

| Primary | Permanent alias (`SKILL.md` frontmatter) |
|---------|------------------------------------------|
| `/av-scan` | `/tw-scan` |
| `/av-verify` | `/tw-verify` |
| `/av-enable` | `/tw-enable` |
| `/av-disable` | `/tw-disable` |
| `/av-self-check` | `/tw-self-check` |
| `/sync-agentvetter-pages` | (gallery sync skill; prefer primary name) |

Prefer `av-*` in new docs and habit. Short `tw-*` aliases remain permanent via
SKILL.md `aliases:` frontmatter only — they are not a second product brand.

## Environment variables

Use `AGENTVETTER_*` only. Update `.env`, CI secrets, and shell profiles before
upgrade. Examples: `AGENTVETTER_JUDGE_PANEL`, `AGENTVETTER_CONFIG`,
`AGENTVETTER_CLONE_TIMEOUT`.

## Config home

Live path: `~/.agentvetter` (hooks at `~/.agentvetter/hooks/`, config at
`~/.agentvetter/config.json`).

If a pre-rebrand config directory still exists under `$HOME`, rename or copy it
to `~/.agentvetter` once, then remove the old directory. Code no longer reads
legacy config homes.

## Modal secrets (operator)

| Secret / app | Name |
|--------------|------|
| Supabase secret | `agentvetter-supabase` |
| Scan secrets | `agentvetter-scan-secrets` |
| Deployed app | `agentvetter-scan` (`modal.App("agentvetter-scan")` in `sandbox/scan_app.py`) |

Prefer `./scripts/setup-modal.sh` (creates/forces the new secret names from
`.env`, then deploys). After verifying a Live scan, stop any leftover prior-brand
scan app and delete unused prior-brand secrets.

**VERIFIED (2026-10-02, maintainer workspace):** `./scripts/setup-modal.sh
--non-interactive` created `agentvetter-supabase` + `agentvetter-scan-secrets` and
deployed `agentvetter-scan`; smoke `agentvetter scan
./fixtures/skills/safe-csv-cleaner --no-defaults --force` completed with
`failed_targets: []` after rollup apply; prior-brand app/secrets removed.

## GitHub Pages / demo path

Live demo: https://neomatrix369.github.io/demos/agentvetter-dashboard/ (HTTP 200).
Sync wrapper path defaults for the local folder `AgentVetter` are in
[neomatrix369.github.io#21](https://github.com/neomatrix369/neomatrix369.github.io/pull/21).

## Dashboard localStorage (prototype)

Keys are `agentvetter-*`. Clear any pre-rebrand keys in the browser (or use a
fresh profile). No automatic migration.

## Database rollup function

Live code calls `agentvetter_rollup_item` (CLI, Modal sandbox, reconcile script).
`db/schema.sql` defines **`agentvetter_rollup_item`** only.

**Operator action:** re-apply `db/schema.sql` (via `agentvetter setup --force` /
first-scan bootstrap, or SQL editor) so the function exists on Supabase.
`db/schema.sql` also carries `DROP FUNCTION IF EXISTS tripwire_rollup_item(uuid)`
so `agentvetter setup --force` idempotently removes the legacy function on any
older deployment.

**VERIFIED (2026-10-02, maintainer workspace):** `agentvetter_rollup_item` applied
to live Supabase (direct SQL at the time; pooler TLS was not yet fixed).
Subsequent Modal smoke scan rollup succeeded.

**VERIFIED (2026-10-08):** Pooler TLS fixed — `agentvetter setup --force` now
works against `*.pooler.supabase.com` without the self-signed certificate chain
error. `pgSslConfig` skips cert verification for pooler hosts only. PR: [#188](https://github.com/neomatrix369/AgentVetter/pull/188).

**VERIFIED (2026-10-08):** `tripwire_rollup_item` dropped from live Supabase;
only `agentvetter_rollup_item` remains. PR: [#188](https://github.com/neomatrix369/AgentVetter/pull/188).

## Checklist for operators

Maintainer workspace ticks (**VERIFIED 2026-10-02**) where noted; leave unchecked
on a machine that has not completed that step.

- [x] Origin URL is `neomatrix369/AgentVetter`
- [ ] Packages installed as `agentvetter` / `agentvetter-cli`
- [x] `agentvetter --help` works
- [x] Skills resolve as `av-*` (`tw-*` aliases still work)
- [ ] Env vars use `AGENTVETTER_*` only
- [x] Config under `~/.agentvetter` (`enable` left false)
- [x] Modal secrets renamed and deploy verified (`agentvetter-scan`; prior-brand
      leftovers removed)
- [x] Pages/demo path is `…/demos/agentvetter-dashboard/`; sync-script
      `AgentVetter` path casing → [Pages PR #21](https://github.com/neomatrix369/neomatrix369.github.io/pull/21)
- [ ] Dashboard localStorage cleared / new keys in use (browser-local)
- [x] Supabase has `agentvetter_rollup_item`
- [x] `tripwire_rollup_item` dropped from Supabase (only `agentvetter_rollup_item` remains; VERIFIED 2026-10-08)
