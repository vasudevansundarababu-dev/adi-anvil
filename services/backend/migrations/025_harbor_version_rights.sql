-- Exact logical versions cannot silently name different source revisions.
CREATE UNIQUE INDEX praxis_logical_version ON anvil.praxis_sources(project_id,task_id,task_version);
ALTER TABLE anvil.harbor_agent_reviews ADD COLUMN expires_at timestamptz;
-- Legacy/missing expiry is deliberately not live-ready; no invented rights validity.
INSERT INTO anvil.schema_versions(version) VALUES(25);
