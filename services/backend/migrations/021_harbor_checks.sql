-- Add deterministic negative-check selection; no paid/custom agent path.
ALTER TABLE anvil.harbor_checks DROP CONSTRAINT harbor_checks_candidate_check;
ALTER TABLE anvil.harbor_checks ADD CHECK(candidate IN ('reference','empty_output','constraint_failure'));
-- Explicitly repeat worker bootstrap grants for existing development schema020 installs.
GRANT SELECT(id,created_by,project_id) ON anvil.harbor_checks TO anvil_worker;
CREATE OR REPLACE FUNCTION anvil.claim_harbor_job() RETURNS SETOF anvil.jobs LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
 BEGIN
 RETURN QUERY UPDATE anvil.jobs SET status='leased',lease_token=gen_random_uuid(),
 lease_until=now()+interval '60 seconds',attempts=attempts+1
 WHERE id=(SELECT id FROM anvil.jobs WHERE kind='harbor_check' AND
 (status='queued' OR (status='leased' AND lease_until<now())) AND attempts<3
 ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *;
 END $$;
REVOKE ALL ON FUNCTION anvil.claim_harbor_job() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.claim_harbor_job() TO anvil_worker;
CREATE TABLE anvil.praxis_export_receipts (
 id uuid PRIMARY KEY, project_id uuid NOT NULL, source_id uuid NOT NULL,
 envelope_sha256 char(64) NOT NULL, envelope_artifact_id uuid NOT NULL, lineage jsonb NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id), created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,envelope_sha256),
 FOREIGN KEY(project_id,source_id) REFERENCES anvil.praxis_sources(project_id,id),
 FOREIGN KEY(project_id,envelope_artifact_id) REFERENCES anvil.artifacts(project_id,id)
);
ALTER TABLE anvil.praxis_export_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.praxis_export_receipts FORCE ROW LEVEL SECURITY;
CREATE POLICY project_scope ON anvil.praxis_export_receipts USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id));
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.praxis_export_receipts FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
GRANT SELECT,INSERT ON anvil.praxis_export_receipts TO anvil_app;
INSERT INTO anvil.schema_versions(version) VALUES(21);
