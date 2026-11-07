# Original fictional benchmark fixtures

`fictional-points-v1` is an original arithmetic software fixture, not Bodhium source, a partner exhibit, model performance or a qualified benchmark. Three FX tasks contain 24/6/51 one-point integer-equality criteria. Their names, arithmetic rules and sidecars are original test data; none reconstructs missing financial criteria.

`runtime_pack/` contains each task's actor materials and stdio arithmetic tool. `eval_pack/` contains separately declared fictional oracle/policy/calibration files and a private canary. Tests exercise the actual deterministic oracle and stdio subprocess; no API/provider or candidate invocation reads expected answers. These public-repository test assets are intentionally fictional; authentic private exhibits must never be placed here.

Reproduce with the isolated backend and local pnpm tool:

```sh
services/backend/.venv/bin/python fixtures/benchmark-bundle/build_fixture.py
node .local/pnpm/node_modules/pnpm/bin/pnpm.cjs exec prettier --write contracts/praxis/benchmark-bundle-v1 fixtures/benchmark-bundle/fictional-points-v1/manifest.json
```

Both steps are part of the deterministic generation recipe. Payload hashes describe exact bytes. The pinned Python OCI base digest comes from the existing `fixtures/executable-import/environment/Dockerfile`; it is not an invented digest or an image qualification. The fixture image has not been pulled/run by this work. Evaluator registry metadata explicitly says unreviewed, and imported Python is inert source, not an installation-approved evaluator.

There is intentionally no signature or installed trust root: this unsigned fixture must remain quarantined at future intake. Unit tests create ephemeral Ed25519 keys in memory to exercise signatures. No signing private key or runtime credential is stored. A verified signature would prove source authenticity under an external installation policy, not data rights, execution readiness, evaluator approval or spending authority.

T01 implements metadata validation, not archive streaming, durable intake, private vaults, native Harbor qualification, execution or scoring APIs. Those remain separately prerequisite-gated.
