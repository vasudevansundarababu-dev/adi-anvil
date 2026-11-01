export type Metrics = {
  reward: number | null;
  score: number | null;
  scored: number;
  attempts: number;
  passed: number;
  task_failed: number;
  execution_errors: number;
  unknown: number;
  elapsed_seconds: number | null;
  known_cost_micro_usd: number | null;
  cost_complete: boolean;
  reserved_micro_usd: number;
  planned?: number;
  cancelled?: number;
  invalid?: number;
  pending?: number;
  unscorable?: number;
};
export type WorkspaceRun = {
  trial?: number;
  kind?: 'harbor' | 'diagnostic';
  id: string;
  task_id: string;
  task_version: string;
  title: string;
  package_id: string;
  package_sha256: string;
  candidate: string;
  state: string;
  origin: string;
  model: string | null;
  error_code: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  metrics: Metrics;
  comparison_signature: string;
  diagnostics?: Record<string, unknown> | null;
  actor_snapshot?: Record<string, unknown>;
  evaluation_snapshot?: Record<string, unknown>;
  source_sha256?: string;
  source_revision_id?: string;
  trajectory_limitations?: string;
  evidence?: { artifact_id: string; kind: string; sha256: string }[];
  calls?: {
    stage_index: number;
    status: string;
    usage: unknown;
    actual_micro_usd: number | null;
    request_sha256?: string;
    request_id?: string | null;
    created_at?: string;
    finished_at?: string | null;
    actor_context?: string | null;
    output_text?: string | null;
  }[];
};
export type WorkspaceTask = {
  id: string;
  task_id: string;
  task_version: string;
  title: string;
  run_count: number;
  versions: number;
  source_sha256: string;
  created_at?: string;
  last_run_at?: string | null;
  package_built?: boolean;
};
export type Page<T> = { items: T[]; next_cursor: string | null; scope: string };

export async function workspaceApi(path: string, method = 'GET', body?: unknown, version?: number) {
  const csrf =
    document.cookie
      .split('; ')
      .find((v) => v.startsWith('anvil_csrf='))
      ?.split('=')[1] || '';
  const response = await fetch('/api/v1' + path, {
    method,
    cache: 'no-store',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': csrf,
      ...(method === 'GET' ? {} : { 'Idempotency-Key': crypto.randomUUID() }),
      ...(version === undefined ? {} : { 'If-Match': String(version) }),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error?.message || 'Unable to load this workspace');
  return result.data;
}
export const shortId = (value: string) => value.slice(0, 8);
export const money = (value: number | null) =>
  value === null
    ? 'Unknown'
    : new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD',
        maximumFractionDigits: 6,
      }).format(value / 1_000_000);
export const dateTime = (value: string | null) =>
  value ? new Date(value).toLocaleString() : 'Not recorded';
export const synthetic = (run: WorkspaceRun) =>
  ['synthetic_software_verification', 'illustrative', 'native_sdk_mock_verification'].includes(
    run.origin,
  );
export const comparable = (runs: WorkspaceRun[]) =>
  runs.length >= 2 &&
  runs.every(
    (r) =>
      r.origin === runs[0].origin &&
      (r.kind === 'diagnostic' || r.state === 'succeeded') &&
      r.metrics.scored &&
      (r.kind !== 'diagnostic' ||
        ((r.metrics.planned || 0) > 0 &&
          r.metrics.scored === r.metrics.planned &&
          r.metrics.attempts === r.metrics.planned)) &&
      r.comparison_signature === runs[0].comparison_signature,
  );
