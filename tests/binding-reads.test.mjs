import assert from 'node:assert/strict';
import test from 'node:test';
import { bindingReads, structuredInputPanel } from '../apps/web/src/lib/bindingReads.ts';

test('read timeout releases the caller even if a read never settles', async () => {
  const controller = new AbortController();
  await assert.rejects(bindingReads(['/bindings', '/options'], () => new Promise(() => {}), controller, 10), /timed out/);
  assert.equal(controller.signal.aborted, true);
});

test('cancelling an obsolete read does not prevent a fresh snapshot', async () => {
  const controller = new AbortController();
  const old = bindingReads(['/old'], () => new Promise(() => {}), controller);
  controller.abort();
  await assert.rejects(old, /cancelled/);
  const result = await bindingReads(['/new'], async (path) => path, new AbortController());
  assert.deepEqual(result, ['/new']);
});

test('failed read aborts siblings and never returns a partial snapshot', async () => {
  const controller = new AbortController();
  await assert.rejects(bindingReads(['/ok', '/bad'], async (path) => {
    if (path === '/bad') throw new Error('denied');
    return 'partial';
  }, controller), /denied/);
  assert.equal(controller.signal.aborted, true);
});

test('Gym-owned dataset upload is visible without an authored default', () => {
  assert.equal(structuredInputPanel({ default_input: null, enabled: true }, false, false), true);
  assert.equal(structuredInputPanel(undefined, false, false), false);
  assert.equal(structuredInputPanel({ default_input: null }, true, false), false);
  assert.equal(structuredInputPanel(undefined, true, true), true);
});
