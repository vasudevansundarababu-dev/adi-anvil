-- Real scoring inputs never enter the ordinary custom-test queue or API vault.
CREATE TABLE banking_private.python_grading_jobs(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,
 trial_id uuid NOT NULL,generation integer NOT NULL CHECK(generation>=0),
 criterion text NOT NULL,binding_id uuid NOT NULL,evaluator_id uuid NOT NULL,
 request jsonb NOT NULL CHECK(octet_length(request::text)<=65536),
 request_sha256 text NOT NULL CHECK(request_sha256~'^[a-f0-9]{64}$'),
 state text NOT NULL DEFAULT 'queued' CHECK(state IN('queued','claimed','completed','error')),
 claim_token uuid,result jsonb,result_sha256 text,created_at timestamptz NOT NULL DEFAULT now(),finished_at timestamptz,
 FOREIGN KEY(project_id,trial_id) REFERENCES banking.trials(project_id,id),
 FOREIGN KEY(project_id,binding_id) REFERENCES anvil.project_binding_versions(project_id,id),
 FOREIGN KEY(project_id,evaluator_id) REFERENCES anvil.custom_python_evaluators(project_id,id),
 UNIQUE(trial_id,generation,criterion));
ALTER TABLE banking_private.python_grading_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE banking_private.python_grading_jobs FORCE ROW LEVEL SECURITY;
CREATE POLICY grader_only ON banking_private.python_grading_jobs TO anvil_golden_grader
 USING(banking.runtime_scope(project_id)) WITH CHECK(banking.runtime_scope(project_id));
GRANT SELECT,INSERT ON banking_private.python_grading_jobs TO anvil_golden_grader;
GRANT UPDATE(state,claim_token,result,result_sha256,finished_at) ON banking_private.python_grading_jobs TO anvil_golden_grader;
CREATE FUNCTION banking_private.python_grading_immutable_input() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='DELETE' OR (NEW.id,NEW.project_id,NEW.trial_id,NEW.generation,NEW.criterion,NEW.binding_id,NEW.evaluator_id,NEW.request,NEW.request_sha256,NEW.created_at)
 IS DISTINCT FROM (OLD.id,OLD.project_id,OLD.trial_id,OLD.generation,OLD.criterion,OLD.binding_id,OLD.evaluator_id,OLD.request,OLD.request_sha256,OLD.created_at)
 THEN RAISE EXCEPTION 'immutable private grading input';END IF;RETURN NEW;END $$;
CREATE TRIGGER immutable_input BEFORE UPDATE OR DELETE ON banking_private.python_grading_jobs
 FOR EACH ROW EXECUTE FUNCTION banking_private.python_grading_immutable_input();
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['custom_python_evaluators','custom_python_jobs','custom_python_revocations',
 'project_binding_versions','project_binding_qualifications','project_binding_qualification_revocations',
 'workspace_execution_groups','praxis_resolved_tasks'] LOOP
  EXECUTE format('GRANT SELECT ON anvil.%I TO anvil_golden_grader',t);
  EXECUTE format('CREATE POLICY private_python_grader_read ON anvil.%I FOR SELECT TO anvil_golden_grader USING(banking.runtime_scope(project_id))',t);
 END LOOP;
END $$;
CREATE FUNCTION anvil.private_python_authors_active(p_binding uuid,p_evaluator uuid) RETURNS boolean
 LANGUAGE sql STABLE SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
 SELECT EXISTS(SELECT 1 FROM anvil.project_binding_versions b JOIN anvil.custom_python_evaluators e ON e.project_id=b.project_id
 WHERE b.id=p_binding AND e.id=p_evaluator AND b.project_id=nullif(current_setting('anvil.project',true),'')::uuid
 AND NOT EXISTS(SELECT 1 FROM unnest(ARRAY[b.created_by,e.created_by]) person(id)
 WHERE NOT EXISTS(SELECT 1 FROM anvil.users u JOIN anvil.memberships m ON m.user_id=u.id
 WHERE u.id=person.id AND u.active AND m.project_id=b.project_id AND m.active AND m.role IN('admin','rl-engineer'))))
 $$;
REVOKE ALL ON FUNCTION anvil.private_python_authors_active(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.private_python_authors_active(uuid,uuid) TO anvil_golden_grader;
