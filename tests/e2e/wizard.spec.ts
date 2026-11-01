import { test, expect, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';

// D-SIMPLE: five-step evaluation wizard, one Admin approval, explicit run.
async function login(page: Page, name: string) {
  await page.context().clearCookies();
  await page.goto('/');
  await page.getByRole('link', { name: 'Sign in with Keycloak' }).click();
  await page.locator('#username').fill(name);
  const password = readFileSync('.local/demo-accounts.md', 'utf8')
    .split('\n')
    .find((l) => l.startsWith(`- ${name}:`))!
    .split('`')[1];
  await page.locator('#password').fill(password);
  await page.locator('#kc-login').click();
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();
}

test('five-step wizard, single Admin approval and run', async ({ page }) => {
  const journey = JSON.parse(readFileSync('artifacts/test-runs/journey.json', 'utf8'));
  const title = 'Wizard acceptance ' + Date.now();
  await login(page, 'researcher');
  await page.goto(`/p/${journey.project_id}/evaluations`);
  await expect(page.getByRole('navigation', { name: 'Project areas' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Evaluations', exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'New evaluation', exact: true }).click();
  await page.locator('#ev-title').fill(title);
  await page
    .locator('#ev-hypothesis')
    .fill('Candidates preserve hard budget constraints when recommending options.');
  await page
    .locator('#ev-success')
    .fill('Score at least 70 on every task with no critical constraint violation.');
  await page.getByRole('button', { name: 'Create and continue', exact: true }).click();

  await expect(page.getByRole('heading', { name: 'Step 2 · Research' })).toBeVisible();
  await page.locator('#ev-notes').fill('Earlier fixture runs drifted on long option lists.');
  await page.getByRole('button', { name: 'Add source', exact: true }).click();
  await page.getByLabel('Source 1 name').fill('Internal note');
  await page.getByRole('button', { name: 'Save and continue', exact: true }).click();

  await expect(page.getByRole('heading', { name: 'Step 3 · Import tasks and data' })).toBeVisible();
  await page.locator('input[name="case"][value="STR-001"]').check();
  await page.getByRole('button', { name: 'Save and continue', exact: true }).click();

  await expect(page.getByRole('heading', { name: 'Step 4 · Define the rubric' })).toBeVisible();
  await expect(page.getByText('Total 100%', { exact: true })).toBeVisible();
  await page.locator('#cr-threshold').fill('70');
  await page.getByRole('button', { name: 'Save and continue', exact: true }).click();

  await expect(
    page.getByRole('heading', { name: 'Step 5 · Select benchmark and run' }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'Submit to Admin', exact: true }).click();
  await expect(page.getByText('Submitted to the Admin.')).toBeVisible();

  await login(page, 'admin-1');
  await page.goto(`/p/${journey.project_id}/evaluations`);
  await page
    .locator('article')
    .filter({ has: page.getByRole('heading', { name: title, exact: true }) })
    .getByRole('button', { name: 'Open' })
    .click();
  await page.locator('#rationale').fill('Objective, rubric, task set and data rights reviewed.');
  await page.getByRole('button', { name: 'Approve', exact: true }).click();
  await expect(page.getByText('Approved. The suite is frozen and the run is ready.')).toBeVisible();

  await login(page, 'researcher');
  await page.goto(`/p/${journey.project_id}/evaluations`);
  await page
    .locator('article')
    .filter({ has: page.getByRole('heading', { name: title, exact: true }) })
    .getByRole('button', { name: 'Open' })
    .click();
  await page.getByRole('button', { name: 'Run evaluation', exact: true }).click();
  await expect(page.getByText(/Run launched/)).toBeVisible();
  await page.screenshot({ path: 'artifacts/test-runs/wizard-step5.png', fullPage: true });
});

test('Ask Anvil answers about the current screen', async ({ page }) => {
  const journey = JSON.parse(readFileSync('artifacts/test-runs/journey.json', 'utf8'));
  await login(page, 'researcher');
  await page.goto(`/p/${journey.project_id}/evaluations`);
  await page.getByRole('button', { name: 'Ask Anvil', exact: true }).click();
  const chat = page.getByRole('dialog', { name: 'Ask Anvil' });
  await chat.getByRole('button', { name: 'How are outputs graded?' }).click();
  await expect(chat.locator('.support-turn.assistant')).toContainText('second grader');
  await chat.locator('#support-question').fill('What do I need to fill in on this screen?');
  await chat.getByRole('button', { name: 'Ask', exact: true }).click();
  await expect(chat.locator('.support-turn.assistant')).toHaveCount(2);
  await page.screenshot({ path: 'artifacts/test-runs/ask-anvil.png' });
});
