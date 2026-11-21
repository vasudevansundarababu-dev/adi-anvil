type Ref = { kind: string; id: string; sha256: string; target: string };
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;

function references(values: unknown, kind: string, targets: string[]): Ref[] {
  if (!Array.isArray(values) || !targets.length || new Set(targets).size !== targets.length ||
      values.length !== targets.length || values.some(value => !value ||
        value.kind !== kind || typeof value.id !== 'string' || !uuid.test(value.id) ||
        typeof value.sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(value.sha256) ||
        typeof value.target !== 'string' || !targets.includes(value.target)) ||
      new Set(values.map(value => value.target)).size !== targets.length)
    throw new Error('Prepared binding references do not match this Project.');
  return values.map(value => ({ kind: value.kind, id: value.id, sha256: value.sha256, target: value.target }));
}

function merge(existing: Ref[], incoming: Ref[]): Ref[] {
  const targets = new Set(incoming.map(value => value.target));
  return [...existing.filter(value => !targets.has(value.target)), ...incoming];
}

export function nativePreparationDraft<T extends { workflow: Ref[]; data: Ref[]; rubric: Ref[] }>(
  previous: T, registered: unknown, taskIds: string[],
  criteria: { target: string; criterion_id: string }[],
): T {
  const body = registered as Record<string, unknown>;
  const manifest = body?.manifest as Record<string, unknown> | undefined;
  const readiness = body?.readiness as Record<string, unknown> | undefined;
  if (!body || !manifest || typeof body.id !== 'string' || !uuid.test(body.id) ||
      body.binding_count !== taskIds.length || !taskIds.length || new Set(taskIds).size !== taskIds.length ||
      manifest.task_mode !== 'reusable_application_workflow' || manifest.paid_calls !== false ||
      readiness?.software_run !== 'ready' || !Array.isArray(manifest.evaluators))
    throw new Error('Exact current registered KYC case import required.');
  const library = manifest.evaluators as Record<string, unknown>[];
  const rubric = references(criteria.map(criterion => {
    const found = library.filter(value => value.kind === 'rubric' && value.requirement === criterion.criterion_id);
    if (found.length !== 1) throw new Error('Registered evaluator does not cover an exact authored criterion.');
    return { kind: 'evaluator', id: found[0].configuration_id,
      sha256: found[0].configuration_sha256, target: criterion.target };
  }), 'evaluator', criteria.map(value => value.target));
  const data = references([{ kind: 'environment', id: body.environment_id,
    sha256: manifest.environment_manifest_sha256, target: 'shared-case-data-and-environment' }],
    'environment', ['shared-case-data-and-environment']);
  return { ...previous,
    workflow: previous.workflow.filter(value => value.kind !== 'package' || !taskIds.some(id => value.target === 'task:' + id)),
    data: merge(previous.data, data), rubric: merge(previous.rubric, rubric) };
}

export function nativeBindingDraft<T extends { workflow: Ref[]; data: Ref[]; rubric: Ref[] }>(
  previous: T, response: unknown, taskIds: string[], rubricTargets: string[],
): T {
  const body = response as Record<string, unknown>;
  if (!body || body.run_authority !== 'not_granted' || body.model_calls !== 0 ||
      !taskIds.length || new Set(taskIds).size !== taskIds.length ||
      body.task_count !== taskIds.length)
    throw new Error('Exact non-dispatch package preparation receipt required.');
  function refs(key: string, kind: string, targets: string[]): Ref[] {
    return references(body[key], kind, targets);
  }
  const workflow = refs('restored_workflow_refs', 'package', taskIds.map(id => 'task:' + id));
  const data = refs('restored_data_refs', 'environment', ['shared-case-data-and-environment']);
  const rubric = refs('restored_rubric_refs', 'evaluator', rubricTargets);
  for (const [existing, required] of [[previous.data, data], [previous.rubric, rubric]]) {
    for (const ref of required) {
      const found = existing.filter(value => value.target === ref.target);
      if (found.length !== 1 || found[0].kind !== ref.kind || found[0].id !== ref.id || found[0].sha256 !== ref.sha256)
        throw new Error('Save the registered environment and evaluator selections before binding inputs and preparing packages.');
    }
  }
  if (previous.workflow.some(value => value.kind === 'package' && workflow.some(ref => ref.target === value.target)))
    throw new Error('Start and save a new preparation before replacing existing native packages.');
  // B1 may add packages only. Preserve every other B0 field and array order.
  return { ...previous, workflow: [...previous.workflow, ...workflow] };
}
