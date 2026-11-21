import assert from 'node:assert/strict';
import test from 'node:test';
import { nativeBindingDraft, nativePreparationDraft } from '../apps/web/src/lib/nativeBindingDraft.ts';

const ref = (kind, target, n = 1) => ({ kind, target,
  id: `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`, sha256: 'a'.repeat(64) });
const previous = { workflow: [ref('framework', 'framework')],
  data: [ref('artifact', 'actor-input'), ref('environment', 'shared-case-data-and-environment')],
  rubric: [ref('evaluator', 'criterion:one'), ref('evaluator', 'criterion:two', 2)],
  policy: [ref('policy_mapping', 'policy')],
  safety: [ref('revision', 'safety')], execution_data: { id: 'saved-input', sha256: 'b'.repeat(64) } };
const receipt = { run_authority: 'not_granted', model_calls: 0, task_count: 2,
  restored_workflow_refs: [ref('package', 'task:one'), ref('package', 'task:two', 2)],
  restored_data_refs: [ref('environment', 'shared-case-data-and-environment')],
  restored_rubric_refs: [ref('evaluator', 'criterion:one'), ref('evaluator', 'criterion:two', 2)] };
const apply = value => nativeBindingDraft(previous, value, ['one', 'two'], ['criterion:one', 'criterion:two']);

test('loads exact references while preserving saved input, policy, safety and framework choices', () => {
  const before = structuredClone(previous);
  const next = apply(receipt);
  assert.deepEqual(previous, before);
  assert.deepEqual(next.workflow, [previous.workflow[0], ...receipt.restored_workflow_refs]);
  assert.deepEqual(next.data, previous.data);
  assert.deepEqual(next.rubric, receipt.restored_rubric_refs);
  for (const key of ['policy', 'safety', 'execution_data']) assert.deepEqual(next[key], previous[key]);
  assert.equal('run_authority' in next, false);
  assert.equal('ready' in next, false);
});

test('B1 adds packages only and rejects changes to B0 non-package selections', () => {
  for (const section of ['data', 'rubric']) {
    const changed = structuredClone(previous); changed[section].pop();
    assert.throws(() => nativeBindingDraft(changed, receipt, ['one', 'two'], ['criterion:one', 'criterion:two']));
  }
  const changed = structuredClone(previous); changed.workflow.push(ref('package', 'task:one', 99));
  assert.throws(() => nativeBindingDraft(changed, receipt, ['one', 'two'], ['criterion:one', 'criterion:two']));
  const next = apply(receipt);
  const projection = value => ({ ...value, workflow: value.workflow.filter(ref => ref.kind !== 'package') });
  assert.deepEqual(projection(next), projection(previous));
});

test('preparation loads exact registered criterion references before input freeze', () => {
  const registered = { id: ref('unused', 'unused').id, binding_count: 2,
    environment_id: ref('environment', 'unused').id, readiness: { software_run: 'ready' },
    manifest: { task_mode: 'reusable_application_workflow', paid_calls: false,
      environment_manifest_sha256: 'a'.repeat(64), evaluators: [
        { kind: 'rubric', requirement: 'C1', configuration_id: ref('evaluator', 'unused').id, configuration_sha256: 'a'.repeat(64) },
        { kind: 'rubric', requirement: 'C2', configuration_id: ref('evaluator', 'unused', 2).id, configuration_sha256: 'a'.repeat(64) },
      ] } };
  const criteria = [{ target: 'criterion:one', criterion_id: 'C1' }, { target: 'criterion:two', criterion_id: 'C2' }];
  const before = { ...previous, workflow: [...previous.workflow, ref('package', 'task:one', 99)], data: [], rubric: [] };
  const next = nativePreparationDraft(before, registered, ['one', 'two'], criteria);
  assert.deepEqual(next.workflow, previous.workflow);
  assert.deepEqual(next.data, receipt.restored_data_refs);
  assert.deepEqual(next.rubric, receipt.restored_rubric_refs);
  for (const key of ['policy', 'safety', 'execution_data']) assert.deepEqual(next[key], previous[key]);
  const changed = structuredClone(registered); changed.manifest.evaluators.pop();
  assert.throws(() => nativePreparationDraft(before, changed, ['one', 'two'], criteria));
  changed.readiness.software_run = 'source_changed';
  assert.throws(() => nativePreparationDraft(before, changed, ['one', 'two'], criteria));
});

test('package additions preserve a non-package reference sharing the task target', () => {
  const before = { ...previous, workflow: [ref('framework', 'task:one'), ...previous.workflow] };
  const next = nativeBindingDraft(before, receipt, ['one', 'two'], ['criterion:one', 'criterion:two']);
  assert.deepEqual(next.workflow.filter(value => value.kind !== 'package'), before.workflow);
  assert.deepEqual(next.workflow, [...before.workflow, ...receipt.restored_workflow_refs]);
});

test('rejects incomplete, wrong-Project, duplicate and corrupted references before changing the draft', () => {
  const changes = [
    value => value.restored_workflow_refs.pop(),
    value => { value.restored_workflow_refs[0].target = 'task:another-project'; },
    value => { value.restored_rubric_refs[1].target = 'criterion:one'; },
    value => { value.restored_data_refs[0].kind = 'policy_mapping'; },
    value => { value.restored_data_refs[0].id = 'invalid'; },
    value => { value.restored_rubric_refs[0].sha256 = 'bad-hash'; },
    value => { value.model_calls = 1; },
    value => { value.run_authority = 'approved'; },
  ];
  for (const change of changes) {
    const value = structuredClone(receipt); change(value);
    assert.throws(() => apply(value));
  }
});

test('copies only binding reference fields from the server receipt', () => {
  const value = structuredClone(receipt);
  value.restored_rubric_refs[0].approved = true;
  value.restored_rubric_refs[0].ready = true;
  assert.deepEqual(apply(value).rubric, receipt.restored_rubric_refs);
});
