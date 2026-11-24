# Slice 61 — Monk Docs Coexistence + Operator Honesty

> Scenario: Brownfield | MoSCoW: **Should** | Status: 📋 PLANNED
> Wave: **15-O — Monk Kit Live packaging** (ADR-0001)
> Depends on: 58 ✅ (can draft in parallel with 59; must not claim VERIFIED until 59 evidence exists)
> Sources: ADR-0001 “Coexistence with today’s docs” · [Monk First Deployment](https://docs.monk.io/getting-started/first-deployment) · [Local Dashboard](https://docs.monk.io/getting-started/local-dashboard)

## Session bootstrap
> Re-read CLAUDE.md before starting — use values there, not hardcoded commands here.
- **Runtime source**: → CLAUDE.md § Environment
- **Test source**: → CLAUDE.md § Testing
- **Load first**: CLAUDE.md → docs/plan/invariants.md → this stub → ADR-0001

## Context
> Read before any implementation. Do not rely on conversation history alone.
- **Stage objective**: Document the Monk Kit path as **additive** beside the workstation Live path, grounded in Monk’s real operator UX (dashboard secrets, approvals, BYOC), without overselling before slice 59 VERIFIED.
- **Depends on**:
  - Slice 58: Kit files exist so docs can point at real paths — `test -f MANIFEST`
  - Slice 59 for any “VERIFIED / try Monk deploy” wording — until then label experimental/Proposed
- **Global invariants**: → `docs/plan/invariants.md`

## Non-goals
> Out of scope for this slice — do not implement here.
- Rewriting QUICKSTART to replace workstation Live as the primary path
- Authoring Capsules or CI/CD operator guides (link only as future)
- Kit YAML / bootstrap implementation (58–60)

## Added scope (2026-11-23 — docs integration plan, revised after reviewer rounds 1+2)

### Three-file doc structure (from documentarist + architect reviews)
Single JTBD per file. Do not collapse into one file.

**File 1: `docs/explanation/monk-deployment-choices.md`** (new — Explanation)
> JTBD: "Help me understand the options and choose"
- P1 decision guide — Option A vs B comparison table (cost, infrastructure, automation, Monk's role)
- Monk architecture explanation: what a Monk Kit is, what a runnable is, what BYOC means
- Monk pricing: 5-day free trial → Free tier (1 cluster / 3 runnables) → Paid (~$29/mo)
- Link to `monk-deploy.md` once decision is made

**File 2: `docs/user-guide/monk-deploy.md`** (new — How-to)
> JTBD: "Help me execute the deploy I've chosen"

Sections (progressive disclosure — pre → deploy → link out to ops):

**P2. Prerequisites checklist** (both options with step-by-step account setup)
- Option A: Supabase ✓, Modal ✓, Cloudflare account + Pages CI config (Framework: None, build output: `prototypes/dc-dashboard`, env vars in Pages Settings)
- Option B: all above + Hetzner account + API token + Monk install + auth + trial/pricing note

**P3. Local-workflow verification gate** (`file://` dashboard loads, redact import, CLI smoke check)

**Choose your path** (branching — reader skips the other path entirely):
- → Option A: Cloudflare Pages deploy steps
- → Option B: Hetzner via Monk deploy steps (with inline Tier 1 secrets list, `monk validate MANIFEST`, region selection, bootstrap status check)

**Outcome statement** (required at top of each path):
> "By the end of this path you'll have: a live [Cloudflare Pages / Hetzner HTTPS] dashboard serving Supabase data, with security headers configured."

**A. What Monk does for AgentVetter** — hybrid model: Supabase provisioning, bootstrap container,
agent plugin commands (`/monk show me what's running`, `/monk deploy the latest changes`)

**B. Monk-readiness checklist** — what each Kit file does; contributor checklist
(`MANIFEST`, `common.yaml`, `v1.0.0.yaml`, `latest.yaml`, `bootstrap/Dockerfile`)

**C. Monk Kit deploy steps (Hetzner BYOC)** — `monk validate MANIFEST` → Hetzner region →
Monk plugin → approve VM plan in local dashboard → enter Tier 1 secrets (all 4 listed inline)
→ Monk provisions VM + bootstrap + nginx dashboard → `monk status bootstrap` = succeeded

**D. Bootstrap failure recovery** — `monk logs agentvetter/bootstrap | tail -20`; fallback: manual
schema apply via Supabase Console; fallback: `python3 scripts/setup-modal.sh`; re-deploy command

**E. After-deploy commands** — full `/monk` command list including cost, scale, logs, deploy

**F. Cloudflare Pages deploy steps (Option A)** — build settings, env vars placement in Pages UI,
`_headers` file, CORS, `wrangler pages deployments list` to verify

**G. Secrets quick reference table** — where to get all 7 secrets (Supabase, Modal, Snyk, Cloudflare,
Hetzner, SUPABASE_ANON_KEY for Option A)

**→ After deploy succeeds:** link to `docs/reference/monk-operations.md` for all ongoing ops

**File 3: `docs/reference/monk-operations.md`** (new — Reference)
> JTBD: "Help me find the command/procedure I need right now"
- Q0. Observability — logs, `monk status`, smoke tests (HTTPS, CORS + positive + negative), browser DevTools check
- Q1. Service lifecycle — pause/stop/restart individually and all at once (Monk CLI + natural language), Cloudflare disable/re-enable, service dependency order
- Q2. Bring down everything and what persists (Option A and Option B)
- Q3. Update dashboard after a code change (`git push` for A; `/monk deploy latest` for B)
- Q4. Kit version upgrade path (schema migration steps, `v1.1.0`, MANIFEST pin, smoke test script)
- Q5. Orphan cleanup — Supabase orphan, Modal orphan, Hetzner VM orphan recovery
- Q6. Monk trial expiry procedure — delete before day 5 or upgrade to paid

**Local-first rule (non-negotiable):** docs must describe cloud as additive bolt-on.
Workstation Live path (`scripts/` + `.env`) remains primary until VERIFIED.

### `QUICKSTART.md` hybrid deploy section
Add a row to the top table pointing at both cloud deploy paths.
Add `## Deploy (Cloud)` section: 2–3 sentences, link to `docs/explanation/monk-deployment-choices.md`
to choose Option A or B, then follow the how-to.
Reference Cloudflare Pages (not GitHub Pages) for the Live dashboard URL.

## Output contract
> Observable shape of completion (shape only — not exact file paths).
- **Baseline**: ADR-0001 exists; user-guide still workstation-centric
- Docs index / STATUS / optional user-guide page describe Monk path with evidence-state labels (Proposed → VERIFIED only when 59 done)
- Links to Monk docs for install, first deploy, local dashboard, secrets-never-in-chat
- Clear “secrets go in Monk dashboard, not chat / not committed `.env` for Kit path”

## Slice Workflow Bundle
- Slice name: `slice-61-monk-docs-coexistence`
- Files: `docs/STATUS.md`, `docs/README.md`, optional `docs/user-guide/monk-kit-deploy.md`, ARCHITECTURE pointer
- Exit criteria: Additive Monk docs published; workstation path remains primary until VERIFIED; DIVIO-ish how-to stays short
- Commit pattern: `docs(slice-61): Monk Kit coexistence + honesty`

## Branch
`slice/61-monk-docs-coexistence`

## Spec (GWT)

### GWT-61.1 — Workstation path remains primary until VERIFIED `@contract-shape:unbounded-preservation`
**Given** a new operator opens QUICKSTART / README
**When** they look for how to run Live
**Then** the workstation `.env` + CLI path is still the documented default
**And** Monk is introduced as additive / experimental until STATUS shows MVL VERIFIED

### GWT-61.2 — Monk operator path points at real Monk UX `@contract-shape:bounded-change`
**Given** the Monk Kit docs page (or STATUS section)
**When** the operator follows “deploy with Monk”
**Then** they see steps aligned to Monk First Deployment: install → deploy prompt → **local dashboard credentials** → approve infra → HTTPS URL
**And** they are warned never to paste cloud/scanner secrets into agent chat ([Local Dashboard](https://docs.monk.io/getting-started/local-dashboard))

### GWT-61.3 — Evidence-state labels are visible `@contract-shape:unbounded-preservation`
**Given** docs mentioning Monk packaging
**When** capability claims are read
**Then** each claim is labelled Proposed / DECIDED / IMPLEMENTED / VERIFIED appropriately
**And** no claim marks registry publish or Capsules as shipped
**And** honesty greps reject phrases like “immediately deployable via Monk” unless adjacent evidence-state is VERIFIED

### GWT-61.4 — ADR and plan are cross-linked `@contract-shape:bounded-change`
**Given** `docs/adr/0001-monk-deployment-and-packaging.md` and Wave O stubs
**When** an operator opens docs/README or ARCHITECTURE decisions
**Then** they can navigate ADR → plan slices 58–61 → Monk public docs

## Acceptance criteria (short-form)
- [ ] GWT-61.1–61.4 satisfied
- [ ] No secrets examples with real values
- [ ] Documentarist-friendly: how-to separate from explanation; STATUS owns honesty

## Before-Checks [GATE]
- [ ] Branch created
- [ ] Slice 58 Kit paths known
- [ ] Confirm with STATUS whether 59 VERIFIED yet (gates wording)

## TDD Execution
- Docs-only: markdown link checks + grep honesty assertions (no “immediately deployable via Monk” without VERIFIED)
- Sequence: RED (failing honesty/link tests) → GREEN → VERIFY

## After-Checks [GATE]
- [ ] Docs committed with `docs(slice-61): ...`
- [ ] Specification coverage via link/honesty tests for each GWT
- [ ] Complexity gates N/A (docs-only) — record N/A reason in gate-evidence
- [ ] **Merge gate:** if STATUS/docs claim Monk MVL **VERIFIED**, then slice 59 ✅ is on `main` (gate-evidence present)
- [ ] `nw-documentarist-reviewer` APPROVE or follow-ons logged

### Closing Gates
- [ ] `nw-at-completeness-check` — AT completeness audit (slice close gate #8)
- [ ] `nw-documentarist-reviewer` — documentation currency (primary for this slice)
- [ ] `nw-gate-evidence-validator` — all 9 gate-evidence conditions pass
- [ ] `/verify-slice` — holistic evidence verdict COMPLETE (final closing gate)

## Gate Status
📋 PLANNED

## Session Metrics
| Metric | Value |
|--------|-------|
| Estimated Pomos | 1 (~25 min) |
| Execution time | — |
| Blockers encountered | — |
| Next-session notes | Soft-gate VERIFIED wording on 59 merge |
