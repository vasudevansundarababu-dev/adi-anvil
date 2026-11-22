'use client';

import Link from 'next/link';
import { EdgeCaseForm, edgeBody, edgeReady, emptyEdge, type EdgeParts } from './EdgeCase';
import { useState } from 'react';
import LiveApprovals from './Live';
import PluginsPanel from './Plugins';
import { GymApiError, send, short, when, wsBase } from './api';
import { Keys, Models } from './Models';
import { labelOf } from './RLGym';
import { Badge, Env, Failure, Hash, Loading, Search, Tabs, useData, useGym } from './ui';

export default function Admin({ parts }: { parts: string[] }) {
  const section = parts[0] ?? 'models';
  const tabs = [
    ['models', 'Models'],
    ['keys', 'Keys'],
    ['live', 'Live approvals'],
    ['environments', 'Environments'],
    ['evaluators', 'Evaluators'],
    ['templates', 'Templates'],
    ['users', 'Users'],
  ].map(([key, label]) => ({ key, label, href: `/gym/admin/${key}` }));
  let body: React.ReactNode;
  if (section === 'environments' && parts[1]) body = <EnvironmentPage vid={parts[1]} />;
  else if (section === 'environments') body = <Environments />;
  else if (section === 'evaluators' && parts[1])
    body = <EvaluatorPage cid={parts[1]} version={parts[2] ?? '1'} />;
  else if (section === 'evaluators') body = <Evaluators />;
  else if (section === 'templates' && parts[1])
    body = <TemplatePage tid={parts[1]} version={parts[2] ?? '1'} />;
  else if (section === 'templates') body = <Templates />;
  else if (section === 'users') body = <Users />;
  else if (section === 'keys') body = <Keys />;
  else if (section === 'live') body = <LiveApprovals />;
  else body = <Models parts={parts.slice(1)} />;
  return (
    <main className="page">
      <h2>Admin</h2>
      <Tabs items={tabs} current={section} />
      {body}
    </main>
  );
}

function Environments() {
  const { ws } = useGym();
  const [q, setQ] = useState('');
  const [state, setState] = useState('');
  const params = new URLSearchParams({ ...(q ? { q } : {}), ...(state ? { state } : {}) });
  const { data, error } = useData<any>(`${wsBase(ws)}/catalog/environments?${params}`);
  return (
    <>
      <div className="toolbar">
        <Search value={q} onChange={setQ} placeholder="Search environments" />
        <label>
          <small>State</small>
          <select value={state} onChange={(e) => setState(e.target.value)} aria-label="State">
            <option value="">All</option>
            <option value="qualified">Qualified</option>
            <option value="failed">Failed</option>
            <option value="revoked">Revoked</option>
          </select>
        </label>
        <small>
          Read-only view of Studio&apos;s registry (local stub). No register, revoke or delete here.
        </small>
      </div>
      <Loading data={data} error={error}>
        {() => (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Environment</th>
                  <th>Version</th>
                  <th>Seed family</th>
                  <th>State</th>
                  <th>Selected by</th>
                  <th>Instances · 30-day cost</th>
                </tr>
              </thead>
              <tbody>
                {data.items.length === 0 && (
                  <tr>
                    <td colSpan={6} style={{ textAlign: 'left' }}>
                      No environment versions mirrored yet.
                    </td>
                  </tr>
                )}
                {data.items.map((v: any) => (
                  <tr key={v.id}>
                    <td>
                      <Link className="link" href={`/gym/admin/environments/${v.id}`}>
                        {v.contract_id}
                      </Link>
                      <small>
                        Studio release {v.release_id} · {when(v.released_at)}
                      </small>
                    </td>
                    <td>v{v.version}</td>
                    <td>
                      <code>{v.seed_family}</code>
                      <small>{v.case_catalog?.cases} cases</small>
                    </td>
                    <td>
                      <Badge
                        state={
                          v.selectable
                            ? v.state
                            : v.qualification?.result === 'failed'
                              ? 'failed'
                              : v.state
                        }
                      />
                      {!v.selectable && v.qualification?.result === 'failed' && (
                        <small>Failed re-qualification · not selected</small>
                      )}
                    </td>
                    <td>
                      {v.selected_by.length
                        ? v.selected_by.map((p: any) => (
                            <small key={p.project_id}>
                              {p.name} ({p.kind.replace('_', ' ')},{' '}
                              {p.change_cause.replace(/_/g, ' ')})
                            </small>
                          ))
                        : '—'}
                    </td>
                    <td>
                      <small>{v.instances.note}</small>
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

function EnvironmentPage({ vid }: { vid: string }) {
  const { ws, say, refreshTodo } = useGym();
  const { data, error, reload } = useData<any>(
    `${wsBase(ws)}/catalog/environments/${encodeURIComponent(vid)}`,
  );
  const [summary, setSummary] = useState('');
  const [neededBy, setNeededBy] = useState('');
  const [failure, setFailure] = useState<GymApiError | null>(null);
  const projects = useData<any>(`${wsBase(ws)}/projects`);
  async function report() {
    setFailure(null);
    try {
      const project =
        projects.data?.items?.find((p: any) =>
          p.environments.some((e: any) => e.version_id === vid),
        ) ?? projects.data?.items?.[0];
      const item = await send('POST', `${wsBase(ws)}/inbox-items`, {
        kind: 'environment_defect',
        template_id: project?.template_id,
        version: project?.template_version,
        environment_version: vid,
        project_id: project?.project_id,
        summary,
        needed_by: neededBy || undefined,
      });
      say(`Environment defect ${item.id} queued for Studio's next-version inbox.`);
      setSummary('');
      reload();
      refreshTodo();
    } catch (e) {
      setFailure(e as GymApiError);
    }
  }
  async function requalify() {
    try {
      await send(
        'POST',
        `${wsBase(ws)}/catalog/environments/${encodeURIComponent(vid)}/requalify`,
        {},
      );
      reload();
    } catch (e) {
      setFailure(e as GymApiError);
    }
  }
  return (
    <Loading data={data} error={error}>
      {() => {
        const cat = data.case_catalog ?? {};
        const types = cat.dimensions?.application_type ?? {};
        const completeness = Object.keys(cat.dimensions?.completeness ?? {});
        const q = data.qualification;
        const failed = (q?.checks ?? []).filter((c: any) => c.result === 'fail');
        const open = data.inbox_items.find((i: any) => !['closed', 'declined'].includes(i.state));
        return (
          <div className="work">
            <aside>
              <Link href="/gym/admin/environments">← Back to environments</Link>
              <h4>Qualification</h4>
              {q ? (
                <>
                  {q.checks.map((c: any) => (
                    <div className="check" key={c.name}>
                      <i className={c.result === 'pass' ? 'ok' : 'no'}>
                        {c.result === 'pass' ? '✓' : '✕'}
                      </i>
                      <span>
                        {c.name}
                        <small>{JSON.stringify(c.evidence)}</small>
                        {c.likely_cause && (
                          <small>Likely cause (suggestion): {c.likely_cause}</small>
                        )}
                      </span>
                    </div>
                  ))}
                  <small>
                    Receipt {q.receipt_id} · {when(q.issued_at)} · {q.result}
                    {q.failure_class ? ` · ${q.failure_class.replace('_', ' ')}` : ''} · mode{' '}
                    {q.mode.replace(/_/g, ' ')}
                  </small>
                  {data.can_requalify && <button onClick={requalify}>Re-qualify</button>}
                </>
              ) : (
                <small>Not qualified by the RL Gym yet.</small>
              )}
            </aside>
            <main>
              <div className="row">
                <h3>
                  {data.contract_id} · v{data.version}
                </h3>
                <Badge
                  state={
                    data.selectable ? data.state : q?.result === 'failed' ? 'failed' : data.state
                  }
                />
                <small>From Studio&apos;s registry</small>
              </div>
              <dl className="kv">
                <dt>Image</dt>
                <dd>
                  <Hash value={data.image_digest} />
                </dd>
                <dt>Seed snapshot</dt>
                <dd>
                  <Hash value={data.seed_sha256} /> <code>{data.seed_ref}</code>
                </dd>
                <dt>Seed family</dt>
                <dd>
                  <code>{data.seed_family}</code>
                </dd>
                <dt>Runtime profile</dt>
                <dd>{data.runtime_profile}</dd>
                <dt>Operations</dt>
                <dd>
                  {data.tools} declared (
                  {(data.operations ?? [])
                    .slice(0, 5)
                    .map((o: string | { operation_id: string }) =>
                      typeof o === 'string' ? o : o.operation_id,
                    )
                    .join(', ')}
                  , …)
                </dd>
                <dt>Schema</dt>
                <dd>
                  {(data.schema_tables ?? [])
                    .map((t: any) => (typeof t === 'string' ? t : `${t.name} (private)`))
                    .join(', ')}
                </dd>
                <dt>Reset strategy</dt>
                <dd>{data.reset_strategy}</dd>
                <dt>Selected by</dt>
                <dd>{data.selected_by.map((p: any) => p.name).join(', ') || '—'}</dd>
                <dt>Used by</dt>
                <dd>
                  {data.used_by.templates.map((t: any) => `${t.name}`).join(', ') || '—'} ·{' '}
                  {data.used_by.tasks_bound} tasks bound · {data.used_by.runs} runs
                </dd>
              </dl>
              <section className="card">
                <h4>Data · case catalog</h4>
                <small>
                  Dataset {cat.dataset} · generator {cat.generator} · seed {cat.seed}. Counts only:
                  private reference answers are never shown. Information only; asking for data
                  belongs to a suite&apos;s data plan (2.6).
                </small>
                <div className="grid4">
                  <div className="stat">
                    <small>Cases</small>
                    <strong>{cat.cases}</strong>
                  </div>
                  <div className="stat">
                    <small>Application types</small>
                    <strong>{Object.keys(types).length}</strong>
                  </div>
                  <div className="stat">
                    <small>Edge cases</small>
                    <strong>
                      {
                        Object.values(cat.dimensions?.edge_cases ?? {}).reduce(
                          (a: number, b: any) => a + b,
                          0,
                        ) as number
                      }
                    </strong>
                  </div>
                  <div className="stat">
                    <small>Open more-data items</small>
                    <strong>
                      {
                        data.more_data_items.filter(
                          (i: any) => !['closed', 'declined', 'released'].includes(i.state),
                        ).length
                      }
                    </strong>
                  </div>
                </div>
                {Object.values(types).some(
                  (n: any) => n < (cat.minimum_per_application_type ?? 0),
                ) && (
                  <small className="wait">
                    This version predates Golden KYC&apos;s coverage minimum of{' '}
                    {cat.minimum_per_application_type} per product.
                  </small>
                )}
                <div
                  className="grid-cells"
                  style={{ gridTemplateColumns: `140px repeat(${completeness.length + 1}, 1fr)` }}
                >
                  <span />
                  <strong>Total</strong>
                  {completeness.map((c) => (
                    <strong key={c}>{c}</strong>
                  ))}
                  {Object.entries(types).map(([t, n]: any) => (
                    <span key={t} style={{ display: 'contents' }}>
                      <span>{t}</span>
                      <span className="cell">{n}</span>
                      {completeness.map((c) => {
                        const v = cat.cells?.[`${t}|${c}`] ?? 0;
                        return (
                          <span key={c} className={`cell ${v < 3 ? 'low' : ''}`}>
                            {v}
                          </span>
                        );
                      })}
                    </span>
                  ))}
                </div>
                <table>
                  <thead>
                    <tr>
                      <th>Edge case</th>
                      <th>Rule it tests</th>
                      <th>Count</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(cat.dimensions?.edge_cases ?? {}).map(([tag, n]: any) => (
                      <tr key={tag}>
                        <td>
                          <code>{tag}</code>
                        </td>
                        <td>{cat.edge_case_rules?.[tag]}</td>
                        <td className={n >= 3 ? 'ok' : 'no'}>{n}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
              <section className="card">
                <h4>Studio inbox · environment defect</h4>
                <small>
                  A released version never changes; the fix is a new version from Studio. The RL Gym
                  sends an inbox item and tracks it.
                </small>
                {data.inbox_items.map((i: any) => (
                  <div key={i.id} className="card">
                    <div className="between">
                      <strong>
                        {i.studio_id ?? i.id} · {i.kind.replace('_', ' ')}
                      </strong>
                      {i.urgent && <Badge state="failed" label="Urgent" />}
                    </div>
                    <small>{i.summary}</small>
                    <div className="timeline">
                      {i.timeline.map((t: any, n: number) => (
                        <span key={n} className="on">
                          {t.state}
                          {t.planned_version ? ` ${t.planned_version}` : ''}
                          {t.released_version ? ` ${t.released_version}` : ''} · {when(t.at)}
                        </span>
                      ))}
                    </div>
                    {i.decline_reason && <small>Declined: {i.decline_reason}</small>}
                  </div>
                ))}
                {!open && (
                  <>
                    {failed.length > 0 && (
                      <dl className="kv">
                        <dt>What needs fixing</dt>
                        <dd>
                          {failed
                            .map((c: any) => `${c.name}: ${JSON.stringify(c.evidence)}`)
                            .join('; ')}
                          {failed[0]?.likely_cause ? (
                            <small>Likely cause (suggestion): {failed[0].likely_cause}</small>
                          ) : null}
                        </dd>
                      </dl>
                    )}
                    <label>
                      Summary and note to Studio
                      <textarea
                        value={summary}
                        onChange={(e) => setSummary(e.target.value)}
                        rows={3}
                      />
                    </label>
                    <label>
                      Needed by
                      <select value={neededBy} onChange={(e) => setNeededBy(e.target.value)}>
                        <option value="">No date</option>
                        <option value="2026-11-28">This week</option>
                        <option value="2026-12-01">Before 1 Dec 2026</option>
                      </select>
                    </label>
                    <button className="primary" disabled={!summary.trim()} onClick={report}>
                      Report to Studio inbox (environment defect)
                    </button>
                  </>
                )}
                <Failure error={failure} />
              </section>
            </main>
          </div>
        );
      }}
    </Loading>
  );
}

function knownCases(row: any) {
  const checks = row.known_case_checks;
  if (!checks) return 'Not run';
  return checks
    .map((c: any) => `${c.name.replace('_', ' ')} ${c.result === 'pass' ? '✓' : '✕'}`)
    .join(' · ');
}

function Evaluators() {
  const { ws, say } = useGym();
  const [q, setQ] = useState('');
  const [state, setState] = useState('');
  const params = new URLSearchParams({ ...(q ? { q } : {}), ...(state ? { state } : {}) });
  const configs = useData<any>(`${wsBase(ws)}/catalog/evaluators?${params}`);
  const frameworks = useData<any>(`${wsBase(ws)}/catalog/frameworks`);
  const [dialog, setDialog] = useState<{ fid: string; action: 'deprecate' | 'revoke' } | null>(
    null,
  );
  return (
    <>
      <PluginsPanel />
      <small>
        The RL Gym owns framework versions and evaluator configurations (option B). First versions
        arrive from Studio&apos;s S7 bindings through A-06; fix versions are made on a configuration
        page. Configurations bind per run by rule (D20).
      </small>
      <h3>Framework versions</h3>
      <Loading data={frameworks.data} error={frameworks.error}>
        {() => (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Framework</th>
                  <th>Version</th>
                  <th>State</th>
                  <th>Reads evidence</th>
                  <th>Configurations</th>
                  <th>Image</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {frameworks.data.items.map((f: any) => (
                  <tr key={f.id}>
                    <td>
                      {f.runtime_id === 'python' ? 'Sandboxed Python' : f.runtime_id.toUpperCase()}
                      <small>{f.install_note}</small>
                    </td>
                    <td>{f.version}</td>
                    <td>
                      <Badge state={f.state} />
                      {!f.installed_locally && <small>not installed locally</small>}
                    </td>
                    <td>{f.evidence_types.join(', ')}</td>
                    <td>{f.configurations}</td>
                    <td>
                      <Hash value={f.image_digest} />
                    </td>
                    <td>
                      {['qualified', 'registered'].includes(f.state) && (
                        <button onClick={() => setDialog({ fid: f.id, action: 'deprecate' })}>
                          Deprecate
                        </button>
                      )}
                      {f.state === 'deprecated' && (
                        <button onClick={() => setDialog({ fid: f.id, action: 'revoke' })}>
                          Revoke…
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Loading>
      <div className="toolbar">
        <h3>Evaluator configurations</h3>
        <Search value={q} onChange={setQ} placeholder="Search configurations" />
        <label>
          <small>State</small>
          <select
            value={state}
            onChange={(e) => setState(e.target.value)}
            aria-label="Configuration state"
          >
            <option value="">All</option>
            {['qualified', 'registered', 'failed', 'deprecated', 'revoked'].map((s) => (
              <option key={s} value={s}>
                {s[0].toUpperCase() + s.slice(1)}
              </option>
            ))}
          </select>
        </label>
      </div>
      <Loading data={configs.data} error={configs.error}>
        {() => (
          <div className="table-wrap scroll">
            <table>
              <thead>
                <tr>
                  <th>Configuration</th>
                  <th>Framework</th>
                  <th>Evidence</th>
                  <th>State</th>
                  <th>Known-case tests</th>
                  <th>Required for release</th>
                  <th>Used by</th>
                </tr>
              </thead>
              <tbody>
                {configs.data.items.length === 0 && (
                  <tr>
                    <td colSpan={7} style={{ textAlign: 'left' }}>
                      No configurations in this state.
                    </td>
                  </tr>
                )}
                {configs.data.items.map((e: any) => (
                  <tr key={`${e.id}@${e.version}`}>
                    <td>
                      <Link className="link" href={`/gym/admin/evaluators/${e.id}/${e.version}`}>
                        {e.id} · v{e.version}
                      </Link>
                      <small>criterion {e.criterion_id}</small>
                    </td>
                    <td>
                      {e.runtime_id} {e.framework_version}
                    </td>
                    <td>
                      <code>{e.evidence_type}</code>
                    </td>
                    <td>
                      <Badge state={e.state} />
                    </td>
                    <td>
                      <small>{knownCases(e)}</small>
                    </td>
                    <td>Golden KYC V{e.source_template_version}</td>
                    <td>
                      {e.used_by.map((p: any) => p.name).join(', ') ||
                        (e.replaced_by_version ? `replaced by v${e.replaced_by_version}` : '—')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Loading>
      {dialog && (
        <ImpactDialog
          subject={dialog.fid}
          impactPath={`${wsBase(ws)}/frameworks/${dialog.fid}/impact`}
          action={dialog.action}
          close={() => setDialog(null)}
          submit={async (reason) => {
            await send('POST', `${wsBase(ws)}/frameworks/${dialog.fid}/${dialog.action}`, {
              reason,
            });
            say(
              `Framework ${dialog.fid} ${dialog.action === 'revoke' ? 'revoked' : 'deprecated'}; Studio is told by event.`,
            );
            frameworks.reload();
            configs.reload();
          }}
        />
      )}
    </>
  );
}

function ImpactDialog({
  subject,
  impactPath,
  action,
  close,
  submit,
}: {
  subject: string;
  impactPath: string;
  action: 'deprecate' | 'revoke';
  close: () => void;
  submit: (reason: string) => Promise<void>;
}) {
  const impact = useData<any>(impactPath);
  const [reason, setReason] = useState('');
  const [failure, setFailure] = useState<GymApiError | null>(null);
  return (
    <>
      <div className="backdrop" onClick={close} />
      <section
        className="drawer"
        role="dialog"
        aria-label={`${action === 'revoke' ? 'Revoke' : 'Deprecate'} ${subject}`}
      >
        <h3>
          {action === 'revoke' ? 'Revoke' : 'Deprecate'} {impact.data?.subject ?? subject}
        </h3>
        <Loading data={impact.data} error={impact.error}>
          {() => (
            <dl className="kv">
              {'replacement' in impact.data && (
                <>
                  <dt>Replacement</dt>
                  <dd>
                    {impact.data.replacement ? (
                      <Env
                        ok
                        label={`v${impact.data.replacement.version} · qualified · known-case tests passed`}
                      />
                    ) : (
                      <Env
                        ok={false}
                        label="None: admission will refuse runs that need this criterion (B4)"
                      />
                    )}
                  </dd>
                </>
              )}
              <dt>Templates</dt>
              <dd>
                {(impact.data.templates ?? [])
                  .map((t: any) => (typeof t === 'string' ? t : `${t.name}`))
                  .join(', ') || '—'}
              </dd>
              {impact.data.projects && (
                <>
                  <dt>Projects</dt>
                  <dd>{impact.data.projects.map((p: any) => p.name).join(', ') || '—'}</dd>
                </>
              )}
              {impact.data.configurations && (
                <>
                  <dt>Configurations on it</dt>
                  <dd>
                    {impact.data.configurations
                      .map((c: any) => `${c.id} v${c.version}`)
                      .join(', ') || 'None'}
                  </dd>
                </>
              )}
              {impact.data.runs && (
                <>
                  <dt>Runs</dt>
                  <dd>
                    {impact.data.runs.completed_flagged} completed flagged ·{' '}
                    {impact.data.runs.running} running
                    <small>{impact.data.runs.note}</small>
                  </dd>
                </>
              )}
            </dl>
          )}
        </Loading>
        <label>
          Reason (required)
          <textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={3}
            aria-label="Reason"
          />
        </label>
        <div className="row">
          <button
            className="primary"
            disabled={!reason.trim()}
            onClick={async () => {
              setFailure(null);
              try {
                await submit(reason);
                close();
              } catch (e) {
                setFailure(e as GymApiError);
              }
            }}
          >
            {action === 'revoke' ? 'Revoke' : 'Deprecate'}
          </button>
          <button onClick={close}>Cancel</button>
        </div>
        <Failure error={failure} />
      </section>
    </>
  );
}

function EvaluatorPage({ cid, version }: { cid: string; version: string }) {
  const { ws, say, refreshTodo } = useGym();
  const path = `${wsBase(ws)}/catalog/evaluators/${encodeURIComponent(cid)}/versions/${version}`;
  const { data, error, reload } = useData<any>(path);
  const [dialog, setDialog] = useState<'revoke' | 'deprecate' | null>(null);
  const [fixOpen, setFixOpen] = useState(false);
  const [config, setConfig] = useState('');
  const [fixReason, setFixReason] = useState('');
  const [failure, setFailure] = useState<GymApiError | null>(null);
  const after = () => {
    reload();
    refreshTodo();
  };
  async function test() {
    setFailure(null);
    try {
      const r = await send('POST', `${wsBase(ws)}/evaluators/${encodeURIComponent(cid)}/test`, {
        version: Number(version),
      });
      say(`Known-case tests: ${r.result} (receipt ${r.receipt_id}).`);
      after();
    } catch (e) {
      setFailure(e as GymApiError);
    }
  }
  async function fix() {
    setFailure(null);
    try {
      const r = await send('POST', `${wsBase(ws)}/evaluators/${encodeURIComponent(cid)}/versions`, {
        fix_of: Number(version),
        config: config.trim() ? JSON.parse(config) : undefined,
        reason: fixReason,
      });
      say(
        `Fix version v${r.configuration.version} created; known-case tests ${r.known_case_test.result}.`,
      );
      window.location.href = `/gym/admin/evaluators/${cid}/${r.configuration.version}`;
    } catch (e) {
      setFailure(
        e instanceof SyntaxError
          ? ({ error: { message: 'Configuration must be JSON', code: 'VALIDATION_FAILED' } } as any)
          : (e as GymApiError),
      );
    }
  }
  return (
    <Loading data={data} error={error}>
      {() => {
        const receipt = data.receipts[0];
        return (
          <div className="work">
            <aside>
              <Link href="/gym/admin/evaluators">← Back to evaluators</Link>
              <h4>Known-case tests</h4>
              {receipt ? (
                <>
                  {receipt.checks.map((c: any) => (
                    <div className="check" key={c.name}>
                      <i className={c.result === 'pass' ? 'ok' : 'no'}>
                        {c.result === 'pass' ? '✓' : '✕'}
                      </i>
                      <span>
                        {c.name.replace('_', ' ')} → {c.expected}
                        <small>
                          {c.case_id} · verdict {c.verdict}
                        </small>
                        {(c.detail ?? []).map((d: string) => (
                          <small key={d}>{d}</small>
                        ))}
                      </span>
                    </div>
                  ))}
                  <small>
                    Receipt {receipt.receipt_id} · {when(receipt.issued_at)} · {receipt.result} ·{' '}
                    {receipt.mode.replace(/_/g, ' ')}
                  </small>
                </>
              ) : (
                <small>Not run</small>
              )}
              <small>All three must pass (and be distinct) before release.</small>
            </aside>
            <main>
              <div className="row">
                <h3>
                  {data.id} · v{data.version}
                </h3>
                <Badge state={data.state} />
              </div>
              {data.state_reason && <small>Reason: {data.state_reason}</small>}
              <dl className="kv">
                <dt>Criterion</dt>
                <dd>
                  {data.criterion_id} · weight {data.weight}
                </dd>
                <dt>Framework</dt>
                <dd>
                  {data.framework.runtime_id} {data.framework.version} ·{' '}
                  <Hash value={data.framework.image_digest} />
                </dd>
                <dt>Reads</dt>
                <dd>
                  <code>{data.evidence_type}</code>
                </dd>
                <dt>Verdicts</dt>
                <dd>{data.verdict_vocabulary.join(', ')}</dd>
                <dt>Configuration hash</dt>
                <dd>
                  <Hash value={data.config_sha256} />
                </dd>
                <dt>Configuration</dt>
                <dd>
                  <pre>{JSON.stringify(data.config, null, 1)}</pre>
                </dd>
                <dt>Created from</dt>
                <dd>
                  {data.created_by === 'studio'
                    ? `Studio S7 binding · ${data.source_template_key} V${data.source_template_version} · via A-06 · ${when(data.created_at)}`
                    : `Fix version created by the RL Gym · fix of v${data.fix_of_version} · ${data.fix_reason}`}
                </dd>
                <dt>Used by</dt>
                <dd>
                  {data.used_by
                    .map(
                      (u: any) =>
                        `${u.name} (${u.kind.replace('_', ' ')}, binds v${u.resolved_version ?? '—'})`,
                    )
                    .join(', ') || '—'}
                  <small>Runs arrive with work package 2.7.</small>
                </dd>
              </dl>
              <section className="card">
                <h4>Version history</h4>
                {data.history.map((h: any) => (
                  <div key={h.version} className="between">
                    <Link href={`/gym/admin/evaluators/${cid}/${h.version}`}>v{h.version}</Link>
                    <Badge state={h.state} />
                    <small>
                      {h.created_by === 'rlgym'
                        ? `fix of v${h.fix_of_version}: ${h.fix_reason}`
                        : 'from Studio S7'}
                      {h.replaced_by_version ? ` · replaced by v${h.replaced_by_version}` : ''}
                      {h.state_reason ? ` · ${h.state_reason}` : ''}
                    </small>
                  </div>
                ))}
              </section>
              <div className="row">
                {data.state !== 'revoked' && <button onClick={test}>Run known-case tests</button>}
                {data.state !== 'revoked' && (
                  <button onClick={() => setFixOpen(!fixOpen)}>New version… (fix)</button>
                )}
                {data.state === 'qualified' && (
                  <button onClick={() => setDialog('deprecate')}>Deprecate</button>
                )}
                {data.state !== 'revoked' && (
                  <button onClick={() => setDialog('revoke')}>Revoke…</button>
                )}
              </div>
              {fixOpen && (
                <section className="card">
                  <h4>New version (fix) · same evaluator contract</h4>
                  <small>
                    A fix keeps the criterion, evidence type and verdicts. It is qualified by its
                    known-case tests and starts a new leaderboard cohort for Latest-qualified rules.
                    No Studio inbox item unless the S7 criterion itself must change.
                  </small>
                  <label>
                    Changed configuration (JSON; leave empty to keep it)
                    <textarea
                      value={config}
                      onChange={(e) => setConfig(e.target.value)}
                      rows={5}
                      placeholder={JSON.stringify(data.config)}
                    />
                  </label>
                  <label>
                    Reason (required)
                    <input
                      value={fixReason}
                      onChange={(e) => setFixReason(e.target.value)}
                      aria-label="Fix reason"
                    />
                  </label>
                  <button className="primary" disabled={!fixReason.trim()} onClick={fix}>
                    Create fix version
                  </button>
                </section>
              )}
              <Failure error={failure} />
            </main>
            {dialog && (
              <ImpactDialog
                subject={`${data.id} v${data.version}`}
                impactPath={`${wsBase(ws)}/evaluators/${encodeURIComponent(cid)}/impact?version=${version}`}
                action={dialog}
                close={() => setDialog(null)}
                submit={async (reason) => {
                  await send(
                    'POST',
                    `${wsBase(ws)}/evaluators/${encodeURIComponent(cid)}/${dialog}`,
                    { version: Number(version), reason },
                  );
                  say(
                    `${data.id} v${data.version} ${dialog === 'revoke' ? 'revoked' : 'deprecated'}; Studio is told by event.`,
                  );
                  after();
                }}
              />
            )}
          </div>
        );
      }}
    </Loading>
  );
}

function Templates() {
  const { ws } = useGym();
  const [q, setQ] = useState('');
  const [state, setState] = useState('');
  const params = new URLSearchParams({ ...(q ? { q } : {}), ...(state ? { state } : {}) });
  const { data, error } = useData<any>(`${wsBase(ws)}/templates?${params}`);
  return (
    <>
      <div className="toolbar">
        <Search value={q} onChange={setQ} placeholder="Search templates" />
        <label>
          <small>State</small>
          <select
            value={state}
            onChange={(e) => setState(e.target.value)}
            aria-label="Template state"
          >
            <option value="">All</option>
            <option value="active">Active</option>
            <option value="blocked">Blocked</option>
            <option value="revoked">Revoked</option>
          </select>
        </label>
        <small>Read-only: templates change only in Studio.</small>
      </div>
      <Loading data={data} error={error}>
        {() => (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Template</th>
                  <th>Version</th>
                  <th>Environments</th>
                  <th>Used by</th>
                  <th>Fingerprints</th>
                </tr>
              </thead>
              <tbody>
                {data.items.length === 0 && (
                  <tr>
                    <td colSpan={5} style={{ textAlign: 'left' }}>
                      No templates in this state.
                    </td>
                  </tr>
                )}
                {data.items.map((t: any) => (
                  <tr key={`${t.template_id}@${t.version}`}>
                    <td>
                      <Link
                        className="link"
                        href={`/gym/admin/templates/${t.template_id}/${t.version}`}
                      >
                        {t.name}
                      </Link>
                      <small>
                        {t.template_key} · Template ID {t.template_id} ·{' '}
                        {t.mode === 'single_agent' ? 'Single agent' : 'Multi agent'} ·{' '}
                        {t.criteria_count} criteria
                      </small>
                    </td>
                    <td>
                      V{t.version} <Badge state={t.state} />
                    </td>
                    <td>
                      {t.environments.map((e: any) => (
                        <Env
                          key={e.alias}
                          ok={e.ok}
                          label={`${e.alias} · ${e.rule} → ${short(e.binds_now)}`}
                        />
                      ))}
                    </td>
                    <td>
                      {t.used_by.map((p: any) => `${p.name} (${p.project_id})`).join(', ') || '—'}
                    </td>
                    <td>
                      <small>
                        Studio <Hash value={t.spec_sha256} />
                      </small>
                      <small>
                        Template <Hash value={t.template_sha256} />
                      </small>
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

function TemplatePage({ tid, version }: { tid: string; version: string }) {
  const { ws, say } = useGym();
  const { data, error, reload } = useData<any>(
    `${wsBase(ws)}/templates/${tid}/versions/${version}`,
  );
  const [summary, setSummary] = useState('');
  const [evidence, setEvidence] = useState('');
  const [edge, setEdge] = useState<EdgeParts>(emptyEdge);
  const [failure, setFailure] = useState<GymApiError | null>(null);
  return (
    <Loading data={data} error={error}>
      {() => (
        <div className="work">
          <aside>
            <Link href="/gym/admin/templates">← Back to templates</Link>
            <h4>Activation</h4>
            <dl className="kv">
              <dt>Template ID</dt>
              <dd>
                <code>{data.template_id}</code>
              </dd>
              <dt>Authoring</dt>
              <dd>
                {data.forge_template_id} v{data.forge_version}
              </dd>
              <dt>Studio fingerprint</dt>
              <dd>
                <Hash value={data.spec_sha256} />
              </dd>
              <dt>Studio release</dt>
              <dd>{data.studio_release}</dd>
            </dl>
            {[
              ['fingerprints_match', 'Fingerprints match'],
              ['environments_can_bind', 'Every environment can bind'],
              ['criteria_can_bind', 'Every criterion can bind'],
              [
                'known_case_tests_passed',
                `Known-case tests passed (${data.checks.known_case_tests})`,
              ],
            ].map(([k, label]) => (
              <div className="check" key={k}>
                <i className={data.checks[k] ? 'ok' : 'no'}>{data.checks[k] ? '✓' : '✕'}</i>
                <span>{label}</span>
              </div>
            ))}
          </aside>
          <main>
            <div className="row">
              <h3>
                {data.name} · {data.template_key}
              </h3>
              <Badge state={data.state} />
              <small>From Studio</small>
            </div>
            <section className="card">
              <h4>Environments</h4>
              {data.environments.map((e: any) => (
                <Env
                  key={e.alias}
                  ok={e.ok}
                  label={`${e.alias} · ${e.rule} → ${short(e.binds_now)}`}
                />
              ))}
            </section>
            <section className="card">
              <h4>Criteria and evaluators · pass at {data.pass_mark}</h4>
              <div className="table-wrap scroll" style={{ maxHeight: 320 }}>
                <table>
                  <thead>
                    <tr>
                      <th>Criterion</th>
                      <th>Weight</th>
                      <th>Rule</th>
                      <th>Binds now</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.criteria.map((c: any) => (
                      <tr key={c.criterion_id}>
                        <td>
                          {c.criterion_id}
                          <small>{c.skill_group}</small>
                        </td>
                        <td>{c.weight}</td>
                        <td>{c.rule}</td>
                        <td>
                          <Env ok={!!c.binds_now} label={c.binds_now ?? 'nothing (B4)'} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
            <section className="card">
              <h4>Case dimensions</h4>
              <dl className="kv">
                <dt>Application type</dt>
                <dd>{data.case_dimensions.application_type.join(', ')}</dd>
                <dt>Completeness</dt>
                <dd>{data.case_dimensions.completeness.join(', ')}</dd>
                <dt>Edge cases</dt>
                <dd>
                  {Object.entries(data.case_dimensions.edge_cases).map(([k, v]: any) => (
                    <small key={k}>
                      <code>{k}</code> · {v}
                    </small>
                  ))}
                </dd>
              </dl>
            </section>
            <section className="card">
              <h4>Used by</h4>
              {data.used_by.map((p: any) => (
                <div key={p.project_id}>
                  <Link href={`/gym/projects/${p.project_id}`}>{p.name}</Link> ·{' '}
                  <code>{p.project_id}</code> · <Badge state={p.state} />
                </div>
              ))}
            </section>
            <section className="card">
              <h4>Inbox items for this template</h4>
              {data.inbox_items.length === 0 && <small>None.</small>}
              {data.inbox_items.map((i: any) => (
                <small key={i.id}>
                  {i.studio_id ?? i.id} · {i.kind} · {i.summary} · {i.state}
                </small>
              ))}
              {(data.edge_cases ?? []).length > 0 && (
                <>
                  <h4>S4 edge cases</h4>
                  {data.edge_cases.map((e: any) => (
                    <small key={e.tag}>
                      <code>{e.tag}</code> · {e.archetype} · {e.complexity} · minimum{' '}
                      {typeof e.minimum === 'object'
                        ? Object.values(e.minimum as Record<string, number>).reduce(
                            (a, b) => a + b,
                            0,
                          )
                        : e.minimum}{' '}
                      · {e.recipe}
                    </small>
                  ))}
                </>
              )}
              <h4>Send to Studio inbox (new case kind)</h4>
              <small>
                The current template version is final: the item changes nothing now and reaches
                tasks only as a new template version.
              </small>
              <label>
                Summary
                <textarea value={summary} onChange={(e) => setSummary(e.target.value)} rows={2} />
              </label>
              <label>
                Evidence (episodes, the case and why it is a new kind)
                <input value={evidence} onChange={(e) => setEvidence(e.target.value)} />
              </label>
              <EdgeCaseForm value={edge} onChange={setEdge} lists={data.slice_lists ?? undefined} />
              <button
                disabled={!summary.trim() || !edgeReady(edge, true)}
                onClick={async () => {
                  setFailure(null);
                  try {
                    const item = await send('POST', `${wsBase(ws)}/inbox-items`, {
                      kind: 'new_case_kind',
                      template_id: data.template_id,
                      version: data.version,
                      summary,
                      evidence: { why: evidence },
                      edge_case: edgeBody(edge),
                    });
                    say(`New case kind item ${item.id} queued for Studio.`);
                    setSummary('');
                    setEdge(emptyEdge);
                    reload();
                  } catch (e) {
                    setFailure(e as GymApiError);
                  }
                }}
              >
                Send to Studio inbox
              </button>
              <Failure error={failure} />
            </section>
          </main>
        </div>
      )}
    </Loading>
  );
}

function Users() {
  const { ws, me, say } = useGym();
  const { data, error, reload } = useData<any>(`${wsBase(ws)}/users`);
  const [failure, setFailure] = useState<GymApiError | null>(null);
  const [q, setQ] = useState('');
  const [profile, setProfile] = useState('');
  const [inviting, setInviting] = useState(false);
  const [form, setForm] = useState({
    username: '',
    email: '',
    name: '',
    profile: 'viewer',
    binding_approver: false,
  });
  const [invited, setInvited] = useState<any>(null);
  const [history, setHistory] = useState<{ id: string; items: any[] } | null>(null);
  const admin = me.profile === 'admin';
  async function patch(u: any, body: object, message?: string) {
    try {
      await send('PATCH', `${wsBase(ws)}/users/${u.id}`, body);
      if (message) say(message);
      reload();
    } catch (err) {
      setFailure(err as GymApiError);
    }
  }
  const rows = (data?.items ?? []).filter(
    (u: any) =>
      (!q || `${u.name} ${u.email}`.toLowerCase().includes(q.toLowerCase())) &&
      (!profile || u.profile === profile),
  );
  return (
    <>
      <small>
        Members are distinct people with their own sign-in (local Keycloak). Profiles are Admin, RL
        Engineer and Viewer; the binding-approver flag lets an Admin or RL Engineer approve rule
        overrides. SMEs have no accounts here: SME review happens in Authoring. Every change is in
        the audit log.
      </small>
      <div className="toolbar">
        <Search value={q} onChange={setQ} placeholder="Search people" />
        <label>
          Profile{' '}
          <select value={profile} onChange={(e) => setProfile(e.target.value)}>
            <option value="">All</option>
            <option value="admin">Admin</option>
            <option value="rl_engineer">RL Engineer</option>
            <option value="viewer">Viewer</option>
          </select>
        </label>
        {admin && (
          <button className="primary" onClick={() => (setInviting(true), setInvited(null))}>
            Invite user
          </button>
        )}
      </div>
      {inviting && (
        <section className="card" role="dialog" aria-label="Invite user">
          <h4>Invite user</h4>
          {invited ? (
            <>
              <p>
                {invited.username} can now sign in to this workspace as {labelOf(invited.profile)}.
              </p>
              {invited.temporary_password && (
                <p>
                  Temporary password: <code>{invited.temporary_password}</code>
                </p>
              )}
              <small>{invited.note}</small>
              <button onClick={() => (setInviting(false), setInvited(null))}>Done</button>
            </>
          ) : (
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                try {
                  const out = await send('POST', `${wsBase(ws)}/users/invitations`, form);
                  setInvited(out);
                  setFailure(null);
                  say(`${out.username} invited.`);
                  reload();
                } catch (err) {
                  setFailure(err as GymApiError);
                }
              }}
            >
              <div className="grid2">
                <label>
                  Username
                  <input
                    value={form.username}
                    onChange={(e) => setForm({ ...form, username: e.target.value })}
                  />
                </label>
                <label>
                  Email
                  <input
                    value={form.email}
                    onChange={(e) => setForm({ ...form, email: e.target.value })}
                  />
                </label>
                <label>
                  Full name
                  <input
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                  />
                </label>
                <label>
                  Profile
                  <select
                    value={form.profile}
                    onChange={(e) => setForm({ ...form, profile: e.target.value })}
                  >
                    <option value="viewer">Viewer</option>
                    <option value="rl_engineer">RL Engineer</option>
                    <option value="admin">Admin</option>
                  </select>
                </label>
              </div>
              <label className="row">
                <input
                  type="checkbox"
                  checked={form.binding_approver}
                  onChange={(e) => setForm({ ...form, binding_approver: e.target.checked })}
                />
                Binding approver
              </label>
              <div className="row">
                <button className="primary" type="submit">
                  Invite
                </button>
                <button type="button" onClick={() => setInviting(false)}>
                  Cancel
                </button>
              </div>
              <small>
                Creates the person&apos;s sign-in with a temporary password they change at first
                sign-in, and their access to this workspace.
              </small>
            </form>
          )}
        </section>
      )}
      <Loading data={data} error={error}>
        {() => (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Person</th>
                  <th>Workspace profile</th>
                  <th>Binding approver</th>
                  <th>Access record</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((u: any) => (
                  <tr key={u.id}>
                    <td>
                      {u.name}
                      <small>{u.email}</small>
                    </td>
                    <td>
                      {admin && u.status === 'active' ? (
                        <select
                          aria-label={`Profile of ${u.name}`}
                          value={u.profile}
                          onChange={(e) =>
                            patch(
                              u,
                              { profile: e.target.value },
                              `${u.name} is now ${labelOf(e.target.value)}.`,
                            )
                          }
                        >
                          <option value="admin">Admin</option>
                          <option value="rl_engineer">RL Engineer</option>
                          <option value="viewer">Viewer</option>
                        </select>
                      ) : (
                        labelOf(u.profile)
                      )}
                    </td>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`Binding approver: ${u.name}`}
                        checked={u.binding_approver}
                        disabled={!admin || u.status !== 'active'}
                        onChange={(e) => patch(u, { binding_approver: e.target.checked })}
                      />
                    </td>
                    <td>
                      <Badge state={u.status === 'active' ? 'ready' : u.status} label={u.status} />
                      <small>last seen {when(u.last_seen_at)}</small>
                    </td>
                    <td>
                      {admin && (
                        <div className="row">
                          <button
                            className="link"
                            onClick={async () => {
                              const out = await fetch(`${wsBase(ws)}/users/${u.id}/history`, {
                                credentials: 'same-origin',
                              }).then((r) => r.json());
                              setHistory({ id: u.id, items: out.data?.items ?? [] });
                            }}
                          >
                            Access history
                          </button>
                          {u.status === 'active' && u.id !== me.id && (
                            <button
                              className="link"
                              onClick={async () => {
                                if (
                                  !window.confirm(
                                    `Remove ${u.name}'s access to this workspace? Their account and history are kept.`,
                                  )
                                )
                                  return;
                                try {
                                  await send('POST', `${wsBase(ws)}/users/${u.id}/remove`, {
                                    reason: 'removed by an Admin',
                                  });
                                  say(`${u.name}'s access removed.`);
                                  reload();
                                } catch (err) {
                                  setFailure(err as GymApiError);
                                }
                              }}
                            >
                              Remove access
                            </button>
                          )}
                        </div>
                      )}
                      {history?.id === u.id && (
                        <ul>
                          {history!.items.length === 0 && <li>No recorded changes.</li>}
                          {history!.items.map((h: any, n: number) => (
                            <li key={n}>
                              <small>
                                {when(h.created_at)} · {h.action} · {JSON.stringify(h.details)}
                              </small>
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Loading>
      <Failure error={failure} />
    </>
  );
}
