ALTER TABLE anvil.artifacts DROP CONSTRAINT artifacts_classification_check;
ALTER TABLE anvil.artifacts ADD CONSTRAINT artifacts_classification_check CHECK(classification IN
 ('actor','hidden_reference','internal','approved_delivery','benchmark_raw','benchmark_eval','benchmark_judge','benchmark_trace','benchmark_output','benchmark_sealed'));
ALTER TABLE anvil.artifacts ADD CONSTRAINT benchmark_sealed_namespace CHECK(classification<>'benchmark_sealed' OR
 (object_key='benchmark-vault/'||project_id::text||'/benchmark_sealed/'||sha256::text AND scan_status='quarantined' AND sha256::text~'^[a-f0-9]{64}$'));
CREATE POLICY sealed_private ON anvil.artifacts AS RESTRICTIVE USING(classification<>'benchmark_sealed' OR anvil.benchmark_private_access(project_id,classification,id))
 WITH CHECK(classification<>'benchmark_sealed' OR anvil.benchmark_private_access(project_id,classification,id));
CREATE FUNCTION anvil.guard_sealed_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF OLD.classification='benchmark_sealed' OR (TG_OP='UPDATE' AND NEW.classification='benchmark_sealed') THEN RAISE EXCEPTION 'immutable sealed artifact'; END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;RETURN NEW;END $$;
CREATE TRIGGER sealed_immutable BEFORE UPDATE OR DELETE ON anvil.artifacts FOR EACH ROW EXECUTE FUNCTION anvil.guard_sealed_immutable();
CREATE OR REPLACE FUNCTION anvil.guard_benchmark_sealed_output() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM anvil.artifacts a WHERE a.project_id=NEW.project_id AND a.id=NEW.sealed_output_artifact_id AND a.classification IN ('benchmark_output','benchmark_sealed'))
 THEN RAISE EXCEPTION 'evaluator requires sealed output';END IF;RETURN NEW;END $$;
CREATE OR REPLACE FUNCTION anvil.guard_benchmark_input() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM anvil.artifacts a WHERE a.project_id=NEW.project_id AND a.id=NEW.artifact_id AND a.sha256=NEW.artifact_sha256 AND a.classification IN ('benchmark_eval','benchmark_judge','benchmark_trace','benchmark_output','benchmark_sealed'))
 THEN RAISE EXCEPTION 'invalid evaluator input binding';END IF;RETURN NEW;END $$;
CREATE OR REPLACE FUNCTION anvil.guard_evaluation_request() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM anvil.benchmark_evaluator_jobs j JOIN anvil.benchmark_evaluator_registrations r ON r.project_id=j.project_id AND r.binding_id=j.binding_id
 JOIN anvil.artifacts a ON a.project_id=j.project_id AND a.id=j.sealed_output_artifact_id
 WHERE j.project_id=NEW.project_id AND j.id=NEW.job_id AND r.id=NEW.registry_id
 AND j.state='queued' AND j.created_by=nullif(current_setting('anvil.user',true),'')::uuid
 AND a.classification='benchmark_sealed' AND a.sha256=NEW.output_sha256 AND anvil.evaluation_review_live(j.project_id,r.id,j.created_by))
 THEN RAISE EXCEPTION 'invalid evaluator request'; END IF;RETURN NEW;
END $$;
CREATE OR REPLACE FUNCTION anvil.finish_benchmark_evaluation(p uuid,j uuid,f uuid,s text,code text,a uuid,h text,n bigint) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
 DECLARE e anvil.benchmark_evaluator_jobs; stored uuid; BEGIN
 PERFORM 1 FROM anvil.projects WHERE id=p FOR KEY SHARE;
 SELECT * INTO e FROM anvil.benchmark_evaluator_jobs WHERE project_id=p AND id=j FOR UPDATE;
 IF f IS NULL OR s IS NULL OR code IS NULL OR a IS NULL OR h IS NULL OR n IS NULL OR e.id IS NULL OR e.state<>'leased' OR e.lease_token<>f OR e.lease_until<=now() OR NOT anvil.benchmark_job_scope(p,j)
 OR s NOT IN ('evaluated','blocked','review_required') OR code!~'^[a-z][a-z0-9_]{0,79}$' OR h!~'^[a-f0-9]{64}$' OR n NOT BETWEEN 1 AND 2000000 THEN RETURN false; END IF;
 INSERT INTO anvil.artifacts(id,project_id,object_key,sha256,byte_size,mime_type,classification,scan_status,origin,uploaded_by)
 VALUES(a,p,'benchmark-vault/'||p::text||'/benchmark_trace/'||h,h,n,'application/json','benchmark_trace','quarantined','restricted_source',e.created_by) ON CONFLICT(project_id,classification,sha256) WHERE classification IN ('benchmark_raw','benchmark_eval','benchmark_judge','benchmark_trace') DO NOTHING RETURNING id INTO stored;
 IF stored IS NULL THEN SELECT id INTO stored FROM anvil.artifacts WHERE project_id=p AND classification='benchmark_trace' AND sha256=h AND byte_size=n; END IF;
 IF stored IS NULL THEN RAISE EXCEPTION 'result artifact conflict';END IF;
 INSERT INTO anvil.benchmark_evaluation_results(project_id,job_id,status,safe_code,report_artifact_id,report_sha256) VALUES(p,j,s,code,stored,h);
 UPDATE anvil.benchmark_evaluator_jobs SET state=CASE WHEN s='evaluated' THEN 'finished' ELSE 'failed' END WHERE id=j;
 RETURN true;
END $$;
INSERT INTO anvil.schema_versions(version) VALUES(48);
