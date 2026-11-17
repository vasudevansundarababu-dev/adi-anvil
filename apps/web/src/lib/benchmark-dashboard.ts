import { benchmarkPath } from './benchmark';

export type DashboardView = 'overview' | 'trace' | 'failures' | 'remediation';
export type DashboardMetric = {
  status: string;
  value: string | number | null;
  reason: string | null;
};
export type DashboardScore = { earned_points: string; possible_points: string; percent: string };
export type DashboardTrace = {
  id: string;
  kind: 'comparison_cell' | 'historical_control';
  label: string;
  task_key: string;
  task_label: string;
  model_key: string | null;
  model_label: string;
  run_id: string | null;
  state: string;
  validity: string | null;
  origin: string;
  environment: string;
  recorded_at: string;
  duration_ms: number | null;
  points: DashboardScore | null;
  official: boolean;
  review_state: string;
  failure_tags: string[];
  severity: 'none' | 'low' | 'medium' | 'high' | 'critical';
  severity_basis: string;
  evidence_available: boolean;
  source_sha256: string | null;
};
export type DashboardSnapshot = {
  schema_version: 'anvil-dashboard-v1';
  generated_at: string;
  snapshot_sha256: string;
  context: {
    model: string[];
    task: string;
    period: string;
    environment: string;
    run_id: string | null;
    score_revision_id: string | null;
    trace_id: string | null;
    cluster: string | null;
  };
  options: {
    models: { key: string; label: string; provider: string }[];
    tasks: { key: string; label: string }[];
    environments: { key: string; label: string }[];
  };
  origin_notice: string;
  limitations: string[];
  overview: {
    leader: { model_key: string; model_id: string; percent: string } | null;
    average_score_percent: string | null;
    total_traces: number;
    model_trace_count: number;
    control_trace_count: number;
    ranked_models: number;
    models: {
      key: string;
      model_key: string;
      provider: string;
      model_id: string;
      suite_key: string;
      primary: DashboardScore | null;
      diagnostic: DashboardScore | null;
      review_state: string;
      run_count: number;
      reviewed_run_count: number;
      authorized_run_count?: number;
      reviewer_verified?: boolean;
      authorization_basis?: string[];
      ranking_eligible: boolean;
      measurement_notice: string;
      scored_cells: number;
      planned_cells: number;
      duration_ms: number | null;
      cost_micro_usd: number | null;
      judge: DashboardMetric;
      logprobs: DashboardMetric;
    }[];
    ranking: {
      observed_win_rate: {
        status: string;
        method: string;
        pair_count: number;
        rows: {
          model_key: string;
          wins: number;
          losses: number;
          ties: number;
          matchups: number;
          percent: string;
        }[];
      };
      bradley_terry: {
        status: string;
        method: string;
        tie_policy: string;
        pair_count: number;
        rows: { model_key: string; relative_strength: string; rank: number }[];
        iterations: number;
        reason: string | null;
      };
    };
  };
  traces: DashboardTrace[];
  failures: {
    eligible_traces: number;
    failed_traces: number;
    error_rate_percent: string | null;
    control_traces: number;
    infrastructure_events: number;
    classification_basis: string;
    rate_basis: string;
    categories: { key: string; label: string; count: number; severity: string }[];
    heatmap: { model_key: string; task_key: string; count: number; severity: string }[];
    traces: DashboardTrace[];
  };
  availability: {
    judge: DashboardMetric;
    logprobs: DashboardMetric;
    retrieval_noise: DashboardMetric;
    multi_step_drift: DashboardMetric;
  };
  report: { path: string; raw_prompts_included: false };
  curation: {
    datasets: number;
    case_versions: number;
    verified_cases: number;
    proposals: number;
    blocked_intents: number;
    cases: unknown[];
    proposal_refs: unknown[];
  };
};
export type DashboardTraceDetail = {
  trace: DashboardTrace;
  snapshot_sha256: string;
  steps: { id: string; kind: string; label: string; status: string; content: string }[];
  outputs: { path: string; sha256: string; byte_size: number; text: string | null }[];
  criteria: { criterion_id: string; earned_points: string; possible_points: string }[];
  judge: DashboardMetric;
  logprobs: DashboardMetric;
  limitations: string[];
};

export function validateDashboardTrace(trace: DashboardTrace) {
  if (trace.kind === 'historical_control' && (trace.model_key !== null || trace.official !== false))
    throw Object.assign(new Error('Historical controls cannot be official model observations'), {
      status: 409,
    });
}

export function validateDashboardSnapshot(value: DashboardSnapshot) {
  if (
    value.schema_version !== 'anvil-dashboard-v1' ||
    !/^[a-f0-9]{64}$/.test(value.snapshot_sha256)
  )
    throw Object.assign(new Error('Unsupported or unbound dashboard response'), { status: 409 });
  for (const model of value.overview.models) {
    const authorized = model.authorized_run_count ?? model.reviewed_run_count;
    if (
      model.primary &&
      (!Number.isInteger(authorized) || authorized < 1 || authorized > model.run_count)
    )
      throw Object.assign(
        new Error('Primary scores require an actual report-authorization basis'),
        {
          status: 409,
        },
      );
  }
  if (
    value.overview.leader &&
    !value.overview.models.some(
      (model) =>
        model.model_key === value.overview.leader!.model_key &&
        model.primary !== null &&
        model.ranking_eligible === true,
    )
  )
    throw Object.assign(new Error('A model leader requires eligible reviewed model measurements'), {
      status: 409,
    });
  for (const trace of value.traces) validateDashboardTrace(trace);
  return value;
}
export const dashboardViews: { id: DashboardView; label: string; description: string }[] = [
  {
    id: 'overview',
    label: 'Overview & leaderboard',
    description: 'The cohort, its evidence and comparable observations.',
  },
  {
    id: 'trace',
    label: 'Trace & rubric',
    description: 'Follow observable execution steps to their stored evidence.',
  },
  {
    id: 'failures',
    label: 'Failure analysis',
    description: 'Separate observed model failures from controls and infrastructure.',
  },
  {
    id: 'remediation',
    label: 'Remediation & datasets',
    description: 'Turn reviewed findings into immutable regression anchors.',
  },
];

const contextKeys = new Set([
  'model',
  'task',
  'period',
  'environment',
  'run_id',
  'score_revision_id',
  'trace_id',
  'cluster',
]);
export function dashboardQuery(source: Pick<URLSearchParams, 'forEach'>) {
  const query = new URLSearchParams();
  let legacyRun: string | null = null;
  source.forEach((value, key) => {
    if (key === 'comparison') legacyRun = value;
    if (contextKeys.has(key) && value) query.append(key, value);
  });
  if (!query.has('run_id') && legacyRun) query.set('run_id', legacyRun);
  return query;
}

export function dashboardSnapshotQuery(context: DashboardSnapshot['context']) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(context)) {
    if (value !== null)
      for (const item of Array.isArray(value) ? value : [value]) query.append(key, item);
  }
  return dashboardQuery(query);
}

export function dashboardContextLink(
  route: string,
  view: DashboardView,
  source: Pick<URLSearchParams, 'forEach'>,
  changes: Record<string, string | string[] | null> = {},
) {
  const query = dashboardQuery(source);
  for (const [key, value] of Object.entries(changes)) {
    if (!contextKeys.has(key)) continue;
    query.delete(key);
    if (value !== null)
      for (const item of Array.isArray(value) ? value : [value]) if (item) query.append(key, item);
  }
  if (
    ['model', 'task', 'period', 'environment', 'run_id', 'cluster'].some((key) => key in changes)
  ) {
    if (!('trace_id' in changes)) query.delete('trace_id');
    if (!('cluster' in changes)) query.delete('cluster');
  }
  if ('run_id' in changes && !('score_revision_id' in changes)) query.delete('score_revision_id');
  const suffix = query.toString();
  return (
    route +
    '/benchmarks' +
    (view === 'overview' ? '/evidence' : '/' + view) +
    (suffix ? '?' + suffix : '')
  );
}

export function dashboardReportLink(
  base: string,
  source: Pick<URLSearchParams, 'forEach'>,
  template: 'executive' | 'technical',
  includeRawPrompts: false,
  snapshotSha256?: string,
) {
  const query = dashboardQuery(source);
  query.set('template', template);
  query.set('include_raw_prompts', String(includeRawPrompts));
  if (snapshotSha256) query.set('snapshot_sha256', snapshotSha256);
  return '/api/v1' + benchmarkPath(base) + '/dashboard/report?' + query.toString();
}

export function dashboardNumber(value: string | number | null | undefined, suffix = '') {
  return value === null || value === undefined ? 'Unavailable' : `${value}${suffix}`;
}

export function dashboardMetricText(metric: DashboardMetric) {
  if (metric.value !== null && metric.value !== undefined) return String(metric.value);
  const value = metric.status.replaceAll('_', ' ');
  return value ? value[0].toUpperCase() + value.slice(1) : 'Unavailable';
}

export function dashboardBar(value: string | number | null | undefined) {
  if (value === null || value === undefined) return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) && numeric >= 0 && numeric <= 100 ? numeric : null;
}
