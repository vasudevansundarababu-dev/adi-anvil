-- Separate immutable audit facts; these can never satisfy qualification/admission.
CREATE TABLE anvil.benchmark_trace_audit (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 project_id uuid NOT NULL REFERENCES anvil.projects(id),
 artifact_id uuid NOT NULL,
 source_record_sha256 text NOT NULL CHECK(source_record_sha256 ~ '^[a-f0-9]{64}$'),
 source_commit text NOT NULL CHECK(source_commit ~ '^[a-f0-9]{40}$'),
 source_packet_sha256 text NOT NULL CHECK(source_packet_sha256 ~ '^[a-f0-9]{64}$'),
 recorded_at timestamptz NOT NULL,
 environment text NOT NULL CHECK(environment IN ('linux_qa','local_qa','unrecorded')),
 metadata jsonb NOT NULL CHECK(jsonb_typeof(metadata)='object' AND octet_length(metadata::text)<=16384),
 imported_by uuid NOT NULL REFERENCES anvil.users(id),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id), UNIQUE(project_id,source_record_sha256),
 FOREIGN KEY(project_id,artifact_id) REFERENCES anvil.artifacts(project_id,id),
 CHECK(metadata->>'origin'='original_synthetic_software_conformance'),
 CHECK(metadata->>'kind'='historical_control'),
 CHECK(metadata->>'current_authority'='false'),
 CHECK(metadata->>'measured_model_performance'='false')
);
ALTER TABLE anvil.benchmark_trace_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.benchmark_trace_audit FORCE ROW LEVEL SECURITY;
CREATE POLICY private_project_audit ON anvil.benchmark_trace_audit USING(
 anvil.in_scope(project_id) AND anvil.benchmark_private_access(project_id,'benchmark_trace',artifact_id));
GRANT SELECT ON anvil.benchmark_trace_audit TO anvil_app;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.benchmark_trace_audit
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE FUNCTION anvil.guard_dashboard_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM anvil.artifacts a WHERE a.project_id=NEW.project_id AND a.id=NEW.artifact_id
 AND a.classification='benchmark_trace' AND a.sha256=NEW.source_record_sha256 AND a.byte_size<=2097152)
 THEN RAISE EXCEPTION 'audit trace requires exact canonical restricted receipt';END IF;
 RETURN NEW; END $$;
CREATE TRIGGER exact_receipt BEFORE INSERT ON anvil.benchmark_trace_audit
 FOR EACH ROW EXECUTE FUNCTION anvil.guard_dashboard_audit();
CREATE INDEX benchmark_trace_audit_context ON anvil.benchmark_trace_audit(project_id,recorded_at,id);
INSERT INTO anvil.schema_versions(version) VALUES('060') ON CONFLICT DO NOTHING;
