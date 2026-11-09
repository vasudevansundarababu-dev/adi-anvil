// Navigation/filter contracts only. These objects are not product execution evidence.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
const require = createRequire(path.resolve('apps/web/package.json'));
const ts = require('typescript'),
  module = { exports: {} };
vm.runInNewContext(
  ts.transpileModule(readFileSync('apps/web/src/lib/benchmark-rehearsal.ts', 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText,
  { module, exports: module.exports, URLSearchParams, Date },
);
const api = module.exports;
test('fictional views preserve exact run/cell context without private URL fields', () => {
  for (const view of ['overview', 'trace', 'failures', 'remediation']) {
    const link = api.rehearsalLink(
      '/workspace/p',
      view,
      'run',
      new URLSearchParams(
        'profile=algorithm&task=FX-001&period=7d&environment=local&cell_id=cell&password=private',
      ),
    );
    const url = new URL(link, 'http://localhost');
    assert.equal(url.searchParams.get('rehearsal_id'), 'run');
    assert.equal(url.searchParams.get('cell_id'), 'cell');
    assert.equal(url.searchParams.get('password'), null);
  }
});
test('fictional filters select actual stored cells and never replace missing data', () => {
  const run = {
    created_at: new Date().toISOString(),
    executed_at: null,
    manifest: { environment: 'local' },
    result: {
      cells: [
        { id: 'a', profile_id: 'one', task_id: 'FX-001' },
        { id: 'b', profile_id: 'two', task_id: 'FX-002' },
      ],
    },
  };
  assert.deepEqual(
    Array.from(api.rehearsalCells(run, new URLSearchParams('profile=one'))).map((x) => x.id),
    ['a'],
  );
  assert.equal(api.rehearsalCells(run, new URLSearchParams('task=FX-003')).length, 0);
  assert.equal(api.rehearsalCells(run, new URLSearchParams('environment=staging')).length, 0);
  run.created_at = '2000-01-01T00:00:00Z';
  assert.equal(api.rehearsalCells(run, new URLSearchParams('period=7d')).length, 0);
});
