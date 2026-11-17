ALTER TABLE anvil.benchmark_build_tasks
 ADD COLUMN environment_digest text CHECK(environment_digest~'^sha256:[a-f0-9]{64}$'),
 ADD COLUMN tool_schema_sha256 text CHECK(tool_schema_sha256~'^[a-f0-9]{64}$');
ALTER TABLE anvil.benchmark_operation_results ADD UNIQUE(project_id,qualification_id);
CREATE OR REPLACE FUNCTION anvil.guard_benchmark_qualification_result() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM anvil.benchmark_qualification_operations o
 JOIN anvil.benchmark_builds b ON b.project_id=o.project_id AND b.id=o.build_id
 JOIN anvil.benchmark_build_tasks t ON t.project_id=b.project_id AND t.build_id=b.id
 AND t.task_id=NEW.task_id AND t.source_id=NEW.source_id AND t.package_id=NEW.package_id
 JOIN anvil.benchmark_source_reviews r ON r.project_id=b.project_id AND r.id=b.review_id
 JOIN anvil.benchmark_qualifications q ON q.project_id=o.project_id AND q.id=NEW.qualification_id
 JOIN anvil.harbor_packages p ON p.project_id=q.project_id AND p.id=q.package_id
 JOIN anvil.artifacts a ON a.project_id=q.project_id AND a.id=q.report_artifact_id
 WHERE o.project_id=NEW.project_id AND o.id=NEW.operation_id AND o.build_id=NEW.build_id AND o.state='running'
 AND o.lease_until>now() AND q.created_at>=o.created_at AND q.reviewed_by=o.created_by
 AND q.package_sha256=p.package_sha256 AND q.environment_digest=t.environment_digest
 AND q.tool_schema_sha256=t.tool_schema_sha256 AND q.evaluator_binding_id=r.evaluator_binding_id
 AND a.classification='benchmark_trace' AND r.rights_confirmed AND r.expires_at>now()
 AND anvil.benchmark_is_admin(r.project_id,r.reviewed_by)
 AND anvil.benchmark_is_admin(o.project_id,o.created_by)
 AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_review_revocations v WHERE v.project_id=r.project_id
 AND (v.review_id=r.id OR (v.target='evaluator' AND v.review_id IN
 (SELECT id FROM anvil.benchmark_source_reviews WHERE evaluator_binding_id=r.evaluator_binding_id))))
 AND q.compiler_sha256=b.dependencies->'sources'->>'services/backend/src/anvil/benchmark_compiler.py')
 THEN RAISE EXCEPTION 'qualification result does not bind a live private build'; END IF;
 RETURN NEW;
END $$;
INSERT INTO anvil.schema_versions(version) VALUES(46);
