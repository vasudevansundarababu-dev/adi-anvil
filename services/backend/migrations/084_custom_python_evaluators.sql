CREATE TABLE anvil.custom_python_evaluators(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 120),code text NOT NULL CHECK(octet_length(code) BETWEEN 1 AND 16384),
 code_sha256 text NOT NULL CHECK(code_sha256~'^[a-f0-9]{64}$'),created_by uuid NOT NULL REFERENCES anvil.users(id),
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(project_id,id));
CREATE TABLE anvil.custom_python_jobs(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),evaluator_id uuid,
 request jsonb NOT NULL CHECK(octet_length(request::text)<=65536),request_sha256 text NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 state text NOT NULL DEFAULT 'queued' CHECK(state IN('queued','claimed','completed','error')),
 claim_token uuid,result jsonb,result_sha256 text,finished_at timestamptz,
 FOREIGN KEY(project_id,evaluator_id) REFERENCES anvil.custom_python_evaluators(project_id,id),UNIQUE(project_id,id));
CREATE TABLE anvil.custom_python_revocations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,evaluator_id uuid NOT NULL,created_by uuid NOT NULL REFERENCES anvil.users(id),
 created_at timestamptz NOT NULL DEFAULT now(),FOREIGN KEY(project_id,evaluator_id) REFERENCES anvil.custom_python_evaluators(project_id,id),UNIQUE(evaluator_id));
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['custom_python_evaluators','custom_python_jobs','custom_python_revocations'] LOOP
  EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY scoped_read ON anvil.%I FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id))',t);
  EXECUTE format('CREATE POLICY scoped_insert ON anvil.%I FOR INSERT TO anvil_app WITH CHECK(anvil.golden_engineer(project_id) AND created_by=nullif(current_setting(''anvil.user'',true),'''')::uuid)',t);
  EXECUTE format('GRANT SELECT,INSERT ON anvil.%I TO anvil_app',t);
 END LOOP;
END $$;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.custom_python_evaluators FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.custom_python_revocations FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE FUNCTION anvil.custom_python_immutable_input() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='DELETE' OR (NEW.id,NEW.project_id,NEW.evaluator_id,NEW.request,NEW.request_sha256,NEW.created_by,NEW.created_at)
 IS DISTINCT FROM (OLD.id,OLD.project_id,OLD.evaluator_id,OLD.request,OLD.request_sha256,OLD.created_by,OLD.created_at)
 THEN RAISE EXCEPTION 'immutable custom evaluator input';END IF;RETURN NEW;END $$;
CREATE TRIGGER immutable_input BEFORE UPDATE OR DELETE ON anvil.custom_python_jobs FOR EACH ROW EXECUTE FUNCTION anvil.custom_python_immutable_input();
CREATE FUNCTION anvil.claim_custom_python_job() RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
DECLARE item anvil.custom_python_jobs%ROWTYPE;token uuid;BEGIN
 SELECT j.* INTO item FROM anvil.custom_python_jobs j
 WHERE j.project_id=nullif(current_setting('anvil.project',true),'')::uuid AND j.state='queued'
 AND EXISTS(SELECT 1 FROM anvil.users u JOIN anvil.memberships m ON m.user_id=u.id WHERE u.id=j.created_by AND u.active AND m.project_id=j.project_id AND m.active AND m.role IN('admin','rl-engineer'))
 AND NOT EXISTS(SELECT 1 FROM anvil.custom_python_revocations r WHERE r.evaluator_id=j.evaluator_id)
 ORDER BY j.created_at,j.id FOR UPDATE SKIP LOCKED LIMIT 1;
 IF NOT FOUND THEN RETURN NULL;END IF;
 token=gen_random_uuid();UPDATE anvil.custom_python_jobs SET state='claimed',claim_token=token WHERE id=item.id;
 RETURN jsonb_build_object('id',item.id,'project_id',item.project_id,'request',item.request,'request_sha256',item.request_sha256,'claim_token',token);
END $$;
CREATE FUNCTION anvil.finish_custom_python_job(p_id uuid,p_token uuid,p_result jsonb,p_hash text) RETURNS boolean
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$ BEGIN
 UPDATE anvil.custom_python_jobs SET result=p_result,result_sha256=p_hash,state=CASE WHEN p_result ? 'execution_error' THEN 'error' ELSE 'completed' END,finished_at=now()
 WHERE project_id=nullif(current_setting('anvil.project',true),'')::uuid AND id=p_id AND claim_token=p_token AND state='claimed';
 RETURN FOUND;END $$;
REVOKE ALL ON FUNCTION anvil.claim_custom_python_job(),anvil.finish_custom_python_job(uuid,uuid,jsonb,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.claim_custom_python_job(),anvil.finish_custom_python_job(uuid,uuid,jsonb,text) TO anvil_golden_scheduler;
