-- Source candidate: immutable original cleanup timing, never work admission.
CREATE FUNCTION marketing_runtime.capture_stop_deadline(p_job uuid,p_lease uuid,p_plan uuid)
 RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET timezone='UTC' AS $$
 SELECT jsonb_build_object('scope',e.scope,'expires_at',e.expires_at,
 'materialize_before',e.expires_at-((q.qualification_canonical::jsonb->'status_transport'->>'cleanup_reserve_seconds')||' seconds')::interval)
 FROM campaign_private.capture_enrollments e
 JOIN campaign_private.capture_channel_qualifications q ON q.project_id=e.project_id AND q.id=e.channel_qualification_id
 JOIN campaign_private.world_sessions w ON w.project_id=e.project_id AND w.plan_id=e.plan_id AND w.job_id=e.job_id
 JOIN marketing_runtime.paid_agent_bindings b ON b.project_id=w.project_id AND b.plan_id=w.plan_id
 JOIN anvil.harbor_agent_plans p ON p.project_id=b.project_id AND p.id=b.plan_id
 JOIN anvil.jobs j ON j.project_id=w.project_id AND j.id=w.job_id AND j.target_id=p.check_id
 WHERE e.project_id=nullif(current_setting('anvil.project',true),'')::uuid
 AND e.actor_id=nullif(current_setting('anvil.user',true),'')::uuid
 AND e.job_id=p_job AND e.plan_id=p_plan AND e.body_schema='anvil.marketing-native-capture-submission.v2'
 AND w.lease_sha256=encode(sha256(convert_to(p_lease::text,'UTF8')),'hex')
 AND(j.lease_token IS NULL OR j.lease_token=p_lease)
 AND j.kind='benchmark_marketing_paid' AND b.created_by=e.actor_id AND p.created_by=b.created_by
 AND p.config->>'marketing_paid'='true' AND coalesce(p.config->>'golden_kyc_paid','false')<>'true'
 AND b.execution_sha256=w.attachment->>'execution_sha256'
 AND e.scope=jsonb_build_object('project_id',w.project_id,'job_id',w.job_id,'plan_id',w.plan_id,
 'world_binding_id',w.world_binding_id,'world_binding_sha256',w.world_binding_sha256,'episode_id',w.episode_id,'generation',w.generation,
 'lease_sha256',w.lease_sha256,'source_qualification_sha256',(SELECT receipt_sha256 FROM campaign_private.world_qualifications v WHERE v.project_id=w.project_id AND v.id=w.qualification_id),
 'execution_sha256',w.attachment->>'execution_sha256')
 AND q.qualification_canonical::jsonb->'status_transport'->>'cleanup_reserve_seconds'~'^[0-9]{1,3}$'
 AND (q.qualification_canonical::jsonb->'status_transport'->>'cleanup_reserve_seconds')::integer BETWEEN 1 AND 600;
$$;
REVOKE ALL ON FUNCTION marketing_runtime.capture_stop_deadline(uuid,uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION marketing_runtime.capture_stop_deadline(uuid,uuid,uuid) TO anvil_app;
