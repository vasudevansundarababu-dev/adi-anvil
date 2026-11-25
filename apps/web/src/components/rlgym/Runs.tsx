'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import { GymApiError, send, short, when, wsBase } from './api';
import Episode from './Episode';
import Report from './Report';
import Sme from './Sme';
import { PolicyMapSummary } from './PolicyMap';
import { Badge, Failure, Hash, Loading, Search, Tabs, useData, useGym } from './ui';
import { HowScored, ScoredBy } from './Scoring';
import { Verification } from './Verification';
import { RunDrafts } from './Workbench';

// Runs (SCREENS 3.17-3.21): list, New run with the admission checklist, Compare, and the run page (Overview, Report,
// Episodes, SME review). Only controlled mock agents run on this machine; every result says it is synthetic.

const STATE_TONE: Record<string, string> = {
  completed: 'ready',
  running: 'queued',
  admitted: 'queued',
  refused: 'blocked',
  failed: 'failed',
  cancelled: 'superseded',
};

function RunBadge({ state }: { state: string }) {
  return (
    <Badge state={STATE_TONE[state] ?? state} label={state[0].toUpperCase() + state.slice(1)} />
  );
}

function usd(v?: number | null) {
  return v === null || v === undefined ? '—' : `$${Number(v).toFixed(v < 1 ? 2 : 0)}`;
}

function duration(s?: number | null) {
  if (s === null || s === undefined) return '—';
  if (s < 60) return `${s} s`;
  const m = Math.round(s / 60);
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`;
}

export default function Runs({ parts }: { parts: string[] }) {
  if (parts[0] === 'new') return <NewRun />;
  if (parts[0] === 'compare') return <Compare />;
  if (parts[0]) return <RunPage id={parts[0]} tab={parts[1] ?? 'overview'} rest={parts.slice(2)} />;
  return <RunsList />;
}

function RunsList() {
  const { ws, say } = useGym();
  const [packaged, setPackaged] = useState<any>(null);
  const [packageError, setPackageError] = useState<GymApiError | null>(null);
  const router = useRouter();
  const [state, setState] = useState('');
  const [q, setQ] = useState('');
  const [ticked, setTicked] = useState<string[]>([]);
  const list = useData<any>(`${wsBase(ws)}/runs${state ? `?state=${state}` : ''}`);
  const items = (list.data?.items ?? []).filter(
    (r: any) => !q || `${r.name} ${r.id} ${r.project_name}`.toLowerCase().includes(q.toLowerCase()),
  );
  return (
    <main className="page">
      <div className="between">
        <h2>Runs</h2>
        <div className="row">
          <button
            disabled={ticked.length < 2}
            onClick={() =>
              router.push(`/gym/runs/compare?baseline=${ticked[0]}&compared=${ticked[1]}`)
            }
          >
            Compare ({ticked.length})
          </button>
          <button
            disabled={ticked.length < 1}
            onClick={async () => {
              try {
                const out = await send('POST', `${wsBase(ws)}/packages`, { run_ids: ticked });
                setPackaged(out);
                say(`Package ${out.id} created.`);
              } catch (e) {
                setPackageError(e as GymApiError);
              }
            }}
          >
            Package ({ticked.length})
          </button>
          <Link className="primary" href="/gym/runs/new">
            New run
          </Link>
        </div>
      </div>
      {packaged && (
        <div className="banner" role="status">
          Package {packaged.id} · {packaged.run_ids.join(', ')} ·{' '}
          <Hash value={packaged.package_sha256} />{' '}
          <a
            className="button"
            href={`${wsBase(ws)}/packages/${packaged.id}/download`}
            download={packaged.file_name}
          >
            Download package
          </a>
        </div>
      )}
      <Failure error={packageError} />
      <div className="toolbar">
        <Search value={q} onChange={setQ} placeholder="Search runs" />
        <label>
          State{' '}
          <select value={state} onChange={(e) => setState(e.target.value)}>
            <option value="">All</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="refused">Refused</option>
            <option value="cancelled">Cancelled</option>
            <option value="failed">Failed</option>
          </select>
        </label>
      </div>
      <Loading data={list.data} error={list.error}>
        {() => (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th aria-label="Select" />
                  <th>Run</th>
                  <th>Project</th>
                  <th>Models</th>
                  <th>State</th>
                  <th>Report</th>
                </tr>
              </thead>
              <tbody>
                {items.length === 0 && (
                  <tr>
                    <td colSpan={6} style={{ textAlign: 'left' }}>
                      No runs in this state.
                    </td>
                  </tr>
                )}
                {items.map((r: any) => (
                  <tr key={r.id}>
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`Select ${r.id}`}
                        title={r.state === 'completed' ? undefined : 'Only completed runs'}
                        disabled={r.state !== 'completed'}
                        checked={ticked.includes(r.id)}
                        onChange={(e) =>
                          setTicked((t) =>
                            e.target.checked ? [...t, r.id] : t.filter((x) => x !== r.id),
                          )
                        }
                      />
                    </td>
                    <td style={{ textAlign: 'left' }}>
                      <Link href={`/gym/runs/${r.id}`}>{r.name}</Link>
                      {r.leaderboard && <Badge state="ready" label="Leaderboard run" />}
                      <small>
                        {r.id} · {when(r.created_at)} ·{' '}
                        {r.manifest_sha256 ? <Hash value={r.manifest_sha256} /> : '—'}
                      </small>
                    </td>
                    <td style={{ textAlign: 'left' }}>
                      {r.project_name}
                      <small>
                        {r.suite.name} v{r.suite.version}
                      </small>
                    </td>
                    <td style={{ textAlign: 'left' }}>
                      {r.models.join(', ') || '—'}
                      <small>{r.episodes} episodes</small>
                    </td>
                    <td style={{ textAlign: 'left' }}>
                      <RunBadge state={r.state} />
                      {r.rescored && <small>re-scored</small>}
                      {r.refusal_reasons && (
                        <small>
                          {r.refusal_reasons.length} reasons:{' '}
                          {r.refusal_reasons.map((x: any) => x.detail || x.label).join('; ')}
                        </small>
                      )}
                    </td>
                    <td>
                      {r.report_available ? (
                        <Link href={`/gym/runs/${r.id}/report`}>Report</Link>
                      ) : (
                        <button disabled title="Available when the run is completed">
                          Report
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
    </main>
  );
}

function NewRun() {
  const { ws, say, me } = useGym();
  const router = useRouter();
  const query = useSearchParams();
  const base = wsBase(ws);
  const projects = useData<any>(`${base}/projects`);
  const [project, setProject] = useState(query.get('project') ?? '');
  const suites = useData<any>(project ? `${base}/projects/${project}/suites` : null);
  const sets = useData<any>(`${base}/model-sets`);
  const systems = useData<any>(`${base}/systems`);
  const [suitePick, setSuite] = useState(query.get('suite') ?? '');
  const [name, setName] = useState('');
  const [modelSet, setModelSet] = useState('');
  const [custom, setCustom] = useState<{ system_id: string; system_version: number }[] | null>(
    null,
  );
  const [attempts, setAttempts] = useState(1);
  const [timeout, setTimeoutMin] = useState(10);
  const [retries, setRetries] = useState(2);
  const [budget, setBudget] = useState(5);
  // D-033: unticked by default; only runs ticked here are counted on the leaderboard (frozen in the manifest).
  const [leaderboard, setLeaderboard] = useState(false);
  const [check, setCheck] = useState<any>(null);
  const [failure, setFailure] = useState<GymApiError | null>(null);
  const [starting, setStarting] = useState(false);
  const saved = useMemo(
    () =>
      (suites.data?.items ?? []).flatMap((s: any) =>
        s.versions
          .filter((v: any) => v.state === 'saved')
          .map((v: any) => ({
            id: v.id,
            label: `${s.name} · v${v.version}`,
            planned: v.planned_on_env_version,
          })),
      ),
    [suites.data],
  );
  // The first saved version is the default until the person picks one (derived, so a pick is never overwritten).
  const suite = suitePick || saved[0]?.id || '';
  const projectName = (projects.data?.items ?? []).find((p: any) => p.project_id === project)?.name;
  useEffect(() => {
    if (!modelSet && sets.data?.items?.length) setModelSet(sets.data.items[0].id);
  }, [sets.data, modelSet]);
  useEffect(() => {
    if (!name && projectName && sets.data) {
      const set = (sets.data?.items ?? []).find((s: any) => s.id === modelSet);
      setName(`${projectName} · ${set ? set.name : 'custom line-up'}`);
    }
  }, [projectName, modelSet, sets.data, name]);
  const selectedSet = (sets.data?.items ?? []).find((s: any) => s.id === modelSet);
  const members =
    custom ??
    (selectedSet?.members ?? []).map((m: any) => ({
      system_id: m.system_id,
      system_version: m.system_version,
    }));
  const body = {
    name,
    project_id: project,
    suite_version_id: suite,
    model_set: custom
      ? { members: custom }
      : selectedSet
        ? { id: selectedSet.id, version: selectedSet.version }
        : {},
    attempts,
    episode_timeout_min: timeout,
    infra_retries: retries,
    budget_usd: budget,
    leaderboard,
  };
  const key = JSON.stringify(body);
  useEffect(() => {
    if (!project) return;
    const t = setTimeout(() => {
      send('POST', `${base}/runs/admission-check`, JSON.parse(key))
        .then((c) => (setCheck(c), setFailure(null)))
        .catch((e) => setFailure(e));
    }, 300);
    return () => clearTimeout(t);
  }, [key, base, project]);
  const toggle = (system_id: string, version: number, on: boolean) => {
    const now = members.filter((m: any) => m.system_id !== system_id);
    setCustom(on ? [...now, { system_id, system_version: version }] : now);
  };
  const canStart = check?.passed && me.profile !== 'viewer' && !starting;
  async function start() {
    setStarting(true);
    try {
      const out = await send('POST', `${base}/runs`, body);
      say(`${out.run.id} admitted: ${out.run.total_episodes} episodes queued.`);
      router.push(`/gym/runs/${out.run.id}`);
    } catch (e) {
      const err = e as GymApiError;
      setFailure(err);
      if (err.error?.details?.run_id)
        say(`Admission refused; stored as ${err.error.details.run_id}.`);
    } finally {
      setStarting(false);
    }
  }
  return (
    <div className="work">
      <aside>
        <Link href="/gym/runs">← Back to runs</Link>
        <h3>Admission checklist</h3>
        {check ? (
          <>
            <Badge
              state={check.passed ? 'ready' : 'blocked'}
              label={check.passed ? 'Passed' : 'Blocked'}
            />
            {check.items.map((i: any) => (
              <div className="check" key={i.key + i.label}>
                <i className={i.ok ? 'ok' : 'no'}>{i.ok ? '✓' : '✕'}</i>
                <span>
                  {i.label}
                  {i.detail && <small>{i.detail}</small>}
                </span>
              </div>
            ))}
          </>
        ) : (
          <p className="wait">Choose a project and a suite.</p>
        )}
        <div className="row">
          <button className="primary" disabled={!canStart} onClick={start}>
            {starting ? 'Starting…' : 'Start run'}
          </button>
        </div>
        {me.profile === 'viewer' && <small>Viewers cannot start runs.</small>}
        <Failure error={failure} />
      </aside>
      <main className="page">
        <h2>New run</h2>
        {check?.note && (
          <div className="banner" role="note">
            {check.note}
          </div>
        )}
        <div className="grid2">
          <label>
            Run name
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label>
            Project
            <select
              value={project}
              onChange={(e) => {
                setProject(e.target.value);
                setSuite('');
              }}
            >
              <option value="">Choose…</option>
              {(projects.data?.items ?? []).map((p: any) => (
                <option key={p.project_id} value={p.project_id}>
                  {p.name} ({p.project_id})
                </option>
              ))}
            </select>
          </label>
          <label>
            Suite
            <select value={suite} onChange={(e) => setSuite(e.target.value)}>
              {saved.length === 0 && <option value="">No saved suite version</option>}
              {saved.map((s: any) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Model set
            <select
              value={custom ? 'custom' : modelSet}
              onChange={(e) => {
                if (e.target.value === 'custom') setCustom(members);
                else {
                  setCustom(null);
                  setModelSet(e.target.value);
                }
              }}
            >
              {(sets.data?.items ?? []).map((s: any) => (
                <option key={s.id} value={s.id}>
                  {s.name} (v{s.version})
                </option>
              ))}
              <option value="custom">Custom</option>
            </select>
          </label>
          <label>
            Attempts per case and model
            <input
              type="number"
              min={1}
              max={10}
              value={attempts}
              onChange={(e) => setAttempts(Number(e.target.value))}
            />
          </label>
          <label>
            Timeout per episode (min)
            <input
              type="number"
              min={1}
              value={timeout}
              onChange={(e) => setTimeoutMin(Number(e.target.value))}
            />
          </label>
          <label>
            Retries on infrastructure error
            <input
              type="number"
              min={0}
              max={5}
              value={retries}
              onChange={(e) => setRetries(Number(e.target.value))}
            />
          </label>
          <label>
            Budget cap (USD)
            <input
              type="number"
              min={0}
              step="0.01"
              value={budget}
              onChange={(e) => setBudget(Number(e.target.value))}
            />
          </label>
        </div>
        <label className="row">
          <input
            type="checkbox"
            checked={leaderboard}
            disabled={!leaderboard && check?.leaderboard?.eligible === false}
            onChange={(e) => setLeaderboard(e.target.checked)}
          />
          Count this run on the leaderboard
          <small>
            Off by default. Fixed when the run starts; only ticked runs are ranked on the
            leaderboard.
          </small>
        </label>
        {check?.leaderboard?.eligible === false && (
          <small className="no">
            Can&rsquo;t be a leaderboard run: {check.leaderboard.reasons.join('; ')}.
          </small>
        )}
        <section className="card">
          <h3>Models</h3>
          {(systems.data?.items ?? []).map((s: any) => {
            const on = members.some((m: any) => m.system_id === s.system_id);
            return (
              <label key={s.system_id} className="row">
                <input
                  type="checkbox"
                  checked={on}
                  onChange={(e) => toggle(s.system_id, s.latest.version, e.target.checked)}
                />
                {s.name} v{s.latest.version}{' '}
                <Badge state={s.status === 'Ready' ? 'ready' : 'draft'} label={s.status} />
                {s.synthetic && <small>synthetic</small>}
              </label>
            );
          })}
        </section>
        {check?.uses && (
          <section className="card">
            <div className="between">
              <h3>What this suite uses</h3>
              {project && suite && <Link href={`/gym/projects/${project}/suites`}>Edit suite</Link>}
            </div>
            <dl className="kv">
              <dt>Environment</dt>
              <dd>
                {check.uses.environment
                  ? `alias ${check.uses.environment.alias} · ${check.uses.environment.rule} → ${short(
                      check.uses.environment.version_id,
                    )} · seed family ${check.uses.environment.seed_family}`
                  : '—'}
                <small>Bound at Start, then frozen.</small>
              </dd>
              <dt>Evaluators</dt>
              <dd>
                {check.uses.evaluators.length} configurations
                <small>{check.uses.evaluators.join(', ')}</small>
              </dd>
              <dt>Data plan</dt>
              <dd>
                {check.uses.data_plan
                  ? `${check.uses.data_plan.selected} cases selected (plan ${check.uses.data_plan.sample_size}) · seed ${check.uses.data_plan.seed}`
                  : '—'}
              </dd>
              <dt>Trust & Safety</dt>
              <dd>{check.uses.trust_and_safety}</dd>
              <dt>Tasks</dt>
              <dd>{check.uses.tasks}</dd>
            </dl>
          </section>
        )}
        {check && (
          <section className="card">
            <h3>
              {check.episodes} episodes · projected {usd(check.projected_usd)}
            </h3>
            {check.per_model.length === 0 ? (
              <p>Pick at least one model.</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Model</th>
                      <th>Episodes</th>
                      <th>Spend per episode</th>
                      <th>Projected</th>
                    </tr>
                  </thead>
                  <tbody>
                    {check.per_model.map((m: any) => (
                      <tr key={m.system_id}>
                        <td style={{ textAlign: 'left' }}>
                          {m.name ?? m.system_id} v{m.version}
                        </td>
                        <td>
                          {m.formula} = {m.episodes}
                        </td>
                        <td>{usd(m.spend_per_episode_usd)}</td>
                        <td>{usd(m.projected_usd)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <small>
              Episodes = (cases + safety prompts) × models × attempts. The controlled mock spends
              nothing.
            </small>
          </section>
        )}
      </main>
    </div>
  );
}

function Compare() {
  const { ws, say } = useGym();
  const query = useSearchParams();
  const base = wsBase(ws);
  const runs = useData<any>(`${base}/runs`);
  const [a, setA] = useState(query.get('baseline') ?? '');
  const [b, setB] = useState(query.get('compared') ?? '');
  const result = useData<any>(
    a && b && a !== b ? `${base}/comparisons?baseline=${a}&compared=${b}` : null,
  );
  const [failure, setFailure] = useState<GymApiError | null>(null);
  const options = (runs.data?.items ?? []).filter(
    (r: any) => r.state !== 'refused' || r.id === a || r.id === b,
  );
  const pick = (value: string, set: (v: string) => void, label: string) => (
    <label>
      {label}
      <select value={value} onChange={(e) => set(e.target.value)}>
        <option value="">Choose…</option>
        {options.map((r: any) => (
          <option key={r.id} value={r.id}>
            {r.id} · {r.name} ({r.state})
          </option>
        ))}
      </select>
    </label>
  );
  const data = result.data;
  return (
    <div className="work">
      <aside>
        <Link href="/gym/runs">← Back to runs</Link>
        <h3>Rule checks</h3>
        {a && b && a === b && <p className="error">Pick two different runs.</p>}
        {data?.checks.map((c: any) => (
          <div className="check" key={c.key}>
            <i className={c.ok ? 'ok' : 'no'}>{c.ok ? '✓' : '✕'}</i>
            <span>
              {c.label}
              {c.detail && <small>{c.detail}</small>}
            </span>
          </div>
        ))}
        {data?.comparable && (
          <button
            className="primary"
            onClick={async () => {
              try {
                const out = await send('POST', `${base}/comparisons`, { baseline: a, compared: b });
                say(`Comparison saved as ${out.id}.`);
              } catch (e) {
                setFailure(e as GymApiError);
              }
            }}
          >
            Save comparison
          </button>
        )}
        <Failure error={failure ?? result.error} />
      </aside>
      <main className="page">
        <h2>Compare runs</h2>
        <div className="grid2">
          {pick(a, setA, 'Baseline')}
          {pick(b, setB, 'Compared')}
        </div>
        {data && !data.comparable && <div className="banner">{data.message}</div>}
        {data?.comparable && (
          <>
            <div className="grid3">
              <section className="card">
                <h4>Mean score</h4>
                <p>
                  {data.mean_score.baseline} → {data.mean_score.compared}
                </p>
                <small>
                  {data.delta >= 0 ? '+' : ''}
                  {data.delta} · paired 95% CI{' '}
                  {data.paired_ci ? `${data.paired_ci[0]} to ${data.paired_ci[1]}` : '—'}
                </small>
              </section>
              <section className="card">
                <h4>Pass rate</h4>
                <p>
                  {Math.round(data.pass_rate.baseline * 100)}% →{' '}
                  {Math.round(data.pass_rate.compared * 100)}%
                </p>
                <small>{data.paired_episodes} paired episodes</small>
              </section>
              <section className="card">
                <h4>Disagreements</h4>
                <p>{data.disagreements.length}</p>
                <small>episodes that pass in one run only</small>
              </section>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Criterion</th>
                    <th>Baseline</th>
                    <th>Compared</th>
                    <th>Delta</th>
                  </tr>
                </thead>
                <tbody>
                  {data.criteria.map((c: any) => (
                    <tr key={c.criterion_id}>
                      <td style={{ textAlign: 'left' }}>{c.criterion_id}</td>
                      <td>{pct(c.baseline)}</td>
                      <td>{pct(c.compared)}</td>
                      <td>
                        {c.delta === null
                          ? '—'
                          : `${c.delta >= 0 ? '+' : ''}${Math.round(c.delta * 100)} pts`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

function pct(v?: number | null) {
  return v === null || v === undefined ? '—' : `${Math.round(v * 100)}%`;
}

function RunPage({ id, tab, rest }: { id: string; tab: string; rest: string[] }) {
  const { ws, say, me } = useGym();
  const base = wsBase(ws);
  const run = useData<any>(`${base}/runs/${id}`);
  const [failure, setFailure] = useState<GymApiError | null>(null);
  const live = run.data && ['admitted', 'running'].includes(run.data.state);
  const { reload } = run;
  useEffect(() => {
    if (!live) return;
    const t = setInterval(reload, 2000);
    return () => clearInterval(t);
  }, [live, reload]);
  async function act(path: string, message: string, bodyIn: object = {}) {
    try {
      await send('POST', `${base}/runs/${id}/${path}`, bodyIn);
      say(message);
      reload();
    } catch (e) {
      setFailure(e as GymApiError);
    }
  }
  return (
    <main className="page">
      <Loading data={run.data} error={run.error}>
        {() => {
          const r = run.data;
          const canAct = me.profile !== 'viewer';
          return (
            <>
              <small>
                Run · {r.manifest?.project?.name ?? r.project_id} · {when(r.created_at)}
              </small>
              <div className="between">
                <h2>
                  {r.name} <RunBadge state={r.state} />
                  {r.rescored && <Badge state="draft" label="Re-scored" />}
                  {r.leaderboard && <Badge state="ready" label="Leaderboard run" />}
                </h2>
                <div className="row">
                  {live && canAct && (
                    <button
                      onClick={() =>
                        act('cancel', 'Cancelling stops queuing; running episodes seal first.', {
                          reason: 'cancelled from the run page',
                        })
                      }
                    >
                      Cancel run
                    </button>
                  )}
                  {r.leaderboard && (
                    <Link href={`/gym?project=${r.project_id}`}>View on leaderboard</Link>
                  )}
                  {r.state === 'completed' && canAct && (
                    <button
                      title="Grades the recorded episodes again with the current qualified evaluator versions; no model is called"
                      onClick={() => {
                        if (
                          window.confirm(
                            'Re-score this run? The recorded episodes are graded again with the current qualified evaluator versions. No model is called; earlier scores are kept.',
                          )
                        )
                          act(
                            'rescore',
                            'Re-scored. Earlier scores are kept beside the new ones.',
                            { reason: 'explicit re-score' },
                          );
                      }}
                    >
                      Re-score…
                    </button>
                  )}
                </div>
              </div>
              <small>
                {r.id} · manifest <Hash value={r.manifest_sha256} />
              </small>
              {r.note && (
                <div className="banner" role="note">
                  {r.note}
                </div>
              )}
              <Failure error={failure} />
              <Tabs
                current={tab}
                items={[
                  { key: 'overview', label: 'Overview', href: `/gym/runs/${id}` },
                  { key: 'report', label: 'Report', href: `/gym/runs/${id}/report` },
                  { key: 'episodes', label: 'Episodes', href: `/gym/runs/${id}/episodes` },
                  { key: 'sme', label: 'SME review', href: `/gym/runs/${id}/sme` },
                  {
                    key: 'verification',
                    label: 'Verification',
                    href: `/gym/runs/${id}/verification`,
                  },
                ]}
              />
              {tab === 'overview' && <Overview r={r} />}
              {tab === 'overview' && <RunDrafts run={r} />}
              {tab === 'report' && <Report id={id} rest={rest} />}
              {tab === 'episodes' &&
                (rest[0] ? <Episode runId={id} episodeId={rest[0]} /> : <Episodes id={id} r={r} />)}
              {tab === 'sme' && <Sme runId={id} />}
              {tab === 'verification' && <Verification runId={id} />}
            </>
          );
        }}
      </Loading>
    </main>
  );
}

const SEGMENTS: [string, string][] = [
  ['scored', 'Scored'],
  ['scoring', 'Scoring'],
  ['running', 'Running'],
  ['queued', 'Queued'],
  ['errored', 'Errored'],
  ['timed_out', 'Timed out'],
  ['cancelled', 'Cancelled'],
];

function Overview({ r }: { r: any }) {
  const total = r.total_episodes || 1;
  const m = r.manifest;
  const running = ['admitted', 'running'].includes(r.state);
  return (
    <>
      <section className="card">
        <div className="stack" role="img" aria-label="Episodes by state">
          {SEGMENTS.filter(([k]) => r.counts[k]).map(([k]) => (
            <span key={k} data-s={k} style={{ width: `${(100 * r.counts[k]) / total}%` }} />
          ))}
        </div>
        <div className="row">
          {SEGMENTS.filter(([k]) => r.counts[k]).map(([k, label]) => (
            <small key={k}>
              <span className="swatch" data-s={k} /> {label} {r.counts[k]}
            </small>
          ))}
          {r.total_episodes === 0 && <small>No episodes (refused).</small>}
        </div>
        {running && (
          <dl className="kv">
            <dt>Elapsed</dt>
            <dd>{duration(r.elapsed_s)}</dd>
            <dt>Estimated finish</dt>
            <dd>
              {r.estimated_remaining_s ? `about ${duration(r.estimated_remaining_s)} left` : '—'}
            </dd>
            <dt>Cost so far</dt>
            <dd>
              {usd(r.cost_so_far_usd)} of {usd(Number(r.budget_usd))} cap · projected{' '}
              {usd(m?.projected_usd)}
            </dd>
          </dl>
        )}
        {(r.live_spend ?? []).length > 0 && (
          <>
            <h4>Live spend</h4>
            <table className="blocks">
              <thead>
                <tr>
                  <th>Model</th>
                  <th>Approval</th>
                  <th>Calls</th>
                  <th>Tokens in · out</th>
                  <th>Cost · run cap</th>
                  <th>Not answered · errors</th>
                </tr>
              </thead>
              <tbody>
                {r.live_spend.map((l: any) => (
                  <tr key={l.system_id}>
                    <td>
                      {l.name} · {l.provider} <code>{l.model_id}</code>
                    </td>
                    <td>
                      <code>{l.approval_id}</code>
                    </td>
                    <td>{l.calls}</td>
                    <td>
                      {l.tokens_in} · {l.tokens_out}
                    </td>
                    <td>
                      {usd(l.cost_usd)} · {usd(l.per_run_cap_usd)}
                    </td>
                    <td>
                      {l.ambiguous} · {l.errors}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </section>
      {r.refusal_reasons && (
        <section className="card">
          <h3>Refused: {r.refusal_reasons.length} reasons</h3>
          {r.refusal_reasons.map((x: any) => (
            <div className="check" key={x.key + x.label}>
              <i className="no">✕</i>
              <span>
                {x.label}
                {x.detail && <small>{x.detail}</small>}
              </span>
            </div>
          ))}
        </section>
      )}
      <PolicyMapSummary summary={r.policy_maps} />
      {r.statistics.systems.length > 0 && (
        <div className="grid3">
          {r.statistics.systems.map((s: any) => (
            <section className="card" key={s.system_id}>
              <div className="between">
                <h4>
                  {s.name} v{s.system_version}
                </h4>
                {s.gate && (
                  <Badge state={s.gate === 'PASSED' ? 'ready' : 'failed'} label={s.gate} />
                )}
              </div>
              <p className="big">{s.mean_score ?? '—'}</p>
              <small>
                {s.mean_score === null
                  ? 'not finished'
                  : `likely range ${s.likely_range ? `${s.likely_range[0]}–${s.likely_range[1]}` : '—'} · passed ${pct(
                      s.pass_rate,
                    )} of cases · ${s.scored} scored`}
              </small>
              {s.provider_refused > 0 && (
                <small className="no">
                  {s.provider_refused} provider-refused episode{s.provider_refused === 1 ? '' : 's'}
                  , excluded from score
                </small>
              )}
              <small>
                {s.errored} errored · {s.timed_out} timed out
                {s.safety.attacks > 0 &&
                  ` · Trust & Safety: acted on ${s.safety.acted_on} of ${s.safety.attacks}, ${s.safety.blocked} blocked, ${s.safety.critical} critical`}
              </small>
            </section>
          ))}
        </div>
      )}
      {m && (
        <section className="card">
          <h3>What this run used</h3>
          <dl className="kv">
            <dt>Suite</dt>
            <dd>
              {m.suite.name} v{m.suite.version} <Hash value={m.suite.suite_sha256} />
            </dd>
            <dt>Environment</dt>
            <dd>
              {short(m.environment.version_id)} · {m.environment.rule} · seed family{' '}
              {m.environment.seed_family}
              <small>
                image {m.environment.local_image?.tag ?? '—'}{' '}
                <Hash value={m.environment.local_image?.id} /> (built locally from the Studio
                recipe)
              </small>
            </dd>
            <dt>Evaluators</dt>
            <dd>
              {m.evaluators.length} configurations
              <small>
                {m.evaluators.map((e: any) => `${e.configuration_id} v${e.version}`).join(', ')}
              </small>
              {Object.keys(r.scoring ?? {}).length > 0 && (
                <ul>
                  {Object.entries(r.scoring).map(([cid, s]: [string, any]) => (
                    <li key={cid}>
                      <strong>{cid}</strong>: <ScoredBy s={s} />
                      <HowScored s={s} />
                    </li>
                  ))}
                </ul>
              )}
            </dd>
            <dt>Data plan</dt>
            <dd>
              {m.data_plan.case_ids.length} cases (plan {m.data_plan.sample_size}) · seed{' '}
              {m.data_plan.sampling_seed}
            </dd>
            <dt>Agent view</dt>
            <dd>
              {m.ids_aliased
                ? 'Case IDs hidden from the agent (opaque per-episode aliases)'
                : 'Case IDs shown to the agent as they are'}
            </dd>
            <dt>Trust & Safety</dt>
            <dd>
              {m.trust_and_safety.enabled
                ? `${m.trust_and_safety.prompts.length} approved prompts · delivered in the ${(
                    m.trust_and_safety.delivered_as ?? m.trust_and_safety.placement
                  ).replace('_', ' ')}`
                : 'off'}
              {m.trust_and_safety.enabled &&
                m.trust_and_safety.delivered_as &&
                m.trust_and_safety.delivered_as !== m.trust_and_safety.placement && (
                  <small>
                    The suite asked for {m.trust_and_safety.placement.replace('_', ' ')}; this
                    environment has no injection point, so hidden instructions in documents or tool
                    output were not tested (D-040).
                  </small>
                )}
            </dd>
            <dt>Models</dt>
            <dd>
              {m.model_set?.custom ? 'Custom' : `${m.model_set?.name} (v${m.model_set?.version})`} ·{' '}
              {m.models.map((x: any) => `${x.name} v${x.version}`).join(', ')}
            </dd>
            <dt>Episodes</dt>
            <dd>
              {m.episodes} = {m.episode_formula}
            </dd>
          </dl>
          <small>None of this changes for this run, even if a version is later revoked.</small>
        </section>
      )}
      {r.statistics.by_stratum.length > 0 && (
        <section className="card">
          <h3>Results by stratum</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Dimension</th>
                  <th>Value</th>
                  <th>Model</th>
                  <th>Episodes</th>
                  <th>Mean</th>
                  <th>Passed</th>
                </tr>
              </thead>
              <tbody>
                {r.statistics.by_stratum.map((s: any) => (
                  <tr key={`${s.dimension}${s.value}${s.system_id}`}>
                    <td style={{ textAlign: 'left' }}>{s.dimension.replace('_', ' ')}</td>
                    <td style={{ textAlign: 'left' }}>{s.value}</td>
                    <td style={{ textAlign: 'left' }}>{s.system_id}</td>
                    <td>
                      {s.episodes}
                      {s.small_sample && <small> small sample</small>}
                    </td>
                    <td>{s.mean_score}</td>
                    <td>{pct(s.pass_rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {r.statistics.systems.length > 0 && (
        <section className="card">
          <h3>Cost</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Model</th>
                  <th>Episodes</th>
                  <th>Cost</th>
                </tr>
              </thead>
              <tbody>
                {r.statistics.systems.map((s: any) => (
                  <tr key={s.system_id}>
                    <td style={{ textAlign: 'left' }}>{s.name}</td>
                    <td>{s.episodes}</td>
                    <td>{usd(s.cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <small>
            Total {usd(r.cost_so_far_usd)} of {usd(Number(r.budget_usd))} cap. Scoring passes:{' '}
            {r.passes.map((p: any) => `${p.pass} (${p.reason})`).join(', ')}.
          </small>
        </section>
      )}
    </>
  );
}

function Episodes({ id, r }: { id: string; r: any }) {
  const { ws } = useGym();
  const [system, setSystem] = useState('');
  const [state, setState] = useState('');
  const [kind, setKind] = useState('');
  const [verdict, setVerdict] = useState('');
  const initial = useSearchParams();
  const [q, setQ] = useState(initial.get('q') ?? '');
  const [page, setPage] = useState(1);
  const params = new URLSearchParams({ page: String(page), size: '50' });
  if (system) params.set('system', system);
  if (state) params.set('state', state);
  if (kind) params.set('kind', kind);
  if (verdict) params.set('verdict', verdict);
  if (q) params.set('q', q);
  const list = useData<any>(`${wsBase(ws)}/runs/${id}/episodes?${params}`);
  const models = r.manifest?.models ?? [];
  const select = (
    value: string,
    set: (v: string) => void,
    label: string,
    options: [string, string][],
  ) => (
    <label>
      {label}{' '}
      <select
        value={value}
        onChange={(e) => {
          set(e.target.value);
          setPage(1);
        }}
      >
        <option value="">All</option>
        {options.map(([v, l]) => (
          <option key={v} value={v}>
            {l}
          </option>
        ))}
      </select>
    </label>
  );
  return (
    <>
      <div className="toolbar">
        <Search value={q} onChange={setQ} placeholder="Search episodes" />
        {select(
          system,
          setSystem,
          'Model',
          models.map((m: any) => [m.system_id, m.name]),
        )}
        {select(state, setState, 'State', SEGMENTS)}
        {select(verdict, setVerdict, 'Verdict', [
          ['passed', 'Passed'],
          ['failed', 'Failed'],
        ])}
        {select(kind, setKind, 'Kind', [
          ['case', 'Normal'],
          ['safety', 'Safety'],
        ])}
      </div>
      <Loading data={list.data} error={list.error}>
        {() => (
          <>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Episode</th>
                    <th>Task · case</th>
                    <th>Model</th>
                    <th>State</th>
                    <th>Score</th>
                    <th>Likely cause</th>
                    <th>Sealed</th>
                  </tr>
                </thead>
                <tbody>
                  {list.data.items.length === 0 && (
                    <tr>
                      <td colSpan={7} style={{ textAlign: 'left' }}>
                        No episodes match.
                      </td>
                    </tr>
                  )}
                  {list.data.items.map((e: any) => (
                    <tr key={e.id}>
                      <td style={{ textAlign: 'left' }}>
                        <Link href={`/gym/runs/${id}/episodes/${e.id}`}>{e.id}</Link>
                        <small>
                          {e.kind === 'safety' ? `safety · ${e.ts_category}` : 'normal'} · attempt{' '}
                          {e.attempt}
                        </small>
                      </td>
                      <td style={{ textAlign: 'left' }}>
                        {e.task_id} r{e.task_revision}
                        <small>
                          {e.case_id} · {e.application_type} · {e.completeness}
                          {e.edge_cases.length ? ` · ${e.edge_cases.join(', ')}` : ''}
                        </small>
                      </td>
                      <td style={{ textAlign: 'left' }}>
                        {e.system_id} v{e.system_version}
                      </td>
                      <td>
                        {e.provider_refused ? (
                          <Badge state="failed" label="provider refused" />
                        ) : (
                          <Badge
                            state={e.state === 'scored' ? 'ready' : e.state}
                            label={e.state.replace('_', ' ')}
                          />
                        )}
                        {e.last_error && <small>{e.last_error}</small>}
                      </td>
                      <td>
                        {e.kind === 'safety'
                          ? `${(e.safety_outcome ?? '—').replace(/_/g, ' ')}${e.safety_critical ? ' · critical' : ''}`
                          : e.provider_refused
                            ? 'excluded from score'
                            : e.score === null
                              ? '—'
                              : `${e.score}${e.passed ? ' · passed' : ' · failed'}`}
                        {e.failed_criteria?.length ? (
                          <small>{e.failed_criteria.join(', ')}</small>
                        ) : null}
                      </td>
                      <td>
                        {e.likely_cause ?? '—'}
                        {e.likely_cause_source === 'rule' && <small>suggested by rule</small>}
                      </td>
                      <td>
                        <Hash value={e.sealed_sha256} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="row">
              <button disabled={page <= 1} onClick={() => setPage(page - 1)}>
                Previous
              </button>
              <small>
                {list.data.total} episodes · page {page}
              </small>
              <button disabled={page * 50 >= list.data.total} onClick={() => setPage(page + 1)}>
                Next
              </button>
            </div>
            <small>
              The episode viewer (path, criteria, timeline, final vs expected output) is work
              package 2.9.
            </small>
          </>
        )}
      </Loading>
    </>
  );
}
