-- Public review hashes and decisions; private expected answers remain disjoint.
DO $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anvil_kyc_expectation_loader') THEN
  CREATE ROLE anvil_kyc_expectation_loader NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION;
 END IF;
END $$;
DO $$ DECLARE runtime name;BEGIN
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anvil_kyc_expectation_loader'
  AND (rolcanlogin OR rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole OR rolreplication))
 THEN RAISE EXCEPTION 'restricted private expectation loader role required';END IF;
 FOREACH runtime IN ARRAY ARRAY['anvil_app','anvil_worker','anvil_golden_scheduler','anvil_golden_grader',
   'anvil_kyc_qualifier','anvil_kyc_context_owner','anvil_private_grade_owner'] LOOP
  IF pg_has_role(runtime,'anvil_kyc_expectation_loader','MEMBER')
   OR pg_has_role('anvil_kyc_expectation_loader',runtime,'MEMBER')
  THEN RAISE EXCEPTION 'disjoint private expectation loader role required';END IF;
 END LOOP;
END $$;
GRANT USAGE ON SCHEMA anvil,banking,banking_private TO anvil_kyc_expectation_loader;
-- Dedicated completed-paid-trial context: a grader has no interactive user GUC.
-- Preserve the scheduler function and derive the same immutable join graph;
-- change only its assignment guard, with an exact-definition assertion.
DO $$ DECLARE definition text;old_guard text;new_guard text;BEGIN
 definition=pg_get_functiondef('banking.product_policy_trial_binding(uuid,integer)'::regprocedure);
 old_guard='AND trial.assigned_user::text=current_setting(''anvil.user'',true)';
 new_guard='AND pg_has_role(session_user,''anvil_golden_grader'',''MEMBER'')
 AND NOT pg_has_role(session_user,''anvil_golden_scheduler'',''MEMBER'')
 AND trial.closed';
 IF (length(definition)-length(replace(definition,old_guard,'')))<>length(old_guard)
 THEN RAISE EXCEPTION 'exact scheduler context definition required';END IF;
 definition=replace(definition,'banking.product_policy_trial_binding(', 'banking.product_policy_grader_binding(');
 definition=replace(definition,old_guard,new_guard);
 EXECUTE definition;
END $$;
REVOKE ALL ON FUNCTION banking.product_policy_grader_binding(uuid,integer) FROM PUBLIC,anvil_app,anvil_worker,anvil_golden_scheduler;
GRANT EXECUTE ON FUNCTION banking.product_policy_grader_binding(uuid,integer) TO anvil_golden_grader;
GRANT CREATE ON SCHEMA banking TO anvil_kyc_context_owner;
ALTER FUNCTION banking.product_policy_grader_binding(uuid,integer) OWNER TO anvil_kyc_context_owner;
REVOKE CREATE ON SCHEMA banking FROM anvil_kyc_context_owner;
GRANT EXECUTE ON FUNCTION anvil.benchmark_is_admin(uuid,uuid),anvil.kyc_policy_operator_scope(uuid) TO anvil_kyc_expectation_loader;
GRANT SELECT ON anvil.kyc_policy_operator_principals TO anvil_kyc_expectation_loader;
ALTER POLICY own_login ON anvil.kyc_policy_operator_principals TO anvil_kyc_qualifier,anvil_kyc_expectation_loader;
GRANT SELECT ON banking.applications TO anvil_kyc_expectation_loader;
CREATE POLICY expectation_loader_read ON banking.applications FOR SELECT TO anvil_kyc_expectation_loader
 USING(anvil.kyc_policy_operator_scope(project_id));
CREATE FUNCTION anvil.lock_expectation_staging(p uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$ BEGIN
 IF p::text IS DISTINCT FROM current_setting('anvil.project',true)
 OR NOT EXISTS(SELECT 1 FROM anvil.kyc_policy_operator_principals x
  WHERE x.login_role=session_user AND x.project_id=p AND x.user_id::text=current_setting('anvil.user',true)
   AND anvil.benchmark_is_admin(p,x.user_id))
 THEN RAISE EXCEPTION 'enrolled expectation staging scope required';END IF;
 PERFORM 1 FROM anvil.projects WHERE id=p FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'project unavailable';END IF;
END $$;
REVOKE ALL ON FUNCTION anvil.lock_expectation_staging(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.lock_expectation_staging(uuid) TO anvil_kyc_expectation_loader;

CREATE TABLE anvil.kyc_expectation_subjects(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,pack_id uuid NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 body_canonical text NOT NULL CHECK(octet_length(body_canonical) BETWEEN 2 AND 2097152),
 content_sha256 text NOT NULL CHECK(content_sha256=encode(sha256(convert_to(body_canonical,'UTF8')),'hex')),
 FOREIGN KEY(project_id,pack_id) REFERENCES banking.packs(project_id,id),
 UNIQUE(project_id,id),UNIQUE(project_id,content_sha256),
 CHECK(body_canonical::jsonb->>'schema_version' IS NOT DISTINCT FROM 'anvil.kyc-expectation-review-subject.v1'),
 CHECK(body_canonical::jsonb->>'project_id' IS NOT DISTINCT FROM project_id::text),
 CHECK(body_canonical::jsonb->>'pack_id' IS NOT DISTINCT FROM pack_id::text));
CREATE TABLE banking_private.expectation_versions(
 project_id uuid NOT NULL,subject_id uuid NOT NULL,pack_id uuid NOT NULL,application_id text NOT NULL,
 snapshot_sha256 text NOT NULL CHECK(snapshot_sha256~'^[a-f0-9]{64}$'),
 body_canonical text NOT NULL CHECK(octet_length(body_canonical) BETWEEN 2 AND 131072),
 content_sha256 text NOT NULL CHECK(content_sha256=encode(sha256(convert_to(body_canonical,'UTF8')),'hex')),
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(project_id,subject_id,application_id),
 FOREIGN KEY(project_id,subject_id) REFERENCES anvil.kyc_expectation_subjects(project_id,id),
 FOREIGN KEY(project_id,pack_id,application_id) REFERENCES banking.applications(project_id,pack_id,id));
CREATE TABLE banking_private.expectation_packets(
 project_id uuid NOT NULL,subject_id uuid NOT NULL,
 body_canonical text NOT NULL CHECK(octet_length(body_canonical) BETWEEN 2 AND 16777216),
 content_sha256 text NOT NULL CHECK(content_sha256=encode(sha256(convert_to(body_canonical,'UTF8')),'hex')),
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(project_id,subject_id),FOREIGN KEY(project_id,subject_id) REFERENCES anvil.kyc_expectation_subjects(project_id,id));
CREATE TABLE anvil.kyc_expectation_review_receipts(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,subject_id uuid NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 expires_at timestamptz NOT NULL,body_canonical text NOT NULL CHECK(octet_length(body_canonical) BETWEEN 2 AND 16384),
 content_sha256 text NOT NULL CHECK(content_sha256=encode(sha256(convert_to(body_canonical,'UTF8')),'hex')),
 UNIQUE(project_id,id),FOREIGN KEY(project_id,subject_id) REFERENCES anvil.kyc_expectation_subjects(project_id,id),
 CHECK(expires_at>created_at));
CREATE TABLE anvil.kyc_expectation_review_revocations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,receipt_id uuid NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 reason text NOT NULL CHECK(length(reason) BETWEEN 10 AND 2000),UNIQUE(project_id,receipt_id),
 FOREIGN KEY(project_id,receipt_id) REFERENCES anvil.kyc_expectation_review_receipts(project_id,id));

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['kyc_expectation_subjects','kyc_expectation_review_receipts','kyc_expectation_review_revocations'] LOOP
  EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY engineer_read ON anvil.%I FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id))',t);
  EXECUTE format('CREATE POLICY grader_read ON anvil.%I FOR SELECT TO anvil_golden_grader USING(banking.runtime_scope(project_id))',t);
  EXECUTE format('CREATE POLICY loader_read ON anvil.%I FOR SELECT TO anvil_kyc_expectation_loader USING(anvil.kyc_policy_operator_scope(project_id))',t);
  EXECUTE format('GRANT SELECT ON anvil.%I TO anvil_app,anvil_golden_grader,anvil_kyc_expectation_loader',t);
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
END $$;
CREATE POLICY loader_stage ON anvil.kyc_expectation_subjects FOR INSERT TO anvil_kyc_expectation_loader
 WITH CHECK(anvil.kyc_policy_operator_scope(project_id) AND created_by::text=current_setting('anvil.user',true));
GRANT INSERT ON anvil.kyc_expectation_subjects TO anvil_kyc_expectation_loader;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['kyc_expectation_review_receipts','kyc_expectation_review_revocations'] LOOP
  EXECUTE format('CREATE POLICY po_decision ON anvil.%I FOR INSERT TO anvil_app WITH CHECK(created_by::text=current_setting(''anvil.user'',true) AND anvil.benchmark_is_admin(project_id,created_by))',t);
  EXECUTE format('GRANT INSERT ON anvil.%I TO anvil_app',t);
 END LOOP;
END $$;
ALTER TABLE banking_private.expectation_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE banking_private.expectation_versions FORCE ROW LEVEL SECURITY;
REVOKE ALL ON banking_private.expectation_versions FROM PUBLIC,anvil_app,anvil_worker,anvil_golden_scheduler,anvil_kyc_qualifier;
GRANT SELECT ON banking_private.expectation_versions TO anvil_golden_grader;
GRANT SELECT,INSERT ON banking_private.expectation_versions TO anvil_kyc_expectation_loader;
CREATE POLICY grader_read ON banking_private.expectation_versions FOR SELECT TO anvil_golden_grader USING(banking.runtime_scope(project_id));
CREATE POLICY loader_scope ON banking_private.expectation_versions TO anvil_kyc_expectation_loader
 USING(anvil.kyc_policy_operator_scope(project_id))
 WITH CHECK(anvil.kyc_policy_operator_scope(project_id) AND created_by::text=current_setting('anvil.user',true));
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON banking_private.expectation_versions
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
ALTER TABLE banking_private.expectation_packets ENABLE ROW LEVEL SECURITY;
ALTER TABLE banking_private.expectation_packets FORCE ROW LEVEL SECURITY;
REVOKE ALL ON banking_private.expectation_packets FROM PUBLIC,anvil_app,anvil_worker,anvil_golden_scheduler,anvil_kyc_qualifier;
GRANT SELECT ON banking_private.expectation_packets TO anvil_golden_grader;
GRANT SELECT,INSERT ON banking_private.expectation_packets TO anvil_kyc_expectation_loader;
CREATE POLICY grader_read ON banking_private.expectation_packets FOR SELECT TO anvil_golden_grader USING(banking.runtime_scope(project_id));
CREATE POLICY loader_scope ON banking_private.expectation_packets TO anvil_kyc_expectation_loader
 USING(anvil.kyc_policy_operator_scope(project_id))
 WITH CHECK(anvil.kyc_policy_operator_scope(project_id) AND created_by::text=current_setting('anvil.user',true));
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON banking_private.expectation_packets
 FOR EACH ROW EXECUTE FUNCTION anvil.immutable();

-- Only existence/hashes cross this definer boundary, never an expected answer.
-- The deferred check makes public review metadata and all private rows atomic.
CREATE FUNCTION banking_private.check_expectation_population() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE body jsonb; packet jsonb; n integer;BEGIN
 body=NEW.body_canonical::jsonb;
 SELECT p.body_canonical::jsonb INTO packet FROM banking_private.expectation_packets p
  WHERE p.project_id=NEW.project_id AND p.subject_id=NEW.id
   AND p.content_sha256=body->>'private_packet_sha256';
 n=jsonb_array_length(body->'cases');
 IF packet IS NULL OR packet->>'schema_version' IS DISTINCT FROM 'anvil.kyc-private-expectation-packet.v1'
 OR packet->>'project_id' IS DISTINCT FROM NEW.project_id::text OR packet->>'pack_id' IS DISTINCT FROM NEW.pack_id::text
 OR jsonb_array_length(packet->'cases') IS DISTINCT FROM n
 OR n<1 OR n>2000
 OR n<>(SELECT count(*) FROM banking.applications a WHERE a.project_id=NEW.project_id AND a.pack_id=NEW.pack_id)
 OR n<>(SELECT count(DISTINCT x->>'application_id') FROM jsonb_array_elements(body->'cases') x)
 OR n<>(SELECT count(*) FROM banking_private.expectation_versions e WHERE e.project_id=NEW.project_id AND e.subject_id=NEW.id)
 OR EXISTS(SELECT 1 FROM jsonb_array_elements(body->'cases') x
   LEFT JOIN banking.applications a ON a.project_id=NEW.project_id AND a.pack_id=NEW.pack_id AND a.id=x->>'application_id'
   LEFT JOIN banking_private.expectation_versions e ON e.project_id=NEW.project_id AND e.subject_id=NEW.id AND e.application_id=x->>'application_id'
   WHERE a.id IS NULL OR e.application_id IS NULL OR e.pack_id<>NEW.pack_id
    OR a.snapshot_sha256 IS DISTINCT FROM x->>'snapshot_sha256'
    OR e.snapshot_sha256 IS DISTINCT FROM a.snapshot_sha256
    OR e.content_sha256 IS DISTINCT FROM x->>'expectation_sha256')
 OR EXISTS(SELECT 1 FROM jsonb_array_elements(packet->'cases') q
  LEFT JOIN banking_private.expectation_versions e ON e.project_id=NEW.project_id AND e.subject_id=NEW.id AND e.application_id=q->>'application_id'
  WHERE e.application_id IS NULL OR e.snapshot_sha256 IS DISTINCT FROM q->>'snapshot_sha256'
   OR e.body_canonical::jsonb IS DISTINCT FROM jsonb_build_object('salt',q->'salt','expectation',q->'expectation')
   OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(body->'cases') x WHERE x->>'application_id'=q->>'application_id'
    AND x->'policy_subject_sha256' IS NOT DISTINCT FROM q->'policy_subject_sha256'))
 OR n<>(SELECT count(DISTINCT q->>'application_id') FROM jsonb_array_elements(packet->'cases') q)
 THEN RAISE EXCEPTION 'complete exact private expectation population required';END IF;
 RETURN NEW;END $$;
REVOKE ALL ON FUNCTION banking_private.check_expectation_population() FROM PUBLIC;
CREATE CONSTRAINT TRIGGER complete_population AFTER INSERT ON anvil.kyc_expectation_subjects
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION banking_private.check_expectation_population();
CREATE FUNCTION banking_private.check_expectation_member() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM anvil.kyc_expectation_subjects s,
   LATERAL jsonb_array_elements(s.body_canonical::jsonb->'cases') x
   WHERE s.project_id=NEW.project_id AND s.id=NEW.subject_id AND s.pack_id=NEW.pack_id
    AND x->>'application_id'=NEW.application_id AND x->>'snapshot_sha256'=NEW.snapshot_sha256
    AND x->>'expectation_sha256'=NEW.content_sha256)
 THEN RAISE EXCEPTION 'exact staged expectation membership required';END IF;
 RETURN NEW;END $$;
REVOKE ALL ON FUNCTION banking_private.check_expectation_member() FROM PUBLIC;
CREATE TRIGGER exact_member BEFORE INSERT ON banking_private.expectation_versions
 FOR EACH ROW EXECUTE FUNCTION banking_private.check_expectation_member();

-- An API client can review metadata; it can never insert private expectations or
-- stage its own self-declared reviewed population. No login/enrollment is seeded.
INSERT INTO anvil.schema_versions(version) VALUES(134);
