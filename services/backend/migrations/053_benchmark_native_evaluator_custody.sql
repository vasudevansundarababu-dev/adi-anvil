-- The app can enqueue evidence, never mark an evaluator jobfinished. A separate
-- restricted evaluator identity attests the exact previously captured native
-- fixture receipt. Generic T06 policy/requests/claims remain unchanged.
CREATE TABLE anvil.benchmark_native_evaluator_custody (
 project_id uuid NOT NULL,attempt_id uuid NOT NULL,job_id uuid NOT NULL,
 fence uuid NOT NULL,output_sha256 text NOT NULL CHECK(output_sha256~'^[a-f0-9]{64}$'),
 report_sha256 text NOT NULL CHECK(report_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(project_id,attempt_id),
 UNIQUE(project_id,job_id),
 FOREIGN KEY(project_id,attempt_id) REFERENCES anvil.benchmark_cell_attempts(project_id,id),
 FOREIGN KEY(project_id,job_id) REFERENCES anvil.benchmark_evaluator_jobs(project_id,id)
);
ALTER TABLE anvil.benchmark_native_evaluator_custody ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.benchmark_native_evaluator_custody FORCE ROW LEVEL SECURITY;
CREATE POLICY project_scope ON anvil.benchmark_native_evaluator_custody USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id));
GRANT SELECT,INSERT ON anvil.benchmark_native_evaluator_custody TO anvil_app;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.benchmark_native_evaluator_custody FOR EACH ROW EXECUTE FUNCTION anvil.immutable();

CREATE FUNCTION anvil.native_evaluator_capture_valid(p uuid,a uuid,f uuid,o text,h text) RETURNS boolean
 LANGUAGE sql STABLE SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
 SELECT EXISTS(SELECT 1 FROM anvil.benchmark_offline_runtime rt
 JOIN anvil.benchmark_cell_attempts ca ON ca.project_id=rt.project_id AND ca.id=rt.attempt_id
 JOIN anvil.benchmark_cells cell ON cell.project_id=ca.project_id AND cell.id=ca.cell_id
 JOIN anvil.benchmark_version_tasks task ON task.project_id=cell.project_id AND task.benchmark_revision_id=cell.benchmark_revision_id AND task.task_revision_id=cell.task_revision_id
 JOIN anvil.benchmark_qualifications q ON q.project_id=task.project_id AND q.id=task.qualification_id AND q.outcome='passed'
 JOIN anvil.benchmark_comparisons b ON b.project_id=cell.project_id AND b.run_id=cell.run_id
 JOIN anvil.revisions protocol ON protocol.project_id=b.project_id AND protocol.id=b.protocol_revision_id
 JOIN anvil.revisions version ON version.project_id=b.project_id AND version.id=b.benchmark_revision_id
 JOIN anvil.benchmark_builds build ON build.project_id=b.project_id AND build.id=(version.content->>'build_id')::uuid
 JOIN anvil.benchmark_source_reviews review ON review.project_id=build.project_id AND review.id=build.review_id
 JOIN anvil.artifacts output ON output.project_id=rt.project_id AND output.id=rt.output_artifact_id AND output.classification='benchmark_sealed' AND output.sha256=o
 JOIN anvil.artifacts report ON report.project_id=rt.project_id AND report.id=rt.report_artifact_id AND report.classification='benchmark_trace' AND report.sha256=h
 WHERE rt.project_id=p AND rt.attempt_id=a AND rt.fence=f AND rt.state='captured'
 AND protocol.content->>'origin'='original_synthetic_fixture'
 AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements(protocol.content->'slots') s WHERE s->>'transport'<>'offline_contract')
 AND review.expires_at>now()
 AND EXISTS(SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id AND u.active WHERE m.project_id=p AND m.user_id=review.reviewed_by AND m.active AND m.role='admin')
 AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_review_revocations r WHERE r.review_id=review.id OR (r.target='evaluator' AND r.review_id IN (SELECT id FROM anvil.benchmark_source_reviews WHERE evaluator_binding_id=review.evaluator_binding_id)))
 AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_qualification_events e WHERE e.qualification_id=q.id)) $$;
REVOKE ALL ON FUNCTION anvil.native_evaluator_capture_valid(uuid,uuid,uuid,text,text) FROM PUBLIC;

CREATE FUNCTION anvil.guard_native_evaluator_custody() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$ BEGIN
 IF NOT anvil.native_evaluator_capture_valid(NEW.project_id,NEW.attempt_id,NEW.fence,NEW.output_sha256,NEW.report_sha256)
 OR NOT EXISTS(SELECT 1 FROM anvil.benchmark_evaluator_jobs j
 JOIN anvil.benchmark_offline_runtime rt ON rt.project_id=j.project_id AND rt.output_artifact_id=j.sealed_output_artifact_id
 JOIN anvil.benchmark_cell_attempts ca ON ca.project_id=rt.project_id AND ca.id=rt.attempt_id
 JOIN anvil.benchmark_cells cell ON cell.project_id=ca.project_id AND cell.id=ca.cell_id
 JOIN anvil.benchmark_version_tasks task ON task.project_id=cell.project_id AND task.benchmark_revision_id=cell.benchmark_revision_id AND task.task_revision_id=cell.task_revision_id
 JOIN anvil.benchmark_qualifications q ON q.project_id=task.project_id AND q.id=task.qualification_id
 WHERE j.project_id=NEW.project_id AND j.id=NEW.job_id AND rt.attempt_id=NEW.attempt_id
 AND j.state='queued' AND j.binding_id=q.evaluator_binding_id
 AND j.created_by=nullif(current_setting('anvil.user',true),'')::uuid)
 THEN RAISE EXCEPTION 'native evaluator custody requires its exact captured job'; END IF;RETURN NEW;END $$;
CREATE TRIGGER exact_capture BEFORE INSERT ON anvil.benchmark_native_evaluator_custody FOR EACH ROW EXECUTE FUNCTION anvil.guard_native_evaluator_custody();

CREATE FUNCTION anvil.finish_native_benchmark_capture(p uuid,a uuid,f uuid,o text,h text) RETURNS uuid
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
 DECLARE j anvil.benchmark_evaluator_jobs; caller text; BEGIN
 caller:=coalesce(nullif(current_setting('role',true),'none'),session_user::text);
 IF caller<>'anvil_benchmark_evaluator' OR p IS DISTINCT FROM nullif(current_setting('anvil.project',true),'')::uuid THEN RETURN NULL;END IF;
 PERFORM 1 FROM anvil.projects WHERE id=p FOR UPDATE;
 IF NOT anvil.native_evaluator_capture_valid(p,a,f,o,h) THEN RETURN NULL;END IF;
 SELECT job.* INTO j FROM anvil.benchmark_evaluator_jobs job JOIN anvil.benchmark_native_evaluator_custody n ON n.project_id=job.project_id AND n.job_id=job.id
 WHERE n.project_id=p AND n.attempt_id=a AND n.fence=f AND n.output_sha256=o AND n.report_sha256=h FOR UPDATE OF job;
 IF j.id IS NULL OR NOT EXISTS(SELECT 1 FROM anvil.benchmark_private_assignments duty
 JOIN anvil.memberships m ON m.project_id=duty.project_id AND m.user_id=duty.user_id AND m.active
 JOIN anvil.users u ON u.id=m.user_id AND u.active
 WHERE duty.project_id=p AND duty.user_id=j.created_by AND duty.scope='evaluation_review' AND duty.artifact_id IS NULL AND duty.expires_at>now()
 AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_private_revocations r WHERE r.assignment_id=duty.id)) THEN RETURN NULL;END IF;
 IF j.state='finished' THEN RETURN j.id;END IF;
 IF j.state<>'queued' THEN RETURN NULL;END IF;
 UPDATE anvil.benchmark_evaluator_jobs SET state='leased',lease_token=gen_random_uuid(),lease_until=now()+interval '120 seconds' WHERE id=j.id;
 SELECT * INTO j FROM anvil.benchmark_evaluator_jobs WHERE id=j.id;
 PERFORM set_config('anvil.benchmark_job',j.id::text,true),set_config('anvil.benchmark_fence',j.lease_token::text,true);
 IF j.state<>'leased' OR j.lease_until<=now() OR NOT anvil.benchmark_job_scope(p,j.id) THEN RAISE EXCEPTION 'native evaluator lease no longer current'; END IF;
 UPDATE anvil.benchmark_evaluator_jobs SET state='finished' WHERE id=j.id;
 RETURN j.id;
 END $$;
REVOKE ALL ON FUNCTION anvil.finish_native_benchmark_capture(uuid,uuid,uuid,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.finish_native_benchmark_capture(uuid,uuid,uuid,text,text) TO anvil_benchmark_evaluator;
INSERT INTO anvil.schema_versions(version) VALUES(53);
