# Benchmark threat model — DRAFT v0.1

Source and authority: `architecture.md`, `approved-specification.txt`, `approval-record.md`, `recovery-report.md`. This is proposed threat coverage, not verified security evidence. Full r6 tests/history remain unrecovered. No negative application test, sandbox, model or cloud operation was executed.

## Assets and boundaries

Assets: restricted source/rights; private oracles/calibration/judge prompts; credentials; immutable package/protocol/output/score/audit hashes; project identities; candidate/judge reservations and unknown charges; host/tool integrity/availability; truthful measured/fixture/reference provenance.

Boundaries: (1) untrusted Praxis archive → parser/quarantine; (2) scoped user/API → PostgreSQL/RLS/artifacts; (3) trusted compiler/host broker → no-egress candidate/tools; (4) sealed output → separate evaluator/judge broker; (5) private evidence → permitted result/export/publication; (6) queue/restarts → dispatch/cancellation/finance; (7) recovery artifacts → source identity claims.

Threat actors: malicious exporter/signer, same-project unassigned viewer, cross-project user, prompt-injecting candidate/tool/report, imported malicious evaluator, stale/duplicate worker and accidental Admin misconfiguration. A hostile root/Docker host remains outside container isolation guarantees and is a residual infrastructure risk.

| ID / threat | Required control | Future evidence |
| --- | --- | --- |
| TM-01 Forged/repacked source or bundled trust root | Detached canonical-manifest signature, configured roots/key validity/revocation, payload hashes, exact immutable source/version conflict; signature is not rights | BM-01 known/unknown/revoked signer, bad canonicalization/hash, undeclared file, concurrent duplicates/changed bytes |
| TM-02 Traversal/bomb/alias/device/hook execution | Stream byte/file/header/path limits, only safe regular files, collision rejection, staging before acceptance, no imported code runs | BM-01 absolute/dotdot/drive/backslash/control/Unicode-case aliases, links/devices/bombs, chunked/disconnect/quota, no partial acceptance |
| TM-03 Cross-project/role/assignment access or confused destination | Auth context + FORCE RLS/composite FKs, server-owned project, current two roles plus individual evaluator assignment, checks on jobs/polls/downloads | BM-04/09/11 two-project full route matrix; lineage project IDs cannot redirect/import roles |
| TM-04 Private rubric/oracle leakage through raw archive/package/notebook/API/log/export | Private raw/eval vault classes/mounts, generic route hard-deny, actor allowlist, separate evaluator identity, redacted diagnostics; no candidate eval mount even mode0700 | BM-04/09/11 canaries and actual access attempts across env/process/filesystem/tool/API/trajectory; legitimate shared numbers reviewed, not blindly rejected |
| TM-05 Host/network/metadata/socket/secret escape | Non-root, read-only root/inputs, no key/DB/socket/host mounts, effective no-egress/metadata denial, canonical workspace tools and no symlink escape | BM-04 forbidden access denied plus legitimate computation; inspect actual runtime policy |
| TM-06 Imported evaluator/image privilege | Inert source scripts, reviewed registry/compiler, pinned image/code/tool digests, no auto-run/pull/build; evaluator no DB admin/socket/unrestricted egress | BM-03/04/08 unreviewed binding blocked, changed digest stale, evaluator least-privilege and no candidate writes |
| TM-07 Prompt injection, forged evidence, biased judge | Candidate output is data, blinded judge context, no browsing/execution, strict criterion IDs/bounds and server totals, hash/span evidence verification | BM-07/08 injected report, missing/duplicate/extra/NaN criteria, false/contradictory citations, paraphrased correct vs keyword-only wrong |
| TM-08 Tool/REPL process/output/transcript exhaustion | Frozen turn/call/byte/time/CPU/RAM/PID/output quotas, whole owned process-tree termination and bounded rendering | BM-03/04 spawned-child/time/memory/output exhaustion; no unrelated PID/process deleted |
| TM-09 Duplicate paid dispatch after lease loss/restart | Unique durable cell/attempt/turn intent, fencing, no ambiguous retry, unknown capacity quarantine, network outside transactions | BM-05/06/09 intent/send/capture crash matrix, duplicate launch/claim, reservation retained and no second send |
| TM-10 Budget/rights/key/model escalation | Exact scoped versions/destinations, separate candidate/judge windows, conservative pricing bounds/expiry, current Admin/activation, no global fallback/retry | BM-05/09 expired/revoked rights/key/pricing, usage/model mismatch, purpose caps, pure readiness |
| TM-11 Cancellation/finalization deadlock or lost counter | Recovered project→run ordering, window-before-run finance order, transition-once unique effects, deterministic cutoff/late capture, no locks over I/O/network | BM-06 siblings/duplicate finalization/cancel races/revocation/restarts; actual r6 regression tests recovered first |
| TM-12 Denominator laundering/rerun bias/incomplete winner | Frozen 81-point exact arithmetic, valid failure vs operational invalidity, incomplete primary null, immutable adjudications and attempt history | BM-07/08/10/11 zero/full/partial, timeout vs outage/judge failure, no best attempt, 24/6/51 coverage and export equality |
| TM-13 XSS/CSV/export/share leakage | Inert bounded Markdown, safe links, formula escaping, server redaction and repeated download/rights checks; no private judge prompts/reasoning/keys | BM-10/11 active HTML/link/CSV payloads, expired share, cross-project download, private-redaction checks |
| TM-14 Recovery/release claims exceed evidence | Preserve raw bytes, independently verify archive/worker, distinguish composite vs full r6 tree, classify omitted paths | Recovery records now; BM-02/06/12 later require full patch/manifest/tests or explicit newly audited baseline acceptance |
| TM-15 General/old worker claims new jobs on rollout/rollback | Dedicated kinds/claim functions/identity, additive gated migration, drain/fence before image rollback | BM-06/12 fresh/upgrade/rollback rehearsal; old/general worker cannot execute new evaluator jobs |

## Security review and release gates

Quarantine, private artifact access, effective sandbox/no-egress, exact financial authority and durable finalization are release gates, not optional UX polish. Secret scans supplement real access/isolation tests. Rights revocation blocks new inference/judging/publication and follows approved retention rules for existing evidence; never erase audit or silently delete partner data.

Residual risks: missing historical r6 changes/tests, compromised signing key/trust admin, hostile host/root, exhibit resource requirements, provider retention/model snapshot behavior, judge variability/calibration, reviewer bias, low power of two repetitions, missing partner rights. Inputs/decisions remain explicit in architecture and plan; none has been invented to close a risk.

Outcome: **DRAFT THREAT ANALYSIS COMPLETE; CONTROLS NOT IMPLEMENTED/TESTED; HUMAN DESIGN APPROVAL PENDING**.
