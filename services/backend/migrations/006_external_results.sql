CREATE TABLE anvil.external_result_receipts (
 id uuid PRIMARY KEY, project_id uuid NOT NULL, run_id uuid NOT NULL UNIQUE,
 import_id uuid NOT NULL UNIQUE, manifest_hash text NOT NULL, receipt_hash text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(project_id,id),
 FOREIGN KEY(project_id,run_id) REFERENCES anvil.runs(project_id,id),
 FOREIGN KEY(project_id,import_id) REFERENCES anvil.import_batches(project_id,id)
);
ALTER TABLE anvil.external_result_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.external_result_receipts FORCE ROW LEVEL SECURITY;
CREATE POLICY project_scope ON anvil.external_result_receipts USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id));
GRANT SELECT,INSERT ON anvil.external_result_receipts TO anvil_app;
GRANT SELECT ON anvil.external_result_receipts TO anvil_worker;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.external_result_receipts FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
ALTER TABLE anvil.episodes ADD external_provenance jsonb;
CREATE FUNCTION anvil.immutable_external_provenance() RETURNS trigger LANGUAGE plpgsql AS $$
 BEGIN
 IF NEW.external_provenance IS DISTINCT FROM OLD.external_provenance THEN
 RAISE EXCEPTION 'immutable external provenance'; END IF;
 RETURN NEW;
 END $$;
CREATE TRIGGER immutable_external_provenance BEFORE UPDATE ON anvil.episodes FOR EACH ROW EXECUTE FUNCTION anvil.immutable_external_provenance();
INSERT INTO anvil.schema_versions(version) VALUES(6);
