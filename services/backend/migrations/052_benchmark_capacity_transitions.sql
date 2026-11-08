-- Trusted coordinator may release or preserve unknown capacity. Existing041
-- fenced-transition trigger keeps immutable identity, no unknown->held/reacquire,
-- no edits afterrelease and no shortened lease. No worker/bypass grant is added.
GRANT UPDATE(state) ON anvil.benchmark_capacity_claims TO anvil_app;
INSERT INTO anvil.schema_versions(version) VALUES(52);
