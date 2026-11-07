# Human approval handoff — STOP BEFORE CODING

- Work ID: anvil-praxis-bodhium-benchmark-2026-11-07.
- Repository: https://github.com/vasudevansundarababu-dev/adi-anvil.git.
- Workspace: `/workspace/anvil-recovered`; branch `codex/anvil-agent-team-2026-11-06`; actual HEAD `8cdc8a84784c7ae52d7bbb88f36193b387aedb60` is BASE, not latest release.
- Source: verified 264-file production overlay from supplied Cloud Build archive on historical base. Composite tree `cc9925ec8380a56fa3fa988c157b2d5d7563cda2`; expected full r6 `18fca788310f91a35a54df39392a37c026ae16b1` remains unrecovered.
- From role / proposed next role: anvil-architect then anvil-planner completed sequentially under explicit current user authorization. Next is **human review**, not Coding.
- Product input: approved specification v0.1; exact approval scope/message references in approval-record.md. Architecture and plan are DRAFT, not human-approved.
- Recovery inputs unchanged at `recovery-evidence/inputs/`: original archive SHA-256 `5679da027619c50f4a2418514805c2b38730888ce45fa2ed3c7a4f42ec29d8fe`; original TXT SHA-256 `17f34a7831f029782ee3b28b5b6944ac7be82d1899ed29f476e5b7580d27b8ec`.

## Bound input/output revisions (SHA-256)

| Artifact in this run folder | SHA-256 |
| --- | --- |
| `approved-specification.txt` | `44196cae04b7a399fb70da8d4577345b2cf95ee6a14daa41f3d8c8f2b4921cbc` |
| `approval-record.md` | `3c02f95ba28a03240a1bc8ae375d024b2d77cb4e33a6f601007cbaf58b20d07c` |
| `recovery-report.md` | `e7a471372a4fb103b1aba9423285f2a3439977a655a39dd3570f2aacc1bdf694` |
| `recovery-inventory.json` | `f8060cf3355b629e7990ca5cd2db568355e49ac84f8d44d3a5d3753db60ba603` |
| `production-source-manifest.jsonl` | `cedfb20d5b3160dcfee2e91f729e237063e16c714eb70dbef52cc7c59e173031` |
| `architecture.md` | `c200d135bd9dbe171b63e13833349a6486d09adff17c5c27daf870d46c6cf68a` |
| `contract-design.md` | `6486299f60ec6f58f2acf21b02137cff5402eb4a13a6df01701a30f9b2c58668` |
| `threat-model.md` | `2ca9cb927254ea2450da4b2c63813993e24fb17da4bc575e52a99fbaf77db673` |
| `requirements-to-test.md` | `b8608c8225231c9a0581ed32959dbac8ad18aa56ce970bae49ef093483bc209f` |
| `implementation-plan.md` | `1cdf87e4d48bc483a2e5116509e83d07b35f2652b95c032635b98bbe0e3f9749` |
| `verification-record.json` | `ecdc1f430664d342ae34fce68c8de4af1c356b0b08b57a87e64f787848f87069` |
| `execution-evidence-index.json` | `d193e6ce2fc9c57ce7d081a2c37446dc5e5916260b6072819ee88ff9761caedb` |

The final artifact-index.json and SHA256SUMS index these artifacts plus this handoff without self-hash cycles. They do not prove full release recovery. No documentation file claims an implementation, passed application QA or deployment for this increment.

## Changes and coverage

Recovered existing release-source files only; authored new recovery/design documents. Proposed design reconciles actual APIs/schema/provider brokers, keeps v1/v2/v3/export compatibility, restores readiness/finalization context, introduces an independently qualified SME bundle/evaluator boundary, three-provider parity/18-cell orchestration, 81-point and incomplete/unknown-cost semantics, UI/migrations/rollback and threat tests. Traceability covers BM-01..12. Proposed file scopes/dependencies and future commands are in implementation-plan.md T00–T13. No product source was changed beyond byte-verified recovery overlay.

## Evidence and gaps

- Recovery checks **Passed**: exact archive size/SHA-256, 318 safe members/264 regular files/4,421,541 expanded bytes; per-file overlay hashes/modes and deployed worker hash; approved spec hash; unchanged historical base-only blobs; recomputed base/composite tree and document completeness.
- Full r6 recovery **Blocked**: expected tree mismatch; 235 tracked base paths absent from archive. Release patch/manifest, changed tests/docs/run history and prior approvals/QA/security/deployment records not supplied. Missing tests/readiness_catalog.mjs is a concrete example. Do not invent the remaining 30-file-increment history or call base tests current.
- Application tests, native Harbor, provider smoke, migrations/build/startup, UI testing and deployment **Not run** by authorization. Their evidence arrays are empty. Authentic Bodhium/live acceptance **Blocked** by absent data/criteria/rights/images/model/judge/cap inputs.
- GCP successful build/login is coordinator-reported; no local runtime cloud authentication or deployment verification. CLI/login setup was superseded by archive delivery; no code/token in chat or credential transfer required.
- No Praxis/Mac/shared-backend operations, cloud writes, benchmark implementation, application tests, product calls, commits or pushes.

## Proposed next allowed scope

Review these exact architecture/plan revisions and decisions first. Supply the full r6 patch/manifest/source bundle and omitted regression/evidence files for T00, or explicitly decide a newly audited baseline exception. After source reconciliation, a separate human message may approve a bounded coding assignment (suggested first T01–T03). It must name approved hashes/scope; it cannot silently authorize later live/provider/deployment work. Missing Bodhium, judge or budget inputs do not require fabricating data and do not grant paid authority. See plan for staged local mechanics versus authentic/live gates.

Prohibited pending further authority: benchmark coding/test creation or execution, paid calls, role/auth changes, deployment/GCP writes/IAM, snapshot/volume operations, credential transfer, commits/pushes and any Praxis/Mac changes.

**Decision: PENDING HUMAN APPROVAL. STOP BEFORE CODING.**

- Human approver of new architecture/plan:
- Actual new approval message reference / timestamp:
- Approved new artifact hashes and bounded next scope:

(Fields intentionally empty: no such approval has been supplied.)
