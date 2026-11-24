# Slice 79 — Security Hardening from Monk Integration Review

> Scenario: Brownfield | MoSCoW: **Must** | Status: 📋 PLANNED
> Wave: **15-O — Monk Kit Live packaging** (ADR-0001)
> Depends on: 58 ✅ (Kit files exist; sandbox/ present)
> Sources: Security audit 2026-11-23 · `sandbox/redact.py` · `db/schema.sql` RLS

## Session bootstrap
- **Load first**: CLAUDE.md → docs/plan/invariants.md → slice 58 stub → this stub

## Context
- **Stage objective**: Close two security gaps identified during the Monk integration security
  audit: missing credential patterns in `sandbox/redact.py` and local-compatibility validation
  of all cloud-layer changes.
- **Why it matters**: `findings.snippet` and `scan_run_scanners.console_output` are
  anon-readable columns (by design via RLS). If a scanned skill outputs a JWT, DB connection
  string, or non-prefix service token, the current `_SECRET_RULES` lets it land in the DB
  visible to any anon-key holder.
- **Local-first rule**: every change must leave the local `file://` dashboard open and
  local `scripts/` execution unaffected.

## Non-goals
- RLS changes (already solid — anon SELECT on correct tables, anon revoked from sensitive ones)
- Dashboard XSS (already low risk — React auto-escaping, no dangerouslySetInnerHTML)
- Dockerfile hardening (already done — digest pin + USER node)
- CSP meta tag in source HTML (intentionally NOT added — breaks `file://` local opens)

## Output contract
- **Baseline**: `sandbox/redact.py` `_SECRET_RULES` has ~8 patterns; JWT/DB URI/non-prefix tokens not covered
- `_SECRET_RULES` extended with: JWT pattern, DB URI prefixes, non-prefix token patterns
- `python3 -c "import sandbox.redact"` runs clean locally
- `prototypes/dc-dashboard/AgentVetter.dc.html` opens via `file://` without CSP errors (no meta CSP added)
- Existing tests pass; no regression in CLI or sandbox behaviour

## Slice Workflow Bundle
- Slice name: `slice-79-security-hardening`
- Files: `sandbox/redact.py`
- Exit criteria: new patterns added; local compat checklist passes; existing tests green
- Commit pattern: `fix(slice-79): extend redact rules for JWT, DB URIs, non-prefix tokens`

## Branch
`slice/79-security-hardening`

## Spec (GWT)

### GWT-62.1 — JWT tokens redacted before DB write
**Given** a scan finding whose `snippet` contains a JWT (3-segment base64url: `xxxxx.yyyyy.zzzzz`)
**When** `redact_secrets(text)` is called
**Then** the JWT is replaced with `[REDACTED]`
**And** the redacted text is written to `findings.snippet`

### GWT-62.2 — DB connection strings redacted
**Given** a scan finding containing `postgresql://user:pass@host/db` or `mongodb+srv://...` or `mysql://...`
**When** `redact_secrets(text)` is called
**Then** the URI (including embedded credentials) is replaced with `[REDACTED]`

### GWT-62.3 — Service tokens redacted (amended 2026-11-24)
**Given** a scan finding containing a Cloudflare API token in a documented prefixed format (`cfut_`, `cfat_` or `cfk_` followed by 40+ characters), a Fly.io token (`fo1_` or `fm2_`, optionally preceded by `FlyV1`), or a Netlify token written after a `NETLIFY_AUTH_TOKEN=`-style label
**When** `redact_secrets(text)` is called
**Then** the token is replaced with `[REDACTED]` (Netlify: `netlify_token=[REDACTED]`)
**And** unlabelled Netlify tokens and legacy unprefixed Cloudflare tokens are **not** masked: neither has a distinguishing shape, and a bare 40-character pattern would hit git commit SHAs
**And** a release identifier such as `v1.0-release-20241231` is left unchanged

**Amendment note (2026-11-24):** the original wording used `v1.0-...` as the Cloudflare shape. Cloudflare's documented formats are `cfut_` (user), `cfat_` (account) and `cfk_` (global key) prefixes, and legacy tokens are unprefixed. `v1.0-` is not a Cloudflare format. Source: Cloudflare Fundamentals docs, Token formats (developers.cloudflare.com/fundamentals/api/get-started/token-formats/), as summarised in research supplied by the operator; not re-fetched in this session.

### GWT-62.4 — Local `file://` dashboard unaffected
**Given** `prototypes/dc-dashboard/AgentVetter.dc.html` opened via `file://` protocol
**When** DevTools console is inspected
**Then** no CSP violation errors appear
**And** Supabase `https://` calls are not blocked by any in-HTML policy

### GWT-62.5 — Local scripts unaffected
**Given** `scripts/setup-supabase.sh` and `scripts/setup-modal.sh` on a local machine
**When** run in a clean environment
**Then** both complete without errors introduced by slice 79 changes

## Local compatibility checklist [GATE]
- [ ] `python3 -c "import sandbox.redact"` exits 0
- [ ] `prototypes/dc-dashboard/AgentVetter.dc.html` opens via `file://`; no CSP errors in DevTools
- [ ] `scripts/setup-supabase.sh` dry-run clean (no regressions)
- [ ] Existing redact tests pass (or are added for new patterns)

## Before-Checks [GATE]
- [ ] Branch `slice/79-security-hardening` created
- [ ] Slice 58 ✅ on `main` (sandbox/ exists)

## After-Checks [GATE]
- [ ] `fix(slice-79): ...` commit on branch
- [ ] All GWT-62.1–62.5 have test coverage or manual evidence
- [ ] Local compatibility checklist above all ticked
- [ ] No new patterns accidentally break existing redaction of AWS/GCP/GitHub tokens

### Closing Gates
- [ ] `nw-gate-evidence-validator` passes for `docs/plan/gate-evidence/slice-79.json` (currently `verdict: BLOCKED`)
- [ ] `/verify-slice` returns COMPLETE (required final gate)
- [ ] Code review: `nw-software-crafter-reviewer` APPROVED
- [ ] GWT-62.4 DevTools check on `file://` run by operator (CSP violations: 0 observed in headless Chromium)
- [ ] GWT-62.5 live dry-run of `scripts/setup-supabase.sh` and `scripts/setup-modal.sh` run by operator (needs credentials)
- [ ] Dashboard live smoke passes on a networked machine (or the exclusion is recorded in DECISIONS.md)

## Gate Status
📋 PLANNED

## Session Metrics
| Metric | Value |
|--------|-------|
| Estimated Pomos | 1 (~25 min) |
| Next-session notes | Run existing redact tests first to establish baseline before adding patterns |
