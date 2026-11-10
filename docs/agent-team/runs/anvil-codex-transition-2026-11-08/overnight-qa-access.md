# Current QA access

The current verified delivery is [QA-team handoff](qa-team-handoff.md), including accounts, record IDs, expected calculations, source limitations, model results and reset instructions. It supersedes the earlier morning access instructions.

Availability: **November 11, noon Chicago /18:00UTC**, same USD100 infrastructure cap. Cleanup after48-hour retention: November13 /18:00UTC. Paid execution is OFF for initial QA.

Private app: https://anvil-qa.127.0.0.1.sslip.io:8443/workspace/1c08f1bc-17ec-4480-9f56-b99ac2e22744/benchmarks?benchmark_run=6340fb00-5756-4a0e-bcff-d6784c29cf20

On the owner Mac open `scripts/Open Overnight QA.command`; Engineer: `node scripts/open-overnight-qa.mjs --engineer`. Other computers need an agreed private access path.

Accounts: qa-team-admin /qa-team-rl-engineer. Passwords only in owner-only `/private/tmp/anvil-overnight-qa-20261110-operator/QA-private-access.html`; never publish it.
