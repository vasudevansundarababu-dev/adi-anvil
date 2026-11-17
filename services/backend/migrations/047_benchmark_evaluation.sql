CREATE TABLE anvil.benchmark_evaluator_registrations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),binding_id uuid NOT NULL,
 policy_artifact_id uuid NOT NULL,evidence_artifact_id uuid NOT NULL,
 policy_sha256 text NOT NULL CHECK(policy_sha256~'^[a-f0-9]{64}$'),
 implementation_sha256 text NOT NULL CHECK(implementation_sha256~'^[a-f0-9]{64}$'),
 calibration_sha256 text NOT NULL CHECK(calibration_sha256~'^[a-f0-9]{64}$'),
 reviewed_by uuid NOT NULL REFERENCES anvil.users(id),expires_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(project_id,id),CHECK(expires_at>created_at),
 FOREIGN KEY(project_id,binding_id) REFERENCES anvil.benchmark_evaluator_bindings(project_id,id),
 FOREIGN KEY(project_id,policy_artifact_id) REFERENCES anvil.artifacts(project_id,id),
 FOREIGN KEY(project_id,evidence_artifact_id) REFERENCES anvil.artifacts(project_id,id)
);
CREATE TABLE anvil.benchmark_evaluation_requests(
 project_id uuid NOT NULL,job_id uuid NOT NULL,registry_id uuid NOT NULL,task_id text NOT NULL CHECK(task_id~'^FX[A-Za-z0-9_-]{1,60}$'),
 sealed_sha256 text NOT NULL CHECK(sealed_sha256~'^[a-f0-9]{64}$'),
 output_sha256 text NOT NULL CHECK(output_sha256~'^[a-f0-9]{64}$'),
 idempotency_key text NOT NULL CHECK(length(idempotency_key) BETWEEN 1 AND 200),
 subject_sha256 text NOT NULL CHECK(subject_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(project_id,job_id),UNIQUE(project_id,idempotency_key),
 FOREIGN KEY(project_id,job_id) REFERENCES anvil.benchmark_evaluator_jobs(project_id,id),
 FOREIGN KEY(project_id,registry_id) REFERENCES anvil.benchmark_evaluator_registrations(project_id,id)
);
CREATE TABLE anvil.benchmark_evaluation_results(
 project_id uuid NOT NULL,job_id uuid NOT NULL,status text NOT NULL CHECK(status IN ('evaluated','blocked','review_required','cancelled')),
 safe_code text NOT NULL CHECK(safe_code~'^[a-z][a-z0-9_]{0,79}$'),
 report_artifact_id uuid,report_sha256 text CHECK(report_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(project_id,job_id),
 FOREIGN KEY(project_id,job_id) REFERENCES anvil.benchmark_evaluation_requests(project_id,job_id),
 FOREIGN KEY(project_id,report_artifact_id) REFERENCES anvil.artifacts(project_id,id),
 CHECK((report_artifact_id IS NULL)=(report_sha256 IS NULL)),CHECK(status<>'evaluated' OR report_artifact_id IS NOT NULL)
);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['benchmark_evaluator_registrations','benchmark_evaluation_requests','benchmark_evaluation_results'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY project_scope ON anvil.%I USING(CASE WHEN current_user=''anvil_benchmark_evaluator'' THEN false ELSE anvil.in_scope(project_id) END)',t);
 EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 EXECUTE format('GRANT SELECT ON anvil.%I TO anvil_app',t);
 END LOOP;
END $$;
GRANT INSERT ON anvil.benchmark_evaluator_registrations,anvil.benchmark_evaluation_requests TO anvil_app;
CREATE POLICY registry_admin ON anvil.benchmark_evaluator_registrations AS RESTRICTIVE FOR INSERT WITH CHECK(
 reviewed_by=nullif(current_setting('anvil.user',true),'')::uuid AND anvil.benchmark_is_admin(project_id,reviewed_by));
CREATE FUNCTION anvil.evaluation_review_live(p uuid,r uuid,u uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
 SELECT EXISTS(SELECT 1 FROM anvil.benchmark_evaluator_registrations g
 JOIN anvil.benchmark_evaluator_bindings b ON b.id=g.binding_id AND b.project_id=g.project_id
 JOIN anvil.memberships m ON m.project_id=g.project_id AND m.user_id=g.reviewed_by AND m.active AND m.role='admin'
 JOIN anvil.users v ON v.id=m.user_id AND v.active
 JOIN anvil.artifacts a ON a.project_id=g.project_id AND a.id=g.policy_artifact_id AND a.classification='benchmark_eval' AND a.sha256=g.policy_sha256
 WHERE g.project_id=p AND g.id=r AND g.expires_at>now()
 AND b.implementation_sha256=g.implementation_sha256 AND b.policy_sha256=g.policy_sha256
 AND EXISTS(SELECT 1 FROM anvil.memberships x JOIN anvil.users y ON y.id=x.user_id AND y.active WHERE x.project_id=p AND x.user_id=u AND x.active)
 AND EXISTS(SELECT 1 FROM anvil.benchmark_private_assignments x WHERE x.project_id=p AND x.user_id=u AND x.scope='evaluation_review'
 AND x.artifact_id IS NULL AND x.expires_at>now() AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_private_revocations y WHERE y.project_id=p AND y.assignment_id=x.id))
 AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_review_revocations x JOIN anvil.benchmark_source_reviews y ON y.project_id=x.project_id AND y.id=x.review_id WHERE x.project_id=p AND y.evaluator_binding_id=b.id AND x.target='evaluator')) $$;
REVOKE ALL ON FUNCTION anvil.evaluation_review_live(uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.evaluation_review_live(uuid,uuid,uuid) TO anvil_app,anvil_benchmark_evaluator;
CREATE FUNCTION anvil.guard_evaluator_registration() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM anvil.artifacts a JOIN anvil.artifacts e ON e.project_id=a.project_id
 WHERE a.project_id=NEW.project_id AND a.id=NEW.policy_artifact_id AND a.classification='benchmark_eval' AND a.sha256=NEW.policy_sha256
 AND e.id=NEW.evidence_artifact_id AND e.classification='benchmark_eval')
 THEN RAISE EXCEPTION 'invalid evaluator review binding'; END IF; RETURN NEW;
END $$;
CREATE TRIGGER registration_binding BEFORE INSERT ON anvil.benchmark_evaluator_registrations FOR EACH ROW EXECUTE FUNCTION anvil.guard_evaluator_registration();
CREATE FUNCTION anvil.guard_evaluation_request() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM anvil.benchmark_evaluator_jobs j JOIN anvil.benchmark_evaluator_registrations r ON r.project_id=j.project_id AND r.binding_id=j.binding_id
 JOIN anvil.artifacts a ON a.project_id=j.project_id AND a.id=j.sealed_output_artifact_id
 WHERE j.project_id=NEW.project_id AND j.id=NEW.job_id AND r.id=NEW.registry_id
 AND j.state='queued' AND j.created_by=nullif(current_setting('anvil.user',true),'')::uuid
 AND a.classification='benchmark_output' AND a.sha256=NEW.output_sha256 AND anvil.evaluation_review_live(j.project_id,r.id,j.created_by))
 THEN RAISE EXCEPTION 'invalid evaluator request'; END IF;RETURN NEW;
END $$;
CREATE TRIGGER request_binding BEFORE INSERT ON anvil.benchmark_evaluation_requests FOR EACH ROW EXECUTE FUNCTION anvil.guard_evaluation_request();
CREATE OR REPLACE FUNCTION anvil.benchmark_job_scope(p uuid,j uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
 SELECT p=nullif(current_setting('anvil.project',true),'')::uuid
 AND j=nullif(current_setting('anvil.benchmark_job',true),'')::uuid AND EXISTS(
 SELECT 1 FROM anvil.benchmark_evaluator_jobs e JOIN anvil.memberships m ON m.project_id=e.project_id AND m.user_id=e.created_by
 JOIN anvil.users u ON u.id=m.user_id WHERE e.project_id=p AND e.id=j AND e.state='leased'
 AND e.lease_token=nullif(current_setting('anvil.benchmark_fence',true),'')::uuid AND e.lease_until>now() AND m.active AND u.active
 AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_evaluation_requests q WHERE q.project_id=e.project_id AND q.job_id=e.id AND NOT anvil.evaluation_review_live(q.project_id,q.registry_id,e.created_by))) $$;
CREATE POLICY evaluator_request ON anvil.benchmark_evaluation_requests USING(current_user='anvil_benchmark_evaluator' AND anvil.benchmark_job_scope(project_id,job_id));
CREATE POLICY evaluator_registry ON anvil.benchmark_evaluator_registrations USING(current_user='anvil_benchmark_evaluator' AND EXISTS(
 SELECT 1 FROM anvil.benchmark_evaluation_requests q WHERE q.project_id=benchmark_evaluator_registrations.project_id AND q.registry_id=benchmark_evaluator_registrations.id AND anvil.benchmark_job_scope(q.project_id,q.job_id)));
GRANT SELECT ON anvil.benchmark_evaluation_requests,anvil.benchmark_evaluator_registrations TO anvil_benchmark_evaluator;
CREATE FUNCTION anvil.claim_benchmark_evaluation(p uuid,j uuid) RETURNS SETOF anvil.benchmark_evaluator_jobs LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$ BEGIN
 -- Project precedes job; no artifacts, providers or Docker under these locks.
 PERFORM 1 FROM anvil.projects WHERE id=p FOR KEY SHARE;
 RETURN QUERY UPDATE anvil.benchmark_evaluator_jobs e SET state='leased',lease_token=gen_random_uuid(),lease_until=now()+interval '120 seconds'
 WHERE e.project_id=p AND e.id=j AND e.state='queued' AND EXISTS(SELECT 1 FROM anvil.benchmark_evaluation_requests q
 WHERE q.project_id=p AND q.job_id=j AND anvil.evaluation_review_live(p,q.registry_id,e.created_by)) RETURNING e.*;
END $$;
REVOKE ALL ON FUNCTION anvil.claim_benchmark_evaluation(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.claim_benchmark_evaluation(uuid,uuid) TO anvil_benchmark_evaluator;
CREATE FUNCTION anvil.finish_benchmark_evaluation(p uuid,j uuid,f uuid,s text,code text,a uuid,h text,n bigint) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
 DECLARE e anvil.benchmark_evaluator_jobs; BEGIN
 PERFORM 1 FROM anvil.projects WHERE id=p FOR KEY SHARE;
 SELECT * INTO e FROM anvil.benchmark_evaluator_jobs WHERE project_id=p AND id=j FOR UPDATE;
 IF e.id IS NULL OR e.state<>'leased' OR e.lease_token<>f OR e.lease_until<=now() OR NOT anvil.benchmark_job_scope(p,j)
 OR s NOT IN ('evaluated','blocked','review_required') OR code!~'^[a-z][a-z0-9_]{0,79}$' OR h!~'^[a-f0-9]{64}$' OR n NOT BETWEEN 1 AND 2000000 THEN RETURN false; END IF;
 INSERT INTO anvil.artifacts(id,project_id,object_key,sha256,byte_size,mime_type,classification,scan_status,origin,uploaded_by)
 VALUES(a,p,'benchmark-vault/'||p::text||'/benchmark_trace/'||h,h,n,'application/json','benchmark_trace','quarantined','restricted_source',e.created_by);
 INSERT INTO anvil.benchmark_evaluation_results(project_id,job_id,status,safe_code,report_artifact_id,report_sha256) VALUES(p,j,s,code,a,h);
 UPDATE anvil.benchmark_evaluator_jobs SET state=CASE WHEN s='evaluated' THEN 'finished' ELSE 'failed' END WHERE id=j;
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION anvil.finish_benchmark_evaluation(uuid,uuid,uuid,text,text,uuid,text,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.finish_benchmark_evaluation(uuid,uuid,uuid,text,text,uuid,text,bigint) TO anvil_benchmark_evaluator;
CREATE FUNCTION anvil.cancel_benchmark_evaluation(p uuid,j uuid) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$ BEGIN
 PERFORM 1 FROM anvil.projects WHERE id=p FOR UPDATE;
 IF NOT anvil.benchmark_is_admin(p,nullif(current_setting('anvil.user',true),'')::uuid) THEN RETURN false; END IF;
 PERFORM 1 FROM anvil.benchmark_evaluation_requests WHERE project_id=p AND job_id=j;
 IF NOT FOUND THEN RETURN false; END IF;
 UPDATE anvil.benchmark_evaluator_jobs SET state='failed' WHERE project_id=p AND id=j AND state IN ('queued','leased');
 IF NOT FOUND THEN RETURN false; END IF;
 INSERT INTO anvil.benchmark_evaluation_results(project_id,job_id,status,safe_code) VALUES(p,j,'cancelled','cancelled_no_retry');RETURN true;
END $$;
REVOKE ALL ON FUNCTION anvil.cancel_benchmark_evaluation(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.cancel_benchmark_evaluation(uuid,uuid) TO anvil_app;
INSERT INTO anvil.schema_versions(version) VALUES(47);
