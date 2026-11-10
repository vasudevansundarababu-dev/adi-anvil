# Current implementation report — recovered T05 final Coding handoff

## Approved task and input revisions

Actual recovery quote appended to approval-log.jsonl from current conversation b59115d76f8b427baccc1382eeb0426e. Initially clean local/remote/open draftPR16 exactlye0a7b5f. Existing branch/Git identity/current ADI-Architecture connection retained, anvil-coding role only. All15 original requirements/design/plan approvals match approved-input-snapshot.json.

## Changed behavior and source revision

Tested commit `4e64f54c368d04afcde6faa8c41cdadd9529e0d9`, tree `0c745b5b5f098f2f55ea066f8c4f8228913cfe6f`. Repair checkpoint `e0a7b5fb45dbc73c1e9d6248647a102387ea5cd8`, tree `d807b5ee4f17acdf1d8f582a356e731863ab0c66`. Recovery/publication change documentation/evidence only; product/test/lock bytes are identical, but whole Git trees are not equated. No new source/test/dependency fix needed. Only product diff from accepted pricingb97ac8d remains NativeGateway/server in benchmark_qualification.py and existing test_benchmark_tool_gateway.py.

```text
bounded <=256B unambiguous frame + absolute1s framing deadline
  -> cancel/fence framing timer
  -> token before JSON/callback -> exact session/single use
  -> one callback, no SDK retry -> bounded response I/O
```

Max4 owned handlers/owned-socket shutdown/1sresponse preserved.21 added cases include32 fixed split-denial schedules plus framing/duplicateCL/TE/Expect/auth/truncation/oversize/stall/capacity/shutdown/valid256B/longcallback/postdispatchdisconnect/replay. No single-use/auth weakening after ambiguous dispatch.

## Requirement coverage

BM05/09/11 bounded T05 repair verification and T06 compatibility only.3 actual installed SDKs and real Unix/stdio/filesystem/Harbor host client exercised. Pricing/capture/evaluator contracts independent. Private negatives prove real compiler/private hash rejection, not isolation. SQL/native qualification blocked, not waived.

## Tests actually run, results and evidence

46 gateway;95 provider-loop; exactly3 fixed diagnostic rounds of6 each;96 pricing/capture;33 T06 contracts;729 full units;3 pre-dispatch private-binding negatives;7 adapter;12 Node; Ruff check/format2 files; scanner/diff: PASS. Counts overlap, not additive unique tests. Full729 is new-runtime proof on committed product/test bytes, not reused historical working-tree729. All invoked commands exited0, correct fixture flag from first test; no retry-until-green/source workaround.40 deselected per diagnostic and9native deselected for private negatives are scoped selections, not skips/passes.

Python3.12.14, independent Harbor0.25.0, OpenAI2.54.0/Anthropic0.125.0/google-genai1.75.0/httpx0.28.1/pytest9.1.1/Node24.22.1/Linux. Exact versions/UTC times/commands/env/local-log hashes/source hashes in t05-recovery-checks.json / commands / source manifest. Existing Authlib jose deprecation and Node module-type warnings retained.

## Failed, blocked and not-run checks

Fresh full T06 SQL/native57 and combinedSQL136, T04 actual native9 and4 resource probes are BLOCKED/NOT RUN. No approved dedicated preloaded Docker/PostgreSQL runtime/images/socket in this new runtime; no new pull/build/load/substitution authority inferred. The3 private negatives invoke no Docker and are not native isolation. Old last4resource action has no observed result.

Read-only platform history yielded sanitized summaries/commands/event IDs/timestamps, not byte-exact raw logs/private artifacts/runtime recovery. Expected old-code4failed/11passed/25deselected and separate absolute-deadline1failed/39deselected, combined KeyboardInterrupt and outer soft timeouts retained. Later3x6/57T06/12T04/136combined/729full/96pricing-capture summaries remain historical; final e0 source observations identified separately. Shell exit0 after tail does not turn failed pytest into pass. Earlier707/1 and689/1 reports remain unchanged.

No new test/setup failure. Read-only guessed filename probes found no native_gateway/conftest files; corrected to actual suite, not counted as tests. Large publication tool requests failed validation or produced no writes; final smaller commands generated the evidence. These tool interruptions did not change test outcomes.

## Compatibility, migrations and remaining risks

All product trees/locks and15 originals unchanged. Legacy providers/dispatch/Harbor/locks/OpenAPI/pricing equalb97ac8d. No migrations here; previous fresh/upgrade049 evidence historical.6 exact rates and prior official sources unchanged, verified2026-11-08T15:25:35.450801Z/expires2026-11-15T15:25:35.450801Z; no unnecessary GET/refresh/expiry extension. Real UTC production expiry/deterministic fixture clock preserved. Do not backfill immutable receipts or convert historical qualification into product admission.

Old conversation preserved. No old credentials/secrets/private exhibits read/copied; no shared sockets, production/cloud/old-runtime lifecycle, Praxis/Mac/local-user checkout, auth or shared permission changes. New tests used a constructed environment allowlist and fresh owner-only HOME/TMP/vault. MockTransport only at unavailable paid HTTP boundary; Unix/process/filesystem/installed SDK/Harbor host-client paths real. No T07/independent QA/full acceptance/paid/judge/model-performance/Bodhium/trust/admission/merge/deployment claim or action. Raw logs/private synthetic outputs/dependencies ignored. Optional uv-created user-bin Python link removed after exact-target verification; no global package/system/config change. Current portable SHA256SUMS excludes unavailable historical TAP bytes but original digest remains in artifact-index.

## Human Coding review handoff — STOP

Offline verification and handoff complete; fresh SQL/native remains an environment blocker. Keep PR16 draft, title/purpose unchanged. Human review only. For fresh SQL/native, supply an approved preloaded dedicated runtime or separately authorize exact two image preparation for this new isolated runtime, then bounded remaining checks. No preparation/next role automatically approved or launched.

Decision: PENDING HUMAN CODING REVIEW.

---

Publication verification:39 source hashes /55 available artifact hashes and staged scanner681 files /0 findings passed; product diff and staged diff clean. Missing historical TAP bytes remain unavailable, not counted.

## Historical implementation reports retained unchanged below

# Current report — verified pricing/T06 checkpoint; full-unit T05 blocker

## Approved task and inputs

Actual user authorized verified current exact-model pricing maintenance, deterministic clock tests and final T06 publication only. Approval append-onlyd7bc624; base T06ca8c279/publication8854f71 verified. Original15 unchanged. Samebranch/current connection/Coding role; no T07/QA/paid/merge/deploy authority.

## Changed behavior and exact source

Tested `b97ac8d2949811d7ec06a00b43fdc8dc391e353e`, tree `1787c39dbd33ae733a775a413e5704afc8babf5f`. Only workspace_costs.py and test_workspace_costs.py changed in source/contracts/Harbor. Actual10 official HTTP200 pricing/model/cache pages verify all6 original exact models/rates; no numeric rate/model/tier/cache/context expansion. Refreshed provider references/verified_at and existing7day expiry after verification, not a blind timestamp extension. Keyword-only optional testclock; production default actualUTC/strict expiry unchanged. Original billing/arithmetic/cache/usage and all T05/T06 core/legacy/Harbor/locks unchanged.

## Authoritative pricing evidence

`t06-pricing-sources.json` retains10 source URLs/resolved URLs/retrieval times/body hashes, exact model IDs and relevant quoted rows, old/new reference/rate/time/expiry comparisons and excluded tiers/context/cache rates. Public full docs remain ignored, not raw source dumps in Git. As-of **2026-11-08T15:25:35.450801Z**, expires **2026-11-15T15:25:35.450801Z**, exactly7days. Sources: OpenAI developers.openai.com/api/docs/pricing.md +4exactmodel pages +prompt-caching.md; Anthropic platform.claude.com/docs/en/about-claude/pricing.md +models/overview.md; Google ai.google.dev/gemini-api/docs/pricing +exactgemini-3.8-flash modelpage. All entries verified; unknown/unlisted IDs still unavailable, no account availability/live authorization inferred.

USD/million tokens, unchanged admitted rates:

| Exact model | Input | Cached input | 30m write | Output |
| --- | ---: | ---: | ---: | ---: |
| gpt-6-luna |0.10|0.01|0.125|0.50|
| gpt-6-astra |10.00|1.00|12.50|50.00|
| gpt-6.1-sol |2.00|0.10|2.50|10.00|
| gpt-6.1-terra |1.00|0.05|1.25|5.00|
| claude-opus-5-5 |4.00|not admitted|not admitted|20.00|
| gemini-3.8-flash |0.75|not added|not added|3.75 including thinking|

OpenAI Standard/global/short context only, runtime<=33792input vs >272Klong context, default30m; excluded12h/long/regional/Batch/Flex/Fast dimensions retained in evidence. Opus direct global Standard/noncached; excludes cache/fast/batch/USgeo uplift. Gemini paid Standard, promo through2026-12-31 with announced2027-01-01 change: Nov15expiry precedes change; no future price/cache storage/grounding admission or automatic renewal. Existing immutable frozen expired-price groups NOT backfilled/revived; normal explicit updated config/run controls remain required.

## Tests actually run and results

Source-bound `t06-pricing-checks.json` / `t06-pricing-source.sha256` / `t06-pricing-commands.md`. On committed source: **36pricing passed**, **57T06 passed** INCLUDING2realnative; **136combined backend passed/3native deselected**,7adapter/12Node/Ruff2 passed.36price tests cover all6exact IDs/current/expiry-1us/equality/+1us/10-yearfuture, unknown/malformed/bool/negative/naive dates, default actualUTC and originalcache/usage/reservation math. Old expiry failure reproduced1failed/17pass; TDD15failed/21passed then36pass. Earlier689/1 pricing failure preserved in historical T06 evidence and superseded ONLY by actual pricing rerun, not a fake full-suite pass.

## Failed/blocked/not-run — concrete stop condition

**Latest exact-source full-unit suite:707passed/1FAILED**, unchanged T05 test_benchmark_tool_gateway.py::test_real_unix_gateway_and_installed_harbor_host_agent_client[anthropic]. Wrong-auth HTTP body sendBrokenPipe before any provider callback; NativeGateway rejects auth/returns409 before reading body and may close socket first. Considered pricing clock, SDK versions, network/daemon, stalepath, process lifetime and request ordering; unchanged source/fresh AF_UNIX path/no callback indicate early-reject vs body-send ordering, not pricing. Initial full run hadsamefailure; focused3provider gateway rerun and one full708pass occurred, but final committed707/1 repeated. All evidence retained; **full-unit gate is not reliably green**, no rerun-until-green/skip/retry/mock/workaround. This T05 transport fix is outside exact pricing/T06-only authorization; stop for separately approved bounded fix before claiming complete regression pass. Existing Authlib warning unchanged.

T06 core/native focused complete and pricing maintenance complete; overall fully green completion blocked by T05 race. No QA/full acceptance/browser/cloud/deployment or paid/model/judge call run. Semantic judge staysBlocked, fictional calibration NOT SME/Bodhium/model performance. No new migrations: historical049 fresh/upgrade/repeat evidence remains prior source-bound, not fabricated as new.

## Compatibility/runtime and handoff

Only2 source/test files changed; original15/T05/T06 core/Harbor/locks/API unchanged. Fresh0700 test vault,4new evaluator+2new actor sessions stopped/retained; existing isolated main PostgreSQL kept running for tmpfs evidence. No daemon restart/pulls/builds/deletion/socket permissions/role/credential/bootstrap/shared/Praxis/Mac/local edits. No frozen config DB mutation. Raw logs/private fictional test inputs ignored; sanitized evidence/hash only committed.

STOP human Coding review of exact `b97ac8d2949811d7ec06a00b43fdc8dc391e353e`. Propose separately authorized bounded T05 wrong-auth transport/test repair, then full-unit rerun; do not execute it now. T07/QA/paid/merge/deploy remain prohibited; resulting code and next-scope approval pending.

---

## Historical reports retained below, not retroactively relabeled

# Current report — T06 reviewable; human Coding review pending

## Approved task and input revisions

User accepted T05bb7713f/publicationdfc8c3e and explicitly authorized T06-only Coding/local SQL/native on same branch; actual quote append-onlyccf34de. Original15 unchanged; current LLM connection retained. T07 onward/QA/paid/merge/deploy not authorized.

## Changed behavior and source revision

Tested `ca8c2792e849ed2c7756a08e633a73a7a5832df2`, tree `2f4fc5f2416cc3e4649ebf4899507e29bbc1fea0`, rerun on committed bytes. New stdlib evaluator program, registry/queue service, least-privilege SQL coordinator and separate native test-operator adapter. Additive047–049 SQL/Alembic; default-off review/queue/status/cancel/revoke API and generated OpenAPI. New private benchmark_sealed preserves legacy benchmark_output; no dependencies, old schema edits, credentials or deployed service provisioning. T05/legacy provider/dispatch/Harbor/locks unchanged.

## Requirement coverage

BM04/07/08/09/11 T06 only: exact seal/task/hash/membership/UTF8 citation/unique IDs/Decimal credit/tolerance/absence recomputation;8 fictional good/bad/boundary/paraphrase/keyword/injection/missing calibration cases. Missing semantic authority yieldsBlocked/no criteria; malformed outputReviewRequired, not candidate0. Registry binds code/image/policy/calibration/reviewer/expiry plus immutable revoke. SQL claim explicitproject/job only; ordinary worker cannot claim; exactly policy+sealed artifact, no arbitrary extra input. FORCE RLS, immutable reports, source/calibration recheck, no expired/revoked/cancelled/stale capture/reclaim. Actual PostgreSQL project-lock revocation race tested. No filesystem/process/provider I/O under SQL locks. API queues only; no Docker on API or SQL coordinator. Evaluator container has no socket/DB admin/egress/actor/vault; fixed pinned program, imported arbitrary code inert.

## Tests actually run, results and evidence

`t06-checks.json`, `t06-source.sha256`, `t06-commands.md`: **57 focused passed** (33 contracts+24 SQL/API INCLUDING2 native); **136 combined non-native backend passed**,7 adapter/12Node/Ruff11 pass.046 upgrade/repeat049 and independent fresh001→049/repeat verified.7 evaluator+3 actor containers across fresh native checks stopped/retained. Fresh main PostgreSQL left running to preserve tmpfs SQL evidence; independent fresh049 DB stopped/retained. Actual actor5+5 stopped before hash seal and separate evaluator; exact private report bytes persisted. No T06 mocks/provider calls.

## Failed, blocked and not-run checks

Full units **689 passed/1 failed**, NOT green. Unchanged T05 pricing source/test expects current OpenAI rates after EXPIRES2026-11-08T02:47:35Z. No invented rates/extended expiry/clock freeze/policy change to green tests. Separate reviewed pricing/test maintenance outside T06; not a T06 regression. Earlier2 fixture setup failures corrected with required ANVIL_FIXTURE_MODE. Earlier TDD absent module/9 output-class fixture errors/bool-span+overflow2 negatives/duplicate pytest basename collection failure recorded/repaired/reverified. Initial combined command was NOT a pass; later42pass verified. Existing Authlib warning remains. Startup soft tool timeouts resolved by actual SQL heads/retained-state verification, not fake/native retry.

External semantic judge/model/rights/cap/calibration/key absent; staysBlocked, no credential provision/access. No T07 admission/attempt matrix/T08 official score/T09 UI-export/QA/full acceptance/paid/merge/deploy. Numeric software calibration is not real SME judge agreement or Bodhium/model performance. Source-bound T04 receipts remain historical; changed input hashes stale correctly.

## Compatibility, migrations and remaining risks

Original15/T05/legacy provider/dispatch/Harbor/locks/pricing unchanged. API additive changes affect T04 input hashes by design; do not reuse old qualification. Registry/calibration are fictional software-only fixtures, not production approvals. Coordinator supports explicit constrained one-job executor; no general daemon/credential auto-setup/cloud activation. Owned retained containers, no pulls/builds/deletes/shared socket/runtime permission edits. Main SQL is ephemeral tmpfs; source/evidence durable in Git.

## Human Coding handoff — STOP, not QA

T06 reviewable/focused passed; overall suite has1 preserved baseline failure. Review exact `ca8c2792e849ed2c7756a08e633a73a7a5832df2` with evidence. PR16 remains draft. Resulting T06 code/next scope approval PENDING. No pricing maintenance or T07/QA/paid/deploy automatically.

---

## Historical reports below retained unchanged

# Current implementation report — T05 offline Coding complete; human review pending

## Approved task and input revisions

User approved T04 source38cc151 and T05 under the original implementation plan, local/offline only, normal checkpoints to existing branch, PR16 draft, preserve Praxis/local changes; stop beforeT06–T10/QA/paid/merge/deploy. User then requested finishT05 while away. Exact approval append-only at377023e; original15 approved spec/design/plan artifacts unchanged. Existing LLM connection unchanged; role Coding.

## Changed behavior and source revision

Source `bb7713fdcee6a187a99daaa04b60c8f9f8afac63`, tree `1369a0254476b7dc64d107d7205527ef9addc2be`; checks rerun on the committed bytes.3 additive modules: `benchmark_conversation.py` typed bounded host loop, `benchmark_provider_wire.py` three real SDK mappings/replay/guard, `benchmark_tool_gateway.py` declared output/stdin/Unix mediation.2 focused unit test files. Keep new SDK/profile code separate instead of altering existing providers/dispatch; reuse installed SMEAgent host-client protocol unchanged. No API/worker/admission route or live transport enabled. Profile `anvil-sme-native-tools-offline-v1` requires exact MockTransport and fixed synthetic credential, never environment/sibling key inference.

## Requirement coverage

BM-05/T05: ordered response/model/text/calls/observations/finish/usage; native OpenAI/Anthropic/Gemini wire formats independently qualified offline; exact endpoints/auth/model, no retries/redirect/proxy fallback.15 responses/task,8 calls/response,64KiB arg/result/final, bounded SDK request/2MB response and task/tool deadlines. Duplicate/reused IDs rejected before side effects; unknown usage/cost remainsNone. Gemini opaque signatures replay internally and native IDs only echoed when supplied. Schemas/raw usage validated before dispatch/SDK coercion.

BM-09/T05 only: host keys never enter actor tools; no live credential retrieval/admission bypass. BM-11/T05 only: typed correlation/error/unknown evidence, not scoring/export. Real MCP protocol/schema/49-and9 arithmetic, owner-only declared write-once output files/16MiB aggregate quota, no path/link escapes, nonblocking total pipe write/read deadline and owned process stop, authenticated single-use Unix gateway to installed Harbor host client. In-memory gateway is NOT a durable paid fence; actual claims/spend remainT07.

## Tests actually run, results and evidence

`t05-checks.json`/`t05-source.sha256`/`t05-commands.md`:120 new tests (95 provider/25 bridge),467 combined backend INCLUDING120,7 adapter guards,12 Node passed. Ruff5 files; source checkpoint654 tracked files/0 scanner findings, final artifacts rescanned. Original15, legacy providers/dispatch/Harbor, locks/SQL/OpenAPI unchanged. Only paid vendor HTTP is mocked, as approved plan requires; tool/process/filesystem/socket paths are real. No final failures/skips.

## Failed, blocked and not-run checks

Earlier collection failure preceded implementation. Tests exposed ordered-content omission, bool RPC ID acceptance, missing schema preflight/direct stdio enforcement and4 raw token coercions; repaired/reverified. HTTPConnection test harness fixed to use closing; redirect classification repaired without following redirects. Existing Authlib deprecation remains. Initial Git credential prompt canceled; ephemeral refreshed authentication used without config changes/reset/force. Evidence metadata script initially used host Python; rerun under actual locked3.12. Full details/raw-log hashes preserved, not relabeled as prior passes.

No T05 native Docker trial or SQL/API/browser/full acceptance run. Installed Harbor host client + real process tools are NOT native container qualification. T04 evidence remains historical and does not qualify this new profile. Actual model/task live smokes are Blocked: exact models/rights/keys/budgets/operator activation absent, no invented selections. T06–T10/QA/merge/deployment not started.

## Compatibility, migrations and remaining risks

Additive separate offline profile; no migrations/dependency changes/routes/default flag changes. Legacy single-action adapters and limits unchanged, all15 approved artifacts preserved. No Docker/SQL/shared/runtime permission/Praxis/Mac/cloud/auth changes. Fresh owner-only test paths only; prior vaults/config untouched. Unknown usage is not0; no model-performance/production trust/admission claim. Live/durable integration, actual model-supported controls and new native-profile qualification require their later explicit scopes.

## Human Coding handoff — not QA

T05 implemented and focused offline-qualified; STOP for human review of `bb7713fdcee6a187a99daaa04b60c8f9f8afac63`. PR16 stays draft. No autonomous next task. Actual approval of resulting T05 code/next role is PENDING, not inferred from user being away. Exact resume at top of BENCHMARK-PROGRESS.md; keep source/input hashes when reviewing.

---

## Historical reports below — unchanged; current T05 status above supersedes

# Current implementation report — T04 approved fictional slice qualified (Coding)

## Approved task and input revisions

Actual user authorized only two exact pinned Docker Hub operator preloads and isolated T04 SQL/native qualification; exact quote appended22096aa. Prior approved specification/design/plan and original15 artifacts remain byte-identical. This is Coding with unchanged LLM connection, NOT QA/release or live authority.

## Changed behavior and source revision

Final source 38cc1513aaee1069b69392b80566d23cb45d216a/tree 0fe379b77c4168bb905a76d1d83f13c3faa7ca30; native launched atd5a97b5, with identical runtime/SQL/Harbor bytes and exercised native test function at final source (5 additional SQL tests/docs only). `t04d-source.sha256` binds files. Recovered044/045 now exercised on real PostgreSQL. New additive046 freezes image/tool-schema inputs and requires current author/review/rights, fresh operation capture and unique qualification reuse. Old migrations and immutable rows unchanged; old rows lacking new hashes cannot qualify without successor build. Worker checks source review again after capture lock.

## Requirement coverage

Approved local fictional T04 slice: deterministic actor-only build, exact input/source/compiler/adapter/tool/evaluator/private-rule/calibration binding, durable immutable qualifications, stale current-policy gates, G1–G5 and9 real software-conformance trials. API queues native work only, never accesses Docker. Missing actual execution profile/authority remains Blocked/ready=false. This is not general imported image/evaluator qualification, a full benchmark implementation, Bodhium or model performance.

## Tests actually run and results

`t04d-checks.json` / `t04d-commands.md`:314 backend (233 software+81 real SQL/API), separate1 native durable testcase containing9 actual Harbor trials/4 resources,3 stale package/private negatives,7 adapter guards,12 Node pass.17 new SQL capture/immutability/race checks. Native positives24/6/51 from real stdio square tools;6 empty/guardrail trials0. Actual3 qualifications/1 operation report persisted and hash-verified, no reclaim, trust revocation yields stale and not Ready.22 native containers stopped/retained. Fresh/repeat046 independently verified plus045->046 upgrade/repeat. Ruff check/format15 files pass; source checkpoint secret scan646/0, final evidence rescanned; all15 original artifacts unchanged. No final failed/skipped executed checks; native deliberately deselected from combined count.

## Earlier failures / not-run limits

2 SQL negatives initially accepted wrong image/tool hashes; fixed046, all pass. Actual project-lock contention exposed pre-lock-only review check; fixed inside-lock check. Observer initially cached PostgreSQL statistics, corrected with pg_stat_clear_snapshot; no mocked lock test. Two long setup/event reads hit tool soft timeout; follow-up head/process/receipt/container verification succeeded, no daemon reset/native retry. Docker recent256-event sample is bounded, not full audit. Existing Authlib/deprecated --time warnings remain.

Full QA/browser/acceptance, general profiles, T05–T10, actual Bodhium/model/judge/paid, merge/deployment not run or authorized. Historical failed SDK/recovery records preserved, not rewritten as success.

## Compatibility, operational state and human review boundary

New dedicated workspace-local VFS daemon, only two exact approved images; PostgreSQL17.6 non-root/read-only/network-none/no ports/private Unix local trust. No shared socket/permissions/Praxis/Mac/cloud/auth changes or old credentials/config/dependencies copied. Main private test DB remains running to preserve ephemeral SQL evidence; independent fresh046 DB and22 native containers stopped/retained, no deletion. Features off by default; source/signature/local fixture review does not grant paid or production authority.

Bounded approved fictional T04 Coding slice complete and focused-verified; STOP for human Coding review of 38cc1513aaee1069b69392b80566d23cb45d216a. PR16 stays draft. No automatic T05–T10/QA/merge/deploy transition. Real data/models/judge/rights/budgets remain missing and Blocked, not invented. Exact source/resume at top of BENCHMARK-PROGRESS.md.

---

## Historical reports below — unchanged; current status above supersedes

# Current implementation report — T04 restart; SQL/native blocked

## Approved task and input revisions

Current user explicitly re-authorized T04 Coding/recovery and normal checkpoints; exact approval is appended to `approval-log.jsonl`. Original15 approved artifacts unchanged; specification44196cae…, architecturec200d135…, plan1cdf87e4… full hashes in `approved-input-snapshot.json`. Existing LLM connection unchanged; role Coding. No next-role approval inferred.

## Changed behavior and source revision

Focused-tested source `c0f98b24de4aaeb8ebc72cbd4e6f8ed3eb5d4534`, tree `c161214346de7bd19bb047e968addb93438cc14a`. Recovery checkpoint23bb8f1 reconstructed11 source files from28 successful read-only edit events. `t04-recovery.json` binds provenance/initial hashes; NOT a byte-exact old workspace snapshot. Old sandbox remains ERROR, detailed cause unknown, not resumed/mutated. No private exhibits, credentials, config or dependencies copied.

Recovered immutable build/review/qualification SQL044/045, queue/fence/lease/cancel worker and API DTO/routes remain WIP. Continuation hardens exact typed native/resource capture, source/private binding/digests/receipt-byte hashes and fresh actor/evaluator identity; hashes actual fictional rules/calibration/evaluator/tool payloads plus policy source; fixes real long Unix socket failure with a fresh short private gateway. OpenAPI regenerated. API does not dispatch Docker; qualification queues for explicit operator. Local fictional review grants neither production trust nor execution authority. Defaults off; readiness false.

## Requirement coverage

Partial T04/BM-03/04 and TM-06/08/09/14 contribution, NOT full acceptance. Actual SQL immutability, authority/cancel/lease/race guards and native G1-G5 require isolated verification. General evaluators/images/Bodhium/performance admission not implemented or inferred.

## Tests actually run, results and evidence

`t04c-checks.json`, `t04c-source.sha256`, `t04c-commands.md`:233 backend (173 existing +60 new),7 adapter guards,12 Node pass; final failures/skips0. New manufactured receipt documents exercise actual validators, not native outcomes. Real signature/parser/compiler/filesystem/Unix-socket paths run without mocks. Ruff lint/format15 files pass, OpenAPI generation pass, original15 byte-identical to1b4f412; source checkpoint scanner640 files/0 findings. Final evidence checkpoint rescanned separately.

## Failed, blocked and not-run checks

New capture tests initially27 failed/13 passed; repaired. New gateway2 tests reproduced AF_UNIX length, then inherited setgid-mode assertion; fixed only fresh owned directory mode. Dependency tests initially lacked new explicit filesystem-root parameter; final5 pass. Detailed actual earlier counts and local-log hashes in check report. Authlib deprecation remains.

**Blocked/not run:** migrations044/045 fresh/repeat;44 existing SQL/HTTP/filesystem tests;21 collected pipeline tests (collection is not execution); durable native matrix/resources;045 SQL partial/forged-pass negatives still need adding/verifying. No dedicated daemon/socket or preloaded approved images exists here. Historical217 backend/9+3+4 native results do not qualify current source. Full historical SHA256SUMS also names2 excluded unavailable local-only inputs; they were not fetched/replaced/claimed reverified. Original15 tracked artifacts independently equal.

## Compatibility, migrations and remaining risks

Only additive044/045/new SME profile; no legacy importer limit relaxation. Recovered SQL and worker authority/fencing/capture/concurrency semantics remain unverified WIP and need real negative checks/repairs. Source changes stale earlier qualification. No app/cloud/deployed/Praxis/Mac/auth settings touched, image pull/build/load, provider/judge call, deletion, QA or deployment.

## Human Coding review / resume boundary

Stop at environment prerequisite, not QA. Exact approved pinned PostgreSQL17.6/Python digests and isolated resume scope at top of `BENCHMARK-PROGRESS.md`. Preload into new dedicated no-network daemon before actual SQL/native checks. No substitutes/shared target/stale sessions/socket weakening. PR16 stays draft; T04 incomplete. No T05-T10/QA/paid/merge/deploy.

---

## Historical reports below — retained unchanged; current status above supersedes

# Current implementation report — T04B native conformance

## Approved task and input revisions

Actual user Yes to9f2dcc3 approved the restricted static-none/preloaded-only/no-delete Harbor plan and retrying the nine native trials. Original specification/design/plan hashes and15 artifacts in `approved-input-snapshot.json` remain unchanged; actual authority is append-only, not inferred from this report. Source commit `fbfcbb868256b809bae252709dccb2eef3900e66`, tree `b04544b27ace0c0d6b4adf9e0b29e4576b02b382`.

## Changed behavior and requirement coverage

Compiler1.0.1 corrects prebuilt relative binds and separate verifier configuration; binds private rules/calibration metadata without placing those assets in actor ZIP. New `anvil_harbor.sme` guards stock SDK hazards and mediates fixed native fixture trials; backend opt-in conformance helper snapshots/seals outputs and records source-bound evidence. No product endpoint/worker gains Docker or new execution authority. Contributions to T04/BM-03/04/11 are focused software conformance, not whole-requirement acceptance or completed durable T04. No migration, dependency lock, legacy importer/readiness/API/scoring-scale change.

## Tests actually run and evidence

`t04b-checks.json`, `t04b-source.sha256`, `t04b-commands.md`: native9 + stale-private/package3 + real limits4 pass; adapter7, existing backend217, Node12 pass. Final failed/skipped0. Actual cgroup OOM/PID/timeout and stdio overflow controls, real tool counts24/6/51, separate evaluator/canary negatives and immutable output checks observed. All18 final native containers are stopped/retained. No model/provider/judge calls; unsigned fictional source is not promoted to installed trust/readiness. Existing Authlib/Node advisories remain.

## Failed, blocked and not-run checks

Original Alpine probe failure preserved. This continuation also exposed a debug `/actor/...` bind outside trial (corrected with pre-start in-trial source checks), JSON warning contamination, absent evaluator cwd and Docker-cp/tmpfs capture failure. Terminal exit lost only ephemeral dedicated DB state; unchanged schema replayed to043. Old restored vault2770 rejected22 checks (195 passed); untouched old vault, fresh owner-only root then217/217. No fallback or permission loosening. Docker event sample is bounded, not full-history proof. See detailed handoff/check report for exact effects and local-only logs.

## Compatibility, remaining risk and human review boundary

Only reviewed fictional constant-no-network profile qualified. Source bindings invalidate changed package/image/tools/evaluator/compiler identity; durable persistence/admission/stale hooks still need implementation before full T04 can pass. T05–T10, QA/acceptance/browser/Bodhium/model/judge/paid/deployment work not performed. No private credential, Mac/Praxis/shared/deployed service or socket permission touched. Stop for human Coding review, not automatic QA. Draft PR16 stays draft.

---

## Earlier reports — superseded status, historical bytes retained

# Current continuation report — compiler/seals passed; native qualification failed/blocked

The actual current user `Ok` allowed bounded pinned-Python-only fictional native scope; see append-only approval log, not a new fabricated approval. Product source6060fd8 pushed: T04A compiler/sealing17 new checks and combined217 backend passed; scanner622 files/zero findings. Exact fixture scope/code/tool/full-manifest review and actual safe Python preflight are recorded. Original15 approved artifacts unchanged.

First real Harbor attempt failed before candidate startup. Unexpected SDK effect: pulled pinned Alpine and ran/auto-removed its new kernel probe outside allowed Python/no-deletion scope. Then platform-helper Docker permission failed; no permission workaround, sidecar build, native gate pass, QA or provider result. Stopped native execution, removed only uncommitted unsafe prototype files, retained committed fail-closed compiler. Complete evidence and proposed bounded static-network/no-auto-pull/no-delete SDK adapter change are in `t04-native-blocker.json` and current `handoff.md`. That changed implementation plan needs human confirmation before retry. No shared/Praxis/Mac/cloud/deployed service or credential operation.

Current T04 is incomplete. T05–T10 not implemented, native G1–G5/nine trials and durable qualification/API/worker still not achieved. These failures are not hidden by passing focused units. Later QA/full acceptance, real data/semantic judge/paid evaluations and release remain separately forbidden/gated.

_Prepared by OpenHands on behalf of the Product Owner; not human approval or QA acceptance._

---

## Previous reports below — status superseded; bytes retained

# Current interim Coding report — T00–T03 implemented; T04 prerequisite pending

Product source revision `08121a212424d1bb8c5ce3fbff5ae85cc1aeb2e2`, tree `3223b6b50a01ba90354458084b1063b812b8bb91`; source/check bindings `t03-source.sha256` and `t03-checks.json`. Current status and exact resume commands are in `BENCHMARK-PROGRESS.md` and current `handoff.md`. The report below is preserved historical T00 evidence; its former no-code/no-environment/no-push statements are superseded only by later actual approvals and checked work, not rewritten as past success.

- Completed now: T00 full exact recovery; T01 strict independent SME contract and original arithmetic fixtures; T02 additive private/canonical/financial foundation; T03 bounded private stream/status/error receipts, exact-byte idempotency/quarantine, atomic safe projections, quotas and cleanup. Product feature defaults off.
- Passed now:200 focused backend checks (44 real isolatedDB/HTTP/filesystem/concurrency),12 configured Node policy checks, migration043 upgrade/repeat, lint/format/whitespace/source hashes and scanner617 files/no findings. Final failures/skips0; old advisory warnings only. Approved15 inputs unchanged.
- Not claimed: complete BM01..12 acceptance, native Harbor isolation, real Bodhium results, model/judge performance, full QA or deploy readiness. No cloud/shared/Praxis/Mac/paid call actions.
- Pending T04: approved native fixture image plus reviewed installation evaluator binding, then actual G2 proof. Fixture metadata is explicitly unqualified/unreviewed. Proposed exact local-only prerequisite review is in handoff/progress; do not bypass it or fabricate review authority.
- Current actual approvals are append-only in `approval-log.jsonl`; no next-role or native prerequisite approval is fabricated. Normal per-step commits/pushes and one draft PR16 are explicitly authorized and recorded; original recovery/code/approval inputs stay preserved.

_Prepared by OpenHands on behalf of the Product Owner; not human approval or a QA result._

---

## Historical T00 report below — superseded status, bytes retained

# Coding-stage report — T00 recovered; benchmark implementation not started

## Approved task and input revisions

Human message in conversation `fdd0cf03f01748698589fa2401680560`, headed `USER APPROVAL 2026-11-07`:

> I approve the benchmark architecture and implementation plan. Run the Coding agent in OpenHands, resolve the source recovery gaps first, keep Praxis and my local changes untouched, and stop for my review before QA or deployment.

The exact actual approval is recorded append-only in `approval-log.jsonl`, followed by a separate T00-verification event. Approved originals remain unchanged under `../anvil-praxis-bodhium-benchmark-2026-11-07/`:
- Architecture SHA-256 `c200d135bd9dbe171b63e13833349a6486d09adff17c5c27daf870d46c6cf68a`.
- Implementation plan SHA-256 `1cdf87e4d48bc483a2e5116509e83d07b35f2652b95c032635b98bbe0e3f9749`.
- Product specification SHA-256 `44196cae04b7a399fb70da8d4577345b2cf95ee6a14daa41f3d8c8f2b4921cbc`.

Role: `anvil-coding`; read recovered AGENTS.md, workflow and Coding/report/handoff templates. The working ADI-Architecture LLM connection was not switched. This is an incomplete Coding-stage report, not implementation completion or a QA handoff authorization.

## Changed behavior and source revision

**No benchmark feature or new product behavior has been implemented.** The completed work is original-source recovery plus a focused baseline check.

The old Anvil sandbox, previously ERROR, now reports RUNNING/finished. Only read-only file/API GETs were used; no command, agent resume, reset or filesystem write was issued there. GitHub still has no r6 commit/tree/releases/actions artifacts. The old sandbox yielded:
- Original `deployment-evidence/release-r6.patch`, 152,768 bytes, SHA-256 `3e3552e21f37388aca0f7985c54e169f54ce02bc318b0368ec19e334b6389e66`.
- Original compressed Git commit object, independently verified as `15e35f12725a89be6e507b2eb73d4433e666dd76`, with parent `8cdc8a84784c7ae52d7bbb88f36193b387aedb60` and tree `18fca788310f91a35a54df39392a37c026ae16b1`.
- Original `finalization-evidence/code-manifest-r6.sha256`, SHA-256 `5c15faf05331d58b26342ce7a40d8b0df5f4be62d2619a2840fbf0cdab3f7c7b`; all 30 source entries pass.
- Hash-bound historical finalization implementation/security/QA reports and QA handoff, actual prior approvals, deployment report/handoff, and original readiness PRD/design/plan. These are historical evidence, not a new QA run or deployment verification.

The patch was applied with `git apply --index` to a pristine isolated base comparison clone. `git write-tree` produced the exact expected tree. All 264 Cloud Build files matched. The existing release object was imported locally without creating a new commit, changing the current branch, or pushing. All **504** release tree files and executable modes then verified in `/workspace/anvil-recovered`.

T00 source gate: **PASSED**. The previously partial composite tree is not used as the current baseline anymore. The approved design's earlier recovery caveats remain preserved as historical facts; this report is the successor recovery evidence rather than an edit to the approved documents.

### Restored file scope

Nine recovered build-overlay paths were already correct. Twenty-one additional historical paths were restored (full list in `t00-source-verification.json`):
- `BUILD-STATUS.md` and `contracts/readiness/reason-codes.v1.json`.
- Fourteen integration fixture/test paths, including the original `journey_support.py`, `test_finalization_concurrency.py`, and changes to API security, budget, factory, import, isolation, worker, access, diagnostics, editor and execution tests.
- Original unit `test_readiness_reason_codes.py`.
- Three original browser specs and `tests/readiness_catalog.mjs`.

These are **recovered historical source**, not newly authored/reconstructed tests. Existing isolated source content was compared to base or verified release bytes before any restoration; no conflicting user edit was overwritten. Original conversation checkout `/workspace/project/adi-anvil`, Mac, Praxis, deployed services, private key/credential files and auth settings were not changed. No credentials/runtime directories or deployment raw logs were copied. Recovery inputs stay under `recovery-evidence/r6-original/`, outside any web-served path.

## Requirement coverage

T00 baseline/provenance prerequisites for BM-02/06/12 are satisfied. Recovered security guidance preserves project→run→job/episode locking, no shared-to-exclusive project lock upgrades, transition-once finalization, and no provider/network work within guard transactions. Historical test limitations remain explicit; reading historical QA reports does not invoke the QA role.

T01–T13 benchmark implementation/acceptance is not complete. No new schema, fixture bank, migration, endpoint, provider adapter, evaluator, scheduler, scoring or UI was authored in this stage. Missing real Bodhium inputs, exact model/judge IDs, rights and budgets remain blocked, not invented.

## Focused checks actually run

| Command/check | Observed result | Evidence |
| --- | --- | --- |
| Pristine base + original patch: `git apply --index .../release-r6.patch`; `git write-tree` | Exact expected tree `18fca788310f91a35a54df39392a37c026ae16b1` | `t00-source-verification.json`; original patch and comparison repo |
| `sha256sum -c ../historical-run/finalization-evidence/code-manifest-r6.sha256` from verified-source comparison | 30/30 entries OK | Original manifest; independent source verification |
| Verify commit object SHA-1, tree/parent, all 504 file blobs/modes and 264 archive hashes | All match | `t00-source-verification.json` |
| `node --test tests/provider_failure.mjs tests/readiness_catalog.mjs` from `/workspace/anvil-recovered` | 12 passed, 0 failed, 0 skipped, exit 0 | `focused-readiness-check.tap`, `focused-check-results.json` |
| `git diff --check 15e35f12725a89be6e507b2eb73d4433e666dd76 --` | No whitespace diagnostics | Read-only focused source check |
| Rehash all 15 approved run-folder files | Unchanged | `approved-input-snapshot.json` and appended approval log |

First Node-check invocation lost the terminal session due to a top-level shell exit; its result was not relied on. It was rerun with a non-exiting status check and passed reliably. No model-profile workaround or product change was made for that terminal issue.

## Failed, blocked and not-run checks

**Environment blocker before dependent implementation:** backend requires Python `>=3.12,<3.13`; this runtime has only Python3.13.15, no backend `.venv`, and no pytest/Pydantic/cryptography/FastAPI/psycopg. pnpm is absent. Node24.22.1 and uv0.13.5 are available. No dependency installation has been attempted. See `environment-preflight.json`.

The development workflow requires consulting the user before investing in a full missing test environment. Unverified implementation or tests against an unsupported interpreter would not be a quality substitute. Backend contract/unit/integration checks, finalization DB races, frontend type/build/browser checks, Docker/Harbor, migrations and app startup are **Not run** here. Full QA role/acceptance and deployment were not invoked. No live candidate/judge calls, model keys, paid inference, cloud/IAM writes, auth changes, commits or pushes.

## Proposed local setup requiring confirmation

Please confirm installing a repository-local Python3.12 interpreter and the locked backend environment from `services/backend/uv.lock`, plus pnpm10.34.5 and locked frontend dependencies from `pnpm-lock.yaml`, with caches/tooling confined to `/workspace/anvil-recovered`. Use only official package sources, no package-manager config changes, no global install, no copied sibling environments/credentials. Do not start application/Docker/database/Keycloak services or change auth settings as part of this initial setup. After confirmation, continue approved T01 onward and run focused checks; any later local service prerequisite must remain isolated and explicitly reviewed.

No broader design reapproval is requested: the approved architecture/plan remain approved. This question concerns the missing execution environment, not a waiver of security/source/authority gates.

## Compatibility, migrations and remaining risks

No new migration/config/lockfile change. Full r6 recovered source remains exact. Historical r6 evidence reported 19 optional Docker/Harbor/Praxis tests blocked and some full-browser/security/accessibility checks not run; these have not been relabeled passed. The deployment's uncommitted environment-specific deployment.json change was not imported into source. No old private gcloud directory, SSH key, runtime credentials or shared backend was used.

## Human review / next step

Status: **T00 complete; benchmark coding blocked pending isolated dependency-setup confirmation**. Source approval was not waived. Human code review remains mandatory before QA or deployment. No automatic next-role transition occurs.
