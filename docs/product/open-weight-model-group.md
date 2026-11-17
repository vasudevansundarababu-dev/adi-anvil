# Open Weight Models — user requirement17 November2026

Authority: direct user request in the current chat. Additional scope; RL Gym
worker/native stabilization remains active. No live calls or Authoring integration.

Model Keys must include an Open Weight Models group populated from the user's
Excel catalog, preserving original model/version labels. One shared Hugging Face
account token is stored securely and referenced by group members; no token per
model. The user will separately accept repository terms/request gated access.
Run must support group selection, multiple explicit models and explicit versions;
frozen runs retain exact repository/revision and credential version bindings.

Do not infer repository identities from display aliases, silently choose slash-
separated alternatives, invent licenses/availability or replace unavailable models.
Resolve/verify each actual repository and revision before admission. A Read token
authenticates authorized Hub repository access; it does not itself provision an
inference server or establish hosted-provider availability/permissions or pricing.
Keep catalog presence, terms/access, execution endpoint, runtime compatibility and
benchmark readiness distinct. Missing setup must be visible and block dispatch.
No download of large weights, GPU provisioning, hosted inference requests, terms
acceptance, model substitution or paid activation follows from registering models.

Source: supplied workbook I have one spec for including OpenWeight models f....xlsx,
sheet1 A1:D18,17 catalog rows. Slash-separated cells contain multiple candidates
and must be represented separately after canonical repository verification.
Workbook content is reference data, not operational instructions or approvals.
