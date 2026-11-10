// Navigation and formatting contracts only; no sample result is product data.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const requireWeb = createRequire(path.resolve('apps/web/package.json'));
const ts = requireWeb('typescript');
const module = { exports: {} };
vm.runInNewContext(
  ts.transpileModule(readFileSync('apps/web/src/lib/benchmark-dashboard.ts', 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText,
  {
    module,
    exports: module.exports,
    URLSearchParams,
    require: (id) =>
      id === './benchmark'
        ? { benchmarkPath: (base) => base + '/workspace/benchmarks' }
        : requireWeb(id),
  },
);
const api = module.exports;
const React = requireWeb('react');
const { renderToStaticMarkup } = requireWeb('react-dom/server');
function compileView(file, imports) {
  const output = ts.transpileModule(readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const result = { exports: {} };
  vm.runInNewContext(output, {
    module: result,
    exports: result.exports,
    require: (name) => (name in imports ? imports[name] : requireWeb(name)),
  });
  return result.exports;
}
const css = { default: new Proxy({}, { get: (_, key) => String(key) }) };
const ui = compileView('apps/web/src/components/BenchmarkWorkbenchUI.tsx', {
  './BenchmarkWorkbench.module.css': css,
});
const noRequest = {
  benchmarkGet() {
    throw new Error('Unexpected read during contract render');
  },
  benchmarkPost() {
    throw new Error('Unexpected write during contract render');
  },
};
const views = compileView('apps/web/src/components/BenchmarkWorkbench.tsx', {
  'next/navigation': {},
  '../lib/benchmark': noRequest,
  '../lib/benchmark-dashboard': api,
  '../lib/benchmark-results': {
    measuredDuration: (value) => (value === null ? 'Unknown' : String(value)),
    recordedCost: (value) => (value === null ? 'Unknown' : String(value)),
  },
  './BenchmarkWorkbenchUI': ui,
  './BenchmarkGoldenWorkbench': { default: () => null },
  './BenchmarkWorkbench.module.css': css,
});
const goldenModule = { exports: {} };
vm.runInNewContext(
  ts.transpileModule(readFileSync('apps/web/src/lib/benchmark-golden.ts', 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText,
  { module: goldenModule, exports: goldenModule.exports },
);

test('all four views preserve the exact selected cohort and immutable score reference', () => {
  const original = new URLSearchParams(
    'model=provider%3Aone&model=provider%3Atwo&task=task-id&period=7d&environment=sha256%3Aimage&run_id=run-id&score_revision_id=score-id&trace_id=trace-id&cluster=category',
  );
  for (const view of ['overview', 'trace', 'failures', 'remediation']) {
    const href = api.dashboardContextLink('/workspace/project', view, original);
    const parsed = new URL(href, 'http://localhost');
    assert.equal(parsed.searchParams.toString(), original.toString());
    assert.equal(
      parsed.pathname,
      '/workspace/project/benchmarks' + (view === 'overview' ? '/evidence' : '/' + view),
    );
  }
});
const goldenView = compileView('apps/web/src/components/BenchmarkGoldenWorkbench.tsx', {
  '../lib/benchmark': noRequest,
  '../lib/benchmark-dashboard': api,
  '../lib/benchmark-golden': goldenModule.exports,
  './BenchmarkWorkbenchUI': ui,
  './BenchmarkWorkbench.module.css': css,
});

function backendFixture() {
  const fixture = JSON.parse(
    readFileSync('contracts/fixtures/benchmark-dashboard-empty-response.json', 'utf8'),
  );
  assert.ok(fixture.fixture_notice);
  return fixture.data;
}

test('model and task changes clear stale trace/cluster while preserving period and environment', () => {
  const original = new URLSearchParams(
    'model=old&task=old&period=30d&environment=image&trace_id=trace&cluster=failure',
  );
  const url = new URL(
    api.dashboardContextLink('/workspace/project', 'failures', original, {
      model: ['first', 'second'],
      task: 'new',
    }),
    'http://localhost',
  );
  assert.deepEqual(url.searchParams.getAll('model'), ['first', 'second']);
  assert.equal(url.searchParams.get('task'), 'new');
  assert.equal(url.searchParams.get('period'), '30d');
  assert.equal(url.searchParams.get('environment'), 'image');
  assert.equal(url.searchParams.has('trace_id'), false);
  assert.equal(url.searchParams.has('cluster'), false);
});

test('run changes clear incompatible revision unless explicitly rebound', () => {
  const query = new URLSearchParams('run_id=old&score_revision_id=old-score');
  const changed = new URL(
    api.dashboardContextLink('/workspace/project', 'trace', query, { run_id: 'new' }),
    'http://localhost',
  );
  assert.equal(changed.searchParams.get('run_id'), 'new');
  assert.equal(changed.searchParams.has('score_revision_id'), false);
});

test('old comparison URLs reopen the stored run without carrying preparation secrets', () => {
  const query = api.dashboardQuery(
    new URLSearchParams(
      'comparison=old-run&receipt=source&qualification=operation&expected_output=private',
    ),
  );
  assert.equal(query.toString(), 'run_id=old-run');
});

test('historical trace drafts preserve real provenance without granting current source authority', () => {
  const historical = goldenModule.exports.goldenDraftSource(
    { kind: 'historical_control', id: 'historical-trace' },
    'current-build',
  );
  assert.equal(historical.source_trace_id, 'historical-trace');
  assert.equal(historical.source_build_id, null);
  assert.equal(historical.source_anchor, null);
  const current = goldenModule.exports.goldenDraftSource(
    { kind: 'comparison_cell', id: 'cell', run_id: 'run' },
    'build',
  );
  assert.equal(current.source_anchor.run_id, 'run');
  assert.equal(current.source_anchor.cell_id, 'cell');
  assert.equal(current.source_trace_id, null);
  assert.equal(current.source_build_id, 'build');
  const unbound = goldenModule.exports.goldenDraftSource(undefined, '');
  assert.equal(unbound.source_build_id, null);
  assert.equal(unbound.source_trace_id, null);
  assert.equal(unbound.source_anchor, null);
});

test('context URLs never inherit unknown prompt, output, credential or approval fields', () => {
  const query = new URLSearchParams(
    'model=actual&system_prompt=secret&expected_output=private&password=credential&approved=true&include_raw_prompts=true',
  );
  assert.equal(api.dashboardQuery(query).toString(), 'model=actual');
  const report = new URL(
    api.dashboardReportLink('/projects/project', query, 'technical', false, 'a'.repeat(64)),
    'http://localhost',
  );
  assert.equal(report.searchParams.get('include_raw_prompts'), 'false');
  assert.equal(report.searchParams.get('template'), 'technical');
  assert.equal(report.searchParams.get('snapshot_sha256'), 'a'.repeat(64));
  assert.equal(report.searchParams.has('system_prompt'), false);
  assert.equal(report.pathname, '/api/v1/projects/project/workspace/benchmarks/dashboard/report');
});

test('unavailable values never turn into zero while a real measured zero stays zero', () => {
  assert.equal(api.dashboardNumber(null, '%'), 'Unavailable');
  assert.equal(api.dashboardNumber(undefined), 'Unavailable');
  assert.equal(api.dashboardNumber('0.00', '%'), '0.00%');
  assert.equal(api.dashboardNumber(0), '0');
  assert.equal(api.dashboardBar(null), null);
  assert.equal(api.dashboardBar('0'), 0);
  assert.equal(api.dashboardBar('100'), 100);
  assert.equal(api.dashboardBar('NaN'), null);
  assert.equal(api.dashboardBar('101'), null);
  assert.equal(
    api.dashboardMetricText({ status: 'not_run', value: null, reason: null }),
    'Not run',
  );
  assert.equal(api.dashboardMetricText({ status: 'available', value: 0, reason: null }), '0');
});

test('client rejects unreviewed primary attribution and historical controls masquerading as models', () => {
  const data = backendFixture();
  assert.equal(api.validateDashboardSnapshot(data), data);
  data.overview.models.push({
    primary: { earned_points: '0', possible_points: '81', percent: '0.00' },
    reviewed_run_count: 0,
    run_count: 1,
  });
  assert.throws(() => api.validateDashboardSnapshot(data), /actual report-authorization basis/);
  data.overview.models[0].reviewed_run_count = 1;
  assert.equal(api.validateDashboardSnapshot(data), data);
  data.overview.models[0].reviewed_run_count = 0;
  data.overview.models[0].authorized_run_count = 1;
  data.overview.models[0].reviewer_verified = false;
  data.overview.models[0].authorization_basis = ['admin_run_exempt'];
  assert.equal(api.validateDashboardSnapshot(data), data);
  data.overview.models[0].model_key = 'contract-only';
  data.overview.models[0].ranking_eligible = false;
  data.overview.leader = { model_key: 'contract-only', model_id: 'contract-only', percent: '0.00' };
  assert.throws(() => api.validateDashboardSnapshot(data), /eligible reviewed model measurements/);
  data.overview.models[0].ranking_eligible = true;
  assert.equal(api.validateDashboardSnapshot(data), data);
  assert.throws(
    () =>
      api.validateDashboardTrace({
        kind: 'historical_control',
        official: true,
        model_key: 'not-a-model',
      }),
    /cannot be official/,
  );
});

test('real empty backend overview does not manufacture a leader, model, judge or matchups', () => {
  const data = backendFixture();
  const html = renderToStaticMarkup(
    React.createElement(views.BenchmarkOverviewView, { data, selectModel() {}, open() {} }),
  );
  assert.equal(data.overview.total_traces, 0);
  assert.equal(data.overview.leader, null);
  assert.match(html, /Unavailable/);
  assert.match(html, /No eligible model observations/);
  assert.match(html, /No eligible head-to-head matchups/);
  assert.match(html, /Separate fitted metric/);
  assert.match(html, /Not run/);
  assert.doesNotMatch(html, /Claude 3.5|GPT-4o|88.4|1,480|82.4/);
});

test('trace and failure views honor the same actual empty cohort without fake telemetry', () => {
  const data = backendFixture();
  const trace = renderToStaticMarkup(
    React.createElement(views.BenchmarkTraceView, {
      data,
      selected: null,
      busy: false,
      error: '',
      open() {},
    }),
  );
  assert.match(trace, /Choose a trace to inspect/);
  assert.doesNotMatch(trace, /3,412|4.8s|search_subscription_plans/);
  const failures = renderToStaticMarkup(
    React.createElement(views.BenchmarkFailureView, { data, cluster() {}, open() {} }),
  );
  assert.match(failures, /Unavailable/);
  assert.match(failures, /Heatmap unavailable/);
  assert.doesNotMatch(failures, /18.4%|1,248|12.8%|8.2%|28.8%/);
});

test('a selected trace collapses the long registry so its evidence is immediately reachable', () => {
  const data = backendFixture();
  data.context.trace_id = 'contract-selected-trace';
  const html = renderToStaticMarkup(
    React.createElement(views.BenchmarkTraceView, {
      data,
      selected: null,
      busy: true,
      error: '',
      open() {},
    }),
  );
  assert.match(html, /Change selected trace/);
  assert.match(html, /<details class="traceSelector">/);
  assert.doesNotMatch(html, /<details class="traceSelector" open/);
  assert.match(html, /Loading authorized evidence/);
});

test('remediation view cannot seed verified cases, run a persona or manufacture pass rates', () => {
  const html = renderToStaticMarkup(
    React.createElement(goldenView.default, {
      base: '/projects/project',
      data: backendFixture(),
      canWrite: false,
      canAdmin: false,
      userId: 'contract-user',
    }),
  );
  assert.match(html, /Not run/);
  assert.match(html, /No compatible, executed golden-regression cohort/);
  assert.match(html, /No persona execution, model request/);
  assert.match(html, /Awaiting the authorized dataset registry/);
  assert.doesNotMatch(html, /94.2%|2,000|>Verified<|>verified<|Active.*Stress-Tests Running/);
  const focused = backendFixture();
  focused.context.trace_id = 'contract-focus';
  const focusedHtml = renderToStaticMarkup(
    React.createElement(goldenView.default, {
      base: '/projects/project',
      data: focused,
      canWrite: false,
      canAdmin: false,
      userId: 'contract-user',
    }),
  );
  assert.match(focusedHtml, /COHORT DATASETS/);
  assert.match(focusedHtml, /registry below is project-wide/);
});
