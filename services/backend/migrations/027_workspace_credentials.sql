CREATE TABLE anvil.workspace_credentials (
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 100),
 provider text NOT NULL CHECK(provider IN ('openai','anthropic','gemini','langsmith')),
 current_version_id uuid,revoked_at timestamptz,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id)
);
CREATE TABLE anvil.workspace_credential_versions (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,credential_id uuid NOT NULL,
 secret_reference uuid NOT NULL,created_by uuid NOT NULL REFERENCES anvil.users(id),
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(project_id,id),
 UNIQUE(project_id,credential_id,id),
 FOREIGN KEY(project_id,credential_id) REFERENCES anvil.workspace_credentials(project_id,id)
);
ALTER TABLE anvil.workspace_credentials ADD FOREIGN KEY(project_id,id,current_version_id)
 REFERENCES anvil.workspace_credential_versions(project_id,credential_id,id);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['workspace_credentials','workspace_credential_versions'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY project_scope ON anvil.%I USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id))',t);
 EXECUTE format('CREATE INDEX ON anvil.%I(project_id)',t);
 EXECUTE format('GRANT SELECT,INSERT ON anvil.%I TO anvil_app',t);
 END LOOP;
END $$;
GRANT UPDATE(current_version_id,revoked_at) ON anvil.workspace_credentials TO anvil_app;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.workspace_credential_versions
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE FUNCTION anvil.guard_workspace_credential() RETURNS trigger LANGUAGE plpgsql AS $$
 BEGIN
 IF OLD.revoked_at IS NOT NULL AND NEW IS DISTINCT FROM OLD THEN
 RAISE EXCEPTION 'revoked credential cannot change'; END IF;
 RETURN NEW;
 END $$;
CREATE TRIGGER guard_workspace_credential BEFORE UPDATE ON anvil.workspace_credentials
 FOR EACH ROW EXECUTE FUNCTION anvil.guard_workspace_credential();
INSERT INTO anvil.schema_versions(version) VALUES(27);
