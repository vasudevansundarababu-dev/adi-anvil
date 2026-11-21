import assert from 'node:assert/strict';
import test from 'node:test';
import { policyReviewMatches } from '../apps/web/src/lib/policyReview.ts';

test('policy decision form requires this group exact task revision', () => {
  const tasks = [{ task_id: 'current-task', task_version: 'approved-revision' }];
  assert.equal(policyReviewMatches(tasks, { task_id: 'current-task', revision_id: 'approved-revision' }), true);
  for (const subject of [null, {}, { task_id: 'another-group', revision_id: 'approved-revision' },
    { task_id: 'current-task', revision_id: 'old-revision' }, { task_id: 42, revision_id: 'approved-revision' }]) {
    assert.equal(policyReviewMatches(tasks, subject), false);
  }
  assert.equal(policyReviewMatches([], { task_id: 'current-task', revision_id: 'approved-revision' }), false);
});
