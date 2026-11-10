ALTER TABLE anvil.environment_records ADD CONSTRAINT environment_record_identity CHECK(jsonb_typeof(content)='object' AND content->>'id'=record_id);
CREATE FUNCTION anvil.environment_instance_transition() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF (NEW.id,NEW.project_id,NEW.environment_id,NEW.initial_sha256,NEW.created_by,NEW.created_at)
 IS DISTINCT FROM (OLD.id,OLD.project_id,OLD.environment_id,OLD.initial_sha256,OLD.created_by,OLD.created_at)
 THEN RAISE EXCEPTION 'environment instance identity is immutable';END IF;
 IF OLD.state='closed' OR NOT (
  (OLD.state='initializing' AND NEW.state='active' AND NEW.generation=OLD.generation)
  OR (OLD.state='active' AND NEW.state='active' AND NEW.generation=OLD.generation+1)
  OR (OLD.state='active' AND NEW.state='closed' AND NEW.generation=OLD.generation)
 ) THEN RAISE EXCEPTION 'invalid environment instance transition';END IF;
 RETURN NEW;END $$;
CREATE TRIGGER instance_transition BEFORE UPDATE ON anvil.environment_instances FOR EACH ROW EXECUTE FUNCTION anvil.environment_instance_transition();
CREATE FUNCTION anvil.environment_record_key() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF (NEW.project_id,NEW.instance_id) IS DISTINCT FROM (OLD.project_id,OLD.instance_id) THEN RAISE EXCEPTION 'component owner is immutable';END IF;
 IF TG_TABLE_NAME='environment_records' AND (to_jsonb(NEW)->>'collection',to_jsonb(NEW)->>'record_id') IS DISTINCT FROM (to_jsonb(OLD)->>'collection',to_jsonb(OLD)->>'record_id') THEN RAISE EXCEPTION 'record key is immutable';END IF;
 IF TG_TABLE_NAME='environment_files' AND to_jsonb(NEW)->>'path' IS DISTINCT FROM to_jsonb(OLD)->>'path' THEN RAISE EXCEPTION 'file path is immutable';END IF;
 RETURN NEW;END $$;
CREATE TRIGGER record_key BEFORE UPDATE ON anvil.environment_records FOR EACH ROW EXECUTE FUNCTION anvil.environment_record_key();
CREATE TRIGGER file_key BEFORE UPDATE ON anvil.environment_files FOR EACH ROW EXECUTE FUNCTION anvil.environment_record_key();
