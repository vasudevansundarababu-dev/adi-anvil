# ANV-BF-001 — Task Profile and deterministic benchmark recommendation

Authorized 2026-09-29. The user confirmed that this increment replaces the earlier
GEO/intent-gap case-first order and that missing benchmark metadata may extend the
existing resource/revision registry. Those cases remain undefined and are not fabricated.

## Scope and requirements

- ANV-TP-001–005: select existing published task revisions under an approved objective;
  show evidence/confidence for inferred dimensions; confirm all required dimensions;
  persist an immutable profile; expose heterogeneity and segmentation advice.
- ANV-REC-001–008: register catalog metadata from existing qualified synthetic tasks,
  compute hard compatibility/access/rights filters, deterministic weighted ranking,
  explanations, gaps, coverage and explicit unknown cost/runtime estimates; suggest
  bounded composition; record threshold, policy, exact versions and override rationale.
- Create a normal Eval Suite draft bound to exact benchmark/profile/recommendation
  revisions. Low coverage offers a prefilled benchmark draft, never publication.

The existing catalog abstraction is the shared resource/revision registry: no new
database, server, task catalog or execution runtime. Registration is metadata only;
it does not imply three-case smoke validation, paid authority or a scientifically
validated benchmark. Preserve original_synthetic_fixture provenance in storage and
display ADI synthetic, never Bodhium.

## Non-goals

Live calls, schedules, 100,000-task execution, adapter implementation, new partner
rights, generated tasks, full manifest publication, and marketing-runtime replacement.

## Acceptance and definition of done

A Researcher uses the existing shell to select tasks, inspect and confirm a profile,
register metadata, obtain repeatable ranked results with exclusions, choose catalog
versions into a suite draft, and save an uncovered-requirements draft. Enforce project
membership, active assignments, current qualified revisions, rights, immutable
snapshots, optimistic concurrency where applicable, audit and idempotency server-side.
Bound selection/catalog queries; refuse truncated recommendation scope rather than
silently rank partial results. No hidden reference text is used in matching.

Affected areas: backend factory service/schemas and additive migration017, existing
suite qualification, web Console/Factory/Help, unit/integration/browser tests, migration
smoke and build/status documentation. Run native checks/build, unit, browser and
integration regressions; verify fresh/repeated migrations in a retained isolated DB.
Report exact results and remaining gaps honestly. No destructive rollback or remote push.
