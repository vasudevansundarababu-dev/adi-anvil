CREATE FUNCTION anvil.immutable_external_execution() RETURNS trigger LANGUAGE plpgsql AS $$
 BEGIN
 IF OLD.external_provenance IS NOT NULL AND
 ROW(NEW.project_id,NEW.run_id,NEW.task_revision_id,NEW.candidate_key,NEW.output_artifact_id,NEW.thread_id,NEW.graph_version)
 IS DISTINCT FROM ROW(OLD.project_id,OLD.run_id,OLD.task_revision_id,OLD.candidate_key,OLD.output_artifact_id,OLD.thread_id,OLD.graph_version) THEN
 RAISE EXCEPTION 'immutable imported execution binding'; END IF;
 RETURN NEW;
 END $$;
CREATE TRIGGER immutable_external_execution BEFORE UPDATE ON anvil.episodes FOR EACH ROW EXECUTE FUNCTION anvil.immutable_external_execution();
ALTER TABLE anvil.episodes ADD CHECK(external_provenance IS NULL OR (invocation_count=0 AND candidate_key='external-reported' AND graph_version='external-static-review-v1'));
INSERT INTO anvil.schema_versions(version) VALUES(7);
