import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';

test('modern Benchmarks integrates profiles, recommendations, suite and gap drafts', async ({
  page,
}) => {
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
  await page.goto(`/p/${journey.project_id}/factory`);
  await expect(page).toHaveURL(new RegExp(`/workspace/${journey.project_id}/benchmarks$`));
  await expect(
    page
      .getByRole('navigation', { name: 'Workspace navigation' })
      .getByRole('link', { name: 'Benchmarks', exact: true }),
  ).toHaveAttribute('href', `/workspace/${journey.project_id}/benchmarks`);
  await expect(page.getByRole('heading', { name: 'Benchmarks', exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Executable task candidates' })).toBeVisible();
  await expect(
    page.getByText(/importing one does not register or publish a benchmark/),
  ).toBeVisible();
  await expect(
    page.locator('#factory-objective option').filter({ hasText: journey.objective.content.title }),
  ).toHaveCount(1);
  await page.locator('#factory-objective').selectOption(journey.objective.current_revision_id);
  await page.locator('#factory-tasks').selectOption(journey.suite.content.task_revision_ids);
  await page.getByRole('button', { name: 'Inspect Task Profile', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Confirm Task Profile' })).toBeVisible();
  await page.locator('#factory-subdomain').fill('business-diagnostics');
  await page.getByRole('button', { name: 'Confirm immutable profile', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Confirmed immutable TaskProfile saved');
  await page
    .getByRole('button', { name: 'Register selected tasks in catalog', exact: true })
    .click();
  await expect(page.getByRole('status')).toContainText('Catalog metadata registered');
  await page.getByRole('button', { name: 'Recommend benchmarks', exact: true }).click();
  const recommendations = page.getByRole('region', { name: 'Benchmark recommendations' });
  await expect(recommendations.getByText(/Match score 100%/).first()).toBeVisible();
  await recommendations.locator('input[type=checkbox]').first().check();
  await page
    .locator('#factory-override')
    .fill('Use selected synthetic catalog metadata for local development only.');
  await page.getByRole('button', { name: 'Create Suite draft', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Suite draft saved');
  await page.locator('#factory-capabilities').fill('uncovered-capability');
  await page.getByRole('button', { name: 'Confirm immutable profile', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Confirmed immutable TaskProfile saved');
  await page.getByRole('button', { name: 'Recommend benchmarks', exact: true }).click();
  await page.getByRole('button', { name: 'Create benchmark from gaps', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Benchmark gap draft saved');
  const savedProfile = await page.locator('#factory-saved-profile').inputValue();
  await page.reload();
  await page.locator('#factory-saved-profile').selectOption(savedProfile);
  await expect(page.locator('#factory-capabilities')).toHaveValue('uncovered-capability');
  await page.getByRole('button', { name: 'Anvil Help', exact: true }).click();
  await page.getByRole('button', { name: 'How are benchmark matches ranked?' }).click();
  await expect(page.getByText(/Matching uses hard interface/)).toBeVisible();
  await page.getByRole('button', { name: 'Collapse help' }).click();
  await page.screenshot({ path: 'artifacts/test-runs/benchmark-factory.png', fullPage: true });
});
