import type { DashboardTrace } from './benchmark-dashboard';

export function goldenDraftSource(trace: DashboardTrace | undefined, sourceBuildId: string) {
  if (trace?.kind === 'historical_control')
    return { source_build_id: null, source_anchor: null, source_trace_id: trace.id };
  return {
    source_build_id: sourceBuildId || null,
    source_anchor:
      trace?.kind === 'comparison_cell' && trace.run_id
        ? { run_id: trace.run_id, cell_id: trace.id }
        : null,
    source_trace_id: null,
  };
}

export type GoldenDataset = {
  id: string;
  project_id: string;
  name: string;
  description: string;
  created_by: string;
  created_at: string;
  archived: boolean;
};
export type GoldenVersionContent = {
  case_key: string;
  title: string;
  category: string;
  input_text: string;
  expected_output: string;
  fictional_task_id: 'FX-001' | 'FX-002' | 'FX-003';
  source_anchor: { run_id: string; cell_id: string } | null;
  source_trace_id: string | null;
  historical_source_binding: {
    trace_id: string;
    task_id: string;
    artifact_id: string;
    source_record_sha256: string;
    source_commit: string;
    current_authority: false;
  } | null;
};
export type GoldenVersion = {
  id: string;
  project_id: string;
  dataset_id: string;
  case_key: string;
  revision: number;
  predecessor_id: string | null;
  source_build_id: string | null;
  content: GoldenVersionContent;
  content_sha256: string;
  created_by: string;
  created_at: string;
  status: 'draft' | 'verified' | 'rejected';
  origin: 'original_synthetic_fixture';
  is_task_scoring_authority: false;
  verification: null | {
    id: string;
    decision: string;
    verifier_id: string;
    created_at: string;
    evidence_sha256: string;
  };
  permissions: { can_verify: boolean; verification_blockers: string[] };
};
export type RemediationProposal = {
  id: string;
  project_id: string;
  source_build_id: string | null;
  content: {
    title: string;
    persona: string;
    rationale: string;
    proposed_prompt: string;
    fictional_task_id: string;
    source_anchor: { run_id: string; cell_id: string } | null;
    source_trace_id: string | null;
    offline_only: true;
  };
  content_sha256: string;
  created_by: string;
  created_at: string;
  state: 'proposed';
  auto_applied: false;
  provider_calls: 0;
  run_intents: {
    id: string;
    project_id: string;
    proposal_id: string;
    created_by: string;
    state: 'blocked';
    code: string;
    provider_calls: 0;
    auto_applied: false;
    limits: { max_steps: number; max_output_bytes: number };
    created_at: string;
  }[];
};
export type GoldenPage<T> = { items: T[]; next_cursor: string | null };
