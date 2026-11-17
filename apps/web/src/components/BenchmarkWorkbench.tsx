'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { benchmarkGet } from '../lib/benchmark';
import {
  DashboardMetric,
  DashboardSnapshot,
  DashboardTrace,
  DashboardTraceDetail,
  DashboardView,
  dashboardBar,
  dashboardContextLink,
  dashboardNumber,
  dashboardMetricText,
  dashboardQuery,
  dashboardReportLink,
  dashboardViews,
  validateDashboardSnapshot,
  validateDashboardTrace,
} from '../lib/benchmark-dashboard';
import { measuredDuration, recordedCost } from '../lib/benchmark-results';
import {
  WorkbenchAvailability,
  WorkbenchBar,
  WorkbenchEmpty,
  WorkbenchMetric,
  WorkbenchPanel,
  WorkbenchStatus,
} from './BenchmarkWorkbenchUI';
import BenchmarkGoldenWorkbench from './BenchmarkGoldenWorkbench';
import styles from './BenchmarkWorkbench.module.css';

const readable = (value: string) => value.replaceAll('_', ' ');
const moment = (value: string) => new Date(value).toLocaleString();
const metricValue = (metric: DashboardMetric) => dashboardMetricText(metric);

export function DashboardTraceTable({
  traces,
  open,
}: {
  traces: DashboardTrace[];
  open: (trace: DashboardTrace) => void;
}) {
  return traces.length ? (
    <div className={styles.tableWrap}>
      <table>
        <caption>Actual stored observations in the selected context</caption>
        <thead>
          <tr>
            <th>Recorded</th>
            <th>Trace / task</th>
            <th>Model or control</th>
            <th>Observed status</th>
            <th>Evidence</th>
          </tr>
        </thead>
        <tbody>
          {traces.map((trace) => (
            <tr key={trace.id}>
              <td>
                {moment(trace.recorded_at)}
                <small>{trace.environment}</small>
              </td>
              <td>
                <button onClick={() => open(trace)}>{trace.label}</button>
                <small>{trace.task_label}</small>
              </td>
              <td>
                {trace.model_label}
                <small>
                  {trace.kind === 'historical_control'
                    ? 'Historical software control · Non-ranking'
                    : trace.review_state}
                </small>
              </td>
              <td>
                <WorkbenchStatus
                  tone={
                    trace.severity === 'critical' || trace.severity === 'high'
                      ? 'danger'
                      : 'neutral'
                  }
                >
                  {readable(trace.state)}
                </WorkbenchStatus>
                <small>{trace.validity || 'Validity not established'}</small>
                <small>{trace.severity_basis || 'Priority provenance unavailable'}</small>
              </td>
              <td>
                <button onClick={() => open(trace)}>Inspect trace ↗</button>
                <small>
                  {trace.evidence_available
                    ? 'Current evidence access'
                    : 'Access or evidence unavailable'}
                </small>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <WorkbenchEmpty title="No traces in this context">
      Change the filters or qualify the fictional task bank. Missing traces are not replaced with
      sample runs.
    </WorkbenchEmpty>
  );
}

export function BenchmarkOverviewView({
  data,
  selectModel,
  open,
}: {
  data: DashboardSnapshot;
  selectModel: (key: string) => void;
  open: (trace: DashboardTrace) => void;
}) {
  const overview = data.overview;
  const modelName = (key: string) =>
    data.options.models.find((model) => model.key === key)?.label || key;
  return (
    <>
      <div className={styles.cards}>
        <WorkbenchMetric
          label="AUTHORIZED COHORT LEADER"
          value={
            overview.leader ? (
              <>
                {overview.leader.percent}
                <small>%</small>
              </>
            ) : (
              'Unavailable'
            )
          }
          note={overview.leader?.model_id || 'Requires comparable, reviewed original observations.'}
          highlight
        />
        <WorkbenchMetric
          label="AVERAGE AUTHORIZED SCORE"
          value={dashboardNumber(overview.average_score_percent, '%')}
          note="Existing task primary only. Judge scores are separate."
        />
        <WorkbenchMetric
          label="STORED SAMPLE TRACES"
          value={overview.total_traces}
          note={`${overview.model_trace_count} model observations · ${overview.control_trace_count} software controls`}
        />
        <WorkbenchMetric
          label="AUTHORIZED MODEL BINDINGS"
          value={overview.ranked_models}
          note="Not a count of active or reachable provider endpoints."
        />
      </div>
      <div className={styles.grid}>
        <WorkbenchPanel title="Benchmark leaderboard" note="Original task scoring preserved">
          {overview.models.length ? (
            <div className={styles.tableWrap}>
              <table>
                <caption>Reviewed primary and unranked diagnostic observations</caption>
                <thead>
                  <tr>
                    <th>Exact model</th>
                    <th>Task primary</th>
                    <th>Diagnostic</th>
                    <th>Judge / 10</th>
                    <th>Scored cells</th>
                    <th>Duration / cost</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.models.map((model) => (
                    <tr key={model.key}>
                      <td>
                        <button onClick={() => selectModel(model.model_key)}>
                          {model.model_id}
                        </button>
                        <small>{model.provider}</small>
                        <small>Binding {model.model_key.slice(0, 8)}</small>
                        <small>
                          {model.measurement_notice || 'Measurement provenance unavailable'}
                        </small>
                        <small>{model.suite_key}</small>
                      </td>
                      <td>
                        {model.primary
                          ? `${model.primary.earned_points} / ${model.primary.possible_points}`
                          : 'Unavailable'}
                        <small>
                          {model.primary
                            ? `${model.primary.percent}% · ${model.review_state}`
                            : readable(model.review_state)}
                        </small>
                      </td>
                      <td>
                        {model.diagnostic
                          ? `${model.diagnostic.earned_points} / ${model.diagnostic.possible_points}`
                          : 'Unavailable'}
                        <small>
                          {model.diagnostic
                            ? `${model.diagnostic.percent}% · not a ranking`
                            : 'No complete eligible repetition'}
                        </small>
                      </td>
                      <td>
                        {metricValue(model.judge)}
                        <small>{model.judge.reason}</small>
                      </td>
                      <td>
                        {model.scored_cells} / {model.planned_cells}
                        <small>
                          {model.authorized_run_count ?? model.reviewed_run_count ?? 'Unknown'}{' '}
                          authorized / {model.run_count} stored runs ·{' '}
                          {model.reviewed_run_count ?? 0} reviewer-verified
                        </small>
                      </td>
                      <td>
                        {measuredDuration(model.duration_ms)}
                        <small>{recordedCost(model.cost_micro_usd)}</small>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <WorkbenchEmpty title="No eligible model observations">
              The fictional task bank can provide software-conformance evidence. It does not create
              reviewed model results or activate paid providers.
            </WorkbenchEmpty>
          )}
        </WorkbenchPanel>
        <WorkbenchPanel
          title="Observed win rate"
          note={readable(overview.ranking.observed_win_rate.status)}
        >
          {overview.ranking.observed_win_rate.rows.length ? (
            <div className={styles.panelBody}>
              {overview.ranking.observed_win_rate.rows.map((row) => (
                <div key={row.model_key}>
                  <WorkbenchBar
                    label={modelName(row.model_key)}
                    value={dashboardBar(row.percent)}
                    display={row.percent + '%'}
                  />
                  <p className={styles.muted}>
                    {row.wins} wins · {row.ties} ties · {row.losses} losses / {row.matchups}{' '}
                    matchups
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <WorkbenchEmpty title="No eligible head-to-head matchups">
              Only actual matched, reviewed observations contribute. Missing or unreviewed cells
              never produce an invented win rate.
            </WorkbenchEmpty>
          )}
          <p className={styles.metricNote}>
            {overview.ranking.observed_win_rate.method} ·{' '}
            {overview.ranking.observed_win_rate.pair_count} eligible pairs
          </p>
        </WorkbenchPanel>
      </div>
      <div className={styles.equalGrid}>
        <WorkbenchPanel title="Bradley–Terry ranking" note="Separate fitted metric">
          {overview.ranking.bradley_terry.rows.length ? (
            <div className={styles.tableWrap}>
              <table>
                <caption>Relative strength from eligible matched observations</caption>
                <thead>
                  <tr>
                    <th>Rank</th>
                    <th>Model</th>
                    <th>Relative strength</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.ranking.bradley_terry.rows.map((row) => (
                    <tr key={row.model_key}>
                      <td>{row.rank}</td>
                      <td>{modelName(row.model_key)}</td>
                      <td>{row.relative_strength}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <WorkbenchEmpty title={readable(overview.ranking.bradley_terry.status)}>
              {overview.ranking.bradley_terry.reason ||
                'A connected set of eligible matched observations is required before fitting a ranking.'}
            </WorkbenchEmpty>
          )}
          <p className={styles.metricNote}>
            {overview.ranking.bradley_terry.method} · {overview.ranking.bradley_terry.tie_policy} ·{' '}
            {overview.ranking.bradley_terry.pair_count} pairs ·{' '}
            {overview.ranking.bradley_terry.iterations} iterations
          </p>
        </WorkbenchPanel>
        <WorkbenchAvailability
          title="Separate judge score / 10"
          state={metricValue(data.availability.judge)}
          reason={
            data.availability.judge.reason ||
            'No supported, separately approved judge measurement is stored.'
          }
        />
      </div>
      <WorkbenchPanel title="Trace registry" note="Open the same context in the inspector">
        <DashboardTraceTable traces={data.traces} open={open} />
      </WorkbenchPanel>
    </>
  );
}

export function BenchmarkTraceView({
  data,
  selected,
  busy,
  error,
  open,
}: {
  data: DashboardSnapshot;
  selected: DashboardTraceDetail | null;
  busy: boolean;
  error: string;
  open: (trace: DashboardTrace) => void;
}) {
  return (
    <>
      {data.context.trace_id ? (
        <details className={styles.traceSelector}>
          <summary>Change selected trace · {data.traces.length} records</summary>
          <WorkbenchPanel
            title="Select a stored execution trace"
            note={`${data.traces.length} records returned`}
          >
            <DashboardTraceTable traces={data.traces} open={open} />
          </WorkbenchPanel>
        </details>
      ) : (
        <WorkbenchPanel
          title="Select a stored execution trace"
          note={`${data.traces.length} records returned`}
        >
          <DashboardTraceTable traces={data.traces} open={open} />
        </WorkbenchPanel>
      )}
      <div style={{ height: 18 }} />
      {error && (
        <p className={styles.alert} role="alert">
          {error}
        </p>
      )}
      {busy ? (
        <WorkbenchPanel title="Trace inspection">
          <WorkbenchEmpty title="Loading authorized evidence">
            Reading the stored trace and rechecking current evidence access.
          </WorkbenchEmpty>
        </WorkbenchPanel>
      ) : !selected ? (
        <WorkbenchPanel title="Trace inspection">
          <WorkbenchEmpty title="Choose a trace to inspect">
            The inspector follows your selected model, task, period and environment. No generic
            prompt, output or hidden reasoning is substituted.
          </WorkbenchEmpty>
        </WorkbenchPanel>
      ) : (
        <>
          <div className={styles.traceHeader}>
            <span>
              TRACE <strong>{selected.trace.label}</strong>
            </span>
            <span>
              MODEL / CONTROL <strong>{selected.trace.model_label}</strong>
            </span>
            <span>
              DURATION <strong>{measuredDuration(selected.trace.duration_ms)}</strong>
            </span>
            <span>
              STATUS <strong>{readable(selected.trace.state)}</strong>
            </span>
            <span>
              TOKENS <strong>Unavailable</strong>
            </span>
          </div>
          <div className={styles.grid}>
            <WorkbenchPanel
              title="Observable execution timeline"
              note={
                selected.trace.kind === 'historical_control'
                  ? 'Non-model control trial'
                  : 'Stored original attempt'
              }
            >
              {selected.steps.length ? (
                <div className={styles.timeline}>
                  {selected.steps.map((step, index) => (
                    <details className={styles.step} key={step.id} open={index === 0}>
                      <summary>
                        {index + 1}. {step.label} · {readable(step.status)}
                      </summary>
                      <p>{readable(step.kind)}</p>
                      <pre className={styles.code}>{step.content}</pre>
                    </details>
                  ))}
                </div>
              ) : (
                <WorkbenchEmpty title="No observable steps retained">
                  Hidden chain-of-thought is not exposed. Only persisted public actions or
                  explicitly supplied summaries can appear here.
                </WorkbenchEmpty>
              )}
              {selected.outputs.length > 0 && (
                <div className={styles.panelBody}>
                  <h4>Captured public outputs</h4>
                  {selected.outputs.map((output) => (
                    <details key={output.path + output.sha256}>
                      <summary>
                        {output.path} · {output.byte_size} bytes
                      </summary>
                      <p className={styles.identifier}>SHA-256 {output.sha256}</p>
                      {output.text === null ? (
                        <p>No text preview was retained.</p>
                      ) : (
                        <pre className={styles.code}>{output.text}</pre>
                      )}
                    </details>
                  ))}
                </div>
              )}
            </WorkbenchPanel>
            <div>
              <WorkbenchPanel title="Task rubric observations" note="Existing task points">
                {selected.criteria.length ? (
                  <div className={styles.rubric}>
                    {selected.criteria.map((criterion) => (
                      <div key={criterion.criterion_id}>
                        <div className={styles.values}>
                          <strong>{criterion.criterion_id}</strong>
                          <span>
                            {criterion.earned_points} / {criterion.possible_points}
                          </span>
                        </div>
                        <p>Actual stored criterion observation · not a judge /10 score</p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <WorkbenchEmpty title="No public criterion observations retained">
                    No score is inferred from the trace text or a missing rubric.
                  </WorkbenchEmpty>
                )}
              </WorkbenchPanel>
              <div style={{ height: 17 }} />
              <WorkbenchAvailability
                title="G-Eval / judge explanation"
                state={metricValue(selected.judge)}
                reason={
                  selected.judge.reason ||
                  'No separately approved judge evaluation or explanation is stored.'
                }
              />
              <div style={{ height: 17 }} />
              <WorkbenchAvailability
                title="Token likelihood telemetry"
                state={metricValue(selected.logprobs)}
                reason={
                  selected.logprobs.reason ||
                  'No supported logprob telemetry is stored. Likelihood is not factual correctness or hallucination probability.'
                }
              />
            </div>
          </div>
          <div className={styles.panelBody}>
            <p className={styles.identifier}>
              Trace {selected.trace.id} · Source {selected.trace.source_sha256 || 'Not recorded'} ·
              Snapshot {selected.snapshot_sha256}
            </p>
            <p className={styles.muted}>
              {selected.trace.severity_basis || 'No calibrated risk assessment is available.'}
            </p>
            {selected.limitations.map((limitation) => (
              <p className={styles.muted} key={limitation}>
                {limitation}
              </p>
            ))}
          </div>
        </>
      )}
    </>
  );
}

export function BenchmarkFailureView({
  data,
  cluster,
  open,
}: {
  data: DashboardSnapshot;
  cluster: (key: string) => void;
  open: (trace: DashboardTrace) => void;
}) {
  const failures = data.failures;
  return (
    <>
      <div className={styles.cards}>
        <WorkbenchMetric
          label="OBSERVED MODEL ERROR RATE"
          value={dashboardNumber(failures.error_rate_percent, '%')}
          note={`${failures.failed_traces} failures / ${failures.eligible_traces} eligible model traces`}
        />
        <WorkbenchMetric
          label="INFRASTRUCTURE EVENTS"
          value={failures.infrastructure_events}
          note="Reported separately. Operational failures are not model zeroes."
        />
        <WorkbenchMetric
          label="RETRIEVAL NOISE"
          value={metricValue(data.availability.retrieval_noise)}
          note={
            data.availability.retrieval_noise.reason ||
            'Only supported stored retrieval measurements count.'
          }
        />
        <WorkbenchMetric
          label="MULTI-STEP DRIFT"
          value={metricValue(data.availability.multi_step_drift)}
          note={
            data.availability.multi_step_drift.reason ||
            'Only explicitly observed constraint drift is reported.'
          }
        />
      </div>
      <div className={styles.equalGrid}>
        <WorkbenchPanel
          title="Derived failure categories"
          note="Evidence tags, not inferred causes"
        >
          {failures.categories.length ? (
            <div className={styles.taxonomy}>
              {failures.categories.map((category) => (
                <div className={styles.taxon} key={category.key}>
                  <span />
                  <button onClick={() => cluster(category.key)}>{category.label}</button>
                  <span>
                    {category.count} · {category.severity}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <WorkbenchEmpty title="No observed failure categories">
              The absence of tagged observations is not proof that a model or system is
              failure-free.
            </WorkbenchEmpty>
          )}
          <p className={styles.metricNote}>
            {failures.classification_basis || 'Derived classification metadata unavailable.'}{' '}
            {failures.rate_basis || 'Rate basis unavailable.'} {failures.control_traces} software
            control traces are excluded from model error rate and ranking.
          </p>
        </WorkbenchPanel>
        <WorkbenchPanel title="Model × task priority" note="Rule-derived, not calibrated risk">
          {failures.heatmap.length ? (
            <div className={styles.tableWrap}>
              <table>
                <caption>Actual model-task failure counts with derived priority tags</caption>
                <thead>
                  <tr>
                    <th>Model</th>
                    <th>Task</th>
                    <th>Count</th>
                    <th>Severity</th>
                  </tr>
                </thead>
                <tbody>
                  {failures.heatmap.map((cell) => (
                    <tr key={cell.model_key + cell.task_key}>
                      <td>
                        {data.options.models.find((model) => model.key === cell.model_key)?.label ||
                          cell.model_key}
                      </td>
                      <td>
                        {data.options.tasks.find((task) => task.key === cell.task_key)?.label ||
                          cell.task_key}
                      </td>
                      <td>
                        <span className={styles.heat}>{cell.count}</span>
                      </td>
                      <td>{cell.severity}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <WorkbenchEmpty title="Heatmap unavailable">
              There are no eligible model-task failure observations for this selection. No sample
              heatmap is generated.
            </WorkbenchEmpty>
          )}
        </WorkbenchPanel>
      </div>
      <WorkbenchPanel title="Flagged trace registry" note="Drill down without losing the cohort">
        <DashboardTraceTable traces={failures.traces} open={open} />
      </WorkbenchPanel>
    </>
  );
}

function ReportDialog({
  base,
  query,
  snapshot,
  close,
}: {
  base: string;
  query: URLSearchParams;
  snapshot: DashboardSnapshot;
  close: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [template, setTemplate] = useState<'executive' | 'technical'>('executive');
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  useEffect(() => {
    dialog.current?.showModal();
    return () => dialog.current?.close();
  }, []);
  async function download() {
    setBusy(true);
    setError('');
    try {
      const response = await fetch(
        dashboardReportLink(base, query, template, false, snapshot.snapshot_sha256),
        { cache: 'no-store' },
      );
      if (!response.ok) {
        const value = await response.json();
        throw new Error(
          typeof value.error?.message === 'string'
            ? value.error.message
            : 'Report unavailable; refresh the current context and retry.',
        );
      }
      if (!response.headers.get('content-type')?.includes('application/pdf'))
        throw new Error('The server did not return a PDF report.');
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = `anvil-${template}-evaluation.pdf`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      close();
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <dialog
      ref={dialog}
      className={styles.dialog}
      aria-labelledby="benchmark-report-title"
      onCancel={close}
    >
      <header className={styles.panelHead}>
        <h3 id="benchmark-report-title">Generate evaluation report</h3>
        <button type="button" onClick={close} aria-label="Close report dialog">
          ×
        </button>
      </header>
      <div className={styles.form}>
        <p>
          The report binds the selected filters and this exact stored snapshot. Fictional
          provenance, review status and unavailable metrics remain visible.
        </p>
        <label className={styles.field}>
          Report template
          <select
            value={template}
            onChange={(event) => setTemplate(event.target.value as typeof template)}
          >
            <option value="executive">Executive evidence summary</option>
            <option value="technical">Technical trace and provenance report</option>
          </select>
        </label>
        <label className={styles.check}>
          <input type="checkbox" checked={false} disabled readOnly />
          Include raw prompts (unavailable)
        </label>
        <p>
          Raw prompt inclusion is not supported for the current safe evidence store. Private grader
          material and hidden reasoning are never included.
        </p>
        {error && (
          <p role="alert" className={styles.alert}>
            {error}
          </p>
        )}
        <p className={styles.identifier}>Snapshot {snapshot.snapshot_sha256}</p>
      </div>
      <footer className={styles.formFooter}>
        <button type="button" onClick={close}>
          Cancel
        </button>
        <button className={styles.primary} disabled={busy} onClick={() => void download()}>
          {busy ? 'Preparing authorized PDF…' : 'Download PDF report'}
        </button>
      </footer>
    </dialog>
  );
}

export default function BenchmarkWorkbench({
  base,
  route,
  canWrite,
  canAdmin,
  userId,
}: {
  base: string;
  route: string;
  canWrite: boolean;
  canAdmin: boolean;
  userId: string;
}) {
  const pathname = usePathname(),
    search = useSearchParams(),
    router = useRouter();
  const section = pathname.split('/')[4];
  const view: DashboardView =
    section === 'trace' || section === 'failures' || section === 'remediation'
      ? section
      : 'overview';
  const queryString = dashboardQuery(search).toString();
  const query = new URLSearchParams(queryString);
  const [data, setData] = useState<DashboardSnapshot | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  const [detail, setDetail] = useState<DashboardTraceDetail | null>(null),
    [traceBusy, setTraceBusy] = useState(false),
    [traceError, setTraceError] = useState('');
  const [report, setReport] = useState(false);
  useEffect(() => {
    setReport(false);
  }, [queryString]);
  const generation = useRef(0),
    detailGeneration = useRef(0);
  const refresh = useCallback(async () => {
    const request = ++generation.current;
    setBusy(true);
    setError('');
    setDetail(null);
    try {
      const value = await benchmarkGet<DashboardSnapshot>(
        base,
        '/dashboard' + (queryString ? '?' + queryString : ''),
      );
      if (request === generation.current) {
        setData(validateDashboardSnapshot(value));
      }
    } catch (failure) {
      if (request === generation.current) {
        setData(null);
        setError((failure as Error).message);
      }
    } finally {
      if (request === generation.current) setBusy(false);
    }
  }, [base, queryString]);
  useEffect(() => {
    setData(null);
    void refresh();
    return () => {
      generation.current++;
    };
  }, [refresh]);
  const traceId = query.get('trace_id');
  useEffect(() => {
    const request = ++detailGeneration.current;
    setDetail(null);
    setTraceError('');
    if (view !== 'trace' || !traceId || !data) {
      setTraceBusy(false);
      return;
    }
    setTraceBusy(true);
    void benchmarkGet<DashboardTraceDetail>(
      base,
      '/dashboard/traces/' + encodeURIComponent(traceId) + (queryString ? '?' + queryString : ''),
    )
      .then((value) => {
        if (request === detailGeneration.current) {
          if (value.trace.id !== traceId) throw new Error('Trace identity changed');
          validateDashboardTrace(value.trace);
          setDetail(value);
        }
      })
      .catch((failure) => {
        if (request === detailGeneration.current) setTraceError((failure as Error).message);
      })
      .finally(() => {
        if (request === detailGeneration.current) setTraceBusy(false);
      });
    return () => {
      detailGeneration.current++;
    };
  }, [base, traceId, data, queryString, view]);
  function change(values: Record<string, string | string[] | null>, destination = view) {
    router.push(dashboardContextLink(route, destination, search, values));
  }
  function open(trace: DashboardTrace) {
    change(
      {
        trace_id: trace.id,
        ...(trace.run_id && trace.run_id !== query.get('run_id') ? { run_id: trace.run_id } : {}),
      },
      'trace',
    );
  }
  const selectedModels = query.getAll('model');
  const selected = dashboardViews.find((item) => item.id === view)!;
  return (
    <section className={styles.workbench} aria-label="Connected benchmark workbench">
      <div className={styles.topbar}>
        <div className={styles.brand}>
          <span className={styles.brandMark}>A</span>Agent evaluation{' '}
          <small>/ Benchmark intelligence</small>
        </div>
        <span className={styles.status}>Evidence-backed workspace</span>
      </div>
      <nav className={styles.tabs} aria-label="Benchmark views">
        {dashboardViews.map((item, index) => (
          <a
            key={item.id}
            href={dashboardContextLink(route, item.id, search)}
            aria-current={view === item.id ? 'page' : undefined}
          >
            <span>{index + 1}</span>
            {item.label}
          </a>
        ))}
      </nav>
      <div className={styles.body}>
        <header className={styles.heading}>
          <div>
            <p className={styles.eyebrow}>
              Evaluation / {view === 'overview' ? 'Overview' : readable(view)}
            </p>
            <h2>{selected.label}</h2>
            <p>{selected.description}</p>
          </div>
          <div className={styles.actions}>
            <a className={styles.button} href={route + '/benchmarks/rehearsal'}>
              New fictional comparison ↗
            </a>
            <button type="button" disabled={busy} onClick={() => void refresh()}>
              {busy ? 'Refreshing…' : 'Refresh evidence'}
            </button>
            <button className={styles.primary} disabled={!data} onClick={() => setReport(true)}>
              Export report ↗
            </button>
          </div>
        </header>
        <div className={styles.filters} aria-label="Shared benchmark context">
          <label>
            Stored run
            <select
              value={query.get('run_id') || ''}
              onChange={(event) => change({ run_id: event.target.value || null })}
            >
              <option value="">All eligible stored runs</option>
              {Array.from(
                new Set([
                  ...(query.get('run_id') ? [query.get('run_id')!] : []),
                  ...(data?.traces.flatMap((trace) => (trace.run_id ? [trace.run_id] : [])) || []),
                ]),
              ).map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </select>
          </label>
          <label>
            Task / suite
            <select
              value={query.get('task') || 'all'}
              onChange={(event) => change({ task: event.target.value })}
            >
              <option value="all">All available tasks / suites</option>
              {data?.options.tasks
                .filter((task) => task.key !== 'all')
                .map((task) => (
                  <option key={task.key} value={task.key}>
                    {task.label}
                  </option>
                ))}
            </select>
          </label>
          <button
            type="button"
            onClick={() => router.push(dashboardContextLink(route, view, new URLSearchParams()))}
          >
            Reset filters
          </button>
          <div className={styles.modelPicker}>
            <p className={styles.eyebrow}>Models</p>
            <details>
              <summary>
                {selectedModels.length
                  ? `${selectedModels.length} selected model bindings`
                  : 'All available model bindings'}{' '}
                ▾
              </summary>
              <div>
                {data?.options.models.length ? (
                  data.options.models.map((model) => (
                    <label key={model.key}>
                      <input
                        type="checkbox"
                        checked={selectedModels.includes(model.key)}
                        onChange={(event) =>
                          change({
                            model: event.target.checked
                              ? [...selectedModels, model.key]
                              : selectedModels.filter((key) => key !== model.key),
                          })
                        }
                      />
                      {model.label} · {model.provider} · binding {model.key.slice(0, 8)}
                    </label>
                  ))
                ) : (
                  <p className={styles.muted}>
                    No model observations are available. Controls are not model endpoints.
                  </p>
                )}
                {selectedModels.length > 0 && (
                  <button onClick={() => change({ model: null })}>Clear model spotlight</button>
                )}
              </div>
            </details>
          </div>
          <label>
            Evaluation period
            <select
              value={query.get('period') || 'all'}
              onChange={(event) => change({ period: event.target.value })}
            >
              <option value="all">All time</option>
              <option value="7d">Last 7 days · UTC</option>
              <option value="30d">Last 30 days · UTC</option>
            </select>
          </label>
          <label>
            Recorded environment
            <select
              value={query.get('environment') || 'all'}
              onChange={(event) => change({ environment: event.target.value })}
            >
              <option value="all">All recorded environments</option>
              {data?.options.environments
                .filter((environment) => environment.key !== 'all')
                .map((environment) => (
                  <option key={environment.key} value={environment.key}>
                    {environment.label}
                  </option>
                ))}
            </select>
          </label>
        </div>
        {error && (
          <p role="alert" className={styles.alert}>
            {error}
          </p>
        )}
        {busy && (
          <p role="status" className={styles.muted}>
            Loading the actual stored cohort…
          </p>
        )}
        {data ? (
          <>
            <aside className={styles.provenance}>
              <strong>Fictional evidence</strong>
              <span>{data.origin_notice}</span>
            </aside>
            {data.context.score_revision_id && (
              <p className={styles.identifier}>
                Exact score revision: {data.context.score_revision_id}{' '}
                <button onClick={() => change({ score_revision_id: null })}>
                  Use current stored revision
                </button>
              </p>
            )}
            {data.context.cluster && (
              <p className={styles.muted}>
                Trace / linked-case focus: {readable(data.context.cluster)}. Overview and
                failure-rate denominators retain the selected model, task, period and environment
                cohort. <button onClick={() => change({ cluster: null })}>Clear category</button>
              </p>
            )}
            {view === 'overview' && (
              <BenchmarkOverviewView
                data={data}
                selectModel={(model) => change({ model: [model] })}
                open={open}
              />
            )}
            {view === 'trace' && (
              <BenchmarkTraceView
                data={data}
                selected={detail}
                busy={traceBusy}
                error={traceError}
                open={open}
              />
            )}
            {view === 'failures' && (
              <BenchmarkFailureView
                data={data}
                cluster={(key) => change({ cluster: key })}
                open={open}
              />
            )}
            {view === 'remediation' && (
              <BenchmarkGoldenWorkbench
                key={queryString}
                base={base}
                data={data}
                canWrite={canWrite}
                canAdmin={canAdmin}
                userId={userId}
                onStored={() => void refresh()}
              />
            )}
            <details className={styles.panelBody}>
              <summary className={styles.muted}>
                Availability, scope and immutable provenance
              </summary>
              {data.limitations.map((item) => (
                <p className={styles.muted} key={item}>
                  {item}
                </p>
              ))}
              <p className={styles.identifier}>
                Snapshot {data.snapshot_sha256}
                <br />
                Generated {moment(data.generated_at)}
                {data.context.run_id && (
                  <>
                    <br />
                    Run {data.context.run_id}
                  </>
                )}
                {data.context.score_revision_id && (
                  <>
                    <br />
                    Score revision {data.context.score_revision_id}
                  </>
                )}
              </p>
            </details>
          </>
        ) : (
          !busy &&
          !error && (
            <WorkbenchEmpty title="No stored dashboard snapshot">
              Refresh to read the selected project. The interface does not manufacture measurements.
            </WorkbenchEmpty>
          )
        )}
      </div>
      <footer className={styles.footer}>
        <span>
          Task scoring retained · Separate judge metrics · No automatic approvals or paid calls
        </span>
        <a href={route + '/benchmarks/setup'}>Sources, qualification & review gates ↗</a>
      </footer>
      {report && data && (
        <ReportDialog base={base} query={query} snapshot={data} close={() => setReport(false)} />
      )}
    </section>
  );
}
