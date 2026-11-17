ALTER TABLE anvil.artifacts ADD CONSTRAINT benchmark_private_namespace CHECK(
 classification NOT IN ('benchmark_raw','benchmark_eval','benchmark_judge','benchmark_trace')
 OR (object_key='benchmark-vault/'||project_id::text||'/'||classification||'/'||sha256::text
 AND scan_status='quarantined' AND sha256::text~'^[a-f0-9]{64}$'));
ALTER TABLE anvil.benchmark_receipt_events ADD CONSTRAINT verified_source_acceptance
 CHECK(source_state<>'accepted' OR signature_status='verified');
CREATE POLICY evaluator_job_initial_state ON anvil.benchmark_evaluator_jobs AS RESTRICTIVE FOR INSERT WITH CHECK(
 created_by=nullif(current_setting('anvil.user',true),'')::uuid AND state='queued'
 AND lease_token IS NULL AND lease_until IS NULL);
CREATE FUNCTION anvil.guard_benchmark_sealed_output() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM anvil.artifacts a WHERE a.project_id=NEW.project_id
 AND a.id=NEW.sealed_output_artifact_id AND a.classification='benchmark_output')
 THEN RAISE EXCEPTION 'evaluator requires sealed benchmark output'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER benchmark_sealed_output BEFORE INSERT ON anvil.benchmark_evaluator_jobs
 FOR EACH ROW EXECUTE FUNCTION anvil.guard_benchmark_sealed_output();
CREATE FUNCTION anvil.guard_benchmark_receipt_event() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM anvil.benchmark_bundle_receipts r WHERE r.project_id=NEW.project_id
 AND r.id=NEW.receipt_id AND r.manifest_sha256=NEW.subject_sha256)
 THEN RAISE EXCEPTION 'receipt event subject mismatch'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER benchmark_event_binding BEFORE INSERT ON anvil.benchmark_receipt_events
 FOR EACH ROW EXECUTE FUNCTION anvil.guard_benchmark_receipt_event();
INSERT INTO anvil.schema_versions(version) VALUES(40);
