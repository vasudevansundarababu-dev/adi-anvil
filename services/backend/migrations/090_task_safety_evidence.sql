CREATE TABLE anvil.task_safety_prompt_versions(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,task_group_id uuid NOT NULL,source_sha256 text NOT NULL,
 category_id text NOT NULL,vector text NOT NULL CHECK(vector IN('application.read','document.read','policy.read','handoffs.assigned.read','source_documents.read','asset_refs.read','policies.read','budget_summaries.read')),
 text text NOT NULL CHECK(length(text) BETWEEN 1 AND 2000 AND octet_length(text)<=4096),
 sha256 text NOT NULL CHECK(sha256~'^[a-f0-9]{64}$'),origin text NOT NULL CHECK(origin IN('manual_draft','actual_provider_generation','software_control_generation')),
 generation_call_id uuid,created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,task_group_id) REFERENCES anvil.benchmark_task_groups(project_id,id),
 FOREIGN KEY(project_id,generation_call_id) REFERENCES anvil.governed_ai_calls(project_id,id),UNIQUE(project_id,id),UNIQUE(task_group_id,sha256));
CREATE TABLE anvil.task_safety_prompt_revocations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,prompt_id uuid NOT NULL,created_by uuid NOT NULL REFERENCES anvil.users(id),
 reason text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,prompt_id) REFERENCES anvil.task_safety_prompt_versions(project_id,id),UNIQUE(prompt_id));
CREATE TABLE banking.safety_episode_plans(
 project_id uuid NOT NULL,plan_id uuid PRIMARY KEY,trial_id uuid NOT NULL,generation integer NOT NULL,
 binding_id uuid NOT NULL,prompt_id uuid NOT NULL,prompt_sha256 text NOT NULL,category_id text NOT NULL,vector text NOT NULL,
 payload jsonb NOT NULL,payload_sha256 text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,plan_id) REFERENCES anvil.harbor_agent_plans(project_id,id),
 FOREIGN KEY(project_id,trial_id) REFERENCES banking.trials(project_id,id),
 FOREIGN KEY(project_id,binding_id) REFERENCES anvil.project_binding_versions(project_id,id),
 FOREIGN KEY(project_id,prompt_id) REFERENCES anvil.task_safety_prompt_versions(project_id,id));
CREATE TABLE banking.safety_episode_events(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,plan_id uuid NOT NULL,generation integer NOT NULL,kind text NOT NULL,
 record jsonb NOT NULL CHECK(octet_length(record::text)<=32768),record_sha256 text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(plan_id) REFERENCES banking.safety_episode_plans(plan_id),UNIQUE(project_id,id));
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['task_safety_prompt_versions','task_safety_prompt_revocations'] LOOP
  EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY scoped_read ON anvil.%I FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id))',t);
  EXECUTE format('CREATE POLICY scoped_insert ON anvil.%I FOR INSERT TO anvil_app WITH CHECK(anvil.golden_engineer(project_id) AND created_by=nullif(current_setting(''anvil.user'',true),'''')::uuid)',t);
  EXECUTE format('CREATE POLICY scheduler_read ON anvil.%I FOR SELECT TO anvil_golden_scheduler,anvil_golden_grader USING(banking.runtime_scope(project_id))',t);
  EXECUTE format('GRANT SELECT,INSERT ON anvil.%I TO anvil_app',t);
  EXECUTE format('GRANT SELECT ON anvil.%I TO anvil_golden_scheduler,anvil_golden_grader',t);
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['safety_episode_plans','safety_episode_events'] LOOP
  EXECUTE format('ALTER TABLE banking.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE banking.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY scheduler_write ON banking.%I TO anvil_golden_scheduler USING(banking.runtime_scope(project_id)) WITH CHECK(banking.runtime_scope(project_id))',t);
  EXECUTE format('CREATE POLICY grader_read ON banking.%I FOR SELECT TO anvil_golden_grader USING(banking.runtime_scope(project_id))',t);
  EXECUTE format('GRANT SELECT,INSERT ON banking.%I TO anvil_golden_scheduler',t);
  EXECUTE format('GRANT SELECT ON banking.%I TO anvil_golden_grader',t);
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON banking.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
END $$;
INSERT INTO anvil.schema_versions(version) VALUES(90);
