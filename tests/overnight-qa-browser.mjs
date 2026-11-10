// QA-only actual browser journeys. No real-account credentials or paid actions.
import fs from 'node:fs';
import path from 'node:path';
import { chromium, expect } from '@playwright/test';

const root = '/private/tmp/anvil-overnight-qa-20261110-operator';
const fixture = JSON.parse(fs.readFileSync(path.join(root, 'browser-synthetic-fixture.json')));
if (fixture.origin !== 'synthetic_oidc_protocol_qa_only') throw new Error('Synthetic QA fixture required');
const web = 'https://anvil-qa.127.0.0.1.sslip.io:8443';
// Trust only these two QA leaf keys, verified against the public QA CA first,
// in this disposable browser process.
// No global trust modification or blanket ignoreHTTPSErrors setting.
const browser = await chromium.launch({ channel: 'chrome', headless: true,
  args: ['--ignore-certificate-errors-spki-list=NVn/gFTYr2wA1O/xrSviI1eiNkmbOWkHcI0bQ6tr9uk=,B4HvfpcZmtQspQ/UYVuW6kRRtKsLlxaMalSy90Dk/ko='] });
const results = [];
try {
  for (const [role, identity] of Object.entries(fixture.users)) {
    const context = await browser.newContext({ acceptDownloads: true });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.name));
    await page.goto(web + `/workspace/${fixture.project}/environments`);
    await page.getByRole('link', { name: 'Sign in with Keycloak' }).click();
    await page.getByLabel('Username').fill(identity.username);
    await page.getByLabel('Password', { exact: true }).fill(identity.password);
    await page.getByRole('button', { name: 'Sign In', exact: true }).click();
    await expect(page.getByRole('navigation', { name: 'Workspace navigation' })).toBeVisible({ timeout: 30000 });
    if (process.env.ANVIL_QA_BROWSER_SCOPE === 'configuration') {
      await page.goto(web + `/workspace/${fixture.project}/tasks`);
      const tasks = await page.evaluate(async project => (await (await fetch(`/api/v1/projects/${project}/workspace/tasks`)).json()).data.items, fixture.project);
      if (tasks.length !== 10) throw new Error('Expected ten exact draft source Tasks');
      await expect(page.getByText(tasks[0].title, { exact: true }).first()).toBeVisible({ timeout: 30000 });
      await page.screenshot({ path: path.join(root, `browser-${role}-tasks.png`), fullPage: true });
      if (role === 'admin') {
        await page.goto(web + `/workspace/${fixture.project}/models`);
        for (const model of ['gpt-6.1-sol', 'gpt-6-luna', 'claude-fable-5-2', 'claude-opus-5-5', 'gemini-4-argon', 'gemini-3.8-flash']) {
          await expect(page.getByText('Overnight QA ' + model, { exact: true }).first()).toBeVisible({ timeout: 30000 });
        }
        await page.screenshot({ path: path.join(root, 'browser-admin-models.png'), fullPage: true });
      }
      results.push({ role, exact_draft_tasks: 10, model_profiles: role === 'admin' ? 6 : 'admin_only', provider_calls: 0 });
      await context.close();
      fs.writeFileSync(path.join(root, 'browser-configuration-public.json'), JSON.stringify({ results, real_owner_acceptance: false }));
      continue;
    }
    await page.goto(web + `/workspace/${fixture.project}/environments`);
    await expect(page.getByRole('heading', { name: 'Environments', exact: true }).last()).toBeVisible();
    await expect(page.locator('select').first().locator('option')).toHaveCount(6, { timeout: 30000 });
    await expect(page.getByText('No environment versions yet. Select a template above.', { exact: true })).toHaveCount(0);
    await page.screenshot({ path: path.join(root, `browser-${role}-environments.png`), fullPage: true });
    await page.goto(web + `/workspace/${fixture.project}/benchmarks`);
    await expect(page.getByRole('region', { name: 'Benchmark dashboard' })).toBeVisible();
    const data = await page.evaluate(async project => {
      const response = await fetch(`/api/v1/projects/${project}/workspace/benchmark`);
      if (!response.ok) throw new Error('Authenticated dashboard request failed');
      return (await response.json()).data;
    }, fixture.project);
    if (data.groups.length !== 5) throw new Error('Expected five imported draft groups');
    const run = role === 'admin' ? 'fb853c89-52ec-4ea8-98a9-080482bb297e' : 'a9603bae-b7fd-43ea-b9a0-65ad93997541';
    await page.goto(web + `/workspace/${fixture.project}/benchmarks?benchmark_run=${run}`);
    const dashboard = page.getByRole('region', { name: 'Benchmark dashboard' });
    const pdf = dashboard.getByRole('button', { name: 'Export PDF', exact: true });
    if (role === 'admin') {
      await expect(pdf).toBeEnabled({ timeout: 30000 });
      for (const name of ['Overview', 'Evaluations', 'Tasks & rubrics', 'Failure modes', 'Safety', 'Remediation', 'Report preview']) {
        await dashboard.getByRole('button', { name, exact: true }).click();
        await expect(pdf).toBeEnabled();
      }
      const download = page.waitForEvent('download');
      await pdf.click();
      await (await download).saveAs(path.join(root, 'browser-admin-report.pdf'));
    } else {
      await expect(dashboard.getByText('12/12 selected executions', { exact: false })).toBeVisible({ timeout: 30000 });
      await expect(pdf).toBeDisabled();
    }
    await page.screenshot({ path: path.join(root, `browser-${role}-benchmarks.png`), fullPage: true });
    if (errors.length) throw new Error('Browser runtime errors: ' + errors.join(','));
    results.push({ role, sign_in: 'passed', environments: 'passed', benchmark_dashboard: 'passed', imported_groups: 5,
      synthetic_identity: true, provider_calls: 0, page_errors: 0, result_views: role === 'admin' ? 7 : 1,
      pdf: role === 'admin' ? 'downloaded' : 'correctly_pending_review' });
    await context.close();
    fs.writeFileSync(path.join(root, 'browser-public.json'), JSON.stringify({ results, tls: 'specific_qa_ca_spki', real_owner_acceptance: false }));
  }
} finally { await browser.close(); }
console.log(JSON.stringify({ actual_browser_journeys: results.length, passed: results.length }));
