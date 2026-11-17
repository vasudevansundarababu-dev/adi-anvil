-- QA admission and host readbacks are operator custody, never client assertions.
CREATE UNIQUE INDEX runtime_qa_client_operation ON anvil.runtime_update_jobs(project_id,role,(request->>'client_operation_id'))
 WHERE scope='qa' AND request->>'client_operation_id' IS NOT NULL;
CREATE TABLE anvil.runtime_qa_admissions(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),role text NOT NULL,
 candidate_id uuid NOT NULL,expected_observation_id uuid NOT NULL,
 envelope jsonb NOT NULL CHECK(jsonb_typeof(envelope)='object' AND octet_length(envelope::text)<=65536),
 envelope_sha256 text NOT NULL CHECK(envelope_sha256~'^[a-f0-9]{64}$'),
 expires_at timestamptz NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,candidate_id) REFERENCES anvil.runtime_role_candidates(project_id,id),
 FOREIGN KEY(project_id,expected_observation_id) REFERENCES anvil.runtime_role_observations(project_id,id),UNIQUE(project_id,id));
CREATE TABLE anvil.runtime_qa_admission_revocations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,admission_id uuid NOT NULL,
 reason text NOT NULL CHECK(length(reason) BETWEEN 10 AND 1000),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,admission_id) REFERENCES anvil.runtime_qa_admissions(project_id,id),UNIQUE(admission_id));
CREATE TABLE anvil.runtime_qa_deployment_projects(
 deployment_id text NOT NULL CHECK(deployment_id='anvil-qa-v1'),role text NOT NULL,
 project_id uuid NOT NULL REFERENCES anvil.projects(id),
 mapping_receipt_sha256 text NOT NULL CHECK(mapping_receipt_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(deployment_id,role,project_id));
CREATE TABLE anvil.runtime_qa_job_admissions(
 job_id uuid PRIMARY KEY,project_id uuid NOT NULL,admission_id uuid NOT NULL,
 reservation jsonb NOT NULL CHECK(jsonb_typeof(reservation)='object' AND octet_length(reservation::text)<=16384),
 reservation_sha256 text NOT NULL CHECK(reservation_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(project_id,job_id) REFERENCES anvil.runtime_update_jobs(project_id,id),
 FOREIGN KEY(project_id,admission_id) REFERENCES anvil.runtime_qa_admissions(project_id,id));
CREATE TABLE anvil.runtime_qa_project_fences(
 job_id uuid NOT NULL REFERENCES anvil.runtime_update_jobs(id),project_id uuid NOT NULL REFERENCES anvil.projects(id),
 role text NOT NULL,created_at timestamptz NOT NULL DEFAULT clock_timestamp(),PRIMARY KEY(job_id,project_id));
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['runtime_qa_admissions','runtime_qa_admission_revocations','runtime_qa_deployment_projects','runtime_qa_job_admissions','runtime_qa_project_fences'] LOOP
  EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY scoped_read ON anvil.%I FOR SELECT TO anvil_app USING(anvil.in_scope(project_id))',t);
  EXECUTE format('GRANT SELECT ON anvil.%I TO anvil_app',t);
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
END $$;
-- Keep raw ledger reservations/operator envelopes out of the public job read model.
REVOKE SELECT ON anvil.runtime_qa_job_admissions FROM anvil_app;
CREATE FUNCTION anvil.runtime_qa_qualification_fence() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended('private-python-authority:'||NEW.project_id::text,0));
 IF EXISTS(SELECT 1 FROM anvil.runtime_qa_project_fences f JOIN anvil.runtime_update_jobs j ON j.id=f.job_id
           WHERE f.project_id=NEW.project_id AND j.scope='qa' AND j.state IN('queued','claimed','installed','outcome_unknown'))
 THEN RAISE EXCEPTION 'Runtime cutover requires fresh qualification after serving verification'; END IF;
 RETURN NEW; END $$;
CREATE TRIGGER runtime_qa_qualification_fence BEFORE INSERT ON anvil.project_binding_qualifications
 FOR EACH ROW EXECUTE FUNCTION anvil.runtime_qa_qualification_fence();
CREATE FUNCTION anvil.runtime_qa_mapping_fence() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended('runtime-qa-mapping:'||NEW.deployment_id||':'||NEW.role,0));
 RETURN NEW;END $$;
CREATE TRIGGER runtime_qa_mapping_fence BEFORE INSERT ON anvil.runtime_qa_deployment_projects
 FOR EACH ROW EXECUTE FUNCTION anvil.runtime_qa_mapping_fence();
ALTER TABLE anvil.runtime_update_events DROP CONSTRAINT runtime_update_events_phase_check;
ALTER TABLE anvil.runtime_update_events ADD CONSTRAINT runtime_update_events_phase_check
 CHECK(phase IN('installed','local_qualified','qualified','invalidated','activated','rolled_back','failed','outcome_unknown','reconciled'));
-- A retained physical activation may be acknowledged after outcome_unknown.
-- Only QA can take this path, with all three immutable cutover receipts present.
CREATE OR REPLACE FUNCTION anvil.runtime_update_guard() RETURNS trigger LANGUAGE plpgsql AS $$
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
       OR (OLD.state='outcome_unknown' AND (NEW.state IN('installed','local_qualified','failed','rolled_back') OR (NEW.scope='qa' AND NEW.state='activated'))))
  THEN RAISE EXCEPTION 'Invalid runtime update transition'; END IF;
  IF NEW.scope='qa' AND NEW.state IN('activated','rolled_back') AND (
    NOT EXISTS(SELECT 1 FROM anvil.runtime_update_events WHERE job_id=NEW.id AND project_id=NEW.project_id AND phase='qualified') OR
    NOT EXISTS(SELECT 1 FROM anvil.runtime_update_events WHERE job_id=NEW.id AND project_id=NEW.project_id AND phase='invalidated') OR
    NOT EXISTS(SELECT 1 FROM anvil.runtime_update_events WHERE job_id=NEW.id AND project_id=NEW.project_id AND phase=NEW.state))
  THEN RAISE EXCEPTION 'QA terminal readback and invalidation receipts required'; END IF;
  IF (NEW.state IN('local_qualified','activated','rolled_back','failed')) <> (NEW.finished_at IS NOT NULL) THEN RAISE EXCEPTION 'Runtime update terminal timestamp required'; END IF;
 END IF;
 RETURN NEW;
END $$;
INSERT INTO anvil.schema_versions(version) VALUES(103);
