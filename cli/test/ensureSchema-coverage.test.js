/**
 * Coverage tests for probeSchema / applySchema / ensureSchema.
 *
 * Author: swami
 * Created: 2026-08-02
 * Scope: missing/ready probe, applySchema validation, ensureSchema ready/applied paths
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  applySchema,
  ensureSchema,
  isMissingSchemaError,
  itemsTypeCheckAllowsPackage,
  probeSchema,
  schemaNeedsApply,
  typeCheckStateFromDef,
  usablePostgresUrl,
} from '../src/ensureSchema.js';

function mockSupabase({ itemsError = null, colError = null, panelError = null } = {}) {
  return {
    from(table) {
      return {
        select() {
          return {
            limit: async () => {
              if (table === 'items') return { error: itemsError };
              if (table === 'scan_run_scanners') return { error: colError };
              if (table === 'judge_panel_runs') return { error: panelError };
              return { error: null };
            },
          };
        },
      };
    },
  };
}

test('given items missing when probeSchema then missing', async () => {
  // -- Given --
  const sb = mockSupabase({
    itemsError: { code: 'PGRST205', message: 'Could not find the table' },
  });

  // -- When / Then --
  assert.equal(await probeSchema(sb), 'missing');
});

test('given completed_at missing when probeSchema then missing', async () => {
  // -- Given --
  const sb = mockSupabase({
    colError: { code: 'PGRST204', message: "Could not find the 'completed_at' column" },
  });

  // -- When / Then --
  assert.equal(await probeSchema(sb), 'missing');
});

test('given judge_panel_runs missing when probeSchema then missing', async () => {
  /**
   * Scenario: DBs created before slice 67 lack judge panel tables.
   * Slice: 67 — judge_panel_runs probe
   *
   * Given items and scan_run_scanners are ready but judge_panel_runs is absent,
   * When probeSchema runs,
   * Then it reports missing so ensureSchema applies db/schema.sql.
   */
  // -- Given --
  const sb = mockSupabase({
    panelError: { code: 'PGRST205', message: 'Could not find the table' },
  });

  // -- When / Then --
  assert.equal(await probeSchema(sb), 'missing');
});

test('given ready tables when probeSchema then ready', async () => {
  // -- Given / When / Then --
  assert.equal(await probeSchema(mockSupabase()), 'ready');
});

test('given non-schema probe error when probeSchema then throws', async () => {
  // -- Given --
  const sb = mockSupabase({ itemsError: { message: 'JWT expired' } });

  // -- When / Then --
  await assert.rejects(() => probeSchema(sb), /Supabase probe failed/);
});

test('given completed_at probe auth failure when probeSchema then aborts rather than reporting ready', async () => {
  // -- Given --
  const sb = mockSupabase({ colError: { message: 'JWT expired' } });

  // -- When / Then --
  await assert.rejects(() => probeSchema(sb), /Supabase probe failed: JWT expired/);
});

test('given empty db url when applySchema then throws', async () => {
  // -- Given / When / Then --
  await assert.rejects(() => applySchema({ dbUrl: '' }), /Set SUPABASE_DB_URL/);
});

test('given http url when applySchema then throws', async () => {
  // -- Given / When / Then --
  await assert.rejects(
    () => applySchema({ dbUrl: 'https://example.com' }),
    /postgresql:\/\//
  );
});

test('given ready probe when ensureSchema then ready without apply', async () => {
  // -- Given / When / Then --
  assert.deepEqual(await ensureSchema({ supabase: mockSupabase(), force: false }), {
    status: 'ready',
  });
});

test('given stale items type check when ensureSchema then applies schema', async () => {
  /**
   * Scenario: existing DBs created before slice 64 still reject type=package.
   * Slice: 64 — items_type_check widen
   *
   * Given HTTP tables are ready but items_type_check does not allow package,
   * When ensureSchema runs,
   * Then db/schema.sql is applied so package inserts can succeed.
   */
  // -- Given --
  let applyCalls = 0;

  // -- When --
  const actual = await ensureSchema({
    supabase: mockSupabase(),
    force: false,
    probeItemsTypeCheckFn: async () => 'stale',
    applySchemaFn: async () => {
      applyCalls += 1;
    },
  });

  // -- Then --
  assert.equal(actual.status, 'applied', 'stale type CHECK must trigger schema apply');
  assert.equal(applyCalls, 1, 'schema apply should run once for a stale type CHECK');
});

test('given constraint def without package when itemsTypeCheckAllowsPackage then false', () => {
  // -- Given --
  const def = "CHECK ((type = ANY (ARRAY['skill'::text, 'mcp_server'::text])))";

  // -- When / Then --
  assert.equal(itemsTypeCheckAllowsPackage(def), false);
});

test('given constraint def with package when itemsTypeCheckAllowsPackage then true', () => {
  // -- Given --
  const def = "CHECK ((type = ANY (ARRAY['skill'::text, 'mcp_server'::text, 'package'::text])))";

  // -- When / Then --
  assert.equal(itemsTypeCheckAllowsPackage(def), true);
});

test('given blank or non-postgres url when usablePostgresUrl then null', () => {
  // -- Given / When / Then --
  assert.equal(usablePostgresUrl(''), null);
  assert.equal(usablePostgresUrl('  '), null);
  assert.equal(usablePostgresUrl('https://example.com'), null);
  assert.equal(usablePostgresUrl('postgresql://user:pass@localhost/db'), 'postgresql://user:pass@localhost/db');
});

test('given constraint defs when typeCheckStateFromDef then ready or stale', () => {
  // -- Given / When / Then --
  assert.equal(typeCheckStateFromDef("CHECK ((type = ANY (ARRAY['skill'::text])))"), 'stale');
  assert.equal(
    typeCheckStateFromDef("CHECK ((type = ANY (ARRAY['skill'::text, 'package'::text])))"),
    'ready',
  );
});

test('given ready tables and ready type check when schemaNeedsApply then false', () => {
  // -- Given / When / Then --
  assert.equal(schemaNeedsApply(false, 'ready', 'ready'), false);
  assert.equal(schemaNeedsApply(false, 'ready', 'skipped'), false);
  assert.equal(schemaNeedsApply(false, 'ready', 'stale'), true);
  assert.equal(schemaNeedsApply(true, 'ready', 'ready'), true);
});

test('given missing schema when ensureSchema without db url then throws on apply', async () => {
  // -- Given --
  const sb = mockSupabase({
    itemsError: { code: 'PGRST205', message: 'Could not find the table' },
  });
  const prev = process.env.SUPABASE_DB_URL;
  delete process.env.SUPABASE_DB_URL;

  // -- When / Then --
  try {
    await assert.rejects(() => ensureSchema({ supabase: sb, force: false }), /SUPABASE_DB_URL/);
  } finally {
    if (prev !== undefined) process.env.SUPABASE_DB_URL = prev;
  }
});

test('given fake Client when applySchema then connects and queries', async () => {
  // -- Given --
  const calls = { connect: 0, query: 0, end: 0 };
  class FakeClient {
    constructor(opts) {
      this.opts = opts;
    }
    async connect() {
      calls.connect += 1;
    }
    async query() {
      calls.query += 1;
    }
    async end() {
      calls.end += 1;
    }
  }

  // -- When --
  await applySchema({
    dbUrl: 'postgresql://u:p@127.0.0.1:5432/db',
    ClientImpl: FakeClient,
  });

  // -- Then --
  assert.deepEqual(calls, { connect: 1, query: 1, end: 1 });
});

test('given PGCONNECT_TIMEOUT_MS of zero when applySchema then falls back to 20 s timeout', async () => {
  // -- Given --
  const prev = process.env.PGCONNECT_TIMEOUT_MS;
  process.env.PGCONNECT_TIMEOUT_MS = '0';
  let seenTimeout;
  class CapturingClient {
    constructor(opts) {
      seenTimeout = opts.connectionTimeoutMillis;
    }
    async connect() {}
    async query() {}
    async end() {}
  }

  try {
    // -- When --
    await applySchema({ dbUrl: 'postgresql://u:p@127.0.0.1:5432/db', ClientImpl: CapturingClient });
  } finally {
    if (prev === undefined) delete process.env.PGCONNECT_TIMEOUT_MS;
    else process.env.PGCONNECT_TIMEOUT_MS = prev;
  }

  // -- Then --
  assert.equal(seenTimeout, 20000);
});

test('given Client connect ENOTFOUND when applySchema then hint in error', async () => {
  // -- Given --
  class FailingClient {
    async connect() {
      const err = new Error('getaddrinfo ENOTFOUND');
      err.code = 'ENOTFOUND';
      throw err;
    }
    async query() {}
    async end() {}
  }

  // -- When / Then --
  await assert.rejects(
    () =>
      applySchema({
        dbUrl: 'postgresql://u:p@db.example.co:5432/db',
        ClientImpl: FailingClient,
      }),
    /Session pooler/
  );
});

test('given force apply when ensureSchema then applied', async () => {
  // -- Given --
  let applyCalls = 0;
  const sb = mockSupabase();

  // -- When --
  const result = await ensureSchema({
    supabase: sb,
    force: true,
    applySchemaFn: async () => {
      applyCalls += 1;
    },
  });

  // -- Then --
  assert.equal(result.status, 'applied');
  assert.equal(applyCalls, 1);
});

test('isMissingSchemaError with null or undefined returns false', () => {
  /**
   * Scenario: guard against falsy errors short-circuits the regex.
   * Slice: coverage — ensureSchema.js line 15 true branch
   */
  // -- Given / When / Then --
  assert.equal(isMissingSchemaError(null), false);
  assert.equal(isMissingSchemaError(undefined), false);
  assert.equal(isMissingSchemaError(0), false);
});

test('given ECONNREFUSED when applySchema then error hints at Session pooler', async () => {
  /**
   * Scenario: pgConnectHint fires when Postgres refuses the connection.
   * Slice: coverage — ensureSchema.js lines 53-55
   *
   * Given a ClientImpl whose connect() throws ECONNREFUSED,
   * When applySchema is called with a valid postgresql:// URL,
   * Then the thrown error message contains the Session pooler hint.
   */
  // -- Given --
  class EconnClient {
    async connect() {
      const err = new Error('connect ECONNREFUSED 127.0.0.1:5432');
      err.code = 'ECONNREFUSED';
      throw err;
    }
    async query() {}
    async end() {}
  }

  // -- When / Then --
  await assert.rejects(
    () => applySchema({ dbUrl: 'postgresql://u:p@db.example.co:5432/db', ClientImpl: EconnClient }),
    /Session pooler/,
  );
});

test('given apply ok but still missing when ensureSchema then throws', async () => {
  // -- Given --
  const sb = mockSupabase({
    itemsError: { code: 'PGRST205', message: 'Could not find the table' },
  });

  // -- When / Then --
  await assert.rejects(
    () =>
      ensureSchema({
        supabase: sb,
        force: true,
        applySchemaFn: async () => {},
      }),
    /still not queryable/
  );
});
