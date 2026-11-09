import { test, expect } from '@playwright/test';
import { lstatSync, readFileSync, writeFileSync } from 'node:fs';

// Actual owned local OIDC and scripted execution only. No route mocks, seeded
// completed cells, provider dispatch or source/reviewer approvals are used.
test('Admin executes eighteen fictional cells and reopens all four views and exact-result PDF', async ({
  page,
}, testInfo) => {
  const project = process.env.ANVIL_DASHBOARD_PROJECT_ID;
  const username = process.env.ANVIL_REHEARSAL_ADMIN_USERNAME;
  const passwordFile = process.env.ANVIL_REHEARSAL_ADMIN_PASSWORD_FILE;
  test.skip(
    !project || !username || !passwordFile,
    'Explicit isolated synthetic Admin test login required',
  );
  const meta = lstatSync(passwordFile!);
  expect(meta.isFile() && !meta.isSymbolicLink() && !(meta.mode & 0o077)).toBe(true);
  if (process.getuid) expect(meta.uid).toBe(process.getuid());
  await page.goto('/');
  await page.getByRole('link', { name: 'Sign in with Keycloak' }).click();
  await page.locator('#username').fill(username!);
  await page.locator('#password').fill(readFileSync(passwordFile!, 'utf8').trim());
  await page.locator('#kc-login').click();
  await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toBeVisible();
  const route = '/workspace/' + project + '/benchmarks';
  const api = '/api/v1/projects/' + project + '/workspace/benchmarks';
  await page.goto(route + '/rehearsal');
  const workbench = page.getByRole('region', { name: 'Fictional comparison workbench' });
  await expect(workbench).toBeVisible();
  await workbench.getByLabel('Required report reviewers').fill('2');
  const configured = page.waitForResponse(
    (response) =>
      response.url().endsWith('/report-review-policy') && response.request().method() === 'POST',
  );
  await workbench.getByRole('button', { name: 'Save Admin report policy' }).click();
  expect((await configured).status()).toBe(200);
  await expect(workbench).toContainText('Current reviewer count: 2');
  await workbench
    .getByLabel('Comparison name')
    .fill('Independent actual fictional execution ' + Date.now());
  const created = page.waitForResponse(
    (response) => response.url().endsWith('/rehearsals') && response.request().method() === 'POST',
  );
  await workbench.getByRole('button', { name: 'Create fictional comparison', exact: true }).click();
  const createResponse = await created;
  expect(createResponse.status()).toBe(201);
  const draft = (await createResponse.json()).data;
  await expect.poll(() => new URL(page.url()).searchParams.get('rehearsal_id')).toBe(draft.id);
  const completed = page.waitForResponse(
    (response) =>
      response.url().endsWith('/rehearsals/' + draft.id + '/execute') &&
      response.request().method() === 'POST',
  );
  await workbench
    .getByRole('button', { name: 'Run fictional comparison · no paid calls', exact: true })
    .click();
  const executionResponse = await completed;
  expect(executionResponse.status()).toBe(200);
  const saved = (await executionResponse.json()).data;
  expect(saved.state).toBe('completed');
  expect(saved.result.cells).toHaveLength(18);
  expect(
    new Set(
      saved.result.cells.map(
        (cell: any) => cell.profile_id + ':' + cell.task_id + ':' + cell.repetition,
      ),
    ).size,
  ).toBe(18);
  expect(saved.provider_calls).toBe(0);
  expect(saved.model_performance).toBe(false);
  expect(saved.official_primary).toBeNull();
  expect(saved.report_authorization).toMatchObject({
    state: 'admin_run_exempt',
    ready: true,
    required_reviewers: 2,
    completed_reviewers: 0,
    reviewer_verified: false,
    admin_actor_id: saved.created_by,
  });
  const perfect = saved.result.profiles.find(
    (profile: any) => profile.profile_id === 'square-all-v1',
  );
  expect(Number(perfect.mean_points)).toBe(81);
  expect(perfect.possible_points).toBe('81');
  expect(
    saved.result.cells.every(
      (cell: any) =>
        cell.outputs.answers_json &&
        cell.criteria.length > 0 &&
        /^[a-f0-9]{64}$/.test(cell.output_sha256),
    ),
  ).toBe(true);
  await expect(workbench).toContainText('admin_run_exempt');
  await page.reload();
  const reopened = await page.request.get(api + '/rehearsals/' + saved.id);
  expect(reopened.status()).toBe(200);
  expect((await reopened.json()).data.result).toEqual(saved.result);
  for (const title of [
    'Trace & rubric',
    'Failure analysis',
    'Remediation & datasets',
    'Overview & leaderboard',
  ]) {
    await workbench
      .getByRole('navigation', { name: 'Fictional benchmark views' })
      .getByRole('link', { name: title, exact: true })
      .click();
    await expect(workbench.getByRole('heading', { name: title, exact: true })).toBeVisible();
    expect(new URL(page.url()).searchParams.get('rehearsal_id')).toBe(saved.id);
  }
  await page.screenshot({
    path: testInfo.outputPath('fictional-comparison-overview.png'),
    fullPage: true,
  });
  await workbench
    .getByRole('navigation', { name: 'Fictional benchmark views' })
    .getByRole('link', { name: 'Remediation & datasets', exact: true })
    .click();
  const pdf = workbench.getByRole('link', { name: 'Technical PDF', exact: true });
  await expect(pdf).toHaveAttribute(
    'href',
    new RegExp('expected_result_sha256=' + saved.result.result_sha256),
  );
  const download = page.waitForEvent('download');
  await pdf.click();
  const file = await download;
  expect(file.suggestedFilename()).toBe('anvil-fictional-technical.pdf');
  const path = await file.path();
  expect(path).not.toBeNull();
  expect(readFileSync(path!).subarray(0, 4).toString()).toBe('%PDF');
  const stale = await page.request.get(
    api + '/rehearsals/' + saved.id + '/report?expected_result_sha256=' + '0'.repeat(64),
  );
  expect(stale.status()).toBe(409);
  if (process.env.ANVIL_REHEARSAL_DISCOVERY_PATH)
    writeFileSync(
      process.env.ANVIL_REHEARSAL_DISCOVERY_PATH,
      JSON.stringify({
        rehearsal_id: saved.id,
        result_sha256: saved.result.result_sha256,
        manifest_sha256: saved.manifest_sha256,
        admin_actor_id: saved.report_authorization.admin_actor_id,
        cells: 18,
        provider_calls: 0,
        reviewer_decisions: 0,
        official_primary: null,
        model_performance: false,
      }) + '\n',
      { mode: 0o600, flag: 'wx' },
    );
});
