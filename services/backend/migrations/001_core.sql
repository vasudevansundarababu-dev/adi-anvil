CREATE SCHEMA IF NOT EXISTS anvil;
CREATE SCHEMA IF NOT EXISTS anvil_checkpoints;
CREATE TABLE anvil.schema_versions(version int PRIMARY KEY, applied_at timestamptz DEFAULT now());
CREATE TABLE anvil.organizations(id uuid PRIMARY KEY, name text NOT NULL);
CREATE TABLE anvil.users(
 id uuid PRIMARY KEY, org_id uuid NOT NULL REFERENCES anvil.organizations(id),
 issuer text NOT NULL, subject text NOT NULL, name text NOT NULL,
 active boolean NOT NULL DEFAULT true, UNIQUE(issuer,subject), UNIQUE(org_id,id));
CREATE TABLE anvil.projects(
 id uuid PRIMARY KEY, org_id uuid NOT NULL REFERENCES anvil.organizations(id),
 name text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(org_id,id));
CREATE TABLE anvil.memberships(
 project_id uuid NOT NULL REFERENCES anvil.projects(id), user_id uuid NOT NULL REFERENCES anvil.users(id),
 role text NOT NULL CHECK(role IN ('researcher','advisor','product-owner','data-engineer','reviewer','adjudicator','sales','admin')),
 active boolean NOT NULL DEFAULT true, PRIMARY KEY(project_id,user_id,role));
CREATE TABLE anvil.sessions(
 token_hash text PRIMARY KEY, user_id uuid NOT NULL REFERENCES anvil.users(id), csrf_hash text NOT NULL,
 issued_at timestamptz NOT NULL DEFAULT now(), last_seen_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL DEFAULT now()+interval '8 hours', revoked_at timestamptz);
CREATE TABLE anvil.oidc_login_attempts(
 state_hash text PRIMARY KEY, nonce_hash text NOT NULL, verifier_cipher text NOT NULL,
 expires_at timestamptz NOT NULL DEFAULT now()+interval '5 minutes', consumed_at timestamptz);
CREATE FUNCTION anvil.in_scope(p uuid) RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT p = nullif(current_setting('anvil.project',true),'')::uuid
 AND (current_user = 'anvil_worker' OR EXISTS (
 SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id
 WHERE m.project_id=p AND m.user_id=nullif(current_setting('anvil.user',true),'')::uuid
 AND m.active AND u.active)) $$;
CREATE TABLE anvil.resources(
 id uuid PRIMARY KEY, org_id uuid NOT NULL, project_id uuid NOT NULL,
 kind text NOT NULL CHECK(kind IN ('objective','case','task','rubric','suite','protocol','finding','report','release','sales_kit','candidate')),
 lifecycle text NOT NULL DEFAULT 'draft', current_revision_id uuid,
 row_version int NOT NULL DEFAULT 1, created_by uuid NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(org_id,project_id) REFERENCES anvil.projects(org_id,id),
 FOREIGN KEY(org_id,created_by) REFERENCES anvil.users(org_id,id), UNIQUE(project_id,id));
CREATE TABLE anvil.revisions(
 id uuid PRIMARY KEY, project_id uuid NOT NULL, resource_id uuid NOT NULL,
 revision int NOT NULL CHECK(revision>0), content jsonb NOT NULL,
 content_hash char(64) NOT NULL, created_by uuid NOT NULL REFERENCES anvil.users(id),
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,resource_id) REFERENCES anvil.resources(project_id,id),
 UNIQUE(resource_id,revision), UNIQUE(project_id,id));
ALTER TABLE anvil.resources ADD FOREIGN KEY(project_id,current_revision_id) REFERENCES anvil.revisions(project_id,id);
CREATE TABLE anvil.revision_links(
 project_id uuid NOT NULL, revision_id uuid NOT NULL, target_revision_id uuid NOT NULL, relation text NOT NULL,
 PRIMARY KEY(revision_id,target_revision_id,relation),
 FOREIGN KEY(project_id,revision_id) REFERENCES anvil.revisions(project_id,id),
 FOREIGN KEY(project_id,target_revision_id) REFERENCES anvil.revisions(project_id,id));
CREATE TABLE anvil.review_decisions(
 id uuid PRIMARY KEY, project_id uuid NOT NULL, revision_id uuid NOT NULL, subject_hash char(64) NOT NULL,
 reviewer_id uuid NOT NULL REFERENCES anvil.users(id), purpose text NOT NULL,
 decision text NOT NULL CHECK(decision IN ('approve','reject','changes_requested')),
 rationale text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,revision_id) REFERENCES anvil.revisions(project_id,id),
 UNIQUE(revision_id,purpose,reviewer_id), UNIQUE(project_id,id));
CREATE TABLE anvil.artifacts(
 id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES anvil.projects(id),
 object_key text NOT NULL UNIQUE, sha256 char(64) NOT NULL, byte_size bigint NOT NULL CHECK(byte_size>=0),
 mime_type text NOT NULL, classification text NOT NULL CHECK(classification IN ('actor','hidden_reference','internal','approved_delivery')),
 scan_status text NOT NULL CHECK(scan_status IN ('quarantined','clean','rejected')),
 origin text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(project_id,id));
CREATE TABLE anvil.artifact_links(
 project_id uuid NOT NULL, revision_id uuid NOT NULL, artifact_id uuid NOT NULL, use_role text NOT NULL,
 PRIMARY KEY(revision_id,artifact_id),
 FOREIGN KEY(project_id,revision_id) REFERENCES anvil.revisions(project_id,id),
 FOREIGN KEY(project_id,artifact_id) REFERENCES anvil.artifacts(project_id,id));
CREATE TABLE anvil.rights_grants(
 id uuid PRIMARY KEY, project_id uuid NOT NULL, source_revision_id uuid NOT NULL,
 operation text NOT NULL, destination text NOT NULL, status text NOT NULL CHECK(status IN ('approved','revoked','unknown')),
 reviewed_by uuid NOT NULL REFERENCES anvil.users(id), evidence text NOT NULL,
 expires_at timestamptz, row_version int NOT NULL DEFAULT 1,
 FOREIGN KEY(project_id,source_revision_id) REFERENCES anvil.revisions(project_id,id),
 UNIQUE(source_revision_id,operation,destination));
CREATE TABLE anvil.import_receipts(
 project_id uuid NOT NULL, fixture_id text NOT NULL, version text NOT NULL, content_hash char(64) NOT NULL,
 resource_id uuid NOT NULL, PRIMARY KEY(project_id,fixture_id,version),
 FOREIGN KEY(project_id,resource_id) REFERENCES anvil.resources(project_id,id));
CREATE TABLE anvil.runs(
 id uuid PRIMARY KEY, project_id uuid NOT NULL, protocol_revision_id uuid NOT NULL,
 state text NOT NULL DEFAULT 'draft', origin text NOT NULL CHECK(origin IN ('illustrative','adi_executed','customer_reported','partner_reported')),
 created_by uuid NOT NULL REFERENCES anvil.users(id), row_version int NOT NULL DEFAULT 1,
 cancel_requested boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now(),
 actual_cost_micro_usd bigint, cost_status text NOT NULL DEFAULT 'not_applicable',
 FOREIGN KEY(project_id,protocol_revision_id) REFERENCES anvil.revisions(project_id,id), UNIQUE(project_id,id));
CREATE TABLE anvil.episodes(
 id uuid PRIMARY KEY, project_id uuid NOT NULL, run_id uuid NOT NULL, task_revision_id uuid NOT NULL,
 candidate_key text NOT NULL, state text NOT NULL DEFAULT 'queued', outcome text NOT NULL DEFAULT 'pending_review',
 output_artifact_id uuid, score numeric(5,2), critical jsonb, final_assessment_id uuid,
 thread_id uuid NOT NULL UNIQUE, graph_version text NOT NULL, invocation_count int NOT NULL DEFAULT 0,
 row_version int NOT NULL DEFAULT 1, created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,run_id) REFERENCES anvil.runs(project_id,id),
 FOREIGN KEY(project_id,task_revision_id) REFERENCES anvil.revisions(project_id,id),
 FOREIGN KEY(project_id,output_artifact_id) REFERENCES anvil.artifacts(project_id,id),
 UNIQUE(run_id,task_revision_id,candidate_key), UNIQUE(project_id,id));
CREATE TABLE anvil.assessments(
 id uuid PRIMARY KEY, project_id uuid NOT NULL, episode_id uuid NOT NULL, reviewer_id uuid NOT NULL REFERENCES anvil.users(id),
 scores jsonb NOT NULL, critical jsonb NOT NULL, evidence jsonb NOT NULL, rationale text NOT NULL,
 score numeric(5,2) NOT NULL, outcome text NOT NULL, round text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,episode_id) REFERENCES anvil.episodes(project_id,id),
 UNIQUE(episode_id,reviewer_id), UNIQUE(project_id,id));
ALTER TABLE anvil.episodes ADD FOREIGN KEY(project_id,final_assessment_id) REFERENCES anvil.assessments(project_id,id);
CREATE TABLE anvil.jobs(
 id uuid PRIMARY KEY, project_id uuid NOT NULL REFERENCES anvil.projects(id), kind text NOT NULL,
 target_id uuid NOT NULL, status text NOT NULL DEFAULT 'queued',
 lease_token uuid, lease_until timestamptz, attempts int NOT NULL DEFAULT 0,
 error_code text, operation_key text NOT NULL UNIQUE, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE anvil.idempotency(
 project_id uuid NOT NULL REFERENCES anvil.projects(id), user_id uuid NOT NULL REFERENCES anvil.users(id),
 route text NOT NULL, key text NOT NULL, body_hash char(64) NOT NULL, response jsonb NOT NULL,
 PRIMARY KEY(project_id,user_id,route,key));
CREATE TABLE anvil.audit_events(
 event_seq bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, project_id uuid NOT NULL REFERENCES anvil.projects(id),
 actor_id uuid REFERENCES anvil.users(id), action text NOT NULL, target_id uuid,
 metadata jsonb NOT NULL DEFAULT '{}', occurred_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE anvil.graph_outbox(
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, project_id uuid NOT NULL REFERENCES anvil.projects(id),
 resource_id uuid NOT NULL, status text NOT NULL DEFAULT 'pending', created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,resource_id) REFERENCES anvil.resources(project_id,id));
CREATE TABLE anvil.graph_projection_state(
 project_id uuid PRIMARY KEY REFERENCES anvil.projects(id), last_event bigint NOT NULL DEFAULT 0,
 status text NOT NULL DEFAULT 'lagging', last_success_at timestamptz);
CREATE INDEX ON anvil.resources(project_id,kind,created_at,id);
CREATE INDEX ON anvil.jobs(status,lease_until);
CREATE INDEX ON anvil.episodes(run_id,state);
CREATE FUNCTION anvil.immutable() RETURNS trigger LANGUAGE plpgsql AS $$
 BEGIN RAISE EXCEPTION 'immutable evidence: create a new revision'; END $$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['revisions','review_decisions','assessments','audit_events'] LOOP
 EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['resources','revisions','revision_links','review_decisions','artifacts','artifact_links','rights_grants','import_receipts','runs','episodes','assessments','jobs','idempotency','audit_events','graph_outbox','graph_projection_state'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY project_scope ON anvil.%I USING (anvil.in_scope(project_id)) WITH CHECK (anvil.in_scope(project_id))',t);
 EXECUTE format('CREATE INDEX ON anvil.%I(project_id)',t);
 END LOOP;
END $$;
CREATE POLICY artifact_worker_isolation ON anvil.artifacts AS RESTRICTIVE
 USING(current_user <> 'anvil_worker' OR classification <> 'hidden_reference');
CREATE POLICY revision_worker_isolation ON anvil.revisions AS RESTRICTIVE
 USING(current_user <> 'anvil_worker' OR NOT EXISTS(SELECT 1 FROM anvil.resources r WHERE r.id=resource_id AND r.kind='rubric'));
CREATE FUNCTION anvil.claim_job() RETURNS SETOF anvil.jobs LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
 BEGIN
 RETURN QUERY UPDATE anvil.jobs SET status='leased', lease_token=gen_random_uuid(),
 lease_until=now()+interval '60 seconds', attempts=attempts+1
 WHERE id=(SELECT id FROM anvil.jobs WHERE (status='queued' OR (status='leased' AND lease_until<now()))
 AND attempts<3 ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *;
 END $$;
REVOKE ALL ON FUNCTION anvil.claim_job() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.claim_job() TO anvil_worker;
GRANT USAGE ON SCHEMA anvil TO anvil_app,anvil_worker;
GRANT SELECT,INSERT,UPDATE ON ALL TABLES IN SCHEMA anvil TO anvil_app,anvil_worker;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA anvil TO anvil_app,anvil_worker;
REVOKE ALL ON anvil.sessions,anvil.oidc_login_attempts FROM anvil_worker;
REVOKE UPDATE,DELETE ON anvil.revisions,anvil.review_decisions,anvil.assessments,anvil.audit_events FROM anvil_app,anvil_worker;
REVOKE ALL ON anvil.schema_versions FROM anvil_app,anvil_worker;
GRANT SELECT ON anvil.schema_versions TO anvil_app,anvil_worker;
GRANT USAGE ON SCHEMA anvil_checkpoints TO anvil_worker;
INSERT INTO anvil.schema_versions(version) VALUES(1);
