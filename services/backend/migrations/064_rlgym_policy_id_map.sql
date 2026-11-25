-- D-056 (owner-approved, 24 Nov 2026): Authoring's per-task policy_id_map (its S4 rule ids → the environment's policy
-- ids, with the environment version and each policy's content_sha256). Kept as sent at import and applied at reset
-- only when it matches the environment being run. Additive only: one nullable column; existing rows read back unchanged.
ALTER TABLE projects.task_imports ADD COLUMN policy_id_map jsonb;
