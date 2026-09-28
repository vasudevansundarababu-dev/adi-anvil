ALTER TABLE anvil.task_imports DROP CONSTRAINT task_imports_status_check;
ALTER TABLE anvil.task_imports ADD CHECK(status IN ('queued','extracting','validating','invalid','ready','published','failed','cancelled'));
CREATE TABLE anvil.ingestion_jobs (
 id uuid PRIMARY KEY, project_id uuid NOT NULL, import_id uuid NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id), import_revision integer NOT NULL,
 state text NOT NULL DEFAULT 'queued', checkpoint integer NOT NULL DEFAULT 0,
 records_total integer NOT NULL DEFAULT 0, bytes_processed bigint NOT NULL DEFAULT 0,
 started_at timestamptz, finished_at timestamptz, retries integer NOT NULL DEFAULT 0,
 error_code text, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(import_id,import_revision), UNIQUE(project_id,id),
 FOREIGN KEY(project_id,import_id) REFERENCES anvil.task_imports(project_id,id)
);
CREATE TABLE anvil.ingestion_chunks (
 project_id uuid NOT NULL, ingestion_id uuid NOT NULL, chunk_offset integer NOT NULL,
 record_count integer NOT NULL, content_sha256 char(64) NOT NULL,
 PRIMARY KEY(ingestion_id,chunk_offset),
 FOREIGN KEY(project_id,ingestion_id) REFERENCES anvil.ingestion_jobs(project_id,id)
);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['ingestion_jobs','ingestion_chunks'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY project_scope ON anvil.%I USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id))',t);
 EXECUTE format('CREATE INDEX ON anvil.%I(project_id)',t);
 EXECUTE format('GRANT SELECT,INSERT,UPDATE ON anvil.%I TO anvil_app',t);
 END LOOP;
END $$;
GRANT SELECT,UPDATE ON anvil.ingestion_jobs TO anvil_worker;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.ingestion_chunks
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
INSERT INTO anvil.schema_versions(version) VALUES(14);
