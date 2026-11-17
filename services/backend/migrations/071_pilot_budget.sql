-- No policy, credential or paid activation is seeded. One retained envelope per environment.
CREATE TABLE anvil.pilot_budget_policies(
 environment text PRIMARY KEY CHECK(environment IN('qa','staging')),
 authority_sha256 text NOT NULL CHECK(authority_sha256~'^[a-f0-9]{64}$'),
 start_at timestamptz NOT NULL,end_at timestamptz NOT NULL,
 total_micro_usd bigint NOT NULL,run_micro_usd bigint NOT NULL,
 committed_micro_usd bigint NOT NULL DEFAULT 0 CHECK(committed_micro_usd>=0),
 status text NOT NULL DEFAULT 'active' CHECK(status IN('active','closed')),created_at timestamptz NOT NULL DEFAULT now(),
 CHECK(start_at>='2026-11-11T05:48:04Z' AND end_at<='2026-12-11T05:48:04Z' AND end_at>start_at AND end_at-start_at<=interval '30 days'),
 CHECK((environment='qa' AND total_micro_usd=100000000 AND run_micro_usd=2000000) OR(environment='staging' AND total_micro_usd=300000000 AND run_micro_usd=5000000)),CHECK(committed_micro_usd<=total_micro_usd));
CREATE TABLE anvil.pilot_budget_reservations(
 environment text NOT NULL REFERENCES anvil.pilot_budget_policies(environment),project_id uuid NOT NULL,
 group_id uuid PRIMARY KEY,subject_hash text NOT NULL CHECK(subject_hash~'^[a-f0-9]{64}$'),
 amount_micro_usd bigint NOT NULL CHECK(amount_micro_usd>0),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,group_id) REFERENCES anvil.workspace_execution_groups(project_id,id));
ALTER TABLE anvil.pilot_budget_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.pilot_budget_policies FORCE ROW LEVEL SECURITY;
ALTER TABLE anvil.pilot_budget_reservations ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.pilot_budget_reservations FORCE ROW LEVEL SECURITY;
CREATE POLICY cap_read ON anvil.pilot_budget_policies FOR SELECT TO anvil_app,anvil_worker USING(true);
CREATE POLICY receipt_read ON anvil.pilot_budget_reservations FOR SELECT TO anvil_app,anvil_worker USING(anvil.in_scope(project_id));
GRANT SELECT ON anvil.pilot_budget_policies,anvil.pilot_budget_reservations TO anvil_app,anvil_worker;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.pilot_budget_reservations FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE FUNCTION anvil.pilot_policy_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='DELETE' OR (to_jsonb(NEW)-ARRAY['committed_micro_usd','status']) IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['committed_micro_usd','status']) OR NEW.committed_micro_usd<OLD.committed_micro_usd OR(OLD.status='closed' AND NEW.status<>'closed') THEN RAISE EXCEPTION 'immutable retained pilot policy';END IF;RETURN NEW;END $$;
CREATE TRIGGER immutable_policy BEFORE UPDATE OR DELETE ON anvil.pilot_budget_policies FOR EACH ROW EXECUTE FUNCTION anvil.pilot_policy_guard();
CREATE FUNCTION anvil.reserve_pilot_budget(p_environment text,p_group uuid) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
DECLARE g anvil.workspace_execution_groups%ROWTYPE;p anvil.pilot_budget_policies%ROWTYPE;
 r anvil.pilot_budget_reservations%ROWTYPE;cap bigint;m jsonb;allowed jsonb;
BEGIN
 -- Lock order: own group then shared envelope, never another group.
 SELECT * INTO g FROM anvil.workspace_execution_groups WHERE id=p_group FOR UPDATE;
 IF NOT FOUND OR g.project_id IS DISTINCT FROM nullif(current_setting('anvil.project',true),'')::uuid OR NOT anvil.golden_engineer(g.project_id) THEN RAISE EXCEPTION 'scoped pilot group required';END IF;
 SELECT * INTO p FROM anvil.pilot_budget_policies WHERE environment=p_environment FOR UPDATE;
 IF NOT FOUND OR p.status<>'active' OR now()<p.start_at OR now()>=p.end_at THEN RAISE EXCEPTION 'pilot authority absent expired or closed';END IF;
 cap=(g.snapshot->'preparation'->>'aggregate_cap_micro_usd')::bigint;
 IF cap IS NULL OR cap<=0 OR cap>p.run_micro_usd THEN RAISE EXCEPTION 'pilot per-Run ceiling exceeded';END IF;
 IF NOT EXISTS(SELECT 1 FROM anvil.workspace_admin_run_authorizations a JOIN anvil.users u ON u.id=a.admin_id AND u.active JOIN anvil.memberships m ON m.project_id=a.project_id AND m.user_id=a.admin_id AND m.active AND m.role='admin' WHERE a.group_id=g.id AND a.project_id=g.project_id AND a.subject_hash=g.subject_hash AND a.cap_micro_usd=cap AND a.rights_confirmed AND a.expires_at>now() AND NOT EXISTS(SELECT 1 FROM anvil.workspace_admin_run_revocations v WHERE v.authorization_id=a.id)) THEN RAISE EXCEPTION 'current exact Admin run authority required';END IF;
 allowed=CASE p_environment WHEN 'qa' THEN '[{"provider":"openai","model_id":"gpt-6.1-sol"},{"provider":"anthropic","model_id":"claude-opus-5-5"},{"provider":"gemini","model_id":"gemini-4-argon"}]'::jsonb ELSE '[{"provider":"openai","model_id":"gpt-6.1-sol"},{"provider":"openai","model_id":"gpt-6-astra"},{"provider":"anthropic","model_id":"claude-opus-5-5"},{"provider":"anthropic","model_id":"claude-fable-5-2"},{"provider":"gemini","model_id":"gemini-4-argon"},{"provider":"gemini","model_id":"gemini-4-carbon"}]'::jsonb END;
 IF jsonb_typeof(g.snapshot->'preparation'->'models') IS DISTINCT FROM 'array' OR jsonb_array_length(g.snapshot->'preparation'->'models')=0 THEN RAISE EXCEPTION 'exact pilot models required';END IF;
 FOR m IN SELECT value FROM jsonb_array_elements(g.snapshot->'preparation'->'models') LOOP
  IF NOT allowed @> jsonb_build_array(jsonb_build_object('provider',m->>'provider','model_id',m->>'model_id')) THEN RAISE EXCEPTION 'unapproved pilot model';END IF;
 END LOOP;
 SELECT * INTO r FROM anvil.pilot_budget_reservations WHERE group_id=g.id;
 IF FOUND THEN
  IF r.environment<>p_environment OR r.project_id<>g.project_id OR r.subject_hash<>g.subject_hash OR r.amount_micro_usd<>cap THEN RAISE EXCEPTION 'pilot reservation replay differs';END IF;RETURN cap;
 END IF;
 IF p.committed_micro_usd+cap>p.total_micro_usd THEN RAISE EXCEPTION 'pilot total exhausted';END IF;
 INSERT INTO anvil.pilot_budget_reservations(environment,project_id,group_id,subject_hash,amount_micro_usd) VALUES(p_environment,g.project_id,g.id,g.subject_hash,cap);
 UPDATE anvil.pilot_budget_policies SET committed_micro_usd=committed_micro_usd+cap WHERE environment=p_environment;
 RETURN cap;
END $$;
REVOKE ALL ON FUNCTION anvil.reserve_pilot_budget(text,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.reserve_pilot_budget(text,uuid) TO anvil_app;
INSERT INTO anvil.schema_versions(version) VALUES(71);
