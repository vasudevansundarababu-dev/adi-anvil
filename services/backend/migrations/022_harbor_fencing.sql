-- Worker can record terminal failures after submitter revocation, without reading private packages.
GRANT UPDATE(state,result,error_code,finished_at) ON anvil.harbor_checks TO anvil_worker;
CREATE FUNCTION anvil.guard_harbor_check() RETURNS trigger LANGUAGE plpgsql AS $$
 BEGIN
 IF ROW(NEW.id,NEW.project_id,NEW.package_id,NEW.created_by,NEW.candidate,NEW.created_at)
 IS DISTINCT FROM ROW(OLD.id,OLD.project_id,OLD.package_id,OLD.created_by,OLD.candidate,OLD.created_at)
 THEN RAISE EXCEPTION 'immutable Harbor execution binding'; END IF;
 IF OLD.state NOT IN ('queued','running') AND NEW IS DISTINCT FROM OLD
 THEN RAISE EXCEPTION 'immutable terminal Harbor evidence'; END IF;
 IF NEW.invocation_count < OLD.invocation_count OR NEW.invocation_count > 1
 THEN RAISE EXCEPTION 'invalid Harbor invocation count'; END IF;
 RETURN NEW;
 END $$;
CREATE TRIGGER guard_harbor_check BEFORE UPDATE OR DELETE ON anvil.harbor_checks
 FOR EACH ROW EXECUTE FUNCTION anvil.guard_harbor_check();
INSERT INTO anvil.schema_versions(version) VALUES(22);
