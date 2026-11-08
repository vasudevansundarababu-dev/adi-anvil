-- Preserve053 byte/history and add a narrow current-role wrapper. An operator
-- downgraded to a read-only legacy role cannot finish even with an old duty.
ALTER FUNCTION anvil.finish_native_benchmark_capture(uuid,uuid,uuid,text,text) RENAME TO finish_native_benchmark_capture_bound;
REVOKE ALL ON FUNCTION anvil.finish_native_benchmark_capture_bound(uuid,uuid,uuid,text,text) FROM PUBLIC,anvil_benchmark_evaluator;
CREATE FUNCTION anvil.finish_native_benchmark_capture(p uuid,a uuid,f uuid,o text,h text) RETURNS uuid
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM anvil.benchmark_native_evaluator_custody n
 JOIN anvil.benchmark_evaluator_jobs job ON job.project_id=n.project_id AND job.id=n.job_id
 JOIN anvil.memberships member ON member.project_id=job.project_id AND member.user_id=job.created_by
 JOIN anvil.users person ON person.id=member.user_id AND person.active
 WHERE n.project_id=p AND n.attempt_id=a AND n.fence=f AND member.active AND member.role IN ('admin','rl-engineer'))
 THEN RETURN NULL;END IF;
 RETURN anvil.finish_native_benchmark_capture_bound(p,a,f,o,h);
 END $$;
REVOKE ALL ON FUNCTION anvil.finish_native_benchmark_capture(uuid,uuid,uuid,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.finish_native_benchmark_capture(uuid,uuid,uuid,text,text) TO anvil_benchmark_evaluator;
INSERT INTO anvil.schema_versions(version) VALUES(56);
