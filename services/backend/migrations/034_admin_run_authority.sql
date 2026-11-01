CREATE TABLE anvil.workspace_admin_run_authorizations (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,group_id uuid NOT NULL,admin_id uuid NOT NULL REFERENCES anvil.users(id),
 subject_hash char(64) NOT NULL,cap_micro_usd bigint NOT NULL CHECK(cap_micro_usd>0),
 rights_confirmed boolean NOT NULL CHECK(rights_confirmed),pricing_hash char(64) NOT NULL,terms_hash char(64) NOT NULL,
 authority_reference text NOT NULL UNIQUE,expires_at timestamptz NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),UNIQUE(project_id,group_id),
 FOREIGN KEY(project_id,group_id) REFERENCES anvil.workspace_execution_groups(project_id,id)
);
CREATE TABLE anvil.workspace_admin_run_revocations (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,authorization_id uuid NOT NULL,revoked_by uuid NOT NULL REFERENCES anvil.users(id),
 rationale text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,authorization_id),
 FOREIGN KEY(project_id,authorization_id) REFERENCES anvil.workspace_admin_run_authorizations(project_id,id)
);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['workspace_admin_run_authorizations','workspace_admin_run_revocations'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY project_scope ON anvil.%I USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id))',t);
 EXECUTE format('GRANT SELECT,INSERT ON anvil.%I TO anvil_app',t);
 EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
END $$;
INSERT INTO anvil.schema_versions(version) VALUES(34);
