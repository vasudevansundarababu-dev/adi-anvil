export type RehearsalCell = {
  id: string;
  profile_id: string;
  task_id: string;
  repetition: number;
  state: string;
  outputs: { answers_json: Record<string, number>; report_md: string };
  output_sha256: string;
  criteria: { id: string; earned_points: string; possible_points: string; passed: boolean }[];
  earned_points: string;
  possible_points: string;
  duration_ms: number;
  failure_tags: string[];
  steps: Record<string, unknown>[];
};
export type Rehearsal = {
  id: string;
  project_id: string;
  name: string;
  state: 'draft' | 'completed' | 'failed';
  created_by: string;
  created_at: string;
  executed_at: string | null;
  origin: 'fictional_scripted_rehearsal';
  model_performance: false;
  provider_calls: 0;
  official_primary: null;
  manifest_sha256: string;
  manifest: {
    suite_id: string;
    repetitions: number;
    environment: string;
    source_hashes: Record<string, string>;
    profiles: { id: string; label: string; version: string; sha256: string }[];
    tasks: { id: string; possible_points: number; items_sha256: string }[];
  };
  result: null | {
    cells: RehearsalCell[];
    profiles: {
      profile_id: string;
      repetitions: { repetition: number; earned_points: string; possible_points: string }[];
      mean_points: string;
      possible_points: string;
    }[];
    ranking: {
      observed_win_rate: {
        status: string;
        pair_count: number;
        method: string;
        rows: {
          profile_id: string;
          wins: number;
          ties: number;
          losses: number;
          matchups: number;
          percent: string;
        }[];
      };
      bradley_terry: {
        status: string;
        reason: string | null;
        method: string;
        rows: { profile_id: string; rank: number; relative_strength: string }[];
      };
    };
    result_sha256: string;
  };
};

export function rehearsalLink(
  route: string,
  view: string,
  id: string,
  context: URLSearchParams,
  updates: Record<string, string | null> = {},
) {
  const query = new URLSearchParams();
  for (const key of ['profile', 'task', 'period', 'environment', 'cell_id']) {
    const value = context.get(key);
    if (value) query.set(key, value);
  }
  if (id) query.set('rehearsal_id', id);
  for (const [key, value] of Object.entries(updates)) {
    if (value === null) query.delete(key);
    else query.set(key, value);
  }
  return (
    route +
    '/benchmarks' +
    (view === 'overview' ? '' : '/' + view) +
    (query.size ? '?' + query.toString() : '')
  );
}

export function rehearsalCells(run: Rehearsal, query: URLSearchParams) {
  const period = query.get('period') || 'all';
  if (!['all', '7d', '30d'].includes(period)) throw new Error('Unsupported rehearsal period');
  const timestamp = run.executed_at || run.created_at;
  if (
    period !== 'all' &&
    Date.parse(timestamp) < Date.now() - Number(period.slice(0, -1)) * 86400000
  )
    return [];
  if (
    query.get('environment') &&
    query.get('environment') !== 'all' &&
    query.get('environment') !== run.manifest.environment
  )
    return [];
  return (run.result?.cells || []).filter(
    (cell) =>
      (!query.get('profile') || query.get('profile') === cell.profile_id) &&
      (!query.get('task') || query.get('task') === 'all' || query.get('task') === cell.task_id),
  );
}
