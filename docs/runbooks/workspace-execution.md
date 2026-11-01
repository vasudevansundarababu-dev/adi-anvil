# Run tasks through execution groups

Current policy: [two roles and separate screens](../product/22-TWO-ROLES-AND-EXECUTION-GROUP-JOURNEY.md).
This supersedes earlier Product Owner, two-Admin and local authority-file instructions for
modern execution groups. Those older decisions remain historical evidence.

1. Open **Tasks** and select **Run**, or open **Execution groups → Create execution group**.
2. On the separate Create page, select the exact task package, execution preset, model
   versions, output/time limits and aggregate USD budget. Create saves immutable records,
   sends no model request and reserves no money.
3. Creation opens the group's separate dashboard. Review the model versions, budget and
   any setup blockers. Creation fields and the group list are on other pages.
4. An authenticated project **Admin** selects **Run**. This action records the exact task/model/key/
   pricing/terms binding, processing-rights confirmation and budget; no Product Owner,
   second Admin or separate approval form/file is needed. A recent sign-in is required.
5. The dashboard shows each model run's state and **View run dashboard** link. Individual
   run dashboards expose captured results/failures, observed trajectories, immutable task/
   rubric/evaluation snapshots, usage and compatible metric comparisons.
6. **Execution groups** returns to the list. **Task → View run history** scopes retained
   runs to that task. Saved preparation URLs remain read-only compatibility views.

## Two access roles

Admin includes RL Engineer work plus keys, model/framework configuration, access and exact
budget authorization. RL Engineers create/import tasks, prepare execution groups, run an
already authorized group, inspect results and perform individually assigned grading duties.
They cannot authorize new paid scope or read unassigned private references. Grading and
adjudication assignments are duties, not additional access roles; run authors cannot claim
independent grading of their own run. Admin self authorization is recorded in audit.

Migration033 archives old memberships, keeps existing Admins, migrates other members to
RL Engineer, and restricts each person to one active role per project. It preserves all
identities, synthetic provenance, passwords, historical decisions and task/run bindings.
Migration034 stores immutable project-scoped Admin authorizations and append-only
revocations. A revocation or inactive authorizing Admin stops further dispatch. Existing
Admin accounts can authorize their exact scope regardless of seeded origin. Identity-origin
metadata remains unchanged for audit; no new account or invitation is required.

## Runtime and exact configuration

Live dispatch remains disabled by default and requires separately authorized runtime
activation. Building this feature does not make paid calls or enable live flags.
Saved provider keys and configurations alone do not authorize a run. The explicit Run
confirmation binds a positive exact aggregate cap with an eight-hour maximum authorization
lifetime; pricing expiry and all frozen metadata are independently rechecked before each
stage. Changed code/model/key versions require a fresh group.

Modern runs resolve only their scoped encrypted credential version. No legacy/global
provider-key fallback is used. Fixed native endpoints and exact returned model IDs,
single-request limits, admitted usage and no retries/redirects remain enforced. Native
OpenAI/Anthropic/Gemini adapters are supported; external LangSmith/Semantic Kernel adapters
remain unqualified and explicitly blocked rather than represented as executable.

## Reservation, sequencing and cancellation

Launch atomically reserves one group cap and queues all child jobs. Concurrent/replayed
launch cannot duplicate reservations or children. Each model executes after its predecessor
succeeds; operational failure, unknown outcome or cancellation stops later dispatch.
Each stage rechecks access, authorization, code, terms, prices, exact versions, secret state,
and the retained reservation. Dispatch intent commits before provider network I/O.

Cancel stops queued work and requests cancellation of active work. It cannot recall a
request already sent. Billing evidence is captured even if access/rights are subsequently
revoked. Unknown and cancelled attempts retain reservations until separately reconciled;
there is no automatic refund, ambiguous retry or silent settlement.

Secrets never enter task archives, Harbor containers, trajectories, audit metadata or error
text. SQL/artifact backup does not include local credential files/wrap key, environment or
Keycloak recovery. Restore those separately and securely; never substitute another key.

## Evidence

Synthetic checks and SDK MockTransport verification are labeled separately from actual model
performance. Predetermined outputs do not demonstrate model quality. Trajectories show only
captured stage inputs/outputs, not invented internal reasoning. Comparisons require compatible
task/evaluation signatures and origins. Live paid smoke tests remain not run under local
build authorization.
