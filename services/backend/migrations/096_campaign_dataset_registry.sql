-- Anvil provisions immutable case packs; Praxis only copies discovery refs.
CREATE TABLE anvil.campaign_dataset_versions(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),dataset_key text NOT NULL,version text NOT NULL,
 manifest jsonb NOT NULL CHECK(octet_length(manifest::text)<=4194304),manifest_sha256 text NOT NULL,
 source_sha256 text NOT NULL,fixture_manifest jsonb NOT NULL,fixture_manifest_sha256 text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(project_id,id),UNIQUE(project_id,dataset_key,version));
CREATE TABLE anvil.campaign_dataset_qualifications(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,dataset_id uuid NOT NULL,
 source_sha256 text NOT NULL,runtime_sha256 text NOT NULL,runtime_image_sha256 text NOT NULL,
 receipt jsonb NOT NULL,receipt_sha256 text NOT NULL,expires_at timestamptz NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,dataset_id) REFERENCES anvil.campaign_dataset_versions(project_id,id),UNIQUE(project_id,id));
CREATE TABLE anvil.campaign_dataset_revocations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,qualification_id uuid NOT NULL,reason text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,qualification_id) REFERENCES anvil.campaign_dataset_qualifications(project_id,id),UNIQUE(qualification_id));
DO $$ DECLARE t text;BEGIN FOREACH t IN ARRAY ARRAY['campaign_dataset_versions','campaign_dataset_qualifications','campaign_dataset_revocations'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY engineer_read ON anvil.%I FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id))',t);
 EXECUTE format('CREATE POLICY runtime_read ON anvil.%I FOR SELECT TO anvil_golden_scheduler,anvil_golden_grader USING(banking.runtime_scope(project_id))',t);
 EXECUTE format('GRANT SELECT ON anvil.%I TO anvil_app,anvil_golden_scheduler,anvil_golden_grader',t);
 EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
END LOOP;END $$;
INSERT INTO anvil.schema_versions(version) VALUES(96);
