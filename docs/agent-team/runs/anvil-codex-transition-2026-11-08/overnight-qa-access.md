# Inspect the overnight QA app

Latest owner-authorized QA window: **November 11, noon Chicago (18:00 UTC)**, with the same USD100 infrastructure cap. The dedicated managed credential resources are provisioned and owner keys bound only to the separate model-smoke project. The new initial QA acceptance project is `1c08f1bc-17ec-4480-9f56-b99ac2e22744`, with no provider credentials. The launcher now opens that project by default; `--smoke-results` selects the earlier model-smoke project. Final acceptance records and real provider receipts are documented in the QA-team handoff; historical paragraphs below describe the earlier morning delivery.

Private acceptance URL: https://anvil-qa.127.0.0.1.sslip.io:8443/workspace/1c08f1bc-17ec-4480-9f56-b99ac2e22744/benchmarks . Owner-only account handoff: `/private/tmp/anvil-overnight-qa-20261110-operator/QA-private-access.html` (do not publish or attach to an issue). The launcher verifies the pinned QA root and both HTTPS chains, then admits only the current leaf keys in its separate browser; renewal does not change system trust.

On this Mac, open `scripts/Open Overnight QA.command` from the Anvil checkout. It opens a separate Chrome window using the labelled **Synthetic QA admin** account. It does not change your normal browser profile or global certificate trust. Close that window when finished.

The private app is at:

https://anvil-qa.127.0.0.1.sslip.io:8443/workspace/b3337332-aff7-4041-93f8-6adf9ca276d3/benchmarks?benchmark_run=ed46621a-9f5d-4c57-b36f-96ab4ad16149

This link depends on the existing authenticated QA tunnel on this Mac. It is not a public deployment address. The launcher checks both HTTPS certificate chains and their exact public keys before opening Chrome. If the tunnel or certificate check fails, it stops; it does not disable certificate verification globally.

The inspection account is synthetic. It is not the owner's ADI account and must not stand in for human source review, processing-rights confirmation or paid-run activation. No real owner login is claimed.

Available for inspection:

- Ten published fictional draft Tasks and their original structured-decision packages.
- Six environment templates and retained technical Run evidence.
- Completed Harbor and OpenEnv technical rehearsals, original unscored Task results, and Admin PDF/JSON exports.
- Engineer review gating and linked retry/cancellation evidence.
- Six disconnected model profiles. No provider calls or model-performance results have been produced.

The VM has an automatic stop at **November 10, noon Chicago time (18:00 UTC)**. Compute/network cleanup is scheduled only after the 48-hour retention period. The separate credential secret and service account have not been created; their additional cleanup authorization remains pending.

Launcher verification and actual headless Chrome sign-in smoke both passed. The launcher consumes only its purpose-specific synthetic test fixture and never displays its password or any provider credential.
