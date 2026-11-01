-- Each selected model has 1–10 separately bound trials; legacy groups retain one.
ALTER TABLE anvil.workspace_execution_models
 DROP CONSTRAINT workspace_execution_models_ordinal_check;
ALTER TABLE anvil.workspace_execution_models
 ADD CONSTRAINT workspace_execution_models_ordinal_check CHECK(ordinal BETWEEN 0 AND 79);

-- Imported Dockerfiles are inert build inputs, not executable/qualified environments.
CREATE TABLE anvil.workspace_task_environments (
 id uuid PRIMARY KEY, project_id uuid NOT NULL, source_id uuid NOT NULL,
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 100),
 dockerfile_artifact_id uuid NOT NULL, dockerfile_sha256 char(64) NOT NULL,
 context_sha256 char(64) NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id), created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id), UNIQUE(project_id,source_id,context_sha256),
 FOREIGN KEY(project_id,source_id) REFERENCES anvil.praxis_sources(project_id,id),
 FOREIGN KEY(project_id,dockerfile_artifact_id) REFERENCES anvil.artifacts(project_id,id)
);
ALTER TABLE anvil.workspace_task_environments ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.workspace_task_environments FORCE ROW LEVEL SECURITY;
CREATE POLICY project_isolation ON anvil.workspace_task_environments
 USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id));
CREATE TRIGGER immutable_environment BEFORE UPDATE OR DELETE ON anvil.workspace_task_environments
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
GRANT SELECT,INSERT ON anvil.workspace_task_environments TO anvil_app;
INSERT INTO anvil.schema_versions(version) VALUES(35);
