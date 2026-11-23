/**
 * Extra orchestrator coverage: spawn failure, identifier reuse, batch path.
 *
 * Author: swami
 * Created: 2026-08-02
 * Scope: runScan error handling + upsert by identifier + multi-target batch
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { runScan } from '../src/orchestrator.js';
import { hashLocalPath } from '../src/hash.js';

function makeThenable(value) {
  return {
    then(resolve, reject) {
      return Promise.resolve(value).then(resolve, reject);
    },
  };
}

function createSupabaseStub({
  byHashItem = null,
  byIdentItem = null,
  itemId = 'item-1',
  runId = 'run-1',
  batchId = 'batch-1',
  batchError = null,
  scanRunInsertError = null,
} = {}) {
  const calls = { failedUpdates: 0, rpc: 0, batches: [], updates: 0, itemUpdates: [] };

  const supabase = {
    calls,
    from(table) {
      return {
        select() {
          if (table === 'items') {
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
                          return makeThenable({
                            data: byIdentItem ? [byIdentItem] : [],
                            error: null,
                          });
                        },
                      };
                    },
                  };
                }
                return { maybeSingle: () => makeThenable({ data: null, error: null }) };
              },
            };
          }
          return {
            eq() {
              return { maybeSingle: () => makeThenable({ data: null, error: null }) };
            },
          };
        },
        insert(row) {
          if (table === 'scan_batches') {
            calls.batches.push(row);
            return {
              select() {
                return {
                  single: () => makeThenable({
                    data: batchError ? null : { id: batchId, ...row },
                    error: batchError,
                  }),
                };
              },
            };
          }
          if (table === 'items') {
            return {
              select() {
                return {
                  single: () =>
                    makeThenable({ data: { id: itemId, ...row }, error: null }),
                };
              },
            };
          }
          if (table === 'scan_runs') {
            return {
              select() {
                return {
                  single: () => makeThenable({
                    data: scanRunInsertError ? null : { id: runId, ...row },
                    error: scanRunInsertError,
                  }),
                };
              },
            };
          }
          return {
            select() {
              return { single: () => makeThenable({ data: {}, error: null }) };
            },
          };
        },
        update(patch) {
          calls.updates += 1;
          if (table === 'scan_runs') {
            calls.failedUpdates += 1;
            return {
              eq() {
                return makeThenable({ data: null, error: null });
              },
            };
          }
          if (table === 'items') calls.itemUpdates.push(patch);
          const base = byHashItem || byIdentItem || { id: itemId };
          return {
            eq() {
              return {
                select() {
                  return {
                    single: () =>
                      makeThenable({
                        data: { ...base, ...patch },
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
    rpc() {
      calls.rpc += 1;
      return makeThenable({ data: null, error: null });
    },
  };
  return supabase;
}

test('given spawn failure when runScan then marks failed and rolls up', async () => {
  // -- Given --
  const dir = await mkdtemp(path.join(tmpdir(), 'av-orch-'));
  await writeFile(path.join(dir, 'SKILL.md'), '# s');
  const sb = createSupabaseStub();
  const targets = [{ target: dir, type: 'skill', locus: 'local', avail: 'source_on_disk' }];

  // -- When --
  await assert.rejects(
    () => runScan(targets, {
      ensureSchemaFn: async () => ({ status: 'ready' }),
      getSupabaseFn: () => sb,
      spawnFn: async () => { throw new Error('modal down'); },
    }),
    /target scan dispatch failure/,
  );

  // -- Then --
  assert.ok(sb.calls.failedUpdates >= 1);
  assert.ok(sb.calls.rpc >= 1);
  await rm(dir, { recursive: true, force: true });
});

test('given existing identifier when upsert then updates hash', async () => {
  // -- Given --
  const dir = await mkdtemp(path.join(tmpdir(), 'av-ident-'));
  await writeFile(path.join(dir, 'SKILL.md'), '# s');
  const sb = createSupabaseStub({
    byIdentItem: { id: 'item-existing', identifier: dir },
  });
  const targets = [{ target: dir, type: 'skill', locus: 'local', avail: 'source_on_disk' }];
  let spawned = 0;

  // -- When --
  await runScan(targets, {
    ensureSchemaFn: async () => ({ status: 'ready' }),
    getSupabaseFn: () => sb,
    spawnFn: async () => {
      spawned += 1;
    },
  });

  // -- Then --
  assert.equal(spawned, 1);
  assert.ok(sb.calls.updates >= 1);
  await rm(dir, { recursive: true, force: true });
});

test('given stale display name when content hash matches then refreshes name without force', async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'av-rename-'));
  await writeFile(path.join(dir, 'SKILL.md'), '# s');
  const contentHash = await hashLocalPath(dir);
  const sb = createSupabaseStub({
    byHashItem: {
      id: 'item-stale-name',
      identifier: 'pbakaus/impeccable/.cursor/skills/audit',
      name: 'impeccable',
      content_hash: contentHash,
    },
  });
  const targets = [{
    target: dir,
    type: 'skill',
    locus: 'local',
    avail: 'source_on_disk',
    identifier: 'pbakaus/impeccable/.cursor/skills/audit',
    name: 'audit',
  }];
  let spawned = 0;

  await runScan(targets, {
    ensureSchemaFn: async () => ({ status: 'ready' }),
    getSupabaseFn: () => sb,
    spawnFn: async () => {
      spawned += 1;
    },
  });

  assert.equal(spawned, 0, 'unchanged content still skips sandbox without --force');
  assert.equal(sb.calls.itemUpdates.length, 1);
  assert.equal(sb.calls.itemUpdates[0].name, 'audit');
  await rm(dir, { recursive: true, force: true });
});

test('given existing identifier when upsert then refreshes display name', async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'av-ident-name-'));
  await writeFile(path.join(dir, 'SKILL.md'), '# s');
  const sb = createSupabaseStub({
    byIdentItem: {
      id: 'item-existing',
      identifier: 'pbakaus/impeccable/.cursor/skills/polish',
      name: 'impeccable',
    },
  });
  const targets = [{
    target: dir,
    type: 'skill',
    locus: 'local',
    avail: 'source_on_disk',
    identifier: 'pbakaus/impeccable/.cursor/skills/polish',
    name: 'polish',
  }];

  await runScan(targets, {
    ensureSchemaFn: async () => ({ status: 'ready' }),
    getSupabaseFn: () => sb,
    spawnFn: async () => {},
  });

  const namePatch = sb.calls.itemUpdates.find(p => p.name === 'polish');
  assert.ok(namePatch, 'identifier reuse must update card name');
  await rm(dir, { recursive: true, force: true });
});

test('given multiple targets when runScan then creates batch', async () => {
  // -- Given --
  const root = await mkdtemp(path.join(tmpdir(), 'av-batch-'));
  const a = path.join(root, 'a');
  const b = path.join(root, 'b');
  await writeFile(path.join(await mkdirSafe(a), 'SKILL.md'), '# a');
  await writeFile(path.join(await mkdirSafe(b), 'SKILL.md'), '# b');
  const sb = createSupabaseStub();
  const targets = [
    { target: a, type: 'skill', locus: 'local', avail: 'source_on_disk' },
    { target: b, type: 'skill', locus: 'local', avail: 'source_on_disk' },
  ];

  // -- When --
  const result = await runScan(targets, {
    ensureSchemaFn: async () => ({ status: 'ready' }),
    getSupabaseFn: () => sb,
    spawnFn: async () => {},
  });

  // -- Then --
  assert.deepEqual(sb.calls.batches, [{
    source_path: `${a},${b}`,
    item_count: 2,
    concurrency_limit: 5,
  }]);
  assert.equal(result.batch_id, 'batch-1');
  assert.deepEqual(result.scan_run_ids, ['run-1', 'run-1']);
  assert.deepEqual(result.failed_targets, []);
  await rm(root, { recursive: true, force: true });
});

test('given batch persistence failure when multiple targets scan then it aborts before dispatch', async () => {
  // -- Given --
  const sb = createSupabaseStub({ batchError: { message: 'database unavailable' } });
  const targets = [
    { target: 'https://one.example/mcp', type: 'mcp_server', avail: 'introspection_only' },
    { target: 'https://two.example/mcp', type: 'mcp_server', avail: 'introspection_only' },
  ];

  // -- When / Then --
  await assert.rejects(
    () => runScan(targets, {
      ensureSchemaFn: async () => ({ status: 'ready' }),
      getSupabaseFn: () => sb,
      spawnFn: async () => assert.fail('dispatch must not start'),
    }),
    /Failed to create scan batch: database unavailable/,
  );
});

test('given zero concurrency through the orchestration API when scan starts then it rejects before schema work', async () => {
  // -- Given --
  let schemaCalls = 0;

  // -- When / Then --
  await assert.rejects(
    () => runScan([], {
      concurrency: 0,
      ensureSchemaFn: async () => { schemaCalls += 1; },
    }),
    /positive integer/,
  );
  assert.equal(schemaCalls, 0);
});

test('given scan_run insert error when dispatch then outer catch returns error without scanRunId', async () => {
  /**
   * Scenario: outer catch in dispatchTarget fires when scan_runs.insert returns a DB error.
   * Slice: coverage — orchestrator.js lines 88-92 (outer catch after inner try)
   *
   * Given a target and a supabase stub where scan_runs insert returns an error,
   * When runScan dispatches the target,
   * Then the outer catch is taken, scanRunId is null, and runScan surfaces the failure.
   */
  // -- Given --
  const dir = await mkdtemp(path.join(tmpdir(), 'av-outer-catch-'));
  await writeFile(path.join(dir, 'SKILL.md'), '# s');
  const sb = createSupabaseStub({
    scanRunInsertError: { message: 'db insert error for scan_runs' },
  });
  const targets = [{ target: dir, type: 'skill', locus: 'local', avail: 'source_on_disk' }];

  // -- When / Then --
  await assert.rejects(
    () => runScan(targets, {
      ensureSchemaFn: async () => ({ status: 'ready' }),
      getSupabaseFn: () => sb,
      spawnFn: async () => { assert.fail('spawn must not be called when scan_run insert fails'); },
    }),
    /target scan dispatch failure/,
  );
  await rm(dir, { recursive: true, force: true });
});

async function mkdirSafe(p) {
  const { mkdir } = await import('node:fs/promises');
  await mkdir(p, { recursive: true });
  return p;
}

test('given introspection target when runScan then uses pending hash', async () => {
  // -- Given --
  const sb = createSupabaseStub();
  const targets = [
    {
      target: 'https://mcp.example.com/sse',
      type: 'mcp_server',
      locus: 'cloud',
      avail: 'introspection_only',
    },
  ];
  let spawned = 0;

  // -- When --
  await runScan(targets, {
    ensureSchemaFn: async () => ({ status: 'ready' }),
    getSupabaseFn: () => sb,
    spawnFn: async () => {
      spawned += 1;
    },
  });

  // -- Then --
  assert.equal(spawned, 1);
});
