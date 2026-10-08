import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { isMissingSchemaError, pgSslConfig, schemaPath } from '../src/ensureSchema.js';

test('schemaPath points at db/schema.sql', () => {
  const path = schemaPath();
  assert.ok(path.endsWith('db/schema.sql'));
  assert.equal(existsSync(path), true);
});

test('isMissingSchemaError detects PostgREST missing-table shapes', () => {
  assert.equal(isMissingSchemaError({ code: 'PGRST205', message: 'nope' }), true);
  assert.equal(
    isMissingSchemaError({ message: 'Could not find the table \'public.items\' in the schema cache' }),
    true
  );
  assert.equal(isMissingSchemaError({ message: 'relation "items" does not exist' }), true);
  assert.equal(isMissingSchemaError({ message: 'JWT expired' }), false);
  assert.equal(isMissingSchemaError(null), false);
});

test('pgSslConfig verifies TLS for remote Postgres and disables SSL on localhost', () => {
  assert.equal(pgSslConfig('postgresql://postgres@localhost:5432/postgres'), false);
  assert.equal(pgSslConfig('postgresql://postgres@127.0.0.1:5432/postgres'), false);
  assert.deepEqual(
    pgSslConfig('postgresql://postgres@db.example.supabase.co:5432/postgres'),
    { rejectUnauthorized: true }
  );
  assert.deepEqual(
    pgSslConfig('postgresql://postgres@aws-0-us-east-1.pooler.supabase.com:5432/postgres'),
    { rejectUnauthorized: false }
  );
});

test('isMissingSchemaError detects PGRST204 missing-column errors', () => {
  assert.equal(
    isMissingSchemaError({ code: 'PGRST204', message: "Could not find the 'completed_at' column of 'scan_run_scanners' in the schema cache" }),
    true
  );
  assert.equal(
    isMissingSchemaError({ message: "Could not find the 'console_output' column of 'scan_run_scanners' in the schema cache" }),
    true
  );
});
