CREATE TABLE anvil.interactive_sessions (
 project_id uuid NOT NULL, episode_id uuid PRIMARY KEY,
 environment_version text NOT NULL CHECK(environment_version='MKT-LH-001/1.0'),
 harness_version text NOT NULL, state jsonb NOT NULL, step integer NOT NULL DEFAULT 1 CHECK(step BETWEEN 1 AND 14),
 FOREIGN KEY(project_id,episode_id) REFERENCES anvil.episodes(project_id,id)
);
CREATE TABLE anvil.interactive_calls (
 project_id uuid NOT NULL, episode_id uuid NOT NULL, step integer NOT NULL CHECK(step BETWEEN 1 AND 13),
 operation_key text NOT NULL UNIQUE, reservation_id uuid NOT NULL REFERENCES anvil.budget_reservations(id),
 request_text text NOT NULL, request_sha256 char(64) NOT NULL, state_before_sha256 char(64) NOT NULL,
 status text NOT NULL DEFAULT 'dispatching' CHECK(status IN ('dispatching','captured','applied','execution_unknown','rejected')),
 result jsonb, state_after_sha256 char(64), receipt jsonb, error_code text,
 started_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
 PRIMARY KEY(episode_id,step),
 FOREIGN KEY(project_id,episode_id) REFERENCES anvil.episodes(project_id,id)
);
CREATE FUNCTION anvil.immutable_interactive_call() RETURNS trigger LANGUAGE plpgsql AS $$
 BEGIN
 IF ROW(NEW.project_id,NEW.episode_id,NEW.step,NEW.operation_key,NEW.reservation_id,NEW.request_text,NEW.request_sha256,NEW.state_before_sha256,NEW.started_at)
 IS DISTINCT FROM ROW(OLD.project_id,OLD.episode_id,OLD.step,OLD.operation_key,OLD.reservation_id,OLD.request_text,OLD.request_sha256,OLD.state_before_sha256,OLD.started_at)
 OR (OLD.result IS NOT NULL AND NEW.result IS DISTINCT FROM OLD.result)
 OR (OLD.status IN ('applied','rejected','execution_unknown') AND NEW IS DISTINCT FROM OLD) THEN
 RAISE EXCEPTION 'immutable interactive evidence'; END IF;
 RETURN NEW;
 END $$;
CREATE TRIGGER immutable_interactive_call BEFORE UPDATE ON anvil.interactive_calls FOR EACH ROW EXECUTE FUNCTION anvil.immutable_interactive_call();
CREATE UNIQUE INDEX marketing_single_spend_authority ON anvil.evaluation_spend_windows(authority_reference)
 WHERE authority_reference='user-2026-09-28-openai-gpt-6-sol-marketing-100-usd';
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['interactive_sessions','interactive_calls'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY project_scope ON anvil.%I USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id))',t);
 EXECUTE format('CREATE INDEX ON anvil.%I(project_id)',t);
 EXECUTE format('GRANT SELECT,INSERT,UPDATE ON anvil.%I TO anvil_app,anvil_worker',t);
 END LOOP;
END $$;
INSERT INTO anvil.schema_versions(version) VALUES(15);
