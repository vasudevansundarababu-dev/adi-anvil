-- Independent operator attestations only; saving/generating a draft is not review.
ALTER TABLE banking.safety_episode_plans ADD CONSTRAINT one_prompt_per_safety_episode UNIQUE(project_id,trial_id,generation);
CREATE TABLE anvil.task_safety_prompt_qualifications(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,prompt_id uuid NOT NULL,source_sha256 text NOT NULL,
 prompt_sha256 text NOT NULL,runtime_sha256 text NOT NULL,runtime_image_sha256 text NOT NULL,framework text NOT NULL,
 receipt jsonb NOT NULL CHECK(octet_length(receipt::text)<=65536),receipt_sha256 text NOT NULL,
 expires_at timestamptz NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,prompt_id) REFERENCES anvil.task_safety_prompt_versions(project_id,id),UNIQUE(project_id,id));
CREATE TABLE anvil.task_safety_qualification_revocations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,qualification_id uuid NOT NULL,reason text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,qualification_id) REFERENCES anvil.task_safety_prompt_qualifications(project_id,id),UNIQUE(qualification_id));
DO $$ DECLARE t text;BEGIN FOREACH t IN ARRAY ARRAY['task_safety_prompt_qualifications','task_safety_qualification_revocations'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY engineer_read ON anvil.%I FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id))',t);
 EXECUTE format('CREATE POLICY runtime_read ON anvil.%I FOR SELECT TO anvil_golden_scheduler,anvil_golden_grader USING(banking.runtime_scope(project_id))',t);
 EXECUTE format('GRANT SELECT ON anvil.%I TO anvil_app,anvil_golden_scheduler,anvil_golden_grader',t);
 EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
END LOOP;END $$;
CREATE FUNCTION banking.read_safety_episode_plan(p_trial uuid,p_generation integer)
 RETURNS jsonb LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog,pg_temp AS $$
 SELECT to_jsonb(s)||jsonb_build_object('text',p.text,'source_sha256',p.source_sha256,
  'task_group_id',p.task_group_id,'actual_prompt_sha256',p.sha256,'binding_snapshot',b.snapshot,
  'actual_category',p.category_id,'actual_vector',p.vector)
 FROM banking.safety_episode_plans s
 JOIN banking.paid_agent_bindings paid ON paid.project_id=s.project_id AND paid.plan_id=s.plan_id AND paid.trial_id=s.trial_id AND paid.generation=s.generation
 JOIN banking.trials t ON t.project_id=s.project_id AND t.id=s.trial_id AND t.generation=s.generation
 JOIN anvil.task_safety_prompt_versions p ON p.id=s.prompt_id AND p.project_id=s.project_id
 JOIN anvil.project_binding_versions b ON b.id=s.binding_id AND b.project_id=s.project_id AND b.task_group_id=p.task_group_id
 WHERE s.project_id=nullif(current_setting('anvil.project',true),'')::uuid AND s.trial_id=p_trial AND s.generation=p_generation;
$$;
REVOKE ALL ON FUNCTION banking.read_safety_episode_plan(uuid,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION banking.read_safety_episode_plan(uuid,integer) TO anvil_golden_scheduler,anvil_golden_grader;
GRANT SELECT ON banking.safety_episode_plans TO anvil_app;
CREATE POLICY broker_plan_read ON banking.safety_episode_plans FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id));
GRANT SELECT ON banking.safety_episode_events TO anvil_app;
CREATE POLICY broker_event_read ON banking.safety_episode_events FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id));
CREATE TABLE banking.safety_broker_receipts(
 project_id uuid NOT NULL,call_id uuid PRIMARY KEY,plan_id uuid NOT NULL,generation integer NOT NULL,
 record jsonb NOT NULL CHECK(octet_length(record::text)<=32768),record_sha256 text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,call_id) REFERENCES anvil.harbor_agent_calls(project_id,id),
 FOREIGN KEY(plan_id) REFERENCES banking.safety_episode_plans(plan_id));
ALTER TABLE banking.safety_broker_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE banking.safety_broker_receipts FORCE ROW LEVEL SECURITY;
CREATE POLICY broker_insert ON banking.safety_broker_receipts FOR INSERT TO anvil_app WITH CHECK(
 anvil.golden_engineer(project_id) AND EXISTS(SELECT 1 FROM anvil.harbor_agent_calls c JOIN anvil.harbor_agent_plans p ON p.id=c.plan_id AND p.project_id=c.project_id
 WHERE c.id=call_id AND c.project_id=safety_broker_receipts.project_id AND c.plan_id=safety_broker_receipts.plan_id AND c.status='completed'
 AND p.created_by=nullif(current_setting('anvil.user',true),'')::uuid));
CREATE POLICY broker_read ON banking.safety_broker_receipts FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id));
CREATE POLICY runtime_read ON banking.safety_broker_receipts FOR SELECT TO anvil_golden_scheduler,anvil_golden_grader USING(banking.runtime_scope(project_id));
GRANT SELECT,INSERT ON banking.safety_broker_receipts TO anvil_app;
GRANT SELECT ON banking.safety_broker_receipts TO anvil_golden_scheduler,anvil_golden_grader;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON banking.safety_broker_receipts FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
INSERT INTO anvil.schema_versions(version) VALUES(98);
