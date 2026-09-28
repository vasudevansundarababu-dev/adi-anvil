import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'tests/e2e',timeout:180000,workers:1,
 reporter:[['list'],['json',{outputFile:'artifacts/test-runs/playwright.json'}]],
 use:{baseURL:'http://127.0.0.1:3202',channel:'chrome',headless:true,screenshot:'only-on-failure',trace:'off'},
 outputDir:'artifacts/test-runs/browser'});
