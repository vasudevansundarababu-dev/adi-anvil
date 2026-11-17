-- Private native-ordinal authority fences and separate semantic judge custody.
-- This migration seeds no evaluator, human calibration, key or spending grant.
CREATE FUNCTION anvil.lock_native_ordinal_award(p_binding uuid,p_evaluator uuid) RETURNS boolean
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE project uuid;b anvil.project_binding_versions;e anvil.evaluator_configurations;authors uuid[];BEGIN
 project=nullif(current_setting('anvil.project',true),'')::uuid;
 IF project IS NULL THEN RETURN false;END IF;
 PERFORM pg_advisory_xact_lock_shared(hashtextextended('private-python-authority:'||project::text,0));
 SELECT * INTO b FROM anvil.project_binding_versions v WHERE v.id=p_binding AND v.project_id=project
 AND v.id=(SELECT latest.id FROM anvil.project_binding_versions latest WHERE latest.project_id=project AND latest.task_group_id=v.task_group_id ORDER BY latest.version DESC,latest.created_at DESC,latest.id DESC LIMIT 1);
 IF b.id IS NULL THEN RETURN false;END IF;
 SELECT * INTO e FROM anvil.evaluator_configurations v WHERE v.project_id=project AND v.id=p_evaluator FOR SHARE;
 IF e.id IS NULL THEN RETURN false;END IF;
 authors=ARRAY[b.created_by,e.created_by];
 PERFORM 1 FROM anvil.users WHERE id=ANY(authors) ORDER BY id FOR SHARE;
 PERFORM 1 FROM anvil.memberships WHERE project_id=project AND user_id=ANY(authors) ORDER BY user_id FOR SHARE;
 RETURN NOT EXISTS(SELECT 1 FROM unnest(authors) person(id) WHERE NOT EXISTS(
  SELECT 1 FROM anvil.users u JOIN anvil.memberships m ON m.user_id=u.id AND m.project_id=project
  WHERE u.id=person.id AND u.active AND m.active AND m.role IN('admin','rl-engineer')));
END $$;
REVOKE ALL ON FUNCTION anvil.lock_native_ordinal_award(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.lock_native_ordinal_award(uuid,uuid) TO anvil_golden_grader;

-- Migration089's governed_change_lock already takes evaluator FOR UPDATE on
-- both validation receipt and revocation insertion. Its lock conflicts with
-- this helper's shared evaluator lock; no duplicate trigger or UPDATE grant.

-- Public sizing metadata contains no anchors, observations or private reasoning.
CREATE TABLE marketing_runtime.semantic_quotes(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,group_id uuid NOT NULL,plan_id uuid NOT NULL,
 batch_index integer NOT NULL CHECK(batch_index BETWEEN 0 AND 22),blueprint jsonb NOT NULL,
 blueprint_sha256 text NOT NULL CHECK(blueprint_sha256~'^[a-f0-9]{64}$'),
 model_binding_sha256 text NOT NULL CHECK(model_binding_sha256~'^[a-f0-9]{64}$'),
 pricing_sha256 text NOT NULL CHECK(pricing_sha256~'^[a-f0-9]{64}$'),
 bound_micro_usd bigint NOT NULL CHECK(bound_micro_usd>0),physical_calls integer NOT NULL CHECK(physical_calls=1),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,plan_id) REFERENCES marketing_runtime.paid_agent_bindings(project_id,plan_id),
 FOREIGN KEY(project_id,group_id) REFERENCES anvil.workspace_execution_groups(project_id,id),
 UNIQUE(project_id,id),UNIQUE(plan_id,batch_index));
ALTER TABLE marketing_runtime.semantic_quotes ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketing_runtime.semantic_quotes FORCE ROW LEVEL SECURITY;
CREATE POLICY scoped_read ON marketing_runtime.semantic_quotes FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id));
CREATE POLICY grader_read ON marketing_runtime.semantic_quotes FOR SELECT TO anvil_golden_grader USING(banking.runtime_scope(project_id));
CREATE POLICY draft_insert ON marketing_runtime.semantic_quotes FOR INSERT TO anvil_app WITH CHECK(anvil.golden_engineer(project_id));
GRANT SELECT,INSERT ON marketing_runtime.semantic_quotes TO anvil_app;
GRANT SELECT ON marketing_runtime.semantic_quotes TO anvil_golden_grader;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON marketing_runtime.semantic_quotes FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE FUNCTION marketing_runtime.guard_semantic_quote() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE p anvil.harbor_agent_plans;g anvil.workspace_execution_groups;BEGIN
 SELECT * INTO p FROM anvil.harbor_agent_plans WHERE project_id=NEW.project_id AND id=NEW.plan_id;
 SELECT * INTO g FROM anvil.workspace_execution_groups WHERE project_id=NEW.project_id AND id=NEW.group_id;
 IF p.id IS NULL OR g.id IS NULL OR p.state<>'draft' OR g.state<>'draft'
 OR p.created_by IS DISTINCT FROM nullif(current_setting('anvil.user',true),'')::uuid
 OR p.config->>'workspace_execution_group' IS DISTINCT FROM g.id::text OR p.config->>'marketing_paid' IS DISTINCT FROM 'true'
 OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(g.snapshot->'shared_call_quote'->'judge_reservations') q
 WHERE q = (to_jsonb(NEW)-ARRAY['id','project_id','group_id','created_at']))
 THEN RAISE EXCEPTION 'exact immutable upfront shared judge quote required';END IF;
 RETURN NEW;END $$;
CREATE TRIGGER exact_shared_quote BEFORE INSERT ON marketing_runtime.semantic_quotes FOR EACH ROW EXECUTE FUNCTION marketing_runtime.guard_semantic_quote();

-- No application, scheduler, candidate or general artifact reader receives raw
-- private-input/result SELECT. Only the exact leased API capability can read an
-- individual queued request through semantic_job_context below.
CREATE TABLE campaign_private.semantic_jobs(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,quote_id uuid NOT NULL UNIQUE,grading_job_id uuid NOT NULL,
 episode_id uuid NOT NULL,generation integer NOT NULL CHECK(generation>=0),capture_sha256 text NOT NULL CHECK(capture_sha256~'^[a-f0-9]{64}$'),
 batch jsonb NOT NULL CHECK(octet_length(batch::text)<=32768),
 projection jsonb NOT NULL CHECK(octet_length(projection::text)<=32768),
 input_projection_sha256 text NOT NULL CHECK(input_projection_sha256~'^[a-f0-9]{64}$'),
 state text NOT NULL DEFAULT 'queued' CHECK(state IN('queued','dispatching','completed','error','execution_unknown')),
 dispatch_token uuid,request_sha256 text,broker_claimed boolean NOT NULL DEFAULT false,
 result jsonb,result_sha256 text,actual_micro_usd bigint CHECK(actual_micro_usd>=0),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),finished_at timestamptz,
 FOREIGN KEY(project_id,quote_id) REFERENCES marketing_runtime.semantic_quotes(project_id,id),
 FOREIGN KEY(project_id,grading_job_id) REFERENCES marketing_runtime.grading_jobs(project_id,id),UNIQUE(project_id,id));
ALTER TABLE campaign_private.semantic_jobs ADD FOREIGN KEY(episode_id,generation) REFERENCES marketing_runtime.seals(episode_id,generation);
ALTER TABLE campaign_private.semantic_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaign_private.semantic_jobs FORCE ROW LEVEL SECURITY;
CREATE POLICY grader_read ON campaign_private.semantic_jobs FOR SELECT TO anvil_golden_grader USING(banking.runtime_scope(project_id));
GRANT SELECT ON campaign_private.semantic_jobs TO anvil_golden_grader;
CREATE FUNCTION campaign_private.semantic_custody() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='DELETE' OR (to_jsonb(NEW)-ARRAY['state','dispatch_token','request_sha256','broker_claimed','result','result_sha256','actual_micro_usd','finished_at'])
 IS DISTINCT FROM(to_jsonb(OLD)-ARRAY['state','dispatch_token','request_sha256','broker_claimed','result','result_sha256','actual_micro_usd','finished_at'])
 OR OLD.state IN('completed','error','execution_unknown') THEN RAISE EXCEPTION 'immutable private semantic intent or terminal result';END IF;
 IF OLD.state='queued' THEN
  IF NEW.state<>'dispatching' OR NEW.dispatch_token IS NULL OR NEW.request_sha256 IS NULL OR NEW.request_sha256!~'^[a-f0-9]{64}$' OR NEW.broker_claimed OR NEW.result IS NOT NULL THEN RAISE EXCEPTION 'once-only semantic dispatch intent required';END IF;
 ELSIF NEW.dispatch_token IS DISTINCT FROM OLD.dispatch_token OR NEW.request_sha256 IS DISTINCT FROM OLD.request_sha256 OR NEW.broker_claimed<OLD.broker_claimed THEN RAISE EXCEPTION 'immutable semantic dispatch capability';
 ELSIF NEW.state='dispatching' THEN
  IF OLD.broker_claimed OR NOT NEW.broker_claimed OR NEW.result IS NOT NULL THEN RAISE EXCEPTION 'once-only semantic broker claim required';END IF;
 ELSIF NEW.state NOT IN('completed','error','execution_unknown') OR NEW.result IS NULL OR NEW.result_sha256 IS NULL OR NEW.result_sha256!~'^[a-f0-9]{64}$' OR NEW.finished_at IS NULL THEN RAISE EXCEPTION 'terminal private semantic receipt required';END IF;
 RETURN NEW;END $$;
CREATE TRIGGER custody BEFORE UPDATE OR DELETE ON campaign_private.semantic_jobs FOR EACH ROW EXECUTE FUNCTION campaign_private.semantic_custody();

-- An ambiguous request is not silently converted into an immutable empty grade.
-- Only an independently retained operator disposition may close it unscored.
-- No public/API/scheduler/grader INSERT grant or score-replacement path exists.
CREATE TABLE campaign_private.semantic_dispositions(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,semantic_job_id uuid NOT NULL UNIQUE,
 disposition text NOT NULL CHECK(disposition='unscored_final'),reason text NOT NULL CHECK(length(reason) BETWEEN 10 AND 2000),
 evidence_sha256 text NOT NULL CHECK(evidence_sha256~'^[a-f0-9]{64}$'),
 operator_receipt_sha256 text NOT NULL CHECK(operator_receipt_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,semantic_job_id) REFERENCES campaign_private.semantic_jobs(project_id,id));
ALTER TABLE campaign_private.semantic_dispositions ENABLE ROW LEVEL SECURITY;
ALTER TABLE campaign_private.semantic_dispositions FORCE ROW LEVEL SECURITY;
CREATE POLICY grader_read ON campaign_private.semantic_dispositions FOR SELECT TO anvil_golden_grader USING(banking.runtime_scope(project_id));
GRANT SELECT ON campaign_private.semantic_dispositions TO anvil_golden_grader;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON campaign_private.semantic_dispositions FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE FUNCTION campaign_private.guard_semantic_disposition() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE s campaign_private.semantic_jobs;j anvil.jobs;BEGIN
 SELECT * INTO s FROM campaign_private.semantic_jobs WHERE id=NEW.semantic_job_id AND project_id=NEW.project_id FOR UPDATE;
 SELECT * INTO j FROM anvil.jobs WHERE id=s.id AND project_id=s.project_id AND kind='benchmark_campaign_judge' FOR UPDATE;
 IF s.id IS NULL OR j.id IS NULL OR NOT((j.lease_until IS NOT NULL AND j.lease_until<=clock_timestamp())
 OR(j.lease_until IS NULL AND j.status='queued' AND s.state='queued' AND NOT s.broker_claimed))
 OR NOT(s.state IN('queued','dispatching','execution_unknown') OR(s.state='completed' AND s.finished_at>j.lease_until))
 THEN RAISE EXCEPTION 'expired exact semantic attempt and independent unscored disposition required';END IF;
 RETURN NEW;END $$;
CREATE TRIGGER exact_expired_attempt BEFORE INSERT ON campaign_private.semantic_dispositions FOR EACH ROW EXECUTE FUNCTION campaign_private.guard_semantic_disposition();
CREATE FUNCTION campaign_private.semantic_result_on_time(p_job uuid) RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
 SELECT EXISTS(SELECT 1 FROM campaign_private.semantic_jobs s JOIN anvil.jobs j ON j.id=s.id AND j.project_id=s.project_id
 WHERE s.id=p_job AND s.project_id=nullif(current_setting('anvil.project',true),'')::uuid AND s.state='completed'
 AND j.kind='benchmark_campaign_judge' AND s.finished_at<=j.lease_until);
$$;
REVOKE ALL ON FUNCTION campaign_private.semantic_result_on_time(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION campaign_private.semantic_result_on_time(uuid) TO anvil_golden_grader;
CREATE FUNCTION marketing_runtime.campaign_grade_ready(p_job uuid) RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
 SELECT EXISTS(SELECT 1 FROM marketing_runtime.grading_jobs g WHERE g.id=p_job
 AND g.project_id=nullif(current_setting('anvil.project',true),'')::uuid AND g.state='queued'
 AND NOT EXISTS(SELECT 1 FROM campaign_private.semantic_jobs s WHERE s.grading_job_id=g.id AND s.project_id=g.project_id
 AND (s.state IN('queued','dispatching','execution_unknown') OR(s.state='completed' AND NOT campaign_private.semantic_result_on_time(s.id)))
 AND NOT EXISTS(SELECT 1 FROM campaign_private.semantic_dispositions d WHERE d.semantic_job_id=s.id AND d.project_id=s.project_id AND d.disposition='unscored_final')));
$$;
REVOKE ALL ON FUNCTION marketing_runtime.campaign_grade_ready(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.campaign_grade_ready(uuid) TO anvil_golden_grader;

CREATE FUNCTION campaign_private.enqueue_semantic_job(p_quote uuid,p_grading uuid,p_batch jsonb,p_projection jsonb,p_input_hash text) RETURNS uuid
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE q marketing_runtime.semantic_quotes;g marketing_runtime.grading_jobs;e marketing_runtime.episodes;seal marketing_runtime.seals;identifier uuid;BEGIN
 SELECT * INTO q FROM marketing_runtime.semantic_quotes WHERE id=p_quote AND project_id=nullif(current_setting('anvil.project',true),'')::uuid;
 SELECT * INTO g FROM marketing_runtime.grading_jobs WHERE id=p_grading AND project_id=q.project_id;
 SELECT * INTO e FROM marketing_runtime.episodes WHERE project_id=g.project_id AND id=g.episode_id;
 SELECT * INTO seal FROM marketing_runtime.seals WHERE project_id=g.project_id AND episode_id=g.episode_id AND generation=g.generation;
 IF q.id IS NULL OR g.id IS NULL OR g.kind<>'workspace_group' OR g.run_id IS DISTINCT FROM q.group_id OR g.plan_id IS DISTINCT FROM q.plan_id
 OR g.state<>'queued' OR e.id IS NULL OR seal.episode_id IS NULL OR g.task_id IS DISTINCT FROM p_batch->>'task_id'
 OR p_batch->>'case_id' IS DISTINCT FROM e.case_id OR p_batch->>'case_snapshot_sha256' IS DISTINCT FROM e.snapshot_sha256
 OR p_projection->'custody' IS DISTINCT FROM jsonb_build_object('grading_job_id',g.id,'episode_id',g.episode_id,'generation',g.generation,'capture_sha256',seal.capture_sha256,'case_id',e.case_id,'case_snapshot_sha256',e.snapshot_sha256)
 OR (p_batch-ARRAY['schema_version','input_projection_sha256']) IS DISTINCT FROM(q.blueprint-'schema_version')
 OR p_batch->>'schema_version' IS DISTINCT FROM 'anvil.campaign-semantic-judge-batch.v1'
 OR p_batch->>'input_projection_sha256' IS DISTINCT FROM p_input_hash OR p_input_hash IS NULL OR p_input_hash!~'^[a-f0-9]{64}$'
 OR octet_length(p_batch::text)>32768 OR octet_length(p_projection::text)>32768 THEN RETURN NULL;END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('campaign-semantic-private-quota:'||q.project_id::text,0));
 IF (SELECT coalesce(sum(octet_length(projection::text)+CASE WHEN state IN('queued','dispatching') THEN 262144 ELSE octet_length(coalesce(result,'{}'::jsonb)::text) END),0) FROM campaign_private.semantic_jobs WHERE project_id=q.project_id)
 +octet_length(p_projection::text)+262144>536870912 THEN RETURN NULL;END IF;
 identifier=gen_random_uuid();
 INSERT INTO campaign_private.semantic_jobs(id,project_id,quote_id,grading_job_id,episode_id,generation,capture_sha256,batch,projection,input_projection_sha256)
 VALUES(identifier,q.project_id,q.id,g.id,g.episode_id,g.generation,seal.capture_sha256,p_batch,p_projection,p_input_hash);
 INSERT INTO anvil.jobs(id,project_id,kind,target_id,status,operation_key) VALUES(identifier,q.project_id,'benchmark_campaign_judge',identifier,'queued','campaign-semantic:'||identifier::text);
 RETURN identifier;
END $$;
REVOKE ALL ON FUNCTION campaign_private.enqueue_semantic_job(uuid,uuid,jsonb,jsonb,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION campaign_private.enqueue_semantic_job(uuid,uuid,jsonb,jsonb,text) TO anvil_golden_grader;

CREATE FUNCTION marketing_runtime.claim_semantic_job() RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE j anvil.jobs;actor uuid;token uuid;BEGIN
 SELECT a.* INTO j FROM anvil.jobs a JOIN campaign_private.semantic_jobs s ON s.id=a.target_id AND s.project_id=a.project_id
 JOIN marketing_runtime.semantic_quotes q ON q.id=s.quote_id AND q.project_id=s.project_id
 JOIN anvil.workspace_execution_groups g ON g.id=q.group_id AND g.project_id=q.project_id
 WHERE a.project_id=nullif(current_setting('anvil.project',true),'')::uuid AND a.kind='benchmark_campaign_judge' AND a.status='queued' AND s.state='queued' AND g.state='launched'
 AND NOT EXISTS(SELECT 1 FROM campaign_private.semantic_dispositions d WHERE d.semantic_job_id=s.id AND d.project_id=s.project_id)
 ORDER BY a.created_at,a.id FOR UPDATE OF a SKIP LOCKED LIMIT 1;
 IF NOT FOUND THEN RETURN NULL;END IF;
 SELECT g.created_by INTO actor FROM campaign_private.semantic_jobs s JOIN marketing_runtime.semantic_quotes q ON q.id=s.quote_id
 JOIN anvil.workspace_execution_groups g ON g.id=q.group_id WHERE s.id=j.target_id;
 token=gen_random_uuid();UPDATE anvil.jobs SET status='leased',lease_token=token,lease_until=clock_timestamp()+interval '180 seconds',attempts=attempts+1 WHERE id=j.id;
 RETURN jsonb_build_object('job_id',j.id,'project_id',j.project_id,'actor_id',actor,'lease_token',token);
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.claim_semantic_job() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.claim_semantic_job() TO anvil_golden_scheduler;

CREATE FUNCTION marketing_runtime.semantic_job_context(p_job uuid,p_lease uuid) RETURNS jsonb
 LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
 SELECT jsonb_build_object('job_id',j.id,'batch',s.batch,'projection',s.projection,'state',s.state,'dispatch_token',s.dispatch_token,
 'request_sha256',s.request_sha256,'broker_claimed',s.broker_claimed,'quote',to_jsonb(q),'plan_id',p.id,'model_binding',p.config->'workspace_model',
 'pricing',p.config->'pricing','request_timeout_seconds',least((p.config->>'request_timeout_seconds')::integer,120),'grading_job_id',s.grading_job_id,
 'custody',jsonb_build_object('grading_job_id',s.grading_job_id,'episode_id',s.episode_id,'generation',s.generation,'capture_sha256',s.capture_sha256,'case_id',s.batch->>'case_id','case_snapshot_sha256',s.batch->>'case_snapshot_sha256'))
 FROM anvil.jobs j JOIN campaign_private.semantic_jobs s ON s.id=j.target_id AND s.project_id=j.project_id
 JOIN marketing_runtime.semantic_quotes q ON q.id=s.quote_id AND q.project_id=s.project_id
 JOIN anvil.harbor_agent_plans p ON p.id=q.plan_id AND p.project_id=q.project_id
 JOIN anvil.workspace_execution_groups g ON g.id=q.group_id AND g.project_id=q.project_id
 JOIN marketing_runtime.episodes e ON e.id=s.episode_id AND e.project_id=s.project_id AND e.generation=s.generation
 JOIN marketing_runtime.seals seal ON seal.episode_id=s.episode_id AND seal.generation=s.generation AND seal.project_id=s.project_id AND seal.capture_sha256=s.capture_sha256
 WHERE j.id=p_job AND j.project_id=nullif(current_setting('anvil.project',true),'')::uuid AND j.kind='benchmark_campaign_judge'
 AND j.status='leased' AND j.lease_token=p_lease AND j.lease_until>clock_timestamp()
 AND s.state IN('queued','dispatching') AND g.state='launched' AND p.state='launched'
 AND NOT EXISTS(SELECT 1 FROM campaign_private.semantic_dispositions d WHERE d.semantic_job_id=s.id AND d.project_id=s.project_id)
 AND e.case_id=s.batch->>'case_id' AND e.snapshot_sha256=s.batch->>'case_snapshot_sha256'
 AND g.created_by=nullif(current_setting('anvil.user',true),'')::uuid AND p.created_by=g.created_by AND anvil.golden_engineer(g.project_id);
$$;
REVOKE ALL ON FUNCTION marketing_runtime.semantic_job_context(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.semantic_job_context(uuid,uuid) TO anvil_app;

CREATE FUNCTION marketing_runtime.start_semantic_job(p_job uuid,p_lease uuid,p_request_hash text) RETURNS uuid
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE context jsonb;token uuid;BEGIN
 PERFORM 1 FROM anvil.workspace_execution_groups g JOIN marketing_runtime.semantic_quotes q ON q.group_id=g.id
 JOIN campaign_private.semantic_jobs s ON s.quote_id=q.id WHERE s.id=p_job FOR UPDATE OF g;
 context=marketing_runtime.semantic_job_context(p_job,p_lease);
 IF context IS NULL OR context->>'state'<>'queued' OR p_request_hash IS NULL OR p_request_hash!~'^[a-f0-9]{64}$' THEN RETURN NULL;END IF;
 token=gen_random_uuid();
 UPDATE campaign_private.semantic_jobs SET state='dispatching',dispatch_token=token,request_sha256=p_request_hash WHERE id=p_job AND state='queued';
 IF NOT FOUND THEN RETURN NULL;END IF;
 RETURN token;
END $$;

CREATE FUNCTION marketing_runtime.claim_semantic_sdk(p_job uuid,p_lease uuid,p_dispatch uuid,p_request_hash text,p_model jsonb) RETURNS boolean
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE context jsonb;q marketing_runtime.semantic_quotes;g anvil.workspace_execution_groups;s campaign_private.semantic_jobs;
 cap bigint;used bigint;slots bigint;budget_id uuid;b jsonb;BEGIN
 SELECT q0.* INTO q FROM marketing_runtime.semantic_quotes q0 JOIN campaign_private.semantic_jobs s0 ON s0.quote_id=q0.id WHERE s0.id=p_job;
 SELECT * INTO g FROM anvil.workspace_execution_groups WHERE id=q.group_id FOR UPDATE;
 context=marketing_runtime.semantic_job_context(p_job,p_lease);
 SELECT * INTO s FROM campaign_private.semantic_jobs WHERE id=p_job FOR UPDATE;
 IF context IS NULL OR s.state<>'dispatching' OR s.broker_claimed OR s.dispatch_token IS DISTINCT FROM p_dispatch
 OR s.request_sha256 IS DISTINCT FROM p_request_hash OR context->'model_binding' IS DISTINCT FROM p_model THEN RETURN false;END IF;
 b=s.batch;
 IF NOT anvil.lock_native_ordinal_award((b->>'binding_id')::uuid,(b->>'configuration_id')::uuid)
 OR NOT EXISTS(SELECT 1 FROM anvil.project_binding_versions v WHERE v.id=(b->>'binding_id')::uuid AND v.project_id=g.project_id AND v.snapshot_sha256=b->>'binding_snapshot_sha256')
 OR NOT EXISTS(SELECT 1 FROM anvil.evaluator_validation_receipts r WHERE r.project_id=g.project_id AND r.id=(b->>'validation_receipt_id')::uuid
 AND r.configuration_id=(b->>'configuration_id')::uuid AND r.configuration_sha256=b->>'configuration_sha256' AND r.evidence_sha256=b->>'validation_receipt_sha256'
 AND r.id=(SELECT latest.id FROM anvil.evaluator_validation_receipts latest WHERE latest.project_id=g.project_id AND latest.configuration_id=r.configuration_id ORDER BY latest.created_at DESC,latest.id DESC LIMIT 1))
 OR EXISTS(SELECT 1 FROM anvil.evaluator_revocations r WHERE r.project_id=g.project_id AND r.configuration_id=(b->>'configuration_id')::uuid)
 THEN RETURN false;END IF;
 PERFORM 1 FROM anvil.project_binding_qualifications q0 WHERE q0.project_id=g.project_id AND q0.binding_id=(b->>'binding_id')::uuid ORDER BY q0.id FOR SHARE;
 IF NOT EXISTS(SELECT 1 FROM anvil.project_binding_qualifications q0 WHERE q0.project_id=g.project_id AND q0.binding_id=(b->>'binding_id')::uuid
 AND q0.release_sha256=b->>'deployment_release_sha256' AND q0.expires_at>clock_timestamp()
 AND NOT EXISTS(SELECT 1 FROM anvil.project_binding_qualification_revocations r WHERE r.qualification_id=q0.id)) THEN RETURN false;END IF;
 cap=(g.snapshot->'preparation'->>'aggregate_cap_micro_usd')::bigint;
 budget_id=(g.snapshot->'preparation'->>'execution_budget_id')::uuid;
 IF cap IS NULL OR cap<=0 OR cap>2000000 OR budget_id IS NULL OR NOT anvil.shared_execution_budget_active(budget_id)
 OR NOT EXISTS(SELECT 1 FROM anvil.shared_execution_group_allocations a WHERE a.group_id=g.id AND a.budget_id=budget_id AND a.amount_micro_usd=cap)
 OR NOT EXISTS(SELECT 1 FROM anvil.pilot_budget_reservations r WHERE r.group_id=g.id AND r.project_id=g.project_id AND r.environment='qa' AND r.subject_hash=g.subject_hash AND r.amount_micro_usd=cap)
 OR NOT EXISTS(SELECT 1 FROM anvil.pilot_budget_policies p WHERE p.environment='qa' AND p.status='active' AND p.start_at<=clock_timestamp() AND p.end_at>clock_timestamp())
 OR NOT EXISTS(SELECT 1 FROM anvil.users u WHERE u.id=g.created_by AND u.active AND NOT u.is_synthetic)
 OR NOT EXISTS(SELECT 1 FROM anvil.workspace_admin_run_authorizations a JOIN anvil.users u ON u.id=a.admin_id AND u.active AND NOT u.is_synthetic
 JOIN anvil.memberships m ON m.project_id=a.project_id AND m.user_id=a.admin_id AND m.active AND m.role='admin'
 WHERE a.group_id=g.id AND a.project_id=g.project_id AND a.subject_hash=g.subject_hash AND a.cap_micro_usd=cap AND a.rights_confirmed AND a.expires_at>clock_timestamp()
 AND NOT EXISTS(SELECT 1 FROM anvil.workspace_admin_run_revocations v WHERE v.authorization_id=a.id)) THEN RETURN false;END IF;
 PERFORM 1 FROM anvil.connections c WHERE c.id=(p_model->>'id')::uuid FOR SHARE;
 PERFORM 1 FROM anvil.workspace_credentials c WHERE c.id=(p_model->'credential'->>'id')::uuid FOR SHARE;
 PERFORM 1 FROM anvil.workspace_model_profiles p JOIN anvil.workspace_model_versions v ON v.profile_id=p.id AND v.project_id=p.project_id WHERE v.connection_id=(p_model->>'id')::uuid FOR SHARE OF p;
 IF NOT EXISTS(SELECT 1 FROM anvil.connections c JOIN anvil.workspace_model_versions v ON v.connection_id=c.id AND v.project_id=c.project_id
 JOIN anvil.workspace_model_profiles p ON p.id=v.profile_id AND p.project_id=v.project_id
 JOIN anvil.workspace_credentials k ON k.id=(p_model->'credential'->>'id')::uuid AND k.project_id=c.project_id
 WHERE c.id=(p_model->>'id')::uuid AND c.project_id=g.project_id AND c.status<>'revoked' AND c.config_hash=p_model->>'config_hash'
 AND p.current_connection_id=c.id AND p.disabled_at IS NULL AND k.revoked_at IS NULL AND k.current_version_id=(p_model->'credential'->>'version_id')::uuid)
 OR NOT anvil.pilot_dispatch_capacity() THEN RETURN false;END IF;
 SELECT coalesce(sum(bound_micro_usd),0),count(*) INTO used,slots FROM marketing_runtime.paid_call_claims WHERE group_id=g.id;
 used=used+(SELECT coalesce(sum(q0.bound_micro_usd),0) FROM campaign_private.semantic_jobs s0 JOIN marketing_runtime.semantic_quotes q0 ON q0.id=s0.quote_id WHERE q0.group_id=g.id AND s0.broker_claimed);
 slots=slots+(SELECT count(*) FROM campaign_private.semantic_jobs s0 JOIN marketing_runtime.semantic_quotes q0 ON q0.id=s0.quote_id WHERE q0.group_id=g.id AND s0.broker_claimed);
 IF used+q.bound_micro_usd>cap OR slots+1>1000 THEN RETURN false;END IF;
 UPDATE campaign_private.semantic_jobs SET broker_claimed=true WHERE id=p_job;
 RETURN true;
END $$;

CREATE FUNCTION marketing_runtime.finish_semantic_job(p_job uuid,p_dispatch uuid,p_state text,p_result jsonb,p_hash text,p_cost bigint) RETURNS boolean
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE bound bigint;BEGIN
 SELECT q.bound_micro_usd INTO bound FROM campaign_private.semantic_jobs s JOIN marketing_runtime.semantic_quotes q ON q.id=s.quote_id
 JOIN anvil.workspace_execution_groups g ON g.id=q.group_id WHERE s.id=p_job AND s.project_id=nullif(current_setting('anvil.project',true),'')::uuid
 AND g.created_by=nullif(current_setting('anvil.user',true),'')::uuid;
 IF bound IS NULL OR p_state NOT IN('completed','error','execution_unknown') OR p_result IS NULL OR octet_length(p_result::text)>262144
 OR p_hash IS NULL OR p_hash!~'^[a-f0-9]{64}$' OR p_cost<0 OR p_cost>bound OR (p_state='completed' AND p_cost IS NULL) THEN RETURN false;END IF;
 UPDATE campaign_private.semantic_jobs SET state=p_state,result=p_result,result_sha256=p_hash,actual_micro_usd=p_cost,finished_at=clock_timestamp()
 WHERE id=p_job AND state='dispatching' AND dispatch_token=p_dispatch AND (p_state<>'completed' OR broker_claimed);
 IF NOT FOUND THEN RETURN false;END IF;
 UPDATE anvil.jobs SET status=CASE WHEN p_state='completed' THEN 'succeeded' ELSE 'failed' END WHERE id=p_job AND kind='benchmark_campaign_judge' AND status='leased';
 INSERT INTO anvil.audit_events(project_id,actor_id,action,target_id,metadata)
 SELECT project_id,nullif(current_setting('anvil.user',true),'')::uuid,'campaign.semantic_completed',id,jsonb_build_object('state',p_state,'result_sha256',p_hash,'actual_micro_usd',p_cost)
 FROM campaign_private.semantic_jobs WHERE id=p_job;
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.start_semantic_job(uuid,uuid,text),marketing_runtime.claim_semantic_sdk(uuid,uuid,uuid,text,jsonb),marketing_runtime.finish_semantic_job(uuid,uuid,text,jsonb,text,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.start_semantic_job(uuid,uuid,text),marketing_runtime.claim_semantic_sdk(uuid,uuid,uuid,text,jsonb),marketing_runtime.finish_semantic_job(uuid,uuid,text,jsonb,text,bigint) TO anvil_app;

-- The original105 candidate fences remain intact. Its private entrypoint cannot
-- be called directly by app; both candidate and judge acquire the same group
-- row before counting the combined once-only physical claims.
ALTER FUNCTION marketing_runtime.claim_paid_call(uuid,uuid,uuid,bigint) RENAME TO claim_paid_candidate_105;
REVOKE ALL ON FUNCTION marketing_runtime.claim_paid_candidate_105(uuid,uuid,uuid,bigint) FROM anvil_app;
CREATE FUNCTION marketing_runtime.claim_paid_call(p_group uuid,p_plan uuid,p_call uuid,p_bound bigint) RETURNS boolean
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE g anvil.workspace_execution_groups;used bigint;slots bigint;BEGIN
 SELECT * INTO g FROM anvil.workspace_execution_groups WHERE id=p_group AND project_id=nullif(current_setting('anvil.project',true),'')::uuid FOR UPDATE;
 IF g.id IS NULL OR p_bound IS NULL OR p_bound<=0 THEN RETURN false;END IF;
 SELECT coalesce(sum(bound_micro_usd),0),count(*) INTO used,slots FROM marketing_runtime.paid_call_claims WHERE group_id=g.id;
 used=used+(SELECT coalesce(sum(q.bound_micro_usd),0) FROM campaign_private.semantic_jobs s JOIN marketing_runtime.semantic_quotes q ON q.id=s.quote_id WHERE q.group_id=g.id AND s.broker_claimed);
 slots=slots+(SELECT count(*) FROM campaign_private.semantic_jobs s JOIN marketing_runtime.semantic_quotes q ON q.id=s.quote_id WHERE q.group_id=g.id AND s.broker_claimed);
 IF used+p_bound>(g.snapshot->'preparation'->>'aggregate_cap_micro_usd')::bigint OR slots+1>1000 THEN RETURN false;END IF;
 RETURN marketing_runtime.claim_paid_candidate_105(p_group,p_plan,p_call,p_bound);
END $$;
REVOKE ALL ON FUNCTION marketing_runtime.claim_paid_call(uuid,uuid,uuid,bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.claim_paid_call(uuid,uuid,uuid,bigint) TO anvil_app;

CREATE OR REPLACE FUNCTION anvil.pilot_dispatch_capacity() RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE env text;cap integer;used bigint;BEGIN
 SELECT environment INTO STRICT env FROM anvil.pilot_budget_policies;
 cap=CASE env WHEN 'qa' THEN 2 WHEN 'staging' THEN 1 ELSE 0 END;
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil:pilot-dispatch-capacity',0));
 SELECT count(*) INTO used FROM anvil.harbor_agent_calls WHERE status IN('dispatching','execution_unknown') AND usage->>'pilot_broker_claimed'='true';
 used=used+(SELECT count(*) FROM anvil.governed_ai_calls WHERE state IN('dispatching','execution_unknown') AND broker_claimed);
 used=used+(SELECT count(*) FROM campaign_private.semantic_jobs WHERE state IN('dispatching','execution_unknown') AND broker_claimed);
 RETURN used<cap;
END $$;

INSERT INTO anvil.schema_versions(version) VALUES(106);
