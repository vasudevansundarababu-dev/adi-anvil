# KYC skill-to-step mapping proposal

Draft configuration research; not saved mappings, approval or performance evidence.
Read only manifest-listed public actors from unchanged ZIP SHA256
3b6d922a489e7a3d5f78f491a84f209cd1d436287f45afd6f1ca2d4e0a078128.
No private reference bodies were read. All four use the application-type profile.

Indices below are zero-based `/sections/S5/steps/{n}`. The supported UI must
return and verify each exact pointer/hash and template role `kyc_analyst` before
saving. Proposed associations use actual action/failure behavior text, not
design-register label equality. Ambiguous rows remain unbound.

| Skill | Individual | Adult joint | Teen joint | Custodial |
|---|---|---|---|---|
| profile | 0 | 0 | 0 | 0 |
| identification_parties | uncertain | 0 | 0 | 0 |
| identification_verification | 1,2 | 2 | 0,1, limited names/addresses | 0,1, limited names/addresses |
| screening | 3 | absent | absent | absent |
| account_exceptions | 4 | 2 | 2 | 2 |
| account_resolution, next_action | 4 | 2 | 2 | 2 |
| evidence | 4 | 3 | 2 | 2 |
| decision | 4 | uncertain: report only | uncertain: prepares sign-off | 2 |
| K.EXTRACT | 1 | uncertain | absent | uncertain |
| K.COMPARE | 4 | 2 | uncertain | 2 |
| K.COMPLETE | 4 | 2 | 2 | 2 |
| K.ASYNC | 3 | absent | absent | absent |

Individual has5 steps, adult4, teen3 and custodial3. The prior viewer's missing
procedure message was a profile-recognition bug; it did not show missing source.

No defensible complete mapping was established for revision integrity; account
classification/roles/eligibility/agreements/authority/party separation; state
applicability/rule selection/effective dates/instruments; or K.FILE, K.PURPOSE,
K.CLAUSE, K.SUPPORT, K.RISK, K.REPLY, K.PERSIST, K.TRANSLATE and K.RULEAPPLY.
K.PROCESS/K.SAFETY may measure across actual steps, but selecting all steps does
not establish exposure, obligations or qualified evaluators. Do not mark absent
or uncertain skills as passed, infer a new authored stage, or change the task
merely to satisfy Gym's configuration checks.
