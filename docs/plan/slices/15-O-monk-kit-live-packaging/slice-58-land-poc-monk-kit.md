# Slice 58 — Land PoC Monk Kit + Bootstrap Image

> Scenario: Brownfield | MoSCoW: **Must** | Status: 📋 PLANNED
> Wave: **15-O — Monk Kit Live packaging** (ADR-0001)
> Depends on: none
> Sources: `docs/adr/0001-monk-deployment-and-packaging.md` · PoC `nooga/tripwire@feat/monk-live-supabase-modal-kit` · [Monk Package Ecosystem](https://docs.monk.io/features/service-templates)

## Session bootstrap
> Re-read CLAUDE.md before starting — use values there, not hardcoded commands here.
- **Runtime source**: → CLAUDE.md § Environment
- **Test source**: → CLAUDE.md § Testing
- **Load first**: CLAUDE.md → docs/plan/invariants.md → this stub → ADR-0001

## Context
> Read before any implementation. Do not rely on conversation history alone.
- **Stage objective**: Land the PoC Monk package definitions and bootstrap image into this repo so Tripwire has an in-tree Kit (manifest + versioned YAML + bootstrap) aligned to ADR-0001 tiers — without claiming Monk deploy is shipped.
- **Depends on**: none (O0 blocks merge/VERIFIED claims, not land prototyping — see [phase-O0-governance](phase-O0-governance.md))
- **Global invariants**: → `docs/plan/invariants.md`
> Executor may diverge from plan if new evidence warrants — document deviations in PROGRESS.md before marking PASSED.
> **Retrospective:** PoC already exists on the fork branch; this slice imports and gap-closes against ADR + current `main`, then tweaks as deploy evidence arrives.

## Non-goals
> Out of scope for this slice — do not implement here.
- End-to-end cloud deploy / MVL proof (slice 59)
- Tier 2/3 coverage honesty UI or deploy signalling (slice 60)
- Monk registry publish, Capsules, or Monk-generated CI/CD (ADR out-of-scope / later)
- Changing the supported workstation Live path (`.env` + QUICKSTART)

## Added scope (2026-11-23 — from Monk integration review + reviewer round 2)

### Image tag pinning (from architect review — High severity)
`MANIFEST` and `v1.0.0.yaml` currently reference `agentvetter-bootstrap:latest`.
This floats at deploy time, breaking reproducibility.

Changes:
- `MANIFEST` image directive: `agentvetter-bootstrap:latest` → `agentvetter-bootstrap:v1.0.0`
- `v1.0.0.yaml` bootstrap-v1 image reference: same pin
- Document versioning contract in `docs/user-guide/monk-deploy.md` (slice 61)

**Local-compat:** image tag pin only affects Monk/Docker deploy path; local scripts unaffected.

### TLS cert provisioning — pre-condition for slice 59 HTTPS proof (from reviewer round 2)
Monk delegates TLS to the nginx runnable — it does NOT auto-provision certs.
Without this, slice 59 `GWT-59.4` ("HTTPS Live dashboard reads PostgREST") cannot pass.

Changes:
- `bootstrap/Dockerfile`: add Certbot step to provision Let's Encrypt cert on Hetzner VM
  before nginx starts (domain = Hetzner VM public IP or hostname)
- Alternative: add `monk.io/proxy: https` annotation to dashboard-v1 in `v1.0.0.yaml`
  if Monk's built-in HTTPS proxy is available for BYOC — verify against Monk docs

### Service dependency declarations — pre-condition for correct startup order (from reviewer round 2)
Without `depends_on`, Monk may start services in parallel; dashboard will serve before schema is applied.

Changes to `v1.0.0.yaml` group definition:
- `bootstrap-v1` → add `depends: supabase-v1`
- `dashboard-v1` → add `depends: bootstrap-v1`

Verify with: `monk validate MANIFEST` (must pass before any deploy attempt).

## Output contract
> Observable shape of completion (shape only — not exact file paths).
- **Baseline**: `test ! -f MANIFEST && test ! -f v1.0.0.yaml` on `main` today (Kit absent)
- Kit entry artifacts present and loadable: `MANIFEST` references versioned YAML; `latest.yaml` inherits immutable `*-v1` defs
- Bootstrap image build context exists (`bootstrap/Dockerfile` + baked scripts/sandbox paths)
- Tier 1–3 secret names declared in Kit surface (Tier 3 may be stubbed pass-through); entity-generated Supabase keys remain unlisted as user SECRETs
- STATUS / docs still say Monk path is Proposed / not VERIFIED

## Slice Workflow Bundle
- Slice name: `slice-58-land-poc-monk-kit`
- Files: `MANIFEST`, `common.yaml`, `latest.yaml`, `v1.0.0.yaml`, `bootstrap/Dockerfile` (+ any minimal script sync required by Dockerfile COPY)
- Exit criteria: Kit files on branch; ADR tier secret inventory reflected; workstation Live docs unchanged in meaning; static Kit checks green
- Commit pattern: `feat(slice-58): land Monk Kit package defs + bootstrap image`

## Branch
`slice/58-land-poc-monk-kit`

## Spec (GWT)

### GWT-58.1 — Kit package tree lands in-repo `@contract-shape:bounded-change`
**Given** `main` has no Tripwire Monk Kit at repo root
**When** slice 58 merges its Kit artifacts from the PoC (adapted to current `main`)
**Then** `MANIFEST` exists and `LOAD`s `common.yaml`, `v1.0.0.yaml`, and `latest.yaml`
**And** `latest.yaml` members inherit immutable `*-v1` definitions (Monk package `inherits` pattern — [Package Ecosystem](https://docs.monk.io/features/service-templates))

### GWT-58.2 — Cluster vs SaaS split matches ADR `@contract-shape:bounded-change`
**Given** the landed `v1.0.0.yaml` group
**When** an operator inspects package members
**Then** in-cluster runnables include bootstrap + dashboard (HTTPS ingress)
**And** Supabase is provisioned as a managed Monk entity, not an in-cluster Postgres container
**And** Modal is configured via secrets + bootstrap (SaaS), not as a cluster container workload

### GWT-58.3 — Secret inventory matches ADR tiers `@contract-shape:bounded-change`
**Given** ADR-0001 Tier 1 / Tier 2 / Tier 3
**When** `MANIFEST` + bootstrap `permitted-secrets` / dotenv key lists are reviewed
**Then** Tier 1 user secrets include Supabase API token + org id and Modal token id/secret
**And** Tier 2 scanner secrets (Snyk, Tessl, Cisco credential shapes) are declared
**And** Tier 3 pass-through keys (`SIE_*`, Alibaba Model Studio, `OSSPREY_API_KEY`) are **declared in Kit surface** (not silently omitted) — presence at deploy remains optional per ADR
**And** entity-generated keys (`supabase-db-password`, `supabase-anon-key`, `supabase-service-key`) are **not** listed as operator-supplied `SECRET` lines

### GWT-58.4 — Bootstrap image builds with pinned schema + baked scripts `@contract-shape:bounded-change`
**Given** the landed `bootstrap/Dockerfile`
**When** the image is built in CI or locally
**Then** the image contains Node + Modal CLI + baked `scripts/` + `sandbox/` as in the PoC intent
**And** the Tripwire schema is **pinned at image build time** (baked COPY or digests-locked path) — not an opportunistic live fetch from a mutable URL as the sole source of truth
**And** bootstrap bash remains POSIX-safe for Monk’s `/bin/sh` execution (no bashisms that die on line 1)

### GWT-58.4b — Bootstrap build fails closed on broken context `@contract-shape:bounded-change`
**Given** a deliberately broken Dockerfile COPY path or missing baked script
**When** the bootstrap image build runs
**Then** the build fails (non-zero) and does not produce a silently incomplete image

### GWT-58.5 — Honesty: not shippable via Monk yet `@contract-shape:unbounded-preservation`
**Given** Kit files exist in the repo
**When** STATUS / README / QUICKSTART are checked
**Then** no public claim states Tripwire is immediately deployable or redistributable via Monk
**And** the workstation Live path remains the supported path until slice 59 is VERIFIED

## Acceptance criteria (short-form)
- [ ] GWT-58.1–58.5 satisfied
- [ ] PoC ↔ `main` drift resolved or logged (schema URL pin, region defaults, script paths)
- [ ] Static validation of Kit YAML/MANIFEST documented in gate evidence
- [ ] Docs honesty preserved (Proposed, not VERIFIED)

## Before-Checks [GATE]
- [ ] Branch `slice/58-land-poc-monk-kit` created from current `main`
- [ ] PoC tree reviewed (`MANIFEST`, `v1.0.0.yaml`, `bootstrap/Dockerfile`)
- [ ] ADR-0001 tier table re-read
- [ ] Prior session recovery checked (if resuming)

## TDD Execution
- **Infra / package-def slice** → characterization + contract tests first (MANIFEST/YAML shape, secret inventory assertions); image build smoke where feasible
- Sequence: RED → GREEN → REFACTOR → VERIFY
- Prefer small pure checkers over full Monk runtime in unit tests

## After-Checks [GATE]
- [ ] Code committed with `feat(slice-58): ...`
- [ ] Specification coverage: every GWT clause has ≥1 test or documented VERIFIED probe
- [ ] Branch coverage: apply repo `./scripts/quality-gates.sh` to any new testable code; Kit YAML-only paths may use contract tests
- [ ] Complexity evidence: policy `reporting` for Kit YAML; any new Python helpers use repository-native complexity tool from quality-gates — record tool/scope/command in gate-evidence
- [ ] Acceptance criteria met
- [ ] Docs audit: STATUS honesty; ARCHITECTURE link to ADR-0001 if missing; no false “shipped via Monk” claims

### Closing Gates
- [ ] `nw-at-completeness-check` — AT completeness audit (slice close gate #8)
- [ ] `nw-software-crafter-reviewer` — code quality + TDD discipline review (slice close gate #9)
- [ ] `nw-platform-architect-reviewer` — Kit/package/deploy surface review (infra)
- [ ] `nw-gate-evidence-validator` — all 9 gate-evidence conditions pass
- [ ] `/verify-slice` — holistic evidence verdict COMPLETE (final closing gate)

## Gate Status
📋 PLANNED

## Session Metrics
| Metric | Value |
|--------|-------|
| Estimated Pomos | 2 (~50 min) — includes PoC↔main drift + first build failure iteration |
| Execution time | — |
| Blockers encountered | — |
| Next-session notes | Import from PoC; tweak after first deploy feedback |
