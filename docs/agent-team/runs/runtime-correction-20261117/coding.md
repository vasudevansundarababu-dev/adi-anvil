# Runtime installation correction — 17 November 2026

Owner scope: current chat's mandatory KYC and Marketing runtime requirement,
following the prior main/QA deployment and deployment-retry authorization.
Source input: sealed build32 manifest9398adfdfe9f92cd965090370649f19b3bac49eab4fe66a7c92892a50943b763,
plus the already reviewed locked runtime packaging inputs recovered from the
existing Anvil team checkout. No sibling source or credential changes.

Observed defects: zero serving runtime observations; Golden scheduler/grader are
sleep placeholders; cached f575 runtime has older first-party source. App health
does not satisfy the mandatory deployment qualification requirements recorded in
Mandatory-deployment-and-import-runtime-gates.txt.

Bounded correction:
- RUNTIME-KYC-01: independently addressable current-source KYC runtime.
- RUNTIME-MKT-01: independently addressable current-source Marketing runtime.
- RUNTIME-PRIVATE-01: grader/evaluator has required pinned components and private
  permissions; no Docker socket, actor credentials or private-reference exposure.
- RUNTIME-EVIDENCE-01: actual observed source/image/lock/library and operation
  evidence, never seeded Ready values or invented independent reviews.

The two task identities share a single independently frozen dependency closure;
they do not splice backend/OpenEnv/Harbor site-packages. Current first-party wheels
are built offline with hashed builder requirements and byte provenance. The private
evaluator adds the existing pinned NeMo/OPA components to the current API base.
LangSmith stays deferred. Unsupported AgentDojo/BIPIA/LangChain adapters are not
advertised as installed/qualified merely by adding packages.

No paid inference, hidden-reference relaxation, authentic source approval, spend
release or existing unknown-request retry is authorized by runtime installation.
Technical runtime qualification and business/source readiness remain distinct.
Current state: packaging prepared; actual builds, operation proofs, installation
and serving observations pending. No completion or independent QA claim.
