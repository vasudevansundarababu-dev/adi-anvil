CREATE TABLE anvil.benchmark_offline_reconciliations (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,attempt_id uuid NOT NULL,fence uuid NOT NULL,
 operator_id uuid NOT NULL REFERENCES anvil.users(id),evidence_artifact_id uuid NOT NULL,
 evidence_sha256 text NOT NULL CHECK(evidence_sha256~'^[a-f0-9]{64}$'),
 disposition text NOT NULL CHECK(disposition='operator_attested_stopped_outcome_unknown'),
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(project_id,id),UNIQUE(project_id,attempt_id),
 FOREIGN KEY(project_id,attempt_id) REFERENCES anvil.benchmark_offline_runtime(project_id,attempt_id),
 FOREIGN KEY(project_id,evidence_artifact_id) REFERENCES anvil.artifacts(project_id,id)
);
ALTER TABLE anvil.benchmark_offline_reconciliations ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.benchmark_offline_reconciliations FORCE ROW LEVEL SECURITY;
CREATE POLICY project_scope ON anvil.benchmark_offline_reconciliations USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id));
CREATE POLICY assigned_admin ON anvil.benchmark_offline_reconciliations AS RESTRICTIVE FOR INSERT WITH CHECK(
 operator_id=nullif(current_setting('anvil.user',true),'')::uuid AND anvil.benchmark_is_admin(project_id,operator_id)
 AND anvil.benchmark_private_access(project_id,'benchmark_trace',evidence_artifact_id));
GRANT SELECT,INSERT ON anvil.benchmark_offline_reconciliations TO anvil_app;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.benchmark_offline_reconciliations FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE FUNCTION anvil.guard_offline_reconciliation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM anvil.benchmark_offline_runtime rt
 JOIN anvil.benchmark_cell_attempts a ON a.project_id=rt.project_id AND a.id=rt.attempt_id
 JOIN anvil.harbor_agent_plans plan ON plan.project_id=a.project_id AND plan.id=a.plan_id
 JOIN anvil.artifacts proof ON proof.project_id=rt.project_id AND proof.id=NEW.evidence_artifact_id
 AND proof.classification='benchmark_trace' AND proof.sha256=NEW.evidence_sha256
 WHERE rt.project_id=NEW.project_id AND rt.attempt_id=NEW.attempt_id AND rt.fence=NEW.fence
 AND rt.state='dispatch_unknown' AND plan.config->>'transport'='offline_contract')
 THEN RAISE EXCEPTION 'reconciliation requires the exact unknown offline capture and private operator evidence';END IF;RETURN NEW;END $$;
CREATE TRIGGER exact_unknown BEFORE INSERT ON anvil.benchmark_offline_reconciliations FOR EACH ROW EXECUTE FUNCTION anvil.guard_offline_reconciliation();
INSERT INTO anvil.schema_versions(version) VALUES(55);
