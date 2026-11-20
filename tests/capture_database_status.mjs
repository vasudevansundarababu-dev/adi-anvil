import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';
import test from 'node:test';

const require = createRequire(new URL('../apps/web/package.json', import.meta.url));
const ts = require('typescript');
const source = readFileSync(new URL('../apps/web/src/lib/captureDatabaseStatus.ts', import.meta.url), 'utf8');
const exports = {};
vm.runInNewContext(ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS },
}).outputText, { exports, Date });
const status = exports.captureDatabaseStatus;
const receipt = () => ({
  owner: 'anvil_provisioning', ready: true, configuration_ready: true,
  runtime_qualified: true, connection_probe_performed: false,
  reason: 'capture_database_runtime_qualified', target_sha256: 'a'.repeat(64),
  qualification: {
    schema_version: 'anvil.capture-database-runtime-qualification.v1',
    scope: 'capture_api_database_target_only', spending_authority: false,
    target_sha256: 'a'.repeat(64), receipt_sha256: 'b'.repeat(64),
    expires_at: new Date(Date.now() + 3600000).toISOString(),
  },
});

test('only exact current server-validated capture scope displays Ready', () => {
  assert.equal(status(receipt()).ready, true);
  assert.equal(status({ ready: true }).ready, false);
  assert.equal(status(null).ready, false);
});

test('stale, malformed, wrong-scope and changed-target evidence never displays Ready', () => {
  for (const change of [
    { scope: 'technical_components_only' }, { spending_authority: true },
    { expires_at: '2020-01-01T00:00:00Z' }, { expires_at: 'invalid' },
    { target_sha256: 'c'.repeat(64) }, { receipt_sha256: 'invalid' },
    { schema_version: 'unknown' },
  ]) {
    const value = receipt();
    Object.assign(value.qualification, change);
    assert.equal(status(value).ready, false, JSON.stringify(change));
  }
  for (const change of [{ runtime_qualified: false }, { ready: false },
    { owner: 'uploaded' }, { connection_probe_performed: true }, { configuration_ready: false }]) {
    assert.equal(status({ ...receipt(), ...change }).ready, false);
  }
});
