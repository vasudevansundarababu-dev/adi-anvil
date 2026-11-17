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
November17 continuation: user explicitly directed finishing/testing RL Gym while
Authoring exports and another small fix are pending. Authoring integration and
live calls remain deferred. The existing reviewed Marketing test fixture pack is
used only for software controls; it is not the user's three pending exports.

Original runtime build b7f3a4bf-71c5-47af-b595-7af57b683ad3 succeeded; KYC,
Marketing and private evaluator images were pulled onto QA. Installed-source and
14 evaluator controls passed. These images were not serving workers. Subsequent
review found scheduler OPA missing despite successful library imports.

New source adds exact-hash OPA and a bounded software-only service. The standalone
Compose configuration uses distinct names, separate role env files, no inherited
app configuration, no mounts/ports/privilege, and an explicit existing DB network.
The supervisor owns each process group, stops descendants on timeout/exception
and normal completion, retains interrupted custody and never restarts failures.
Read-only code review reproduced and verified repair of a SIGTERM-resistant
descendant leak. This is code/process review, not native qualification approval.

Recovered current tests omitted by the sealed release; repaired stale fixtures
for original deadlines, bounded cleanup reserve, service records and pricing
expiry. Pricing data itself remains unchanged and expired prices stay blocked.
Development OpenEnv now explicitly uses the current editable checkout; production
runtime still installs separately frozen hashed wheels with no path overlay.

Fresh/repeated schema127 and28 actual PostgreSQL tests have passed, including
200-cell disjoint KYC capture/grade/report and twelve Marketing graph windows.
Final regression and installed-image policy/source build checks are in progress.
No full-product stability, native qualification or paid benchmark claim.
