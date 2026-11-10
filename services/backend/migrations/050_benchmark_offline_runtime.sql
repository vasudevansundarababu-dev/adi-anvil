-- Offline SDK conformance only. Canonical comparison/cell/attempt identity remains
-- in041; this journal is fenced runtime state, not an alternative score system.
CREATE TABLE anvil.benchmark_offline_runtime (
 project_id uuid NOT NULL,attempt_id uuid NOT NULL,run_id uuid NOT NULL,
 state text NOT NULL CHECK(state IN ('queued','claimed','intent','captured','completed','operational_failed','dispatch_unknown','cancelled')),
 fence uuid NOT NULL,generation bigint NOT NULL DEFAULT 1 CHECK(generation>0),
 lease_until timestamptz,report_artifact_id uuid,output_artifact_id uuid,
 reason_code text CHECK(reason_code~'^[a-z][a-z0-9_]{0,79}$'),
 created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(project_id,attempt_id),
 FOREIGN KEY(project_id,attempt_id) REFERENCES anvil.benchmark_cell_attempts(project_id,id),
 FOREIGN KEY(project_id,run_id) REFERENCES anvil.benchmark_comparisons(project_id,run_id),
 FOREIGN KEY(project_id,report_artifact_id) REFERENCES anvil.artifacts(project_id,id),
 FOREIGN KEY(project_id,output_artifact_id) REFERENCES anvil.artifacts(project_id,id)
);
ALTER TABLE anvil.benchmark_offline_runtime ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.benchmark_offline_runtime FORCE ROW LEVEL SECURITY;
CREATE POLICY project_scope ON anvil.benchmark_offline_runtime USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id));
GRANT SELECT,INSERT,UPDATE ON anvil.benchmark_offline_runtime TO anvil_app;
CREATE FUNCTION anvil.guard_benchmark_offline_runtime() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='DELETE' OR ROW(NEW.project_id,NEW.attempt_id,NEW.run_id,NEW.fence,NEW.generation,NEW.created_at)
 IS DISTINCT FROM ROW(OLD.project_id,OLD.attempt_id,OLD.run_id,OLD.fence,OLD.generation,OLD.created_at)
 OR OLD.state IN ('completed','operational_failed','dispatch_unknown','cancelled')
 OR NOT ((OLD.state='queued' AND NEW.state IN ('claimed','cancelled'))
 OR (OLD.state='claimed' AND NEW.state IN ('intent','operational_failed','cancelled'))
 OR (OLD.state='intent' AND NEW.state IN ('captured','dispatch_unknown'))
 OR (OLD.state='captured' AND NEW.state IN ('completed','operational_failed')))
 OR (OLD.report_artifact_id IS NOT NULL AND NEW.report_artifact_id IS DISTINCT FROM OLD.report_artifact_id)
 OR (OLD.output_artifact_id IS NOT NULL AND NEW.output_artifact_id IS DISTINCT FROM OLD.output_artifact_id)
 THEN RAISE EXCEPTION 'immutable benchmark offline fence or invalid transition'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER fenced_transition BEFORE UPDATE OR DELETE ON anvil.benchmark_offline_runtime FOR EACH ROW EXECUTE FUNCTION anvil.guard_benchmark_offline_runtime();
INSERT INTO anvil.schema_versions(version) VALUES(50);
