# Phase O0 — Wave O Governance (Monk Kit)

> Scenario: Brownfield | MoSCoW: **Must** | Status: 📋 PLANNED
> Wave: **15-O — Monk Kit Live packaging**
> Phase label: **O0** (not a global `slice-N` — no renumber of 58–61)
> Depends on: none
> ADR: [`docs/adr/0001-monk-deployment-and-packaging.md`](../../../adr/0001-monk-deployment-and-packaging.md)

## Session bootstrap
- **Load first**: CLAUDE.md → docs/plan/invariants.md → ADR-0001 → this stub → slices 58–61

## Context
- **Stage objective**: Close Wave O governance — ADR Accept HITL, open-question DECISIONS, and tracker honesty — so MVL **VERIFIED** claims and merge of “shipped via Monk” docs have a clear gate.
- **Depends on**: none
- **Global invariants**: → `docs/plan/invariants.md`
> **Rule (mirrors H0):** O0 **blocks merge / VERIFIED claims**, **not Kit land prototyping**. Slice **58** may proceed on a branch while O0 is open. Slice **59** must not mark STATUS Monk MVL **VERIFIED** until O0’s ADR-0001 **Accepted** check is done. Slice **60** must not start UI for partial-coverage signalling until the signalling-surface DECISIONS row exists (can be recorded in O0).

## Monk install prerequisites (added 2026-11-23)
Before O0 governance work can proceed, the local Monk installation must be clean:

1. **Uninstall Homebrew Monk** (v3.21.3):
   ```bash
   brew uninstall monk
   rm -rf ~/.monk
   ```
   Verify: `which monk` returns nothing.

2. **Install Monk as agent plugin** (not Homebrew):
   ```bash
   curl -fsSL https://get.monk.io/stable/plugin | sh
   ```
   Then authenticate in Claude Code: `/mcp` → choose monk → browser auth flow.

3. **Install in IDE** (Claude Code and/or Cursor):
   - Claude Code: `/plugin marketplace add monk-io/monk-plugin` → `/reload-plugins` → `/mcp`
   - Cursor: `/add-plugin https://github.com/monk-io/monk-plugin` → restart → Settings → Tools & MCP → sign in

> These are setup prerequisites — not automated gate evidence. Operator attests completion.

## Non-goals
- Landing Kit YAML / bootstrap image (slice 58)
- Running the MVL deploy (slice 59)
- Implementing Tier 2/3 plumbing or docs coexistence (60–61)
- Renumbering 58–61 to `00–…`
- Capsules / Monk CI/CD / registry (Won't for O)

## Output contract
- **Baseline**: ADR-0001 Proposed; Wave O stubs 58–61 + nw-review follow-ups on branch `docs/monk-kit-wave-o`
- ADR-0001 status recorded as **Accepted** (HITL) or explicitly deferred with owner + unblock condition
- DECISIONS row for partial-coverage primary surface (`deploy_summary` | `dashboard` | `both`) — or deferred with owner slice 60 Before-Check still armed
- TRAIL/PROGRESS/README show **O0** then 58–61; this stub linked
- Workstation Live honesty unchanged

## Slice Workflow Bundle
- Phase name: `phase-O0-governance`
- Files: ADR-0001 status, DECISIONS, TRAIL, PROGRESS, STATUS (honesty only), this stub
- Exit criteria: O0 ✅; ADR Accept resolved; signalling DECISIONS resolved or consciously deferred; trackers link this stub
- Commit pattern: `docs(O0): Wave O Monk Kit governance …`

## Branch
`docs/monk-kit-wave-o` (plan) or follow-on docs branch — not required to be `slice/58-…`.

## Spec (GWT)

### GWT-O0.1 — ADR Accept HITL resolved
**Given** ADR-0001 is the intent record for Monk Kit packaging
**When** O0 closes
**Then** ADR-0001 status is **Accepted** (human) **or** DECISIONS records deferral with owner and “blocks 59 VERIFIED until Accept”
**And** invariants / slice 59 Before-Check remain consistent with that decision

### GWT-O0.2 — Partial-coverage signalling surface decided or deferred
**Given** ADR-0001 open question on how MVL signals partial scanner coverage
**When** O0 closes
**Then** DECISIONS names primary surface `deploy_summary` | `dashboard` | `both`
**Or** DECISIONS defers to slice 60 Before-Check with explicit owner (still blocking 60 UI)

### GWT-O0.3 — Trackers name O0 without renumbering product slices
**Given** Wave O plan artifacts
**When** TRAIL / PROGRESS / plan README are read
**Then** O0 appears as governance Must before 58–61
**And** product work remains global slices **58–61** (not `slice-00`)

### GWT-O0.4 — Prototyping vs merge rule is explicit
**Given** an executor wants to start slice 58
**When** they read this stub / TRAIL Wave O
**Then** land/prototyping of 58 may proceed while O0 is 📋/🔨
**And** STATUS must not claim Monk MVL VERIFIED until O0 Accept path + slice 59 evidence are done

## Before-Checks [GATE]
- [ ] Branch for plan docs available (`docs/monk-kit-wave-o` or equivalent)
- [ ] Slices 58–61 stubs exist
- [ ] nw-review follow-ups applied (or listed as remaining)

## After-Checks [GATE]
- [ ] O0 ✅ in TRAIL + PROGRESS
- [ ] GWT-O0.1–O0.4 satisfied
- [ ] This stub linked from TRAIL O0 row
- [ ] No “deployable via Monk” claim without VERIFIED evidence

### Closing Gates
- [ ] Maintainer HITL on ADR Accept (and signalling if not deferred)
- [ ] Docs consistency check (STATUS ↔ ADR status)
- [ ] `/verify-slice` N/A for phase-only — close via TRAIL/PROGRESS + DECISIONS

## Gate Status
📋 PLANNED

## Session Metrics
| Metric | Value |
|--------|-------|
| Estimated Pomos | 1 (~25 min) |
| Next-session notes | Prefer Accept ADR-0001 in O0 before scheduling slice 59 VERIFIED run |
