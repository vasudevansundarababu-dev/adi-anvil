# Dependency security candidate

Prepared from `d72587e8923ce35496d233c399e745f8f3e5303f`. This is a dependency-only successor, not deployment approval. No application source, API permissions, SQL migrations, actor/evaluator isolation policy or Harbor SDK version changed. The historical running preview and its environments remain untouched.

## Narrow changes and upstream verification

| Dependency | Previous | Candidate | Reason |
|---|---|---|---|
| Next.js | 16.3.6 | 16.4.1 | Highest verified fixed threshold among the reported Next advisories; matching Next environment/SWC packages only |
| source-map-js | 1.2.1 | 1.2.2 | Targeted vulnerable-version override; transitive Tailwind dependency |
| Authlib | 1.8.0 | 1.9.1 | Verified security thresholds 1.9.0 and 1.9.1 |
| certifi | 2026.7.22 | 2026.10.18 | Published root-certificate removal fix |
| joserfc | 1.7.5 | 1.7.6 | Compact JWS allocation guard fix |
| langgraph | 1.2.12 | 1.2.14 | Identifier encoding fix |
| langgraph-sdk | 0.4.5 | 0.4.6 | Same identifier encoding advisory |
| langgraph-checkpoint-postgres | 3.1.2 | 3.1.3 | Published security fix |
| langgraph-checkpoint | 4.2.0 | 4.3.0 | Minimum dependency required by patched postgres package; not independently upgraded to latest |
| opentelemetry-api | 1.45.0 | 1.45.1 | Tracestate parsing fix |
| opentelemetry-semantic-conventions | 0.66b0 | 0.66b1 | Necessary exact OpenTelemetry API compatibility pairing |
| Pillow | 12.3.0 | 13.0.0 | Verified fixed threshold for the reported Pillow advisories |
| pyasn1 | 0.6.4 | 0.6.5 | Verified security threshold |
| Harbor runtime filelock | 3.32.7 | 4.2.1 | Published local file-lock security fixes |
| Harbor runtime LiteLLM | 1.106.6 | 1.108.3 | Required compatibility repair: old version requires filelock<4; 1.106.7 and 1.108.0–1.108.2 retain that bound; 1.108.3 permits filelock<5 |

Harbor remains **0.25.0**. All other backend and Harbor locked package versions remain unchanged. Direct backend minimum requirements were raised only for the affected direct Authlib, LangGraph and postgres-checkpoint dependencies. Python remains 3.12.14, uv 0.12.19, Node 24.21.0 and pnpm 10.34.5.

The 58 backend repository advisories were read directly through their upstream GitHub repository security-advisory API, and exact candidate releases/dependency constraints were verified with official PyPI release JSON. These public responses are retained in `/private/tmp/anvil-security-upstream`; the original complete advisory inventory is `production-dependency-advisories-edcc051.json`. Database flags are not proof of exploitability: the current upstream Authlib GHSA-8m4g range ends at 1.7.2, excluding the original 1.8.0. The reported Next image issue already had the upstream Sharp>=0.35.5 mitigation; cache-component exploit conditions were not observed in application source. The dependency update remains appropriate without asserting those features were exploited.

Primary references: [Authlib 1.9.1](https://github.com/authlib/authlib/releases/tag/v1.9.1), [LangGraph identifier advisory](https://github.com/langchain-ai/langgraph/security/advisories/GHSA-3fx2-cqw9-xr3c), [postgres-checkpoint advisory](https://github.com/langchain-ai/langgraph/security/advisories/GHSA-6hmw-9432-67qq), [certifi advisory](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2), [joserfc advisory](https://github.com/authlib/joserfc/security/advisories/GHSA-9pg5-8c7x-5hfx), [OpenTelemetry advisory](https://github.com/open-telemetry/opentelemetry-python/security/advisories/GHSA-xcq7-p3pf-p88h), [Pillow 13](https://github.com/python-pillow/Pillow/releases/tag/13.0.0), [pyasn1 0.6.5](https://github.com/pyasn1/pyasn1/releases/tag/v0.6.5), [filelock 4.2.1](https://github.com/tox-dev/filelock/releases/tag/4.2.1), [filelock Unix boundary](https://github.com/tox-dev/filelock/security/advisories/GHSA-69hj-f68j-2879), [source-map-js 1.2.2](https://github.com/7rulnik/source-map-js/releases/tag/v1.2.2).

## Coding verification

All checks ran in fresh owned temporary copies using private package caches, excluding local environment files/state. No old preview dependencies were synchronized.

| Check | Actual result |
|---|---|
| Frozen web install, scripts disabled | PASS |
| `pnpm --filter @anvil/web check` | PASS |
| `node --test tests/provider_failure.mjs tests/readiness_catalog.mjs` | 12 PASS |
| `NEXT_TELEMETRY_DISABLED=1 pnpm --filter @anvil/web build` | PASS, Next 16.4.1 production build |
| `pnpm audit --prod --json` using official npm registry | PASS, 102 production dependencies, zero reported advisories |
| Frozen backend sync into new successor venv | PASS, 85 installed packages |
| Backend `uv pip check` | PASS |
| `python -m pytest services/backend/tests/unit -q --tb=short` | 793 PASS, 35.39 seconds; existing Authlib deprecation warning |
| Harbor pinned sync into new isolated runtime | PASS, 91 packages |
| Harbor `uv pip check` | PASS after necessary LiteLLM compatibility update |
| Harbor `python -m unittest discover -s services/harbor/tests -v` | 9 PASS |
| Pillow 13 PNG/JPEG/TIFF decode → ReportLab 4.5.1 PDF → pypdf page parsing | All three PASS |
| `git diff --check` | PASS |

Initial local test setup attempts lacked WEB_ORIGIN, the new isolated Harbor path and Unix-socket permission; those attempts were not treated as product failures or passes. An installation command naming the historical interpreter was rejected by automatic approval review before execution; the successful command instead explicitly bound a newly created successor environment. The first filelock-only installation exposed the LiteLLM<4 constraint via `uv pip check`; it was not accepted as a consistent candidate.

## Frozen file hashes

| File | SHA-256 |
|---|---|
| apps/web/package.json | 74172a2b9f1ef903d0101da441e78ada46a0a1eeb6b4b4eba150649f8e52cd02 |
| pnpm-lock.yaml | aca63f223856b6ebd415765934a7332b792e5797cba2aec2706ff7b61b8369b6 |
| pnpm-workspace.yaml | 01a2e5bc955db255030f223e98826ced0fa2617ebfb95c1eddf22f12552d14bf |
| services/backend/pyproject.toml | b8f470f90101b14f497e33a616d17bfe53321053cad4b9779cfa34fa944e6cc0 |
| services/backend/uv.lock | 22bef436122e38ca72554a0e540688124397fc624394003ddd4066175f68b5fd |
| services/harbor/requirements.lock | 2daf87656097906db875028e92840767e16a62562704a3b58ffd76d134461757 |

Independent successor advisory/SQL/browser regression checks and **fresh Linux native qualification are still required**. The old 28-case native result binds the earlier dependency lineage and cannot be relabeled as this candidate. The previous uploaded cloud package/build configuration is historical until new source/package hashes and actual upload provenance are prepared. No cloud build, application deployment or paid model call was performed by this repair.
