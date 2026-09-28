ALTER TABLE anvil.budget_reservations ADD UNIQUE(project_id,id);
ALTER TABLE anvil.interactive_calls DROP CONSTRAINT interactive_calls_reservation_id_fkey;
ALTER TABLE anvil.interactive_calls ADD FOREIGN KEY(project_id,reservation_id)
 REFERENCES anvil.budget_reservations(project_id,id);
CREATE FUNCTION anvil.immutable_interactive_binding() RETURNS trigger LANGUAGE plpgsql AS $$
 BEGIN
 IF ROW(NEW.project_id,NEW.episode_id,NEW.environment_version,NEW.harness_version)
 IS DISTINCT FROM ROW(OLD.project_id,OLD.episode_id,OLD.environment_version,OLD.harness_version) THEN
 RAISE EXCEPTION 'immutable interactive environment binding'; END IF;
 IF NEW.step < OLD.step OR NEW.step > OLD.step + 1 THEN
 RAISE EXCEPTION 'interactive steps must advance sequentially'; END IF;
 RETURN NEW;
 END $$;
CREATE TRIGGER immutable_interactive_binding BEFORE UPDATE ON anvil.interactive_sessions
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable_interactive_binding();
INSERT INTO anvil.schema_versions(version) VALUES(16);
