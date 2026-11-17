-- Preserve valid authored packages independently of execution provisioning.
CREATE TABLE anvil.praxis_project_intakes(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 package_key text NOT NULL,package_version text NOT NULL,package_sha256 text NOT NULL,
 batch_key text NOT NULL,part_index integer NOT NULL,part_count integer NOT NULL,
 private_archive_id uuid NOT NULL,public_snapshot jsonb NOT NULL,public_snapshot_sha256 text NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,private_archive_id) REFERENCES anvil.artifacts(project_id,id),
 UNIQUE(project_id,id),UNIQUE(project_id,package_key,package_version),UNIQUE(project_id,batch_key,part_index));
ALTER TABLE anvil.praxis_project_intakes ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.praxis_project_intakes FORCE ROW LEVEL SECURITY;
CREATE POLICY scoped_read ON anvil.praxis_project_intakes FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id));
CREATE POLICY admin_insert ON anvil.praxis_project_intakes FOR INSERT TO anvil_app WITH CHECK(
 anvil.benchmark_is_admin(project_id,nullif(current_setting('anvil.user',true),'')::uuid)
 AND created_by=nullif(current_setting('anvil.user',true),'')::uuid);
GRANT SELECT,INSERT ON anvil.praxis_project_intakes TO anvil_app;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.praxis_project_intakes FOR EACH ROW EXECUTE FUNCTION anvil.immutable();

-- Requalification appends an Anvil execution binding without changing Praxis
-- source versions or rewriting old receipts/tasks/results.
ALTER TABLE anvil.praxis_export_resolutions ADD COLUMN execution_binding_key text
 GENERATED ALWAYS AS (coalesce(receipt->>'binding_context_sha256',receipt->>'source_sha256')) STORED
 CHECK(execution_binding_key~'^[a-f0-9]{64}$');
DO $$ DECLARE item record; BEGIN
 FOR item IN SELECT conname FROM pg_constraint WHERE conrelid='anvil.praxis_export_resolutions'::regclass AND contype='u' AND cardinality(conkey)=3 LOOP
  EXECUTE format('ALTER TABLE anvil.praxis_export_resolutions DROP CONSTRAINT %I',item.conname);
 END LOOP;
END $$;
CREATE UNIQUE INDEX praxis_resolution_source_binding ON anvil.praxis_export_resolutions(project_id,package_key,version,execution_binding_key);
CREATE UNIQUE INDEX praxis_resolution_batch_binding ON anvil.praxis_export_resolutions(project_id,batch_key,part_index,execution_binding_key);
CREATE FUNCTION anvil.praxis_resolution_source_fence() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 PERFORM id FROM anvil.projects WHERE id=NEW.project_id FOR UPDATE;
 IF EXISTS(SELECT 1 FROM anvil.praxis_export_resolutions WHERE project_id=NEW.project_id AND package_key=NEW.package_key AND version=NEW.version AND package_sha256<>NEW.package_sha256)
 THEN RAISE EXCEPTION 'immutable Praxis package bytes';END IF;
 IF EXISTS(SELECT 1 FROM anvil.praxis_export_resolutions WHERE project_id=NEW.project_id AND batch_key=NEW.batch_key AND (part_count<>NEW.part_count OR part_index=NEW.part_index AND (package_key<>NEW.package_key OR version<>NEW.version OR package_sha256<>NEW.package_sha256)))
 THEN RAISE EXCEPTION 'immutable Praxis batch partition';END IF;
 RETURN NEW;END $$;
CREATE TRIGGER source_fence BEFORE INSERT ON anvil.praxis_export_resolutions FOR EACH ROW EXECUTE FUNCTION anvil.praxis_resolution_source_fence();
