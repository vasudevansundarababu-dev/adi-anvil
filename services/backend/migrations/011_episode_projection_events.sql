CREATE FUNCTION anvil.episode_projection_event() RETURNS trigger LANGUAGE plpgsql AS $$
 BEGIN
 IF TG_OP='INSERT' OR ROW(NEW.state,NEW.outcome,NEW.score,NEW.final_assessment_id,NEW.invalidity_resolution_id)
 IS DISTINCT FROM ROW(OLD.state,OLD.outcome,OLD.score,OLD.final_assessment_id,OLD.invalidity_resolution_id) THEN
 INSERT INTO anvil.graph_outbox(project_id,resource_id)
 SELECT NEW.project_id,resource_id FROM anvil.revisions WHERE id=NEW.task_revision_id AND project_id=NEW.project_id;
 END IF;
 RETURN NEW;
 END $$;
CREATE TRIGGER episode_projection_event AFTER INSERT OR UPDATE OF state,outcome,score,final_assessment_id,invalidity_resolution_id
 ON anvil.episodes FOR EACH ROW EXECUTE FUNCTION anvil.episode_projection_event();
INSERT INTO anvil.schema_versions(version) VALUES(11);
