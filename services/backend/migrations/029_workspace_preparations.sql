-- Planning records only. No worker/job, approval or spending authority is created.
CREATE TABLE anvil.workspace_execution_presets (
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 100),
 runner_profile_id uuid NOT NULL,candidate_profile_id uuid,tracing_profile_id uuid,
 snapshot jsonb NOT NULL,subject_hash char(64) NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),
 FOREIGN KEY(project_id,runner_profile_id) REFERENCES anvil.workspace_framework_profiles(project_id,id),
 FOREIGN KEY(project_id,candidate_profile_id) REFERENCES anvil.workspace_framework_profiles(project_id,id),
 FOREIGN KEY(project_id,tracing_profile_id) REFERENCES anvil.workspace_framework_profiles(project_id,id)
);
CREATE TABLE anvil.workspace_preset_models (
 project_id uuid NOT NULL,preset_id uuid NOT NULL,connection_id uuid NOT NULL,
 PRIMARY KEY(project_id,preset_id,connection_id),
 FOREIGN KEY(project_id,preset_id) REFERENCES anvil.workspace_execution_presets(project_id,id),
 FOREIGN KEY(project_id,connection_id) REFERENCES anvil.connections(project_id,id)
);
CREATE TABLE anvil.workspace_run_preparations (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,preset_id uuid NOT NULL,package_id uuid NOT NULL,
 snapshot jsonb NOT NULL,subject_hash char(64) NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),UNIQUE(project_id,id,preset_id),
 FOREIGN KEY(project_id,preset_id) REFERENCES anvil.workspace_execution_presets(project_id,id),
 FOREIGN KEY(project_id,package_id) REFERENCES anvil.harbor_packages(project_id,id)
);
CREATE TABLE anvil.workspace_preparation_models (
 project_id uuid NOT NULL,preparation_id uuid NOT NULL,preset_id uuid NOT NULL,
 connection_id uuid NOT NULL,credential_id uuid,credential_version_id uuid,
 CHECK((credential_id IS NULL)=(credential_version_id IS NULL)),
 PRIMARY KEY(project_id,preparation_id,connection_id),
 FOREIGN KEY(project_id,preparation_id,preset_id) REFERENCES anvil.workspace_run_preparations(project_id,id,preset_id),
 FOREIGN KEY(project_id,preset_id,connection_id) REFERENCES anvil.workspace_preset_models(project_id,preset_id,connection_id),
 FOREIGN KEY(project_id,credential_id,credential_version_id) REFERENCES anvil.workspace_credential_versions(project_id,credential_id,id)
);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['workspace_execution_presets','workspace_preset_models','workspace_run_preparations','workspace_preparation_models'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY project_scope ON anvil.%I USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id))',t);
 EXECUTE format('GRANT SELECT,INSERT ON anvil.%I TO anvil_app',t);
 EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
END $$;
INSERT INTO anvil.schema_versions(version) VALUES(29);
