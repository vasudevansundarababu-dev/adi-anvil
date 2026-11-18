# Open Weight Models — configuration and software verification

Authority: user's workbook enhancement and17 November instruction to deploy QA,
continue native/Open Weight work, test without live calls or Authoring integration.

The catalog preserves17 worksheet rows /24 display alternatives.32 exact public
repository choices cover base/instruct/quantized alternatives explicitly, each
with a frozen40-character observed Hub commit. Metadata provenance and direct
repository/API URLs live in `services/backend/src/anvil/open_weight_repositories.json`.
Workbook SHA2562065695f88e3fdb34439df1c20d09c7b354dd5d3b81aa46d208eb73cc1532380.
No weights, tokens, inference, user terms acceptance or rights approval fetched.
Metadata GETs initially failed with the system Python missing CA trust; retry
used `/etc/ssl/cert.pem` with TLS verification enabled;32/32 succeeded.

Models & Keys now has Open Weight Models, explicit repository/commit choices and
bulk registration. One existing encrypted Hugging Face credential/version can
bind every selected model; configuration without a token is allowed. Migration128
extends only the credential provider CHECK, preserving RLS/grants/immutable history.
Registration is Admin-only, idempotent, bounded32, serialized within the project;
cross-project, duplicate/unobserved pins and stale/revoked credentials refuse.
No new secret store, runtime destination, SDK fallback or global provider adapter.

Run's shared model selector supports group filtering, explicit saved model/version
choice, multiple selected revisions, max8, and visible selections outside filters.
Catalog entries awaiting configuration remain visible; no synthetic profile IDs
are passed as actual models. Exact Hub revisions and credential versions are frozen
in configuration/preparation snapshots. Account access, rights, route/runtime,
pricing and provider adapter readiness remain separate fail-closed prerequisites.
No executable HF runtime is claimed from catalog metadata or a Read token.

Verified: earlier complete source1063 units+10 subtests; focused model tests18;
fresh/repeated128 and real API/SQL shared token, all32 registered versions,
cross-project isolation, rotation/revocation, duplicate registration and immutable
prior bindings PASS. Actual Chrome journey with synthetic local API responses PASS:
bulk32 choices with one credential, delayed catalog edit preservation, explicit
version selection and hidden selection visibility. Not an authenticated QA journey.
Browser verification found/fixed Select-all-before-catalog-load race; initial
locators were corrected for required-field suffixes. Final full checks recorded
in BUILD-STATUS when complete. No live calls or Authoring integration.
