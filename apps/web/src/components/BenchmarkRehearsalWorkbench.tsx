'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { benchmarkGet, benchmarkPost } from '../lib/benchmark';
import { Rehearsal, rehearsalCells, rehearsalLink } from '../lib/benchmark-rehearsal';
import { WorkbenchPanel, WorkbenchMetric, WorkbenchEmpty } from './BenchmarkWorkbenchUI';
import styles from './BenchmarkWorkbench.module.css';

type Policy = { required_reviewers: number; revision: string | number; policy_sha256: string };
type Authorization = {
  ready: boolean;
  state: string;
  required_reviewers: number;
  completed_reviewers: number;
  policy_sha256: string;
  admin_actor_id?: string;
};
type Run = Rehearsal & { report_authorization?: Authorization };
const views = [
  ['overview', 'Overview & leaderboard'],
  ['trace', 'Trace & rubric'],
  ['failures', 'Failure analysis'],
  ['remediation', 'Remediation & datasets'],
] as const;

export default function BenchmarkRehearsalWorkbench({
  base,
  route,
  canAdmin,
  canWrite,
}: {
  base: string;
  route: string;
  canAdmin: boolean;
  canWrite: boolean;
}) {
  const router = useRouter(),
    pathname = usePathname(),
    search = useSearchParams();
  const query = new URLSearchParams(search.toString()),
    id = query.get('rehearsal_id') || '';
  const view = views.find(([key]) => pathname.endsWith('/' + key))?.[0] || 'overview';
  const [run, setRun] = useState<Run | null>(null),
    [runs, setRuns] = useState<Run[]>([]);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [notice, setNotice] = useState('');
  const [name, setName] = useState('Fictional arithmetic comparison'),
    [policy, setPolicy] = useState<Policy | null>(null),
    [count, setCount] = useState('1');
  const [rationale, setRationale] = useState(''),
    [expected, setExpected] = useState(''),
    [draftTitle, setDraftTitle] = useState(''),
    [draftReason, setDraftReason] = useState('');
  const [reviewAssignment, setReviewAssignment] = useState('');
  const [humanInspected, setHumanInspected] = useState(false);
  const [datasetName, setDatasetName] = useState('Fictional comparison regression drafts');
  const loadGeneration = useRef(0);
  const load = useCallback(async () => {
    const generation = ++loadGeneration.current;
    setError('');
    try {
      const [list, p, current] = await Promise.all([
        benchmarkGet<{ items: Run[] }>(base, '/rehearsals'),
        benchmarkGet<Policy>(base, '/report-review-policy'),
        id
          ? benchmarkGet<Run>(base, '/rehearsals/' + encodeURIComponent(id))
          : Promise.resolve(null),
      ]);
      if (generation !== loadGeneration.current) return;
      setRuns(list.items);
      setPolicy(p);
      setCount(String(p.required_reviewers));
      setRun(current);
    } catch (e) {
      if (generation !== loadGeneration.current) return;
      setError((e as Error).message);
      setRun(null);
    }
  }, [base, id]);
  useEffect(() => {
    void load();
    return () => {
      loadGeneration.current++;
    };
  }, [load]);
  useEffect(() => {
    setExpected('');
    setDraftTitle('');
    setDraftReason('');
  }, [id, search.get('cell_id')]);
  async function act(work: () => Promise<void>) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await work();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const link = (next: string, updates: Record<string, string | null> = {}) =>
    rehearsalLink(route, next, id, query, updates);
  const cells = run ? rehearsalCells(run, query) : [];
  const selected = cells.find((c) => c.id === query.get('cell_id')) || null;
  const label = (key: string) => run?.manifest.profiles.find((p) => p.id === key)?.label || key;
  function filter(key: string, value: string) {
    router.push(link(view, { [key]: value === 'all' ? null : value, cell_id: null }));
  }
  const failures = cells.filter((c) => c.failure_tags.length > 0);
  const auth = run?.report_authorization;
  async function create() {
    await act(async () => {
      const item = await benchmarkPost<Run>(base, '/rehearsals', { name });
      router.push(rehearsalLink(route, 'overview', item.id, new URLSearchParams()));
      setRun(item);
      setNotice('Draft saved. No execution or approval was created.');
    });
  }
  async function execute() {
    if (!run) return;
    await act(async () => {
      const item = await benchmarkPost<Run>(base, '/rehearsals/' + run.id + '/execute', {
        expected_manifest_sha256: run.manifest_sha256,
      });
      setRun(item);
      setNotice(
        'Executed and persisted the fictional software comparison. No model provider was called.',
      );
      await load();
    });
  }
  async function draft() {
    if (!selected || !run) return;
    await act(async () => {
      const bank = await benchmarkPost<{ id: string }>(base, '/golden-datasets', {
        name: datasetName,
        description:
          'Human-authored draft from fictional software rehearsal ' +
          run.id +
          '. No source or scoring authority.',
      });
      await benchmarkPost(base, '/golden-datasets/' + bank.id + '/versions', {
        case_key: 'rehearsal-' + selected.id,
        title: draftTitle,
        category: 'task_correctness',
        input_text:
          'Fictional software rehearsal ' +
          run.id +
          '; result ' +
          run.result?.result_sha256 +
          '; cell ' +
          selected.id +
          '; task ' +
          selected.task_id +
          '. ' +
          draftReason,
        expected_output: expected,
        fictional_task_id: selected.task_id,
        source_build_id: null,
        source_anchor: null,
        source_trace_id: null,
        predecessor_id: null,
      });
      setNotice(
        'Golden draft saved with the rehearsal/cell reference in its human-authored context. It is unbound, unverified and grants no scoring authority.',
      );
      setExpected('');
    });
  }
  const table = (items: typeof cells) => (
    <div className={styles.tableWrap}>
      <table>
        <caption>Actual persisted scripted executions · no model measurements</caption>
        <thead>
          <tr>
            <th>Profile</th>
            <th>Task / repetition</th>
            <th>Points</th>
            <th>Execution</th>
            <th>Evidence</th>
          </tr>
        </thead>
        <tbody>
          {items.map((c) => (
            <tr key={c.id}>
              <td>{label(c.profile_id)}</td>
              <td>
                {c.task_id} · {c.repetition + 1}
              </td>
              <td>
                {c.earned_points} / {c.possible_points}
              </td>
              <td>
                {c.state}
                <small>{c.duration_ms.toFixed(3)} ms</small>
              </td>
              <td>
                <a href={link('trace', { cell_id: c.id })}>Inspect execution ↗</a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
  return (
    <section className={styles.workbench} aria-label="Fictional comparison workbench">
      <div className={styles.topbar}>
        <div className={styles.brand}>Fictional software comparison</div>
        <span>Paid calls off · No model performance claims</span>
      </div>
      <nav className={styles.tabs} aria-label="Fictional benchmark views">
        {views.map(([key, title]) => (
          <a
            key={key}
            href={id ? link(key) : route + '/benchmarks/rehearsal'}
            aria-current={view === key ? 'page' : undefined}
          >
            {title}
          </a>
        ))}
      </nav>
      <div className={styles.body}>
        <header className={styles.heading}>
          <div>
            <p className={styles.eyebrow}>FICTIONAL / {view}</p>
            <h2>{views.find(([key]) => key === view)?.[1]}</h2>
            <p>
              Execute public arithmetic tasks against versioned scripted algorithms, inspect their
              outputs and compare their computed scores. This is software conformance, not a
              vendor-model benchmark.
            </p>
          </div>
          <a href={route + '/benchmarks/evidence'}>Stored evidence workspace ↗</a>
        </header>
        {error && (
          <p className={styles.alert} role="alert">
            {error}
          </p>
        )}
        {notice && (
          <p className={styles.notice} role="status">
            {notice}
          </p>
        )}
        <aside className={styles.notice}>
          No source approval, qualification or reviewer decision is manufactured. The official
          benchmark workflow keeps its source, execution and spending gates.
        </aside>
        <div className={styles.filters}>
          <label className={styles.field}>
            Stored fictional comparison
            <select
              value={id}
              disabled={busy}
              onChange={(e) =>
                router.push(rehearsalLink(route, 'overview', e.target.value, new URLSearchParams()))
              }
            >
              <option value="">New comparison</option>
              {runs.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name} · {r.state}
                </option>
              ))}
            </select>
          </label>
          {run && (
            <>
              <label className={styles.field}>
                Scripted profile
                <select
                  value={query.get('profile') || 'all'}
                  onChange={(e) => filter('profile', e.target.value)}
                >
                  <option value="all">All scripted profiles</option>
                  {run.manifest.profiles.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className={styles.field}>
                Fictional task
                <select
                  value={query.get('task') || 'all'}
                  onChange={(e) => filter('task', e.target.value)}
                >
                  <option value="all">All tasks</option>
                  {run.manifest.tasks.map((t) => (
                    <option key={t.id}>{t.id}</option>
                  ))}
                </select>
              </label>
              <label className={styles.field}>
                Evaluation period
                <select
                  value={query.get('period') || 'all'}
                  onChange={(e) => filter('period', e.target.value)}
                >
                  <option value="all">All time</option>
                  <option value="7d">Last 7 days · UTC</option>
                  <option value="30d">Last 30 days · UTC</option>
                </select>
              </label>
              <label className={styles.field}>
                Recorded environment
                <select
                  value={query.get('environment') || 'all'}
                  onChange={(e) => filter('environment', e.target.value)}
                >
                  <option value="all">All environments</option>
                  <option value={run.manifest.environment}>{run.manifest.environment}</option>
                </select>
              </label>
            </>
          )}
        </div>
        {!run && (
          <WorkbenchPanel title="Create a fictional comparison" note="Original public task bank">
            <form
              className={styles.form}
              onSubmit={(e) => {
                e.preventDefault();
                void create();
              }}
            >
              <label className={styles.field}>
                Comparison name
                <input
                  required
                  maxLength={160}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
              <p>
                Three fixed scripted profiles, three fictional tasks and two repetitions. Candidate
                functions receive public inputs only; a separate evaluator calculates criterion
                points. Execution uses trusted built-in functions, not Docker isolation or model
                inference.
              </p>
              <button disabled={busy || !canWrite}>Create fictional comparison</button>
            </form>
          </WorkbenchPanel>
        )}
        {run && (
          <>
            <div className={styles.traceHeader}>
              <span>
                {run.name} · {run.state}
              </span>
              <span>{run.manifest.suite_id} · 2 repetitions</span>
              <span>Provider calls: {run.provider_calls}</span>
            </div>
            {run.state === 'draft' && (
              <WorkbenchPanel title="Frozen execution plan" note="Explicit start required">
                <div className={styles.panelBody}>
                  <p>{run.manifest.profiles.map((p) => p.label).join(' · ')}</p>
                  <p>
                    {run.manifest.tasks
                      .map((t) => `${t.id}: ${t.possible_points} points`)
                      .join(' · ')}{' '}
                    · 81 points per repetition.
                  </p>
                  <p className={styles.identifier}>Manifest SHA-256 {run.manifest_sha256}</p>
                  <button
                    className={styles.primary}
                    disabled={busy || !canWrite}
                    onClick={() => void execute()}
                  >
                    Run fictional comparison · no paid calls
                  </button>
                </div>
              </WorkbenchPanel>
            )}
            {run.state === 'failed' && (
              <WorkbenchEmpty title="Fictional execution failed">
                No successful score is claimed. Inspect the recorded failure and create a new frozen
                draft after the cause is resolved.
              </WorkbenchEmpty>
            )}
            {run.state === 'completed' && run.result && (
              <>
                {view === 'overview' && (
                  <>
                    <div className={styles.cards}>
                      <WorkbenchMetric
                        label="SCRIPTED PROFILE COMPARISON"
                        value={run.result.profiles.length}
                        note="These are algorithms, not models."
                      />
                      <WorkbenchMetric
                        label="STORED EXECUTION CELLS"
                        value={run.result.cells.length}
                        note="3 profiles × 3 tasks × 2 repetitions"
                      />
                      <WorkbenchMetric
                        label="PAID PROVIDER CALLS"
                        value={run.provider_calls}
                        note="No provider SDK dispatch"
                      />
                      <WorkbenchMetric
                        label="REPORT AUTHORIZATION"
                        value={auth?.state || 'Pending policy check'}
                        note="Authorization is separate from human-verified scoring."
                      />
                    </div>
                    <WorkbenchPanel
                      title="Fictional comparison scores"
                      note="Full frozen suite · arithmetic mean of two repetitions"
                    >
                      <div className={styles.tableWrap}>
                        <table>
                          <thead>
                            <tr>
                              <th>Scripted profile</th>
                              <th>Repetition 1</th>
                              <th>Repetition 2</th>
                              <th>Mean / 81</th>
                              <th>Percent</th>
                            </tr>
                          </thead>
                          <tbody>
                            {run.result.profiles.map((p) => (
                              <tr key={p.profile_id}>
                                <td>{label(p.profile_id)}</td>
                                {p.repetitions.map((r) => (
                                  <td key={r.repetition}>
                                    {r.earned_points} / {r.possible_points}
                                  </td>
                                ))}
                                <td>
                                  {p.mean_points} / {p.possible_points}
                                </td>
                                <td>
                                  {(
                                    (Number(p.mean_points) / Number(p.possible_points)) *
                                    100
                                  ).toFixed(2)}
                                  %
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </WorkbenchPanel>
                    <div className={styles.grid}>
                      <WorkbenchPanel
                        title="Observed win / tie rate"
                        note="Fictional profiles only · full suite"
                      >
                        <div className={styles.panelBody}>
                          {run.result.ranking.observed_win_rate.rows.map((r) => (
                            <p key={r.profile_id}>
                              {label(r.profile_id)}: <strong>{r.percent}%</strong> · {r.wins} wins /{' '}
                              {r.ties} ties / {r.losses} losses · {r.matchups} matchups
                            </p>
                          ))}
                        </div>
                      </WorkbenchPanel>
                      <WorkbenchPanel title="Bradley–Terry" note="Separate fit · full frozen suite">
                        <div className={styles.panelBody}>
                          <p>{run.result.ranking.bradley_terry.status}</p>
                          <p>{run.result.ranking.bradley_terry.reason}</p>
                          {run.result.ranking.bradley_terry.rows.map((r) => (
                            <p key={r.profile_id}>
                              #{r.rank} {label(r.profile_id)} · relative strength{' '}
                              {r.relative_strength}
                            </p>
                          ))}
                        </div>
                      </WorkbenchPanel>
                    </div>
                    <WorkbenchPanel
                      title="Execution registry"
                      note="Filters narrow evidence, not the full-suite score above"
                    >
                      {table(cells)}
                    </WorkbenchPanel>
                  </>
                )}
                {view === 'trace' && (
                  <>
                    {selected ? (
                      <>
                        <div className={styles.traceHeader}>
                          <span>{label(selected.profile_id)}</span>
                          <span>
                            {selected.task_id} · repetition {selected.repetition + 1}
                          </span>
                          <span>
                            {selected.earned_points} / {selected.possible_points}
                          </span>
                        </div>
                        <div className={styles.grid}>
                          <WorkbenchPanel
                            title="Actual execution evidence"
                            note="Persisted outputs, not sample responses"
                          >
                            <div className={styles.panelBody}>
                              {selected.steps.map((s, i) => (
                                <pre className={styles.code} key={i}>
                                  {JSON.stringify(s, null, 2)}
                                </pre>
                              ))}
                              <h4>answers.json</h4>
                              <pre className={styles.code}>
                                {JSON.stringify(selected.outputs.answers_json, null, 2)}
                              </pre>
                              <h4>report.md</h4>
                              <pre className={styles.code}>{selected.outputs.report_md}</pre>
                              <p className={styles.identifier}>
                                Output SHA-256 {selected.output_sha256}
                              </p>
                            </div>
                          </WorkbenchPanel>
                          <WorkbenchPanel
                            title="Deterministic criterion results"
                            note="No LLM judge"
                          >
                            <div className={styles.tableWrap}>
                              <table>
                                <thead>
                                  <tr>
                                    <th>Criterion</th>
                                    <th>Points</th>
                                    <th>Check</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {selected.criteria.map((c) => (
                                    <tr key={c.id}>
                                      <td>{c.id}</td>
                                      <td>
                                        {c.earned_points}/{c.possible_points}
                                      </td>
                                      <td>{c.passed ? 'Passed' : 'Arithmetic mismatch'}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </WorkbenchPanel>
                        </div>
                      </>
                    ) : (
                      <WorkbenchEmpty title="Select an execution">
                        Choose an actual cell below.
                      </WorkbenchEmpty>
                    )}
                    <details className={styles.traceSelector} open={!selected}>
                      <summary>Choose execution · {cells.length} matching cells</summary>
                      {table(cells)}
                    </details>
                  </>
                )}
                {view === 'failures' && (
                  <>
                    <div className={styles.cards}>
                      <WorkbenchMetric
                        label="FICTIONAL CONTROL MISMATCHES"
                        value={failures.length}
                        note={`${cells.length} matching scripted cells. Not model failures.`}
                      />
                      <WorkbenchMetric
                        label="SCRIPTED MISMATCH RATE"
                        value={
                          cells.length
                            ? ((100 * failures.length) / cells.length).toFixed(2) + '%'
                            : 'Unavailable'
                        }
                        note="Explicit arithmetic checks, not inferred hallucinations."
                      />
                      <WorkbenchMetric
                        label="JUDGE / LOGPROBS"
                        value="Not run"
                        note="No supported judge or likelihood observations."
                      />
                    </div>
                    <WorkbenchPanel
                      title="Profile × task mismatch counts"
                      note="Actual failed cells"
                    >
                      <div className={styles.tableWrap}>
                        <table>
                          <thead>
                            <tr>
                              <th>Profile</th>
                              {run.manifest.tasks.map((t) => (
                                <th key={t.id}>{t.id}</th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {run.manifest.profiles
                              .filter((p) => !query.get('profile') || query.get('profile') === p.id)
                              .map((p) => (
                                <tr key={p.id}>
                                  <td>{p.label}</td>
                                  {run.manifest.tasks.map((t) => (
                                    <td key={t.id}>
                                      {
                                        failures.filter(
                                          (c) => c.profile_id === p.id && c.task_id === t.id,
                                        ).length
                                      }
                                    </td>
                                  ))}
                                </tr>
                              ))}
                          </tbody>
                        </table>
                      </div>
                    </WorkbenchPanel>
                    <WorkbenchPanel title="Inspect a mismatch" note="No root cause is invented">
                      {table(failures)}
                    </WorkbenchPanel>
                  </>
                )}
                {view === 'remediation' && (
                  <>
                    <WorkbenchPanel
                      title="Draft a regression anchor"
                      note="Human-authored expected output required"
                    >
                      <div className={styles.panelBody}>
                        <p>
                          Select a stored cell. Saving creates an unbound fictional draft in the
                          existing golden registry; it is not verified and cannot change scoring or
                          source authority.
                        </p>
                        <select
                          aria-label="Rehearsal cell for draft"
                          value={selected?.id || ''}
                          onChange={(e) =>
                            router.push(link(view, { cell_id: e.target.value || null }))
                          }
                        >
                          <option value="">Select execution</option>
                          {cells.map((c) => (
                            <option key={c.id} value={c.id}>
                              {label(c.profile_id)} · {c.task_id} · repetition {c.repetition + 1}
                            </option>
                          ))}
                        </select>
                        {selected && (
                          <form
                            className={styles.form}
                            onSubmit={(e) => {
                              e.preventDefault();
                              void draft();
                            }}
                          >
                            <label className={styles.field}>
                              Dataset name
                              <input
                                required
                                maxLength={160}
                                value={datasetName}
                                onChange={(e) => setDatasetName(e.target.value)}
                              />
                            </label>
                            <label className={styles.field}>
                              Draft title
                              <input
                                required
                                maxLength={160}
                                value={draftTitle}
                                onChange={(e) => setDraftTitle(e.target.value)}
                              />
                            </label>
                            <label className={styles.field}>
                              Human-authored rationale
                              <textarea
                                required
                                minLength={10}
                                value={draftReason}
                                onChange={(e) => setDraftReason(e.target.value)}
                              />
                            </label>
                            <label className={styles.field}>
                              Human-authored expected output
                              <textarea
                                required
                                value={expected}
                                onChange={(e) => setExpected(e.target.value)}
                              />
                            </label>
                            <button disabled={busy || !canWrite}>
                              Save unverified golden draft
                            </button>
                          </form>
                        )}
                        <a href={route + '/benchmarks/remediation'}>
                          Inspect saved golden versions and proposals ↗
                        </a>
                      </div>
                    </WorkbenchPanel>
                    <WorkbenchPanel
                      title="Reports and review policy"
                      note="Exact-result authorization"
                    >
                      <div className={styles.panelBody}>
                        <p>
                          Report state: {auth?.state || 'Pending'} · required reviewers:{' '}
                          {auth?.required_reviewers ?? 'Unavailable'} · completed:{' '}
                          {auth?.completed_reviewers ?? 0}
                        </p>
                        {canAdmin && auth && !auth.ready && (
                          <form
                            className={styles.form}
                            onSubmit={(e) => {
                              e.preventDefault();
                              void act(async () => {
                                await benchmarkPost(
                                  base,
                                  '/rehearsals/' + run.id + '/report-approval',
                                  { expected_result_sha256: run.result!.result_sha256, rationale },
                                );
                                await load();
                              });
                            }}
                          >
                            <label className={styles.field}>
                              Admin approval rationale
                              <textarea
                                required
                                minLength={10}
                                value={rationale}
                                onChange={(e) => setRationale(e.target.value)}
                              />
                            </label>
                            <button disabled={busy}>Approve this exact report as Admin</button>
                          </form>
                        )}
                        {!canAdmin && auth && !auth.ready && (
                          <form
                            className={styles.form}
                            onSubmit={(e) => {
                              e.preventDefault();
                              void act(async () => {
                                await benchmarkPost(
                                  base,
                                  '/rehearsals/' + run.id + '/report-review',
                                  {
                                    expected_result_sha256: run.result!.result_sha256,
                                    assignment_id: reviewAssignment,
                                    human_reviewed: humanInspected,
                                    rationale,
                                  },
                                );
                                await load();
                                setHumanInspected(false);
                              });
                            }}
                          >
                            <label className={styles.field}>
                              Current report reviewer assignment
                              <input
                                required
                                value={reviewAssignment}
                                onChange={(e) => setReviewAssignment(e.target.value)}
                              />
                            </label>
                            <label className={styles.field}>
                              Reviewer rationale
                              <textarea
                                required
                                minLength={10}
                                maxLength={2000}
                                value={rationale}
                                onChange={(e) => setRationale(e.target.value)}
                              />
                            </label>
                            <label>
                              <input
                                type="checkbox"
                                required
                                checked={humanInspected}
                                onChange={(e) => setHumanInspected(e.target.checked)}
                              />
                              I personally inspected this exact fictional result.
                            </label>
                            <button disabled={busy || !canWrite || !humanInspected}>
                              Record my report review
                            </button>
                            <p>
                              A current distinct project-wide reviewer duty is required. No duty is
                              created by this form.
                            </p>
                          </form>
                        )}
                        <p>
                          Exports include fictional provenance and authorization basis. No private
                          expected output or fabricated judge result is included.
                        </p>
                        {['executive', 'technical'].map((template) => (
                          <a
                            className={styles.button}
                            key={template}
                            aria-disabled={!auth?.ready}
                            href={
                              auth?.ready
                                ? '/api/v1' +
                                  base +
                                  '/workspace/benchmarks/rehearsals/' +
                                  run.id +
                                  '/report?template=' +
                                  template +
                                  '&expected_result_sha256=' +
                                  run.result?.result_sha256
                                : undefined
                            }
                          >
                            {template === 'executive' ? 'Executive PDF' : 'Technical PDF'}
                          </a>
                        ))}
                      </div>
                    </WorkbenchPanel>
                  </>
                )}
                <p className={styles.identifier}>
                  Result SHA-256 {run.result.result_sha256} · Rehearsal {run.id} · Environment{' '}
                  {run.manifest.environment}
                </p>
              </>
            )}
          </>
        )}
        <WorkbenchPanel
          title="Project report review policy"
          note="Admin-configurable; new runs snapshot this policy"
        >
          <div className={styles.panelBody}>
            <p>
              Admin-run and explicitly Admin-approved reports require no additional report sign-off.
              Source rights, execution qualification and spending gates are separate. Existing run
              policies are not silently rewritten.
            </p>
            {policy && (
              <p>
                Current reviewer count: {policy.required_reviewers} · policy revision{' '}
                {policy.revision}
              </p>
            )}
            {canAdmin ? (
              <form
                className={styles.form}
                onSubmit={(e) => {
                  e.preventDefault();
                  void act(async () => {
                    await benchmarkPost(base, '/report-review-policy', {
                      required_reviewers: Number(count),
                    });
                    await load();
                    setNotice(
                      'Project report policy saved. Existing frozen run policies remain unchanged.',
                    );
                  });
                }}
              >
                <label className={styles.field}>
                  Required report reviewers
                  <input
                    type="number"
                    min={0}
                    max={10}
                    required
                    value={count}
                    onChange={(e) => setCount(e.target.value)}
                  />
                </label>
                <button disabled={busy}>Save Admin report policy</button>
              </form>
            ) : (
              <p>Only an Admin can configure this policy or explicitly approve a report.</p>
            )}
          </div>
        </WorkbenchPanel>
      </div>
    </section>
  );
}
