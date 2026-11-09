import { test, expect, Page } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const metadataPath = process.env.ANVIL_ENVIRONMENT_PREVIEW_METADATA;
const accessPath = process.env.ANVIL_ENVIRONMENT_TEST_ACCESS;
test.skip(
  !metadataPath || !accessPath,
  'Requires an explicitly supplied owned local environment preview and test-only sign-in fixture.',
);

function fixture() {
  const info = JSON.parse(fs.readFileSync(metadataPath!, 'utf8'));
  const access = JSON.parse(fs.readFileSync(accessPath!, 'utf8'));
  if (
    access.kind !== 'synthetic-browser-test-accounts' ||
    access.provider_calls !== 0 ||
    Object.keys(access).some((k) => !['kind', 'provider_calls', 'identities'].includes(k))
  )
    throw new Error(
      'Narrow synthetic browser fixture required; runtime configuration is forbidden',
    );
  if (info.deployment || info.provider_calls !== 0 || !info.url.startsWith('http://127.0.0.1:'))
    throw new Error('Local paid-off preview required');
  return { info, access };
}

async function signIn(page: Page, identity: 'admin-1' | 'rl-engineer') {
  const { info, access } = fixture();
  await expect
    .poll(
      async () => {
        try {
          return (
            await page.request.get(
              `http://127.0.0.1:${info.oidc_port}/realms/anvil/.well-known/openid-configuration`,
            )
          ).status();
        } catch {
          return 0;
        }
      },
      { timeout: 30000 },
    )
    .toBe(200);
  await page.goto(info.url);
  await page.getByRole('link', { name: 'Sign in with Keycloak' }).click();
  await page.getByLabel('Username').fill(identity);
  await page.getByLabel('Password', { exact: true }).fill(access.identities[identity].password);
  await page.getByRole('button', { name: 'Sign In', exact: true }).click();
  await expect(page.getByRole('navigation', { name: 'Workspace navigation' })).toBeVisible();
  await page.goto(info.url);
  await expect(
    page.getByRole('heading', { name: 'Environments', exact: true }).last(),
  ).toBeVisible();
}

test('all six materialized environments expose real tools files reset and evidence', async ({
  page,
}, testInfo) => {
  test.setTimeout(240000);
  const { info } = fixture();
  const matrix = JSON.parse(
    fs.readFileSync(path.join(info.root, 'reference-validation.json'), 'utf8'),
  );
  await signIn(page, 'admin-1');
  expect(await page.getByRole('table').first().getByRole('row').count()).toBeGreaterThanOrEqual(31);
  await page.screenshot({
    path: testInfo.outputPath('six-environment-library-viewport.png'),
    fullPage: false,
  });
  await page.screenshot({
    path: testInfo.outputPath('six-environment-library.png'),
    fullPage: true,
  });
  const operations: Record<string, string> = {
    'BOD-FIN': 'save_analysis',
    'MKT-PHONE': 'create_campaign',
    'MKT-LOCALE': 'render_variant',
    'BNK-KYC': 'request_information',
    'BNK-KYB': 'ownership_paths',
    'BNK-AML': 'record_step',
  };
  for (const template of Object.keys(operations)) {
    const row = matrix.find((r: { template: string }) => r.template === template);
    await page
      .getByRole('button', { name: `Open version ${row.environment_id.slice(0, 8)}`, exact: true })
      .click();
    await page.getByRole('button', { name: 'Register local version', exact: true }).click();
    await expect(page.getByRole('status')).toContainText('Registered local reference');
    await page.getByRole('button', { name: 'Open isolated local instance', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Live component workspace' })).toBeVisible();
    await page
      .getByLabel('Environment operation', { exact: true })
      .selectOption(operations[template]);
    await page.getByRole('button', { name: 'Execute local tool', exact: true }).click();
    await expect(page.getByText(/Ordered tool events · 1 visible/)).toBeVisible();
    const downloading = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Export trusted evidence', exact: true }).click();
    const downloaded = await downloading;
    const target = testInfo.outputPath(`${template}-actual-evidence.json`);
    await downloaded.saveAs(target);
    const captured = JSON.parse(fs.readFileSync(target, 'utf8'));
    expect(captured.content.provider_calls).toBe(0);
    expect(captured.content.model_performance).toBe(false);
    expect(captured.content.events.at(-1).operation).toBe(operations[template]);
    expect(captured.content.events.at(-1).result.status).toBe('ok');
    await page.getByRole('button', { name: 'Reset to pinned data', exact: true }).click();
    await expect(page.getByRole('status')).toContainText('Restored the exact pinned');
    await page.getByRole('button', { name: 'Files', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Actual files' })).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath(`${template}-actual-workspace.png`),
      fullPage: true,
    });
    await page.getByRole('button', { name: 'Close instance', exact: true }).click();
    await expect(page.getByRole('status')).toContainText('Instance closed');
  }
});

test('RL Engineer can automatically build validate and register without another approval queue', async ({
  page,
}) => {
  await signIn(page, 'rl-engineer');
  await page.getByLabel('Environment template', { exact: true }).selectOption('BNK-KYC');
  await page.getByLabel('Environment scenario', { exact: true }).selectOption('complete');
  await page
    .getByRole('textbox', { name: 'Name', exact: true })
    .fill('Browser-created KYC local reference');
  await page
    .getByRole('button', { name: 'Build and validate local environment', exact: true })
    .click();
  await expect(page.getByRole('status')).toContainText('Built locally');
  await page.getByRole('button', { name: 'Register local version', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Registered local reference');
  await expect(
    page.getByText('Cloud and authentic Task readiness are separate.', { exact: false }),
  ).toBeVisible();
});
