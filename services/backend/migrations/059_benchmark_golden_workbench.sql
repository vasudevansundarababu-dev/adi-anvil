-- Human-curated private expected outputs; never candidate/scoring authority.
CREATE FUNCTION anvil.golden_engineer(p uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=anvil,pg_temp AS $$
 SELECT p=nullif(current_setting('anvil.project',true),'')::uuid AND EXISTS(
 SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id
 WHERE m.project_id=p AND m.user_id=nullif(current_setting('anvil.user',true),'')::uuid
 AND m.active AND u.active AND m.role IN ('admin','rl-engineer')) $$;
CREATE FUNCTION anvil.golden_source_live(p uuid,b uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=anvil,pg_temp AS $$
 SELECT anvil.golden_engineer(p) AND (b IS NULL OR EXISTS(
 SELECT 1 FROM anvil.benchmark_builds build JOIN anvil.benchmark_source_reviews r ON r.project_id=build.project_id AND r.id=build.review_id
 JOIN anvil.memberships reviewer ON reviewer.project_id=p AND reviewer.user_id=r.reviewed_by AND reviewer.active AND reviewer.role='admin'
 JOIN anvil.users ru ON ru.id=reviewer.user_id AND ru.active
 JOIN anvil.memberships author ON author.project_id=p AND author.user_id=build.created_by AND author.active
 JOIN anvil.users au ON au.id=author.user_id AND au.active
 WHERE build.id=b AND build.project_id=p AND r.rights_confirmed AND r.expires_at>now()
 AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_review_revocations x WHERE x.review_id=r.id OR
 (x.target='evaluator' AND x.review_id IN(SELECT id FROM anvil.benchmark_source_reviews WHERE evaluator_binding_id=r.evaluator_binding_id))))) $$;
REVOKE ALL ON FUNCTION anvil.golden_engineer(uuid),anvil.golden_source_live(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.golden_engineer(uuid),anvil.golden_source_live(uuid,uuid) TO anvil_app;

CREATE TABLE anvil.benchmark_golden_datasets(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),name text NOT NULL CHECK(length(name) BETWEEN 1 AND 160),
 description text NOT NULL CHECK(length(description)<=2000),created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(project_id,id));
CREATE TABLE anvil.benchmark_golden_dataset_events(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,dataset_id uuid NOT NULL,action text NOT NULL CHECK(action='archived'),
 actor_id uuid NOT NULL REFERENCES anvil.users(id),rationale text NOT NULL CHECK(length(rationale) BETWEEN 10 AND 2000),created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,dataset_id),FOREIGN KEY(project_id,dataset_id) REFERENCES anvil.benchmark_golden_datasets(project_id,id));
CREATE TABLE anvil.benchmark_golden_versions(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,dataset_id uuid NOT NULL,case_key text NOT NULL CHECK(case_key~'^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$'),
 revision integer NOT NULL CHECK(revision>0),predecessor_id uuid,source_build_id uuid,content jsonb NOT NULL CHECK(jsonb_typeof(content)='object' AND octet_length(content::text)<=262144 AND content ? 'origin' AND content->>'origin'='original_synthetic_fixture'),
 content_sha256 text NOT NULL CHECK(content_sha256~'^[a-f0-9]{64}$'),created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),UNIQUE(project_id,dataset_id,case_key,revision),FOREIGN KEY(project_id,dataset_id) REFERENCES anvil.benchmark_golden_datasets(project_id,id),
 FOREIGN KEY(project_id,predecessor_id) REFERENCES anvil.benchmark_golden_versions(project_id,id),FOREIGN KEY(project_id,source_build_id) REFERENCES anvil.benchmark_builds(project_id,id),
 CHECK(content->>'source_trace_id' IS NULL OR source_build_id IS NULL));
CREATE TABLE anvil.benchmark_golden_verifications(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,version_id uuid NOT NULL,assignment_id uuid NOT NULL,
 evidence_artifact_id uuid NOT NULL,evidence_sha256 text NOT NULL CHECK(evidence_sha256~'^[a-f0-9]{64}$'),expected_content_sha256 text NOT NULL CHECK(expected_content_sha256~'^[a-f0-9]{64}$'),
 verifier_id uuid NOT NULL REFERENCES anvil.users(id),decision text NOT NULL CHECK(decision IN ('verified','rejected')),
 rationale text NOT NULL CHECK(length(rationale) BETWEEN 10 AND 2000),human_reviewed boolean NOT NULL CHECK(human_reviewed),created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,version_id),FOREIGN KEY(project_id,version_id) REFERENCES anvil.benchmark_golden_versions(project_id,id),
 FOREIGN KEY(project_id,assignment_id) REFERENCES anvil.benchmark_private_assignments(project_id,id),FOREIGN KEY(project_id,evidence_artifact_id) REFERENCES anvil.artifacts(project_id,id));
CREATE FUNCTION anvil.golden_latest_version(p uuid,d uuid,k text) RETURNS TABLE(id uuid,revision integer) LANGUAGE sql STABLE SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
 SELECT v.id,v.revision FROM anvil.benchmark_golden_versions v WHERE anvil.golden_engineer(p) AND v.project_id=p AND v.dataset_id=d AND v.case_key=k ORDER BY v.revision DESC LIMIT 1 $$;
REVOKE ALL ON FUNCTION anvil.golden_latest_version(uuid,uuid,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.golden_latest_version(uuid,uuid,text) TO anvil_app;
CREATE TABLE anvil.benchmark_remediation_proposals(
 id uuid PRIMARY KEY,project_id uuid NOT NULL REFERENCES anvil.projects(id),source_build_id uuid,
 content jsonb NOT NULL CHECK(jsonb_typeof(content)='object' AND octet_length(content::text)<=65536 AND content ? 'origin' AND content->>'origin'='original_synthetic_fixture'),content_sha256 text NOT NULL CHECK(content_sha256~'^[a-f0-9]{64}$'),created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),FOREIGN KEY(project_id,source_build_id) REFERENCES anvil.benchmark_builds(project_id,id),CHECK(content->>'source_trace_id' IS NULL OR source_build_id IS NULL));
CREATE TABLE anvil.benchmark_remediation_intents(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,proposal_id uuid NOT NULL,created_by uuid NOT NULL REFERENCES anvil.users(id),
 state text NOT NULL CHECK(state='blocked'),code text NOT NULL CHECK(code='compatible_offline_executor_unavailable'),
 provider_calls integer NOT NULL CHECK(provider_calls=0),auto_applied boolean NOT NULL CHECK(NOT auto_applied),limits jsonb NOT NULL CHECK(
 limits ?& ARRAY['max_steps','max_output_bytes'] AND limits-ARRAY['max_steps','max_output_bytes']='{}'::jsonb
 AND jsonb_typeof(limits->'max_steps')='number' AND jsonb_typeof(limits->'max_output_bytes')='number'
 AND (limits->>'max_steps')::integer BETWEEN 1 AND 20 AND (limits->>'max_output_bytes')::integer BETWEEN 64 AND 65536),
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,proposal_id) REFERENCES anvil.benchmark_remediation_proposals(project_id,id));

CREATE FUNCTION anvil.guard_golden_version() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$ DECLARE parent anvil.benchmark_golden_versions; BEGIN
 IF NEW.created_by IS DISTINCT FROM nullif(current_setting('anvil.user',true),'')::uuid OR NOT anvil.golden_source_live(NEW.project_id,NEW.source_build_id)
 THEN RAISE EXCEPTION 'current golden author and source required'; END IF;
 IF EXISTS(SELECT 1 FROM anvil.benchmark_golden_dataset_events WHERE dataset_id=NEW.dataset_id) THEN RAISE EXCEPTION 'dataset archived'; END IF;
 IF NEW.predecessor_id IS NULL THEN
  IF NEW.revision<>1 THEN RAISE EXCEPTION 'first golden revision must be one'; END IF;
 ELSE
  SELECT * INTO parent FROM anvil.benchmark_golden_versions WHERE id=NEW.predecessor_id AND project_id=NEW.project_id;
  IF NOT FOUND OR parent.dataset_id<>NEW.dataset_id OR parent.case_key<>NEW.case_key OR NEW.revision<>parent.revision+1
  OR EXISTS(SELECT 1 FROM anvil.benchmark_golden_versions WHERE predecessor_id=parent.id)
  THEN RAISE EXCEPTION 'exact current golden predecessor required'; END IF;
 END IF;
 RETURN NEW; END $$;
CREATE TRIGGER golden_version_binding BEFORE INSERT ON anvil.benchmark_golden_versions FOR EACH ROW EXECUTE FUNCTION anvil.guard_golden_version();
CREATE FUNCTION anvil.guard_golden_verification() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$ DECLARE v anvil.benchmark_golden_versions; BEGIN
 SELECT * INTO v FROM anvil.benchmark_golden_versions WHERE id=NEW.version_id AND project_id=NEW.project_id;
 IF NOT FOUND OR v.created_by=NEW.verifier_id OR v.content_sha256<>NEW.expected_content_sha256 OR v.source_build_id IS NULL OR v.content->>'source_trace_id' IS NOT NULL
 OR NEW.verifier_id IS DISTINCT FROM nullif(current_setting('anvil.user',true),'')::uuid OR NOT anvil.golden_source_live(NEW.project_id,v.source_build_id)
 OR NOT EXISTS(SELECT 1 FROM anvil.benchmark_build_tasks t WHERE t.project_id=NEW.project_id AND t.build_id=v.source_build_id AND t.task_id=v.content->>'fictional_task_id')
 THEN RAISE EXCEPTION 'distinct human verifier and current exact source required'; END IF;
 IF NOT EXISTS(SELECT 1 FROM anvil.benchmark_private_assignments a WHERE a.id=NEW.assignment_id AND a.project_id=NEW.project_id
 AND a.user_id=NEW.verifier_id AND a.scope='evaluation_review' AND a.artifact_id IS NULL AND a.expires_at>now()
 AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_private_revocations r WHERE r.assignment_id=a.id))
 THEN RAISE EXCEPTION 'current individual evaluation duty required'; END IF;
 IF NOT EXISTS(SELECT 1 FROM anvil.artifacts a WHERE a.project_id=NEW.project_id AND a.id=NEW.evidence_artifact_id
 AND a.sha256=NEW.evidence_sha256 AND a.classification IN ('benchmark_eval','benchmark_trace'))
 THEN RAISE EXCEPTION 'exact private verification evidence required'; END IF;
 RETURN NEW; END $$;
CREATE TRIGGER golden_human_verification BEFORE INSERT ON anvil.benchmark_golden_verifications FOR EACH ROW EXECUTE FUNCTION anvil.guard_golden_verification();

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['benchmark_golden_datasets','benchmark_golden_dataset_events','benchmark_golden_versions','benchmark_golden_verifications','benchmark_remediation_proposals','benchmark_remediation_intents'] LOOP
  EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY golden_project_scope ON anvil.%I USING(anvil.golden_engineer(project_id)) WITH CHECK(anvil.golden_engineer(project_id))',t);
  EXECUTE format('GRANT SELECT,INSERT ON anvil.%I TO anvil_app',t);
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
END $$;
CREATE POLICY golden_private ON anvil.benchmark_golden_versions AS RESTRICTIVE USING(
 anvil.golden_source_live(project_id,source_build_id) AND (created_by=nullif(current_setting('anvil.user',true),'')::uuid OR anvil.benchmark_private_access(project_id,'benchmark_eval',id)))
 WITH CHECK(created_by=nullif(current_setting('anvil.user',true),'')::uuid AND anvil.golden_source_live(project_id,source_build_id));
CREATE POLICY remediation_private ON anvil.benchmark_remediation_proposals AS RESTRICTIVE USING(
 anvil.golden_source_live(project_id,source_build_id) AND (created_by=nullif(current_setting('anvil.user',true),'')::uuid OR anvil.benchmark_private_access(project_id,'benchmark_eval',id)))
 WITH CHECK(created_by=nullif(current_setting('anvil.user',true),'')::uuid AND anvil.golden_source_live(project_id,source_build_id));
CREATE POLICY golden_verification_private ON anvil.benchmark_golden_verifications AS RESTRICTIVE USING(
 EXISTS(SELECT 1 FROM anvil.benchmark_golden_versions v WHERE v.project_id=benchmark_golden_verifications.project_id AND v.id=version_id))
 WITH CHECK(verifier_id=nullif(current_setting('anvil.user',true),'')::uuid);
CREATE POLICY remediation_intent_private ON anvil.benchmark_remediation_intents AS RESTRICTIVE USING(
 EXISTS(SELECT 1 FROM anvil.benchmark_remediation_proposals p WHERE p.project_id=benchmark_remediation_intents.project_id AND p.id=proposal_id))
 WITH CHECK(created_by=nullif(current_setting('anvil.user',true),'')::uuid AND EXISTS(SELECT 1 FROM anvil.benchmark_remediation_proposals p WHERE p.project_id=benchmark_remediation_intents.project_id AND p.id=proposal_id));
CREATE POLICY golden_dataset_author ON anvil.benchmark_golden_datasets AS RESTRICTIVE FOR INSERT WITH CHECK(created_by=nullif(current_setting('anvil.user',true),'')::uuid);
CREATE POLICY golden_archive_author ON anvil.benchmark_golden_dataset_events AS RESTRICTIVE FOR INSERT WITH CHECK(
 actor_id=nullif(current_setting('anvil.user',true),'')::uuid AND EXISTS(SELECT 1 FROM anvil.benchmark_golden_datasets d WHERE d.id=dataset_id AND d.project_id=benchmark_golden_dataset_events.project_id AND (d.created_by=actor_id OR anvil.benchmark_is_admin(project_id,actor_id))));
INSERT INTO anvil.schema_versions(version) VALUES(59);
