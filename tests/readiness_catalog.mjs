import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  UNKNOWN_REASON_TEXT,
  actionLink,
  describeReason,
  explainImportState,
  importStates,
  itemText,
  modelSelectionMessage,
  reasonCatalog,
  runBlockerItems,
  runBlockers,
} from '../apps/web/src/lib/readinessCatalog.ts';

const contract = JSON.parse(
  readFileSync(new URL('../contracts/readiness/reason-codes.v1.json', import.meta.url), 'utf8'),
);
const RAW_CODE = /\b[a-z]+(_[a-z]+)+\b/;

test('every server-produced reason code has a complete catalog entry', () => {
  assert.equal(contract.codes.length, 29);
  for (const code of contract.codes) {
    const entry = reasonCatalog[code];
    assert.ok(entry, 'missing catalog entry: ' + code);
    assert.ok(['package', 'setup', 'admission'].includes(entry.layer), code);
    assert.ok(['engineer', 'admin', 'operator'].includes(entry.fixer), code);
    for (const role of [true, false]) {
      const item = describeReason(code, role);
      assert.ok(item.known && item.text.length > 10, code);
      assert.doesNotMatch(item.text, RAW_CODE, code + ' main text contains a raw code');
      assert.equal(item.diagnostic, null);
    }
  }
});

test('engineers get admin-directed wording for admin and operator fixes', () => {
  for (const code of Object.keys(reasonCatalog)) {
    const engineer = describeReason(code, false);
    if (reasonCatalog[code].fixer === 'admin') {
      assert.match(engineer.text, /\bAdmin\b/, code + ' engineer text must direct to an Admin');
      assert.match(engineer.fixerLabel, /project Admin/);
      assert.match(describeReason(code, true).fixerLabel, /you \(Admin\)/);
    }
    if (reasonCatalog[code].fixer === 'operator') {
      assert.match(engineer.fixerLabel, /Anvil administrator/);
    }
  }
  assert.match(describeReason('credential_missing', false).text, /Ask a project Admin/);
});

test('unknown codes use the generic explanation with only a safe secondary diagnostic', () => {
  const unknown = describeReason('future_gate_added_later', false);
  assert.equal(unknown.text, UNKNOWN_REASON_TEXT);
  assert.equal(unknown.diagnostic, 'future_gate_added_later');
  assert.equal(unknown.known, false);
  const rendered = itemText(unknown);
  assert.ok(rendered.indexOf(UNKNOWN_REASON_TEXT) < rendered.indexOf('Diagnostic code:'));
  for (const unsafe of [
    'x<script>alert(1)</script>',
    'a b',
    'Uppercase_code',
    'a'.repeat(65),
    '1starts_with_digit',
    'sk-live-secret-value',
    'toString',
    '__proto__',
    null,
    42,
    { missing: [] },
  ]) {
    const item = describeReason(unsafe, true);
    assert.equal(item.text, UNKNOWN_REASON_TEXT);
    if (typeof unsafe === 'string' && /^[a-z][a-z0-9_]{0,63}$/.test(unsafe)) {
      assert.equal(item.diagnostic, unsafe);
    } else {
      assert.equal(item.diagnostic, null, String(unsafe));
      assert.ok(!itemText(item).includes(String(unsafe)));
    }
  }
});

test('blocker semantics are unchanged: same count, unknowns block, Admin exception only', () => {
  const readiness = {
    missing: ['admin_run_authorization_required', 'aggregate_api_cap_missing', 'brand_new_gate'],
    models: [
      { model_profile_id: 'm1', model: 'gpt-x', missing: ['credential_missing', 'brand_new_gate'] },
      { model_profile_id: 'm2', missing: [] },
    ],
  };
  const engineer = runBlockerItems(readiness, false);
  const admin = runBlockerItems(readiness, true);
  assert.equal(engineer.length, 5);
  assert.equal(admin.length, 4);
  assert.ok(!admin.some((item) => item.code === 'admin_run_authorization_required'));
  assert.ok(engineer.filter((item) => !item.known).length === 2);
  assert.ok(runBlockers({ missing: ['brand_new_gate'], models: [] }, true).length === 1);
  assert.ok(
    runBlockers({ missing: ['admin_run_authorization_required'], models: [] }, false).length === 1,
  );
  assert.equal(
    runBlockers({ missing: ['admin_run_authorization_required'], models: [] }, true).length,
    0,
  );
  assert.equal(runBlockers({ missing: [], models: [] }, false).length, 0);
  assert.match(runBlockers(readiness, false).join('\n'), /^gpt-x: /m);
});

test('readiness wording makes no score, quality or performance claims', () => {
  const all = [
    ...Object.values(reasonCatalog).flatMap((e) => [e.text, e.engineerText || '']),
    ...Object.values(importStates).flatMap((e) => [e.label, e.reason, e.next]),
    UNKNOWN_REASON_TEXT,
  ].join('\n');
  assert.doesNotMatch(all, /score|quality|perform|benchmark|accura/i);
  assert.match(importStates.ready.reason, /checked separately/);
});

test('the seven approved import states explain reason and next step; others use a fallback', () => {
  const approved = [
    'queued',
    'generating',
    'validating',
    'needs_clarification',
    'generation_failed',
    'validation_failed',
    'ready',
  ];
  assert.deepEqual(Object.keys(importStates).sort(), [...approved].sort());
  for (const state of approved) {
    const explained = explainImportState(state);
    assert.ok(explained.label && explained.reason && explained.next, state);
    assert.doesNotMatch(explained.label + explained.reason + explained.next, RAW_CODE, state);
  }
  for (const state of ['generation_failed', 'validation_failed', 'needs_clarification']) {
    assert.match(explainImportState(state).next, /validation report/);
  }
  assert.equal(explainImportState('generation_failed').tone, 'failed');
  assert.equal(explainImportState('validation_failed').tone, 'failed');
  const other = explainImportState('budget_paused');
  assert.equal(other.label, 'Needs attention');
  assert.doesNotMatch(other.label + other.reason + other.next, RAW_CODE);
  assert.equal(other.diagnostic, 'budget_paused');
  assert.equal(explainImportState('<b>x</b>').diagnostic, null);
});

test('model-selection 409 text replaces raw codes only for the exact server prefix', () => {
  const message = modelSelectionMessage(
    'Select an enabled current model version: model_version_superseded, model_profile_disabled',
  );
  assert.match(message, /newer version of this model/);
  assert.match(message, /disabled for new runs/);
  assert.doesNotMatch(message, /model_version_superseded|model_profile_disabled/);
  assert.match(
    modelSelectionMessage('Select an enabled current model version: future_code'),
    /Diagnostic code: future_code/,
  );
  const injected = modelSelectionMessage(
    'Select an enabled current model version: <img src=x onerror=alert(1)>',
  );
  assert.equal(injected, UNKNOWN_REASON_TEXT);
  assert.equal(modelSelectionMessage('Package not found in this project'), null);
  assert.equal(modelSelectionMessage('select an enabled current model version: x'), null);
});

const TO = {
  workspace: '/workspace/p1',
  configure: '/workspace/p1/execution-groups/new',
  share: '/workspace/p1/execution-groups/g1',
  run: '#execution-group-run',
};
const ADMIN_ONLY_PATHS = /\/(models|frameworks|people|limits)(\/|$|\?)/;

test('every blocker gets exactly one role-safe next-action link', () => {
  const codes = [...Object.keys(reasonCatalog), 'future_gate', 'Bad Code!'];
  for (const code of codes)
    for (const canAdmin of [true, false]) {
      const item = describeReason(code, canAdmin, 'Synthetic model');
      const link = actionLink(item, canAdmin, TO);
      assert.ok(link.label.length > 12 && /^[A-Z]/.test(link.label), code + ' descriptive label');
      assert.doesNotMatch(link.label, RAW_CODE, code + ' label contains a raw code');
      assert.ok(Object.values(TO).some((d) => link.href === d || link.href.startsWith(d + '/')));
      assert.equal(actionLink(item, canAdmin, { ...TO, run: undefined }).href === TO.run, false);
      if (!canAdmin) {
        assert.doesNotMatch(link.href, ADMIN_ONLY_PATHS, code + ' Engineer got Admin-only page');
        assert.notEqual(link.href, TO.run, code + ' Engineer cannot authorize a run');
      }
    }
});

test('next-action destinations match who can fix the blocker', () => {
  const link = (code, canAdmin, to = TO) =>
    actionLink(describeReason(code, canAdmin), canAdmin, to);
  assert.deepEqual(link('credential_missing', true), {
    label: 'Open Models & keys',
    href: '/workspace/p1/models',
  });
  assert.deepEqual(link('credential_missing', false), {
    label: 'Link to this page for a project Admin',
    href: TO.share,
  });
  assert.deepEqual(link('framework_binding_changed_or_unavailable', true), {
    label: 'Open Frameworks & presets',
    href: '/workspace/p1/frameworks',
  });
  assert.equal(link('framework_binding_changed_or_unavailable', false).href, TO.share);
  for (const role of [true, false]) {
    assert.deepEqual(link('aggregate_api_cap_missing', role), {
      label: 'Change run configuration',
      href: TO.configure,
    });
    assert.equal(link('execution_group_not_launched', role).href, '/workspace/p1/execution-groups');
    assert.equal(link('package_agent_admission_missing', role).href, '/workspace/p1/tasks');
    assert.equal(link('provider_task_adapter_not_supported', role).href, TO.configure);
    assert.deepEqual(link('live_dispatch_disabled_in_runtime', role), {
      label: 'Link to this page for your Anvil administrator',
      href: TO.share,
    });
  }
  // Engineers have their own documented path for these Admin-fixed blockers.
  assert.equal(link('initiator_access_revoked', false).href, TO.configure);
  assert.equal(link('model_revoked_or_unavailable', false).href, TO.configure);
  assert.deepEqual(link('admin_run_authorization_required', true), {
    label: 'Go to Run to authorize this run',
    href: '#execution-group-run',
  });
  assert.equal(
    link('admin_run_authorization_required', true, { ...TO, run: undefined }).href,
    TO.configure,
  );
  assert.equal(link('admin_run_authorization_required', false).href, TO.share);
  assert.equal(link('future_gate', false).label, 'Link to this page for a project Admin');
  assert.equal(link('future_gate', true).label, 'Link to this page for your Anvil administrator');
});

test('every Admin-fixed blocker gives an Admin a direct destination, not an escalation', () => {
  for (const [code, entry] of Object.entries(reasonCatalog)) {
    const admin = actionLink(describeReason(code, true), true, TO);
    if (entry.fixer === 'admin') assert.notEqual(admin.href, TO.share, code);
    // Its approved text tells the user to select a supported provider's model.
    if (entry.fixer === 'operator' && code !== 'provider_task_adapter_not_supported')
      assert.equal(admin.href, TO.share, code);
  }
});
