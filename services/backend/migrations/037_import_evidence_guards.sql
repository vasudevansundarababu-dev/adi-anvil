-- Terminal usage capture survives actor revocation; private artifacts remain restricted.
GRANT SELECT,UPDATE ON anvil.executable_imports,anvil.executable_import_revisions,anvil.import_generation_calls TO anvil_worker;
CREATE FUNCTION anvil.guard_import_family() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF ROW(NEW.id,NEW.project_id,NEW.source_id,NEW.settings_id,NEW.cap_micro_usd,NEW.created_by,NEW.created_at)
 IS DISTINCT FROM ROW(OLD.id,OLD.project_id,OLD.source_id,OLD.settings_id,OLD.cap_micro_usd,OLD.created_by,OLD.created_at)
 OR NEW.charged_micro_usd<OLD.charged_micro_usd THEN RAISE EXCEPTION 'immutable import configuration/cumulative spend'; END IF;
 RETURN NEW; END $$;
CREATE TRIGGER guard_import_family BEFORE UPDATE OR DELETE ON anvil.executable_imports FOR EACH ROW EXECUTE FUNCTION anvil.guard_import_family();
CREATE FUNCTION anvil.guard_import_revision() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='DELETE' OR OLD.finished_at IS NOT NULL
 OR ROW(NEW.id,NEW.project_id,NEW.import_id,NEW.base_revision_id,NEW.kind,NEW.created_by,NEW.created_at)
 IS DISTINCT FROM ROW(OLD.id,OLD.project_id,OLD.import_id,OLD.base_revision_id,OLD.kind,OLD.created_by,OLD.created_at)
 OR (OLD.bundle_artifact_id IS NOT NULL AND NEW.bundle_artifact_id IS DISTINCT FROM OLD.bundle_artifact_id)
 THEN RAISE EXCEPTION 'immutable generated evidence: create a successor draft'; END IF;
 RETURN NEW; END $$;
CREATE TRIGGER guard_import_revision BEFORE UPDATE OR DELETE ON anvil.executable_import_revisions FOR EACH ROW EXECUTE FUNCTION anvil.guard_import_revision();
CREATE FUNCTION anvil.guard_import_call() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='DELETE' OR OLD.state<>'intent'
 OR ROW(NEW.id,NEW.project_id,NEW.import_id,NEW.revision_id,NEW.reservation_micro_usd,NEW.request_sha256,NEW.created_at)
 IS DISTINCT FROM ROW(OLD.id,OLD.project_id,OLD.import_id,OLD.revision_id,OLD.reservation_micro_usd,OLD.request_sha256,OLD.created_at)
 THEN RAISE EXCEPTION 'immutable generation intent/outcome'; END IF;
 RETURN NEW; END $$;
CREATE TRIGGER guard_import_call BEFORE UPDATE OR DELETE ON anvil.import_generation_calls FOR EACH ROW EXECUTE FUNCTION anvil.guard_import_call();
INSERT INTO anvil.schema_versions(version) VALUES(37);
