-- Explicit graph testing registration, never inherited from a legacy Task review.
CREATE TABLE anvil.workflow_definitions(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,package_id uuid NOT NULL,
 definition jsonb NOT NULL,subject_hash text NOT NULL CHECK(subject_hash~'^[a-f0-9]{64}$'),
 approved_by uuid NOT NULL REFERENCES anvil.users(id),review_artifact_id uuid NOT NULL,
 revoked_at timestamptz,created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(project_id,id),
 FOREIGN KEY(project_id,package_id) REFERENCES anvil.harbor_packages(project_id,id),
 FOREIGN KEY(project_id,review_artifact_id) REFERENCES anvil.artifacts(project_id,id));
CREATE TABLE anvil.workflow_native_links(
 project_id uuid NOT NULL,execution_id uuid PRIMARY KEY,plan_id uuid NOT NULL UNIQUE,
 definition_id uuid NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,execution_id) REFERENCES anvil.workflow_executions(project_id,id),
 FOREIGN KEY(project_id,plan_id) REFERENCES anvil.harbor_agent_plans(project_id,id),
 FOREIGN KEY(project_id,definition_id) REFERENCES anvil.workflow_definitions(project_id,id));
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['workflow_definitions','workflow_native_links'] LOOP
  EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY read_scope ON anvil.%I FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id))',t);
  EXECUTE format('CREATE POLICY write_scope ON anvil.%I FOR INSERT TO anvil_app WITH CHECK(anvil.golden_engineer(project_id))',t);
  EXECUTE format('GRANT SELECT,INSERT ON anvil.%I TO anvil_app',t);
 END LOOP;
END $$;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.workflow_native_links FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
GRANT UPDATE(revoked_at) ON anvil.workflow_definitions TO anvil_app;
CREATE POLICY revoke_scope ON anvil.workflow_definitions FOR UPDATE TO anvil_app USING(anvil.golden_engineer(project_id));
CREATE FUNCTION anvil.workflow_definition_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='DELETE' OR OLD.revoked_at IS NOT NULL OR NEW.revoked_at IS NULL OR (to_jsonb(OLD)-'revoked_at') IS DISTINCT FROM (to_jsonb(NEW)-'revoked_at') THEN RAISE EXCEPTION 'immutable workflow definition'; END IF;RETURN NEW;END $$;
CREATE TRIGGER binding BEFORE UPDATE OR DELETE ON anvil.workflow_definitions FOR EACH ROW EXECUTE FUNCTION anvil.workflow_definition_guard();
CREATE POLICY native_create ON anvil.workflow_executions FOR INSERT TO anvil_app WITH CHECK(anvil.golden_engineer(project_id) AND created_by=nullif(current_setting('anvil.user',true),'')::uuid AND mode='native');
GRANT UPDATE(state,state_sha256) ON anvil.workflow_executions TO anvil_app;
DROP POLICY scoped_worker ON anvil.workflow_executions;
CREATE POLICY scoped_worker_read ON anvil.workflow_executions FOR SELECT TO anvil_worker USING(anvil.in_scope(project_id) AND mode='software_conformance');
CREATE POLICY scoped_worker_write ON anvil.workflow_executions FOR UPDATE TO anvil_worker USING(anvil.in_scope(project_id) AND mode='software_conformance');
CREATE POLICY native_events ON anvil.workflow_events FOR INSERT TO anvil_app WITH CHECK(anvil.golden_engineer(project_id));
CREATE POLICY native_requests ON anvil.workflow_human_requests FOR INSERT TO anvil_app WITH CHECK(anvil.golden_engineer(project_id));
GRANT INSERT ON anvil.workflow_events,anvil.workflow_human_requests TO anvil_app;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['workflow_events','workflow_human_requests','workflow_human_answers'] LOOP
  EXECUTE format('CREATE POLICY worker_fixture_only ON anvil.%I AS RESTRICTIVE FOR ALL TO anvil_worker USING(EXISTS(SELECT 1 FROM anvil.workflow_executions e WHERE e.id=execution_id AND e.mode=''software_conformance'')) WITH CHECK(EXISTS(SELECT 1 FROM anvil.workflow_executions e WHERE e.id=execution_id AND e.mode=''software_conformance''))',t);
 END LOOP;
END $$;
CREATE FUNCTION anvil.wake_workflow_jobs() RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$ DECLARE n integer; BEGIN
 UPDATE anvil.jobs j SET status='queued',lease_token=NULL,lease_until=NULL,attempts=0
 WHERE j.kind='harbor_check' AND j.status='workflow_wait' AND EXISTS(
 SELECT 1 FROM anvil.workflow_native_links l JOIN anvil.harbor_agent_plans p ON p.id=l.plan_id JOIN anvil.workflow_executions e ON e.id=l.execution_id JOIN anvil.harbor_checks h ON h.id=p.check_id
 WHERE p.check_id=j.target_id AND e.project_id=j.project_id AND e.state->>'status'='waiting_human'
 AND (e.cancel_requested OR h.cancel_requested OR e.expires_at<=now() OR EXISTS(SELECT 1 FROM anvil.workflow_human_requests r WHERE r.execution_id=e.id AND e.state->'humans'->r.request_key->>'status'='waiting' AND (r.deadline<=now() OR EXISTS(SELECT 1 FROM anvil.workflow_human_answers a WHERE a.execution_id=r.execution_id AND a.request_key=r.request_key)))));
 GET DIAGNOSTICS n=ROW_COUNT;RETURN n;END $$;
REVOKE ALL ON FUNCTION anvil.wake_workflow_jobs() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.wake_workflow_jobs() TO anvil_worker;
-- Native slots survive coordinator/connection loss. Only attested owned cleanup
-- releases them; expiry is not evidence that an orphaned container stopped.
CREATE TABLE anvil.pilot_native_allocations(
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),project_id uuid NOT NULL REFERENCES anvil.projects(id),
 job_id uuid NOT NULL REFERENCES anvil.jobs(id),lease_token uuid NOT NULL,
 attempt_key text NOT NULL CHECK(attempt_key='attempt' OR attempt_key~'^[a-f0-9]{64}$'),
 node_sha256 text NOT NULL CHECK(node_sha256~'^[a-f0-9]{64}$'),
 slot integer NOT NULL CHECK(slot BETWEEN 1 AND 2),created_at timestamptz NOT NULL DEFAULT now(),released_at timestamptz);
CREATE UNIQUE INDEX pilot_native_active_slot ON anvil.pilot_native_allocations(slot) WHERE released_at IS NULL;
CREATE UNIQUE INDEX pilot_native_active_attempt ON anvil.pilot_native_allocations(job_id,attempt_key) WHERE released_at IS NULL;
ALTER TABLE anvil.pilot_native_allocations ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.pilot_native_allocations FORCE ROW LEVEL SECURITY;
CREATE POLICY scoped_read ON anvil.pilot_native_allocations FOR SELECT TO anvil_worker USING(anvil.in_scope(project_id));
GRANT SELECT ON anvil.pilot_native_allocations TO anvil_worker;
CREATE FUNCTION anvil.native_allocation_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='DELETE' OR OLD.released_at IS NOT NULL OR NEW.released_at IS NULL OR (to_jsonb(OLD)-'released_at') IS DISTINCT FROM (to_jsonb(NEW)-'released_at') THEN RAISE EXCEPTION 'immutable native allocation';END IF;RETURN NEW;END $$;
CREATE TRIGGER retained BEFORE UPDATE OR DELETE ON anvil.pilot_native_allocations FOR EACH ROW EXECUTE FUNCTION anvil.native_allocation_guard();
CREATE FUNCTION anvil.reserve_native_slot(p_job uuid,p_lease uuid,p_attempt text,p_node text) RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
DECLARE j anvil.jobs%ROWTYPE;env text;cap integer;chosen integer;allocation uuid;BEGIN
 SELECT * INTO j FROM anvil.jobs WHERE id=p_job AND kind='harbor_check' AND status='leased' AND lease_token=p_lease AND lease_until>now() AND anvil.in_scope(project_id);
 IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM anvil.harbor_checks h WHERE h.id=j.target_id AND h.project_id=j.project_id AND h.state='running' AND NOT h.cancel_requested) THEN RAISE EXCEPTION 'native lease invalid';END IF;
 SELECT environment INTO STRICT env FROM anvil.pilot_budget_policies;
 cap=CASE env WHEN 'qa' THEN 2 WHEN 'staging' THEN 1 ELSE 0 END;
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil:retained-native-slots',0));
 IF (SELECT count(*) FROM anvil.pilot_native_allocations WHERE released_at IS NULL)>=cap THEN RAISE EXCEPTION 'native capacity retained';END IF;
 SELECT n INTO chosen FROM generate_series(1,cap) n WHERE NOT EXISTS(SELECT 1 FROM anvil.pilot_native_allocations a WHERE a.slot=n AND a.released_at IS NULL) ORDER BY n LIMIT 1;
 INSERT INTO anvil.pilot_native_allocations(project_id,job_id,lease_token,attempt_key,node_sha256,slot) VALUES(j.project_id,j.id,p_lease,p_attempt,p_node,chosen) RETURNING id INTO allocation;RETURN allocation;
END $$;
CREATE FUNCTION anvil.release_native_slot(p_job uuid,p_lease uuid,p_attempt text,p_node text) RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
DECLARE n integer;BEGIN
 IF NOT EXISTS(SELECT 1 FROM anvil.jobs WHERE id=p_job AND kind='harbor_check' AND status='leased' AND lease_token=p_lease AND lease_until>now() AND anvil.in_scope(project_id)) THEN RAISE EXCEPTION 'native cleanup lease invalid';END IF;
 UPDATE anvil.pilot_native_allocations SET released_at=now() WHERE job_id=p_job AND attempt_key=p_attempt AND node_sha256=p_node AND released_at IS NULL;
 GET DIAGNOSTICS n=ROW_COUNT;RETURN n;END $$;
REVOKE ALL ON FUNCTION anvil.reserve_native_slot(uuid,uuid,text,text),anvil.release_native_slot(uuid,uuid,text,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.reserve_native_slot(uuid,uuid,text,text),anvil.release_native_slot(uuid,uuid,text,text) TO anvil_worker;
-- Called in the same transaction as the one-way broker claim. The transaction
-- lock serializes the global count/claim; uncertain claims keep capacity held.
CREATE FUNCTION anvil.pilot_dispatch_capacity() RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
DECLARE env text;cap integer;BEGIN
 SELECT environment INTO STRICT env FROM anvil.pilot_budget_policies;
 cap=CASE env WHEN 'qa' THEN 2 WHEN 'staging' THEN 1 ELSE 0 END;
 PERFORM pg_advisory_xact_lock(hashtextextended('anvil:pilot-dispatch-capacity',0));
 RETURN (SELECT count(*) FROM anvil.harbor_agent_calls WHERE status IN('dispatching','execution_unknown') AND usage->>'pilot_broker_claimed'='true')<cap;
END $$;
REVOKE ALL ON FUNCTION anvil.pilot_dispatch_capacity() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.pilot_dispatch_capacity() TO anvil_app;
INSERT INTO anvil.schema_versions(version) VALUES(74);
