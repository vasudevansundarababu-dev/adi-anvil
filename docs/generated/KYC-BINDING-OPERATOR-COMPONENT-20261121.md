# Separate KYC binding-operator component

Implemented and locally tested; not deployed or independently qualified yet.
This follows the requested separate Core, Environments and Evals/Bindings phases.

The native executable images/source remain immutable8a22280, Golden source
0ad34c122a56e9fa1f83bce6f2c09e8fe672d946a3f6b25222fae391238c4368.
Their physical component observations ran against isolated schema134. Migration135
adds only scoped SELECT access for an existing disjoint enrolled qualifier to
eight public banking/environment/evaluator tables. It does not change native
actor/grader code, API/runtime role permissions, private answer access or writes.
No LOGIN, principal enrollment, owner review or run authority is created.

The SQL, Alembic wrapper and observer are independently pinned operational
artifacts. Stage them outside the native image/source tree. Final deployment
acceptance must bind both the original native134 evidence and the operator135
evidence and explicitly report actual schema135. Never relabel native134 traces
as135 or edit an old reviewed component receipt to attach new observations.
A new composite reviewed receipt must carry the new evidence and review hashes.

Existing permissive PUBLIC policies could otherwise admit an unenrolled role
using a forged Admin/project GUC. Each new table read therefore also has an
AS RESTRICTIVE enrollment predicate. The predicate binds actual session_user,
current project/user GUCs, exact enrolled principal and current real Admin status.

The observer derives original scope with policy_scope, executes existing import
integrity validation using one bounded software resource proof, checks actual
saved evaluator/configuration/receipt identities and runs actual saved native
ZEN scoring controls. Copied-input negatives are labelled as such. It emits
observed_not_qualified; no uploaded pass flag is a qualification. Generic other
configuration checks are labelled software integrity, not substantive KYC grading.
The CLI uses a read-only transaction, a five-minute deadline, exclusive owner-only
output and sanitized failure text. It never reads private expectations.

Local verification:15 observer-validation tests passed, including self-consistent
rehashing of stale/generic programs and unsupported reset-contract negatives.
Migration135 upgrade/repeat passed. Ten actual SQL role/grader/private-review
tests passed on a new marked synthetic clone, including an enrolled real LOGIN,
known foreign rows, forged GUC/unenrolled/revoked-owner denial, private-read/write denial and
unchanged grader/review behavior. First fixture attempt omitted the foreign
project's actual author GUC; corrected the synthetic fixture, not application
authorization. This is separate from QA physical acceptance.
The observer's actual catalog/RLS preflight also passed under that LOGIN. Its
initial private-privilege check hit the intentionally denied private schema;
fixed it to inspect catalog OIDs, preserving the schema denial. It also checks
forced row security and exact permissive/restrictive policy definitions.

Remaining: independently verify the exact deployment artifacts; apply134/135
with backup and compatibility checks; provision an explicitly authorized bounded
operator enrollment; run the observer on actual stored bindings; independently
review/publish new scoped runtime-control evidence; consume genuine owner policy
and expectation decisions. Method/safety/exact B1 qualification remain separate.
