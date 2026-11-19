-- Admission to a synthetic TEST, never production qualification or paid scoring.
-- Owner-only issuance is additionally confined to a disposable component DB.
-- The historical PUBLIC policy invokes membership tables as the caller. It is
-- not safe to rely on OR short-circuiting with the dedicated runtime policy.
-- Keep the original app/worker policy for its intended identities; the grader
-- uses its existing narrow SECURITY DEFINER runtime_scope policy instead.
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['custom_python_evaluators','custom_python_jobs','custom_python_revocations',
  'project_binding_versions','project_binding_qualifications','project_binding_qualification_revocations',
  'workspace_execution_groups','praxis_resolved_tasks'] LOOP
  IF EXISTS(SELECT 1 FROM pg_catalog.pg_policies WHERE schemaname='anvil' AND tablename=t AND policyname='project_scope') THEN
   EXECUTE format('ALTER POLICY project_scope ON anvil.%I TO anvil_app,anvil_worker',t);
  END IF;
 END LOOP;
END $$;
CREATE TABLE banking_private.python_control_admissions(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,job_id uuid NOT NULL UNIQUE,
 trial_id uuid NOT NULL,generation integer NOT NULL CHECK(generation>=0),
 binding_id uuid NOT NULL,evaluator_id uuid NOT NULL,criterion text NOT NULL,
 fixture_nonce text NOT NULL CHECK(fixture_nonce~'^[a-f0-9]{64}$'),
 context jsonb NOT NULL CHECK(octet_length(context::text)<=16384),
 context_sha256 text NOT NULL CHECK(context_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),expires_at timestamptz NOT NULL,
 CHECK(expires_at>created_at AND expires_at<=created_at+interval '30 minutes'),
 FOREIGN KEY(project_id,trial_id) REFERENCES banking.trials(project_id,id),
 FOREIGN KEY(project_id,binding_id) REFERENCES anvil.project_binding_versions(project_id,id),
 FOREIGN KEY(project_id,evaluator_id) REFERENCES anvil.custom_python_evaluators(project_id,id),
 UNIQUE(project_id,id));
CREATE TABLE banking_private.python_control_revocations(
 admission_id uuid PRIMARY KEY REFERENCES banking_private.python_control_admissions(id),
 project_id uuid NOT NULL,reason text NOT NULL CHECK(length(reason) BETWEEN 10 AND 1000),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,admission_id) REFERENCES banking_private.python_control_admissions(project_id,id));
CREATE TABLE banking_private.python_control_intents(
 admission_id uuid PRIMARY KEY REFERENCES banking_private.python_control_admissions(id),
 project_id uuid NOT NULL,job_id uuid NOT NULL UNIQUE REFERENCES banking_private.python_grading_jobs(id),
 request_sha256 text NOT NULL CHECK(request_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,admission_id) REFERENCES banking_private.python_control_admissions(project_id,id));
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['python_control_admissions','python_control_revocations','python_control_intents'] LOOP
  EXECUTE format('ALTER TABLE banking_private.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE banking_private.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY grader_only ON banking_private.%I FOR SELECT TO anvil_golden_grader USING(banking.runtime_scope(project_id))',t);
  EXECUTE format('GRANT SELECT ON banking_private.%I TO anvil_golden_grader',t);
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON banking_private.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
END $$;
CREATE TRIGGER authority_revoke BEFORE INSERT ON banking_private.python_control_revocations
 FOR EACH ROW EXECUTE FUNCTION anvil.private_python_authority_mutation();

CREATE FUNCTION banking_private.python_control_fixture(p uuid,n text) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE allowed boolean;
BEGIN
 IF pg_catalog.current_database() !~ '^anvil_golden_kyc_component_[a-z0-9_]+$'
  OR pg_catalog.to_regclass('anvil.component_control_fixture') IS NULL THEN RETURN false;END IF;
 -- Fixed SQL only; the relation is intentionally absent from real application DBs.
 EXECUTE 'SELECT count(*)=1 AND bool_and(project_id=$1 AND fixture_nonce=$2
  AND fixture_label=''synthetic-component-control-not-performance''
  AND created_at>clock_timestamp()-interval ''30 minutes'' AND created_at<=clock_timestamp())
  FROM anvil.component_control_fixture' INTO allowed USING p,n;
 RETURN COALESCE(allowed,false);
END $$;
REVOKE ALL ON FUNCTION banking_private.python_control_fixture(uuid,text) FROM PUBLIC;

CREATE FUNCTION banking_private.python_control_issuance() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$ BEGIN
 IF NOT banking_private.python_control_fixture(NEW.project_id,NEW.fixture_nonce)
  OR NEW.created_at>pg_catalog.clock_timestamp() OR NEW.created_at<pg_catalog.clock_timestamp()-interval '5 seconds'
  OR NEW.context->>'purpose' IS DISTINCT FROM 'synthetic_private_scoring_control'
 THEN RAISE EXCEPTION 'fresh isolated technical fixture required';END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION banking_private.python_control_issuance() FROM PUBLIC;
CREATE TRIGGER isolated_issuance BEFORE INSERT ON banking_private.python_control_admissions
 FOR EACH ROW EXECUTE FUNCTION banking_private.python_control_issuance();

CREATE FUNCTION banking_private.python_control_allowed(a uuid,j uuid,p uuid,t uuid,g integer,b uuid,e uuid,k text,r jsonb)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE principal record;admission record;parents integer;
BEGIN
 SELECT x.* INTO principal FROM pg_catalog.pg_roles x WHERE x.rolname=session_user;
 SELECT count(*) INTO parents FROM pg_catalog.pg_auth_members m WHERE m.member=principal.oid;
 IF principal.oid IS NULL OR NOT principal.rolcanlogin OR principal.rolsuper OR principal.rolbypassrls
  OR principal.rolcreatedb OR principal.rolcreaterole OR principal.rolreplication OR parents<>1
  OR NOT pg_catalog.pg_has_role(session_user,'anvil_golden_grader','MEMBER')
  OR pg_catalog.pg_has_role(session_user,'anvil_app','MEMBER')
  OR pg_catalog.pg_has_role(session_user,'anvil_worker','MEMBER')
  OR pg_catalog.pg_has_role(session_user,'anvil_golden_scheduler','MEMBER')
  OR pg_catalog.current_setting('transaction_isolation')<>'read committed'
  OR p::text IS DISTINCT FROM pg_catalog.current_setting('anvil.project',true)
 THEN RETURN false;END IF;
 IF NOT anvil.lock_private_python_award(b,e) THEN RETURN false;END IF;
 SELECT * INTO admission FROM banking_private.python_control_admissions x WHERE x.id=a AND x.project_id=p;
 IF NOT FOUND OR NOT banking_private.python_control_fixture(p,admission.fixture_nonce)
  OR admission.expires_at<=pg_catalog.clock_timestamp()
  OR (admission.job_id,admission.trial_id,admission.generation,admission.binding_id,admission.evaluator_id,admission.criterion)
    IS DISTINCT FROM (j,t,g,b,e,k)
  OR EXISTS(SELECT 1 FROM banking_private.python_control_revocations x WHERE x.admission_id=a)
  OR r->>'schema_version' IS DISTINCT FROM 'anvil.private-python-control-grade.v1'
  OR r->'technical_control' IS DISTINCT FROM jsonb_build_object('id',a::text,'sha256',admission.context_sha256,
     'purpose','synthetic_private_scoring_control')
  OR r->>'source_sha256' IS DISTINCT FROM admission.context->>'grader_source_sha256'
  OR r->>'image_id' IS DISTINCT FROM admission.context->>'executor_image_id'
  OR r->>'binding_sha256' IS DISTINCT FROM admission.context->>'binding_sha256'
  OR r->>'code_sha256' IS DISTINCT FROM admission.context->>'code_sha256'
  OR r->>'target' IS DISTINCT FROM admission.context->>'target'
  OR r->>'state_sha256' IS DISTINCT FROM admission.context->>'state_sha256'
  OR r->'actual' IS DISTINCT FROM admission.context->'private_input'->'actual'
  OR r->'expected' IS DISTINCT FROM admission.context->'private_input'->'expected'
  OR r->>'code' IS DISTINCT FROM (SELECT x.code FROM anvil.custom_python_evaluators x WHERE x.id=e AND x.project_id=p)
  OR NOT anvil.private_python_authors_active(b,e)
 THEN RETURN false;END IF;
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION banking_private.python_control_allowed(uuid,uuid,uuid,uuid,integer,uuid,uuid,text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION banking_private.python_control_allowed(uuid,uuid,uuid,uuid,integer,uuid,uuid,text,jsonb) TO anvil_golden_grader;

CREATE FUNCTION banking_private.python_control_job_fence() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE technical boolean;a uuid;
BEGIN
 technical=NEW.request->>'schema_version'='anvil.private-python-control-grade.v1';
 IF technical THEN
  a=(NEW.request->'technical_control'->>'id')::uuid;
  IF NOT banking_private.python_control_allowed(a,NEW.id,NEW.project_id,NEW.trial_id,NEW.generation,
       NEW.binding_id,NEW.evaluator_id,NEW.criterion,NEW.request)
   AND NOT COALESCE((TG_OP='UPDATE' AND OLD.state='claimed' AND NEW.state='error' AND NEW.result->>'status'='error'),false)
  THEN RAISE EXCEPTION 'technical scoring admission denied';END IF;
  IF TG_OP='INSERT' THEN
   INSERT INTO banking_private.python_control_intents(admission_id,project_id,job_id,request_sha256)
    VALUES(a,NEW.project_id,NEW.id,NEW.request_sha256);
  ELSIF NEW.result IS NOT NULL AND (NEW.result->>'schema_version' IS DISTINCT FROM 'anvil.private-python-control-grade.v1'
    OR NEW.result->'technical_control' IS DISTINCT FROM NEW.request->'technical_control')
  THEN RAISE EXCEPTION 'technical result purpose mismatch';END IF;
 ELSIF NEW.request ? 'technical_control' OR NEW.result ? 'technical_control'
   OR NEW.result->>'schema_version'='anvil.private-python-control-grade.v1'
 THEN RAISE EXCEPTION 'production cannot consume technical scoring';END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION banking_private.python_control_job_fence() FROM PUBLIC;
CREATE TRIGGER technical_purpose AFTER INSERT ON banking_private.python_grading_jobs
 FOR EACH ROW EXECUTE FUNCTION banking_private.python_control_job_fence();
CREATE TRIGGER technical_result BEFORE UPDATE ON banking_private.python_grading_jobs
 FOR EACH ROW EXECUTE FUNCTION banking_private.python_control_job_fence();
INSERT INTO anvil.schema_versions(version) VALUES(133);
