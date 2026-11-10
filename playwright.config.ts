import { defineConfig } from '@playwright/test';
const webPort = process.env.ANVIL_TEST_WEB_PORT || '3202';
if (!/^[0-9]+$/.test(webPort) || Number(webPort) < 1024 || Number(webPort) > 65535) {
  throw new Error('ANVIL_TEST_WEB_PORT must be an unprivileged loopback port');
}
export default defineConfig({
  testDir: 'tests/e2e',
  // Retired classic UI journeys remain in Git history; the shipped app is modern-only.
  testIgnore: [
    '**/harbor.spec.ts',
    '**/journey.spec.ts',
    '**/marketing.spec.ts',
    '**/task-import.spec.ts',
    '**/wizard.spec.ts',
  ],
  timeout: 180000,
  workers: 1,
  reporter: [['list'], ['json', { outputFile: 'artifacts/test-runs/playwright.json' }]],
  use: {
    baseURL: `http://127.0.0.1:${Number(webPort)}`,
    ...(process.env.CI ? {} : { channel: 'chrome' }),
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'off',
  },
  outputDir: 'artifacts/test-runs/browser',
});
