'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import HarborWorkbench from './HarborWorkbench';
import WorkspacePreparation from './WorkspacePreparation';
import WorkspaceExecutionGroups from './WorkspaceExecutionGroups';
import {
  dateTime,
  Page,
  shortId,
  workspaceApi as api,
  WorkspaceRun,
  WorkspaceTask,
} from '../lib/workspace';
import styles from './ModernWorkspace.module.css';
import ui from './WorkspaceTasks.module.css';

type Actor = {
  objective?: string;
  stages?: { id: string; instruction: string; completion: string }[];
  evidence?: { id: string; content: string }[];
  actions?: { id: string; description: string }[];
  deliverables?: { id: string; description: string; path: string }[];
  constraints?: { id: string; description: string }[];
  environment?: { binding: string; initial_state: unknown };
};
type Task = {
  id: string;
  task_id: string;
  task_version: string;
  title: string;
  created_at: string;
  run_count: number;
  source_sha256: string;
  actor: Actor;
  versions: { id: string; task_version: string }[];
  packages: {
    id: string;
    base_image: string;
    package_sha256: string;
    stage_count: number;
    binding: string;
  }[];
  rubric: { criteria: Criterion[]; stages: { id: string; criteria: Criterion[] }[] };
  environments: { id: string; name: string; status: string; context_sha256: string }[];
};
type Criterion = { id: string; description: string; weight_bps: number };
const tabs = ['Task', 'MCP / Tool calls', 'Input files', 'Rubrics', 'Verifiers'];

export default function WorkspaceTasks({
  base,
  sourceId,
  mode,
  groupId,
  canPlan,
  canAdmin,
}: {
  base: string;
  sourceId?: string;
  mode?: string;
  groupId?: string | null;
  canPlan: boolean;
  canAdmin: boolean;
}) {
  const router = useRouter();
  const route = base.replace('/projects/', '/workspace/');
  const [search, setSearch] = useState(''),
    [filter, setFilter] = useState('all');
  const [page, setPage] = useState<Page<WorkspaceTask> | null>(null),
    [previous, setPrevious] = useState<string[]>([]),
    [cursor, setCursor] = useState('');
  const [task, setTask] = useState<Task | null>(null),
    [tab, setTab] = useState('Task');
  const [loading, setLoading] = useState(true),
    [error, setError] = useState(''),
    [revision, setRevision] = useState(0);
  const [importedId, setImportedId] = useState('');
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    setTask(null);
    setPage(null);
    if (sourceId === 'import') {
      setLoading(false);
      return;
    }
    const timer = setTimeout(
      () => {
        const path = sourceId
          ? '/tasks/' + encodeURIComponent(sourceId)
          : '/tasks?' +
            new URLSearchParams({
              search,
              status: filter,
              limit: '10',
              ...(cursor ? { after: cursor } : {}),
            });
        api(base + '/workspace' + path)
          .then((data) => {
            if (active) sourceId ? setTask(data) : setPage(data);
          })
          .catch((e) => {
            if (active) setError(e.message);
          })
          .finally(() => {
            if (active) setLoading(false);
          });
      },
      sourceId ? 0 : 200,
    );
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [base, sourceId, search, filter, cursor, revision]);
  const taskHref = (id: string) => route + '/tasks/' + id;
  if (sourceId === 'import')
    return (
      <section className={styles.panel}>
        <a href={route + '/tasks'}>← Tasks</a>
        <h2>Import task</h2>
        <HarborWorkbench
          base={base}
          api={api}
          canApprove={canAdmin}
          canPlan={canPlan}
          canAdmin={canAdmin}
          preparationHref={(id) => route + '/execution-groups/new?task=' + encodeURIComponent(id)}
          onSourceSelected={setImportedId}
        />
        {importedId && (
          <>
            <EnvironmentImport key={importedId} base={base} sourceId={importedId} />
            <a className="button" href={taskHref(importedId)}>
              View imported task
            </a>
          </>
        )}
      </section>
    );
  if (!sourceId)
    return (
      <section className={`${styles.panel} ${ui.taskList}`} aria-label="Task library">
        <div className={ui.toolbar}>
          <label className={ui.search}>
            Search tasks
            <input
              type="search"
              placeholder="Search tasks…"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setCursor('');
                setPrevious([]);
              }}
            />
          </label>
          <label>
            Status
            <select
              value={filter}
              onChange={(e) => {
                setFilter(e.target.value);
                setCursor('');
                setPrevious([]);
              }}
            >
              <option value="all">All tasks</option>
              <option value="ready">Package built</option>
              <option value="draft">Needs package</option>
            </select>
          </label>
          {canPlan && (
            <a className={`button ${ui.import}`} href={route + '/tasks/import'}>
              ＋ Import Task
            </a>
          )}
          <button onClick={() => setRevision(revision + 1)} disabled={loading}>
            Refresh tasks
          </button>
        </div>
        {error && (
          <p role="alert">
            {error} <button onClick={() => setRevision(revision + 1)}>Retry</button>
          </p>
        )}
        {loading && <p role="status">Loading tasks…</p>}
        <div className={styles.tableScroll}>
          <table className={ui.table}>
            <thead>
              <tr>
                <th>Task name</th>
                <th>Version</th>
                <th>Last run date / time</th>
                <th>Runs</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {page?.items.map((t) => (
                <tr key={t.id}>
                  <td>
                    <span className={`${ui.badge} ${t.package_built ? ui.ready : ui.draft}`}>
                      {t.package_built ? 'Package built' : 'Needs package'}
                    </span>
                    <strong>{t.title || t.task_id}</strong>
                    <small>{t.task_id}</small>
                  </td>
                  <td>
                    {t.task_version}
                    <small>
                      {t.versions} version{t.versions === 1 ? '' : 's'}
                    </small>
                  </td>
                  <td>{t.last_run_at ? dateTime(t.last_run_at) : 'Not run yet'}</td>
                  <td>{t.run_count}</td>
                  <td>
                    <div className={ui.rowActions}>
                      {canPlan && (
                        <a className={`button ${ui.run}`} href={taskHref(t.id) + '/run'}>
                          Run
                        </a>
                      )}
                      <a className="button" href={taskHref(t.id)}>
                        View
                      </a>
                    </div>
                    <a href={route + '/runs?task=' + encodeURIComponent(t.task_id)}>Run history</a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!loading && !error && !page?.items.length && (
          <div className={ui.empty}>
            <h3>
              {search || filter !== 'all' ? 'No matching tasks' : 'Your task library is empty'}
            </h3>
            <p>
              {search || filter !== 'all'
                ? 'Try another search or status.'
                : 'Import a task to inspect its instructions and configure a run.'}
            </p>
          </div>
        )}
        <div className={ui.pagination}>
          <span>{page?.items.length || 0} tasks on this page</span>
          <div className={ui.rowActions}>
            <button
              disabled={loading || !previous.length}
              onClick={() => {
                setCursor(previous.at(-1) || '');
                setPrevious(previous.slice(0, -1));
              }}
            >
              Previous
            </button>
            <span>Page {previous.length + 1}</span>
            <button
              disabled={loading || !page?.next_cursor}
              onClick={() => {
                setPrevious([...previous, cursor]);
                setCursor(page!.next_cursor!);
              }}
            >
              Next
            </button>
          </div>
        </div>
      </section>
    );
  if (loading) return <p role="status">Loading task version…</p>;
  if (error)
    return (
      <section className={styles.panel}>
        <p role="alert">{error}</p>
        <button onClick={() => setRevision(revision + 1)}>Retry</button>
        <a href={route + '/tasks'}>Back to Tasks</a>
      </section>
    );
  if (!task) return null;
  const pkg = task.packages[0];
  const run = mode === 'run';
  return (
    <div className={ui.detail}>
      <div className={ui.breadcrumb}>
        <a href={route + '/tasks'}>← Tasks</a>
        <span>/</span>
        <span>{run ? 'Run' : 'View'}</span>
      </div>
      <div className={styles.pageHead}>
        <div>
          <h2 className={ui.title}>
            {run ? 'Run: ' : ''}
            {task.title}
          </h2>
          <p className={styles.muted}>
            {task.task_id} · Version {task.task_version}
          </p>
        </div>
        <div className={ui.rowActions}>
          {run ? (
            <a className="button" href={taskHref(task.id)}>
              View task
            </a>
          ) : (
            canPlan && (
              <a className={`button ${ui.run}`} href={taskHref(task.id) + '/run'}>
                ▶ Run task
              </a>
            )
          )}
          <a className="button" href={route + '/runs?task=' + encodeURIComponent(task.task_id)}>
            Run history ({task.run_count})
          </a>
        </div>
      </div>
      {run ? (
        <>
          {!canPlan ? (
            <p role="alert">Your account cannot prepare runs in this project.</p>
          ) : !pkg ? (
            <section className={styles.panel}>
              <h3>Build a package first</h3>
              <p>This task version has no Harbor package yet.</p>
              <a className="button" href={route + '/tasks/import'}>
                Open import & package builder
              </a>
            </section>
          ) : (
            <div className={ui.runLayout}>
              <div>
                {groupId ? (
                  <WorkspaceExecutionGroups
                    key={groupId}
                    base={base}
                    groupId={groupId}
                    canAdmin={canAdmin}
                    expectedSourceId={task.id}
                    onUpdated={(id) => router.push(taskHref(task.id) + '/run?group=' + id)}
                    createHref={taskHref(task.id) + '/run'}
                  />
                ) : (
                  <WorkspacePreparation
                    base={base}
                    taskId={task.task_id}
                    sourceId={task.id}
                    packageId={pkg.id}
                    environments={task.environments}
                    createGroup
                    open={(id) => router.push(taskHref(task.id) + '/run?group=' + id)}
                  />
                )}
              </div>
              <ExecutionLog
                key={groupId || 'draft'}
                base={base}
                groupId={groupId}
                route={route}
                sourceId={task.id}
              />
            </div>
          )}
        </>
      ) : (
        <>
          <section className={`${styles.panel} ${ui.summary}`} aria-label="Task summary">
            <dl>
              <div>
                <dt>Task name</dt>
                <dd>{task.title}</dd>
              </div>
              <div>
                <dt>Version</dt>
                <dd>{task.task_version}</dd>
              </div>
              <div>
                <dt>Imported</dt>
                <dd>{dateTime(task.created_at)}</dd>
              </div>
              <div>
                <dt>Runs · all versions</dt>
                <dd>{task.run_count}</dd>
              </div>
            </dl>
            <label>
              View version
              <select value={task.id} onChange={(e) => router.push(taskHref(e.target.value))}>
                {task.versions.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.task_version}
                  </option>
                ))}
              </select>
            </label>
            {task.versions.length >= 100 && (
              <p className={styles.muted}>
                Showing the latest 100 versions and the currently opened version.
              </p>
            )}
          </section>
          <nav className={ui.tabs} aria-label="Task details">
            {tabs.map((name) => (
              <button key={name} aria-pressed={tab === name} onClick={() => setTab(name)}>
                {name}
              </button>
            ))}
          </nav>
          {tab === 'Task' && (
            <>
              <section className={styles.panel}>
                <h3>Task prompt & horizon specification</h3>
                <p className={ui.prompt}>{task.actor.objective}</p>
                {task.actor.stages?.map((s) => (
                  <article className={ui.card} key={s.id}>
                    <h4>{s.id}</h4>
                    <p className={ui.prompt}>{s.instruction}</p>
                    <small>Completion: {s.completion}</small>
                  </article>
                ))}
              </section>
              <section className={styles.panel}>
                <h3>Environment</h3>
                <dl className={ui.environment}>
                  <div>
                    <dt>Docker image</dt>
                    <dd>{pkg?.base_image || 'Build a package to bind its image'}</dd>
                  </div>
                  <div>
                    <dt>Task binding</dt>
                    <dd>{task.actor.environment?.binding || 'Not specified'}</dd>
                  </div>
                  <div>
                    <dt>Task horizon</dt>
                    <dd>{pkg ? pkg.stage_count + ' model calls per trial' : 'Not packaged'}</dd>
                  </div>
                </dl>
                <p className={styles.muted}>
                  Time and output limits are selected on Run Task. Task stages are fixed by this
                  version.
                </p>
                {task.environments.map((env) => (
                  <article className={ui.card} key={env.id}>
                    <strong>{env.name}</strong>
                    <p>Imported · Awaiting environment qualification</p>
                    <small>Context SHA-256: {env.context_sha256}</small>
                  </article>
                ))}
                {canPlan && (
                  <EnvironmentImport
                    base={base}
                    sourceId={task.id}
                    onSaved={() => setRevision(revision + 1)}
                  />
                )}
              </section>
              <section className={styles.panel}>
                <h3>Deliverables</h3>
                {task.actor.deliverables?.map((d) => (
                  <p key={d.id}>
                    <strong>{d.path}</strong> · {d.description}
                  </p>
                ))}
              </section>
            </>
          )}
          {tab === 'MCP / Tool calls' && (
            <section className={styles.panel}>
              <h3>Declared task actions</h3>
              <p className={styles.muted}>
                These are task-defined actions. No external MCP server is connected by importing a
                task.
              </p>
              {task.actor.actions?.length ? (
                task.actor.actions.map((a) => (
                  <article className={ui.card} key={a.id}>
                    <h4>{a.id}</h4>
                    <p>{a.description}</p>
                  </article>
                ))
              ) : (
                <p>No tool actions declared.</p>
              )}
            </section>
          )}
          {tab === 'Input files' && (
            <section className={styles.panel}>
              <h3>Actor-visible inputs</h3>
              {task.actor.evidence?.length ? (
                task.actor.evidence.map((e) => (
                  <details className={ui.card} key={e.id}>
                    <summary>{e.id}</summary>
                    <pre>{e.content}</pre>
                  </details>
                ))
              ) : (
                <p>No actor-visible inputs declared.</p>
              )}
              <p className={styles.muted}>Private grading references are excluded.</p>
            </section>
          )}
          {tab === 'Rubrics' && (
            <section className={styles.panel}>
              <h3>Evaluation rubrics</h3>
              <Rubric criteria={task.rubric.criteria} />
              {task.rubric.stages.map((s) => (
                <article key={s.id}>
                  <h4>{s.id}</h4>
                  <Rubric criteria={s.criteria} />
                </article>
              ))}
              <p className={styles.muted}>
                Descriptions and weights only. Private grading values and reference outputs stay
                hidden.
              </p>
            </section>
          )}
          {tab === 'Verifiers' && (
            <section className={styles.panel}>
              <h3>Verification constraints</h3>
              {task.actor.constraints?.map((c) => (
                <article key={c.id} className={ui.card}>
                  <h4>{c.id}</h4>
                  <p>{c.description}</p>
                </article>
              ))}
              <p>
                Executable verifiers are immutable in the package. Results appear after a trial is
                evaluated.
              </p>
            </section>
          )}
          <details className={ui.binding}>
            <summary>Exact version binding</summary>
            <p>Source SHA-256: {task.source_sha256}</p>
            {task.packages.map((p) => (
              <p key={p.id}>
                Package {shortId(p.id)}: {p.package_sha256}
              </p>
            ))}
          </details>
        </>
      )}
    </div>
  );
}
function Rubric({ criteria }: { criteria: Criterion[] }) {
  return (
    <div>
      {criteria.map((c) => (
        <article className={ui.criterion} key={c.id}>
          <div>
            <strong>{c.id}</strong>
            <p>{c.description}</p>
          </div>
          <span>{c.weight_bps / 100}%</span>
        </article>
      ))}
    </div>
  );
}

function EnvironmentImport({
  base,
  sourceId,
  onSaved,
}: {
  base: string;
  sourceId: string;
  onSaved?: () => void;
}) {
  const [name, setName] = useState(''),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState(''),
    [error, setError] = useState('');
  return (
    <div className={ui.card}>
      <h3>Import Docker environment</h3>
      <p>
        Select the environment folder containing Dockerfile and its companion inputs. Text files
        only, up to 1 MiB total.
      </p>
      <label>
        Environment name
        <input
          value={name}
          maxLength={100}
          onChange={(e) => setName(e.target.value)}
          placeholder="Marketing budget environment"
        />
      </label>
      <label>
        Environment folder
        <input
          type="file"
          multiple
          {...{ webkitdirectory: '' }}
          disabled={busy || !name.trim()}
          onChange={async (e) => {
            const files = Array.from(e.target.files || []);
            if (!files.length) return;
            setBusy(true);
            setError('');
            setNotice('');
            try {
              if (files.length > 100 || files.reduce((n, f) => n + f.size, 0) > 1048576)
                throw new Error('Select at most 100 text files, up to 1 MiB total.');
              const context = await Promise.all(
                files.map(async (file) => {
                  const content = new TextDecoder('utf-8', { fatal: true }).decode(
                    await file.arrayBuffer(),
                  );
                  if (content.includes('\0'))
                    throw new Error('Binary files are not supported in this environment import.');
                  const path = file.webkitRelativePath
                    ? file.webkitRelativePath.split('/').slice(1).join('/')
                    : file.name;
                  return { path, content };
                }),
              );
              await api(base + '/workspace/tasks/' + sourceId + '/environments', 'POST', {
                name,
                files: context,
              });
              setNotice(
                'Environment saved with this task version. Custom Dockerfiles remain quarantined until build isolation and scanner qualification are available; no build or execution was started.',
              );
              onSaved?.();
            } catch (err) {
              setError((err as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        />
      </label>
      <p className={styles.muted}>
        Import does not build the image. The qualified task-bound Harbor environment remains
        available for execution.
      </p>
      {busy && <p role="status">Saving environment…</p>}
      {notice && <p role="status">{notice}</p>}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}

function ExecutionLog({
  base,
  groupId,
  route,
  sourceId,
}: {
  base: string;
  groupId?: string | null;
  route: string;
  sourceId: string;
}) {
  const [runs, setRuns] = useState<WorkspaceRun[]>([]),
    [status, setStatus] = useState('Not started'),
    [error, setError] = useState(''),
    [total, setTotal] = useState(0),
    [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!groupId) return;
    let active = true,
      timer: ReturnType<typeof setTimeout>;
    async function poll() {
      let pollAgain = true;
      try {
        const group = await api(base + '/workspace/execution-groups/' + groupId);
        if (group.snapshot.preparation.package.source_id !== sourceId)
          throw new Error('This execution group belongs to a different task version.');
        const checks = group.models.filter((m: { check: unknown }) => m.check);
        const records = await Promise.all(
          checks.map((m: { check: { id: string } }) => api(base + '/workspace/runs/' + m.check.id)),
        );
        pollAgain =
          group.state !== 'launched' ||
          records.some((r: WorkspaceRun) => ['queued', 'running'].includes(r.state));
        if (active) {
          setRuns(records);
          setStatus(group.status === 'draft' ? 'Awaiting Run' : group.status);
          setTotal(group.models.length);
          setError('');
        }
      } catch (e) {
        if (active) setError((e as Error).message);
      } finally {
        if (active && pollAgain) timer = setTimeout(poll, 3000);
      }
    }
    void poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [base, groupId, sourceId, revision]);
  const done = runs.filter((r) => !['queued', 'running'].includes(r.state)).length;
  return (
    <section className={ui.logPanel} aria-label="Execution live log">
      <div className={ui.logHead}>
        <h3>Execution live log</h3>
        <span>{status.replaceAll('_', ' ')}</span>
        {groupId && <button onClick={() => setRevision(revision + 1)}>Refresh events</button>}
      </div>
      <div className={ui.console} role="log" aria-live="polite" aria-relevant="additions text">
        {error && <p role="alert">{error}</p>}
        {!runs.length && (
          <p>
            {groupId
              ? 'Configuration saved. Review setup requirements, then select Run to begin.'
              : 'Configure your models, environment, repetitions and budget. Execution events will appear here after launch.'}
          </p>
        )}
        {runs.map((r) => (
          <article key={r.id}>
            <p>
              [{dateTime(r.created_at)}] Trial {r.trial || 1} · {r.model} · {r.state}
            </p>
            {r.started_at && <p>Harbor execution started: {dateTime(r.started_at)}</p>}
            {r.calls?.map((c) => (
              <p key={c.stage_index}>
                Stage {c.stage_index + 1}: {c.status.replaceAll('_', ' ')}
                {c.finished_at ? ' · ' + dateTime(c.finished_at) : ''}
              </p>
            ))}
            {r.error_code && <p>Execution issue: {r.error_code}</p>}
            {r.finished_at && (
              <p>
                Finished: {dateTime(r.finished_at)} ·{' '}
                {r.metrics.score === null ? 'Unscored' : 'Score ' + r.metrics.score + '/100'}
              </p>
            )}
            <a href={route + '/runs?run=' + r.id + '&task=' + encodeURIComponent(r.task_id)}>
              View results & trajectories ↗
            </a>
          </article>
        ))}
      </div>
      <div className={ui.logFoot}>
        <progress aria-label="Completed trials" value={done} max={total || 1} />
        <span>
          {done} / {total} trials finished · Recorded lifecycle events
        </span>
        <small>Sanitized events only. Raw container logs and private reasoning are excluded.</small>
      </div>
    </section>
  );
}
