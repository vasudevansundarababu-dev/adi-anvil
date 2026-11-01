'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import HarborWorkbench from './HarborWorkbench';
import ModelProfiles from './ModelProfiles';
import FrameworkProfiles from './FrameworkProfiles';
import DiagnosticResults from './DiagnosticResults';
import WorkspaceRevisionEditor from './WorkspaceRevisionEditor';
import WorkspacePeople, { WorkspaceAccess } from './WorkspacePeople';
import WorkspacePreparation, { ExecutionPresets } from './WorkspacePreparation';
import {
  comparable,
  dateTime,
  money,
  Page,
  shortId,
  synthetic,
  workspaceApi as api,
  WorkspaceRun,
  WorkspaceTask,
} from '../lib/workspace';
import styles from './ModernWorkspace.module.css';

type Project = { id: string; name: string; roles: string[]; workspace_access: WorkspaceAccess };
type User = { id: string; name: string; projects: Project[] };
const navigation = [
  ['overview', 'Overview'],
  ['tasks', 'Tasks'],
  ['runs', 'Runs'],
  ['models', 'Models & keys'],
  ['frameworks', 'Frameworks'],
  ['people', 'People'],
  ['limits', 'Limits & usage'],
];
const runTabs = [
  'Dashboard',
  'Results',
  'Failure modes',
  'Trajectories',
  'Task & evaluations',
  'Usage',
];

export default function ModernWorkspace() {
  const pathname = usePathname();
  return <WorkspaceView key={pathname.split('/')[2] || 'default'} />;
}

function WorkspaceView() {
  const router = useRouter(),
    pathname = usePathname(),
    query = useSearchParams();
  const parts = pathname.split('/'),
    section = parts[3] || 'overview';
  const [user, setUser] = useState<User | null>(null),
    [ready, setReady] = useState(false);
  const [error, setError] = useState(''),
    [loading, setLoading] = useState(false),
    [dark, setDark] = useState(false);
  const [tasks, setTasks] = useState<Page<WorkspaceTask> | null>(null),
    [runs, setRuns] = useState<Page<WorkspaceRun> | null>(null);
  const [detail, setDetail] = useState<WorkspaceRun | null>(null),
    [selected, setSelected] = useState<string[]>([]);
  const [tab, setTab] = useState(
      runTabs.includes(query.get('tab') || '') ? query.get('tab')! : 'Dashboard',
    ),
    [prepare, setPrepare] = useState(false);
  const [frameworkRevision, setFrameworkRevision] = useState(0);
  const project =
    user?.projects.find((p) => p.id === parts[2]) || (parts[2] ? undefined : user?.projects[0]);
  const capabilities = project?.workspace_access.capabilities || [];
  const admin = capabilities.includes('models.manage');
  const allowed = capabilities.includes('workspace.read');
  const base = project ? '/projects/' + project.id : '',
    route = project ? '/workspace/' + project.id : '/workspace';
  const taskFilter = query.get('task'),
    runId = query.get('run');
  const diagnostic = query.get('kind') === 'diagnostic';
  const tasksEndpoint = diagnostic ? 'diagnostic-tasks' : 'tasks';
  const runsEndpoint = diagnostic ? 'diagnostic-runs' : 'runs';
  const scopeQuery = diagnostic ? 'kind=diagnostic' : '';
  const generation = useRef(0);
  useEffect(() => {
    let active = true;
    api('/me')
      .then((value) => {
        if (active) setUser(value);
      })
      .catch(() => {
        if (active) setUser(null);
      })
      .finally(() => {
        if (active) setReady(true);
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    if (project && !parts[2]) router.replace('/workspace/' + project.id + '/overview');
  }, [project, parts[2], router]);
  const load = useCallback(async () => {
    if (!base || !allowed) return;
    const current = ++generation.current;
    setLoading(true);
    setError('');
    setDetail(null);
    setTasks(null);
    setRuns(null);
    try {
      const [nextTasks, nextRuns, nextDetail] = await Promise.all([
        api(base + '/workspace/' + tasksEndpoint),
        api(
          base +
            '/workspace/' +
            runsEndpoint +
            (taskFilter ? '?task_id=' + encodeURIComponent(taskFilter) : ''),
        ),
        runId ? api(base + '/workspace/' + runsEndpoint + '/' + encodeURIComponent(runId)) : null,
      ]);
      if (current !== generation.current) return;
      setTasks(nextTasks);
      setRuns(nextRuns);
      setDetail(nextDetail);
    } catch (e) {
      if (current === generation.current) setError((e as Error).message);
    } finally {
      if (current === generation.current) setLoading(false);
    }
  }, [base, allowed, taskFilter, runId, section, tasksEndpoint, runsEndpoint]);
  useEffect(() => {
    void load();
    setPrepare(false);
    setSelected([]);
    return () => {
      generation.current++;
    };
  }, [load]);
  useEffect(() => {
    if (!detail || !['queued', 'running'].includes(detail.state)) return;
    const timer = setTimeout(() => {
      void load();
    }, 3000);
    return () => clearTimeout(timer);
  }, [detail, load]);
  function go(page: string) {
    setTab('Dashboard');
    router.push(route + '/' + page + (scopeQuery ? '?' + scopeQuery : ''));
  }
  function openRun(run: WorkspaceRun) {
    setTab('Dashboard');
    router.push(
      route +
        '/runs?run=' +
        run.id +
        (scopeQuery ? '&' + scopeQuery : '') +
        (taskFilter ? '&task=' + encodeURIComponent(taskFilter) : ''),
    );
  }
  const selectedRuns = (runs?.items || []).filter((r) => selected.includes(r.id));
  const title =
    section === 'preparation'
      ? 'Prepare evaluation'
      : section === 'editor'
        ? 'Edit as new version'
        : navigation.find(([key]) => key === section)?.[1] || 'Overview';
  const canEdit = capabilities.includes('task_drafts.write');
  const editorHref = (id: string, returnRun = query.get('return_run') || runId || '') =>
    route +
    '/editor?kind=diagnostic&revision=' +
    encodeURIComponent(id) +
    '&return_run=' +
    encodeURIComponent(returnRun);
  if (!ready)
    return (
      <main className={styles.login} role="status">
        Loading your Anvil session…
      </main>
    );
  if (!user)
    return (
      <main className={styles.login}>
        <img src="/brand/adi-anvil-logo-v1.png" alt="ADI Anvil" />
        <h1>One workspace for evaluation</h1>
        <p>Configure models, work with tasks and inspect the evidence behind every run.</p>
        <a className="button primary" href="/api/v1/auth/login">
          Sign in with Keycloak
        </a>
        <a href="/">Open classic Anvil</a>
      </main>
    );
  return (
    <div className={`${styles.workspace} ${dark ? styles.night : ''}`}>
      <aside className={styles.sidebar}>
        <a className={styles.brand} href={route + '/overview'}>
          ADI Anvil<small>Frontier evaluations</small>
        </a>
        <nav aria-label="Workspace navigation">
          {navigation
            .filter(([key]) => admin || !['models', 'frameworks', 'people', 'limits'].includes(key))
            .map(([key, label], i) => (
              <a
                key={key}
                href={route + '/' + key}
                aria-current={section === key ? 'page' : undefined}
              >
                {i === 3 && <small>Administration</small>}
                {label}
              </a>
            ))}
        </nav>
        <div className={styles.sidebarFoot}>
          <span>{admin ? 'Admin includes engineering work' : 'Engineering workspace'}</span>
          <a href={'/p/' + project?.id + '/harbor'}>Compare classic journey ↗</a>
        </div>
      </aside>
      <div className={styles.body}>
        <header className={styles.header}>
          <div>
            {user.projects.length > 1 ? (
              <select
                aria-label="Project"
                value={project?.id || ''}
                onChange={(e) => router.push('/workspace/' + e.target.value + '/overview')}
              >
                {user.projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            ) : (
              <span>{project?.name || 'No assigned project'}</span>
            )}
            <span className={styles.muted}> / {title}</span>
          </div>
          <div className={styles.actions}>
            <span>
              {user.name} · {project?.workspace_access.label || 'Project access'}
            </span>
            <button onClick={() => setDark(!dark)} aria-pressed={dark}>
              {dark ? 'Light' : 'Dark'} theme
            </button>
            <button
              onClick={async () => {
                try {
                  await api('/auth/logout', 'POST', {});
                  setUser(null);
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              Sign out
            </button>
          </div>
        </header>
        <main className={styles.content}>
          {!project || !allowed ? (
            <section className={styles.panel}>
              <h1>Workspace access unavailable</h1>
              <p>This account needs an assigned engineering or Admin capability in this project.</p>
              <a href="/">Open your classic workspace</a>
            </section>
          ) : (
            <>
              <div className={styles.pageHead}>
                <div>
                  <h1>
                    {detail
                      ? shortId(detail.id) + ' / ' + (detail.model || detail.candidate)
                      : taskFilter && section === 'runs'
                        ? 'Task run history'
                        : title}
                  </h1>
                  <p className={styles.muted}>
                    {detail
                      ? detail.title + ' · Task ' + detail.task_version
                      : section === 'runs'
                        ? taskFilter ||
                          (diagnostic
                            ? 'Diagnostic evaluations · whole-run metrics'
                            : 'All retained Harbor executions in this project')
                        : section === 'tasks'
                          ? 'Import, inspect and evaluate versioned tasks.'
                          : 'Configure once. Evaluate and inspect evidence in one workspace.'}
                  </p>
                </div>
                <div className={styles.actions}>
                  <button onClick={() => void load()} disabled={loading}>
                    Refresh
                  </button>
                  {['tasks', 'runs'].includes(section) && !diagnostic && (
                    <button className={styles.primary} onClick={() => setPrepare(!prepare)}>
                      {prepare ? 'Close preparation' : 'Import / prepare run'}
                    </button>
                  )}
                </div>
              </div>
              {['overview', 'tasks', 'runs'].includes(section) && (
                <nav className={styles.tabs} aria-label="Evaluation history source">
                  <a className="button" href={route + '/' + section}>
                    Harbor
                  </a>
                  <a className="button" href={route + '/' + section + '?kind=diagnostic'}>
                    Diagnostic evaluations
                  </a>
                </nav>
              )}
              {error && (
                <div className={styles.error} role="alert">
                  {error}
                </div>
              )}
              {loading && <p role="status">Loading project records…</p>}
              {prepare && (
                <section className={styles.panel}>
                  <HarborWorkbench
                    base={base}
                    api={api}
                    canApprove={project.roles.includes('product-owner')}
                    canPlan={capabilities.includes('harbor.prepare')}
                    canAdmin={admin}
                    preparationHref={(taskId) =>
                      route + '/preparation?task=' + encodeURIComponent(taskId)
                    }
                    onPackageBuilt={() => void load()}
                  />
                  <p className={styles.muted}>
                    Existing authorization and spending controls apply. Admin includes task import,
                    package building and execution preparation.
                  </p>
                </section>
              )}
              {section === 'overview' && (
                <Overview
                  tasks={tasks?.items || []}
                  runs={runs?.items || []}
                  admin={admin}
                  go={go}
                  openRun={openRun}
                />
              )}
              {section === 'tasks' && (
                <section className={styles.panel}>
                  <h2>Your tasks</h2>
                  <p className={styles.muted}>
                    {diagnostic
                      ? 'Versioned diagnostic tasks. History spans all revisions; metrics describe the whole run.'
                      : 'Praxis imports and immutable Harbor packages.'}
                  </p>
                  {tasks?.items.length ? (
                    <div className={styles.tableScroll}>
                      <table>
                        <thead>
                          <tr>
                            <th>Task</th>
                            <th>Latest version</th>
                            <th>Versions</th>
                            <th>Runs</th>
                            <th></th>
                          </tr>
                        </thead>
                        <tbody>
                          {tasks.items.map((t) => (
                            <tr key={t.task_id}>
                              <td>
                                <strong>{t.title || t.task_id}</strong>
                                <small>{t.task_id}</small>
                              </td>
                              <td>{t.task_version}</td>
                              <td>{t.versions}</td>
                              <td>{t.run_count}</td>
                              <td>
                                <a
                                  href={
                                    route +
                                    '/runs?task=' +
                                    encodeURIComponent(t.task_id) +
                                    (scopeQuery ? '&' + scopeQuery : '')
                                  }
                                >
                                  View run history
                                </a>
                                {!diagnostic && capabilities.includes('harbor.prepare') && (
                                  <a
                                    href={
                                      route + '/preparation?task=' + encodeURIComponent(t.task_id)
                                    }
                                  >
                                    Prepare evaluation
                                  </a>
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    !loading && (
                      <Empty
                        title="No imported tasks yet"
                        text="Use Import / prepare run to bring a Praxis task into this project."
                      />
                    )
                  )}
                  {tasks?.next_cursor && (
                    <button
                      onClick={async () => {
                        const current = generation.current;
                        try {
                          const next = await api(
                            base +
                              '/workspace/' +
                              tasksEndpoint +
                              '?after=' +
                              encodeURIComponent(tasks.next_cursor!),
                          );
                          if (current === generation.current)
                            setTasks({ ...next, items: [...tasks.items, ...next.items] });
                        } catch (e) {
                          if (current === generation.current) setError((e as Error).message);
                        }
                      }}
                    >
                      Load more tasks
                    </button>
                  )}
                </section>
              )}
              {section === 'runs' &&
                (detail ? (
                  <>
                    <div className={styles.actions}>
                      <a
                        href={
                          route +
                          '/runs' +
                          '?' +
                          scopeQuery +
                          (taskFilter ? '&task=' + encodeURIComponent(taskFilter) : '')
                        }
                      >
                        ← Run history
                      </a>
                      <Origin run={detail} />
                    </div>
                    <nav className={styles.tabs} aria-label="Run detail">
                      {runTabs.map((t) => (
                        <button key={t} aria-pressed={tab === t} onClick={() => setTab(t)}>
                          {t}
                        </button>
                      ))}
                    </nav>
                    <RunDetails
                      key={detail.id}
                      run={detail}
                      tab={tab}
                      base={base}
                      setTab={setTab}
                      canEdit={canEdit}
                      editorHref={editorHref}
                    />
                  </>
                ) : (
                  <>
                    <section className={styles.panel}>
                      <div className={styles.pageHead}>
                        <h2>Run history</h2>
                        <button
                          disabled={selected.length < 2}
                          onClick={() => setTab(tab === 'Compare' ? 'Dashboard' : 'Compare')}
                        >
                          {tab === 'Compare'
                            ? 'Close comparison'
                            : 'Compare selected (' + selected.length + ')'}
                        </button>
                      </div>
                      {runs?.items.length ? (
                        <RunTable
                          runs={runs.items}
                          selected={selected}
                          onSelect={(id) =>
                            setSelected(
                              selected.includes(id)
                                ? selected.filter((x) => x !== id)
                                : [...selected, id],
                            )
                          }
                          open={openRun}
                        />
                      ) : (
                        !loading && (
                          <Empty
                            title="No runs in this view"
                            text="Build an immutable task package and prepare an authorized execution. No sample results are inserted here."
                          />
                        )
                      )}
                      {runs?.next_cursor && (
                        <button
                          onClick={async () => {
                            const current = generation.current;
                            try {
                              const next = await api(
                                base +
                                  '/workspace/' +
                                  runsEndpoint +
                                  '?after=' +
                                  runs.next_cursor +
                                  (taskFilter ? '&task_id=' + encodeURIComponent(taskFilter) : ''),
                              );
                              if (current === generation.current)
                                setRuns({ ...next, items: [...runs.items, ...next.items] });
                            } catch (e) {
                              if (current === generation.current) setError((e as Error).message);
                            }
                          }}
                        >
                          Load more runs
                        </button>
                      )}
                    </section>
                    {tab === 'Compare' && <Comparison runs={selectedRuns} />}
                  </>
                ))}
              {section === 'editor' &&
                (query.get('revision') ? (
                  <WorkspaceRevisionEditor
                    key={base + query.get('revision')}
                    base={base}
                    revisionId={query.get('revision')!}
                    href={editorHref}
                    returnHref={
                      route +
                      '/runs?kind=diagnostic&run=' +
                      encodeURIComponent(query.get('return_run') || '') +
                      '&tab=' +
                      encodeURIComponent('Task & evaluations')
                    }
                    onSaved={(id) => router.replace(editorHref(id))}
                  />
                ) : (
                  <p>Open an exact task, rubric or evaluation version from a run snapshot.</p>
                ))}
              {section === 'models' && admin && <ModelProfiles key={base} base={base} />}
              {section === 'frameworks' && admin && (
                <>
                  <FrameworkProfiles
                    key={base}
                    base={base}
                    onSaved={() => setFrameworkRevision((value) => value + 1)}
                  />
                  <ExecutionPresets
                    key={base + '-presets'}
                    base={base}
                    frameworkRevision={frameworkRevision}
                  />
                </>
              )}
              {section === 'preparation' &&
                (capabilities.includes('harbor.prepare') ? (
                  <WorkspacePreparation
                    key={base + ':' + (query.get('task') || 'all')}
                    base={base}
                    taskId={query.get('task')}
                    preparationId={query.get('preparation')}
                    canReview={project.roles.includes('product-owner')}
                    canAdmin={admin}
                    open={(id) =>
                      router.replace(
                        route +
                          '/preparation?' +
                          (query.get('task')
                            ? 'task=' + encodeURIComponent(query.get('task')!) + '&'
                            : '') +
                          'preparation=' +
                          id,
                      )
                    }
                  />
                ) : (
                  <p role="alert">Preparation requires an assigned planning capability.</p>
                ))}
              {section === 'people' && admin && <WorkspacePeople key={base} base={base} />}
              {section === 'limits' && admin && (
                <section className={styles.panel}>
                  <h2>Operating boundaries</h2>
                  <p>
                    No default spending amount is granted. Existing exact-run authority, pricing,
                    data rights and cumulative reservations remain required.
                  </p>
                  <p>
                    External tracing is not enabled by this workspace. Unknown dispatch outcomes
                    retain their reservations.
                  </p>
                  <a href={'/p/' + project.id + '/providers'}>Inspect current provider readiness</a>
                </section>
              )}
              {!admin && ['models', 'frameworks', 'people', 'limits'].includes(section) && (
                <p role="alert">Administration is restricted to project Admins.</p>
              )}
            </>
          )}
          <footer className={styles.footer}>
            Modern workspace · existing project data · synthetic software checks are not model
            performance
          </footer>
        </main>
      </div>
    </div>
  );
}

function Empty({ title, text }: { title: string; text: string }) {
  return (
    <div className={styles.empty}>
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}
function Origin({ run }: { run: WorkspaceRun }) {
  return (
    <span className={styles.tag}>
      {run.kind === 'diagnostic'
        ? synthetic(run)
          ? 'Synthetic diagnostic fixture'
          : run.origin.replaceAll('_', ' ')
        : synthetic(run)
          ? 'Synthetic software check'
          : 'Model execution · unreviewed'}
    </span>
  );
}
function Stat({ label, value, note }: { label: string; value: string | number; note: string }) {
  return (
    <div className={styles.panel}>
      <small>{label}</small>
      <strong className={styles.value}>{value}</strong>
      <small>{note}</small>
    </div>
  );
}
function Overview({
  tasks,
  runs,
  admin,
  go,
  openRun,
}: {
  tasks: WorkspaceTask[];
  runs: WorkspaceRun[];
  admin: boolean;
  go: (page: string) => void;
  openRun: (r: WorkspaceRun) => void;
}) {
  return (
    <div className={styles.grid}>
      <section className={styles.panel}>
        <h2>{admin ? 'Set up your workspace' : 'Your evaluation workspace'}</h2>
        {(admin
          ? [
              ['Models & keys', 'Configure exact model IDs and inspect readiness.', 'models'],
              ['Frameworks', 'Inspect runner, agent and tracing capabilities.', 'frameworks'],
              ['People', 'Review assigned project access.', 'people'],
              ['Limits & usage', 'Inspect operating boundaries.', 'limits'],
            ]
          : [
              ['Tasks', 'Import and inspect versioned tasks.', 'tasks'],
              ['Runs', 'Review retained outputs and evidence.', 'runs'],
            ]
        ).map(([label, note, page]) => (
          <div key={page} className={styles.setupRow}>
            <div>
              <h3>{label}</h3>
              <small>{note}</small>
            </div>
            <button onClick={() => go(page)}>Open</button>
          </div>
        ))}
        <p className={styles.muted}>
          {tasks.length} tasks loaded. Additional pages are available in Tasks.
        </p>
      </section>
      <section className={styles.panel}>
        <h2>Recent runs</h2>
        {runs.length ? (
          runs.slice(0, 5).map((r) => (
            <div className={styles.setupRow} key={r.id}>
              <div>
                <h3>{r.title}</h3>
                <small>
                  {shortId(r.id)} · {r.state}
                </small>
                <Origin run={r} />
              </div>
              <button onClick={() => openRun(r)}>Open run</button>
            </div>
          ))
        ) : (
          <Empty
            title="No executions yet"
            text="Run history appears after an authorized execution is prepared."
          />
        )}
      </section>
    </div>
  );
}
function RunTable({
  runs,
  selected,
  onSelect,
  open,
}: {
  runs: WorkspaceRun[];
  selected: string[];
  onSelect: (id: string) => void;
  open: (run: WorkspaceRun) => void;
}) {
  return (
    <div className={styles.tableScroll}>
      <table>
        <thead>
          <tr>
            <th>Select</th>
            <th>Run / started</th>
            <th>Model / task</th>
            <th>Score</th>
            <th>Outcome</th>
            <th>Known cost</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id}>
              <td>
                <input
                  type="checkbox"
                  aria-label={'Select run ' + shortId(r.id)}
                  checked={selected.includes(r.id)}
                  onChange={() => onSelect(r.id)}
                />
              </td>
              <td>
                <strong>{shortId(r.id)}</strong>
                <small>{dateTime(r.created_at)}</small>
              </td>
              <td>
                {r.model || r.candidate}
                <small>Task {r.task_version}</small>
                <Origin run={r} />
              </td>
              <td>{r.metrics.score === null ? 'Unscored' : r.metrics.score + '/100'}</td>
              <td>
                {r.kind === 'diagnostic'
                  ? r.metrics.passed + ' / ' + r.metrics.scored + ' passed'
                  : r.metrics.task_failed
                    ? 'Task failed'
                    : r.metrics.passed
                      ? 'Full reward'
                      : r.state}
              </td>
              <td>
                {money(r.metrics.known_cost_micro_usd)}
                <small>{r.metrics.cost_complete ? 'Complete' : 'Partial / unresolved'}</small>
              </td>
              <td>
                <button onClick={() => open(r)}>Open run</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function Comparison({ runs }: { runs: WorkspaceRun[] }) {
  const [baseline, setBaseline] = useState(runs[0]?.id);
  const base = runs.find((r) => r.id === baseline) || runs[0];
  const eligible = comparable(runs);
  const fields: [string, (r: WorkspaceRun) => string | number][] = [
    ['Score', (r) => r.metrics.score ?? 'Unscored'],
    [
      'Scored / created / planned',
      (r) =>
        r.metrics.scored +
        ' / ' +
        r.metrics.attempts +
        ' / ' +
        (r.metrics.planned ?? r.metrics.attempts),
    ],
    ['Task version', (r) => r.task_version],
    ['Execution state', (r) => r.state],
    ['Task failures', (r) => r.metrics.task_failed],
    ['Execution errors', (r) => r.metrics.execution_errors],
    ['Unknown outcomes', (r) => r.metrics.unknown],
    [
      'Known cost',
      (r) => money(r.metrics.known_cost_micro_usd) + (r.metrics.cost_complete ? '' : ' · partial'),
    ],
    [
      'Duration',
      (r) => (r.metrics.elapsed_seconds === null ? 'Unknown' : r.metrics.elapsed_seconds + 's'),
    ],
  ];
  return (
    <section className={styles.panel}>
      <h2>Compare runs</h2>
      <label>
        Baseline{' '}
        <select value={base?.id || ''} onChange={(e) => setBaseline(e.target.value)}>
          {runs.map((r) => (
            <option key={r.id} value={r.id}>
              {shortId(r.id)} · {r.model || r.candidate}
            </option>
          ))}
        </select>
      </label>
      <p className={styles.notice}>
        {eligible
          ? 'Matching package, origin and scoring signature. No significance claim is made.'
          : 'Different or unscored execution signatures: descriptive comparison only. Score deltas are unavailable.'}
      </p>
      <div className={styles.tableScroll}>
        <table>
          <thead>
            <tr>
              <th>Metric</th>
              {runs.map((r) => (
                <th key={r.id}>
                  {shortId(r.id)}
                  <small>{r.model || r.candidate}</small>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {fields.map(([name, fn]) => (
              <tr key={name}>
                <th>{name}</th>
                {runs.map((r) => (
                  <td key={r.id}>{fn(r)}</td>
                ))}
              </tr>
            ))}
            {eligible && (
              <tr>
                <th>Score Δ vs baseline</th>
                {runs.map((r) => (
                  <td key={r.id}>
                    {((r.metrics.score || 0) - (base.metrics.score || 0)).toFixed(2)} points
                  </td>
                ))}
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className={styles.muted}>
        Harbor checks have one attempt; diagnostic metrics describe the whole run. Only finalized
        valid grades enter diagnostic score denominators. Fixture and real-execution cohorts stay
        separate.
      </p>
    </section>
  );
}
function RunDetails({
  run,
  tab,
  base,
  setTab,
  canEdit,
  editorHref,
}: {
  run: WorkspaceRun;
  tab: string;
  base: string;
  setTab: (tab: string) => void;
  canEdit: boolean;
  editorHref: (id: string) => string;
}) {
  const [evidence, setEvidence] = useState<{
      kind: string;
      content: string;
      sha256: string;
    } | null>(null),
    [error, setError] = useState(''),
    [pending, setPending] = useState(false);
  const m = run.metrics;
  async function inspect(id: string) {
    setPending(true);
    setError('');
    try {
      setEvidence(await api(base + '/workspace/runs/' + run.id + '/evidence/' + id));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(false);
    }
  }
  if (tab === 'Dashboard')
    return (
      <>
        <div className={styles.stats}>
          <Stat
            label={run.kind === 'diagnostic' ? 'Reviewed mean score' : 'Automated score'}
            value={m.score === null ? 'Unscored' : m.score + '/100'}
            note={m.scored + ' scored / ' + m.attempts + ' created attempts'}
          />
          <Stat
            label="Task outcome"
            value={
              run.kind === 'diagnostic'
                ? m.passed + ' / ' + m.scored + ' passed'
                : m.passed
                  ? 'Full reward'
                  : m.task_failed
                    ? 'Task failed'
                    : run.state
            }
            note="Execution state and task outcome are separate"
          />
          <Stat
            label="Duration"
            value={m.elapsed_seconds === null ? 'Unknown' : m.elapsed_seconds + 's'}
            note="Recorded runner duration"
          />
          <Stat
            label="Known cost"
            value={money(m.known_cost_micro_usd)}
            note={m.cost_complete ? 'Complete recorded cost' : 'Partial / unresolved'}
          />
        </div>
        <div className={styles.grid}>
          <section className={styles.panel}>
            <h2>Evaluation results</h2>
            {run.kind === 'diagnostic' ? (
              <p>
                Scored: {m.scored}; pending: {m.pending}; canceled: {m.cancelled}; invalid:{' '}
                {m.invalid}. Planned: {m.planned}. Whole-run metrics; finalized pass/fail scores
                only.
              </p>
            ) : (
              <Diagnostics data={run.diagnostics} />
            )}
          </section>
          <section className={styles.panel}>
            <h2>What needs attention</h2>
            <p>Task failures: {m.task_failed}</p>
            <p>Execution errors: {m.execution_errors}</p>
            <p>Unknown outcomes: {m.unknown}</p>
            {run.error_code && <p>{run.error_code}</p>}
            <div className={styles.actions}>
              <button onClick={() => setTab('Failure modes')}>Inspect failures</button>
              <button onClick={() => setTab('Results')}>All results</button>
            </div>
          </section>
        </div>
      </>
    );
  if (tab === 'Task & evaluations')
    return (
      <div className={styles.grid}>
        <section className={styles.panel}>
          <h2>Task snapshot · {run.task_version}</h2>
          <p>
            {String(run.actor_snapshot?.objective || 'Inspect the actor-visible snapshot below.')}
          </p>
          <details>
            <summary>
              {run.kind === 'diagnostic' ? 'Bound task metadata' : 'Actor-visible task definition'}
            </summary>
            <pre>{JSON.stringify(run.actor_snapshot, null, 2)}</pre>
          </details>
          <p className={styles.muted}>Source revision {run.source_revision_id}</p>
          <p className={styles.hash}>Binding SHA-256: {run.source_sha256}</p>
          {run.kind === 'diagnostic' && canEdit && (
            <details>
              <summary>Edit a task as a new version</summary>
              <ul>
                {(Array.isArray(run.actor_snapshot?.tasks) ? run.actor_snapshot.tasks : []).map(
                  (t: { revision_id: string; title: string }) => (
                    <li key={t.revision_id}>
                      <a href={editorHref(t.revision_id)}>{t.title}</a>
                    </li>
                  ),
                )}
              </ul>
            </details>
          )}
        </section>
        <section className={styles.panel}>
          <h2>Bound evaluation configuration</h2>
          <pre>{JSON.stringify(run.evaluation_snapshot, null, 2)}</pre>
          {run.kind === 'diagnostic' && canEdit && (
            <>
              <a className="button" href={editorHref(run.source_revision_id!)}>
                Edit evaluation as new version
              </a>
              <details>
                <summary>Edit a rubric as a new version</summary>
                <ul>
                  {(Array.isArray(run.evaluation_snapshot?.rubrics)
                    ? run.evaluation_snapshot.rubrics
                    : []
                  ).map((r: { revision_id: string }) => (
                    <li key={r.revision_id}>
                      <a href={editorHref(r.revision_id)}>Rubric {shortId(r.revision_id)}</a>
                    </li>
                  ))}
                </ul>
              </details>
            </>
          )}
          <p className={styles.muted}>
            Historical inputs are read-only. Editing opens a separate version workspace and creates
            an unapproved draft. Existing run evidence is never overwritten. Source-asset changes
            require a new import.
          </p>
        </section>
      </div>
    );
  if (tab === 'Usage')
    return (
      <section className={styles.panel}>
        <h2>Usage & accounting</h2>
        <p>
          Known cost: {money(m.known_cost_micro_usd)} ·{' '}
          {m.cost_complete ? 'complete' : 'partial / unresolved'}
        </p>
        <p>Reserved calls: {money(m.reserved_micro_usd)}</p>
        <p>
          Started: {dateTime(run.started_at)}
          <br />
          Finished: {dateTime(run.finished_at)}
        </p>
        {run.calls?.length ? (
          <pre>{JSON.stringify(run.calls, null, 2)}</pre>
        ) : (
          <p>
            {run.kind === 'diagnostic'
              ? 'Detailed provider-call records are not projected in this view; missing usage is not zero usage.'
              : 'No model-provider calls recorded for this execution.'}
          </p>
        )}
      </section>
    );
  if (tab === 'Failure modes')
    return (
      <section className={styles.panel}>
        <h2>Failure modes & execution issues</h2>
        <p>
          {run.kind === 'diagnostic'
            ? m.task_failed +
              ' finalized task failures; ' +
              m.execution_errors +
              ' execution errors; ' +
              m.unknown +
              ' unknown outcomes.'
            : m.task_failed
              ? 'Automated task constraints did not receive full reward.'
              : m.passed
                ? 'All executable checks received full reward.'
                : 'No scored task outcome is available.'}
        </p>
        {run.error_code && <p>Runner error: {run.error_code}</p>}
        {!!m.unknown && (
          <p>Dispatch outcome is unresolved. No automatic retry or zero-cost assumption.</p>
        )}
        {run.kind === 'diagnostic' ? (
          <p>
            Scored: {m.scored}; pending: {m.pending}; canceled: {m.cancelled}; invalid: {m.invalid}.
            Planned: {m.planned}. Whole-run metrics; finalized pass/fail scores only.
          </p>
        ) : (
          <Diagnostics data={run.diagnostics} />
        )}
        <button onClick={() => setTab('Trajectories')}>Inspect observable evidence</button>
      </section>
    );
  if (run.kind === 'diagnostic')
    return (
      <DiagnosticResults
        key={base + run.id}
        base={base}
        run={run}
        trajectory={tab === 'Trajectories'}
      />
    );
  return (
    <section className={styles.panel}>
      <h2>{tab === 'Results' ? 'Results & retained outputs' : 'Observable trajectory'}</h2>
      <p className={styles.muted}>{run.trajectory_limitations}</p>
      {tab === 'Trajectories' && !!run.calls?.length && (
        <ol aria-label="Observed stage events">
          {run.calls.map((call) => (
            <li key={call.stage_index}>
              <h3>
                Stage {call.stage_index + 1} · {call.status.replaceAll('_', ' ')}
              </h3>
              <p>
                Intent recorded: {dateTime(call.created_at || null)}. Outcome captured:{' '}
                {dateTime(call.finished_at || null)}.
              </p>
              <p>Request ID: {call.request_id || 'not captured'}</p>
              <details>
                <summary>Actor context actually supplied</summary>
                {call.actor_context ? (
                  <pre>{call.actor_context}</pre>
                ) : (
                  <p>Verified context is unavailable; no reconstruction is shown.</p>
                )}
                <small>Actor-context SHA-256: {call.request_sha256}</small>
              </details>
              <details>
                <summary>Captured final output</summary>
                {call.output_text !== null && call.output_text !== undefined ? (
                  <pre>{call.output_text}</pre>
                ) : (
                  <p>No terminal captured output is available. Unknown dispatch is not retried.</p>
                )}
              </details>
              <details>
                <summary>Usage and finish status</summary>
                <pre>{JSON.stringify(call.usage, null, 2)}</pre>
              </details>
            </li>
          ))}
        </ol>
      )}
      <p>
        Execution {run.state} ·{' '}
        {m.score === null ? 'unscored' : 'automated score ' + m.score + '/100'}
      </p>
      <div className={styles.actions}>
        {run.evidence?.map((e, i) => (
          <button
            key={e.artifact_id}
            disabled={pending}
            onClick={() => void inspect(e.artifact_id)}
          >
            {e.kind} · {i + 1}
          </button>
        ))}
      </div>
      {!run.evidence?.length && (
        <Empty
          title="No retained output evidence"
          text="Queued, failed, canceled or unknown executions may have no output. No trajectory is generated to fill a gap."
        />
      )}
      {pending && <p role="status">Loading permitted evidence…</p>}
      {error && <p role="alert">{error}</p>}
      {evidence && (
        <>
          <h3>{evidence.kind}</h3>
          <pre>{evidence.content}</pre>
          <p className={styles.hash}>SHA-256: {evidence.sha256}</p>
        </>
      )}
      <details>
        <summary>Recorded lifecycle timestamps</summary>
        <p>
          Prepared: {dateTime(run.created_at)}
          <br />
          Started: {dateTime(run.started_at)}
          <br />
          Finished: {dateTime(run.finished_at)}
        </p>
      </details>
      <p className={styles.muted}>
        Only actual retained outputs and runner evidence. Private model reasoning and restricted
        reference content are excluded.
      </p>
    </section>
  );
}
function Diagnostics({ data }: { data?: Record<string, unknown> | null }) {
  if (!data) return <p className={styles.muted}>No evaluator results recorded.</p>;
  const stages = (Array.isArray(data.stages) ? data.stages : [data]) as {
    stage_id?: string;
    reward?: number;
    diagnostic_score?: number;
    hard_failures?: string[];
    criteria?: Record<string, { passed: boolean; weight_bps: number }>;
  }[];
  return (
    <>
      {stages.map((stage, i) => (
        <div className={styles.diagnostic} key={stage.stage_id || i}>
          <h3>{stage.stage_id || 'Decision'}</h3>
          <p>
            Reward: {stage.reward ?? 'Unknown'} · diagnostic score:{' '}
            {stage.diagnostic_score ?? 'Unknown'}
          </p>
          {stage.hard_failures?.length ? (
            <p>Hard failures: {stage.hard_failures.join(', ')}</p>
          ) : null}
          {stage.criteria &&
            Object.entries(stage.criteria).map(([id, c]) => (
              <div className={styles.criterion} key={id}>
                <span>
                  {id} <small>{c.weight_bps / 100}% weight</small>
                </span>
                <strong>{c.passed ? 'Pass' : 'Fail'}</strong>
              </div>
            ))}
        </div>
      ))}
    </>
  );
}
function Frameworks() {
  return (
    <>
      <div className={styles.grid}>
        {[
          [
            'Harbor',
            'Evaluation runner',
            'Existing pinned structured/staged adapter. Configure and run through Tasks.',
          ],
          [
            'LangSmith',
            'Tracing / evaluation',
            'Adapter not implemented. No destination, credentials or external trace export enabled.',
          ],
          [
            'Semantic Kernel',
            'Candidate agent orchestration',
            'Adapter not implemented. Requested compatibility remains separate from Microsoft Agent Framework.',
          ],
        ].map(([name, role, note]) => (
          <section className={styles.panel} key={name}>
            <span className={styles.tag}>{role}</span>
            <h2>{name}</h2>
            <p>{note}</p>
          </section>
        ))}
      </div>
      <section className={styles.panel}>
        <h2>Platform orchestration</h2>
        <p>
          Anvil / LangGraph retains durable checkpoints, authorization and accounting. Adding
          framework metadata will not install an SDK or enable execution.
        </p>
      </section>
    </>
  );
}
