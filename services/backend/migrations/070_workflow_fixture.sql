-- Offline conformance only. No live/native graph admission is granted here.
CREATE TABLE anvil.workflow_fixture_trials(
 id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES anvil.projects(id),
 created_by uuid NOT NULL REFERENCES anvil.users(id), binding jsonb NOT NULL,
 binding_sha256 text NOT NULL CHECK(binding_sha256 ~ '^[a-f0-9]{64}$'),
 mode text NOT NULL DEFAULT 'software_fixture' CHECK(mode='software_fixture'),
 cancel_requested boolean NOT NULL DEFAULT false,
 expires_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id));
CREATE TABLE anvil.workflow_fixture_effects(
 project_id uuid NOT NULL, trial_id uuid NOT NULL, effect_key text NOT NULL,
 request_sha256 text NOT NULL CHECK(request_sha256 ~ '^[a-f0-9]{64}$'),
 status text NOT NULL CHECK(status IN('dispatched','completed')),
 response jsonb, response_sha256 text,
 created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz,
 PRIMARY KEY(trial_id,effect_key),
 FOREIGN KEY(project_id,trial_id) REFERENCES anvil.workflow_fixture_trials(project_id,id),
 CHECK((status='dispatched' AND response IS NULL AND response_sha256 IS NULL AND completed_at IS NULL)
 OR(status='completed' AND response IS NOT NULL AND response_sha256 ~ '^[a-f0-9]{64}$' AND completed_at IS NOT NULL)));
ALTER TABLE anvil.workflow_fixture_trials ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.workflow_fixture_trials FORCE ROW LEVEL SECURITY;
ALTER TABLE anvil.workflow_fixture_effects ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.workflow_fixture_effects FORCE ROW LEVEL SECURITY;
CREATE POLICY fixture_reader ON anvil.workflow_fixture_trials FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id));
CREATE POLICY fixture_creator ON anvil.workflow_fixture_trials FOR INSERT TO anvil_app WITH CHECK(anvil.golden_engineer(project_id) AND created_by=nullif(current_setting('anvil.user',true),'')::uuid);
CREATE POLICY fixture_worker ON anvil.workflow_fixture_trials TO anvil_worker USING(anvil.in_scope(project_id));
CREATE POLICY fixture_effect_reader ON anvil.workflow_fixture_effects FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id));
CREATE POLICY fixture_effect_worker ON anvil.workflow_fixture_effects TO anvil_worker USING(anvil.in_scope(project_id));
GRANT SELECT,INSERT ON anvil.workflow_fixture_trials TO anvil_app;
GRANT SELECT ON anvil.workflow_fixture_effects TO anvil_app;
GRANT SELECT,UPDATE ON anvil.workflow_fixture_trials TO anvil_worker;
GRANT SELECT,INSERT,UPDATE ON anvil.workflow_fixture_effects TO anvil_worker;
CREATE FUNCTION anvil.workflow_fixture_trial_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'fixture history is retained'; END IF;
 IF (to_jsonb(OLD)-'cancel_requested') IS DISTINCT FROM (to_jsonb(NEW)-'cancel_requested')
 OR (OLD.cancel_requested AND NOT NEW.cancel_requested) THEN RAISE EXCEPTION 'immutable fixture binding'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER workflow_fixture_trial_guard BEFORE UPDATE OR DELETE ON anvil.workflow_fixture_trials FOR EACH ROW EXECUTE FUNCTION anvil.workflow_fixture_trial_guard();
CREATE FUNCTION anvil.workflow_fixture_effect_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'effect history is retained'; END IF;
 IF OLD.status<>'dispatched' OR NEW.status<>'completed'
 OR (to_jsonb(OLD)-ARRAY['status','response','response_sha256','completed_at']) IS DISTINCT FROM
 (to_jsonb(NEW)-ARRAY['status','response','response_sha256','completed_at']) THEN RAISE EXCEPTION 'immutable effect receipt'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER workflow_fixture_effect_guard BEFORE UPDATE OR DELETE ON anvil.workflow_fixture_effects FOR EACH ROW EXECUTE FUNCTION anvil.workflow_fixture_effect_guard();
INSERT INTO anvil.schema_versions(version) VALUES(70);
