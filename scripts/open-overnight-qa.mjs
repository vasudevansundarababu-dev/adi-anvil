// Open only the owned private QA app, as a labelled synthetic inspection user.
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import https from 'node:https';
import { createHash, X509Certificate } from 'node:crypto';
import { chromium, expect } from '@playwright/test';

const root = '/private/tmp/anvil-overnight-qa-20261110-operator';
const web = 'https://anvil-qa.127.0.0.1.sslip.io:8443';
const auth = 'https://auth-anvil-qa.127.0.0.1.sslip.io:8443';
const pins = new Map([
  ['anvil-qa.127.0.0.1.sslip.io', 'NVn/gFTYr2wA1O/xrSviI1eiNkmbOWkHcI0bQ6tr9uk='],
  ['auth-anvil-qa.127.0.0.1.sslip.io', 'B4HvfpcZmtQspQ/UYVuW6kRRtKsLlxaMalSy90Dk/ko='],
]);
let stage = 'preflight';
let context;
try {
  if (Date.now() >= Date.parse('2026-11-10T18:00:00Z')) throw new Error();
  const ca = fs.readFileSync(path.join(root, 'qa-root-ca.crt'));
  async function get(url) {
    return await new Promise((resolve, reject) => {
      const request = https.get(url, { ca, agent: new https.Agent({ ca }), rejectUnauthorized: true, timeout: 15000 }, response => {
        const certificate = new X509Certificate(response.socket.getPeerCertificate().raw);
        const pin = createHash('sha256').update(certificate.publicKey.export({ type: 'spki', format: 'der' })).digest('base64');
        if (pin !== pins.get(new URL(url).hostname) || response.statusCode !== 200) {
          response.destroy(); reject(new Error()); return;
        }
        let body = '';
        response.setEncoding('utf8');
        response.on('data', chunk => { body += chunk; if (body.length > 65536) response.destroy(new Error()); });
        response.on('end', () => { try { resolve(JSON.parse(body)); } catch { reject(new Error()); } });
        response.on('error', reject);
      });
      request.on('timeout', () => request.destroy(new Error()));
      request.on('error', reject);
    });
  }
  const health = await get(web + '/api/v1/health');
  const discovery = await get(auth + '/realms/anvil-overnight-qa/.well-known/openid-configuration');
  if (health.data.api !== 'ready' || discovery.issuer !== auth + '/realms/anvil-overnight-qa') throw new Error();
  const file = path.join(root, 'browser-synthetic-fixture.json');
  const info = fs.lstatSync(file);
  if (!info.isFile() || info.isSymbolicLink() || info.uid !== os.userInfo().uid || (info.mode & 0o077)) throw new Error();
  if (process.argv.includes('--check')) {
    console.log('Private QA tunnel, certificate pins and sign-in endpoint verified. No browser or model call started.');
    process.exit(0);
  }
  const fixture = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (fixture.origin !== 'synthetic_oidc_protocol_qa_only') throw new Error();
  const role = process.argv.includes('--engineer') ? 'rl-engineer' : 'admin';
  const identity = fixture.users[role];
  if (!identity.username.startsWith('synthetic-qa-')) throw new Error();
  const profile = fs.mkdtempSync(path.join(root, 'inspection-browser-'));
  fs.chmodSync(profile, 0o700);
  const browserEnv = Object.fromEntries(['PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'USER', 'LOGNAME', 'SHELL'].filter(key => process.env[key]).map(key => [key, process.env[key]]));
  stage = 'browser';
  context = await chromium.launchPersistentContext(profile, { channel: 'chrome', headless: process.argv.includes('--smoke'),
    env: browserEnv, viewport: { width: 1440, height: 1000 },
    args: ['--ignore-certificate-errors-spki-list=' + [...pins.values()].join(',')] });
  const page = context.pages()[0] || await context.newPage();
  await page.goto(web + `/workspace/${fixture.project}/environments`);
  await page.getByRole('link', { name: 'Sign in with Keycloak' }).click();
  await page.getByLabel('Username').fill(identity.username);
  await page.getByLabel('Password', { exact: true }).fill(identity.password);
  await page.getByRole('button', { name: 'Sign In', exact: true }).click();
  await expect(page.getByRole('navigation', { name: 'Workspace navigation' })).toBeVisible({ timeout: 30000 });
  await page.goto(web + `/workspace/${fixture.project}/benchmarks?benchmark_run=ed46621a-9f5d-4c57-b36f-96ab4ad16149`);
  await expect(page.getByRole('region', { name: 'Benchmark dashboard' })).toBeVisible();
  console.log('Synthetic QA inspection browser opened. This account does not represent owner approval or model performance.');
  if (process.argv.includes('--smoke')) {
    await context.close();
    console.log('Launcher browser smoke passed; no model calls.');
  } else {
    await context.waitForEvent('close', { timeout: 0 });
  }
} catch {
  if (context) await context.close().catch(() => {});
  console.error(`QA ${stage} check did not complete. Keep the private QA tunnel running; no credentials or certificate settings were changed.`);
  process.exitCode = 1;
}
