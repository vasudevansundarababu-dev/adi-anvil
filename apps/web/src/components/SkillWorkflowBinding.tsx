'use client';

export type StepRef = { source: 'actor' | 'template_execution'; path: string; sha256: string };
export type SkillMapping = { target: string; role: string; steps: StepRef[] };
export type WorkflowStep = StepRef & {
  node_id: string | null;
  label: string;
  instruction_preview?: string;
  role: string | null;
  role_name?: string | null;
  authored_role_id?: string | null;
  role_kind: string;
  role_source?: string | null;
  role_source_path?: string | null;
  role_source_sha256?: string | null;
};
export type TaskStepOptions = {
  task_id: string;
  task_version: string;
  payload_sha256: string;
  steps: WorkflowStep[];
  status: string;
};
const key = (step: StepRef) => step.source + ':' + step.path;

export default function SkillWorkflowBinding({
  skill,
  options,
  value,
  onChange,
}: {
  skill: {
    target: string;
    task_id: string;
    task_version: string;
    payload_sha256: string;
    skill_id: string;
  };
  options?: TaskStepOptions;
  value?: SkillMapping;
  onChange: (mapping: SkillMapping | undefined) => void;
}) {
  const exact =
    options?.task_id === skill.task_id &&
    options?.task_version === skill.task_version &&
    options?.payload_sha256 === skill.payload_sha256;
  const steps = exact ? options!.steps : [];
  const selected = steps.filter((step) =>
    value?.steps.some((ref) => key(ref) === key(step) && ref.sha256 === step.sha256),
  );
  const roles = [
    ...new Set(selected.map((step) => step.role).filter((role): role is string => !!role)),
  ];
  const stale = !!value && selected.length !== value.steps.length;
  return (
    <details>
      <summary>Workflow binding · {value?.steps.length || 0} selected steps</summary>
      <p>
        Choose the actual authored steps that produce evidence for this skill. A saved mapping does
        not establish evaluator or execution qualification.
      </p>
      {!exact && <p>Exact workflow locations for this task revision have not been returned.</p>}
      {exact && !steps.length && <p>No authored workflow locations are available for this task.</p>}
      {stale && (
        <p role="alert">
          The selected workflow reference changed or is unavailable. Choose current source steps
          before saving.
        </p>
      )}
      {steps.map((step) => {
        const checked = selected.some((item) => key(item) === key(step));
        return (
          <div key={key(step)} style={{ margin: '12px 0' }}>
            <label>
              <input
                type="checkbox"
                checked={checked}
                disabled={!step.role}
                aria-label={
                  skill.task_id +
                  ' · ' +
                  skill.skill_id +
                  ' · ' +
                  step.label +
                  ' · ' +
                  (step.node_id || step.path)
                }
                onChange={(event) => {
                  const next = event.target.checked
                    ? [...selected, step]
                    : selected.filter((item) => key(item) !== key(step));
                  if (!next.length) {
                    onChange(undefined);
                    return;
                  }
                  const available = [
                    ...new Set(
                      next.map((item) => item.role).filter((role): role is string => !!role),
                    ),
                  ];
                  const role =
                    value?.role && available.includes(value.role)
                      ? value.role
                      : available.length === 1
                        ? available[0]
                        : '';
                  onChange({
                    target: skill.target,
                    role,
                    steps: next.map((item) => ({
                      source: item.source,
                      path: item.path,
                      sha256: item.sha256,
                    })),
                  });
                }}
              />{' '}
              {step.label}
            </label>
            <small style={{ display: 'block' }}>
              Role: {step.role_name || step.role || 'Not declared'} ·{' '}
              {step.role_kind === 'single_agent_template_runtime_role'
                ? 'Single-agent template runtime role'
                : 'Authored graph role'}
            </small>
            {!step.role && <p>Role provenance is missing; this step cannot yet be bound.</p>}
            <details>
              <summary>Source evidence</summary>
              <p>{step.instruction_preview}</p>
              <p>
                {step.node_id
                  ? 'Authored node ID: ' + step.node_id
                  : 'This ordered procedure item has no authored node ID.'}
              </p>
              <p style={{ overflowWrap: 'anywhere' }}>
                Location: {step.source}
                {step.path} · {step.sha256}
              </p>
              <p style={{ overflowWrap: 'anywhere' }}>
                Role source: {step.role_source || 'Not declared'}
                {step.role_source_path || ''} · {step.role_source_sha256 || 'Not declared'}
              </p>
            </details>
          </div>
        );
      })}
      <label>
        Responsible workflow role
        <select
          aria-label={'Responsible workflow role for ' + skill.task_id + ' · ' + skill.skill_id}
          value={value?.role || ''}
          disabled={!roles.length || stale}
          onChange={(event) => {
            if (value) onChange({ ...value, role: event.target.value });
          }}
        >
          <option value="">Choose a role that owns a selected step</option>
          {roles.map((role) => (
            <option key={role} value={role}>
              {selected.find((step) => step.role === role)?.role_name || role.replaceAll('_', ' ')}
            </option>
          ))}
        </select>
      </label>
      {!!value && <button onClick={() => onChange(undefined)}>Clear workflow mapping</button>}
    </details>
  );
}
