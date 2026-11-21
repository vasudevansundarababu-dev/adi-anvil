# Consumed QA operators — immutable source archive

These are the exact public Python program bytes reviewed and executed for the
20 November 2026 QA release and first-write investigation. They are retained as
text, not active maintenance commands: their one-time intent names, backups,
container identities and expected baselines are consumed or superseded. Do not
replay them. A future operation needs a fresh reviewed plan against current state.

| Archived source | Executed SHA-256 |
| --- | --- |
| rollout-v2.py.txt | 2e6807ecd3c0724ee8a7e68e5d2ed3d5f042c41258c88b39f1d932c3941f93b6 |
| api-tmpfs-rollout.py.txt | 9f9e9d375391344edac31593b7fa09ba5bb174e2b963eca1b22bdcd06cf03cdb |
| first-temp-operator.py.txt | d427471de64e379f2316befbb78f6a36d655a7b458cececf893d44379f48088f |
| first-temp-worker.py.txt | 49ab2e1133a068a4fe2e95d282c052825481136f45635549e1e6c0f54e8981e8 |
| registration-http-diagnostic.py.txt | baf930e64e65478b38920905383341775b8d6ebcef4f4f46f53de3f3166728ef |
| registration-http-worker.py.txt | 2117fbb2c2de648ba6fafa8f1fa7b2757657e2716f49c0b3a9fc1704d2b91907 |

The archive preserves original formatting and byte pins rather than rewriting
historical executed programs. Live maintained QA scratch configuration is in
`infra/gcp/qa_native_wiring.py`; its unit tests exercise future provisioning.
No credentials, private configuration or raw execution logs are archived here.
Programs that generate synthetic fixture credentials do so only at runtime into
private files in a separate, disposable test database.

For actual outcomes, current qualification boundaries and next steps, read
`BUILD-STATUS.md` and `docs/generated/QA-BENCHMARK-GAP-REGISTER.md`.
