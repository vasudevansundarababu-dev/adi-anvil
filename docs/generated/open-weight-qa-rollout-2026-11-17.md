# Open Weight QA rollout — 17 November 2026

Existing QA only: https://anvil-qa.adi-labs.ai/workspace . Source
`dc9a1441668b8e15a4e3863038ee701173619b06`, Gym source hash
`280e925c934303a541657829164948893f5312183cad209e9d9dcc59eddde3b7`.
GCP build `1412cea1-288a-4790-a4cc-539da655827c` SUCCESS, installed source/policy
checks passed both in Cloud Build and on the actual QA host.

- API, worker, business-worker: backend digest
  `200e67e6f193e6da0bcae58b2be078ba54c52753e2bf2a11f94040bb4189917e`.
- Dedicated software scheduler/grader: kyc-runtime digest
  `963cddc916ff9e3fafd5c944a9211219ba7fea341d425e859d272b5a64137a3b`.
- Web digest `a3542b905e87a3b73a03c97da2313ce05a86bb5a348206c4a9b6f5eaa647d550`.
- Marketing runtime published digest
  `90d4338501fe4134a8a5dfc9a71ec5b77ae86e4e8ec3544507a11b768dcc523d`;
  publication/package controls are not native activation.

Passed final1064 units +10 subtests;28 actual fresh/repeated PostgreSQL KYC/
Marketing software checks with unchanged source hash; fresh/repeated128 and actual
HF bulk32/shared-token/RLS/rotation/revocation/immutable-binding checks; one real
Chrome UI journey using clearly synthetic local API responses; types/production
frontend build and scoped lint/diff checks. No provider/model calls or Authoring.

Schema127→128 applied after idle-work verification, exact installed controls,
root-only SQL dump2405474bytes and canonical Compose backup. Retained at
`/var/lib/anvil-qa-v1/backups/open-weight-dc9a144-20261117`. No env/credential,
identity, project-data or production change. Additive migration has no downgrade.

Actual post-rollout PASS: all six exact source/image identities, running/zero
restarts, live flags off, real dedicated polling, deployed24-variant/32-repository
catalog, schema128, actual compiled frontend markers, public workspace/health200,
anonymous project catalog401. Authenticated real QA user click-through NOT RUN;
browser configuration journey used synthetic API metadata, separately from SQL.

Four current serving-role observations appended using real installed versions,
health and polling metadata: API, business worker, scheduler and grader. All are
`observed_not_qualified`; no native qualification, allowlist, admission or approval
was created. Raw logs are not put into the UI/read model. Native coordinator and
task environment remain without a current qualified serving observation.

Failures retained: first GCP build8710206c failed because frontend Dockerfile
omitted shared workflow contracts. Added explicit COPY; full checked retry passed.
Earlier disk-full condition was resolved by user-approved30→50GB expansion; no
old containers/images or volumes deleted. Runtime/frontend/dependency locks kept.

Exactly one new blocker/deployment email sent only to
vasudevan.sundarababu@adi-labs.ai, Gmail message/thread `1a1ed239877309e4`.
It states deployed scope, tests, QA/build links, remaining native isolation block,
later HF token/terms/runtime setup, no live calls and no Authoring integration.

Native corrections continue separately at `.local/marketing-native-next-20261117`,
source checkpoint5cbf104;1071 units+10 subtests and minimal packaging/privacy checks
pass. Not serving or qualified; native remains closed due the reproduced helper
proc-root bypass and incomplete independent process/capture/operator admission.
