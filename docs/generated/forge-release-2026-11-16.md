# Corrected ADI Forge deployment — 16 November 2026

Verified22:36UTC /2:36PM Pacific. Main and existing QA run the actual Forge release:

- Main: https://anvil-34-36-217-66.sslip.io/workspace
- QA: https://anvil-qa.adi-labs.ai/workspace
- QA login: https://anvil-qa.adi-labs.ai/api/v1/auth/login

## Source and corrected scope

The earlier d503880 rollout used an older Git branch. The user correctly reported
missing current changes. The actual source package was recovered from the team's
sealed build32/candidate12 workspace, without altering that workspace. All1024
files matched manifest SHA256
`9398adfdfe9f92cd965090370649f19b3bac49eab4fe66a7c92892a50943b763`.
Current recovered source: `.local/forge-main-release-20261116` in this repository.
Its recorded base commit isdfef6ae9449e5abd802f5fa0d0d224a2ffccb2f1; the package
contains working-tree bytes, so that Git commit alone does not identify the release.
Original checkout, unrelated edits, other products and team workspaces are preserved.
No GitHub publication or merge was performed.

Delivered source includes Forge logo/name, Home/Projects/Execution/Admin navigation,
project/input/workflow and evaluator integration, report review, and schema127.
Internal legacy namespace/issuer/resource names remain compatible. Main Keycloak
display name now says ADI Forge; realm, users and security settings are unchanged.

Only application-source differences from the sealed package are the Next.js security
patch package/lock pair:16.4.1→16.4.5. Official advisory:
https://github.com/vercel/next.js/security/advisories/GHSA-mfr8-8qww-v76h .
Patched package SHA256 `5e9d5dd6586480ac9ab3ce29165e8b17608d7d284a5bbd973df19edfb7af1d5e`;
lock SHA256 `7fc477c545eb2f6bc204acb9ab483b7da1d6befcc86f38f9a2ee68a87b9d28f4`.
Frontend allowlists excluded local state, dependency folders and credentials.

## Actual images and builds

- Exact qualified backend: `sha256:a2819e51c44c933b61329067aee68c327ec1ebddba7e2658c0607aee6abe230a`.
- Patched web: `sha256:bf35dddaf41ef576ba90400153db150b0459473f9df52314a24f56fd3a40f810`.
- Current-source main Harbor worker: `sha256:0d956fb8521e1727d158639d3034a97f7711f5b9cd8cdedc67e38fb67949fff9`.
- Backend reused qualified build32 image, preserving its source-manifest label.
- Web build `e0b9bd11-3abd-4825-9621-145030c1d38c`: SUCCESS.
- Harbor packaging `51f07a1f-0ddf-4a29-a698-414687628598`: SUCCESS. It combines
  current sealed backend/Harbor source with the already locked0.25.0 runtime and
  Docker CLI from the prior main worker; no native/model trial is claimed.
- QA web mirror `5b4a5e77-7e15-450e-ba51-3a5d40118c5a`: SUCCESS, same web digest.
- Disposable migration `4c1bad0c-5295-4faa-8d1f-1f3e829baea7`: SUCCESS, fresh127,
  repeat127,069→127 and repeat, with unchanged historical001–069 source bytes.

Main API/ordinary worker/Harbor/web independently inspected running correct images.
QA API/ordinary worker/business worker/web inspected running correct digests.
QA's preexisting idle Golden scheduler/grader and core services remain unchanged.
Main VM image metadata and QA canonical Compose persist the corrected references.

## Validation and honest limits

PASS: `uv sync --frozen --project services/backend`; current readiness test file
(`ANVIL_ENV=local WEB_ORIGIN=http://127.0.0.1:3202` with release venv
`python -m pytest services/backend/tests/unit/test_deployment_readiness.py -q`),7tests;
`pnpm install --frozen-lockfile`; frontend types and production build; patched
`pnpm audit --prod --json`, zero known reported vulnerabilities. Earlier full935-unit
results are older-branch evidence, not current-source qualification.

PASS on actual main/QA: schema127, exact source/image identities, API/PostgreSQL and
private Neo4j readiness, live public Forge title/new logo/navigation assets, OIDC form,
and retained original identity/spending fields. Main browser explicitly displayed
ADI Forge logo/title and “Sign in to ADI Forge.” Main metadata was updated after
successful rollout. QA runtime env files stayed hash-identical; Compose updates the
existing software-only source fingerprint and explicitly keeps governed AI off.

PASS QA anonymous access checks: imported-projects, workflow definitions, runtime
Admin roles and expert-review listing all401; private readiness and public Keycloak
administration404. These prove access rejection, not authenticated role acceptance.

NOT RUN: authenticated Admin/RL end-to-end workflows; native Golden qualification;
new live benchmarks, generated report/export journeys, or full current-source
SQL/security/browser regressions. No paid provider/generation request, approval or
source review was issued as smoke. Historical QA data was not copied to main.
Deployment retry authority did not authorize model calls/retries or spending changes.
This is successful deployment smoke, not full scientific/product acceptance.

## Retained failures and recovery

- First disposable rehearsal raced PostgreSQL's temporary initialization server;
  TCP readiness fixed the harness. Original failed build retained.
- Main pull filled30GB boot disk before switch. Removed only nine unused historical
  web-image caches; kept active and two rollback releases, task images and all data
  volumes. Freed4.6GB, retained failed attempt, retried successfully. No disk resize.
- QA first pull lacked Docker registry auth. Existing VM GCP identity helper was
  configured; no personal credentials copied or IAM grants added. Retry succeeded.
- Initial QA private readiness returned503. Independent PG and Neo checks passed,
  subsequent bounded endpoint passed in1.729s. Original failure retained; cold-start
  latency is not asserted as a proven root cause.
- QA full-row fingerprint differed because083 adds generated display_id. Original
  fields were explicitly projected and all hashed identically; display IDs separately
  validated. Original mismatch and both projections are retained.

Snapshots READY before switches: `anvil-before-forge-build32-20261116` and
`anvil-qa-before-forge127-20261116`. Root-only recovery records, SQL dumps and original
Compose/configuration on each VM:

- Main `/var/lib/anvil/releases/forge-build32-main-20261116`
- QA `/var/lib/anvil-qa-v1/releases/forge127-20261116`

Failed-pull siblings are retained. Migrations are forward-only; review compatibility
before image rollback. Never overwrite current data automatically from snapshots.
Cloud build/snapshot charges are unreconciled; no zero-infrastructure-cost claim.

## Requested completion email

Exactly one Gmail email sent only to vasudevan.sundarababu@adi-labs.ai, no CC/BCC:
message/thread `1a1e681794a64667`, subject “ADI Forge deployment completed — current
release and QA smoke results.” It includes build IDs, fixes, smoke results, main/QA
links, preserved initial failures and remaining authenticated/live verification limits.
