import { workspaceApi } from './workspace';

export type BenchmarkBlocker = { code: string; layer: string; fixer: string; action: string };
export type BenchmarkReceipt = {
  receipt_id: string;
  exporter: string;
  bank_id: string;
  bank_version: string;
  manifest_sha256: string;
  source_state: string;
  signature_status: string;
  task_count: number;
  source_classification: string;
  latest_build?: { build_id: string; subject_sha256: string; state: string } | null;
};
export type BenchmarkReadiness = {
  subject_sha256: string;
  ready: boolean;
  state?: string;
  software_qualified?: boolean;
  planned_cells?: number;
  blockers: BenchmarkBlocker[];
};
export type BenchmarkVersion = {
  benchmark_revision_id: string;
  suite_revision_id: string;
  subject_sha256: string;
  build_id: string;
  tasks: {
    task_revision_id: string;
    source_id: string;
    package_id: string;
    qualification_id: string;
    package_sha256: string;
    environment_digest: string;
    tool_schema_sha256: string;
    evaluator_binding_id: string;
    possible_points: number;
    criterion_count: number;
  }[];
};
export type BenchmarkProtocol = {
  protocol_revision_id: string;
  subject_sha256: string;
  state: string;
  protocol: {
    origin: string;
    repetitions: number;
    max_active_trials: number;
    tasks: unknown[];
    slots: unknown[];
  };
};
export type BenchmarkComparison = {
  run_id: string;
  protocol_revision_id: string;
  subject_sha256: string;
  state: string;
  origin: string;
  planned_cells: number;
  cells: {
    cell_id: string;
    task_revision_id: string;
    slot: number;
    repetition: number;
    state: string;
    validity: string | null;
  }[];
  scorecard: {
    complete: boolean;
    origin: string;
    models: {
      slot: number;
      provider: string;
      model_id: string;
      planned: number;
      scored: number;
      completion: 'complete' | 'incomplete';
      primary: { earned_points: string; possible_points: string; percent: string } | null;
      cost: {
        candidate_micro_usd: number | null;
        judge_micro_usd: number | null;
        combined_micro_usd: number | null;
        status: string;
      };
      duration: { median_ms: number | null; samples: number };
    }[];
  } | null;
  blockers: BenchmarkBlocker[];
};
export const benchmarkPath = (base: string) => base + '/workspace/benchmarks';
export async function benchmarkGet<T>(base: string, path = ''): Promise<T> {
  return workspaceApi(benchmarkPath(base) + path);
}
export async function benchmarkPost<T>(base: string, path: string, body: unknown): Promise<T> {
  return workspaceApi(benchmarkPath(base) + path, 'POST', body);
}
export async function uploadBenchmark(
  base: string,
  file: File,
  idempotencyKey: string,
): Promise<BenchmarkReceipt> {
  const csrf =
    document.cookie
      .split('; ')
      .find((v) => v.startsWith('anvil_csrf='))
      ?.split('=')[1] || '';
  const response = await fetch('/api/v1' + benchmarkPath(base) + '/imports', {
    method: 'POST',
    cache: 'no-store',
    body: file,
    headers: {
      'Content-Type': 'application/gzip',
      'X-CSRF-Token': csrf,
      'Idempotency-Key': idempotencyKey,
    },
  });
  const result = await response.json();
  if (!response.ok)
    throw new Error(
      typeof result.error?.message === 'string'
        ? result.error.message
        : 'Benchmark import failed. No execution was started.',
    );
  return result.data;
}
