CREATE TABLE anvil.benchmark_source_reviews (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,receipt_id uuid NOT NULL,evaluator_binding_id uuid NOT NULL,
 manifest_sha256 text NOT NULL CHECK(manifest_sha256~'^[a-f0-9]{64}$'),evidence_artifact_id uuid NOT NULL,
 reviewed_by uuid NOT NULL REFERENCES anvil.users(id),rights_confirmed boolean NOT NULL CHECK(rights_confirmed),
 scope text NOT NULL CHECK(scope='local_fictional_qualification_only'),expires_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(project_id,id),UNIQUE(project_id,id,receipt_id),
 FOREIGN KEY(project_id,receipt_id) REFERENCES anvil.benchmark_bundle_receipts(project_id,id),
 FOREIGN KEY(project_id,evaluator_binding_id) REFERENCES anvil.benchmark_evaluator_bindings(project_id,id),
 FOREIGN KEY(project_id,evidence_artifact_id) REFERENCES anvil.artifacts(project_id,id),CHECK(expires_at>created_at)
);
CREATE TABLE anvil.benchmark_review_revocations (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,review_id uuid NOT NULL,target text NOT NULL CHECK(target IN ('review','evaluator')),
 actor_id uuid NOT NULL REFERENCES anvil.users(id),rationale text NOT NULL CHECK(length(rationale) BETWEEN 10 AND 2000),
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(project_id,review_id,target),
 FOREIGN KEY(project_id,review_id) REFERENCES anvil.benchmark_source_reviews(project_id,id)
);
CREATE TABLE anvil.benchmark_builds (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,receipt_id uuid NOT NULL,review_id uuid NOT NULL,
 subject_sha256 text NOT NULL CHECK(subject_sha256~'^[a-f0-9]{64}$'),dependencies jsonb NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),UNIQUE(project_id,id,receipt_id),UNIQUE(project_id,receipt_id,subject_sha256),
 FOREIGN KEY(project_id,review_id,receipt_id) REFERENCES anvil.benchmark_source_reviews(project_id,id,receipt_id)
);
CREATE TABLE anvil.benchmark_build_tasks (
 project_id uuid NOT NULL,build_id uuid NOT NULL,receipt_id uuid NOT NULL,task_id text NOT NULL,source_id uuid NOT NULL,
 package_id uuid NOT NULL,binding_sha256 text NOT NULL CHECK(binding_sha256~'^[a-f0-9]{64}$'),bindings_artifact_id uuid NOT NULL,
 PRIMARY KEY(project_id,build_id,task_id),UNIQUE(project_id,build_id,task_id,source_id,package_id),
 FOREIGN KEY(project_id,build_id,receipt_id) REFERENCES anvil.benchmark_builds(project_id,id,receipt_id),
 FOREIGN KEY(project_id,receipt_id,task_id) REFERENCES anvil.benchmark_receipt_tasks(project_id,receipt_id,task_id),
 FOREIGN KEY(project_id,source_id) REFERENCES anvil.praxis_sources(project_id,id),
 FOREIGN KEY(project_id,package_id) REFERENCES anvil.harbor_packages(project_id,id),
 FOREIGN KEY(project_id,bindings_artifact_id) REFERENCES anvil.artifacts(project_id,id)
);
CREATE TABLE anvil.benchmark_qualification_operations (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,build_id uuid NOT NULL,created_by uuid NOT NULL REFERENCES anvil.users(id),
 state text NOT NULL CHECK(state IN ('queued','running','passed','failed','blocked','cancelled','execution_unknown')),
 fence uuid,lease_until timestamptz,report_artifact_id uuid,safe_code text NOT NULL DEFAULT 'qualification_queued'
 CHECK(safe_code~'^[a-z][a-z0-9_]{0,79}$'),created_at timestamptz NOT NULL DEFAULT now(),finished_at timestamptz,
 UNIQUE(project_id,id),UNIQUE(project_id,id,build_id),
 FOREIGN KEY(project_id,build_id) REFERENCES anvil.benchmark_builds(project_id,id),
 FOREIGN KEY(project_id,report_artifact_id) REFERENCES anvil.artifacts(project_id,id),
 CHECK(state<>'running' OR (fence IS NOT NULL AND lease_until IS NOT NULL)),
 CHECK((state IN ('queued','running'))=(finished_at IS NULL))
);
CREATE UNIQUE INDEX benchmark_one_active_qualification ON anvil.benchmark_qualification_operations(project_id,build_id)
 WHERE state IN ('queued','running','execution_unknown');
CREATE TABLE anvil.benchmark_operation_results (
 project_id uuid NOT NULL,operation_id uuid NOT NULL,build_id uuid NOT NULL,task_id text NOT NULL,source_id uuid NOT NULL,
 package_id uuid NOT NULL,qualification_id uuid NOT NULL,
 PRIMARY KEY(project_id,operation_id,task_id),
 FOREIGN KEY(project_id,operation_id,build_id) REFERENCES anvil.benchmark_qualification_operations(project_id,id,build_id),
 FOREIGN KEY(project_id,build_id,task_id,source_id,package_id) REFERENCES anvil.benchmark_build_tasks(project_id,build_id,task_id,source_id,package_id),
 FOREIGN KEY(project_id,qualification_id,source_id,package_id) REFERENCES anvil.benchmark_qualifications(project_id,id,source_id,package_id)
);
CREATE TABLE anvil.benchmark_operation_events (
 operation_id uuid NOT NULL,project_id uuid NOT NULL,event_seq bigint GENERATED ALWAYS AS IDENTITY,
 state text NOT NULL,safe_code text NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(operation_id,event_seq),
 FOREIGN KEY(project_id,operation_id) REFERENCES anvil.benchmark_qualification_operations(project_id,id)
);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['benchmark_source_reviews','benchmark_review_revocations','benchmark_builds','benchmark_build_tasks','benchmark_qualification_operations','benchmark_operation_results','benchmark_operation_events'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY project_scope ON anvil.%I USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id))',t);
 EXECUTE format('GRANT SELECT,INSERT ON anvil.%I TO anvil_app',t);
 EXECUTE format('CREATE INDEX ON anvil.%I(project_id)',t);
 IF t<>'benchmark_qualification_operations' THEN
 EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END IF;
 END LOOP;
END $$;
GRANT UPDATE ON anvil.benchmark_qualification_operations TO anvil_app;
CREATE POLICY benchmark_review_admin ON anvil.benchmark_source_reviews AS RESTRICTIVE FOR INSERT WITH CHECK(
 reviewed_by=nullif(current_setting('anvil.user',true),'')::uuid AND anvil.benchmark_is_admin(project_id,reviewed_by));
CREATE POLICY benchmark_revoke_admin ON anvil.benchmark_review_revocations AS RESTRICTIVE FOR INSERT WITH CHECK(
 actor_id=nullif(current_setting('anvil.user',true),'')::uuid AND anvil.benchmark_is_admin(project_id,actor_id));
CREATE POLICY benchmark_build_author ON anvil.benchmark_builds AS RESTRICTIVE FOR INSERT WITH CHECK(
 created_by=nullif(current_setting('anvil.user',true),'')::uuid);
CREATE POLICY benchmark_operation_author ON anvil.benchmark_qualification_operations AS RESTRICTIVE FOR INSERT WITH CHECK(
 created_by=nullif(current_setting('anvil.user',true),'')::uuid AND anvil.benchmark_is_admin(project_id,created_by)
 AND state='queued' AND fence IS NULL AND lease_until IS NULL AND report_artifact_id IS NULL);
CREATE FUNCTION anvil.guard_benchmark_review() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM anvil.benchmark_bundle_receipts r JOIN anvil.artifacts a ON a.project_id=r.project_id
 AND a.id=NEW.evidence_artifact_id WHERE r.project_id=NEW.project_id AND r.id=NEW.receipt_id
 AND r.manifest_sha256=NEW.manifest_sha256 AND a.classification='benchmark_eval')
 THEN RAISE EXCEPTION 'invalid benchmark review evidence'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER benchmark_review_binding BEFORE INSERT ON anvil.benchmark_source_reviews FOR EACH ROW EXECUTE FUNCTION anvil.guard_benchmark_review();
CREATE FUNCTION anvil.guard_benchmark_build_task() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM anvil.benchmark_receipt_tasks t JOIN anvil.harbor_packages p ON p.project_id=t.project_id
 AND p.id=NEW.package_id AND p.source_id=t.source_id JOIN anvil.artifacts a ON a.project_id=t.project_id
 AND a.id=NEW.bindings_artifact_id WHERE t.project_id=NEW.project_id AND t.receipt_id=NEW.receipt_id
 AND t.task_id=NEW.task_id AND t.source_id=NEW.source_id AND a.classification='benchmark_eval' AND a.sha256=NEW.binding_sha256)
 THEN RAISE EXCEPTION 'invalid benchmark build task binding'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER benchmark_task_binding BEFORE INSERT ON anvil.benchmark_build_tasks FOR EACH ROW EXECUTE FUNCTION anvil.guard_benchmark_build_task();
CREATE FUNCTION anvil.guard_benchmark_operation() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='DELETE' OR ROW(NEW.id,NEW.project_id,NEW.build_id,NEW.created_by,NEW.created_at)
 IS DISTINCT FROM ROW(OLD.id,OLD.project_id,OLD.build_id,OLD.created_by,OLD.created_at)
 OR OLD.state NOT IN ('queued','running')
 OR (OLD.state='queued' AND NEW.state NOT IN ('running','cancelled','blocked'))
 OR (OLD.state='running' AND (NEW.state NOT IN ('passed','failed','blocked','cancelled','execution_unknown') OR NEW.fence IS DISTINCT FROM OLD.fence))
 THEN RAISE EXCEPTION 'immutable qualification operation transition'; END IF;
 IF NEW.report_artifact_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM anvil.artifacts a WHERE a.project_id=NEW.project_id
 AND a.id=NEW.report_artifact_id AND a.classification='benchmark_trace') THEN RAISE EXCEPTION 'private qualification report required'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER benchmark_operation_transition BEFORE UPDATE OR DELETE ON anvil.benchmark_qualification_operations FOR EACH ROW EXECUTE FUNCTION anvil.guard_benchmark_operation();
CREATE FUNCTION anvil.record_benchmark_operation_event() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 INSERT INTO anvil.benchmark_operation_events(operation_id,project_id,state,safe_code) VALUES(NEW.id,NEW.project_id,NEW.state,NEW.safe_code);
 RETURN NEW;
END $$;
CREATE TRIGGER benchmark_operation_event AFTER INSERT OR UPDATE ON anvil.benchmark_qualification_operations FOR EACH ROW EXECUTE FUNCTION anvil.record_benchmark_operation_event();
INSERT INTO anvil.schema_versions(version) VALUES(44);
