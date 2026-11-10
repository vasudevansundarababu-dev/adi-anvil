# Production dependency advisory check — edcc051

**Public advisory databases flag the reviewed locks. This is not an image vulnerability scan or proof that every flagged path is exploitable.** Source is the unchanged reviewed build context for `edcc0514c43ceb614b813566820ee0c2c7311463`, queried2026-11-09 UTC. Frontend lockSHA256 `f8894918d5b987e401bd3ca123b51a19370ec98882766c210f48e0acb81274b7`; backend lockSHA256 `00a917be042f5204926d3149c5e9bcbf57c0717c298afe202a20799ca58d7bb3`.

## Actual findings

`pnpm10.34.5 audit --prod --json` against the public npm registry reported11 advisories: **two critical,three high,five moderate,one low**, across Next16.3.6 and source-map-js1.2.1. The tool reported102 production dependency entries; this is a lock graph count, not a deployed-image inventory.

| Frontend package | Reported affected ranges/fixes |
| --- | --- |
| Next16.3.6 | Ten advisory records. Older branches require16.3.8; the two critical records and Server Actions DoS require16.4.1. Exact per-advisory ranges/IDs are in the JSON report |
| source-map-js1.2.1, through Tailwind PostCSS/node | GHSA-68fv-2mgg-jv7q, high, affected>=1.0.0<1.2.2; fixed>=1.2.2. [Upstream repair](https://github.com/7rulnik/source-map-js/pull/79) |

Important existing qualification: [Next image-optimization RCE GHSA-2464-fhr4-w9xw](https://github.com/vercel/next.js/security/advisories/GHSA-2464-fhr4-w9xw) identifies sharp>=0.35.5 as a workaround; this lock **already pins sharp0.35.5**. Do not infer this issue is exploitable from Next's version flag alone. [Next cache-function RCE GHSA-673q-mjm6-r5xr](https://github.com/vercel/next.js/security/advisories/GHSA-673q-mjm6-r5xr) has a Cache Components/typed-array condition. Bounded app/config search found no use-cache/cacheComponents/useCache matches; that is not a complete reachability audit. Upstream still recommends upgrading. No exploit probe or image/SBOM verification was performed.

Backend production requirements were exported **offline/frozen/no-dev/no-project** from the exact lock, then evaluated for Linux x86_64/CPython3.12.14. OSV queries covered78 public PyPI pins, excluding only three platform-inapplicable requirements. Nine packages were flagged. OSV returned83 IDs including GHSA/PYSEC aliases; the complete result contains58 unique GHSA records: **seven critical,30high,21moderate**. These are not83 distinct CVEs or58 proven exploits; one advisory can cover multiple packages.

| Backend package and locked version | Largest reported fixed threshold across returned ranges | Primary upstream example |
| --- | --- | --- |
| authlib1.8.0 |1.9.1; some records fixed1.9.0 | [JWT/JWS](https://github.com/authlib/authlib/security/advisories/GHSA-6v38-4h7w-rj9h), [algorithm confusion](https://github.com/authlib/authlib/security/advisories/GHSA-7vr2-2fgp-9w7p) |
| certifi2026.7.22 |2026.10.18 | [CA trust issue](https://github.com/certifi/python-certifi/security/advisories/GHSA-6q48-6c7w-9gw2) |
| joserfc1.7.5 |1.7.6 | [Size-guard allocation](https://github.com/authlib/joserfc/security/advisories/GHSA-9pg5-8c7x-5hfx) |
| langgraph1.2.12 |1.2.14 | [SDK identifier handling](https://github.com/langchain-ai/langgraph/security/advisories/GHSA-3fx2-cqw9-xr3c) |
| langgraph-checkpoint-postgres3.1.2 |3.1.3 | [Store namespace handling](https://github.com/langchain-ai/langgraph/security/advisories/GHSA-6hmw-9432-67qq) |
| langgraph-sdk0.4.5 |0.4.6 | Same SDK identifier advisory as langgraph |
| opentelemetry-api1.45.0 |1.45.1 | [Tracestate parsing](https://github.com/open-telemetry/opentelemetry-python/security/advisories/GHSA-xcq7-p3pf-p88h) |
| pillow12.3.0 |13.0.0 | [TIFF memory issue](https://github.com/python-pillow/Pillow/security/advisories/GHSA-332p-7hrc-92wf);41GHSA records returned for this pin |
| pyasn10.6.4 |0.6.5 | [Constructed BIT STRING decoding](https://github.com/pyasn1/pyasn1/security/advisories/GHSA-2qm8-x737-gmw5) |

The JSON report preserves every returned GHSA's exact affected ranges, aliases, severity and upstream links. Thresholds above are advisory database facts, not tested upgrade compatibility or permission to change dependencies. No backend upgrade was performed.

Bounded source observations: the OIDC callback explicitly permits RS256, requires issuer/audience/expiry/subject/nonce, and compares nonce independently; no direct JWS JSON call was observed. This does not clear all Authlib findings. The worker uses PostgresSaver with pickle_fallbackfalse; this does not prove the separate Store namespace or SDK advisories are unreachable. No complete call-graph, input-reachability or deployment-configuration analysis was attempted.

## Separate Harbor runtime

All91 exact public pins in `services/harbor/requirements.lock` were also queried independently; lockSHA256 `612ab41777d8eb6ec2dee6c3390705130e55d9d1a216c79df34a1597c6156ec3`. Harbor remains0.25.0. Only **filelock3.32.7** was flagged:13 unique GHSA records, one high,nine moderate,three low. Most ranges end at4.2.1; one ReadWriteLock symlink issue ends at4.0.9. The largest reported threshold covering this returned set is **4.2.1**. Examples: [UnixFileLock renamed/hard-linked lock path](https://github.com/tox-dev/filelock/security/advisories/GHSA-69hj-f68j-2879) and [ReadWriteLock SQLite side-file issue](https://github.com/tox-dev/filelock/security/advisories/GHSA-v4x8-3wr5-3wq8). Full exact ranges and13 IDs are in the JSON report.

Public PyPI metadata confirms filelock4.2.1 exists, has no yanked artifacts and requires Python>=3.11, compatible with the planned3.12 interpreter. Existing installed metadata declares Harbor0.25.0 requires filelock>=3.29.4 and huggingface-hub1.33.0 requires>=3.10.0, with no upper bound observed. Thus there is no declared dependency constraint requiring a Harbor SDK upgrade to attempt this fix. This is **not runtime compatibility proof**. No SDK or lock was changed; any repair must regenerate the91-package lock/hash manifest honestly and qualify the resulting runtime rather than reuse the old digest/native evidence.

Shared-name comparison matters: Harbor already pins certifi2026.10.23 and opentelemetry-api1.45.2, above their backend advisory thresholds; neither was flagged in the Harbor query. The other seven flagged backend package names are absent from this separate Harbor lock. Conversely filelock is not in the backend production export. Do not copy exposure findings between these environments just because the application uses both.

Some filelock records are Windows-specific and others depend on another local user controlling lock paths/files. The Anvil operator's private0700 roots are relevant isolation, but no complete transitive-caller/lock-path review was performed. A bounded search found no direct filelock import in Harbor's own Python files; that does not exclude transitive callers. No advisory was returned for the Harbor0.25.0 package itself; that is database coverage, not a security guarantee.

## Method, errors and limits

Exact public manifests/locks were copied into a fresh0700 private workspace/home/cache. Source/context hashes were checked before/after and remain unchanged. No credentials, private package names, project code or environment secrets were sent to advisory services. The existing pip-audit module was unavailable; it was not installed. Existing uv exported the backend production closure offline; public OSV backend batch/nine affected-package queries and Harbor batch/one affected-package query succeeded with no API lookup errors. No image pull, cloud mutation, model call or scanner API enablement occurred. **Container Scanning API remains disabled; container/OS vulnerability scanning was not run.**

Deviation preserved: the installed pnpm entry point was a Corepack shim. A fresh COREPACK_HOME unexpectedly fetched the same pnpm10.34.5 tool archive into the private cache. This exceeded the intended no-new-tool-download boundary. Root was informed; no further Corepack invocation followed. No application dependencies, global configuration, product source or locks were installed/changed by this check. The stderr notice and its hash are retained, rather than claiming no download occurred.

Complete safe machine-readable findings: `production-dependency-advisories-edcc051.json`. Raw npm JSON: `/private/tmp/anvil-production-advisory-b8757b139d4e45209c4cb650aaffd667/frontend-audit.stdout`; full OSV response/report is in the same private directory. Coding received both paths for a separately coordinated repair. This report makes no blanket security verdict and does not authorize deployment or another paid build.
