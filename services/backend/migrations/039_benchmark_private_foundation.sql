-- Roles are cluster-global, while each independently migrated database owns
-- its own schema. Reuse only the exact restricted role; never silently repair
-- an existing broader principal or alter another database's grants.
DO $$ DECLARE evaluator pg_roles%ROWTYPE; BEGIN
 BEGIN
  CREATE ROLE anvil_benchmark_evaluator NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION;
 EXCEPTION WHEN duplicate_object OR unique_violation THEN NULL;
 END;
 SELECT * INTO STRICT evaluator FROM pg_roles WHERE rolname='anvil_benchmark_evaluator';
 IF evaluator.rolcanlogin OR evaluator.rolsuper OR evaluator.rolbypassrls
 OR evaluator.rolcreatedb OR evaluator.rolcreaterole OR evaluator.rolinherit
 OR evaluator.rolreplication OR EXISTS(SELECT 1 FROM pg_auth_members WHERE member=evaluator.oid)
 THEN RAISE EXCEPTION 'existing benchmark evaluator role is not the required restricted principal'; END IF;
END $$;
GRANT USAGE ON SCHEMA anvil TO anvil_benchmark_evaluator;

ALTER TABLE anvil.artifacts DROP CONSTRAINT artifacts_classification_check;
ALTER TABLE anvil.artifacts ADD CONSTRAINT artifacts_classification_check CHECK(classification IN
 ('actor','hidden_reference','internal','approved_delivery','benchmark_raw','benchmark_eval','benchmark_judge','benchmark_trace','benchmark_output'));
CREATE UNIQUE INDEX benchmark_content_identity ON anvil.artifacts(project_id,classification,sha256)
 WHERE classification IN ('benchmark_raw','benchmark_eval','benchmark_judge','benchmark_trace');

CREATE TABLE anvil.benchmark_private_assignments (
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 user_id uuid NOT NULL REFERENCES anvil.users(id),scope text NOT NULL CHECK(scope IN ('source_review','evaluation_review')),
 artifact_id uuid,granted_by uuid NOT NULL REFERENCES anvil.users(id),
 expires_at timestamptz NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),FOREIGN KEY(project_id,artifact_id) REFERENCES anvil.artifacts(project_id,id),
 CHECK(expires_at>created_at)
);
CREATE INDEX ON anvil.benchmark_private_assignments(project_id,user_id,expires_at);
CREATE TABLE anvil.benchmark_private_revocations (
 project_id uuid NOT NULL,assignment_id uuid PRIMARY KEY,revoked_by uuid NOT NULL REFERENCES anvil.users(id),
 rationale text NOT NULL CHECK(length(rationale) BETWEEN 1 AND 2000),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,assignment_id) REFERENCES anvil.benchmark_private_assignments(project_id,id)
);
CREATE TABLE anvil.benchmark_bundle_receipts (
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),
 exporter text NOT NULL CHECK(length(exporter) BETWEEN 1 AND 80),bank_id text NOT NULL CHECK(length(bank_id) BETWEEN 1 AND 80),
 bank_version text NOT NULL CHECK(length(bank_version) BETWEEN 1 AND 80),archive_artifact_id uuid NOT NULL,
 archive_sha256 text NOT NULL CHECK(archive_sha256~'^[a-f0-9]{64}$'),
 manifest_sha256 text NOT NULL CHECK(manifest_sha256~'^[a-f0-9]{64}$'),
 raw_manifest_artifact_id uuid,canonical_manifest_artifact_id uuid,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),UNIQUE(project_id,exporter,bank_id,bank_version),
 FOREIGN KEY(project_id,archive_artifact_id) REFERENCES anvil.artifacts(project_id,id),
 FOREIGN KEY(project_id,raw_manifest_artifact_id) REFERENCES anvil.artifacts(project_id,id),
 FOREIGN KEY(project_id,canonical_manifest_artifact_id) REFERENCES anvil.artifacts(project_id,id)
);
CREATE INDEX ON anvil.benchmark_bundle_receipts(project_id,created_at,id);
CREATE TABLE anvil.benchmark_receipt_events (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,receipt_id uuid NOT NULL,event_seq bigint GENERATED ALWAYS AS IDENTITY,
 source_state text NOT NULL CHECK(source_state IN ('received','validating','quarantined','accepted','superseded')),
 signature_status text NOT NULL CHECK(signature_status IN ('verified','unsigned','unknown_signer','expired_signer','revoked_signer','invalid')),
 safe_code text NOT NULL CHECK(safe_code~'^[a-z][a-z0-9_]{0,79}$'),subject_sha256 text NOT NULL CHECK(subject_sha256~'^[a-f0-9]{64}$'),
 actor_id uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),FOREIGN KEY(project_id,receipt_id) REFERENCES anvil.benchmark_bundle_receipts(project_id,id)
);
CREATE INDEX ON anvil.benchmark_receipt_events(project_id,receipt_id,event_seq);
CREATE TABLE anvil.benchmark_evaluator_bindings (
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),registry_id text NOT NULL,version text NOT NULL,
 implementation_sha256 text NOT NULL CHECK(implementation_sha256~'^[a-f0-9]{64}$'),
 image_digest text NOT NULL CHECK(image_digest~'^sha256:[a-f0-9]{64}$'),
 policy_sha256 text NOT NULL CHECK(policy_sha256~'^[a-f0-9]{64}$'),
 reviewed_by uuid NOT NULL REFERENCES anvil.users(id),review_evidence_sha256 text NOT NULL CHECK(review_evidence_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(project_id,id),
 UNIQUE(project_id,registry_id,version,implementation_sha256,image_digest,policy_sha256)
);
CREATE TABLE anvil.benchmark_evaluator_jobs (
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),binding_id uuid NOT NULL,
 sealed_output_artifact_id uuid NOT NULL,created_by uuid NOT NULL REFERENCES anvil.users(id),
 state text NOT NULL CHECK(state IN ('queued','leased','finished','failed')),
 lease_token uuid,lease_until timestamptz,created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),FOREIGN KEY(project_id,binding_id) REFERENCES anvil.benchmark_evaluator_bindings(project_id,id),
 FOREIGN KEY(project_id,sealed_output_artifact_id) REFERENCES anvil.artifacts(project_id,id),
 CHECK(state<>'leased' OR (lease_token IS NOT NULL AND lease_until IS NOT NULL))
);
CREATE INDEX ON anvil.benchmark_evaluator_jobs(project_id,state,lease_until,id);
CREATE TABLE anvil.benchmark_evaluator_job_inputs (
 project_id uuid NOT NULL,job_id uuid NOT NULL,artifact_id uuid NOT NULL,
 artifact_sha256 text NOT NULL CHECK(artifact_sha256~'^[a-f0-9]{64}$'),
 PRIMARY KEY(project_id,job_id,artifact_id),
 FOREIGN KEY(project_id,job_id) REFERENCES anvil.benchmark_evaluator_jobs(project_id,id),
 FOREIGN KEY(project_id,artifact_id) REFERENCES anvil.artifacts(project_id,id)
);

CREATE FUNCTION anvil.benchmark_is_admin(p uuid,u uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
 SELECT p=nullif(current_setting('anvil.project',true),'')::uuid AND EXISTS(
 SELECT 1 FROM anvil.memberships m JOIN anvil.users v ON v.id=m.user_id
 WHERE m.project_id=p AND m.user_id=u AND m.active AND v.active AND m.role='admin') $$;
CREATE FUNCTION anvil.benchmark_job_scope(p uuid,j uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
 SELECT p=nullif(current_setting('anvil.project',true),'')::uuid
 AND j=nullif(current_setting('anvil.benchmark_job',true),'')::uuid AND EXISTS(
 SELECT 1 FROM anvil.benchmark_evaluator_jobs e JOIN anvil.memberships m ON m.project_id=e.project_id AND m.user_id=e.created_by
 JOIN anvil.users u ON u.id=m.user_id WHERE e.project_id=p AND e.id=j AND e.state='leased'
 AND e.lease_token=nullif(current_setting('anvil.benchmark_fence',true),'')::uuid
 AND e.lease_until>now() AND m.active AND u.active) $$;
CREATE FUNCTION anvil.benchmark_private_access(p uuid,cl text,a uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
 SELECT p=nullif(current_setting('anvil.project',true),'')::uuid AND CASE
 WHEN coalesce(nullif(current_setting('role',true),'none'),session_user::text)='anvil_app' THEN EXISTS(
 SELECT 1 FROM anvil.benchmark_private_assignments g JOIN anvil.memberships m ON m.project_id=g.project_id AND m.user_id=g.user_id
 JOIN anvil.users u ON u.id=m.user_id WHERE g.project_id=p AND g.user_id=nullif(current_setting('anvil.user',true),'')::uuid
 AND m.active AND u.active AND g.expires_at>now() AND (g.artifact_id IS NULL OR g.artifact_id=a)
 AND (g.scope='evaluation_review' OR cl IN ('benchmark_raw','benchmark_eval'))
 AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_private_revocations r WHERE r.assignment_id=g.id AND r.project_id=p))
 WHEN coalesce(nullif(current_setting('role',true),'none'),session_user::text)='anvil_benchmark_evaluator' THEN EXISTS(
 SELECT 1 FROM anvil.benchmark_evaluator_job_inputs i WHERE i.project_id=p AND i.artifact_id=a AND anvil.benchmark_job_scope(p,i.job_id))
 ELSE false END $$;
REVOKE ALL ON FUNCTION anvil.benchmark_is_admin(uuid,uuid),anvil.benchmark_job_scope(uuid,uuid),anvil.benchmark_private_access(uuid,text,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.benchmark_is_admin(uuid,uuid),anvil.benchmark_job_scope(uuid,uuid),anvil.benchmark_private_access(uuid,text,uuid) TO anvil_app,anvil_worker,anvil_benchmark_evaluator;

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['benchmark_private_assignments','benchmark_private_revocations','benchmark_bundle_receipts','benchmark_receipt_events','benchmark_evaluator_bindings','benchmark_evaluator_jobs','benchmark_evaluator_job_inputs'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY project_scope ON anvil.%I USING(CASE WHEN current_user=''anvil_benchmark_evaluator'' THEN false ELSE anvil.in_scope(project_id) END) WITH CHECK(CASE WHEN current_user=''anvil_benchmark_evaluator'' THEN false ELSE anvil.in_scope(project_id) END)',t);
 EXECUTE format('CREATE INDEX ON anvil.%I(project_id)',t);
 EXECUTE format('GRANT SELECT,INSERT ON anvil.%I TO anvil_app',t);
 IF t<>'benchmark_evaluator_jobs' THEN
 EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END IF;
 END LOOP;
END $$;
CREATE POLICY assignment_admin ON anvil.benchmark_private_assignments AS RESTRICTIVE FOR INSERT WITH CHECK(
 granted_by=nullif(current_setting('anvil.user',true),'')::uuid AND anvil.benchmark_is_admin(project_id,granted_by));
CREATE POLICY revocation_admin ON anvil.benchmark_private_revocations AS RESTRICTIVE FOR INSERT WITH CHECK(
 revoked_by=nullif(current_setting('anvil.user',true),'')::uuid AND anvil.benchmark_is_admin(project_id,revoked_by));
CREATE POLICY binding_admin ON anvil.benchmark_evaluator_bindings AS RESTRICTIVE FOR INSERT WITH CHECK(
 reviewed_by=nullif(current_setting('anvil.user',true),'')::uuid AND anvil.benchmark_is_admin(project_id,reviewed_by));
CREATE POLICY receipt_author ON anvil.benchmark_bundle_receipts AS RESTRICTIVE FOR INSERT WITH CHECK(created_by=nullif(current_setting('anvil.user',true),'')::uuid);
CREATE POLICY receipt_event_author ON anvil.benchmark_receipt_events AS RESTRICTIVE FOR INSERT WITH CHECK(actor_id=nullif(current_setting('anvil.user',true),'')::uuid);

ALTER POLICY project_scope ON anvil.artifacts USING(CASE WHEN current_user='anvil_benchmark_evaluator' THEN false ELSE anvil.in_scope(project_id) END) WITH CHECK(CASE WHEN current_user='anvil_benchmark_evaluator' THEN false ELSE anvil.in_scope(project_id) END);
CREATE POLICY benchmark_private_isolation ON anvil.artifacts AS RESTRICTIVE USING(
 classification NOT IN ('benchmark_raw','benchmark_eval','benchmark_judge','benchmark_trace')
 OR anvil.benchmark_private_access(project_id,classification,id)) WITH CHECK(
 classification NOT IN ('benchmark_raw','benchmark_eval','benchmark_judge','benchmark_trace')
 OR anvil.benchmark_private_access(project_id,classification,id));
CREATE POLICY evaluator_artifact_scope ON anvil.artifacts USING(
 current_user='anvil_benchmark_evaluator' AND anvil.benchmark_private_access(project_id,classification,id));
CREATE POLICY evaluator_job_scope ON anvil.benchmark_evaluator_jobs USING(
 current_user='anvil_benchmark_evaluator' AND anvil.benchmark_job_scope(project_id,id));
CREATE POLICY evaluator_input_scope ON anvil.benchmark_evaluator_job_inputs USING(
 current_user='anvil_benchmark_evaluator' AND anvil.benchmark_job_scope(project_id,job_id));
GRANT SELECT ON anvil.artifacts,anvil.benchmark_evaluator_jobs,anvil.benchmark_evaluator_job_inputs TO anvil_benchmark_evaluator;

CREATE FUNCTION anvil.guard_benchmark_artifact() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF OLD.classification IN ('benchmark_raw','benchmark_eval','benchmark_judge','benchmark_trace','benchmark_output')
 OR (TG_OP='UPDATE' AND NEW.classification IN ('benchmark_raw','benchmark_eval','benchmark_judge','benchmark_trace','benchmark_output'))
 THEN RAISE EXCEPTION 'immutable benchmark artifact'; END IF;
 IF TG_OP='DELETE' THEN RETURN OLD; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER benchmark_immutable BEFORE UPDATE OR DELETE ON anvil.artifacts FOR EACH ROW EXECUTE FUNCTION anvil.guard_benchmark_artifact();
CREATE FUNCTION anvil.guard_benchmark_receipt() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM anvil.artifacts a WHERE a.project_id=NEW.project_id AND a.id=NEW.archive_artifact_id
 AND a.classification='benchmark_raw' AND a.sha256=NEW.archive_sha256) THEN RAISE EXCEPTION 'invalid private source binding'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER benchmark_receipt_binding BEFORE INSERT ON anvil.benchmark_bundle_receipts FOR EACH ROW EXECUTE FUNCTION anvil.guard_benchmark_receipt();
CREATE FUNCTION anvil.guard_benchmark_input() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM anvil.artifacts a WHERE a.project_id=NEW.project_id AND a.id=NEW.artifact_id
 AND a.sha256=NEW.artifact_sha256 AND a.classification IN ('benchmark_eval','benchmark_judge','benchmark_trace','benchmark_output'))
 THEN RAISE EXCEPTION 'invalid evaluator input binding'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER benchmark_input_binding BEFORE INSERT ON anvil.benchmark_evaluator_job_inputs FOR EACH ROW EXECUTE FUNCTION anvil.guard_benchmark_input();
CREATE FUNCTION anvil.guard_benchmark_evaluator_job() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='DELETE' OR ROW(NEW.id,NEW.project_id,NEW.binding_id,NEW.sealed_output_artifact_id,NEW.created_by,NEW.created_at)
 IS DISTINCT FROM ROW(OLD.id,OLD.project_id,OLD.binding_id,OLD.sealed_output_artifact_id,OLD.created_by,OLD.created_at)
 OR OLD.state IN ('finished','failed') THEN RAISE EXCEPTION 'immutable evaluator job binding'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER benchmark_job_binding BEFORE UPDATE OR DELETE ON anvil.benchmark_evaluator_jobs FOR EACH ROW EXECUTE FUNCTION anvil.guard_benchmark_evaluator_job();
CREATE OR REPLACE FUNCTION anvil.claim_job() RETURNS SETOF anvil.jobs LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$ BEGIN
 RETURN QUERY UPDATE anvil.jobs SET status='leased',lease_token=gen_random_uuid(),lease_until=now()+interval '60 seconds',attempts=attempts+1
 WHERE id=(SELECT id FROM anvil.jobs WHERE kind NOT IN ('harbor_check','executable_import') AND kind NOT LIKE 'benchmark\_%' ESCAPE '\'
 AND (status='queued' OR (status='leased' AND lease_until<now())) AND attempts<3 ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *;
END $$;
INSERT INTO anvil.schema_versions(version) VALUES(39);
