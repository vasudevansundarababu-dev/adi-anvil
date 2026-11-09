'use client';

import { useCallback, useEffect, useState } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import { workspaceApi as api } from '../lib/workspace';
import s from './BenchmarkRunDashboard.module.css';

type Axis = {
  id: string;
  label: string;
  value: number | null;
  decided: number;
  planned: number;
  unknown: number;
  availability?: string;
  counts?: Record<string, number>;
};
type Criterion = {
  id: string;
  description: string;
  passed: boolean;
  earned_points: string;
  possible_points: string;
};
type Finding = {
  policy_id?: string;
  policy_version?: string;
  severity?: string;
  rule_id: string;
  requirement: string;
  outcome: string;
  reason: string;
  task_id?: string;
  model_key?: string;
  environment_key?: string;
};
type Cell = {
  id: string;
  task_key: string;
  model_key: string;
  environment_key: string;
  repetition: number;
  capture_sha256: string;
  assessment: {
    earned_points: string;
    possible_points: string;
    criteria: Criterion[];
    policy_findings: Finding[];
    safety: { axis: string; outcome: string; reason: string; legitimate_completion?: boolean }[];
  };
  capture?: { output: unknown; events: unknown[]; duration_ms: number };
};
type Task = {
  task_id: string;
  task_version: string;
  title: string;
  actor: unknown;
  environment_ids: string[];
  rubric: { criteria: { id: string; description: string; weight_bps: number }[] } | null;
};
type Group = {
  id: string;
  name: string;
  source_project_id: string;
  source_version: string;
  tasks: Task[];
  environments: { id: string; name: string }[];
};
type Plan = {
  runnable: boolean;
  id: string;
  name: string;
  task_group_id: string;
  snapshot_sha256: string;
  snapshot: { planned_cells: number };
};
type Run = {
  id: string;
  state: string;
  created_at: string;
  result_sha256: string;
  snapshot: {
    task_group_id: string;
    models: { id: string; name: string }[];
    environments: { id: string; name: string }[];
    planned_cells: number;
  };
  report_review: {
    state: string;
    ready: boolean;
    required_reviewers: number;
    completed_reviewers: number;
    executor: { name: string } | null;
    contact: string | null;
    decisions: { name: string; decision: string }[];
  };
};
type Method = {
  id: string;
  name: string;
  version: string;
  status: string;
  reason: string | null;
  scope: string;
  execution_status?: string;
  configuration_id?: string;
};
type Catalog = {
  report_policy: { required_reviewers: number };
  groups: Group[];
  plans: Plan[];
  runs: Run[];
  models: { id: string; name: string }[];
  methods: { catalog: Method[]; configured: { id: string; name: string }[] };
};
type View = {
  run: Run;
  task_group: Group;
  view_sha256: string;
  context: { cell_id: string | null };
  summary: {
    models: { model_key: string; mean_points: string; cells: number; percent: string }[];
    ranking: unknown;
  };
  cells: Cell[];
  selected_cell: Cell | null;
  series: { model_key: string; name: string; axes: Axis[] }[];
  methods: Method[];
  evaluators: {
    id: string;
    name: string;
    version: string;
    rule_id: string;
    coverage: { percent: number | null; decided: number; planned: number };
  }[];
  failures: {
    cells: number;
    total_cells: number;
    percent: number | null;
    by_task: { task_id: string; name: string; failed: number; total: number }[];
    policy_findings: Finding[];
  };
  remediation: {
    task_id: string;
    title: string;
    failed_cells: number;
    environment_ids: string[];
    recommendation: string;
    sample: unknown;
    licensing: string;
    improvement: string;
  }[];
  limitations: string[];
};
const tabs = [
  'Overview',
  'Evaluations',
  'Tasks & rubrics',
  'Failure modes',
  'Safety',
  'Remediation',
  'Report preview',
];
const shades = ['#168594', '#cf7543', '#8066b0'];
const label = (value: string) => value.replaceAll('_', ' ');

function Radar({ series }: { series: View['series'] }) {
  const point = (i: number, v: number) => [
    200 + ((118 * v) / 100) * Math.sin((i * Math.PI) / 3),
    170 - ((118 * v) / 100) * Math.cos((i * Math.PI) / 3),
  ];
  return (
    <svg
      viewBox="0 0 400 350"
      className={s.radar}
      role="img"
      aria-label="Six-axis quality, trust and safety comparison. Missing values are gaps."
    >
      {[25, 50, 75, 100].map((v) => (
        <polygon
          key={v}
          points={Array.from({ length: 6 }, (_, i) => point(i, v).join(',')).join(' ')}
          fill="none"
          stroke="#dbe6ec"
        />
      ))}
      {['Correctness', 'Evidence', 'Constraints', 'Policy', 'Injection', 'Containment'].map(
        (a, i) => (
          <g key={a}>
            <line x1="200" y1="170" x2={point(i, 100)[0]} y2={point(i, 100)[1]} stroke="#dbe6ec" />
            <text
              x={point(i, 125)[0]}
              y={point(i, 125)[1]}
              textAnchor="middle"
              fontSize="11"
              fill="#3b586c"
            >
              {a}
            </text>
          </g>
        ),
      )}
      {series.map((v, n) => (
        <g key={v.model_key}>
          {v.axes.map((a, i) => {
            const b = v.axes[(i + 1) % 6];
            if (a.value === null || b.value === null) return null;
            return (
              <line
                key={a.id}
                x1={point(i, a.value)[0]}
                y1={point(i, a.value)[1]}
                x2={point((i + 1) % 6, b.value)[0]}
                y2={point((i + 1) % 6, b.value)[1]}
                stroke={shades[n % 3]}
                strokeWidth="2.5"
              />
            );
          })}
          {v.axes.map((a, i) =>
            a.value === null ? null : (
              <circle
                key={a.id}
                cx={point(i, a.value)[0]}
                cy={point(i, a.value)[1]}
                r="3"
                fill={shades[n % 3]}
              />
            ),
          )}
        </g>
      ))}
    </svg>
  );
}

export default function BenchmarkRunDashboard({
  base,
  canAdmin,
}: {
  base: string;
  canAdmin: boolean;
}) {
  const endpoint = base + '/workspace/benchmark';
  const query = useSearchParams(),
    pathname = usePathname();
  const [catalog, setCatalog] = useState<Catalog | null>(null),
    [view, setView] = useState<View | null>(null);
  const [loadingView, setLoadingView] = useState(false);
  const [error, setError] = useState(''),
    [message, setMessage] = useState(''),
    [busy, setBusy] = useState(false),
    [setup, setSetup] = useState(query.get('configure') === '1');
  const [selectedGroup, setSelectedGroup] = useState(''),
    [policies, setPolicies] = useState<{
      id: string | null;
      manifest: {
        policies: {
          policy_id: string;
          version: string;
          title: string;
          rules: { rule_id: string; requirement: string }[];
        }[];
      } | null;
      mappings: unknown[];
      sources: {
        id: string;
        path: string;
        sha256: string;
        extraction: { status: string; text: string | null; reason: string | null };
      }[];
    } | null>(null);
  const [configs, setConfigs] = useState<{ id: string; name: string; status: string }[]>([]);
  const runId = query.get('benchmark_run') || '',
    tab = query.get('view') || 'Overview',
    groupId = query.get('task_group') || selectedGroup;
  const update = useCallback(
    (changes: Record<string, string>) => {
      // Read the current browser URL, so rapid filter changes compose rather than
      // replacing each other with an earlier React render's query snapshot.
      const p = new URLSearchParams(window.location.search);
      for (const [k, v] of Object.entries(changes)) {
        if (v) p.set(k, v);
        else p.delete(k);
      }
      const target = pathname + '?' + p.toString();
      window.history.pushState(null, '', target);
      if (p.get('benchmark_run')) sessionStorage.setItem('anvil-benchmark:' + base, target);
    },
    [base, pathname],
  );
  const scope = new URLSearchParams();
  for (const key of ['model', 'environment', 'task', 'period', 'method', 'cell'])
    for (const value of query.getAll(key)) scope.append(key, value);
  const scopeString = scope.toString();
  useEffect(() => {
    if (runId && new URLSearchParams(window.location.search).get('benchmark_run') === runId)
      sessionStorage.setItem('anvil-benchmark:' + base, pathname + window.location.search);
  }, [base, pathname, query, runId]);
  const reload = useCallback(async () => {
    const c = (await api(endpoint)) as Catalog;
    setCatalog(c);
    return c;
  }, [endpoint]);
  useEffect(() => {
    reload().catch((e) => setError(e.message));
  }, [reload]);
  useEffect(() => {
    if (!catalog) return;
    if (!groupId && catalog.groups[0]) setSelectedGroup(catalog.groups[0].id);
    if (!runId && catalog.runs.length && !query.has('new_run'))
      update({
        benchmark_run: catalog.runs[0].id,
        task_group: catalog.runs[0].snapshot.task_group_id,
      });
  }, [catalog, groupId, runId, query, update]);
  useEffect(() => {
    if (!runId) {
      setView(null);
      return;
    }
    let active = true;
    setLoadingView(true);
    const load = () =>
      api(endpoint + '/runs/' + runId + '?' + scopeString)
        .then((v: View) => {
          if (active) {
            setView(v);
            setError('');
            setLoadingView(false);
          }
        })
        .catch((e) => {
          if (active) {
            setError(e.message);
            setLoadingView(false);
          }
        });
    load();
    const timer = setInterval(load, 2500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [endpoint, runId, scopeString]);
  useEffect(() => {
    if (!groupId) return;
    api(endpoint + '/groups/' + groupId + '/policies')
      .then(setPolicies)
      .catch((e) => setError(e.message));
    api(base + '/workspace/evaluators')
      .then((c) => setConfigs(c.items))
      .catch((e) => setError(e.message));
  }, [base, endpoint, groupId, message]);
  const action = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError('');
    try {
      await fn();
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Operation failed');
    } finally {
      setBusy(false);
    }
  };
  const download = async (format: string) => {
    if (!view) return;
    await action(async () => {
      const q = new URLSearchParams(scopeString);
      q.set('format', format);
      q.set('expected_view_sha256', view.view_sha256);
      const response = await fetch('/api/v1' + endpoint + '/runs/' + runId + '/export?' + q, {
        cache: 'no-store',
      });
      if (!response.ok) {
        const e = await response.json();
        throw new Error(e.error?.message || 'Export failed');
      }
      const url = URL.createObjectURL(await response.blob());
      const a = document.createElement('a');
      a.href = url;
      a.download = 'anvil-benchmark-' + runId + '.' + format;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 30000);
      setMessage('Export downloaded for the selected scope.');
    });
  };
  const group = catalog?.groups.find((g) => g.id === groupId),
    selected = view?.selected_cell,
    names = Object.fromEntries(
      (view?.run.snapshot.models || catalog?.models || []).map((m) => [m.id, m.name]),
    );
  const exportReady = !!view?.run.report_review.ready && !loadingView;
  return (
    <section className={s.root} aria-label="Benchmark dashboard" aria-busy={loadingView}>
      <header className={s.header}>
        <div>
          <small>ANVIL / BENCHMARKS</small>
          <h2>Agent benchmark</h2>
          <p>Tasks, evidence and trust — one frozen Run.</p>
        </div>
        <div className={s.actions}>
          <span className={s.pill}>Paid calls off</span>
          <button onClick={() => setSetup(!setup)}>Import & configure Run</button>
          <button disabled={!exportReady || busy} onClick={() => download('json')}>
            Export JSON
          </button>
          <button
            className={s.primary}
            disabled={!exportReady || busy}
            onClick={() => download('pdf')}
          >
            Export PDF
          </button>
        </div>
      </header>
      {error && (
        <p role="alert" className={s.error}>
          {error}
        </p>
      )}
      {message && <p role="status">{message}</p>}
      {setup && catalog && (
        <div className={s.card}>
          <h3>Import → configure → Run</h3>
          <p>A Praxis Project becomes one Task Group. Each Task Group can have many Runs.</p>
          <div className={s.actions}>
            <a href={'/api/v1' + endpoint + '/sample.zip'}>Download fictional Project ZIP</a>
            <button
              disabled={busy}
              onClick={() =>
                action(async () => {
                  const g = await api(endpoint + '/sample', 'POST');
                  setSelectedGroup(g.id);
                  update({ task_group: g.id, new_run: '1', benchmark_run: '' });
                  setMessage('Fictional Project imported with original policy source.');
                })
              }
            >
              Import fictional banking Project
            </button>
            <label>
              Import Project ZIP
              <input
                type="file"
                accept=".zip"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (!file) return;
                  action(async () => {
                    const csrf =
                      document.cookie
                        .split('; ')
                        .find((v) => v.startsWith('anvil_csrf='))
                        ?.split('=')[1] || '';
                    const r = await fetch('/api/v1' + endpoint + '/import', {
                      method: 'POST',
                      headers: {
                        'X-CSRF-Token': csrf,
                        'Content-Type': 'application/zip',
                        'Idempotency-Key': crypto.randomUUID(),
                      },
                      body: file,
                    });
                    const value = await r.json();
                    if (!r.ok) throw new Error(value.error?.message || 'Import rejected');
                    setSelectedGroup(value.data.id);
                    update({ task_group: value.data.id, new_run: '1', benchmark_run: '' });
                    setMessage('Versioned Project imported.');
                  });
                }}
              />
            </label>
          </div>
          <label>
            Task Group
            <select
              value={groupId}
              onChange={(e) => {
                setSelectedGroup(e.target.value);
                update({ task_group: e.target.value, new_run: '1', benchmark_run: '' });
              }}
            >
              <option value="">Select imported Project</option>
              {catalog.groups.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name} · v{g.source_version}
                </option>
              ))}
            </select>
          </label>
          {group && (
            <>
              <details open>
                <summary>Optional policies & deterministic verifiers</summary>
                {policies?.sources?.map((source) => (
                  <details key={source.id}>
                    <summary>
                      Policy source: {source.path} · {label(source.extraction.status)}
                    </summary>
                    <p>{source.extraction.reason}</p>
                    {source.extraction.text && <pre>{source.extraction.text}</pre>}
                    <a
                      href={
                        '/api/v1' +
                        endpoint +
                        '/groups/' +
                        group.id +
                        '/policies/sources/' +
                        encodeURIComponent(source.id)
                      }
                    >
                      Download original source
                    </a>
                    <p className={s.note}>
                      SHA256 {source.sha256}. Extracted text is source material, not an executable
                      verifier.
                    </p>
                  </details>
                ))}
                {policies?.manifest?.policies.map((p) => (
                  <div key={p.policy_id}>
                    <h4>
                      {p.title} · v{p.version}
                    </h4>
                    {p.rules.map((r) => (
                      <p key={r.rule_id}>
                        <strong>{r.rule_id}</strong> — {r.requirement}
                      </p>
                    ))}
                  </div>
                ))}
                {!policies?.id && <p>No custom policy attached. Custom checks will be N/A.</p>}
                {policies?.id && (
                  <>
                    <p>
                      {policies.mappings.length} saved mappings. Unmapped rules remain Not
                      evaluated.
                    </p>
                    <div className={s.actions}>
                      {['builtin', 'zen', 'opa-local'].map((adapter) => (
                        <button
                          key={adapter}
                          disabled={busy}
                          onClick={() =>
                            action(async () => {
                              await api(
                                endpoint +
                                  '/groups/' +
                                  group.id +
                                  '/sample-verifiers?adapter=' +
                                  adapter,
                                'POST',
                              );
                              setMessage('Banking rules tested and mapped with ' + adapter + '.');
                            })
                          }
                        >
                          Test & map fictional rules: {adapter}
                        </button>
                      ))}
                    </div>
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        const f = new FormData(e.currentTarget);
                        const [policy_id, policy_version, rule_id] = String(f.get('rule')).split(
                          '|',
                        );
                        action(async () => {
                          await api(endpoint + '/mappings', 'POST', {
                            policy_set_id: policies.id,
                            policy_id,
                            policy_version,
                            rule_id,
                            configuration_id: f.get('config'),
                            task_ids: f.getAll('task_scope'),
                            environment_ids: [],
                          });
                          setMessage('Policy mapping saved.');
                        });
                      }}
                    >
                      <label>
                        Rule
                        <select name="rule">
                          {policies.manifest?.policies.flatMap((p) =>
                            p.rules.map((r) => (
                              <option
                                key={p.policy_id + r.rule_id}
                                value={[p.policy_id, p.version, r.rule_id].join('|')}
                              >
                                {p.title} / {r.rule_id}
                              </option>
                            )),
                          )}
                        </select>
                      </label>
                      <label>
                        Tested configuration
                        <select name="config" required>
                          <option value="">Select Ready verifier</option>
                          {configs
                            .filter((c) => c.status === 'ready')
                            .map((c) => (
                              <option key={c.id} value={c.id}>
                                {c.name}
                              </option>
                            ))}
                        </select>
                      </label>
                      <fieldset>
                        <legend>Task scope (none = all Tasks)</legend>
                        {group.tasks.map((t) => (
                          <label key={t.task_id}>
                            <input type="checkbox" name="task_scope" value={t.task_id} />
                            {t.task_id}
                          </label>
                        ))}
                      </fieldset>
                      <button disabled={busy}>Save mapping</button>
                    </form>
                  </>
                )}
              </details>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const f = new FormData(e.currentTarget);
                  action(async () => {
                    const p = await api(endpoint + '/plans', 'POST', {
                      name: f.get('name'),
                      task_group_id: group.id,
                      task_ids: f.getAll('tasks'),
                      models: f.getAll('models'),
                      environment_ids: f.getAll('envs'),
                      method_ids: ['task-rubric-v1', ...f.getAll('methods')],
                      repetitions: Number(f.get('repetitions')),
                    });
                    setMessage('Execution Group saved. Start a Run below.');
                    update({ task_group: group.id, new_run: '1', benchmark_run: '' });
                    return p;
                  });
                }}
              >
                <h3>Execution Group</h3>
                <label>
                  Name
                  <input
                    name="name"
                    required
                    defaultValue="Fictional banking evaluation"
                    maxLength={160}
                  />
                </label>
                <div className={s.grid}>
                  <fieldset>
                    <legend>Tasks</legend>
                    {group.tasks.map((t) => (
                      <label key={t.task_id}>
                        <input name="tasks" type="checkbox" defaultChecked value={t.task_id} />
                        {t.title}
                      </label>
                    ))}
                  </fieldset>
                  <fieldset>
                    <legend>Agents / models</legend>
                    {catalog.models.map((m) => (
                      <label key={m.id}>
                        <input name="models" type="checkbox" defaultChecked value={m.id} />
                        {m.name}
                      </label>
                    ))}
                    <small>
                      Transparent software controls. Real provider inference remains off.
                    </small>
                  </fieldset>
                  <fieldset>
                    <legend>Environments</legend>
                    {group.environments.map((e) => (
                      <label key={e.id}>
                        <input name="envs" type="checkbox" defaultChecked value={e.id} />
                        {e.name}
                      </label>
                    ))}
                  </fieldset>
                  <fieldset>
                    <legend>Evaluation methods</legend>
                    <label>
                      <input type="checkbox" checked disabled />
                      Task rubric / 81
                    </label>
                    {catalog.methods.catalog
                      .filter((m) => m.id !== 'task-rubric-v1')
                      .map((m) => (
                        <label key={m.id} title={m.reason || m.scope}>
                          <input
                            name="methods"
                            type="checkbox"
                            value={m.id}
                            defaultChecked={m.id === 'safety-observed-v1'}
                          />
                          {m.name} · {label(m.status)}
                        </label>
                      ))}
                    {catalog.methods.configured.map((m) => (
                      <label key={m.id}>
                        <input name="methods" type="checkbox" value={m.id} />
                        {m.name}
                      </label>
                    ))}
                  </fieldset>
                </div>
                <label>
                  Repetitions
                  <input name="repetitions" type="number" min={1} max={5} defaultValue={1} />
                </label>
                <button className={s.primary} disabled={busy}>
                  Save Execution Group
                </button>
              </form>
              <h3>Saved Execution Groups</h3>
              {catalog.plans
                .filter((p) => p.task_group_id === group.id)
                .map((p) => (
                  <div className={s.plan} key={p.id}>
                    <div>
                      <strong>{p.name}</strong>
                      <small>
                        {p.snapshot.planned_cells} executions · frozen versions
                        {!p.runnable ? ' · source updated; save a new group' : ''}
                      </small>
                    </div>
                    <button
                      disabled={busy || !p.runnable}
                      onClick={() =>
                        action(async () => {
                          const r = await api(endpoint + '/runs', 'POST', {
                            plan_id: p.id,
                            expected_plan_sha256: p.snapshot_sha256,
                          });
                          update({
                            benchmark_run: r.id,
                            task_group: r.snapshot.task_group_id,
                            new_run: '',
                            cell: '',
                            model: '',
                            environment: '',
                            method: '',
                            task: '',
                          });
                          setSetup(false);
                          setMessage('Run queued. Results are saved as the worker completes.');
                        })
                      }
                    >
                      Start Run
                    </button>
                  </div>
                ))}
            </>
          )}
          {canAdmin && (
            <details>
              <summary>Report review setting for future Runs</summary>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  const f = new FormData(e.currentTarget);
                  action(async () => {
                    await api(endpoint + '/report-policy', 'POST', {
                      required_reviewers: Number(f.get('reviewers')),
                      rationale: 'Authenticated Admin sets report review count for future Runs.',
                    });
                    setMessage(
                      'Report review count saved for future Runs. Existing Run snapshots are unchanged.',
                    );
                  });
                }}
              >
                <label>
                  Required actual reviewers (0–10)
                  <input
                    name="reviewers"
                    type="number"
                    min={0}
                    max={10}
                    defaultValue={catalog.report_policy.required_reviewers}
                    required
                  />
                </label>
                <p>
                  Actual Admin execution or exact-result Admin approval exempts further report
                  review. Source rights and paid-call gates remain separate.
                </p>
                <button disabled={busy}>Save report review setting</button>
              </form>
            </details>
          )}
          <details>
            <summary>Configure benchmark methodology</summary>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const f = new FormData(e.currentTarget);
                action(async () => {
                  await api(endpoint + '/methods', 'POST', {
                    name: f.get('name'),
                    method_key: f.get('method_key'),
                    instruction_weight: Number(f.get('instruction')),
                    accuracy_weight: Number(f.get('accuracy')),
                    tone_weight: Number(f.get('tone')),
                  });
                  setMessage('Versioned methodology saved; availability remains explicit.');
                });
              }}
            >
              <label>
                Configuration name
                <input name="name" required />
              </label>
              <label>
                Method
                <select name="method_key">
                  {catalog.methods.catalog.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name}
                    </option>
                  ))}
                </select>
              </label>
              <div className={s.actions}>
                {[
                  ['instruction', 40],
                  ['accuracy', 30],
                  ['tone', 30],
                ].map(([k, v]) => (
                  <label key={k}>
                    {k}
                    <input name={String(k)} type="number" min={0} max={100} defaultValue={v} />
                  </label>
                ))}
              </div>
              <button disabled={busy}>Save method</button>
            </form>
          </details>
        </div>
      )}
      <div className={s.filters}>
        <label>
          Task Group
          <select
            aria-label="Task Group"
            value={groupId}
            onChange={(e) => {
              const r = catalog?.runs.find((r) => r.snapshot.task_group_id === e.target.value);
              update({
                task_group: e.target.value,
                benchmark_run: r?.id || '',
                new_run: r ? '' : '1',
                cell: '',
                model: '',
                environment: '',
                task: '',
                method: '',
              });
            }}
          >
            <option value="">Select</option>
            {catalog?.groups.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name} · v{g.source_version}
              </option>
            ))}
          </select>
        </label>
        <label>
          Run
          <select
            aria-label="Run"
            value={runId}
            onChange={(e) =>
              update({
                benchmark_run: e.target.value,
                cell: '',
                model: '',
                environment: '',
                task: '',
                method: '',
              })
            }
          >
            <option value="">Select Run</option>
            {catalog?.runs
              .filter((r) => !groupId || r.snapshot.task_group_id === groupId)
              .map((r) => (
                <option key={r.id} value={r.id}>
                  {r.created_at.slice(0, 16).replace('T', ' ')} · {r.id.slice(0, 8)} · {r.state}
                </option>
              ))}
          </select>
        </label>
        {view && (
          <>
            <label>
              Model
              <select
                aria-label="Model"
                value={query.get('model') || ''}
                onChange={(e) => update({ model: e.target.value, cell: '' })}
              >
                <option value="">All selected agents</option>
                {view.run.snapshot.models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Environment
              <select
                aria-label="Environment"
                value={query.get('environment') || ''}
                onChange={(e) => update({ environment: e.target.value, cell: '' })}
              >
                <option value="">All environments</option>
                {view.run.snapshot.environments.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Eval period
              <select
                aria-label="Eval period"
                value={query.get('period') || 'all'}
                onChange={(e) => update({ period: e.target.value })}
              >
                <option value="all">All Run dates</option>
                <option value="7d">Last 7 days</option>
                <option value="30d">Last 30 days</option>
              </select>
            </label>
            <label>
              Method
              <select
                aria-label="Method"
                value={query.get('method') || 'all'}
                onChange={(e) => update({ method: e.target.value })}
              >
                <option value="all">All selected methods</option>
                {view.methods.map((m) => (
                  <option key={m.configuration_id || m.id} value={m.configuration_id || m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}
      </div>
      {!view && (
        <div className={s.card}>
          <h3>{catalog?.groups.length ? 'Select or create a Run' : 'Import your first Project'}</h3>
          <p>
            Use Import & configure Run to load the fictional task bank, test verifiers, and execute
            the complete local flow.
          </p>
        </div>
      )}
      {view && (
        <>
          {loadingView && <p role="status">Updating the selected evidence scope…</p>}
          <div className={s.context}>
            <strong>
              {view.task_group.name} · v{view.task_group.source_version}
            </strong>
            <span>
              {view.run.state} · {view.cells.length}/{view.run.snapshot.planned_cells} selected
              executions
            </span>
            <span>Fictional software evidence · 0 provider calls</span>
          </div>
          <nav className={s.tabs} aria-label="Benchmark views">
            {tabs.map((t) => (
              <button
                key={t}
                aria-current={tab === t ? 'page' : undefined}
                onClick={() => update({ view: t })}
              >
                {t}
              </button>
            ))}
          </nav>
          {view.run.state !== 'completed' && (
            <p role="status">
              Run {view.run.state}. The durable worker preserves capture and assessment separately.{' '}
              {['failed', 'blocked'].includes(view.run.state)
                ? 'Inspect the saved Run failure before creating a new Run.'
                : 'Results refresh automatically.'}
            </p>
          )}
          {tab === 'Overview' && (
            <>
              <div className={s.metrics}>
                <div>
                  <small>EXECUTIONS</small>
                  <strong>{view.cells.length}</strong>
                </div>
                <div>
                  <small>TASKS</small>
                  <strong>{new Set(view.cells.map((c) => c.task_key)).size}</strong>
                </div>
                <div>
                  <small>AGENTS</small>
                  <strong>{view.summary.models.length}</strong>
                </div>
                <div>
                  <small>FAILURE CELLS</small>
                  <strong>{view.failures.cells}</strong>
                </div>
              </div>
              <div className={s.grid}>
                <div className={s.card}>
                  <h3>Task score comparison</h3>
                  {view.summary.models.map((m, i) => (
                    <div className={s.score} key={m.model_key}>
                      <span>{names[m.model_key]}</span>
                      <strong>{m.mean_points} / 81</strong>
                      <div>
                        <i
                          style={{
                            width: m.percent + '%',
                            background:
                              shades[view.series.findIndex((v) => v.model_key === m.model_key) % 3],
                          }}
                        />
                      </div>
                    </div>
                  ))}
                  <p className={s.note}>
                    Matched Task/environment/repetition cohorts. These agents are fictional
                    controls.
                  </p>
                  <details>
                    <summary>Observed wins / ties and Bradley–Terry</summary>
                    <pre>{JSON.stringify(view.summary.ranking, null, 2)}</pre>
                  </details>
                </div>
                <div className={s.card}>
                  <h3>Rubric profile · trust & safety</h3>
                  <Radar series={view.series} />
                  {view.series.map((v, i) => (
                    <span className={s.legend} style={{ color: shades[i % 3] }} key={v.model_key}>
                      ● {v.name}
                    </span>
                  ))}
                  <p className={s.note}>Unknown axes are gaps. Safety and quality stay separate.</p>
                </div>
              </div>
            </>
          )}
          {tab === 'Evaluations' && (
            <div className={s.card}>
              <h3>Methods used by this Run</h3>
              <table>
                <thead>
                  <tr>
                    <th>Method</th>
                    <th>Version</th>
                    <th>Status</th>
                    <th>Methodology</th>
                  </tr>
                </thead>
                <tbody>
                  {view.methods.map((m) => (
                    <tr key={m.configuration_id || m.id}>
                      <td>{m.name}</td>
                      <td>{m.version}</td>
                      <td>{label(m.execution_status || m.status)}</td>
                      <td>{m.reason || m.scope}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <h3>Policy verifiers</h3>
              {view.evaluators.map((e) => (
                <div className={s.plan} key={e.id + e.rule_id}>
                  <strong>
                    {e.name} · {e.version} / {e.rule_id}
                  </strong>
                  <span>
                    {e.coverage.percent === null
                      ? 'Not evaluated'
                      : e.coverage.percent.toFixed(1) + '%'}{' '}
                    · {e.coverage.decided}/{e.coverage.planned} decided
                  </span>
                </div>
              ))}
              {!view.evaluators.length && (
                <p>No verifier mapping captured. Unmapped policy checks are Not evaluated.</p>
              )}
            </div>
          )}
          {tab === 'Tasks & rubrics' && (
            <div className={s.card}>
              <h3>Tasks and execution evidence</h3>
              <label>
                Task
                <select
                  aria-label="Task"
                  value={query.get('task') || 'all'}
                  onChange={(e) => update({ task: e.target.value, cell: '' })}
                >
                  <option value="all">All Tasks</option>
                  {view.task_group.tasks.map((t) => (
                    <option key={t.task_id} value={t.task_id}>
                      {t.title}
                    </option>
                  ))}
                </select>
              </label>
              <table>
                <thead>
                  <tr>
                    <th>Task</th>
                    <th>Agent</th>
                    <th>Environment</th>
                    <th>Score /81</th>
                    <th>Rubric</th>
                  </tr>
                </thead>
                <tbody>
                  {view.cells.map((c) => (
                    <tr key={c.id} className={selected?.id === c.id ? s.selected : ''}>
                      <td>
                        <button disabled={loadingView} onClick={() => update({ cell: c.id })}>
                          {c.task_key}
                        </button>
                      </td>
                      <td>{names[c.model_key]}</td>
                      <td>{c.environment_key}</td>
                      <td>{Number(c.assessment.earned_points).toFixed(1)}</td>
                      <td>
                        <button disabled={loadingView} onClick={() => update({ cell: c.id })}>
                          View rubric
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {selected && (
                <article id="execution-detail">
                  <h3>Selected execution · {selected.task_key}</h3>
                  <p>
                    {names[selected.model_key]} / {selected.environment_key} / repetition{' '}
                    {selected.repetition + 1}
                  </p>
                  <details>
                    <summary>View Task detail</summary>
                    <pre>
                      {JSON.stringify(
                        view.task_group.tasks.find((t) => t.task_id === selected.task_key)?.actor,
                        null,
                        2,
                      )}
                    </pre>
                  </details>
                  <table>
                    <thead>
                      <tr>
                        <th>Rubric</th>
                        <th>Criterion</th>
                        <th>Result</th>
                        <th>Points</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selected.assessment.criteria.map((c) => (
                        <tr key={c.id}>
                          <td>{c.id}</td>
                          <td>{c.description}</td>
                          <td>{c.passed ? 'Pass' : 'Fail'}</td>
                          <td>
                            {c.earned_points}/{c.possible_points}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <h4>Actual stored output</h4>
                  <pre>{JSON.stringify(selected.capture?.output, null, 2)}</pre>
                  <details>
                    <summary>Observable tool trace</summary>
                    <pre>{JSON.stringify(selected.capture?.events, null, 2)}</pre>
                  </details>
                  <small>Capture SHA256 {selected.capture_sha256}</small>
                </article>
              )}
            </div>
          )}
          {tab === 'Failure modes' && (
            <div className={s.card}>
              <h3>Task-level failure analysis</h3>
              {view.failures.by_task.map((t) => (
                <div className={s.score} key={t.task_id}>
                  <button
                    onClick={() => update({ view: 'Tasks & rubrics', task: t.task_id, cell: '' })}
                  >
                    {t.name}
                  </button>
                  <strong>
                    {t.failed} / {t.total} executions
                  </strong>
                  <div>
                    <i
                      style={{
                        width: (t.total ? (t.failed / t.total) * 100 : 0) + '%',
                        background: '#ca6a43',
                      }}
                    />
                  </div>
                </div>
              ))}
              <p className={s.note}>
                A failed execution has a failed rubric criterion or deterministic policy check.
                Infrastructure errors and Unknown are not policy failures.
              </p>
              {view.remediation.map((r) => (
                <div key={r.task_id}>
                  <h4>{r.title}</h4>
                  <p>
                    {r.failed_cells} evidence-linked failures ·{' '}
                    <button onClick={() => update({ view: 'Remediation', task: r.task_id })}>
                      View applicable datasets
                    </button>
                  </p>
                </div>
              ))}
            </div>
          )}
          {tab === 'Safety' && (
            <div className={s.card}>
              <h3>Policy adherence · injection resistance · environment containment</h3>
              <p className={s.note}>
                Prohibited attempts fail policy checks even if the simulated environment blocks
                their effects. Containment here is a local simulator observation.
              </p>
              <table>
                <thead>
                  <tr>
                    <th>Agent</th>
                    <th>Axis</th>
                    <th>Result</th>
                    <th>Coverage</th>
                    <th>Unknown</th>
                    <th>N/A</th>
                  </tr>
                </thead>
                <tbody>
                  {view.series.flatMap((v) =>
                    v.axes.slice(3).map((a) => (
                      <tr key={v.model_key + a.id}>
                        <td>{v.name}</td>
                        <td>{a.label}</td>
                        <td>
                          {a.value === null
                            ? label(a.availability || 'not_evaluated')
                            : a.value.toFixed(1) + '%'}
                        </td>
                        <td>
                          {a.decided}/{a.planned}
                        </td>
                        <td>{a.unknown}</td>
                        <td>{a.counts?.not_applicable || 0}</td>
                      </tr>
                    )),
                  )}
                </tbody>
              </table>
              <details>
                <summary>
                  Task-level policy evidence · {view.failures.policy_findings.length} checks
                </summary>
                <table>
                  <thead>
                    <tr>
                      <th>Task / environment</th>
                      <th>Agent / rule</th>
                      <th>Verdict</th>
                      <th>Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {view.failures.policy_findings.map((f, i) => (
                      <tr key={i}>
                        <td>
                          {f.task_id} / {f.environment_key}
                        </td>
                        <td>
                          {names[f.model_key || '']} / {f.policy_id} v{f.policy_version} /{' '}
                          {f.rule_id}
                        </td>
                        <td>
                          {label(f.outcome)} · {f.severity}
                        </td>
                        <td>{f.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
              <details>
                <summary>Injection and containment evidence per execution</summary>
                {view.cells.map((c) => (
                  <div key={c.id}>
                    <button onClick={() => update({ view: 'Tasks & rubrics', cell: c.id })}>
                      {c.task_key} / {names[c.model_key]} / {c.environment_key}
                    </button>
                    {c.assessment.safety.map((a) => (
                      <p key={a.axis}>
                        {a.axis}: {a.outcome} · {a.reason}
                        {a.axis === 'injection' && typeof a.legitimate_completion === 'boolean' && (
                          <>
                            {' '}
                            · Legitimate Task decision:{' '}
                            {a.legitimate_completion ? 'correct' : 'incorrect'} (source correctness
                            criterion, separate from resistance)
                          </>
                        )}
                      </p>
                    ))}
                  </div>
                ))}
              </details>
            </div>
          )}
          {tab === 'Remediation' && (
            <div className={s.card}>
              <div className={s.actions}>
                <h3>Failure-matched datasets</h3>
                <button disabled={!exportReady || busy} onClick={() => download('jsonl')}>
                  Export sample JSONL
                </button>
                <button
                  disabled={!exportReady || busy}
                  onClick={() =>
                    action(async () => {
                      await api(
                        endpoint + '/runs/' + runId + '/remediation?' + scopeString,
                        'POST',
                      );
                      setMessage(
                        'Evidence-bound draft dataset saved. No purchase or human verification created.',
                      );
                    })
                  }
                >
                  Save draft dataset
                </button>
              </div>
              {view.remediation.map((r) => (
                <article key={r.task_id}>
                  <h3>{r.title}</h3>
                  <p>{r.recommendation}</p>
                  <p>
                    <strong>Tasks + environments:</strong> {r.environment_ids.join(', ')}
                  </p>
                  <details>
                    <summary>View sample dataset</summary>
                    <pre>{JSON.stringify(r.sample, null, 2)}</pre>
                  </details>
                  <p className={s.note}>{r.licensing}</p>
                  <p>{r.improvement}</p>
                </article>
              ))}
            </div>
          )}
          {tab === 'Report preview' && (
            <div className={s.card}>
              <h3>Report Reviewed</h3>
              <p>
                <strong>{label(view.run.report_review.state)}</strong> · Executor:{' '}
                {view.run.report_review.executor?.name || 'Not executed'} · Contact:{' '}
                {view.run.report_review.contact || 'Not supplied'}
              </p>
              <p>
                {view.run.report_review.completed_reviewers} actual reviewer decisions; requirement{' '}
                {view.run.report_review.required_reviewers}. An actual Admin execution or
                exact-result Admin approval exempts further report review.
              </p>
              {view.run.report_review.decisions.map((d, i) => (
                <p key={i}>
                  {d.name}: {label(d.decision)}
                </p>
              ))}
              {!exportReady && view.run.state === 'completed' && (
                <button
                  disabled={busy}
                  onClick={() =>
                    action(async () => {
                      await api(endpoint + '/runs/' + runId + '/review', 'POST', {
                        expected_result_sha256: view.run.result_sha256,
                        decision: canAdmin ? 'admin_approved' : 'reviewed',
                        rationale:
                          'I have reviewed this exact benchmark result and its task-level evidence.',
                      });
                      setMessage('Your actual report decision was recorded.');
                    })
                  }
                >
                  {canAdmin ? 'Approve this exact report' : 'Record my review'}
                </button>
              )}
              <h3>PDF contents</h3>
              <ol>
                <li>Selected Run, Task Group, agents and environment scope</li>
                <li>Score bars, matched comparison and six-axis radar</li>
                <li>Task failures, policy outcomes and evidence identifiers</li>
                <li>Applicable remediation Task/environment datasets</li>
                <li>All Task rubrics, evaluation methodology and verifier versions</li>
                <li>Actual Report Reviewed state and exact result/scope hashes</li>
              </ol>
              <div className={s.actions}>
                <button disabled={!exportReady || busy} onClick={() => download('pdf')}>
                  Download report PDF
                </button>
                <button disabled={!exportReady || busy} onClick={() => download('json')}>
                  Download evidence JSON
                </button>
              </div>
              <details>
                <summary>Evidence and limitations</summary>
                {view.limitations.map((v) => (
                  <p key={v}>{v}</p>
                ))}
                <code>{view.view_sha256}</code>
              </details>
            </div>
          )}
          {!exportReady && (
            <p className={s.note}>
              Export is always available in this header once the Run is complete and its frozen
              report review requirement is satisfied.
            </p>
          )}
        </>
      )}
    </section>
  );
}
