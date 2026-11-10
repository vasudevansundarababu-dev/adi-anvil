# Linux QA authorization and staging demo handoff

Recorded 2026-11-08, America/Chicago. This is a session-specific authority record, not a standing deployment grant.

The user initially selected “Hold cloud provisioning,” then explicitly reversed that decision: “sorry can you do cloud hosting and linux testing.” Root stated the bounded interpretation: proceed with the published isolated Linux QA-host plan under its USD60 ceiling; application deployment remains paused. The user subsequently instructed: “Continue Linux testing and fix any issues. Prepare Anvil for an end-to-end staging demo tomorrow, keep Praxis and my local changes untouched, and ask for deployment approval when ready.”

## Authorized now

- Execute the exact test-host proposal published at `88bcb5d`, within USD60 of the existing additional USD500 monthly infrastructure allowance. Creation cannot occur before 2026-11-08T19:30:00Z; absolute VM STOP remains 2026-11-15T19:30:00Z.
- Use only the isolated Anvil resources, named Anvil principal, independent CLI/config, pinned packages/images and fictional test inputs in that proposal. Record actual identities, resource IDs, source/archive hashes, expiry, package provenance and observed isolation before tests.
- Run real Linux-native tests; fix confirmed issues on the existing Anvil branch, rerun affected checks, and push normal checkpoints. Preserve failed evidence and rebind/retest any successor source rather than calling old evidence current.
- Prepare a reviewable staging demo release for November9. The demonstration target is import, qualification, execution, separate evaluation, human review and results/export using explicitly fictional inputs with paid calls disabled. Record any missing product flow as a gap rather than substituting SQL metadata or invented results.
- Export sanitized test evidence and clean up only the exact test resources created under this approval, as described in the published plan.

## Still gated

Application deployment, merge, production changes, paid candidate/judge calls, additional images/resources/IAM beyond the reviewed test-host plan and use of authentic data without its rights remain unauthorized. Ask for application deployment approval with exact release, test evidence, target configuration, cost and rollback plan when ready. The prior intermittent local integration failure remains documented; clean repeat passed but its cause is unconfirmed.

Praxis and the original Anvil checkout/local changes remain untouched. The test host is not an application deployment or proof of an end-to-end release. Cloud billing estimates and an operator ceiling are not technical hard caps.

## OS Login access amendment

The project has `enable-oslogin=true`, so the proposal's instance-only metadata SSH key method is not applicable. Root requested permission to register a temporary SSH public key on the existing Anvil Google account, with a one-hour expiry, and remove it after testing, without IAM grants or project settings changes. The user explicitly answered **“Allow temporary OS Login key.”** Use a new repository-local dedicated private key; never display or copy that private key to the host. Record only the public-key fingerprint, expiry and removal outcome. No unrestricted renewal or project-wide metadata modification is included.

## Explicit resumption after automatic review rejection

The first creation request at 2026-11-08T19:30:10Z was rejected before execution by automatic approval review, which considered the earlier hold unresolved. No resources were created by that request. Root reported the rejection and requested an explicit resource-specific confirmation.

The user subsequently instructed, verbatim: **“Create the isolated Anvil Linux test VM, disk, network, NAT and IAP firewall within $60. Continue Linux testing and fix issues. Keep Praxis and my local changes untouched, and ask before application deployment.”** This explicitly supersedes the earlier hold for these test resources only. Application deployment remains separately gated. Resume through the normal approval mechanism with this current instruction; do not bypass a rejection.

The former temporary OS Login key's one-hour expiry has elapsed. Root interpreted the new active resumption instruction together with the existing explicit OS Login permission as allowing one bounded one-hour access refresh for the same principal/key/purpose, without new permissions or indefinite renewal. Record its actual new expiry and remove it when testing finishes. Stop if a different identity, broader permission or access mechanism is required.

## One additional bounded access extension

After25 native cases passed and the evaluator/pipeline work remained, root asked whether to extend the same temporary public key once until **8:51 PM Central on November8**, with options “Allow access until8:51PM” and “Keep the current7:51PM expiry.” The user replied **“1.”** Root explicitly stated the interpretation as approval of the first option. DevOps then updated only the same account/key's expiration and verified **2026-11-09T02:51:10Z** through the official SDK. No new key, IAM grant, account setting or cloud resource was introduced. Remove the exact existing fingerprint after testing; no further extension is implied.
