# KYC four-product QA — 20-cell stage matrix

This is the actual serving **software-reference** import, not an authored ZIP or model benchmark. Paid calls are off; Authoring is paused; Stage/Production are on hold.

Serving source: `4e53d1c1b41ca373b2c9eecf695c22654c3d3885fdbed84dd70a5b1c74f730f0`. Proposed decoder source `c26a7965…201e4` is not yet deployed or qualified.

Actual import `d2e76679-9362-4082-90ec-3792c5dbd43f`, manifest `c065f96c1046572646525d31b15089eba9526c1fdb10178f2f2fd48fea12dc28`, pack `7e17aa6b-4a23-4abc-a28f-f4ba97186c2d`, environment `a9058247-8ac8-4bbe-bac6-c7791ca34471`, task group `10a913b7-edcb-4924-b871-c691bcdf27cf`. Four product bindings share 50 evaluator configurations; all 200 original snapshot hashes and product selectors match.

| Product | State | Reference cases/binding | Registry software control | Authored import | Authored native/evaluators/report |
| --- | --- | --- | --- | --- | --- |
| adult_joint | CA | 10 / verified | Candidate read passed* | Blocked | Not run |
| adult_joint | FL | 10 / verified | Candidate read passed* | Blocked | Not run |
| adult_joint | IL | 10 / verified | Candidate read passed* | Blocked | Not run |
| adult_joint | NY | 10 / verified | Candidate read passed* | Blocked | Not run |
| adult_joint | TX | 10 / verified | Candidate read passed* | Blocked | Not run |
| custodial | CA | 10 / verified | Candidate read passed* | Blocked | Not run |
| custodial | FL | 10 / verified | Candidate read passed* | Blocked | Not run |
| custodial | IL | 10 / verified | Candidate read passed* | Blocked | Not run |
| custodial | NY | 10 / verified | Candidate read passed* | Blocked | Not run |
| custodial | TX | 10 / verified | Candidate read passed* | Blocked | Not run |
| individual | CA | 10 / verified | Candidate read passed* | Blocked | Not run |
| individual | FL | 10 / verified | Candidate read passed* | Blocked | Not run |
| individual | IL | 10 / verified | Candidate read passed* | Blocked | Not run |
| individual | NY | 10 / verified | Candidate read passed* | Blocked | Not run |
| individual | TX | 10 / verified | Candidate read passed* | Blocked | Not run |
| teen_joint | CA | 10 / verified | Candidate read passed* | Blocked | Not run |
| teen_joint | FL | 10 / verified | Candidate read passed* | Blocked | Not run |
| teen_joint | IL | 10 / verified | Candidate read passed* | Blocked | Not run |
| teen_joint | NY | 10 / verified | Candidate read passed* | Blocked | Not run |
| teen_joint | TX | 10 / verified | Candidate read passed* | Blocked | Not run |

*Registry-reader controls use explicitly manufactured software prerequisites and return `registry_candidate_not_admitted`. They are not legal/case/rights approval, real authored execution, or model performance. The fixture calls `register(..., application_types=True)`; it is not the five-state/default workflow.

## Remaining stages and owners

- Gym engineering: qualify and deploy the new exact decoder source/images; old source receipts do not cover it.
- Authoring system/owner review: correct the nine undeclared procedure tool references in the reviewed successor export; retain original approved records. See `KYC-V8-AUTHORING-TOOL-BINDING-CORRECTION.md`.
- Gym data/policy owners: bind the real approved assessment-date/charter context, actual data and private expectations, current rights and case/policy reviews. Reference fixtures must not be relabelled as real V8 inputs. These are not Authoring dataset responsibilities.
- QA: after admission is possible, verify actual authored resolution, exact environment/evaluator binding, no-model native flow and reports for every product/state subject. Until then those stages are blocked/not run, not passed by extrapolation.
- Actual model benchmarking: remains separately disabled and requires exact user model/budget selection and existing run admission.

## Evidence

Serving readback SHA-256: `486e7eac622681dcbd74ec3bac4f1684bd8f469d85e5421f956a8c455110f21f`.

Installed registry software output SHA-256: `e5e39eb28b0fd6372c41b0b5582cea1000efe8ec8454c1af673aca2dce4370f9`.

Raw sanitized runtime records remain in ignored `.local/releases/88214ba/`; no private task bodies or expected answers are published in this matrix.
