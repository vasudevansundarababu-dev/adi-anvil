-- Existing privileged host operator owns physical actions. No app/ordinary
-- worker UPDATE, claim, operation-receipt or serving-observation privilege.
ALTER TABLE anvil.runtime_role_allowlist ADD COLUMN compatibility jsonb NOT NULL DEFAULT '{}'::jsonb
 CHECK(jsonb_typeof(compatibility)='object' AND octet_length(compatibility::text)<=16384);
CREATE TABLE anvil.runtime_update_jobs(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,role text NOT NULL,candidate_id uuid NOT NULL,
 expected_observation_id uuid,scope text NOT NULL CHECK(scope IN('local_control','qa')),
 state text NOT NULL DEFAULT 'queued' CHECK(state IN('queued','claimed','installed','local_qualified','activated','rolled_back','failed','outcome_unknown')),
 request jsonb NOT NULL,request_sha256 text NOT NULL CHECK(request_sha256~'^[a-f0-9]{64}$'),
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 claim_token uuid,claimed_at timestamptz,finished_at timestamptz,
 FOREIGN KEY(project_id,candidate_id) REFERENCES anvil.runtime_role_candidates(project_id,id),
 FOREIGN KEY(project_id,expected_observation_id) REFERENCES anvil.runtime_role_observations(project_id,id),
 UNIQUE(project_id,id));
CREATE UNIQUE INDEX runtime_one_active_update ON anvil.runtime_update_jobs(project_id,role)
 WHERE state IN('queued','claimed','installed','outcome_unknown');
CREATE TABLE anvil.runtime_update_events(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,job_id uuid NOT NULL,
 phase text NOT NULL CHECK(phase IN('installed','local_qualified','activated','rolled_back','failed','outcome_unknown','reconciled')),
 receipt jsonb NOT NULL CHECK(jsonb_typeof(receipt)='object' AND octet_length(receipt::text)<=65536),
 receipt_sha256 text NOT NULL CHECK(receipt_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,job_id) REFERENCES anvil.runtime_update_jobs(project_id,id),UNIQUE(job_id,phase,receipt_sha256));
CREATE UNIQUE INDEX runtime_single_operation_result ON anvil.runtime_update_events(job_id,phase) WHERE phase<>'outcome_unknown';
CREATE FUNCTION anvil.runtime_update_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Runtime update history is retained'; END IF;
 IF TG_OP='INSERT' THEN
  IF NEW.state<>'queued' OR NEW.claim_token IS NOT NULL OR NEW.claimed_at IS NOT NULL OR NEW.finished_at IS NOT NULL THEN
   RAISE EXCEPTION 'Runtime update starts queued without a claim/result'; END IF;
  RETURN NEW;
 END IF;
 IF ROW(NEW.id,NEW.project_id,NEW.role,NEW.candidate_id,NEW.expected_observation_id,NEW.scope,NEW.request,NEW.request_sha256,NEW.created_by,NEW.created_at)
 IS DISTINCT FROM ROW(OLD.id,OLD.project_id,OLD.role,OLD.candidate_id,OLD.expected_observation_id,OLD.scope,OLD.request,OLD.request_sha256,OLD.created_by,OLD.created_at)
 THEN RAISE EXCEPTION 'Runtime update pin is immutable'; END IF;
 IF OLD.state IN('local_qualified','activated','rolled_back','failed') THEN RAISE EXCEPTION 'Runtime update result is immutable'; END IF;
 IF OLD.state='queued' THEN
  IF NEW.state<>'claimed' OR NEW.claim_token IS NULL OR NEW.claimed_at IS NULL OR NEW.finished_at IS NOT NULL THEN RAISE EXCEPTION 'Runtime update claim required'; END IF;
 ELSE
  IF NEW.claim_token IS DISTINCT FROM OLD.claim_token OR NEW.claimed_at IS DISTINCT FROM OLD.claimed_at THEN RAISE EXCEPTION 'Runtime update claim cannot change'; END IF;
  IF NOT ((OLD.state='claimed' AND NEW.state IN('installed','failed','outcome_unknown'))
       OR (OLD.state='installed' AND NEW.state IN('local_qualified','activated','rolled_back','failed','outcome_unknown'))
       OR (OLD.state='outcome_unknown' AND NEW.state IN('installed','local_qualified','failed','rolled_back'))) THEN RAISE EXCEPTION 'Invalid runtime update transition'; END IF;
  IF (NEW.state IN('local_qualified','activated','rolled_back','failed')) <> (NEW.finished_at IS NOT NULL) THEN RAISE EXCEPTION 'Runtime update terminal timestamp required'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER runtime_update_guard BEFORE INSERT OR UPDATE OR DELETE ON anvil.runtime_update_jobs
 FOR EACH ROW EXECUTE FUNCTION anvil.runtime_update_guard();
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.runtime_update_events
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
ALTER TABLE anvil.runtime_update_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.runtime_update_jobs FORCE ROW LEVEL SECURITY;
ALTER TABLE anvil.runtime_update_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.runtime_update_events FORCE ROW LEVEL SECURITY;
CREATE POLICY scoped_read ON anvil.runtime_update_jobs FOR SELECT TO anvil_app USING(anvil.in_scope(project_id));
CREATE POLICY scoped_read ON anvil.runtime_update_events FOR SELECT TO anvil_app USING(anvil.in_scope(project_id));
CREATE POLICY admin_queue ON anvil.runtime_update_jobs FOR INSERT TO anvil_app WITH CHECK(
 anvil.in_scope(project_id) AND created_by=nullif(current_setting('anvil.user',true),'')::uuid
 AND EXISTS(SELECT 1 FROM anvil.memberships WHERE project_id=runtime_update_jobs.project_id AND user_id=created_by AND active AND role='admin')
 AND EXISTS(SELECT 1 FROM anvil.runtime_role_candidates t WHERE t.project_id=runtime_update_jobs.project_id AND t.id=candidate_id AND t.role=runtime_update_jobs.role));
GRANT SELECT,INSERT ON anvil.runtime_update_jobs TO anvil_app;
GRANT SELECT ON anvil.runtime_update_events TO anvil_app;
INSERT INTO anvil.schema_versions(version) VALUES(101);
