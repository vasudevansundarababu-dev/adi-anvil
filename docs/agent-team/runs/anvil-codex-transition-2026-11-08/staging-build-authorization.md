# Isolated image-build authorization

The user explicitly approved the build plan at checkpoint `d72587e` in reply to question `call_6df3789b7ac14040b5326934e8d274ba`:

> Approve the isolated Anvil image-build plan at checkpoint `d72587e`: create a staging-only image registry, private seven-day source bucket and build-only account with the listed limited permissions; run one backend/web build with a 40-minute timeout under a $5 allowance from your $500 budget; and clean up only these new resources if setup/build fails? No application VM, public endpoint, DNS changes, paid model calls or deployment.

User answer: **Approve the isolated build plan**.

This authorizes only the exact resource/permission diff and source/configuration packet published at that checkpoint. It does not authorize application deployment, additional builds, API enablement, broader permissions, production changes or model/evaluation calls. Revalidate all local source/configuration inputs, fresh name absence and existing controls before mutation. Use the independent Anvil deploy account and SDK configuration; no keys are created for the build identity. Preserve all unrelated resources and Praxis/local changes.

Upload only the reviewed381-file public source selection, recording the actual package hash and GCS object/generation before the one build. Record its actual build ID without blindly retrying an ambiguous submission. Actual resource IDs, lifecycle and narrow IAM receipts must precede submission. Missing service-agent or organization authority remains blocked rather than repaired with broader grants.

Failure cleanup covers only resources newly created by this approved operation after actual build terminal state and ownership/reference verification. Preserve source/build evidence. Successful output images remain held for a later, separate application deployment review. The USD5 amount is an operator allocation within the existing USD500 allowance, not a technical billing cutoff.
