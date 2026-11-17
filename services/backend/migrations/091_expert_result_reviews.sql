-- Optional human interpretation, never dispatch or alteration of automated scores.
ALTER TABLE anvil.memberships DROP CONSTRAINT memberships_active_two_roles;
ALTER TABLE anvil.memberships ADD CONSTRAINT memberships_active_supported_roles
 CHECK(NOT active OR role IN('admin','rl-engineer','sme-reviewer'));
DROP INDEX anvil.one_active_project_role;
CREATE UNIQUE INDEX one_active_execution_role ON anvil.memberships(project_id,user_id)
 WHERE active AND role IN('admin','rl-engineer');
CREATE FUNCTION anvil.result_reader(p uuid) RETURNS boolean LANGUAGE sql STABLE AS $$
 SELECT anvil.in_scope(p) AND EXISTS(SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id AND u.active
 WHERE m.project_id=p AND m.user_id=nullif(current_setting('anvil.user',true),'')::uuid AND m.active
 AND m.role IN('admin','rl-engineer','sme-reviewer')) $$;
CREATE TABLE anvil.expert_review_executions(
 project_id uuid NOT NULL,run_id uuid NOT NULL,kind text NOT NULL CHECK(kind IN('benchmark_run','workspace_group')),
 snapshot_sha256 text NOT NULL CHECK(snapshot_sha256~'^[a-f0-9]{64}$'),origin text NOT NULL,
 gates jsonb NOT NULL,expected_scope jsonb NOT NULL DEFAULT '{}'::jsonb,created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(project_id,run_id));
CREATE TABLE anvil.expert_review_targets(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,run_id uuid NOT NULL,target_key text NOT NULL,
 content jsonb NOT NULL CHECK(octet_length(content::text)<=131072),content_sha256 text NOT NULL CHECK(content_sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,run_id) REFERENCES anvil.expert_review_executions(project_id,run_id),
 UNIQUE(project_id,id),UNIQUE(run_id,target_key));
CREATE TABLE anvil.expert_review_evidence(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,run_id uuid NOT NULL,title text NOT NULL,
 content jsonb NOT NULL CHECK(octet_length(content::text)<=131072),sha256 text NOT NULL CHECK(sha256~'^[a-f0-9]{64}$'),
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,run_id) REFERENCES anvil.expert_review_executions(project_id,run_id),UNIQUE(project_id,id),UNIQUE(run_id,sha256));
CREATE TABLE anvil.expert_result_reviews(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,run_id uuid NOT NULL,target_id uuid NOT NULL,
 kind text NOT NULL CHECK(kind IN('assessment','diagnosis','resolution','source_correction')),
 revision integer NOT NULL CHECK(revision>0),content jsonb NOT NULL CHECK(octet_length(content::text)<=32768),
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,target_id) REFERENCES anvil.expert_review_targets(project_id,id),
 UNIQUE(project_id,id),UNIQUE(target_id,kind,created_by,revision));
CREATE TABLE anvil.expert_report_snapshots(
 id uuid PRIMARY KEY,project_id uuid NOT NULL,run_id uuid NOT NULL,review_revision text NOT NULL,
 content jsonb NOT NULL,content_sha256 text NOT NULL CHECK(content_sha256~'^[a-f0-9]{64}$'),
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,run_id) REFERENCES anvil.expert_review_executions(project_id,run_id),UNIQUE(project_id,id));
CREATE FUNCTION anvil.guard_expert_review_execution() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,anvil AS $$ BEGIN
 IF NOT ((NEW.kind='benchmark_run' AND EXISTS(SELECT 1 FROM anvil.benchmark_runs r WHERE r.project_id=NEW.project_id AND r.id=NEW.run_id AND r.snapshot_sha256=NEW.snapshot_sha256))
 OR (NEW.kind='workspace_group' AND EXISTS(SELECT 1 FROM anvil.workspace_execution_groups g WHERE g.project_id=NEW.project_id AND g.id=NEW.run_id AND g.subject_hash=NEW.snapshot_sha256)))
 THEN RAISE EXCEPTION 'exact persisted execution snapshot required';END IF;
 RETURN NEW;END $$;
CREATE TRIGGER exact_execution BEFORE INSERT ON anvil.expert_review_executions FOR EACH ROW EXECUTE FUNCTION anvil.guard_expert_review_execution();
CREATE FUNCTION anvil.guard_expert_result_review() RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE required_role text; BEGIN
 IF NEW.created_by IS DISTINCT FROM nullif(current_setting('anvil.user',true),'')::uuid
 OR NOT anvil.result_reader(NEW.project_id) THEN RAISE EXCEPTION 'current project reviewer required';END IF;
 required_role=CASE WHEN NEW.kind='diagnosis' THEN 'rl-engineer' ELSE 'sme-reviewer' END;
 IF NOT EXISTS(SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id AND u.active
 WHERE m.project_id=NEW.project_id AND m.user_id=NEW.created_by AND m.active AND m.role IN('admin',required_role))
 THEN RAISE EXCEPTION 'explicit assessment or engineering duty required';END IF;
 IF NOT EXISTS(SELECT 1 FROM anvil.expert_review_targets t WHERE t.project_id=NEW.project_id AND t.id=NEW.target_id AND t.run_id=NEW.run_id)
 THEN RAISE EXCEPTION 'exact review target required';END IF;
 RETURN NEW;END $$;
CREATE TRIGGER actual_reviewer BEFORE INSERT ON anvil.expert_result_reviews FOR EACH ROW EXECUTE FUNCTION anvil.guard_expert_result_review();
CREATE FUNCTION anvil.lock_result_reviewer(p uuid) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,anvil AS $$
 DECLARE actor uuid=nullif(current_setting('anvil.user',true),'')::uuid; BEGIN
 IF NOT anvil.result_reader(p) THEN RAISE EXCEPTION 'current result access required';END IF;
 PERFORM 1 FROM anvil.users WHERE id=actor AND active FOR SHARE;
 PERFORM 1 FROM anvil.memberships WHERE project_id=p AND user_id=actor AND active ORDER BY role FOR SHARE;
 END $$;
REVOKE ALL ON FUNCTION anvil.lock_result_reviewer(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.lock_result_reviewer(uuid) TO anvil_app;
CREATE FUNCTION anvil.set_sme_result_membership(p uuid,p_subject uuid,enabled boolean) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,anvil AS $$
 DECLARE actor uuid=nullif(current_setting('anvil.user',true),'')::uuid; BEGIN
 IF NOT anvil.in_scope(p) THEN RAISE EXCEPTION 'current project required';END IF;
 PERFORM 1 FROM anvil.users WHERE id=actor AND active FOR SHARE;
 PERFORM 1 FROM anvil.memberships WHERE project_id=p AND user_id=actor AND active AND role='admin' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'current project Admin required';END IF;
 IF NOT EXISTS(SELECT 1 FROM anvil.users u JOIN anvil.projects project ON project.org_id=u.org_id
 WHERE project.id=p AND u.id=p_subject AND u.active) THEN RAISE EXCEPTION 'existing active organization identity required';END IF;
 INSERT INTO anvil.memberships(project_id,user_id,role,active) VALUES(p,p_subject,'sme-reviewer',enabled)
 ON CONFLICT(project_id,user_id,role) DO UPDATE SET active=EXCLUDED.active;
 END $$;
REVOKE ALL ON FUNCTION anvil.set_sme_result_membership(uuid,uuid,boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.set_sme_result_membership(uuid,uuid,boolean) TO anvil_app;
CREATE FUNCTION anvil.result_run_navigation(p uuid,r uuid) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,anvil AS $$
 DECLARE e anvil.expert_review_executions%ROWTYPE;s jsonb;g uuid;label text;models jsonb;stamp timestamptz;state text;BEGIN
 IF NOT anvil.result_reader(p) THEN RAISE EXCEPTION 'assigned project results required';END IF;
 SELECT * INTO e FROM anvil.expert_review_executions WHERE project_id=p AND run_id=r;
 IF NOT FOUND THEN RETURN NULL;END IF;
 IF e.kind='benchmark_run' THEN
  SELECT run.snapshot,plan.task_group_id,plan.name,run.created_at,run.state INTO s,g,label,stamp,state FROM anvil.benchmark_runs run JOIN anvil.benchmark_execution_plans plan ON plan.id=run.plan_id AND plan.project_id=run.project_id WHERE run.project_id=p AND run.id=r;
 ELSE
  SELECT run.snapshot->'preparation',(run.snapshot->'preparation'->'project_binding'->>'task_group_id')::uuid,'Benchmark execution',run.created_at,'results_available' INTO s,g,label,stamp,state FROM anvil.workspace_execution_groups run WHERE run.project_id=p AND run.id=r;
 END IF;
 SELECT coalesce(jsonb_agg(jsonb_build_object('id',coalesce(m->>'id',m->>'model_id'),'name',coalesce(m->>'name',m->>'model_id',m->>'id'))),'[]'::jsonb) INTO models FROM jsonb_array_elements(coalesce(s->'models','[]'::jsonb)) m;
 RETURN jsonb_build_object('id',r,'name',label,'state',state,'created_at',stamp,'snapshot',jsonb_build_object('task_group_id',g,'repetitions',coalesce((s->>'repetitions')::integer,1),'models',models),'project_name',(SELECT name FROM anvil.benchmark_task_groups WHERE id=g AND project_id=p),'result_origin',e.origin,'read_only',true);
 END $$;
REVOKE ALL ON FUNCTION anvil.result_run_navigation(uuid,uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.result_run_navigation(uuid,uuid) TO anvil_app;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['expert_review_executions','expert_review_targets','expert_review_evidence','expert_result_reviews','expert_report_snapshots'] LOOP
  EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
  EXECUTE format('CREATE POLICY reader ON anvil.%I FOR SELECT TO anvil_app USING(anvil.result_reader(project_id))',t);
  EXECUTE format('GRANT SELECT ON anvil.%I TO anvil_app',t);
  EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['expert_review_executions','expert_review_targets','expert_review_evidence'] LOOP
  EXECUTE format('GRANT SELECT,INSERT ON anvil.%I TO anvil_golden_grader,anvil_worker',t);
  EXECUTE format('CREATE POLICY grader ON anvil.%I TO anvil_golden_grader USING(banking.runtime_scope(project_id)) WITH CHECK(banking.runtime_scope(project_id))',t);
  EXECUTE format('CREATE POLICY worker ON anvil.%I TO anvil_worker USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id))',t);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['expert_result_reviews','expert_report_snapshots'] LOOP
  EXECUTE format('GRANT INSERT ON anvil.%I TO anvil_app',t);
  EXECUTE format('CREATE POLICY current_author ON anvil.%I FOR INSERT TO anvil_app WITH CHECK(anvil.result_reader(project_id) AND created_by=nullif(current_setting(''anvil.user'',true),'''')::uuid)',t);
 END LOOP;
END $$;
-- Existing read roles remain unchanged elsewhere; SME access is this explicit projection only.
INSERT INTO anvil.schema_versions(version) VALUES(91);
