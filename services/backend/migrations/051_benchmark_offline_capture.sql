ALTER TABLE anvil.benchmark_offline_runtime ADD duration_ms bigint CHECK(duration_ms>=0);
CREATE FUNCTION anvil.guard_benchmark_offline_capture() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF (NEW.output_artifact_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM anvil.artifacts a WHERE a.project_id=NEW.project_id AND a.id=NEW.output_artifact_id AND a.classification='benchmark_sealed'))
 OR (NEW.report_artifact_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM anvil.artifacts a WHERE a.project_id=NEW.project_id AND a.id=NEW.report_artifact_id AND a.classification='benchmark_trace'))
 OR (TG_OP='UPDATE' AND OLD.duration_ms IS NOT NULL AND NEW.duration_ms IS DISTINCT FROM OLD.duration_ms)
 OR (NEW.state IN ('captured','completed') AND (NEW.output_artifact_id IS NULL OR NEW.report_artifact_id IS NULL OR NEW.duration_ms IS NULL))
 THEN RAISE EXCEPTION 'offline capture requires exact sealed output, private trace and measured duration';END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER capture_binding BEFORE INSERT OR UPDATE ON anvil.benchmark_offline_runtime FOR EACH ROW EXECUTE FUNCTION anvil.guard_benchmark_offline_capture();
INSERT INTO anvil.schema_versions(version) VALUES(51);
