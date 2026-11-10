CREATE TABLE anvil.environment_task_bindings(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,environment_id uuid NOT NULL,task_group_id uuid NOT NULL,
 task_id text NOT NULL,task_version text NOT NULL,snapshot jsonb NOT NULL,
 snapshot_sha256 text NOT NULL,created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,environment_id) REFERENCES anvil.environment_versions(project_id,id),
 FOREIGN KEY(project_id,task_group_id) REFERENCES anvil.benchmark_task_groups(project_id,id),UNIQUE(project_id,id));
CREATE TABLE anvil.environment_evaluations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,binding_id uuid NOT NULL,evidence_receipt_id uuid NOT NULL,
 content jsonb NOT NULL,content_sha256 text NOT NULL,created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,binding_id) REFERENCES anvil.environment_task_bindings(project_id,id),
 FOREIGN KEY(project_id,evidence_receipt_id) REFERENCES anvil.environment_receipts(project_id,id),UNIQUE(project_id,id));
DO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY['environment_task_bindings','environment_evaluations'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY engineer ON anvil.%I TO anvil_app USING(anvil.golden_engineer(project_id)) WITH CHECK(anvil.golden_engineer(project_id))',t);
 EXECUTE format('GRANT SELECT,INSERT ON anvil.%I TO anvil_app',t);
 EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 EXECUTE format('CREATE TRIGGER actual_author BEFORE INSERT ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.environment_author()',t);
 END LOOP;END $$;
