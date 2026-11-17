-- A generic protocol revision is never proof that benchmark freeze ran.
CREATE TABLE anvil.benchmark_protocol_bindings (
 project_id uuid NOT NULL,protocol_revision_id uuid NOT NULL,benchmark_revision_id uuid NOT NULL,
 subject_sha256 text NOT NULL CHECK(subject_sha256~'^[a-f0-9]{64}$'),
 runtime_sha256 text NOT NULL CHECK(runtime_sha256~'^[a-f0-9]{64}$'),
 review_policy_sha256 text NOT NULL CHECK(review_policy_sha256~'^[a-f0-9]{64}$'),
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(project_id,protocol_revision_id),
 FOREIGN KEY(project_id,protocol_revision_id) REFERENCES anvil.revisions(project_id,id),
 FOREIGN KEY(project_id,benchmark_revision_id) REFERENCES anvil.benchmark_version_bindings(project_id,benchmark_revision_id)
);
ALTER TABLE anvil.benchmark_protocol_bindings ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.benchmark_protocol_bindings FORCE ROW LEVEL SECURITY;
CREATE POLICY project_scope ON anvil.benchmark_protocol_bindings USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id));
GRANT SELECT,INSERT ON anvil.benchmark_protocol_bindings TO anvil_app;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.benchmark_protocol_bindings FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE FUNCTION anvil.guard_benchmark_protocol_receipt() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM anvil.revisions r JOIN anvil.resources resource ON resource.project_id=r.project_id AND resource.id=r.resource_id
 WHERE r.project_id=NEW.project_id AND r.id=NEW.protocol_revision_id AND resource.kind='protocol'
 AND r.created_by=NEW.created_by AND r.content_hash=NEW.subject_sha256
 AND r.content->>'profile'='sme-comparison-v1' AND r.content->>'runtime_sha256'=NEW.runtime_sha256
 AND (r.content->>'benchmark_revision_id')::uuid=NEW.benchmark_revision_id)
 THEN RAISE EXCEPTION 'benchmark protocol requires its exact server freeze receipt';END IF;RETURN NEW;END $$;
CREATE TRIGGER exact_freeze BEFORE INSERT ON anvil.benchmark_protocol_bindings FOR EACH ROW EXECUTE FUNCTION anvil.guard_benchmark_protocol_receipt();
INSERT INTO anvil.schema_versions(version) VALUES(54);
