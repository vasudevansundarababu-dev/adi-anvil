-- Durable graph coordination. No native qualification or paid launch is seeded.
CREATE TABLE anvil.workflow_executions(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 created_by uuid NOT NULL REFERENCES anvil.users(id),binding jsonb NOT NULL,
 binding_sha256 text NOT NULL CHECK(binding_sha256~'^[a-f0-9]{64}$'),
 mode text NOT NULL CHECK(mode IN('software_conformance','native')),
 assignments jsonb NOT NULL,state jsonb NOT NULL,state_sha256 text NOT NULL,
 cancel_requested boolean NOT NULL DEFAULT false,expires_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(project_id,id));
CREATE TABLE anvil.workflow_human_requests(
 project_id uuid NOT NULL,execution_id uuid NOT NULL,request_key text NOT NULL,
 assigned_to uuid NOT NULL REFERENCES anvil.users(id),request_sha256 text NOT NULL,
 deadline timestamptz NOT NULL,PRIMARY KEY(execution_id,request_key),
 FOREIGN KEY(project_id,execution_id) REFERENCES anvil.workflow_executions(project_id,id));
CREATE TABLE anvil.workflow_human_answers(
 project_id uuid NOT NULL,execution_id uuid NOT NULL,request_key text NOT NULL,
 actor_id uuid NOT NULL REFERENCES anvil.users(id),response jsonb NOT NULL,
 outcome text NOT NULL DEFAULT 'next' CHECK(outcome IN('next','error')),
 response_sha256 text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(execution_id,request_key),
 FOREIGN KEY(execution_id,request_key) REFERENCES anvil.workflow_human_requests(execution_id,request_key));
CREATE TABLE anvil.workflow_events(
 project_id uuid NOT NULL,execution_id uuid NOT NULL,event_index integer NOT NULL,
 event jsonb NOT NULL,event_sha256 text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(execution_id,event_index),
 FOREIGN KEY(project_id,execution_id) REFERENCES anvil.workflow_executions(project_id,id));
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['workflow_executions','workflow_human_requests','workflow_human_answers','workflow_events'] LOOP
  EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY scoped_read ON anvil.%I FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id))',t);
  EXECUTE format('CREATE POLICY scoped_worker ON anvil.%I TO anvil_worker USING(anvil.in_scope(project_id))',t);
  EXECUTE format('GRANT SELECT ON anvil.%I TO anvil_app,anvil_worker',t);
 END LOOP;
END $$;
CREATE POLICY create_execution ON anvil.workflow_executions FOR INSERT TO anvil_app
 WITH CHECK(anvil.golden_engineer(project_id) AND created_by=nullif(current_setting('anvil.user',true),'')::uuid AND mode='software_conformance');
GRANT INSERT ON anvil.workflow_executions TO anvil_app;
CREATE POLICY cancel_execution ON anvil.workflow_executions FOR UPDATE TO anvil_app USING(anvil.golden_engineer(project_id)) WITH CHECK(anvil.golden_engineer(project_id));
GRANT UPDATE(cancel_requested) ON anvil.workflow_executions TO anvil_app;
GRANT UPDATE(state,state_sha256,cancel_requested) ON anvil.workflow_executions TO anvil_worker;
GRANT INSERT ON anvil.workflow_human_requests,anvil.workflow_events TO anvil_worker;
CREATE POLICY answer_request ON anvil.workflow_human_answers FOR INSERT TO anvil_app WITH CHECK(
 actor_id=nullif(current_setting('anvil.user',true),'')::uuid AND anvil.golden_engineer(project_id)
 AND EXISTS(SELECT 1 FROM anvil.users u WHERE u.id=actor_id AND u.active AND NOT u.is_synthetic)
 AND EXISTS(SELECT 1 FROM anvil.workflow_human_requests r JOIN anvil.workflow_executions e ON e.id=r.execution_id
 WHERE r.execution_id=workflow_human_answers.execution_id AND r.request_key=workflow_human_answers.request_key
 AND r.project_id=workflow_human_answers.project_id AND r.assigned_to=actor_id AND r.deadline>now()
 AND NOT e.cancel_requested AND e.expires_at>now() AND e.state->>'status'='waiting_human'));
GRANT INSERT ON anvil.workflow_human_answers TO anvil_app;
CREATE FUNCTION anvil.workflow_execution_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='DELETE' OR (to_jsonb(OLD)-ARRAY['state','state_sha256','cancel_requested']) IS DISTINCT FROM
 (to_jsonb(NEW)-ARRAY['state','state_sha256','cancel_requested']) OR (OLD.cancel_requested AND NOT NEW.cancel_requested)
 THEN RAISE EXCEPTION 'immutable workflow execution binding'; END IF; RETURN NEW; END $$;
CREATE TRIGGER execution_binding BEFORE UPDATE OR DELETE ON anvil.workflow_executions FOR EACH ROW EXECUTE FUNCTION anvil.workflow_execution_guard();
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.workflow_human_requests FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.workflow_human_answers FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.workflow_events FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
INSERT INTO anvil.schema_versions(version) VALUES(72);
