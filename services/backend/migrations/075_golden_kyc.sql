-- Golden KYC: additive isolated pilot. No grants to ordinary anvil_worker.
CREATE SCHEMA banking;
CREATE SCHEMA banking_private;
CREATE FUNCTION banking.runtime_scope(p uuid) RETURNS boolean LANGUAGE sql STABLE AS $$ SELECT p=nullif(current_setting('anvil.project',true),'')::uuid $$;
REVOKE ALL ON FUNCTION banking.runtime_scope(uuid) FROM PUBLIC;
REVOKE ALL ON SCHEMA banking_private FROM PUBLIC,anvil_app,anvil_worker;
GRANT USAGE ON SCHEMA banking TO anvil_app;
CREATE TABLE banking.packs(
 id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES anvil.projects(id),
 manifest jsonb NOT NULL, created_by uuid NOT NULL REFERENCES anvil.users(id),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(project_id,id));
CREATE TABLE banking.applications(
 id text NOT NULL, project_id uuid NOT NULL, pack_id uuid NOT NULL,
 snapshot jsonb NOT NULL, snapshot_sha256 text NOT NULL CHECK(snapshot_sha256~'^[a-f0-9]{64}$'),
 PRIMARY KEY(project_id,pack_id,id),
 FOREIGN KEY(project_id,pack_id) REFERENCES banking.packs(project_id,id));
CREATE TABLE banking.trials(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,pack_id uuid NOT NULL,application_id text NOT NULL,
 assigned_user uuid NOT NULL REFERENCES anvil.users(id),model_label text NOT NULL,
 repetition integer NOT NULL CHECK(repetition BETWEEN 1 AND 10),generation integer NOT NULL DEFAULT 0,
 state jsonb NOT NULL,credential_sha256 text NOT NULL,closed boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(project_id,id),
 FOREIGN KEY(project_id,pack_id,application_id) REFERENCES banking.applications(project_id,pack_id,id));
CREATE TABLE banking.events(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,trial_id uuid NOT NULL,generation integer NOT NULL,
 sequence integer NOT NULL,action text NOT NULL,record jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(trial_id,generation,sequence),
 FOREIGN KEY(project_id,trial_id) REFERENCES banking.trials(project_id,id));
CREATE TABLE banking.recommendations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,trial_id uuid NOT NULL,generation integer NOT NULL,
 content jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(trial_id,generation),
 FOREIGN KEY(project_id,trial_id) REFERENCES banking.trials(project_id,id));
CREATE TABLE banking_private.scenarios(
 project_id uuid NOT NULL,pack_id uuid NOT NULL,application_id text NOT NULL,controls jsonb NOT NULL,
 PRIMARY KEY(project_id,pack_id,application_id),
 FOREIGN KEY(project_id,pack_id,application_id) REFERENCES banking.applications(project_id,pack_id,id));
CREATE TABLE banking_private.results(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,trial_id uuid NOT NULL,generation integer NOT NULL,
 result jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(trial_id,generation),
 FOREIGN KEY(project_id,trial_id) REFERENCES banking.trials(project_id,id));
CREATE TABLE banking_private.expectations(
 project_id uuid NOT NULL,pack_id uuid NOT NULL,application_id text NOT NULL,expectation jsonb NOT NULL,
 PRIMARY KEY(project_id,pack_id,application_id),
 FOREIGN KEY(project_id,pack_id,application_id) REFERENCES banking.applications(project_id,pack_id,id));
CREATE TABLE banking.commands(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 requested_by uuid NOT NULL REFERENCES anvil.users(id),kind text NOT NULL CHECK(kind IN ('seed','trial','step','run')),
 arguments jsonb NOT NULL,idempotency_key text NOT NULL,body_sha256 text NOT NULL,
 status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','completed','denied','error')),
 result jsonb,created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,requested_by,idempotency_key));
ALTER TABLE banking.commands ENABLE ROW LEVEL SECURITY;
ALTER TABLE banking.commands FORCE ROW LEVEL SECURITY;
CREATE POLICY own_commands ON banking.commands FOR SELECT TO anvil_app USING(
 anvil.golden_engineer(project_id) AND requested_by=nullif(current_setting('anvil.user',true),'')::uuid);
CREATE POLICY own_submit ON banking.commands FOR INSERT TO anvil_app WITH CHECK(
 anvil.golden_engineer(project_id) AND requested_by=nullif(current_setting('anvil.user',true),'')::uuid
 AND status='queued' AND result IS NULL);
GRANT SELECT,INSERT ON banking.commands TO anvil_app;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['packs','applications','trials','events','recommendations'] LOOP
  EXECUTE format('ALTER TABLE banking.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE banking.%I FORCE ROW LEVEL SECURITY',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['packs','applications'] LOOP
  EXECUTE format('CREATE POLICY engineer_read ON banking.%I FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id))',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['trials','events','recommendations'] LOOP
  EXECUTE format('CREATE POLICY assigned_read ON banking.%I FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id) AND %s)',t,
   CASE WHEN t='trials' THEN 'assigned_user=nullif(current_setting(''anvil.user'',true),'''')::uuid'
   ELSE 'EXISTS(SELECT 1 FROM banking.trials x WHERE x.id=trial_id AND x.assigned_user=nullif(current_setting(''anvil.user'',true),'''')::uuid)' END);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['packs','applications','events','recommendations'] LOOP
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON banking.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['scenarios','results','expectations'] LOOP
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON banking_private.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
END $$;
GRANT SELECT ON banking.packs,banking.applications,banking.trials,banking.events,banking.recommendations TO anvil_app;
-- API submits commands only; it cannot write observed state, events or outcomes.
REVOKE ALL ON ALL TABLES IN SCHEMA banking_private FROM PUBLIC,anvil_app,anvil_worker;
-- NOLOGIN capability roles; deployment must provision distinct non-owner logins.
-- Neither role is granted to the ordinary API/worker.
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anvil_golden_scheduler') THEN
  CREATE ROLE anvil_golden_scheduler NOLOGIN NOSUPERUSER NOBYPASSRLS;
 END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anvil_golden_grader') THEN
  CREATE ROLE anvil_golden_grader NOLOGIN NOSUPERUSER NOBYPASSRLS;
 END IF;
END $$;
GRANT USAGE ON SCHEMA anvil,banking,banking_private TO anvil_golden_scheduler,anvil_golden_grader;
GRANT SELECT ON anvil.memberships,anvil.users TO anvil_golden_scheduler;
GRANT SELECT,INSERT ON banking.packs,banking.applications,banking.trials,banking.events,banking.recommendations TO anvil_golden_scheduler;
GRANT SELECT,UPDATE ON banking.commands TO anvil_golden_scheduler;
GRANT UPDATE(state,generation,credential_sha256,closed) ON banking.trials TO anvil_golden_scheduler;
GRANT SELECT,INSERT ON banking_private.scenarios TO anvil_golden_scheduler;
-- Seeding expectations uses the separate local loader, not scheduler runtime.
GRANT SELECT ON banking_private.expectations TO anvil_golden_grader;
GRANT SELECT,INSERT ON banking_private.results TO anvil_golden_grader;
GRANT SELECT ON banking.packs,banking.applications,banking.trials,banking.events,banking.recommendations TO anvil_golden_grader;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['packs','applications','trials','events','recommendations','commands'] LOOP
  EXECUTE format('CREATE POLICY scheduler_scope ON banking.%I TO anvil_golden_scheduler USING(banking.runtime_scope(project_id)) WITH CHECK(banking.runtime_scope(project_id))',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['packs','applications','trials','events','recommendations'] LOOP
  EXECUTE format('CREATE POLICY grader_scope ON banking.%I FOR SELECT TO anvil_golden_grader USING(banking.runtime_scope(project_id))',t);
 END LOOP;
END $$;
GRANT EXECUTE ON FUNCTION banking.runtime_scope(uuid) TO anvil_golden_scheduler,anvil_golden_grader;
CREATE TABLE banking.seals(
 project_id uuid NOT NULL,trial_id uuid NOT NULL,generation integer NOT NULL,
 state jsonb NOT NULL,state_sha256 text NOT NULL CHECK(state_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(trial_id,generation),
 FOREIGN KEY(project_id,trial_id) REFERENCES banking.trials(project_id,id));
CREATE TABLE banking.evaluation_summaries(
 project_id uuid NOT NULL,trial_id uuid NOT NULL,generation integer NOT NULL,
 summary jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(trial_id,generation),
 FOREIGN KEY(project_id,trial_id) REFERENCES banking.trials(project_id,id));
ALTER TABLE banking.seals ENABLE ROW LEVEL SECURITY;
ALTER TABLE banking.seals FORCE ROW LEVEL SECURITY;
ALTER TABLE banking.evaluation_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE banking.evaluation_summaries FORCE ROW LEVEL SECURITY;
CREATE POLICY scheduler_seal ON banking.seals FOR INSERT TO anvil_golden_scheduler WITH CHECK(banking.runtime_scope(project_id));
CREATE POLICY scheduler_seal_read ON banking.seals FOR SELECT TO anvil_golden_scheduler USING(banking.runtime_scope(project_id));
CREATE POLICY grader_seal ON banking.seals FOR SELECT TO anvil_golden_grader USING(banking.runtime_scope(project_id));
CREATE POLICY grader_summary ON banking.evaluation_summaries TO anvil_golden_grader USING(banking.runtime_scope(project_id)) WITH CHECK(banking.runtime_scope(project_id));
CREATE POLICY assigned_summary ON banking.evaluation_summaries FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id) AND EXISTS(SELECT 1 FROM banking.trials x WHERE x.id=trial_id AND x.assigned_user=nullif(current_setting('anvil.user',true),'')::uuid));
GRANT SELECT,INSERT ON banking.seals TO anvil_golden_scheduler;
GRANT SELECT ON banking.seals TO anvil_golden_grader;
GRANT SELECT,INSERT ON banking.evaluation_summaries TO anvil_golden_grader;
GRANT SELECT ON banking.evaluation_summaries TO anvil_app;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON banking.seals FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON banking.evaluation_summaries FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE TABLE banking.runs(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,pack_id uuid NOT NULL,created_by uuid NOT NULL,
 profile jsonb NOT NULL,profile_sha256 text NOT NULL CHECK(profile_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(project_id,id),
 FOREIGN KEY(project_id,pack_id) REFERENCES banking.packs(project_id,id));
CREATE TABLE banking.run_cells(
 project_id uuid NOT NULL,run_id uuid NOT NULL,application_id text NOT NULL,
 model_label text NOT NULL,repetition integer NOT NULL,trial_id uuid NOT NULL UNIQUE,
 PRIMARY KEY(run_id,application_id,model_label,repetition),
 FOREIGN KEY(project_id,run_id) REFERENCES banking.runs(project_id,id),
 FOREIGN KEY(project_id,trial_id) REFERENCES banking.trials(project_id,id));
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['runs','run_cells'] LOOP
  EXECUTE format('ALTER TABLE banking.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE banking.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY scheduler_scope ON banking.%I TO anvil_golden_scheduler USING(banking.runtime_scope(project_id)) WITH CHECK(banking.runtime_scope(project_id))',t);
  EXECUTE format('CREATE POLICY curator_read ON banking.%I FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id))',t);
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON banking.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
  EXECUTE format('GRANT SELECT,INSERT ON banking.%I TO anvil_golden_scheduler',t);
  EXECUTE format('GRANT SELECT ON banking.%I TO anvil_app',t);
 END LOOP;
END $$;
ALTER TABLE banking_private.scenarios ENABLE ROW LEVEL SECURITY;
ALTER TABLE banking_private.scenarios FORCE ROW LEVEL SECURITY;
ALTER TABLE banking_private.expectations ENABLE ROW LEVEL SECURITY;
ALTER TABLE banking_private.expectations FORCE ROW LEVEL SECURITY;
ALTER TABLE banking_private.results ENABLE ROW LEVEL SECURITY;
ALTER TABLE banking_private.results FORCE ROW LEVEL SECURITY;
CREATE POLICY scheduler_scope ON banking_private.scenarios TO anvil_golden_scheduler USING(banking.runtime_scope(project_id)) WITH CHECK(banking.runtime_scope(project_id));
CREATE POLICY grader_scope ON banking_private.expectations FOR SELECT TO anvil_golden_grader USING(banking.runtime_scope(project_id));
CREATE POLICY grader_scope ON banking_private.results TO anvil_golden_grader USING(banking.runtime_scope(project_id)) WITH CHECK(banking.runtime_scope(project_id));
INSERT INTO anvil.schema_versions(version) VALUES(75);
