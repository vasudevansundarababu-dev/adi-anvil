-- Local human attestations, never authenticated Authoring API publication.
CREATE TABLE anvil.praxis_offline_publication_subjects(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,template_id uuid NOT NULL,created_by uuid NOT NULL REFERENCES anvil.users(id),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),raw_record_utf8 text NOT NULL CHECK(octet_length(raw_record_utf8) BETWEEN 2 AND 131072),
 body_canonical text NOT NULL CHECK(octet_length(body_canonical) BETWEEN 2 AND 262144),
 content_sha256 text NOT NULL CHECK(content_sha256=encode(sha256(convert_to(body_canonical,'UTF8')),'hex')),
 UNIQUE(project_id,id),UNIQUE(project_id,content_sha256),
 FOREIGN KEY(project_id,template_id) REFERENCES anvil.praxis_template_versions(project_id,id));
CREATE TABLE anvil.praxis_offline_publication_attestations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,subject_id uuid NOT NULL,created_by uuid NOT NULL REFERENCES anvil.users(id),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),expires_at timestamptz NOT NULL,self_approved boolean NOT NULL,
 body_canonical text NOT NULL CHECK(octet_length(body_canonical) BETWEEN 2 AND 16384),
 content_sha256 text NOT NULL CHECK(content_sha256=encode(sha256(convert_to(body_canonical,'UTF8')),'hex')),
 UNIQUE(project_id,id),FOREIGN KEY(project_id,subject_id) REFERENCES anvil.praxis_offline_publication_subjects(project_id,id));
CREATE TABLE anvil.praxis_offline_publication_revocations(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,subject_id uuid NOT NULL,created_by uuid NOT NULL REFERENCES anvil.users(id),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),reason text NOT NULL CHECK(length(reason) BETWEEN 10 AND 2000),
 UNIQUE(project_id,subject_id),FOREIGN KEY(project_id,subject_id) REFERENCES anvil.praxis_offline_publication_subjects(project_id,id));
GRANT EXECUTE ON FUNCTION banking.runtime_scope(uuid) TO anvil_kyc_context_owner;
DO $$ DECLARE t text;BEGIN
 FOREACH t IN ARRAY ARRAY['praxis_offline_publication_subjects','praxis_offline_publication_attestations','praxis_offline_publication_revocations'] LOOP
  EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON anvil.%I FROM PUBLIC,anvil_worker',t);
  EXECUTE format('GRANT SELECT,INSERT ON anvil.%I TO anvil_app',t);
  EXECUTE format('GRANT SELECT ON anvil.%I TO anvil_kyc_qualifier,anvil_golden_scheduler,anvil_golden_grader,anvil_kyc_context_owner',t);
  EXECUTE format('CREATE POLICY app_read ON anvil.%I FOR SELECT TO anvil_app USING(anvil.golden_engineer(project_id))',t);
  EXECUTE format('CREATE POLICY app_append ON anvil.%I FOR INSERT TO anvil_app WITH CHECK(created_by::text=current_setting(''anvil.user'',true) AND anvil.benchmark_is_admin(project_id,created_by))',t);
  EXECUTE format('CREATE POLICY qualifier_read ON anvil.%I FOR SELECT TO anvil_kyc_qualifier USING(anvil.kyc_policy_operator_scope(project_id))',t);
  EXECUTE format('CREATE POLICY runtime_read ON anvil.%I FOR SELECT TO anvil_golden_scheduler,anvil_golden_grader,anvil_kyc_context_owner USING(banking.runtime_scope(project_id))',t);
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
  EXECUTE format('CREATE TRIGGER no_truncate BEFORE TRUNCATE ON anvil.%I FOR EACH STATEMENT EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
END $$;
CREATE FUNCTION anvil.check_offline_publication() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER
SET search_path=pg_catalog,pg_temp AS $$
DECLARE b jsonb;s anvil.praxis_offline_publication_subjects;t anvil.praxis_template_versions;n integer;BEGIN
 PERFORM id FROM anvil.projects WHERE id=NEW.project_id FOR UPDATE;
 IF TG_TABLE_NAME='praxis_offline_publication_subjects' THEN
  b=NEW.body_canonical::jsonb;
  SELECT * INTO t FROM anvil.praxis_template_versions WHERE project_id=NEW.project_id AND id=NEW.template_id;
  IF t.id IS NULL OR b->>'schema_version' IS DISTINCT FROM 'anvil.offline-publication-subject.v1'
   OR b->>'template_id' IS DISTINCT FROM t.id::text OR b->>'template_sha256' IS DISTINCT FROM t.spec_sha256
   OR b->'part_hashes' IS DISTINCT FROM t.part_hashes OR b->'record' IS DISTINCT FROM NEW.raw_record_utf8::jsonb
   OR b->>'raw_record_sha256' IS DISTINCT FROM encode(sha256(convert_to(NEW.raw_record_utf8,'UTF8')),'hex')
   OR NOT ((b->'record') ?| ARRAY['status','publication_status'])
   OR ((b->'record') ? 'status' AND b#>>'{record,status}' IS DISTINCT FROM 'published')
   OR ((b->'record') ? 'publication_status' AND b#>>'{record,publication_status}' IS DISTINCT FROM 'published')
   OR b#>>'{record,template_id}' IS DISTINCT FROM t.template_key
   OR b#>'{record,version}' IS DISTINCT FROM to_jsonb(t.version)
   OR b#>>'{record,published_at}' IS NULL
   OR b#>>'{record,published_at}'!~'(Z|[+-][0-9]{2}:[0-9]{2})$'
   OR (b#>>'{record,published_at}')::timestamptz>clock_timestamp()
   OR b#>>'{record,template_sha256}' IS DISTINCT FROM t.spec_sha256 OR b#>'{record,part_hashes}' IS DISTINCT FROM t.part_hashes
  THEN RAISE EXCEPTION 'published exact offline record and registered template required';END IF;
 ELSIF TG_TABLE_NAME='praxis_offline_publication_attestations' THEN
  b=NEW.body_canonical::jsonb;
  SELECT * INTO s FROM anvil.praxis_offline_publication_subjects WHERE project_id=NEW.project_id AND id=NEW.subject_id;
  SELECT count(*) INTO n FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id
   WHERE m.project_id=NEW.project_id AND m.role='admin' AND m.active AND u.active;
  IF s.id IS NULL OR NOT anvil.benchmark_is_admin(NEW.project_id,NEW.created_by)
   OR EXISTS(SELECT 1 FROM anvil.praxis_offline_publication_revocations r WHERE r.project_id=NEW.project_id AND r.subject_id=s.id)
   OR b->>'schema_version' IS DISTINCT FROM 'anvil.po-offline-publication-attestation.v1'
   OR b->>'origin' IS DISTINCT FROM 'po_attested_offline' OR b->'publication_verified' IS DISTINCT FROM 'false'::jsonb
   OR b->>'id' IS DISTINCT FROM NEW.id::text OR b->>'project_id' IS DISTINCT FROM NEW.project_id::text
   OR b->>'subject_id' IS DISTINCT FROM s.id::text OR b->>'subject_sha256' IS DISTINCT FROM s.content_sha256
   OR b->>'template_id' IS DISTINCT FROM s.template_id::text OR b->>'attested_by' IS DISTINCT FROM NEW.created_by::text
   OR length(coalesce(b->>'rationale','')) NOT BETWEEN 10 AND 2000
   OR b->>'expires_at' IS NULL OR b->>'expires_at'!~'(Z|[+-][0-9]{2}:[0-9]{2})$'
   OR (b->>'expires_at')::timestamptz IS DISTINCT FROM NEW.expires_at OR NEW.expires_at<=clock_timestamp()
   OR NEW.self_approved IS DISTINCT FROM (s.created_by=NEW.created_by)
   OR b->'self_approved' IS DISTINCT FROM to_jsonb(NEW.self_approved) OR NEW.self_approved AND n<>1
  THEN RAISE EXCEPTION 'explicit current exact PO attestation required';END IF;
 END IF;
 RETURN NEW;END $$;
REVOKE ALL ON FUNCTION anvil.check_offline_publication() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.check_offline_publication() TO anvil_app;
CREATE TRIGGER exact_subject BEFORE INSERT ON anvil.praxis_offline_publication_subjects FOR EACH ROW EXECUTE FUNCTION anvil.check_offline_publication();
CREATE TRIGGER exact_attestation BEFORE INSERT ON anvil.praxis_offline_publication_attestations FOR EACH ROW EXECUTE FUNCTION anvil.check_offline_publication();
CREATE TRIGGER serialize_revocation BEFORE INSERT ON anvil.praxis_offline_publication_revocations FOR EACH ROW EXECUTE FUNCTION anvil.check_offline_publication();

CREATE FUNCTION anvil.offline_publication_current(p uuid,t uuid,a uuid,h text) RETURNS boolean LANGUAGE sql STABLE SECURITY INVOKER
SET search_path=pg_catalog,pg_temp AS $$
 SELECT EXISTS(SELECT 1 FROM anvil.praxis_offline_publication_attestations x
 JOIN anvil.praxis_offline_publication_subjects s ON s.project_id=x.project_id AND s.id=x.subject_id
 WHERE x.project_id=p AND s.template_id=t AND x.id=a AND x.content_sha256=h AND x.expires_at>statement_timestamp()
 AND anvil.benchmark_is_admin(p,x.created_by)
 AND NOT EXISTS(SELECT 1 FROM anvil.praxis_offline_publication_revocations r WHERE r.project_id=p AND r.subject_id=s.id))
$$;
CREATE FUNCTION anvil.template_publication_current(p uuid,t uuid,b jsonb) RETURNS boolean LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path=pg_catalog,pg_temp AS $$ DECLARE basis jsonb=b->'publication_basis';BEGIN
 -- Legacy API-qualified receipts retain their original meaning; offline never sets this flag.
 IF b->'publication_verified'='true'::jsonb THEN RETURN true;END IF;
 IF b->'publication_verified' IS DISTINCT FROM 'false'::jsonb OR b->'publication_accepted' IS DISTINCT FROM 'true'::jsonb
 OR basis->>'kind' IS DISTINCT FROM 'po_attested_offline' THEN RETURN false;END IF;
 RETURN EXISTS(SELECT 1 FROM anvil.praxis_offline_publication_attestations a
 JOIN anvil.praxis_offline_publication_subjects s ON s.project_id=a.project_id AND s.id=a.subject_id
 WHERE a.project_id=p AND s.template_id=t AND a.id::text=basis->>'attestation_id'
 AND a.content_sha256=basis->>'attestation_sha256' AND s.id::text=basis->>'subject_id'
 AND s.content_sha256=basis->>'subject_sha256' AND a.expires_at=(basis->>'expires_at')::timestamptz
 AND anvil.offline_publication_current(p,t,a.id,a.content_sha256));
END $$;
REVOKE ALL ON FUNCTION anvil.offline_publication_current(uuid,uuid,uuid,text),anvil.template_publication_current(uuid,uuid,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.offline_publication_current(uuid,uuid,uuid,text),anvil.template_publication_current(uuid,uuid,jsonb),anvil.benchmark_is_admin(uuid,uuid)
 TO anvil_app,anvil_kyc_qualifier,anvil_golden_scheduler,anvil_golden_grader,anvil_kyc_context_owner;
-- Extend the existing source-custody predicates rather than replace them.
DO $$ DECLARE f text;body text;BEGIN
 FOREACH f IN ARRAY ARRAY['anvil.check_kyc_resolved_input_scope()','anvil.check_kyc_policy_qualification_scope()',
                          'banking.product_policy_trial_binding(uuid,integer)'] LOOP
  SELECT pg_get_functiondef(f::regprocedure) INTO body;
  IF strpos(body,'q.status=''qualified''')=0 THEN RAISE EXCEPTION 'exact original template qualification guard required';END IF;
  EXECUTE replace(body,'q.status=''qualified''','q.status=''qualified'' AND anvil.template_publication_current(q.project_id,q.template_id,q.receipt)');
 END LOOP;
END $$;
INSERT INTO anvil.schema_versions(version) VALUES(130);
