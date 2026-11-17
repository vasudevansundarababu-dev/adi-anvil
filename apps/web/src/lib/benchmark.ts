import { workspaceApi } from './workspace';

export type BenchmarkBlocker = {
  code: string;
  layer: string;
  fixer: string;
  action: string;
};
export type BenchmarkReceipt = {
  receipt_id: string;
  exporter: string;
  bank_id: string;
  bank_version: string;
  bank_title?: string | null;
  source_owner?: string | null;
  manifest_sha256: string;
  source_state: string;
  signature_status: string;
  task_count: number;
  source_classification: string;
  latest_build?: {
    build_id: string;
    subject_sha256: string;
    state: string;
  } | null;
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
  calibration_sha256: string;
  task_labels?: Record<string, string | null>;
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
export type BenchmarkReviewPolicy = {
  tasks: {
    task_revision_id: string;
    pass_threshold_percent: string;
    critical_criterion_ids: string[];
  }[];
  calibration_sha256: string;
  version?: 1 | 2;
  first_assignment_id?: string;
  second_assignment_id?: string;
  adjudicator_assignment_id?: string;
  reviewer_assignment_ids?: string[];
  sample_percent: 10;
  borderline_percentage_points: 5;
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
  checkpoint_event_seq: number;
  task_labels?: Record<string, string | null>;
  model_slots?: { slot: number; provider: string; model_id: string }[];
  cells: {
    cell_id: string;
    task_revision_id: string;
    slot: number;
    repetition: number;
    state: string;
    validity: string | null;
    reconciled: boolean;
  }[];
  scorecard: {
    profile: string;
    protocol_sha256: string;
    complete: boolean;
    execution_complete: boolean;
    origin: string;
    models: {
      slot: number;
      provider: string;
      model_id: string;
      planned: number;
      scored: number;
      completion: 'complete' | 'incomplete';
      score_complete: boolean;
      diagnostic: {
        earned_points: string;
        possible_points: string;
        included: {
          task_revision_id: string;
          repetition: number;
          earned_points: string;
          raw_earned_points: string;
          possible_points: string;
          evidence_sha256: string;
          hard_constraint_ids: string[];
        }[];
        excluded: {
          task_revision_id: string;
          repetition: number;
          reason: string;
        }[];
        complete_repetition_mean: {
          earned_points: string;
          possible_points: string;
          percent: string;
        } | null;
        complete_repetitions: {
          repetition: number;
          earned_points: string;
          possible_points: string;
          percent: string;
        }[];
      };
      primary: {
        earned_points: string;
        possible_points: string;
        percent: string;
      } | null;
      cost: {
        candidate_micro_usd: number | null;
        judge_micro_usd: number | null;
        combined_micro_usd: number | null;
        status: string;
      };
      duration: { median_ms: number | null; samples: number };
    }[];
    review_requirements?: {
      state: string;
      first_assignment_id?: string;
      second_assignment_id?: string;
      adjudicator_assignment_id?: string;
    };
  } | null;
  blockers: BenchmarkBlocker[];
};
export type BenchmarkStoredScore = {
  score_revision_id: string;
  revision: number;
  projection_sha256: string;
  projection: NonNullable<BenchmarkComparison['scorecard']>;
  review_state: string;
  reviews: number;
};
export const benchmarkPath = (base: string) => base + '/workspace/benchmarks';
export async function benchmarkGet<T>(base: string, path = ''): Promise<T> {
  return workspaceApi(benchmarkPath(base) + path);
}
// Tokens survive a reload when session storage is available. Only an opaque
// token and request hash are stored, never source, scores or credentials.
const operationTokens = new Map<string, string>();
export async function benchmarkPost<T>(base: string, path: string, body: unknown): Promise<T> {
  const endpoint = benchmarkPath(base) + path;
  const signature = endpoint + ':' + JSON.stringify(body);
  let token = operationTokens.get(signature);
  if (!token) {
    const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(signature));
    const key =
      'anvil:benchmark:request:' +
      Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, '0')).join('');
    // Another submit may have resolved the hash while this one was awaiting it.
    token = operationTokens.get(signature);
    try {
      token ||= sessionStorage.getItem(key) || undefined;
    } catch {
      /* Page-local retry tokens still work if storage is unavailable. */
    }
    if (!token) token = crypto.randomUUID();
    try {
      sessionStorage.setItem(key, token);
    } catch {
      /* Do not change the user's browser storage policy. */
    }
    operationTokens.set(signature, token);
  }
  return workspaceApi(endpoint, 'POST', body, undefined, token);
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
