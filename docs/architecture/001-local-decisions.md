# Local implementation decisions

2026-09-28. Authorized eight-hour local build; single writer.

- Web port 3202 replaces 3200 because 3200 and 3201 were occupied. No unrelated process stopped.
- Next 16.3.6, React 19.3.0 and Tailwind 4.3.3 resolved independently from npm. Python 3.12.14 was already available; isolated backend virtualenv and uv.lock created. Exact transitive versions are in lockfiles.
- Images initially pinned to PostgreSQL 17.6-bookworm, Neo4j 5.26.12-community and Keycloak 26.3.5. Image digests and advisory review remain M7 verification work.
- Canonical typed content uses the specified shared resource/revision registry and Pydantic models, normalized composite project foreign keys, review/rights/assessment/job tables. psycopg transaction services are used directly; SQLAlchemy backs the Alembic migration runner. Additive migrations 001–004 are tested from an empty database and through repeat upgrade. Fully normalized typed detail tables remain a baseline compatibility gap.
- Every stored content revision is immutable, including draft snapshots. Draft editing appends another revision; approvals bind exact revision/hash.
- Runtime API and worker identities are nonowner/non-superuser without BYPASSRLS. Worker cannot read hidden-reference artifacts or rubric content. Migration identity alone owns schema/library checkpoint setup.
- OIDC code flow uses PKCE, browser-bound single-use state, nonce, RS256 issuer/audience/expiry checks and encrypted verifier. Browser receives only opaque session/CSRF cookies. Invitation identity is issuer+subject.
- General uploads remain quarantined. Only registered original fixture hashes can enter the trusted local importer. Import creates drafts with no automatic rights, qualification or paid approvals.

Reference checks: [Next installation](https://nextjs.org/docs/app/getting-started/installation), [Keycloak container guide](https://www.keycloak.org/server/containers), [PostgresSaver](https://reference.langchain.com/python/langgraph.checkpoint.postgres/PostgresSaver). Resolved APIs are also inspected in local installed packages.

Continuation decisions: immutable image digests were recorded from the locally installed official images. GitHub action tags were resolved through the official repositories and pinned to commit hashes in a local-only CI draft. Dependency update configuration follows [GitHub's ecosystem reference](https://github.com/github/docs/blob/main/content/code-security/reference/supply-chain-security/dependabot-options-reference.md) and [uv's Dependabot guidance](https://docs.astral.sh/uv/guides/integration/dependabot/). No remote or CI execution occurred.

Reports now persist the evidence ZIP as an immutable artifact alongside the PDF/HTML. Successor revisions invalidate old approvals, and current rubric/task/objective/protocol/rights checks guard downloads. Aggregate definitions explicitly separate pending/cancelled/invalid/unknown episodes and retain null averages for zero valid denominators. Earlier synthetic reports with a previous aggregate shape must be regenerated and reviewed; they are not silently rewritten.

Mail is a strictly network-free fixture workflow with `.invalid` contacts, distinct local sender-Admin activation, exact Product Owner approval and terminal simulated acceptance/failure/unknown states. This is not a real sender connector or paid authorization mechanism. No email SDK or network-send path is installed.
