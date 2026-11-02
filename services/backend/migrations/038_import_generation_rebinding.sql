-- Explicit configuration changes preserve the original cap/ledger and every old revision.
ALTER TABLE anvil.executable_imports ADD COLUMN active_settings_id uuid REFERENCES anvil.import_generation_settings(id);
UPDATE anvil.executable_imports SET active_settings_id=settings_id;
ALTER TABLE anvil.executable_import_revisions ADD COLUMN settings_id uuid REFERENCES anvil.import_generation_settings(id);
ALTER TABLE anvil.executable_import_revisions DISABLE TRIGGER guard_import_revision;
UPDATE anvil.executable_import_revisions r SET settings_id=i.settings_id FROM anvil.executable_imports i WHERE i.id=r.import_id;
ALTER TABLE anvil.executable_import_revisions ENABLE TRIGGER guard_import_revision;
ALTER TABLE anvil.executable_import_revisions ALTER COLUMN settings_id SET NOT NULL;
CREATE OR REPLACE FUNCTION anvil.guard_import_revision() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='DELETE' OR OLD.finished_at IS NOT NULL
 OR ROW(NEW.id,NEW.project_id,NEW.import_id,NEW.base_revision_id,NEW.settings_id,NEW.kind,NEW.created_by,NEW.created_at)
 IS DISTINCT FROM ROW(OLD.id,OLD.project_id,OLD.import_id,OLD.base_revision_id,OLD.settings_id,OLD.kind,OLD.created_by,OLD.created_at)
 OR (OLD.bundle_artifact_id IS NOT NULL AND NEW.bundle_artifact_id IS DISTINCT FROM OLD.bundle_artifact_id)
 THEN RAISE EXCEPTION 'immutable generated evidence: create a successor draft'; END IF;
 RETURN NEW; END $$;
INSERT INTO anvil.schema_versions(version) VALUES(38);
