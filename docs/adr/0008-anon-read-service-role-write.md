# ADR-0008: Anon read, service-role write

- **Status:** Accepted
- **Date:** 2026-08-01
- **Deciders:** AgentVetter maintainers
- **Tags:** security, rls, auth, supabase

## Context

Horizon A has no multi-user identity product. The browser dashboard must read
scan data; the CLI and Modal sandbox must write it. Putting the Supabase
`service_role` key in browser-facing config would let anyone mutate or dump
the project.

Supabase RLS defaults can lock tables without SELECT policies, which silently
breaks the anon dashboard while the CLI (service role, bypasses RLS) still
works.

## Decision

Split keys by trust boundary.

- **Writes:** `SUPABASE_SERVICE_ROLE_KEY` on the CLI and in Modal secret
  `agentvetter-supabase`. Service role bypasses RLS.
- **Browser reads:** `SUPABASE_ANON_KEY` with RLS enabled and `anon` SELECT
  policies + GRANTs on `items`, `scan_runs`, `scan_run_scanners`, `findings`.
- **Never** put `service_role` in `agentvetter-dashboard.config.js`. Prefer
  `serve-dashboard.mjs` local proxy when the anon key is omitted.
- **Never** toggle RLS in the Supabase UI. Apply `db/schema.sql` via
  `agentvetter setup --force` so policies and GRANTs land together.
- No end-user login (Auth0/Clerk/Keycloak) for Horizon A. Shared-instance auth
  is deferred to future packaging work (ADR 0001 reserved; draft under review).

Anon SELECT is `using (true)` — any holder of the project anon key can read
all scan rows. Treat the Supabase project as a single-operator trust domain.

### Amendment (2026-11-23): judge panel tables are not anon-readable

`judge_panel_runs` and `judge_panel_judgements` hold raw model responses that
can echo scanned secrets. The dashboard never reads them, so they have no anon
policy or GRANT and are service-role only. Finding snippets and scanner console
output stay anon-readable (the dashboard shows them), but the sandbox masks
secret-like values before writing them (`sandbox/redact.py`).

## Consequences

- Leaking the anon key leaks findings for that project; leaking service role
  leaks write access. `.env` and dashboard config stay gitignored.
- Operators who enable RLS in the dashboard without re-applying schema see a
  “broken Live” that is actually a GRANT/policy miss
  (`./scripts/check-supabase.sh`).
- Multi-tenant or shared-team instances need a new ADR before they are safe.

## Alternatives considered

### A. Service role in the browser

Rejected: unrestricted write from any visitor of the dashboard origin.

### B. Authenticated-only reads from day one

Rejected: no identity product in Horizon A; would block the walking skeleton.

## References

- `db/schema.sql` RLS + GRANT block
- [docs/user-guide/supabase-setup.md](../user-guide/supabase-setup.md)
- [prototypes/README.md](../../prototypes/README.md)
