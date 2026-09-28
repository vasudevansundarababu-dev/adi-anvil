# ADI Anvil

Frontier Evaluation & Diagnostics Platform

**Active local build — 28 September 2026.** Work resumed under the user's additional eight-hour window (11:24–19:24 UTC). The fixture journey, production build, unit tests and expanded security tests pass; the complete MVP acceptance matrix remains partial. Live inference and external sending are disabled. See [current build status](BUILD-STATUS.md); the [morning report](docs/generated/morning-report.md) records the previous window. Local checkpoint: `7377af7`.

## Start

1. Run `pnpm setup:local` to install locked dependencies and start PostgreSQL, Neo4j and Keycloak. Docker, Node/pnpm, Python and uv must already be available.
2. Run `pnpm dev`, then open http://127.0.0.1:3202. Distinct local account credentials are in ignored, owner-only `.local/demo-accounts.md`.
3. Verify with `pnpm check`, `pnpm test:unit`, `pnpm test:e2e`, then `pnpm test:integration`. Integration budget tests require the qualified protocol produced by E2E.
4. `pnpm stop` stops registered app/worker processes while preserving infrastructure and data. `pnpm services:down` stops infrastructure without deleting volumes.

The [acceptance walkthrough](docs/build/04-MORNING-ACCEPTANCE.md) describes the target; consult the [test matrix](docs/generated/test-matrix.md) for remaining gates. No specification is evidence of a passed test.

## Engineering authority

The latest user selected a new independent repository named **ADI-Anvil**, private, local build first and GitHub publication only after review. Infrastructure and the eight-hour/local-only build boundaries are confirmed. The requested morning target includes the diagnostic journey **and live model evaluations**. Provider families are selected, but credentials, exact model IDs, budget and real paid approvals remain missing; live calls stay blocked until configured and authorized.

Read [overnight build specification](docs/build/01-OVERNIGHT-BUILD-SPEC.md), [repository structure](docs/build/02-REPOSITORY-STRUCTURE.md), [runbook](docs/build/03-EXECUTION-RUNBOOK.md), [live evaluation gates](docs/build/05-LIVE-EVALUATION.md) and [fixture contract](docs/build/06-FIXTURE-CONTRACT.md).

The files in `docs/product/` preserve the detailed v1.0 product/contracts baseline. The new `docs/build/` instructions supersede only the old folder name, phase-0–1-only coding prompt, one-phase-per-request sequencing, and prohibition on local Git initialization once this build is launched. They do not remove security, rights, review, truthfulness or budget controls. The old ADI-Core-Frontier folder is not a runtime dependency and must remain unchanged.

## Build outcome

Real local UI + API + PostgreSQL + LangGraph worker + Neo4j projection + OIDC, with case intake, qualification, versioned suites/protocols, fixture and authorized live runs, human review, diagnostics, downloadable reports and one-page Sales Kit. No enterprise training, TNG/TTM, simulator authoring, cloud deployment, real email, Notion publishing or live Praxis synchronization.

Original sample cases test application mechanics, not research novelty, long-horizon intelligence, university validation or commercial performance. All fixture outputs remain illustrative after review/export. No real Bodhium cases are included.
