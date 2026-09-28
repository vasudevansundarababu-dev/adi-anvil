CREATE TABLE anvil.import_batches (
 id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES anvil.projects(id),
 created_by uuid NOT NULL REFERENCES anvil.users(id), manifest jsonb NOT NULL,
 manifest_hash text NOT NULL, status text NOT NULL CHECK(status IN ('validated','rejected','committed')),
 validation_errors jsonb NOT NULL DEFAULT '[]', committed_source_ids jsonb NOT NULL DEFAULT '[]',
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(project_id,id)
);
CREATE TABLE anvil.source_import_receipts (
 project_id uuid NOT NULL REFERENCES anvil.projects(id), partner_key text NOT NULL,
 external_case_id text NOT NULL, source_version text NOT NULL, content_hash text NOT NULL,
 resource_id uuid NOT NULL,
 PRIMARY KEY(project_id,partner_key,external_case_id,source_version),
 FOREIGN KEY(project_id,resource_id) REFERENCES anvil.resources(project_id,id)
);
ALTER TABLE anvil.import_batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.import_batches FORCE ROW LEVEL SECURITY;
CREATE POLICY project_scope ON anvil.import_batches USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id));
ALTER TABLE anvil.source_import_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.source_import_receipts FORCE ROW LEVEL SECURITY;
CREATE POLICY project_scope ON anvil.source_import_receipts USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id));
GRANT SELECT,INSERT,UPDATE ON anvil.import_batches TO anvil_app;
GRANT SELECT,INSERT ON anvil.source_import_receipts TO anvil_app;
CREATE FUNCTION anvil.immutable_import_manifest() RETURNS trigger LANGUAGE plpgsql AS $$
 BEGIN
 IF NEW.manifest IS DISTINCT FROM OLD.manifest OR NEW.manifest_hash IS DISTINCT FROM OLD.manifest_hash
 OR NEW.project_id IS DISTINCT FROM OLD.project_id OR NEW.created_by IS DISTINCT FROM OLD.created_by THEN
 RAISE EXCEPTION 'immutable import manifest'; END IF;
 RETURN NEW;
 END $$;
CREATE TRIGGER immutable_manifest BEFORE UPDATE ON anvil.import_batches FOR EACH ROW EXECUTE FUNCTION anvil.immutable_import_manifest();
INSERT INTO anvil.schema_versions(version) VALUES(3);
