/**
 * Slice 6 — characterization of runScan idempotency + Modal spawn args.
 * Locks current behaviour with mocked Supabase + spawn (no live Modal).
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { runScan } from '../src/orchestrator.js';
import { spawnScanSandbox } from '../src/modalClient.js';
import { hashLocalPath } from '../src/hash.js';

function makeThenable(value) {
  return {
    then(resolve, reject) {
      return Promise.resolve(value).then(resolve, reject);
    },
  };
}

/**
 * Minimal fluent Supabase stub for upsertItem + runScan paths.
 * `byHashItem` — when set, content_hash lookup returns cached item.
 */
function createSupabaseStub({ byHashItem = null, itemId = 'item-1', runId = 'run-1' } = {}) {
  const calls = { insertScanRuns: 0, insertItems: 0, insertedItems: [], updateItems: 0, rpc: [] };

  function chain(terminal) {
    const api = {
      select() { return api; },
      eq() { return api; },
      order() { return api; },
      limit() { return api; },
      single() { return makeThenable(terminal); },
      maybeSingle() { return makeThenable(terminal); },
      then: makeThenable(terminal).then.bind(makeThenable(terminal)),
    };
    return api;
  }

  const supabase = {
    calls,
    from(table) {
      return {
        select() {
          if (table === 'items') {
            // content_hash lookup → maybeSingle; identifier lookup → array
            return {
              eq(col) {
                if (col === 'content_hash') {
                  return {
                    maybeSingle: () => makeThenable({ data: byHashItem, error: null }),
                  };
                }
                if (col === 'identifier') {
                  return {
                    order() {
                      return {
                        limit() {
                          return makeThenable({ data: [], error: null });
                        },
                      };
                    },
                  };
                }
                return chain({ data: null, error: null });
              },
            };
          }
          return chain({ data: null, error: null });
        },
        insert(row) {
          if (table === 'items') {
            calls.insertItems += 1;
            calls.insertedItems.push(row);
            return {
              select() {
                return {
                  single: () => makeThenable({
                    data: { id: itemId, ...row },
                    error: null,
                  }),
                };
              },
            };
          }
          if (table === 'scan_runs') {
            calls.insertScanRuns += 1;
            return {
              select() {
                return {
                  single: () => makeThenable({
                    data: { id: runId, ...row },
                    error: null,
                  }),
                };
              },
            };
          }
          if (table === 'scan_batches') {
            return {
              select() {
                return {
                  single: () => makeThenable({
                    data: { id: 'batch-1', ...row },
                    error: null,
                  }),
                };
              },
            };
          }
          return chain({ data: null, error: null });
        },
        update() {
          if (table === 'items') calls.updateItems += 1;
          return {
            eq() {
              return {
                select() {
                  return {
                    single: () => makeThenable({
                      data: byHashItem || { id: itemId },
                      error: null,
                    }),
                  };
                },
              };
            },
          };
        },
      };
    },
    rpc(name, args) {
      calls.rpc.push({ name, args });
      return makeThenable({ data: null, error: null });
    },
  };
  return supabase;
}

async function withFixtureDir(fn) {
  const dir = await mkdtemp(path.join(tmpdir(), 'agentvetter-orch-'));
  await writeFile(path.join(dir, 'SKILL.md'), '# fixture\n');
  try {
    return await fn(dir);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

test('given unchanged content_hash when runScan without force then skips spawn', async () => {
  await withFixtureDir(async (dir) => {
    const contentHash = await hashLocalPath(dir);
    const item = {
      id: 'cached-item',
      identifier: dir,
      content_hash: contentHash,
    };
    const supabase = createSupabaseStub({ byHashItem: item, itemId: item.id });
    const spawnCalls = [];

    await runScan(
      [{ target: dir, type: 'skill', locus: 'local', avail: 'source_on_disk' }],
      {
        force: false,
        ensureSchemaFn: async () => {},
        getSupabaseFn: () => supabase,
        spawnFn: async (args) => { spawnCalls.push(args); },
      }
    );

    assert.equal(spawnCalls.length, 0, 'unchanged content must not spawn sandbox when not forced');
    assert.equal(supabase.calls.insertScanRuns, 0, 'skip path must not insert scan_runs');
  });
});

test('given unchanged content_hash when runScan with force then spawns with expected args shape', async () => {
  await withFixtureDir(async (dir) => {
    const contentHash = await hashLocalPath(dir);
    const item = {
      id: 'cached-item',
      identifier: dir,
      content_hash: contentHash,
    };
    const runId = 'forced-run';
    const supabase = createSupabaseStub({ byHashItem: item, itemId: item.id, runId });
    const spawnCalls = [];

    await runScan(
      [{ target: dir, type: 'skill', locus: 'local', avail: 'source_on_disk' }],
      {
        force: true,
        ensureSchemaFn: async () => {},
        getSupabaseFn: () => supabase,
        spawnFn: async (args) => { spawnCalls.push(args); },
      }
    );

    assert.equal(spawnCalls.length, 1, 'force must spawn even when content hash is unchanged');
    assert.equal(supabase.calls.insertScanRuns, 1);
    assert.deepEqual(spawnCalls[0], {
      target: dir,
      itemType: 'skill',
      itemId: item.id,
      scanRunId: runId,
      packPath: null,
    });
  });
});

test('given new content when runScan then inserts run and spawns sandbox', async () => {
  await withFixtureDir(async (dir) => {
    const supabase = createSupabaseStub({ byHashItem: null, itemId: 'new-item', runId: 'new-run' });
    const spawnCalls = [];

    await runScan(
      [{ target: dir, type: 'mcp_server', locus: 'local', avail: 'source_on_disk' }],
      {
        force: false,
        ensureSchemaFn: async () => {},
        getSupabaseFn: () => supabase,
        spawnFn: async (args) => { spawnCalls.push(args); },
      }
    );

    assert.equal(supabase.calls.insertItems, 1);
    assert.equal(supabase.calls.insertScanRuns, 1);
    assert.equal(spawnCalls.length, 1);
    assert.equal(spawnCalls[0].itemType, 'mcp_server');
    assert.equal(spawnCalls[0].itemId, 'new-item');
    assert.equal(spawnCalls[0].scanRunId, 'new-run');
    assert.equal(spawnCalls[0].target, dir);
  });
});

test('given git artifact identity when runScan then persists its identifier and name', async () => {
  await withFixtureDir(async (dir) => {
    const supabase = createSupabaseStub({ byHashItem: null });
    const target = {
      target: dir,
      type: 'skill',
      locus: 'local',
      avail: 'source_on_disk',
      identifier: 'org/repo/skills/foo',
      name: 'foo',
    };

    await runScan([target], {
      ensureSchemaFn: async () => {},
      getSupabaseFn: () => supabase,
      spawnFn: async () => {},
      routeFn: async () => {},
    });

    assert.equal(supabase.calls.insertedItems[0].identifier, target.identifier,
      'git artifacts must retain their repo-scoped identifier');
    assert.equal(supabase.calls.insertedItems[0].name, target.name,
      'git artifacts must retain the artifact basename as their name');
  });
});

test('GWT-62.3: multi-artifact runScan spawns once per target with distinct identifiers', async () => {
  await withFixtureDir(async (skillDir) => {
    await withFixtureDir(async (mcpDir) => {
      const supabase = createSupabaseStub({ byHashItem: null });
      const spawnCalls = [];
      const targets = [
        {
          target: skillDir,
          type: 'skill',
          locus: 'local',
          avail: 'source_on_disk',
          identifier: 'org/repo/skills/foo',
          name: 'foo',
        },
        {
          target: mcpDir,
          type: 'mcp_server',
          locus: 'local',
          avail: 'source_on_disk',
          identifier: 'org/repo/mcp/bar',
          name: 'bar',
        },
      ];

      await runScan(targets, {
        ensureSchemaFn: async () => {},
        getSupabaseFn: () => supabase,
        spawnFn: async (args) => { spawnCalls.push(args); },
        routeFn: async () => {},
      });

      assert.equal(spawnCalls.length, 2, 'each discovered artifact must get its own sandbox spawn');
      const types = spawnCalls.map(call => call.itemType).sort();
      assert.deepEqual(types, ['mcp_server', 'skill']);
      const ids = supabase.calls.insertedItems.map(item => item.identifier);
      assert.deepEqual(ids.sort(), ['org/repo/mcp/bar', 'org/repo/skills/foo']);
      assert.ok(ids.every(id => id.startsWith('org/repo/')),
        'identifiers must share the org/repo prefix');
      // Data-flow review: identity must round-trip in org/repo/<relpath> shape for card signature
      assert.ok(ids.every(id => /^[^/]+\/[^/]+\/.+$/.test(id)),
        'persisted identifier must be org/repo/<relpath> for dashboard org/repo signature');
      const names = supabase.calls.insertedItems.map(item => item.name).sort();
      assert.deepEqual(names, ['bar', 'foo'],
        'persisted name must remain artifact basename for card title');
    });
  });
});

test('spawnScanSandbox invokes modal run scan_app.py with expected argv (mocked child_process)', async () => {
  const spawned = [];
  const fakeProc = new EventEmitter();
  // exit asynchronously so listeners attach first
  queueMicrotask(() => fakeProc.emit('exit', 0));

  await spawnScanSandbox({
    target: 'fixtures/mcp/vuln-command-injection-server',
    itemType: 'mcp_server',
    itemId: 'item-xyz',
    scanRunId: 'run-xyz',
    spawnImpl: (cmd, args, opts) => {
      spawned.push({ cmd, args, opts });
      return fakeProc;
    },
  });

  // T3: scan_app.py resolved package-relatively (absolute) so scan works from any cwd.
  const expectedScanApp = fileURLToPath(new URL('../../sandbox/scan_app.py', import.meta.url));
  assert.equal(spawned.length, 1);
  assert.equal(spawned[0].cmd, 'modal');
  assert.deepEqual(spawned[0].args, [
    'run', expectedScanApp,
    '--target', 'fixtures/mcp/vuln-command-injection-server',
    '--item-type', 'mcp_server',
    '--item-id', 'item-xyz',
    '--scan-run-id', 'run-xyz',
  ]);
  assert.equal(spawned[0].opts.stdio, 'inherit');
});
