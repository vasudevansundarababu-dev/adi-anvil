'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Fragment, useState } from 'react';
import { GymApiError, send, short, when, wsBase } from './api';
import { SuiteEditor, SuitesTab } from './Suites';
import { Badge, Env, Failure, Hash, Loading, Search, Tabs, useData, useGym } from './ui';

function caseText(sel: any) {
  if (!sel) return '—';
  return [sel.application_type, sel.completeness, ...(sel.edge_cases ?? [])]
    .filter(Boolean)
    .join(' · ');
}

function SuggestedAction({ actions }: { actions: any[] }) {
  const router = useRouter();
  const first = actions[0];
  if (!first) return null;
  return (
    <label style={{ textAlign: 'left' }}>
      <select
        aria-label={`Suggested: ${first.label}`}
        value=""
        onChange={(e) => e.target.value && router.push(e.target.value)}
        style={{
          borderColor:
            first.kind === 'bad' ? '#dc2626' : first.kind === 'warn' ? '#d97706' : undefined,
        }}
      >
        <option value="">Suggested: {first.label}</option>
        {actions.map((a, i) => (
          <option key={a.label} value={a.link}>
            {i === 0 ? '★ ' : ''}
            {a.label}
          </option>
        ))}
      </select>
      {first.reason ? <small>{first.reason}</small> : null}
    </label>
  );
}

export function ProjectsList() {
  const { ws } = useGym();
  const [q, setQ] = useState('');
  const [state, setState] = useState('');
  const params = new URLSearchParams({ ...(q ? { q } : {}), ...(state ? { state } : {}) });
  const { data, error } = useData<any>(`${wsBase(ws)}/projects?${params}`);
  return (
    <main className="page">
      <div className="toolbar">
        <div>
          <h2>Projects</h2>
          <small>
            Authoring projects in this workspace. Projects are created only by Authoring export.
          </small>
        </div>
        <Search value={q} onChange={setQ} placeholder="Search projects" />
        <label>
          <small>Status</small>
          <select value={state} onChange={(e) => setState(e.target.value)} aria-label="Status">
            <option value="">All</option>
            <option value="ready">Ready</option>
            <option value="blocked">Blocked</option>
            <option value="revoked">Revoked</option>
          </select>
        </label>
      </div>
      <Loading data={data} error={error}>
        {() => (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Project</th>
                  <th>Mode</th>
                  <th>Template</th>
                  <th>Environment</th>
                  <th>Tasks</th>
                  <th>Status</th>
                  <th>Last export</th>
                  <th>Suggested action</th>
                </tr>
              </thead>
              <tbody>
                {data.items.length === 0 && (
                  <tr>
                    <td colSpan={8} style={{ textAlign: 'left' }}>
                      No {state || ''} projects.
                    </td>
                  </tr>
                )}
                {data.items.map((p: any) => (
                  <tr key={p.project_id}>
                    <td>
                      <Link className="link" href={`/gym/projects/${p.project_id}`}>
                        {p.name}
                      </Link>
                      <small>Project ID {p.project_id}</small>
                    </td>
                    <td>
                      <Badge
                        state="progress"
                        label={p.mode === 'single_agent' ? 'Single agent' : 'Multi agent'}
                      />
                    </td>
                    <td>
                      {p.template_name}
                      <small>Template ID {p.template_id}</small>
                    </td>
                    <td>
                      {p.environments.map((e: any) => (
                        <div key={e.alias}>
                          <Env ok={e.ok} label={e.label} />
                        </div>
                      ))}
                    </td>
                    <td>
                      <Link href={`/gym/projects/${p.project_id}/tasks`}>{p.tasks} tasks</Link>
                    </td>
                    <td>
                      <Badge state={p.state} />
                    </td>
                    <td>
                      {p.last_export ? (
                        <>
                          {p.last_export.export_id} · {when(p.last_export.received_at)}
                          <small>
                            {p.last_export.new_count} new · {p.last_export.superseding_count}{' '}
                            superseding · {p.last_export.unchanged_count} unchanged
                          </small>
                        </>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td>
                      <SuggestedAction actions={p.suggested_actions} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p style={{ padding: '0 14px 10px' }}>
              <small>
                {data.items.length} of {data.total} projects
              </small>
            </p>
          </div>
        )}
      </Loading>
    </main>
  );
}

export function ProjectPage({ id, tab, rest }: { id: string; tab: string; rest: string[] }) {
  const { ws } = useGym();
  const project = useData<any>(`${wsBase(ws)}/projects/${id}`);
  const base = `/gym/projects/${id}`;
  if (tab === 'tasks' && rest[0]) return <TaskDetail project={id} taskId={rest[0]} />;
  if (tab === 'suites' && rest[0])
    return <SuiteEditor project={id} id={rest[0]} step={rest[1] ?? 'bindings'} />;
  return (
    <Loading data={project.data} error={project.error}>
      {() => {
        const p = project.data;
        return (
          <div className="work">
            <aside>
              <Link href="/gym/projects">← Back to projects</Link>
              <small>Project · from Authoring</small>
              <h3>{p.name}</h3>
              <Badge state={p.state} />
              {p.state_reason ? <small>{p.state_reason}</small> : null}
              <dl className="kv">
                <dt>Mode</dt>
                <dd>{p.mode === 'single_agent' ? 'Single agent' : 'Multi agent'}</dd>
                <dt>Environment</dt>
                <dd>
                  {p.environments.map((e: any) => (
                    <div key={e.alias}>
                      <Env ok={e.ok} label={e.label} />
                    </div>
                  ))}
                </dd>
                <dt>Project ID</dt>
                <dd>
                  <code>{p.project_id}</code> (Authoring)
                </dd>
                <dt>Template ID</dt>
                <dd>
                  <code>
                    {p.template_id} V{p.template_version}
                  </code>{' '}
                  (Studio)
                </dd>
              </dl>
              <Link
                href={p.state === 'ready' ? `/gym/runs/new?project=${p.project_id}` : '#'}
                aria-disabled={p.state !== 'ready'}
                title={p.state === 'ready' ? 'Run benchmark' : `Project is ${p.state}`}
                style={p.state === 'ready' ? {} : { pointerEvents: 'none', opacity: 0.55 }}
              >
                Run benchmark
              </Link>
              <small>
                Results for SME review are sent to this Authoring project (SME review is work
                package 2.9).
              </small>
            </aside>
            <main>
              <Tabs
                current={tab}
                items={[
                  { key: 'tasks', label: 'Tasks', href: `${base}/tasks` },
                  {
                    key: 'selection-rules',
                    label: 'Selection rules',
                    href: `${base}/selection-rules`,
                    badge: p.overrides_waiting,
                  },
                  { key: 'exports', label: 'Exports', href: `${base}/exports` },
                  { key: 'suites', label: 'Suites and runs', href: `${base}/suites` },
                ]}
              />
              {tab === 'tasks' && <TasksTab project={id} />}
              {tab === 'selection-rules' && (
                <SelectionRules project={id} reloadProject={project.reload} />
              )}
              {tab === 'exports' && <ExportsTab project={id} />}
              {tab === 'suites' && <SuitesTab project={id} />}
            </main>
          </div>
        );
      }}
    </Loading>
  );
}

function TasksTab({ project }: { project: string }) {
  const { ws } = useGym();
  const [q, setQ] = useState('');
  const { data, error } = useData<any>(
    `${wsBase(ws)}/projects/${project}/tasks${q ? `?q=${encodeURIComponent(q)}` : ''}`,
  );
  return (
    <>
      <div className="toolbar">
        <Search value={q} onChange={setQ} placeholder="Search tasks" />
        <small>Read-only: tasks change only in Authoring.</small>
      </div>
      <Loading data={data} error={error}>
        {() => (
          <div className="table-wrap scroll">
            <table>
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Case</th>
                  <th>Source</th>
                  <th>State</th>
                </tr>
              </thead>
              <tbody>
                {data.items.length === 0 && (
                  <tr>
                    <td colSpan={4} style={{ textAlign: 'left' }}>
                      No tasks in this project.
                    </td>
                  </tr>
                )}
                {data.items.map((t: any) => (
                  <tr key={t.id}>
                    <td>
                      <Link
                        className="link"
                        href={`/gym/projects/${project}/tasks/${t.task_id}?revision=${t.revision}`}
                      >
                        {t.task_id} · r{t.revision}
                      </Link>
                      <small>
                        {t.title} · <Hash value={t.package_sha256} />
                      </small>
                    </td>
                    <td>{caseText(t.case_selector)}</td>
                    <td>
                      {t.corrects_revision
                        ? `Corrected in Authoring (corrects r${t.corrects_revision})`
                        : 'Exported by Authoring'}
                      {t.sme_batch_id ? <small>SME batch {t.sme_batch_id}</small> : null}
                      <small>{t.export_id}</small>
                    </td>
                    <td>
                      <Badge state={t.state} />
                      {t.state_reason ? <small>{t.state_reason}</small> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Loading>
    </>
  );
}

function TaskDetail({ project, taskId }: { project: string; taskId: string }) {
  const { ws } = useGym();
  const query = useSearchParams();
  const revision = query.get('revision');
  const { data, error } = useData<any>(
    `${wsBase(ws)}/projects/${project}/tasks/${taskId}${revision ? `?revision=${revision}` : ''}`,
  );
  return (
    <Loading data={data} error={error}>
      {() => (
        <div className="work">
          <aside>
            <Link href={`/gym/projects/${project}/tasks`}>← Back to {data.project.name}</Link>
            <dl className="kv">
              <dt>Project</dt>
              <dd>
                {data.project.name} · <code>{data.project.project_id}</code>
              </dd>
              <dt>Mode</dt>
              <dd>{data.project.mode}</dd>
              <dt>Revisions</dt>
              <dd>
                {data.revisions.map((r: any) => (
                  <div key={r.revision}>
                    r{r.revision} · {r.export_id} · <Badge state={r.state} />
                  </div>
                ))}
              </dd>
            </dl>
            <small>Bindings are set per project under Selection rules, never per task.</small>
          </aside>
          <main>
            <div className="row">
              <h3>
                {data.task.task_id} · revision {data.task.revision}
              </h3>
              <Badge state={data.task.state} />
              <span className="badge immut">Immutable</span>
            </div>
            <dl className="kv">
              <dt>Template</dt>
              <dd>{data.template_name}</dd>
              <dt>Case</dt>
              <dd>{caseText(data.task.case_selector)}</dd>
              <dt>Package</dt>
              <dd>
                <Hash value={data.task.package_sha256} />
              </dd>
            </dl>
            <section className="card">
              <h4>As the agent sees it</h4>
              <PartView value={data.actor} labels={ACTOR_LABELS} />
            </section>
            <section className="card">
              <h4>
                Rubric and expected result <Badge state="deprecated" label={data.private_label} />
              </h4>
              <PartView value={data.private} labels={PRIVATE_LABELS} />
            </section>
            {data.workflow && (
              <section className="card">
                <h4>Workflow</h4>
                <div className="flow">
                  {data.workflow.nodes.map((n: any, i: number) => (
                    <span key={n.id} className="row">
                      {i > 0 && <span className="arrow">→</span>}
                      <span className="node">{n.label}</span>
                    </span>
                  ))}
                </div>
              </section>
            )}
            <section className="card">
              <h4>Runs of this task</h4>
              <small>{data.runs_note}</small>
            </section>
          </main>
        </div>
      )}
    </Loading>
  );
}

function ExportsTab({ project }: { project: string }) {
  const { ws } = useGym();
  const { data, error } = useData<any>(`${wsBase(ws)}/projects/${project}/exports`);
  return (
    <Loading data={data} error={error}>
      {() => (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Export</th>
                <th>Received</th>
                <th>Tasks</th>
                <th>Result</th>
                <th>Hash</th>
              </tr>
            </thead>
            <tbody>
              {data.items.length === 0 && (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'left' }}>
                    No exports yet.
                  </td>
                </tr>
              )}
              {data.items.map((e: any) => (
                <tr key={e.export_id}>
                  <td>
                    <strong>{e.export_id}</strong>
                    <small>{e.reason}</small>
                  </td>
                  <td>{when(e.received_at)}</td>
                  <td>{e.new_count + e.superseding_count + e.unchanged_count}</td>
                  <td>
                    {e.new_count} new · {e.superseding_count} superseding · {e.unchanged_count}{' '}
                    unchanged · {e.blocked_count} blocked
                    {e.blocked.map((b: any) => (
                      <small key={b.task_id}>
                        {b.task_id}: {b.reason} ({b.alias})
                      </small>
                    ))}
                  </td>
                  <td>
                    <Hash value={e.export_sha256} />
                    <small>
                      receipt <Hash value={e.receipt_sha256} />
                    </small>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Loading>
  );
}

function ruleOptionValue(o: any) {
  return JSON.stringify({
    kind: o.kind,
    pinned_version_id: o.pinned_version_id,
    seed_family: o.seed_family,
  });
}

function SelectionRules({
  project,
  reloadProject,
}: {
  project: string;
  reloadProject: () => void;
}) {
  const { ws, say, refreshTodo } = useGym();
  const query = useSearchParams();
  const router = useRouter();
  const view = useData<any>(`${wsBase(ws)}/projects/${project}/selection-rules`);
  const [alias, setAlias] = useState('');
  const [rule, setRule] = useState('');
  const [reason, setReason] = useState(
    query.get('fix') ? 'The pinned version can no longer be selected' : '',
  );
  const [failure, setFailure] = useState<GymApiError | null>(null);
  const review = query.get('review');
  const reload = () => {
    view.reload();
    reloadProject();
    refreshTodo();
  };
  async function request() {
    setFailure(null);
    try {
      const current = view.data.aliases.find(
        (a: any) => a.alias === (alias || view.data.aliases[0].alias),
      );
      const o = JSON.parse(rule);
      const row = await send('POST', `${wsBase(ws)}/rule-overrides`, {
        project_id: project,
        alias: current.alias,
        to_rule: o,
        reason,
      });
      say(`Override ${row.short_id} requested; a binding approver other than you decides.`);
      setReason('');
      setRule('');
      reload();
    } catch (e) {
      setFailure(e as GymApiError);
    }
  }
  return (
    <Loading data={view.data} error={view.error}>
      {() => (
        <>
          {view.data.aliases.map((a: any) => (
            <section className="card" key={a.alias}>
              <div className="between">
                <div>
                  <strong>{a.alias}</strong> <small>contract {a.contract_id}</small>
                </div>
                <Env
                  ok={a.ok}
                  label={
                    a.ok
                      ? `Would bind now: ${short(a.would_bind)} · Qualified`
                      : `${a.code}: ${a.reason}`
                  }
                />
              </div>
              <div>
                Rule: <strong>{a.rule}</strong>{' '}
                {a.override && <Badge state="requested" label="override" />}
                {a.override && <small>template rule: {a.template_rule}</small>}
              </div>
              <small>The actual binding is made per run, at admission.</small>
              <details>
                <summary>Selection history ({a.history.length})</summary>
                <ul>
                  {a.history.map((h: any) => (
                    <li key={h.valid_from}>
                      <small>
                        {when(h.valid_from)} · {h.change_cause.replace(/_/g, ' ')} · {h.change_note}
                      </small>
                    </li>
                  ))}
                </ul>
              </details>
              {!a.ok && a.code === 'B2' && (
                <div className="banner">
                  No qualified version of {a.contract_id}.{' '}
                  {view.data.inbox_items.some((i: any) => i.kind === 'environment_defect')
                    ? 'Track the inbox item'
                    : 'Report an environment defect'}{' '}
                  on <Link href="/gym/admin/environments">Admin → Environments</Link>.
                </div>
              )}
            </section>
          ))}
          <section className="card">
            <h4>Evaluators · {view.data.criteria.length} criteria</h4>
            <small>
              Configurations are bound per run by rule, like environments (D20). Latest qualified: a
              new version starts a new leaderboard cohort. Pinned: its own leaderboard group.
            </small>
            <div className="table-wrap scroll" style={{ maxHeight: 300 }}>
              <table>
                <thead>
                  <tr>
                    <th>Criterion</th>
                    <th>Rule</th>
                    <th>Binds now</th>
                  </tr>
                </thead>
                <tbody>
                  {view.data.criteria.map((cr: any) => (
                    <tr key={cr.criterion_id}>
                      <td>
                        {cr.criterion_id}
                        <small>
                          <Link
                            href={`/gym/admin/evaluators/${cr.configuration_id}/${cr.binds_now ?? 1}`}
                          >
                            {cr.configuration_id}
                          </Link>
                        </small>
                      </td>
                      <td>{cr.rule}</td>
                      <td>
                        <Env
                          ok={cr.ok}
                          label={cr.ok ? `v${cr.binds_now} · Qualified` : cr.reason}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {view.data.evaluator_history.length > 0 && (
              <details>
                <summary>
                  Evaluator selection history ({view.data.evaluator_history.length})
                </summary>
                <ul>
                  {view.data.evaluator_history.map((h: any) => (
                    <li key={h.criterion_id + h.valid_from}>
                      <small>
                        {when(h.valid_from)} · {h.criterion_id} · {h.change_note}
                      </small>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </section>
          <section className="card">
            <h4>Overrides</h4>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Rule change</th>
                    <th>Reason</th>
                    <th>State</th>
                    <th>Decision</th>
                  </tr>
                </thead>
                <tbody>
                  {view.data.overrides.length === 0 && (
                    <tr>
                      <td colSpan={4} style={{ textAlign: 'left' }}>
                        No overrides.
                      </td>
                    </tr>
                  )}
                  {view.data.overrides.map((o: any) => (
                    <tr key={o.id}>
                      <td>
                        {o.from_label} → {o.to_label}
                        <small>
                          {o.alias} · {o.short_id} · requested by {o.requested_by_name} ·{' '}
                          {when(o.requested_at)}
                        </small>
                      </td>
                      <td>{o.reason}</td>
                      <td>
                        <Badge state={o.decision} />
                      </td>
                      <td>
                        {o.decision === 'requested' ? (
                          <Link href={`?review=${o.short_id}`}>Review</Link>
                        ) : o.decided_by_name ? (
                          <small>
                            {o.decision === 'approved'
                              ? 'Approved'
                              : o.decision === 'rejected'
                                ? 'Rejected'
                                : 'Decided'}{' '}
                            by {o.decided_by_name}
                            {o.decision_note ? ` · ${o.decision_note}` : ''}
                          </small>
                        ) : null}
                        {o.decision === 'approved' &&
                          view.data.aliases.some((a: any) => a.override_id === o.id) && (
                            <button
                              onClick={async () => {
                                try {
                                  await send(
                                    'POST',
                                    `${wsBase(ws)}/rule-overrides/${o.short_id}/remove`,
                                    {},
                                  );
                                  say(`Override ${o.short_id} removed; back to the template rule.`);
                                  reload();
                                } catch (e) {
                                  setFailure(e as GymApiError);
                                }
                              }}
                            >
                              Remove override
                            </button>
                          )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="card">
            <h4>Request a rule change</h4>
            <small>
              An override changes the rule of one alias for this project; a binding approver other
              than you decides.
            </small>
            <div className="grid3">
              <label>
                Alias
                <select value={alias} onChange={(e) => setAlias(e.target.value)}>
                  {view.data.aliases.map((a: any) => (
                    <option key={a.alias} value={a.alias}>
                      {a.alias}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                New rule
                <select
                  value={rule}
                  onChange={(e) => setRule(e.target.value)}
                  aria-label="New rule"
                >
                  <option value="">Choose…</option>
                  {(
                    view.data.aliases.find(
                      (a: any) => a.alias === (alias || view.data.aliases[0]?.alias),
                    )?.options ?? []
                  )
                    .filter((o: any) => !o.current)
                    .map((o: any) => (
                      <option key={ruleOptionValue(o)} value={ruleOptionValue(o)}>
                        {o.label} (selects {short(o.selects)}, {o.cases} cases)
                      </option>
                    ))}
                </select>
              </label>
              <label>
                Reason
                <input
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  aria-label="Reason"
                />
              </label>
            </div>
            <div className="row">
              <button className="primary" disabled={!rule || !reason.trim()} onClick={request}>
                Request override
              </button>
            </div>
            <Failure error={failure} />
          </section>
          {review && (
            <ReviewPanel
              override={view.data.overrides.find((o: any) => o.short_id === review)}
              me={view.data.me}
              close={() => router.replace(`/gym/projects/${project}/selection-rules`)}
              done={reload}
            />
          )}
        </>
      )}
    </Loading>
  );
}

function ReviewPanel({
  override,
  me,
  close,
  done,
}: {
  override: any;
  me: any;
  close: () => void;
  done: () => void;
}) {
  const { ws, say } = useGym();
  const [ack, setAck] = useState(false);
  const [note, setNote] = useState('');
  const [failure, setFailure] = useState<GymApiError | null>(null);
  if (!override) return null;
  const r = override.review;
  const mine = !r.different_person;
  const canDecide = override.decision === 'requested' && !mine && r.you_are_approver;
  async function decide(decision: 'approved' | 'rejected') {
    setFailure(null);
    try {
      await send('POST', `${wsBase(ws)}/rule-overrides/${override.short_id}/decision`, {
        decision,
        note,
        new_cohort_acknowledged: ack,
      });
      say(`Override ${override.short_id} ${decision}.`);
      done();
      close();
    } catch (e) {
      setFailure(e as GymApiError);
    }
  }
  return (
    <>
      <div className="backdrop" onClick={close} />
      <section className="drawer" role="dialog" aria-label={`Review override ${override.short_id}`}>
        <div className="between">
          <h3>Review override {override.short_id}</h3>
          <Badge state={override.decision} />
        </div>
        <dl className="kv">
          <dt>Alias</dt>
          <dd>{override.alias}</dd>
          <dt>Rule now</dt>
          <dd>
            {override.from_label} → selects {short(override.from_version_id)}
          </dd>
          <dt>Requested rule</dt>
          <dd>
            {override.to_label} → selects {short(r.selects_now)}
          </dd>
          <dt>Reason</dt>
          <dd>{override.reason}</dd>
          <dt>Requested by</dt>
          <dd>
            {override.requested_by_name} · {when(override.requested_at)}
          </dd>
        </dl>
        <div className="check">
          <i className={r.different_person ? 'ok' : 'no'}>{r.different_person ? '✓' : '✕'}</i>
          <span>
            Different person
            <small>
              Requested by {override.requested_by_name}; you are {me.name}
              {mine ? ' (the requester cannot decide)' : ''}
            </small>
          </span>
        </div>
        <div className="check">
          <i className={r.you_are_approver ? 'ok' : 'no'}>{r.you_are_approver ? '✓' : '✕'}</i>
          <span>
            Binding approver
            <small>
              {r.you_are_approver
                ? 'You may approve rule overrides'
                : 'You are not a binding approver'}
            </small>
          </span>
        </div>
        <div className="check">
          <i className={r.version_safe ? 'ok' : 'no'}>{r.version_safe ? '✓' : '✕'}</i>
          <span>
            Version is safe to use
            <small>Qualified, same contract, not deprecated (checked by the RL Gym)</small>
          </span>
        </div>
        <div className="check">
          <i className={r.data_change ? 'no' : 'ok'}>{r.data_change ? '!' : '✓'}</i>
          <span>
            Data change
            <small>
              {r.data_change
                ? 'The seed family changes: results are not comparable with earlier runs; the leaderboard starts a new cohort.'
                : 'Same seed family'}
            </small>
          </span>
        </div>
        <div className="check">
          <i>·</i>
          <span>
            Impact
            <small>
              {r.tasks_affected} tasks · {r.impact}
            </small>
          </span>
        </div>
        <div className="check">
          <i>·</i>
          <span>
            Lasts
            <small>Until removed; Remove override returns the alias to the template's rule.</small>
          </span>
        </div>
        {r.data_change && (
          <label className="row">
            <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /> I
            understand results will start a new cohort
          </label>
        )}
        <label>
          Decision note (required to reject)
          <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3} />
        </label>
        <div className="row">
          <button
            className="primary"
            disabled={!canDecide || (r.data_change && !ack)}
            onClick={() => decide('approved')}
          >
            Approve
          </button>
          <button disabled={!canDecide || !note.trim()} onClick={() => decide('rejected')}>
            Reject
          </button>
          <button onClick={close}>Close</button>
        </div>
        <Failure error={failure} />
      </section>
    </>
  );
}

// A task package's actor or private part, whatever its shape (the ADI Forge stub's fields, or Authoring's
// praxis.authored-task-package.v1 profile, title, sections and workflow): known fields get their label, every other
// field is shown by name; nested values are shown as formatted JSON.
const ACTOR_LABELS: Record<string, string> = {
  assignment: 'Assignment',
  inputs: 'Inputs',
  tools: 'Tools',
  output_contract: 'Output',
};
const PRIVATE_LABELS: Record<string, string> = {
  rubric: 'Rubric',
  criteria: 'Criteria',
  points_each: 'Points each',
  pass_mark: 'Pass mark',
  expected: 'Expected',
};

function PartView({ value, labels }: { value: any; labels: Record<string, string> }) {
  if (!value || typeof value !== 'object') return <small>Not in this package.</small>;
  const keys = [
    ...Object.keys(labels).filter((k) => k in value),
    ...Object.keys(value).filter((k) => !(k in labels)),
  ];
  return (
    <dl className="kv">
      {keys.map((k) => {
        const v = value[k];
        const text =
          v === null || v === undefined
            ? '—'
            : typeof v !== 'object'
              ? String(v)
              : Array.isArray(v) && v.every((x) => typeof x !== 'object')
                ? v.join(', ')
                : null;
        return (
          <Fragment key={k}>
            <dt>{labels[k] ?? k.replace(/_/g, ' ')}</dt>
            <dd>{text ?? <pre className="part-json">{JSON.stringify(v, null, 2)}</pre>}</dd>
          </Fragment>
        );
      })}
    </dl>
  );
}
