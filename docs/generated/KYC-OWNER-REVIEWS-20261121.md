# KYC owner reviews required

These are content decisions for the real project Product Owner, not engineering
approval, template re-authoring or permission to make model calls. A single PO
may decide under D-SIMPLE; no additional independent reviewer is mandatory.
Where permitted self-approval applies, the application must record it explicitly.

## 1. Policy applicability:20 staged subjects

In Forge QA, Project7 **KYC onboarding and refresh → Policy Binding to Evals →
KYC policy review subjects**, inspect each exact subject before approving or
rejecting it. The20 subjects cover four products × CA/NY/TX/FL/IL.

Review federal and bank source references, state source references, product and
national-bank charter applicability, instruments, dates and any caveats. The
charter is national/OCC, home state New York; the assessment is November12,2026.
The selected pilot interval is November12 inclusive to November13 exclusive.
That interval choice did not approve policy contents or statutory effectivity.

* Individual: five explicit **state not applicable** decisions. Review the
  recorded rationale; these are not five missing source lists to fill blindly.
* Adult joint: five applicable state joint-account subjects.
* Teen joint: five minors-deposit/joint-account subjects, including the recorded
  national-bank caveats for Texas and Illinois.
* Custodial: five applicable state UTMA subjects.

For each decision, supply the exact displayed subject hash, approve/reject,
rationale, supporting evidence reference/hash, and a future review-expiry time.
Use the reviewed source bundle as evidence, not a software-test result. The API
already supports listing/detail, decisions and revocation under
`/golden-banking/v1/policy-reviews`. No decisions have been made on your behalf.

Exact UI sequence (after the Projects-list defect is repaired):

1. Sign in to https://anvil-qa.adi-labs.ai/workspace as the actual project PO.
2. Open **Projects → KYC onboarding and refresh → Policy Binding to Evals**.
3. Expand **KYC policy review subjects** and click **Reload staged subjects and decisions**.
4. Choose a staged subject. Inspect its product, state, charter caveats, source
   references, applicability interval and full subject hash. Repeat for all20;
   do not assume a UUID in the selector identifies the intended state.
5. Enter **Decision rationale** (at least10 characters), **Reviewed evidence
   reference**, the exact64-character **Reviewed evidence SHA-256** from the
   reviewed artifact/manifest, and a future **Review expiry** in local time.
6. Only after reviewing the evidence, check **I reviewed this exact subject and
   its source evidence**, then choose **Record Product Owner approval** or
   **Record rejection**. Inspect **Recorded decisions** for the returned receipt.

The UI attaches the displayed subject hash itself; no JSON or code writing is
required. Do not use an invented evidence hash, a software-control hash or the
pilot interval as statutory effective dates. Missing source effectivity remains
an explicit content gap. If an outcome is unconfirmed, keep the hold and ask for
reconciliation; do not repeat the decision under a new identity/key.

## 2. Case expectations: one exact frozen200-case population review

Review the expected outcome and evidence requirements for every case included in
the proposed private-review population. One genuine decision may cover a fully
enumerated population;200 separate button clicks are not inherently required.
Check expected disposition, mandatory evidence, acceptable partial/gap handling,
state-reference applicability and any cases that must remain unscored.

Current child pack: `729266f3-1741-563b-b4ba-586cf7fae4b3`,200 applications,
50 per product,10 per product/state. Population hash:
`37e42886bc9362b5a6e39b51a1be6b34f1e06b8e0e631ef8abeb2b09abba5cf0`.
It currently has0 installed reviewed expectations. Parent expectations must not
be silently inherited into this changed context.

Gym has prepared a local private worksheet and salted canonical review packet in
`.local/kyc-owner-review-20261121/` (not committed or emailed). This is a draft,
not a reviewed population: all200 proposed outcomes need confirmation against the
changed child context. Normative criterion and state-reference evidence remains
absent, so those checks cannot be promoted to scored correctness by approving
the dispositions alone. Gym must finish the evidence preparation before asking
you to approve the final packet; a CSV approval cell is not an application receipt.

The append-only review API, private loader, owner UI and frozen-binding/grader
checks are deployed in8a22280. After restricted staging of the final packet,
use **Data & Environments → KYC expectation review**:
inspect the private worksheet, compare the exact canonical packet hash, then
explicitly approve/reject with rationale, evidence reference and future expiry.
Only metadata/hashes reach this UI. An uploaded `approved` string is insufficient.
The ordinary API and scheduler never receive private expectation bodies. A later
review does not replace the review frozen into an existing preparation; save a
new preparation explicitly. No new Authoring task is requested.

Exact UI sequence once Gym supplies the final privately prepared worksheet and
canonical packet (the current draft is not ready for this approval):

1. Open **Data & Environments → KYC private expectation reviews**.
2. Click **Load expectation review subjects**, then **Inspect** for the exact
   child pack/population. Confirm200 cases, the subject hash and private packet hash.
3. Review every expected outcome/evidence obligation in the private worksheet.
   Keep unsupported normative/state checks unscored. Report corrections to Gym
   before approving; changing the packet creates a different review subject.
4. Enter **SHA-256 of the privately reviewed canonical packet** (must match the
   displayed hash), choose Approve/Reject, enter a rationale of at least10
   characters, a **Private review evidence reference**, and future **Review expires**.
5. Check **I reviewed this exact private packet and population**, then click
   **Record owner decision**. Confirm the receipt/current-review status.

Do not upload private answers into this screen. One decision can cover the exact
enumerated200-case population;200 individual approval clicks are not required.
Engineering will explicitly save a new preparation using that receipt afterward.

## 3. Processing rights and run authorization: after model selection

Once preparation is ready and you choose the exact model, review the frozen Run
summary: exact dataset/tasks/model/key versions, external processing destination,
processing terms, current pricing, repetition/turn limits and total spend cap.
Confirm processing rights only if those exact synthetic inputs and policy
materials may be sent to that destination. Explicitly authorize that Run through
the existing execution-group authorization step with a recent Admin sign-in.

That real Run authority consumes `rights_confirmed=true` and the frozen subject
hash. A source declaration, unused rights hash or ordinary case-rights record is
not a substitute. Do not authorize a Run during this no-model QA work. No model
or budget is being selected or approved by the engineering work.

## What is not an owner review

Exact runtime/evaluator controls, method and safety qualification, diagnostic
configuration, skill-to-step configuration, restricted operator provisioning and
the final technical readiness check remain Gym responsibilities. No owner should
be asked to declare those technical controls passed to clear a blocking badge.
