-- One-way custody and explicit no-replay reconciliation. Historical results stay
-- unchanged; legacy claimed rows may have no known claim timestamp.
ALTER TABLE banking_private.python_grading_jobs ADD COLUMN claimed_at timestamptz;
GRANT UPDATE(claimed_at) ON banking_private.python_grading_jobs TO anvil_golden_grader;
CREATE FUNCTION banking_private.python_grading_transition() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='INSERT' THEN
  IF NEW.state<>'queued' OR NEW.claim_token IS NOT NULL OR NEW.claimed_at IS NOT NULL
   OR NEW.result IS NOT NULL OR NEW.result_sha256 IS NOT NULL OR NEW.finished_at IS NOT NULL
   THEN RAISE EXCEPTION 'new grading job must be queued without outcome';END IF;
 ELSE
  IF OLD.state IN('completed','error') THEN RAISE EXCEPTION 'terminal grading result immutable';END IF;
  IF OLD.state='queued' THEN
   IF NEW.state<>'claimed' OR NEW.claim_token IS NULL OR NEW.claimed_at IS NULL
    OR NEW.result IS NOT NULL OR NEW.result_sha256 IS NOT NULL OR NEW.finished_at IS NOT NULL
    THEN RAISE EXCEPTION 'grading claim transition required';END IF;
  ELSIF OLD.state='claimed' THEN
   IF NEW.state NOT IN('completed','error') OR NEW.claim_token IS DISTINCT FROM OLD.claim_token
    OR NEW.claimed_at IS DISTINCT FROM OLD.claimed_at OR NEW.result IS NULL
    OR NEW.result_sha256 IS NULL OR NEW.result_sha256!~'^[a-f0-9]{64}$' OR NEW.finished_at IS NULL
    THEN RAISE EXCEPTION 'once-only grading completion required';END IF;
  END IF;
 END IF;RETURN NEW;END $$;
CREATE TRIGGER legal_transition BEFORE INSERT OR UPDATE ON banking_private.python_grading_jobs
 FOR EACH ROW EXECUTE FUNCTION banking_private.python_grading_transition();

CREATE TABLE banking_private.python_grading_reconciliations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,job_id uuid NOT NULL REFERENCES banking_private.python_grading_jobs(id),
 action text NOT NULL CHECK(action IN('late_result_consumed','unconfirmed_disposed')),
 rationale text NOT NULL CHECK(length(rationale) BETWEEN 10 AND 1000),
 request_sha256 text NOT NULL,result_sha256 text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(job_id));
ALTER TABLE banking_private.python_grading_reconciliations ENABLE ROW LEVEL SECURITY;
ALTER TABLE banking_private.python_grading_reconciliations FORCE ROW LEVEL SECURITY;
CREATE POLICY grader_only ON banking_private.python_grading_reconciliations TO anvil_golden_grader
 USING(banking.runtime_scope(project_id)) WITH CHECK(banking.runtime_scope(project_id));
GRANT SELECT,INSERT ON banking_private.python_grading_reconciliations TO anvil_golden_grader;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON banking_private.python_grading_reconciliations
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable();

-- Binding/revocation mutations coordinate with a final award's shared lock,
-- including privileged SQL writers, rather than relying on a UI convention.
CREATE FUNCTION anvil.private_python_authority_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended('private-python-authority:'||NEW.project_id::text,0));
 RETURN NEW;END $$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['project_binding_versions','custom_python_revocations','project_binding_qualification_revocations'] LOOP
  EXECUTE format('CREATE TRIGGER private_python_authority BEFORE INSERT ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.private_python_authority_mutation()',t);
 END LOOP;
END $$;
CREATE FUNCTION anvil.lock_private_python_award(p_binding uuid,p_evaluator uuid) RETURNS boolean
 LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
DECLARE project uuid;authors uuid[];BEGIN
 project=nullif(current_setting('anvil.project',true),'')::uuid;
 PERFORM pg_advisory_xact_lock_shared(hashtextextended('private-python-authority:'||project::text,0));
 SELECT ARRAY[b.created_by,e.created_by] INTO authors FROM anvil.project_binding_versions b
 JOIN anvil.custom_python_evaluators e ON e.project_id=b.project_id
 WHERE b.id=p_binding AND e.id=p_evaluator AND b.project_id=project;
 IF NOT FOUND THEN RETURN false;END IF;
 PERFORM 1 FROM anvil.users WHERE id=ANY(authors) ORDER BY id FOR SHARE;
 PERFORM 1 FROM anvil.memberships WHERE project_id=project AND user_id=ANY(authors) ORDER BY user_id FOR SHARE;
 RETURN true;END $$;
REVOKE ALL ON FUNCTION anvil.lock_private_python_award(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.lock_private_python_award(uuid,uuid) TO anvil_golden_grader;
