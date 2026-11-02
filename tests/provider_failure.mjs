import { test } from 'node:test';
import assert from 'node:assert/strict';
import { providerFailure } from '../apps/web/src/lib/providerFailure.ts';

test('provider failures distinguish service availability from deadlines without claiming cost', () => {
  const unavailable = providerFailure({ provider_evidence: { provider_http_status: 503 } });
  const deadline = providerFailure({ provider_evidence: { provider_http_status: 504 } });
  assert.match(unavailable, /Provider unavailable/);
  assert.match(deadline, /deadline exceeded/);
  for (const message of [unavailable, deadline]) {
    assert.match(message, /unconfirmed/);
    assert.match(message, /reservation remains held/);
    assert.match(message, /No automatic retry/);
  }
});

test('untrusted evidence never leaks messages and malformed metadata stays silent', () => {
  for (const value of [
    null,
    [],
    true,
    'private secret',
    { provider_evidence: [] },
    { provider_evidence: { provider_http_status: '503' } },
    { provider_evidence: { provider_http_status: 200, message: 'private secret' } },
  ]) {
    assert.equal(providerFailure(value), null);
  }
  const message = providerFailure({
    provider_evidence: { provider_http_status: 503, message: 'private secret' },
  });
  assert.ok(!message.includes('private secret'));
});
