/**
 * Content hash is committed only after a successful scan, so an edited skill
 * keeps its old hash (and fails the guard's tamper check) until it is re-scanned.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { dispatchTarget } from '../src/orchestrator.js';
import { hashLocalPath } from '../src/hash.js';

function fakeSupabase(existing) {
  const itemUpdates = [];
  const lookups = [];
  const inserts = [];
  const supabase = {
    itemUpdates,
    inserts,
    lookups,
    from(table) {
      if (table === 'items') {
        return {
          insert(payload) {
            inserts.push(payload);
            return { select() { return { single: async () => ({ data: { id: 'item-new', ...payload }, error: null }) }; } };
          },
          select() {
            return {
              eq(col) {
                if (col === 'content_hash') {
                  return { maybeSingle: async () => { lookups.push(col); return { data: null, error: null }; } };
                }
                return { order() { return { limit: async () => ({ data: existing ? [existing] : [], error: null }) }; } };
              },
            };
          },
          update(fields) {
            return {
              eq() {
                return {
                  select() {
                    return {
                      single: async () => {
                        itemUpdates.push(fields);
                        return { data: { ...existing, ...fields }, error: null };
                      },
                    };
                  },
                };
              },
            };
          },
        };
      }
      return {
        insert() {
          return { select() { return { single: async () => ({ data: { id: 'run-1' }, error: null }) }; } };
        },
        update() {
          // Chainable: failStuckRuns uses .eq().eq().lt(); the failure path uses .eq().
          const done = { error: null };
          const chain = { eq: () => chain, lt: () => chain, then: (resolve) => resolve(done) };
          return chain;
        },
      };
    },
    rpc: async () => ({ error: null }),
  };
  return supabase;
}

async function editedSkillDir() {
  const dir = await mkdtemp(path.join(tmpdir(), 'av-hash-commit-'));
  await writeFile(path.join(dir, 'SKILL.md'), 'edited content');
  return dir;
}

const hashWrites = (updates) => updates.filter((u) => 'content_hash' in u);

test('given edited skill when scan succeeds then new hash is committed after the spawn', async () => {
  // -- Given --
  const dir = await editedSkillDir();
  const existing = { id: 'item-1', identifier: 'skills/x', name: 'x', content_hash: 'old-hash' };
  const supabase = fakeSupabase(existing);
  const target = { target: dir, type: 'skill', identifier: 'skills/x', avail: 'source_on_disk' };
  let hashesBeforeSpawn = null;
  const spawnFn = async () => { hashesBeforeSpawn = hashWrites(supabase.itemUpdates).length; };

  try {
    // -- When --
    const outcome = await dispatchTarget(supabase, target, { batchId: 'b1', force: true, spawnFn });

    // -- Then --
    assert.equal(outcome.error, undefined);
    assert.equal(hashesBeforeSpawn, 0, 'hash must not be written before the scan');
    const written = hashWrites(supabase.itemUpdates);
    assert.equal(written.length, 1);
    assert.equal(written[0].content_hash, await hashLocalPath(dir));
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('given edited skill when scan fails then old hash is kept so the guard fails closed', async () => {
  // -- Given --
  const dir = await editedSkillDir();
  const existing = { id: 'item-1', identifier: 'skills/x', name: 'x', content_hash: 'old-hash' };
  const supabase = fakeSupabase(existing);
  const target = { target: dir, type: 'skill', identifier: 'skills/x', avail: 'source_on_disk' };
  const spawnFn = async () => { throw new Error('sandbox exited 1'); };

  try {
    // -- When --
    await dispatchTarget(supabase, target, { batchId: 'b1', force: true, spawnFn });

    // -- Then --
    assert.equal(hashWrites(supabase.itemUpdates).length, 0, 'failed scan must not commit the new hash');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('given new skill when first scan fails then a placeholder hash is stored so the next run rescans', async () => {
  // -- Given --
  const dir = await editedSkillDir();
  const supabase = fakeSupabase(null);
  const target = { target: dir, type: 'skill', identifier: 'skills/new', avail: 'source_on_disk' };
  const spawnFn = async () => { throw new Error('sandbox exited 1'); };

  try {
    // -- When --
    await dispatchTarget(supabase, target, { batchId: 'b1', force: false, spawnFn });

    // -- Then --
    assert.equal(supabase.inserts.length, 1);
    assert.match(supabase.inserts[0].content_hash, /^pending:/, 'real hash must not be stored before a scan');
    assert.equal(hashWrites(supabase.itemUpdates).length, 0);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('given new skill when first scan succeeds then the real hash is committed', async () => {
  // -- Given --
  const dir = await editedSkillDir();
  const supabase = fakeSupabase(null);
  const target = { target: dir, type: 'skill', identifier: 'skills/new', avail: 'source_on_disk' };

  try {
    // -- When --
    await dispatchTarget(supabase, target, { batchId: 'b1', force: false, spawnFn: async () => {} });

    // -- Then --
    const written = hashWrites(supabase.itemUpdates);
    assert.equal(written.length, 1);
    assert.equal(written[0].content_hash, await hashLocalPath(dir));
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('given non-disk target that failed its first scan when re-run then it is not treated as cached', async () => {
  // -- Given --
  const supabase = fakeSupabase(null);
  const target = { target: 'remote-skill', type: 'skill', identifier: 'skills/remote', avail: 'remote' };
  const spawnFn = async () => { throw new Error('sandbox exited 1'); };

  // -- When --
  const outcome = await dispatchTarget(supabase, target, { batchId: 'b1', force: false, spawnFn });

  // -- Then --
  assert.equal(outcome.error, 'sandbox exited 1');
  assert.equal(supabase.lookups.length, 0, 'placeholder must never be used as a cache key');
});
