// Renders one RL Gym report HTML file to an A4 PDF with headless Chromium (Playwright, already in the repo).
// Usage: node scripts/render-report-pdf.mjs <in.html> <out.pdf> <footer text>
// The page has no network: every request other than the inline document is aborted.
import { chromium } from '@playwright/test';
import { readFileSync } from 'node:fs';

const [input, output, footer] = process.argv.slice(2);
if (!input || !output || !footer) {
  console.error('usage: render-report-pdf.mjs <in.html> <out.pdf> <footer>');
  process.exit(2);
}
const escape = (s) =>
  s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
// Same browser as the repo's Playwright tests: the installed Chrome channel locally, the bundled Chromium otherwise.
async function launch() {
  try {
    return await chromium.launch({
      headless: true,
      channel: process.env.RLGYM_PDF_CHANNEL ?? 'chrome',
    });
  } catch {
    return await chromium.launch({ headless: true });
  }
}
const browser = await launch();
try {
  const context = await browser.newContext({ javaScriptEnabled: false, offline: true });
  const page = await context.newPage();
  await page.route('**/*', (route) => route.abort());
  await page.setContent(readFileSync(input, 'utf8'), { waitUntil: 'load', timeout: 30000 });
  await page.pdf({
    path: output,
    format: 'A4',
    printBackground: true,
    margin: { top: '14mm', bottom: '16mm', left: '12mm', right: '12mm' },
    displayHeaderFooter: true,
    // Running header (shared/BRANDING.md): ADI Labs Forge · RL Gym Evaluation
    headerTemplate:
      '<div style="font-size:7px;width:100%;padding:0 12mm;color:#5d6475;font-family:Helvetica,Arial,sans-serif;letter-spacing:0.08em">ADI Labs Forge · RL Gym Evaluation</div>',
    footerTemplate: `<div style="font-size:7px;width:100%;padding:0 12mm;color:#536779;display:flex;justify-content:space-between;font-family:Helvetica,Arial,sans-serif"><span>${escape(footer)}</span><span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span></div>`,
  });
  console.log(JSON.stringify({ ok: true }));
} finally {
  await browser.close();
}
