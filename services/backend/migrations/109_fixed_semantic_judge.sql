-- Versioned independent judge snapshots; preserve every legacy row and grant.
-- Source only until migration109 and its exact SQL/RLS/race checks qualify.
CREATE FUNCTION marketing_runtime.fixed_judge_schema_version() RETURNS integer
 LANGUAGE sql IMMUTABLE SECURITY INVOKER AS $$ SELECT 2 $$;
REVOKE ALL ON FUNCTION marketing_runtime.fixed_judge_schema_version() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.fixed_judge_schema_version() TO anvil_app,anvil_golden_grader;

ALTER TABLE marketing_runtime.semantic_quotes
 ADD COLUMN model_binding jsonb,
 ADD COLUMN pricing jsonb,
 ADD CONSTRAINT semantic_quote_model_version CHECK ((
  (blueprint->>'schema_version'='anvil.campaign-semantic-judge-blueprint.v1'
   AND model_binding IS NULL AND pricing IS NULL)
  OR (blueprint->>'schema_version'='anvil.campaign-semantic-judge-blueprint.v2'
   AND model_binding IS NOT NULL AND pricing IS NOT NULL
   AND jsonb_typeof(model_binding)='object' AND jsonb_typeof(pricing)='object'
   AND octet_length(model_binding::text)<=32768 AND octet_length(pricing::text)<=32768
   AND model_binding->>'id'=blueprint->>'judge_model_profile_id'
   AND model_binding->>'provider'=pricing->>'provider'
   AND model_binding->>'model_id'=pricing->>'model_id')) IS TRUE);

CREATE OR REPLACE FUNCTION marketing_runtime.guard_semantic_quote() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
DECLARE p anvil.harbor_agent_plans;g anvil.workspace_execution_groups;incoming jsonb;BEGIN
 SELECT * INTO p FROM anvil.harbor_agent_plans WHERE project_id=NEW.project_id AND id=NEW.plan_id;
 SELECT * INTO g FROM anvil.workspace_execution_groups WHERE project_id=NEW.project_id AND id=NEW.group_id;
 incoming=to_jsonb(NEW)-ARRAY['id','project_id','group_id','created_at'];
 IF NEW.blueprint->>'schema_version'='anvil.campaign-semantic-judge-blueprint.v1' THEN
  incoming=incoming-ARRAY['model_binding','pricing'];
 END IF;
 IF p.id IS NULL OR g.id IS NULL OR p.state<>'draft' OR g.state<>'draft'
 OR p.created_by IS DISTINCT FROM nullif(current_setting('anvil.user',true),'')::uuid
 OR p.config->>'workspace_execution_group' IS DISTINCT FROM g.id::text OR p.config->>'marketing_paid' IS DISTINCT FROM 'true'
 OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(g.snapshot->'shared_call_quote'->'judge_reservations') q
 WHERE q = incoming)
 THEN RAISE EXCEPTION 'exact immutable upfront shared judge quote required';END IF;
 RETURN NEW;END $$;

CREATE OR REPLACE FUNCTION campaign_private.enqueue_semantic_job(p_quote uuid,p_grading uuid,p_batch jsonb,p_projection jsonb,p_input_hash text) RETURNS uuid
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
 OR p_batch->>'schema_version' IS DISTINCT FROM (CASE q.blueprint->>'schema_version'
 WHEN 'anvil.campaign-semantic-judge-blueprint.v1' THEN 'anvil.campaign-semantic-judge-batch.v1'
 WHEN 'anvil.campaign-semantic-judge-blueprint.v2' THEN 'anvil.campaign-semantic-judge-batch.v2' ELSE NULL END)
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

CREATE OR REPLACE FUNCTION marketing_runtime.semantic_job_context(p_job uuid,p_lease uuid) RETURNS jsonb
 LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
 SELECT jsonb_build_object('job_id',j.id,'batch',s.batch,'projection',s.projection,'state',s.state,'dispatch_token',s.dispatch_token,
 'request_sha256',s.request_sha256,'broker_claimed',s.broker_claimed,'quote',to_jsonb(q),'plan_id',p.id,'candidate_model_binding',p.config->'workspace_model',
 'model_binding',CASE WHEN q.blueprint->>'schema_version'='anvil.campaign-semantic-judge-blueprint.v2' THEN q.model_binding ELSE p.config->'workspace_model' END,
 'pricing',CASE WHEN q.blueprint->>'schema_version'='anvil.campaign-semantic-judge-blueprint.v2' THEN q.pricing ELSE p.config->'pricing' END,'request_timeout_seconds',least((p.config->>'request_timeout_seconds')::integer,120),'grading_job_id',s.grading_job_id,
 'custody',jsonb_build_object('grading_job_id',s.grading_job_id,'episode_id',s.episode_id,'generation',s.generation,'capture_sha256',s.capture_sha256,'case_id',s.batch->>'case_id','case_snapshot_sha256',s.batch->>'case_snapshot_sha256'))
 FROM anvil.jobs j JOIN campaign_private.semantic_jobs s ON s.id=j.target_id AND s.project_id=j.project_id
 JOIN marketing_runtime.semantic_quotes q ON q.id=s.quote_id AND q.project_id=s.project_id
 JOIN anvil.harbor_agent_plans p ON p.id=q.plan_id AND p.project_id=q.project_id
 JOIN anvil.workspace_execution_groups g ON g.id=q.group_id AND g.project_id=q.project_id
 JOIN marketing_runtime.episodes e ON e.id=s.episode_id AND e.project_id=s.project_id AND e.generation=s.generation
 JOIN marketing_runtime.seals seal ON seal.episode_id=s.episode_id AND seal.generation=s.generation AND seal.project_id=s.project_id AND seal.capture_sha256=s.capture_sha256
 WHERE j.id=p_job AND j.project_id=nullif(current_setting('anvil.project',true),'')::uuid AND j.kind='benchmark_campaign_judge'
 AND ((q.blueprint->>'schema_version'='anvil.campaign-semantic-judge-blueprint.v1'
       AND s.batch->>'schema_version'='anvil.campaign-semantic-judge-batch.v1'
       AND q.model_binding IS NULL AND q.pricing IS NULL)
  OR (q.blueprint->>'schema_version'='anvil.campaign-semantic-judge-blueprint.v2'
       AND s.batch->>'schema_version'='anvil.campaign-semantic-judge-batch.v2'
       AND q.model_binding IS NOT NULL AND q.pricing IS NOT NULL
       AND s.batch->>'model_binding_sha256'=q.model_binding_sha256
       AND s.batch->>'candidate_model_binding_sha256'=q.blueprint->>'candidate_model_binding_sha256'
       AND s.batch->>'judge_model_profile_id'=q.model_binding->>'id'
       AND (q.pricing->>'expires_at')::timestamptz>clock_timestamp()))
 AND j.status='leased' AND j.lease_token=p_lease AND j.lease_until>clock_timestamp()
 AND s.state IN('queued','dispatching') AND g.state='launched' AND p.state='launched'
 AND NOT EXISTS(SELECT 1 FROM campaign_private.semantic_dispositions d WHERE d.semantic_job_id=s.id AND d.project_id=s.project_id)
 AND e.case_id=s.batch->>'case_id' AND e.snapshot_sha256=s.batch->>'case_snapshot_sha256'
 AND g.created_by=nullif(current_setting('anvil.user',true),'')::uuid AND p.created_by=g.created_by AND anvil.golden_engineer(g.project_id);
$$;

-- A private grader can verify the actual parent candidate without broad access
-- to model connections, other plans or credential values.
CREATE FUNCTION marketing_runtime.semantic_candidate_binding(p_grading uuid) RETURNS jsonb
 LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
 SELECT p.config->'workspace_model'
 FROM marketing_runtime.grading_jobs g
 JOIN anvil.harbor_agent_plans p ON p.id=g.plan_id AND p.project_id=g.project_id
 JOIN marketing_runtime.paid_agent_bindings b ON b.plan_id=p.id AND b.project_id=p.project_id
 WHERE g.id=p_grading AND g.project_id=nullif(current_setting('anvil.project',true),'')::uuid
 AND g.kind='workspace_group' AND g.state='queued' AND banking.runtime_scope(g.project_id);
$$;
REVOKE ALL ON FUNCTION marketing_runtime.semantic_candidate_binding(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.semantic_candidate_binding(uuid) TO anvil_golden_grader;
