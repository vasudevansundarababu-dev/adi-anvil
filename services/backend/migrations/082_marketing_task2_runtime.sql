-- Task2 private runtime state is available only to the dedicated scheduler.
-- Candidate/API/ordinary worker never receive role/controller tokens or futures.
CREATE SCHEMA marketing_runtime;
CREATE TABLE marketing_runtime.episodes(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 assigned_user uuid NOT NULL REFERENCES anvil.users(id),
 case_id text NOT NULL CHECK(case_id IN ('GT2-R01','GT2-R02')),
 dataset_id text NOT NULL,dataset_version text NOT NULL,
 dataset_sha256 text NOT NULL CHECK(dataset_sha256~'^[a-f0-9]{64}$'),
 snapshot_sha256 text NOT NULL CHECK(snapshot_sha256~'^[a-f0-9]{64}$'),
 generation integer NOT NULL CHECK(generation>=0),
 state jsonb NOT NULL CHECK(octet_length(state::text)<=16777216),
 state_sha256 text NOT NULL CHECK(state_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id));
ALTER TABLE marketing_runtime.episodes ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketing_runtime.episodes FORCE ROW LEVEL SECURITY;
CREATE POLICY scheduler_scope ON marketing_runtime.episodes TO anvil_golden_scheduler
 USING(banking.runtime_scope(project_id)) WITH CHECK(banking.runtime_scope(project_id));
GRANT USAGE ON SCHEMA marketing_runtime TO anvil_golden_scheduler,anvil_golden_grader;
GRANT SELECT,INSERT,UPDATE ON marketing_runtime.episodes TO anvil_golden_scheduler;

CREATE TABLE marketing_runtime.seals(
 project_id uuid NOT NULL,episode_id uuid NOT NULL,generation integer NOT NULL,
 capture jsonb NOT NULL,capture_sha256 text NOT NULL CHECK(capture_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(episode_id,generation),
 FOREIGN KEY(project_id,episode_id) REFERENCES marketing_runtime.episodes(project_id,id));
ALTER TABLE marketing_runtime.seals ENABLE ROW LEVEL SECURITY;
ALTER TABLE marketing_runtime.seals FORCE ROW LEVEL SECURITY;
CREATE POLICY scheduler_seal ON marketing_runtime.seals TO anvil_golden_scheduler
 USING(banking.runtime_scope(project_id)) WITH CHECK(banking.runtime_scope(project_id));
CREATE POLICY grader_seal ON marketing_runtime.seals FOR SELECT TO anvil_golden_grader
 USING(banking.runtime_scope(project_id));
GRANT SELECT,INSERT ON marketing_runtime.seals TO anvil_golden_scheduler;
GRANT SELECT ON marketing_runtime.seals TO anvil_golden_grader;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON marketing_runtime.seals
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
