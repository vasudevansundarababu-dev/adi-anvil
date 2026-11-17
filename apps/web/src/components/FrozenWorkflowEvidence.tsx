'use client';

export type WorkflowProvenance = {
  source?: { task_id: string; task_version: string; payload_sha256: string };
  authored_steps?: {
    source: string;
    path: string;
    sha256: string;
    node_id: string | null;
    role: string | null;
    authored_role_id: string | null;
    role_kind: string;
    role_source?: string | null;
    role_source_path?: string | null;
    role_source_sha256?: string | null;
  }[];
  skill_mapping_sha256?: string;
  skill_mapping_binding?: { id: string; task_group_id: string; snapshot_sha256: string };
};

export default function FrozenWorkflowEvidence({
  item,
  label,
}: {
  item: WorkflowProvenance;
  label: string;
}) {
  return (
    <details aria-label={label}>
      <summary>{label}</summary>
      <p>
        This is the mapping retained for this execution. Current Project edits do not change it. A
        mapping alone does not establish evaluator qualification or a passing score.
      </p>
      {item.source ? (
        <p style={{ overflowWrap: 'anywhere' }}>
          Task {item.source.task_id} · revision {item.source.task_version} · payload{' '}
          {item.source.payload_sha256}
        </p>
      ) : (
        <p>Task revision provenance was not recorded.</p>
      )}
      {item.authored_steps?.length ? (
        <>
          {item.authored_steps.map((step) => (
            <section key={step.source + ':' + step.path} style={{ overflowWrap: 'anywhere' }}>
              <h5>
                {step.node_id
                  ? 'Authored node: ' + step.node_id
                  : 'Ordered procedure item · no authored node ID'}
              </h5>
              <p>
                Source: {step.source}
                {step.path} · {step.sha256}
              </p>
              <p>
                Responsible step role: {step.role || 'Not recorded'} ·{' '}
                {step.role_kind === 'single_agent_template_runtime_role'
                  ? 'Single-agent template runtime role'
                  : 'Authored graph role'}
                {step.authored_role_id ? ' · authored role ID: ' + step.authored_role_id : ''}
              </p>
              <p>
                Role provenance: {step.role_source || 'Not recorded'}
                {step.role_source_path || ''} · {step.role_source_sha256 || 'No digest recorded'}
              </p>
            </section>
          ))}
          <p style={{ overflowWrap: 'anywhere' }}>
            Mapping digest: {item.skill_mapping_sha256 || 'Not recorded'}
          </p>
          {item.skill_mapping_binding && (
            <p style={{ overflowWrap: 'anywhere' }}>
              Project binding: {item.skill_mapping_binding.id} · snapshot{' '}
              {item.skill_mapping_binding.snapshot_sha256}
            </p>
          )}
        </>
      ) : (
        <p>
          No exact authored workflow mapping was retained. Design labels do not establish an
          authored step binding.
        </p>
      )}
    </details>
  );
}
