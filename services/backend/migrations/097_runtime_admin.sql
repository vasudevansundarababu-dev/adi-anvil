-- Observation/allowlist custody belongs to the operator. Admin selects a candidate
-- only: no serving pointer, installer, job, dispatch or promotion is created.
CREATE TABLE anvil.runtime_role_allowlist(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 role text NOT NULL CHECK(role IN('api','business-worker','golden-grader','golden-scheduler','golden-native-coordinator','task-environment','isolated-python-runner')),
 image_digest text NOT NULL CHECK(image_digest~'^us-west1-docker[.]pkg[.]dev/adi-anvil-mvp-2026/anvil-qa-v1/[a-z0-9-]+@sha256:[a-f0-9]{64}$'),
 source_commit text NOT NULL CHECK(source_commit~'^[a-f0-9]{40}$'),
 lock_digest text NOT NULL CHECK(lock_digest~'^[a-f0-9]{64}$'),
 review_receipt_sha256 text NOT NULL CHECK(review_receipt_sha256~'^[a-f0-9]{64}$'),
 expires_at timestamptz NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),UNIQUE(project_id,role,image_digest,source_commit,lock_digest,id));
CREATE TABLE anvil.runtime_role_allowlist_revocations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,allowlist_id uuid NOT NULL,
 reason text NOT NULL CHECK(length(reason) BETWEEN 10 AND 1000),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,allowlist_id) REFERENCES anvil.runtime_role_allowlist(project_id,id),UNIQUE(allowlist_id));
CREATE TABLE anvil.runtime_role_observations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 role text NOT NULL CHECK(role IN('api','business-worker','golden-grader','golden-scheduler','golden-native-coordinator','task-environment','isolated-python-runner')),
 origin text NOT NULL CHECK(origin IN('local_build','isolated_image_control','observed_deployed_role')),
 evidence jsonb NOT NULL CHECK(jsonb_typeof(evidence)='object' AND octet_length(evidence::text)<=65536),
 evidence_sha256 text NOT NULL CHECK(evidence_sha256~'^[a-f0-9]{64}$'),
 verified_at timestamptz NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 CHECK(verified_at<=created_at),UNIQUE(project_id,id));
CREATE TABLE anvil.runtime_role_revocations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,observation_id uuid NOT NULL,
 reason text NOT NULL CHECK(length(reason) BETWEEN 10 AND 1000),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,observation_id) REFERENCES anvil.runtime_role_observations(project_id,id),UNIQUE(observation_id));
CREATE TABLE anvil.runtime_role_candidates(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,role text NOT NULL,
 image_digest text NOT NULL,source_commit text NOT NULL,lock_digest text NOT NULL,allowlist_id uuid NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 receipt jsonb NOT NULL CHECK(octet_length(receipt::text)<=4096 AND receipt ?& ARRAY['status','serving_changed','dispatch_authorized'] AND receipt->>'status'='staged_not_promoted' AND receipt->'serving_changed'='false'::jsonb AND receipt->'dispatch_authorized'='false'::jsonb),
 receipt_sha256 text NOT NULL CHECK(receipt_sha256~'^[a-f0-9]{64}$'),
 FOREIGN KEY(project_id,role,image_digest,source_commit,lock_digest,allowlist_id)
 REFERENCES anvil.runtime_role_allowlist(project_id,role,image_digest,source_commit,lock_digest,id),
 UNIQUE(project_id,id));
CREATE INDEX runtime_observation_latest ON anvil.runtime_role_observations(project_id,role,verified_at DESC,created_at DESC,id DESC);
CREATE INDEX runtime_candidate_latest ON anvil.runtime_role_candidates(project_id,role,created_at DESC,id DESC);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['runtime_role_allowlist','runtime_role_allowlist_revocations','runtime_role_observations','runtime_role_revocations','runtime_role_candidates'] LOOP
  EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY scoped_read ON anvil.%I FOR SELECT TO anvil_app USING(anvil.in_scope(project_id))',t);
  EXECUTE format('GRANT SELECT ON anvil.%I TO anvil_app',t);
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
END $$;
CREATE POLICY admin_stage ON anvil.runtime_role_candidates FOR INSERT TO anvil_app WITH CHECK(
 anvil.in_scope(project_id) AND created_by=nullif(current_setting('anvil.user',true),'')::uuid
 AND EXISTS(SELECT 1 FROM anvil.memberships WHERE project_id=runtime_role_candidates.project_id
 AND user_id=created_by AND active AND role='admin'));
GRANT INSERT ON anvil.runtime_role_candidates TO anvil_app;
-- No application/worker INSERT into operator evidence, no UPDATE/DELETE grants,
-- no new runtime identity, no serving changes and no seeded qualification.
INSERT INTO anvil.schema_versions(version) VALUES(97);
