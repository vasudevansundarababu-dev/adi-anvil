import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';

test('import five tasks, pin a run, and use accessible static help', async ({ page }) => {
  const journey = JSON.parse(readFileSync('artifacts/test-runs/journey.json', 'utf8'));
  await page.goto('/');
  await page.getByRole('link', { name: 'Sign in with Keycloak' }).click();
  await page.locator('#username').fill('researcher');
  const password = readFileSync('.local/demo-accounts.md', 'utf8')
    .split('\n')
    .find((l) => l.startsWith('- researcher:'))!
    .split('`')[1];
  await page.locator('#password').fill(password);
  await page.locator('#kc-login').click();
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();
  await page.goto(`/p/${journey.project_id}/objectives`);
  await page.getByRole('button', { name: 'New objective', exact: true }).click();
  await page.getByRole('button', { name: 'Save draft', exact: true }).click();
  const summary = page.getByRole('alert').filter({ hasText: 'Correct these fields:' });
  await expect(summary).toBeFocused();
  await summary.getByRole('link').first().click();
  await expect(page.locator('#title')).toBeFocused();
  await page.locator('#title').fill('Unsaved synthetic objective');
  await page.getByRole('button', { name: 'Anvil Help', exact: true }).click();
  await page.getByRole('button', { name: 'How do I write a measurable objective?' }).click();
  await page.getByRole('button', { name: 'Collapse help' }).click();
  await expect(page.locator('#title')).toHaveValue('Unsaved synthetic objective');
  await expect(page.getByRole('button', { name: 'Anvil Help', exact: true })).toBeFocused();
  await page.getByRole('button', { name: 'New objective', exact: true }).click();
  const card = page.locator('article').filter({
    has: page.getByRole('heading', { name: journey.objective.content.title, exact: true }),
  });
  await card.getByRole('button', { name: 'Import tasks', exact: true }).click();
  const csv =
    'row_id,question,payload\n' +
    Array.from({ length: 5 }, (_, n) => `csv-${n},Choose within budget,"{""budget"":1000}"`).join(
      '\n',
    );
  await page
    .locator('#task-source')
    .setInputFiles({ name: 'custom.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) });
  await page.getByRole('button', { name: 'Upload and preview', exact: true }).click();
  await expect(page.locator('#map-input')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Publish immutable dataset' })).toBeDisabled();
  await page.locator('#map-external_id').selectOption('row_id');
  await page.locator('#map-instruction').selectOption('question');
  await page.locator('#map-input').selectOption('payload');
  await page.getByRole('button', { name: 'Revalidate mapping' }).click();
  await expect(page.getByRole('button', { name: 'Publish immutable dataset' })).toBeEnabled({
    timeout: 30000,
  });
  await page
    .locator('#task-source')
    .setInputFiles('apps/web/public/examples/synthetic-five-tasks.jsonl');
  await page
    .getByRole('button', { name: 'Upload corrected file to this dataset', exact: true })
    .click();
  await expect(page.getByText(/synthetic-five-tasks.jsonl · SHA-256/)).toBeVisible();
  await expect(page.getByText('5 received · 5 valid · 0 invalid · 0 duplicate rows')).toBeVisible({
    timeout: 30000,
  });
  await page.getByRole('button', { name: 'Anvil Help', exact: true }).click();
  await page.getByRole('button', { name: 'Why is input required?' }).click();
  await page.getByRole('button', { name: 'Focus related field (when visible)' }).last().click();
  await expect(page.locator('#map-input')).toBeFocused();
  await page.locator('#anvil-help-question').fill('Publish this dataset for me');
  await page.getByRole('button', { name: 'Ask', exact: true }).click();
  await expect(page.getByText(/Anvil Help cannot publish or approve/)).toBeVisible();
  await page.getByRole('button', { name: 'Collapse help' }).click();
  await page.getByRole('button', { name: 'Publish immutable dataset', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Dataset version 1 published' })).toBeVisible();
  await page.locator('#dataset-suite').selectOption(journey.suite.id);
  await page.getByRole('button', { name: 'Attach exact version' }).click();
  await page.locator('#dataset-protocol').selectOption(journey.protocol.current_revision_id);
  await page.getByRole('link', { name: 'Configure run', exact: true }).click();
  await expect(page.getByText('5 imported tasks selected')).toBeVisible();
  await page
    .locator('section[aria-label="Configure imported run"]')
    .screenshot({ path: 'artifacts/test-runs/task-import-config.png' });
  await page.getByRole('button', { name: 'Save configured run' }).click();
  await expect(
    page.getByRole('status').filter({ hasText: 'Run configured with immutable dataset binding:' }),
  ).toBeVisible();
  await expect(page.getByText(/Imported dataset version 1 · 5 tasks/).first()).toBeVisible();
});
