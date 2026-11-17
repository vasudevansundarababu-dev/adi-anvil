-- Operator-produced public policy text/metadata from exact reviewed task sources.
-- No automatic legal review, no evaluator-private expectations, no API INSERT.
CREATE TABLE anvil.task_policy_materializations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 task_id text NOT NULL,task_version text NOT NULL,payload_sha256 text NOT NULL,
 source_sha256 text NOT NULL,runtime_source_sha256 text NOT NULL,governing_state text NOT NULL CHECK(governing_state IN('CA','NY','TX','FL','IL')),
 content jsonb NOT NULL CHECK(octet_length(content::text)<=65536),content_sha256 text NOT NULL CHECK(content_sha256~'^[a-f0-9]{64}$'),
 domain_review_receipt_sha256 text NOT NULL CHECK(domain_review_receipt_sha256~'^[a-f0-9]{64}$'),
 runtime_control_receipt_sha256 text NOT NULL CHECK(runtime_control_receipt_sha256~'^[a-f0-9]{64}$'),
 expires_at timestamptz NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(project_id,id));
CREATE TABLE anvil.task_policy_materialization_revocations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,materialization_id uuid NOT NULL,reason text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),FOREIGN KEY(project_id,materialization_id) REFERENCES anvil.task_policy_materializations(project_id,id),UNIQUE(materialization_id));
DO $$ DECLARE t text;BEGIN FOREACH t IN ARRAY ARRAY['task_policy_materializations','task_policy_materialization_revocations'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY engineer_read ON anvil.%I FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id))',t);
 EXECUTE format('CREATE POLICY runtime_read ON anvil.%I FOR SELECT TO anvil_golden_scheduler,anvil_golden_grader USING(banking.runtime_scope(project_id))',t);
 EXECUTE format('GRANT SELECT ON anvil.%I TO anvil_app,anvil_golden_scheduler,anvil_golden_grader',t);
 EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;END $$;
CREATE FUNCTION banking.bound_state_policy_materialization(p_trial uuid,p_generation integer) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,anvil,banking AS $$
 DECLARE p uuid=nullif(current_setting('anvil.project',true),'')::uuid;m anvil.task_policy_materializations%ROWTYPE;BEGIN
 SELECT module.* INTO m FROM banking.paid_agent_bindings paid JOIN anvil.praxis_resolved_tasks task ON task.id=paid.resolved_task_id AND task.project_id=paid.project_id
 JOIN banking.trials trial ON trial.id=paid.trial_id AND trial.project_id=paid.project_id
 JOIN anvil.workspace_execution_groups execution ON execution.id=paid.group_id AND execution.project_id=paid.project_id
 JOIN anvil.project_binding_versions binding ON binding.id=(execution.snapshot->'preparation'->'project_binding'->>'id')::uuid AND binding.project_id=paid.project_id
 JOIN anvil.task_policy_materializations module ON module.project_id=task.project_id AND module.task_id=task.task_key AND module.task_version=task.revision AND module.payload_sha256=task.private_reference_sha256 AND module.source_sha256=binding.snapshot->>'source_sha256'
 WHERE paid.project_id=p AND paid.trial_id=p_trial AND paid.generation=p_generation AND trial.generation=p_generation AND module.governing_state=trial.state->'application'->>'governing_state'
 ORDER BY module.created_at DESC,module.id DESC LIMIT 1;
 IF NOT FOUND THEN RETURN NULL;END IF;
 RETURN to_jsonb(m)||jsonb_build_object('active',m.expires_at>clock_timestamp() AND NOT EXISTS(SELECT 1 FROM anvil.task_policy_materialization_revocations r WHERE r.materialization_id=m.id));
 END $$;
REVOKE ALL ON FUNCTION banking.bound_state_policy_materialization(uuid,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION banking.bound_state_policy_materialization(uuid,integer) TO anvil_golden_scheduler,anvil_golden_grader;
INSERT INTO anvil.schema_versions(version) VALUES(93);
