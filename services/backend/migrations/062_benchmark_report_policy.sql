CREATE TABLE anvil.benchmark_report_policies(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 required_reviewers integer NOT NULL CHECK(required_reviewers BETWEEN 0 AND 10),
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 rationale text NOT NULL CHECK(length(rationale) BETWEEN 10 AND 2000),UNIQUE(project_id,id));
CREATE TABLE anvil.benchmark_report_authorizations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 target_kind text NOT NULL CHECK(target_kind IN ('comparison','rehearsal')),target_id uuid NOT NULL,
 policy jsonb NOT NULL,policy_sha256 text NOT NULL CHECK(policy_sha256~'^[a-f0-9]{64}$'),
 admin_run_exempt boolean NOT NULL,actor_id uuid NOT NULL REFERENCES anvil.users(id),
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(project_id,target_kind,target_id));
CREATE TABLE anvil.benchmark_report_decisions(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 target_kind text NOT NULL CHECK(target_kind IN ('comparison','rehearsal')),target_id uuid NOT NULL,
 result_sha256 text NOT NULL CHECK(result_sha256~'^[a-f0-9]{64}$'),
 actor_id uuid NOT NULL REFERENCES anvil.users(id),assignment_id uuid,
 decision text NOT NULL CHECK(decision IN ('admin_approved','reviewed')),
 rationale text NOT NULL CHECK(length(rationale) BETWEEN 10 AND 2000),human_reviewed boolean NOT NULL CHECK(human_reviewed),
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,target_kind,target_id,result_sha256,actor_id),
 FOREIGN KEY(project_id,assignment_id) REFERENCES anvil.benchmark_private_assignments(project_id,id),
 CHECK((decision='admin_approved' AND assignment_id IS NULL) OR(decision='reviewed' AND assignment_id IS NOT NULL)));
CREATE TABLE anvil.benchmark_report_admin_executions(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 target_kind text NOT NULL CHECK(target_kind IN ('comparison','rehearsal')),target_id uuid NOT NULL,
 actor_id uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,target_kind,target_id));
DO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY['benchmark_report_policies','benchmark_report_authorizations','benchmark_report_decisions','benchmark_report_admin_executions'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY scope ON anvil.%I USING(anvil.golden_engineer(project_id)) WITH CHECK(anvil.golden_engineer(project_id))',t);
 EXECUTE format('GRANT SELECT,INSERT ON anvil.%I TO anvil_app',t);
 EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;END $$;
CREATE FUNCTION anvil.guard_report_authority() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE actor uuid; administrator boolean; result_hash text; BEGIN
 actor:=nullif(current_setting('anvil.user',true),'')::uuid;
 SELECT EXISTS(SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id AND u.active WHERE m.project_id=NEW.project_id AND m.user_id=actor AND m.active AND m.role='admin') INTO administrator;
 IF TG_TABLE_NAME='benchmark_report_policies' THEN
  IF NEW.created_by IS DISTINCT FROM actor OR NOT administrator THEN RAISE EXCEPTION 'authenticated Admin policy author required';END IF;
  RETURN NEW;
 END IF;
 IF NEW.actor_id IS DISTINCT FROM actor THEN RAISE EXCEPTION 'actual authenticated actor required';END IF;
 IF NEW.target_kind='rehearsal' THEN
  SELECT result->>'result_sha256' INTO result_hash FROM anvil.benchmark_rehearsals WHERE id=NEW.target_id AND project_id=NEW.project_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'exact rehearsal target required';END IF;
 ELSE
  PERFORM 1 FROM anvil.benchmark_comparisons WHERE run_id=NEW.target_id AND project_id=NEW.project_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'exact comparison target required';END IF;
 END IF;
 IF TG_TABLE_NAME='benchmark_report_authorizations' THEN
  IF NEW.admin_run_exempt AND NOT administrator THEN RAISE EXCEPTION 'actual Admin run required';END IF;
  IF (NEW.policy->>'required_reviewers')::integer NOT BETWEEN 0 AND 10 OR NEW.policy->>'version'<>'2' THEN RAISE EXCEPTION 'bounded frozen policy required';END IF;
  IF NEW.policy->>'policy_id' IS NULL THEN
   IF NEW.policy->>'required_reviewers'<>'1' THEN RAISE EXCEPTION 'safe default report policy required';END IF;
  ELSIF NOT EXISTS(SELECT 1 FROM anvil.benchmark_report_policies p WHERE p.id=(NEW.policy->>'policy_id')::uuid AND p.project_id=NEW.project_id AND p.required_reviewers=(NEW.policy->>'required_reviewers')::integer) THEN RAISE EXCEPTION 'exact frozen policy revision required';END IF;
 ELSIF TG_TABLE_NAME='benchmark_report_admin_executions' THEN
  IF NOT administrator OR result_hash IS NULL THEN RAISE EXCEPTION 'actual Admin completed execution required';END IF;
 ELSE
  IF NEW.target_kind='rehearsal' AND result_hash IS DISTINCT FROM NEW.result_sha256 THEN RAISE EXCEPTION 'exact stored rehearsal hash required';END IF;
  IF NEW.target_kind='comparison' AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_score_revisions WHERE run_id=NEW.target_id AND project_id=NEW.project_id AND projection_sha256=NEW.result_sha256) THEN RAISE EXCEPTION 'exact stored score revision required';END IF;
  IF NEW.decision='admin_approved' THEN
   IF NOT administrator THEN RAISE EXCEPTION 'authenticated Admin approval required';END IF;
  ELSIF NOT EXISTS(SELECT 1 FROM anvil.benchmark_private_assignments a WHERE a.project_id=NEW.project_id AND a.id=NEW.assignment_id AND a.user_id=actor AND a.scope='evaluation_review' AND a.artifact_id IS NULL AND a.expires_at>now() AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_private_revocations r WHERE r.assignment_id=a.id)) THEN RAISE EXCEPTION 'actual current human duty required';END IF;
 END IF;
 RETURN NEW;END $$;
DO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY['benchmark_report_policies','benchmark_report_authorizations','benchmark_report_decisions','benchmark_report_admin_executions'] LOOP
 EXECUTE format('CREATE TRIGGER authenticated_authority BEFORE INSERT ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.guard_report_authority()',t);
END LOOP;END $$;
INSERT INTO anvil.schema_versions(version) VALUES('062') ON CONFLICT DO NOTHING;
