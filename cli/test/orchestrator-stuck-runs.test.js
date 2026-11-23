/**
 * Scenario: abandoned 'running' scan runs for an item are failed once they are past the cutoff.
 * Slice: stuck-run cleanup (follow-up to the open-items review).
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { failStuckRuns, STUCK_RUN_MS } from '../src/orchestrator.js';

function fakeRunsSupabase() {
  const calls = [];
  return {
    calls,
    from(table) {
      const call = { table, filters: [] };
      calls.push(call);
      const chain = {
        update(patch) { call.patch = patch; return chain; },
        eq(col, val) { call.filters.push(['eq', col, val]); return chain; },
        lt(col, val) { call.filters.push(['lt', col, val]); return chain; },
        then: (resolve) => resolve({ error: null }),
      };
      return chain;
    },
  };
}

test('given an item when failStuckRuns then only its running rows older than the cutoff are failed', async () => {
  // -- Given --
  const supabase = fakeRunsSupabase();
  const now = Date.parse('2026-11-23T12:00:00Z');

  // -- When --
  await failStuckRuns(supabase, 'item-1', now);

  // -- Then --
  const [call] = supabase.calls;
  assert.equal(call.table, 'scan_runs');
  assert.equal(call.patch.status, 'failed');
  assert.deepEqual(call.filters, [
    ['eq', 'item_id', 'item-1'],
    ['eq', 'status', 'running'],
    ['lt', 'started_at', new Date(now - STUCK_RUN_MS).toISOString()],
  ]);
});

test('given the cutoff when read then it is twelve hours', () => {
  // -- Then --
  assert.equal(STUCK_RUN_MS, 12 * 60 * 60 * 1000);
});
