# Cloud-ready golden imports

Use these **version1.1.0** successors with the deployed Anvil workspace:

- [Marketing](01-marketing.export.json)
- [KYC / AML](02-kyc_aml.export.json)
- [Fraud](03-fraud.export.json)

Download one `.export.json` and select Tasks → Import Task. These use the same synthetic
rules, public data and private QA as the original [local golden set](../golden-v3/README.md),
but bind the actual GCP registry image's immutable OCI digest. The existing Anvil VM
preloads that image; no local Docker archive upload is needed on that host.
Original versions, source hashes and existing run bindings are unchanged.

Code generation and evaluation have separate settings and budgets. The YC rollout
enables generation only (`gpt-6.1-sol`, $10 per whole import); paid model evaluation is
disabled. No fixture or scripted trial is a live model-performance measurement.

Reproduce these exports after verifying the target image's real registry digest:
`python3 scripts/cloud_golden_exports.py --image REGISTRY/IMAGE@sha256:DIGEST`.
Never substitute an invented digest or mutable tag. Each export preserves exact payload
bytes, updates its payload/source SHA256 and explicitly versions the environment binding.
