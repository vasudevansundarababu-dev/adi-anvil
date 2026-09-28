CREATE FUNCTION anvil.immutable_run_binding() RETURNS trigger LANGUAGE plpgsql AS $$
 BEGIN
 IF ROW(NEW.id,NEW.project_id,NEW.protocol_revision_id,NEW.origin,NEW.created_by,NEW.created_at)
 IS DISTINCT FROM ROW(OLD.id,OLD.project_id,OLD.protocol_revision_id,OLD.origin,OLD.created_by,OLD.created_at) THEN
 RAISE EXCEPTION 'immutable run binding'; END IF;
 RETURN NEW;
 END $$;
CREATE TRIGGER immutable_run_binding BEFORE UPDATE ON anvil.runs FOR EACH ROW EXECUTE FUNCTION anvil.immutable_run_binding();

CREATE FUNCTION anvil.immutable_episode_binding() RETURNS trigger LANGUAGE plpgsql AS $$
 BEGIN
 IF ROW(NEW.id,NEW.project_id,NEW.run_id,NEW.task_revision_id,NEW.candidate_key,NEW.thread_id,NEW.graph_version,NEW.created_at)
 IS DISTINCT FROM ROW(OLD.id,OLD.project_id,OLD.run_id,OLD.task_revision_id,OLD.candidate_key,OLD.thread_id,OLD.graph_version,OLD.created_at) THEN
 RAISE EXCEPTION 'immutable episode binding'; END IF;
 IF OLD.output_artifact_id IS NOT NULL AND NEW.output_artifact_id IS DISTINCT FROM OLD.output_artifact_id THEN
 RAISE EXCEPTION 'immutable captured output'; END IF;
 IF NEW.invocation_count < OLD.invocation_count THEN
 RAISE EXCEPTION 'invocation history cannot decrease'; END IF;
 RETURN NEW;
 END $$;
CREATE TRIGGER immutable_runtime_binding BEFORE UPDATE ON anvil.episodes FOR EACH ROW EXECUTE FUNCTION anvil.immutable_episode_binding();
ALTER TABLE anvil.episodes ADD CHECK(invocation_count BETWEEN 0 AND 1);
INSERT INTO anvil.schema_versions(version) VALUES(9);
