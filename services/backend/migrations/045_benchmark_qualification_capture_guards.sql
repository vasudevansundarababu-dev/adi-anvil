CREATE FUNCTION anvil.guard_benchmark_qualification_result() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM anvil.benchmark_qualification_operations o
 JOIN anvil.benchmark_builds b ON b.project_id=o.project_id AND b.id=o.build_id
 JOIN anvil.benchmark_source_reviews r ON r.project_id=b.project_id AND r.id=b.review_id
 JOIN anvil.benchmark_qualifications q ON q.project_id=o.project_id AND q.id=NEW.qualification_id
 JOIN anvil.harbor_packages p ON p.project_id=q.project_id AND p.id=q.package_id
 JOIN anvil.artifacts a ON a.project_id=q.project_id AND a.id=q.report_artifact_id
 WHERE o.project_id=NEW.project_id AND o.id=NEW.operation_id AND o.build_id=NEW.build_id AND o.state='running'
 AND o.lease_until>now() AND q.package_sha256=p.package_sha256
 AND q.evaluator_binding_id=r.evaluator_binding_id AND a.classification='benchmark_trace'
 AND q.compiler_sha256=b.dependencies->'sources'->>'services/backend/src/anvil/benchmark_compiler.py')
 THEN RAISE EXCEPTION 'qualification result does not bind a live private build'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER benchmark_qualification_result_binding BEFORE INSERT ON anvil.benchmark_operation_results
 FOR EACH ROW EXECUTE FUNCTION anvil.guard_benchmark_qualification_result();
CREATE FUNCTION anvil.guard_benchmark_passed_operation() RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE expected int; actual int; BEGIN
 IF NEW.state='passed' THEN
 SELECT count(*) INTO expected FROM anvil.benchmark_build_tasks WHERE project_id=NEW.project_id AND build_id=NEW.build_id;
 SELECT count(*) INTO actual FROM anvil.benchmark_operation_results r JOIN anvil.benchmark_qualifications q
 ON q.project_id=r.project_id AND q.id=r.qualification_id WHERE r.project_id=NEW.project_id AND r.operation_id=NEW.id
 AND q.outcome='passed' AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_qualification_events e WHERE e.project_id=q.project_id AND e.qualification_id=q.id);
 IF expected=0 OR expected<>actual OR NEW.report_artifact_id IS NULL OR OLD.lease_until<=now()
 THEN RAISE EXCEPTION 'complete current qualification evidence required'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER benchmark_operation_pass_binding BEFORE UPDATE ON anvil.benchmark_qualification_operations
 FOR EACH ROW EXECUTE FUNCTION anvil.guard_benchmark_passed_operation();
CREATE POLICY benchmark_qualification_author ON anvil.benchmark_qualifications AS RESTRICTIVE FOR INSERT WITH CHECK(
 reviewed_by=nullif(current_setting('anvil.user',true),'')::uuid AND anvil.benchmark_is_admin(project_id,reviewed_by));
CREATE POLICY benchmark_qualification_revoker ON anvil.benchmark_qualification_events AS RESTRICTIVE FOR INSERT WITH CHECK(
 actor_id=nullif(current_setting('anvil.user',true),'')::uuid AND anvil.benchmark_is_admin(project_id,actor_id));
INSERT INTO anvil.schema_versions(version) VALUES(45);
