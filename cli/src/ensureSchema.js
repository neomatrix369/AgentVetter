import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import pg from 'pg';
import { getSupabase } from './supabaseClient.js';

const { Client } = pg;

export function schemaPath() {
  return join(dirname(fileURLToPath(import.meta.url)), '../../db/schema.sql');
}

/** True when PostgREST/Postgres says tables or columns are missing. */
export function isMissingSchemaError(error) {
  if (!error) return false;
  const blob = `${error.code || ''} ${error.message || ''} ${error.details || ''}`;
  return /PGRST20[45]|could not find the (table|.*column)|relation ["'].*["'] does not exist|schema cache/i.test(blob);
}

async function probeSelect(supabase, table, columns) {
  const { error } = await supabase.from(table).select(columns).limit(1);
  if (!error) return 'ready';
  if (isMissingSchemaError(error)) return 'missing';
  throw new Error(`Supabase probe failed: ${error.message || error.code || 'unknown error'}`);
}

/**
 * Probe via HTTP API whether core tables and migration columns are queryable.
 * Checks `items` (table existence), `scan_run_scanners.completed_at`
 * (column-level migration), and `judge_panel_runs` (slice 67 panel tables),
 * so `ensureSchema --force` is triggered when the DB has stale columns/tables.
 * @returns {'ready'|'missing'}
 */
export async function probeSchema(supabase = getSupabase()) {
  const probes = [
    ['items', 'id'],
    ['scan_run_scanners', 'completed_at'],
    ['judge_panel_runs', 'id'],
  ];
  for (const [table, columns] of probes) {
    if ((await probeSelect(supabase, table, columns)) === 'missing') return 'missing';
  }
  return 'ready';
}

/** SSL options for a Postgres URL. Local servers have no TLS; remote hosts must verify the cert.
 *  Supabase pooler hosts use a self-signed chain — skip cert verification for them only. */
export function pgSslConfig(url) {
  if (url.includes('localhost') || url.includes('127.0.0.1')) return false;
  if (url.includes('.pooler.supabase.com')) return { rejectUnauthorized: false };
  return { rejectUnauthorized: true };
}

/** True when a Postgres CHECK definition already allows items.type = package. */
export function itemsTypeCheckAllowsPackage(def) {
  return /'package'/.test(String(def || ''));
}

/**
 * Trim and validate a Postgres connection URL. Returns null when unusable.
 * @param {string|undefined|null} dbUrl
 * @returns {string|null}
 */
export function usablePostgresUrl(dbUrl) {
  const url = (dbUrl || '').trim();
  if (!url) return null;
  if (!/^postgres(ql)?:\/\//i.test(url)) return null;
  return url;
}

/** Map a live CHECK definition to ready/stale for package support. */
export function typeCheckStateFromDef(def) {
  return itemsTypeCheckAllowsPackage(def) ? 'ready' : 'stale';
}

/**
 * Apply schema when tables are missing or the live items.type CHECK is pre-package.
 * @param {boolean} force
 * @param {'ready'|'missing'} tableState
 * @param {'ready'|'stale'|'skipped'} typeState
 */
export function schemaNeedsApply(force, tableState, typeState) {
  if (force) return true;
  if (tableState !== 'ready') return true;
  return typeState === 'stale';
}

async function fetchItemsTypeCheckDef(client) {
  const { rows } = await client.query(
    `SELECT pg_get_constraintdef(oid) AS def
     FROM pg_constraint
     WHERE conrelid = 'public.items'::regclass AND conname = 'items_type_check'`
  );
  return rows[0]?.def || '';
}

/**
 * Read live items_type_check. Skipped in the Node test runner and when DB URL is unset.
 * @returns {Promise<'ready'|'stale'|'skipped'>}
 */
export async function probeItemsTypeCheck({
  dbUrl = process.env.SUPABASE_DB_URL,
  ClientImpl = Client,
} = {}) {
  if (process.env.NODE_TEST_CONTEXT) return 'skipped';
  const url = usablePostgresUrl(dbUrl);
  if (!url) return 'skipped';
  const client = new ClientImpl({
    connectionString: url, ssl: pgSslConfig(url), connectionTimeoutMillis: 5000,
  });
  try {
    await client.connect();
    return typeCheckStateFromDef(await fetchItemsTypeCheckDef(client));
  } catch {
    return 'skipped';
  } finally {
    await client.end().catch(() => {});
  }
}

function pgConnectHint(code) {
  return code === 'ENOTFOUND' || code === 'ECONNREFUSED'
    ? ' Check SUPABASE_DB_URL host (Project Settings → Database). Prefer the Session pooler URI if db.<ref>.supabase.co does not resolve, and confirm the project is not paused.'
    : '';
}

export async function applySchema({
  dbUrl = process.env.SUPABASE_DB_URL,
  ClientImpl = Client,
} = {}) {
  const url = (dbUrl || '').trim();
  if (!url) {
    throw new Error(
      'AgentVetter tables are missing. Set SUPABASE_DB_URL (postgresql://…) in .env, then run `agentvetter setup` ' +
        '(or re-run scan — it auto-bootstraps). HTTP SUPABASE_URL alone cannot apply DDL.'
    );
  }
  if (!/^postgres(ql)?:\/\//i.test(url)) {
    throw new Error('SUPABASE_DB_URL must be a postgresql:// connection string.');
  }

  const sql = readFileSync(schemaPath(), 'utf8');
  const client = new ClientImpl({ connectionString: url, ssl: pgSslConfig(url) });
  try {
    await client.connect();
    await client.query(sql);
  } catch (err) {
    const hint = pgConnectHint(err && err.code);
    throw new Error(`Failed to apply schema via SUPABASE_DB_URL: ${err.message}.${hint}`, { cause: err });
  } finally {
    await client.end().catch(() => {});
  }
}

/**
 * Ensure schema exists. Applies db/schema.sql when tables are missing or
 * items.type CHECK has not been widened to include `package`.
 * @returns {{ status: 'ready'|'applied' }}
 */
export async function ensureSchema({
  force = false,
  supabase = getSupabase(),
  applySchemaFn = applySchema,
  probeItemsTypeCheckFn = probeItemsTypeCheck,
} = {}) {
  const tableState = force ? 'missing' : await probeSchema(supabase);
  const typeState = force ? 'stale' : await probeItemsTypeCheckFn();
  if (!schemaNeedsApply(force, tableState, typeState)) return { status: 'ready' };

  console.error('[agentvetter] Applying db/schema.sql to Supabase…');
  await applySchemaFn();

  const after = await probeSchema(supabase);
  if (after !== 'ready') {
    throw new Error(
      'Schema apply finished but `items` is still not queryable. Check SUPABASE_DB_URL points at the same project as SUPABASE_URL, and PostgREST schema cache has refreshed.'
    );
  }
  console.error('[agentvetter] Schema ready.');
  return { status: 'applied' };
}
