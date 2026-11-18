# Shared-token successor linking correction

Final read-only review found that registering catalog models without a token,
then registering them with the shared token, created duplicate current profiles.
The same happened after token rotation. This was a configuration issue, not a
dispatch/secret exposure. Initial QA deployment and its evidence remain historical.

Bulk registration now creates successor versions on the one matching current
repository/revision/catalog profile, preserving settings and prior immutable
bindings. Exact bindings are reused; omitting a token never unlinks an existing
one. Ambiguous multiple profiles require explicit profile selection. Existing
HTTP project serialization remains; an additional catalog advisory lock also
serializes direct helper calls. Credential/profile locks retain rotation and
concurrent-edit checks. No old rows/profiles are deleted or silently rewritten.

Run model-version choices now include the credential and configuration identity,
so already-existing distinct profiles are distinguishable.

PASS:1064 units+10 subtests; types and production frontend build; real Chrome
synthetic API journey; fresh/repeated128 and real SQL/API flow covering keyless
setup, bulk linking and rotation across32 repositories, no duplicate profiles,
preserved historical bindings, revocation and cross-project rejection. The test
retains34 profiles total: two separate manually configured controls plus the32
catalog profiles, after all linking/rotation steps. No live calls or Authoring.
No schema change beyond already deployed128. Subsequent QA build/rollout recorded
after exact image verification; never claim this correction is serving from Git.
