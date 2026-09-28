# Frontier — Pack Release and Delivery

Version: 0.2 · Review draft · 27 September 2026
Module: F09

## 1. Purpose and boundary

Approve and deliver immutable research assets for a named recipient and permitted use. This releases data/environments/evidence—not enterprise agents or model weights for live business operation.

No production Deploy or business-agent Monitor module. Internal job, storage, delivery and security observability remain necessary. Product service deployment belongs to the team's DevOps, not a customer-facing agent-deployment workflow.

## 2. Release candidate

Proposed ownership correction F-A05: F09 owns assembly of the generic CapabilityPackVersion (PackVersion) and its manifest as well as release/delivery. F05 supplies a qualified LearningAssetSetVersion only when learning assets are requested. A diagnostic package can be assembled and delivered without F05. Module-specific task/data/environment/evidence qualification remains with its source owner; assembly cannot override it.

PackVersion binds objective, qualified task/family/data versions, environment/runner where contracted, grading/reward definitions, permitted learning assets, split visibility, evidence reports, source/licenses/rights, dependency/security review, compatible interfaces, known limitations and artifact digests. Praxis-originated assets pin the accepted source record/snapshot and Frontier qualification separately. Source acceptance is not customer release approval.

Use a manifest version and explicit format compatibility. Data-only and runnable-environment packages have different readiness checks. An unavailable component cannot be listed as included. A generator's descendants inherit relevant source restrictions.

Hold back hidden benchmark solutions or internal reference state unless the recipient is explicitly authorized for the stated use; never expose it to the tested agent. Include a README/data card and integration instructions. No raw provider credentials or contributor identity records.

## 3. Approval and states

Proposed release authority is assigned per project before actual release; it is not automatically the scientist or salesperson. Require completed technical/domain qualification as applicable, rights/disclosure approval and correct recipient/destination.

Release: Candidate → Review pending → Approved for delivery → Delivery in progress → Delivered. Alternatives: Blocked, Changes requested, Delivery failed, Superseded, Withdrawn.

CustomerAcceptance is independent: Pending / Accepted / Rejected / Changes requested, with the accepting owner, contract criteria and evidence. Download or transfer success is not acceptance.

Changing contents, rights, interfaces or recipient scope requires a new version or renewed scoped authorization as applicable. A run/qualification/report pass is not delivery approval. AssetRequest status in Training Packs only references this lifecycle.

## 4. Delivery and updates

Validate digests, package schema, redaction, rights and configured destination before transfer. Record actor, recipient, time, manifest, allowed use, transfer attempt and outcome. Retry is an explicit scoped operation and preserves failed attempts; unknown receiver status is not delivered.

Customer-hosted execution can use the package offline/privately where its declared dependencies permit. Do not promise air-gapped operation when generation, grading or environments require remote services. No mandatory telemetry or private-result return; validate any chosen external calls.

For defects: block affected future deliveries, identify dependent findings/reports, create successor version, requalify/reapprove and notify recipients through an authorized correction process. Withdrawal records cannot erase already downloaded copies; contractual handling and retention requirements must be clear.

## 5. Operational controls

Logs track service jobs, isolation faults, access/export events, costs, missing artifacts and delivery errors. Retain explicit alert ownership; exact SLAs/retention are undecided. No automatic regenerate/re-release or customer-side training on an alert.

## 6. Acceptance criteria

- F-REL01: Only a qualified, rights-cleared approved manifest can be delivered.
- F-REL02: Recipient/destination/scope changes cannot reuse an unrelated approval.
- F-REL03: Delivered and Customer accepted are separate states.
- F-REL04: Data-only assets cannot pass runnable-environment acceptance checks.
- F-REL05: Hidden answers, secrets and contributor identity records are absent from unauthorized exports.
- F-REL06: Delivery failure/retry preserves evidence and does not falsely mark acceptance.
- F-REL07: Corrections preserve historical versions and invalidate affected claims for review.
- F-REL08: Release/delivery starts no optimizer, model deployment or business-agent execution.

Release roles, contractual acceptance, correction timelines, retention and first delivery mechanism remain open. No package has been delivered by this specification.
