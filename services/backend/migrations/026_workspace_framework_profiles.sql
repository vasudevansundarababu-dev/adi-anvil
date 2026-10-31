-- Metadata-only configuration. No credentials, new runtime or dispatch authority.
CREATE TABLE anvil.workspace_framework_profiles (
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 100),
 framework text NOT NULL CHECK(framework IN ('harbor','langsmith','semantic_kernel')),
 config jsonb NOT NULL,config_hash char(64) NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id)
);
ALTER TABLE anvil.workspace_framework_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.workspace_framework_profiles FORCE ROW LEVEL SECURITY;
CREATE POLICY project_scope ON anvil.workspace_framework_profiles
 USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id));
CREATE INDEX ON anvil.workspace_framework_profiles(project_id,id);
GRANT SELECT,INSERT ON anvil.workspace_framework_profiles TO anvil_app;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.workspace_framework_profiles
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
INSERT INTO anvil.schema_versions(version) VALUES(26);
