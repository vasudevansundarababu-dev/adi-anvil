ALTER TABLE anvil.runs ADD UNIQUE(project_id,id,protocol_revision_id);
ALTER TABLE anvil.jobs ADD UNIQUE(project_id,id);

CREATE TABLE anvil.benchmark_receipt_tasks (
 project_id uuid NOT NULL,receipt_id uuid NOT NULL,task_id text NOT NULL,task_version text NOT NULL,source_id uuid NOT NULL,
 PRIMARY KEY(project_id,receipt_id,task_id),UNIQUE(project_id,source_id),
 FOREIGN KEY(project_id,receipt_id) REFERENCES anvil.benchmark_bundle_receipts(project_id,id),
 FOREIGN KEY(project_id,source_id) REFERENCES anvil.praxis_sources(project_id,id)
);
CREATE TABLE anvil.benchmark_qualifications (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,source_id uuid NOT NULL,package_id uuid NOT NULL,evaluator_binding_id uuid NOT NULL,
 package_sha256 text NOT NULL CHECK(package_sha256~'^[a-f0-9]{64}$'),
 environment_digest text NOT NULL CHECK(environment_digest~'^sha256:[a-f0-9]{64}$'),
 compiler_sha256 text NOT NULL CHECK(compiler_sha256~'^[a-f0-9]{64}$'),
 tool_schema_sha256 text NOT NULL CHECK(tool_schema_sha256~'^[a-f0-9]{64}$'),
 harbor_version text NOT NULL CHECK(harbor_version='0.25.0'),
 outcome text NOT NULL CHECK(outcome IN ('passed','failed','blocked')),
 report_artifact_id uuid NOT NULL,reviewed_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),UNIQUE(project_id,id,source_id,package_id),
 FOREIGN KEY(project_id,source_id) REFERENCES anvil.praxis_sources(project_id,id),
 FOREIGN KEY(project_id,package_id) REFERENCES anvil.harbor_packages(project_id,id),
 FOREIGN KEY(project_id,evaluator_binding_id) REFERENCES anvil.benchmark_evaluator_bindings(project_id,id),
 FOREIGN KEY(project_id,report_artifact_id) REFERENCES anvil.artifacts(project_id,id)
);
CREATE TABLE anvil.benchmark_qualification_events (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,qualification_id uuid NOT NULL,
 decision text NOT NULL CHECK(decision IN ('revoked','stale')),rationale text NOT NULL CHECK(length(rationale) BETWEEN 1 AND 2000),
 actor_id uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(project_id,id),
 FOREIGN KEY(project_id,qualification_id) REFERENCES anvil.benchmark_qualifications(project_id,id)
);
CREATE TABLE anvil.benchmark_version_bindings (
 project_id uuid NOT NULL,benchmark_revision_id uuid NOT NULL,suite_revision_id uuid NOT NULL,
 subject_sha256 text NOT NULL CHECK(subject_sha256~'^[a-f0-9]{64}$'),
 scoring_policy_sha256 text NOT NULL CHECK(scoring_policy_sha256~'^[a-f0-9]{64}$'),
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(project_id,benchmark_revision_id),UNIQUE(project_id,suite_revision_id),
 FOREIGN KEY(project_id,benchmark_revision_id) REFERENCES anvil.revisions(project_id,id),
 FOREIGN KEY(project_id,suite_revision_id) REFERENCES anvil.revisions(project_id,id)
);
CREATE TABLE anvil.benchmark_version_tasks (
 project_id uuid NOT NULL,benchmark_revision_id uuid NOT NULL,ordinal int NOT NULL CHECK(ordinal BETWEEN 0 AND 99),
 task_revision_id uuid NOT NULL,source_id uuid NOT NULL,package_id uuid NOT NULL,qualification_id uuid NOT NULL,
 possible_points numeric(20,8) NOT NULL CHECK(possible_points>0 AND possible_points<=1000000),criterion_count int NOT NULL CHECK(criterion_count BETWEEN 1 AND 1000),
 PRIMARY KEY(project_id,benchmark_revision_id,ordinal),UNIQUE(project_id,benchmark_revision_id,task_revision_id),
 FOREIGN KEY(project_id,benchmark_revision_id) REFERENCES anvil.benchmark_version_bindings(project_id,benchmark_revision_id),
 FOREIGN KEY(project_id,task_revision_id) REFERENCES anvil.revisions(project_id,id),
 FOREIGN KEY(project_id,qualification_id,source_id,package_id) REFERENCES anvil.benchmark_qualifications(project_id,id,source_id,package_id)
);
CREATE TABLE anvil.benchmark_comparisons (
 project_id uuid NOT NULL,run_id uuid NOT NULL,benchmark_revision_id uuid NOT NULL,protocol_revision_id uuid NOT NULL,
 subject_sha256 text NOT NULL CHECK(subject_sha256~'^[a-f0-9]{64}$'),planned_cells int NOT NULL CHECK(planned_cells BETWEEN 1 AND 3000),
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(project_id,run_id),
 UNIQUE(project_id,run_id,benchmark_revision_id),
 FOREIGN KEY(project_id,run_id,protocol_revision_id) REFERENCES anvil.runs(project_id,id,protocol_revision_id),
 FOREIGN KEY(project_id,benchmark_revision_id) REFERENCES anvil.benchmark_version_bindings(project_id,benchmark_revision_id)
);
CREATE TABLE anvil.benchmark_comparison_groups (
 project_id uuid NOT NULL,run_id uuid NOT NULL,benchmark_revision_id uuid NOT NULL,task_revision_id uuid NOT NULL,group_id uuid NOT NULL,
 PRIMARY KEY(project_id,run_id,task_revision_id),UNIQUE(project_id,group_id),
 FOREIGN KEY(project_id,run_id,benchmark_revision_id) REFERENCES anvil.benchmark_comparisons(project_id,run_id,benchmark_revision_id),
 FOREIGN KEY(project_id,benchmark_revision_id,task_revision_id) REFERENCES anvil.benchmark_version_tasks(project_id,benchmark_revision_id,task_revision_id),
 FOREIGN KEY(project_id,group_id) REFERENCES anvil.workspace_execution_groups(project_id,id)
);
CREATE TABLE anvil.benchmark_cells (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,run_id uuid NOT NULL,benchmark_revision_id uuid NOT NULL,task_revision_id uuid NOT NULL,
 slot int NOT NULL CHECK(slot BETWEEN 0 AND 2),repetition int NOT NULL CHECK(repetition BETWEEN 0 AND 9),
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(project_id,id),UNIQUE(project_id,run_id,id),
 UNIQUE(project_id,run_id,task_revision_id,slot,repetition),
 FOREIGN KEY(project_id,run_id,benchmark_revision_id) REFERENCES anvil.benchmark_comparisons(project_id,run_id,benchmark_revision_id),
 FOREIGN KEY(project_id,benchmark_revision_id,task_revision_id) REFERENCES anvil.benchmark_version_tasks(project_id,benchmark_revision_id,task_revision_id)
);
CREATE TABLE anvil.benchmark_cell_attempts (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,cell_id uuid NOT NULL,attempt_no int NOT NULL CHECK(attempt_no>0),
 predecessor_id uuid,plan_id uuid NOT NULL,check_id uuid,job_id uuid,created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),UNIQUE(project_id,cell_id,id),UNIQUE(project_id,cell_id,attempt_no),
 UNIQUE(project_id,plan_id),UNIQUE(project_id,check_id),UNIQUE(project_id,job_id),
 FOREIGN KEY(project_id,cell_id) REFERENCES anvil.benchmark_cells(project_id,id),
 FOREIGN KEY(project_id,cell_id,predecessor_id) REFERENCES anvil.benchmark_cell_attempts(project_id,cell_id,id),
 FOREIGN KEY(project_id,plan_id) REFERENCES anvil.harbor_agent_plans(project_id,id),
 FOREIGN KEY(project_id,check_id) REFERENCES anvil.harbor_checks(project_id,id),
 FOREIGN KEY(project_id,job_id) REFERENCES anvil.jobs(project_id,id),
 CHECK((attempt_no=1)=(predecessor_id IS NULL))
);
CREATE TABLE anvil.benchmark_attempt_events (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,attempt_id uuid NOT NULL,event_seq bigint GENERATED ALWAYS AS IDENTITY,
 state text NOT NULL CHECK(state IN ('queued','running','collecting','completed','model_failed','operational_failed','dispatch_unknown','cancelled')),
 validity text NOT NULL CHECK(validity IN ('pending','valid','invalid','unresolved')),fence uuid NOT NULL,
 sealed_output_artifact_id uuid,reason_code text CHECK(reason_code~'^[a-z][a-z0-9_]{0,79}$'),created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),FOREIGN KEY(project_id,attempt_id) REFERENCES anvil.benchmark_cell_attempts(project_id,id),
 FOREIGN KEY(project_id,sealed_output_artifact_id) REFERENCES anvil.artifacts(project_id,id)
);
CREATE TABLE anvil.benchmark_evaluator_calls (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,attempt_id uuid NOT NULL,evaluator_job_id uuid NOT NULL,
 evaluation_revision int NOT NULL CHECK(evaluation_revision>0),purpose text NOT NULL CHECK(purpose IN ('deterministic','judge','second_review')),
 request_sha256 text NOT NULL CHECK(request_sha256~'^[a-f0-9]{64}$'),reservation_id uuid,created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),UNIQUE(project_id,attempt_id,evaluation_revision,purpose),
 FOREIGN KEY(project_id,attempt_id) REFERENCES anvil.benchmark_cell_attempts(project_id,id),
 FOREIGN KEY(project_id,evaluator_job_id) REFERENCES anvil.benchmark_evaluator_jobs(project_id,id),
 FOREIGN KEY(project_id,reservation_id) REFERENCES anvil.budget_reservations(project_id,id),
 CHECK((purpose='deterministic')=(reservation_id IS NULL))
);
CREATE TABLE anvil.benchmark_criterion_results (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,evaluator_call_id uuid NOT NULL,criterion_id text NOT NULL,
 earned_points numeric(20,8) NOT NULL CHECK(earned_points>=0 AND earned_points<=1000000),possible_points numeric(20,8) NOT NULL CHECK(possible_points>0 AND possible_points<=1000000),
 output_artifact_id uuid,output_sha256 text CHECK(output_sha256~'^[a-f0-9]{64}$'),
 evidence_start bigint,evidence_end bigint,absence_event_id uuid,created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),UNIQUE(project_id,evaluator_call_id,criterion_id),
 FOREIGN KEY(project_id,evaluator_call_id) REFERENCES anvil.benchmark_evaluator_calls(project_id,id),
 FOREIGN KEY(project_id,output_artifact_id) REFERENCES anvil.artifacts(project_id,id),
 FOREIGN KEY(project_id,absence_event_id) REFERENCES anvil.benchmark_attempt_events(project_id,id),
 CHECK(earned_points<=possible_points),
 CHECK((output_artifact_id IS NOT NULL AND output_sha256 IS NOT NULL AND evidence_start IS NOT NULL AND evidence_end IS NOT NULL AND evidence_start>=0 AND evidence_end>evidence_start AND absence_event_id IS NULL)
 OR (output_artifact_id IS NULL AND output_sha256 IS NULL AND evidence_start IS NULL AND evidence_end IS NULL AND absence_event_id IS NOT NULL AND earned_points=0))
);
CREATE TABLE anvil.benchmark_score_revisions (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,run_id uuid NOT NULL,revision int NOT NULL CHECK(revision>0),predecessor_id uuid,
 projection_sha256 text NOT NULL CHECK(projection_sha256~'^[a-f0-9]{64}$'),redacted_projection jsonb NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),UNIQUE(project_id,run_id,id),UNIQUE(project_id,run_id,revision),
 FOREIGN KEY(project_id,run_id) REFERENCES anvil.benchmark_comparisons(project_id,run_id),
 FOREIGN KEY(project_id,run_id,predecessor_id) REFERENCES anvil.benchmark_score_revisions(project_id,run_id,id),
 CHECK((revision=1)=(predecessor_id IS NULL)),CHECK(jsonb_typeof(redacted_projection)='object')
);
CREATE TABLE anvil.benchmark_score_reviews (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,score_revision_id uuid NOT NULL,reviewer_id uuid NOT NULL REFERENCES anvil.users(id),
 assignment_id uuid NOT NULL,decision text NOT NULL CHECK(decision IN ('approved','disputed','changes_required','adjudicated')),
 evidence_sha256 text NOT NULL CHECK(evidence_sha256~'^[a-f0-9]{64}$'),rationale text NOT NULL CHECK(length(rationale) BETWEEN 1 AND 2000),
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(project_id,id),UNIQUE(project_id,score_revision_id,reviewer_id),
 FOREIGN KEY(project_id,score_revision_id) REFERENCES anvil.benchmark_score_revisions(project_id,id),
 FOREIGN KEY(project_id,assignment_id) REFERENCES anvil.benchmark_private_assignments(project_id,id)
);
CREATE TABLE anvil.benchmark_spend_bindings (
 project_id uuid NOT NULL,run_id uuid NOT NULL,purpose text NOT NULL CHECK(purpose IN ('candidate','judge')),window_id uuid NOT NULL,
 cap_micro_usd bigint NOT NULL CHECK(cap_micro_usd>=0),pricing_sha256 text NOT NULL CHECK(pricing_sha256~'^[a-f0-9]{64}$'),
 authority_sha256 text NOT NULL CHECK(authority_sha256~'^[a-f0-9]{64}$'),created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(project_id,run_id,purpose),UNIQUE(project_id,window_id),
 FOREIGN KEY(project_id,run_id) REFERENCES anvil.benchmark_comparisons(project_id,run_id),
 FOREIGN KEY(project_id,window_id) REFERENCES anvil.evaluation_spend_windows(project_id,id)
);
CREATE TABLE anvil.benchmark_capacity_claims (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,run_id uuid NOT NULL,cell_id uuid NOT NULL,attempt_id uuid NOT NULL,
 provider text NOT NULL CHECK(length(provider) BETWEEN 1 AND 80),slot int NOT NULL CHECK(slot BETWEEN 0 AND 2),
 fence uuid NOT NULL,generation bigint NOT NULL CHECK(generation>0),lease_until timestamptz NOT NULL,state text NOT NULL CHECK(state IN ('held','dispatch_unknown','released')),
 created_at timestamptz NOT NULL DEFAULT now(),UNIQUE(project_id,id),
 FOREIGN KEY(project_id,run_id,cell_id) REFERENCES anvil.benchmark_cells(project_id,run_id,id),
 FOREIGN KEY(project_id,cell_id,attempt_id) REFERENCES anvil.benchmark_cell_attempts(project_id,cell_id,id)
);
CREATE UNIQUE INDEX benchmark_capacity_generation ON anvil.benchmark_capacity_claims(project_id,attempt_id,generation);
CREATE UNIQUE INDEX benchmark_active_capacity ON anvil.benchmark_capacity_claims(project_id,run_id,slot) WHERE state<>'released';
CREATE UNIQUE INDEX benchmark_attempt_capacity ON anvil.benchmark_capacity_claims(project_id,attempt_id) WHERE state<>'released';
CREATE TABLE anvil.benchmark_dispatch_intents (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,attempt_id uuid NOT NULL,turn_index int NOT NULL CHECK(turn_index BETWEEN 0 AND 14),
 request_sha256 text NOT NULL CHECK(request_sha256~'^[a-f0-9]{64}$'),actor_input_sha256 text NOT NULL CHECK(actor_input_sha256~'^[a-f0-9]{64}$'),
 fence uuid NOT NULL,reservation_id uuid NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),UNIQUE(project_id,attempt_id,turn_index),
 FOREIGN KEY(project_id,attempt_id) REFERENCES anvil.benchmark_cell_attempts(project_id,id),
 FOREIGN KEY(project_id,reservation_id) REFERENCES anvil.budget_reservations(project_id,id)
);

CREATE FUNCTION anvil.guard_benchmark_version() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM anvil.revisions v JOIN anvil.resources r ON r.project_id=v.project_id AND r.id=v.resource_id
 WHERE v.project_id=NEW.project_id AND v.id=NEW.benchmark_revision_id AND r.kind='benchmark')
 OR NOT EXISTS(SELECT 1 FROM anvil.revisions v JOIN anvil.resources r ON r.project_id=v.project_id AND r.id=v.resource_id
 WHERE v.project_id=NEW.project_id AND v.id=NEW.suite_revision_id AND r.kind='suite')
 THEN RAISE EXCEPTION 'benchmark/suite revision kind mismatch' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER benchmark_version_kind BEFORE INSERT ON anvil.benchmark_version_bindings FOR EACH ROW EXECUTE FUNCTION anvil.guard_benchmark_version();
CREATE FUNCTION anvil.guard_benchmark_qualification() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM anvil.harbor_packages p WHERE p.project_id=NEW.project_id AND p.id=NEW.package_id
 AND p.source_id=NEW.source_id AND p.package_sha256=NEW.package_sha256)
 THEN RAISE EXCEPTION 'qualification package/source/hash mismatch' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER benchmark_qualification_binding BEFORE INSERT ON anvil.benchmark_qualifications FOR EACH ROW EXECUTE FUNCTION anvil.guard_benchmark_qualification();
CREATE FUNCTION anvil.guard_benchmark_spend() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM anvil.evaluation_spend_windows w WHERE w.project_id=NEW.project_id AND w.id=NEW.window_id
 AND w.cap_micro_usd=NEW.cap_micro_usd AND w.status='active')
 OR EXISTS(SELECT 1 FROM anvil.run_budgets b WHERE b.project_id=NEW.project_id AND b.window_id=NEW.window_id)
 THEN RAISE EXCEPTION 'benchmark spend requires its own exact active window' USING ERRCODE='23514'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER benchmark_spend_window BEFORE INSERT ON anvil.benchmark_spend_bindings FOR EACH ROW EXECUTE FUNCTION anvil.guard_benchmark_spend();

CREATE FUNCTION anvil.guard_benchmark_capacity() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='DELETE' OR ROW(NEW.id,NEW.project_id,NEW.run_id,NEW.cell_id,NEW.attempt_id,NEW.provider,NEW.slot,NEW.fence,NEW.generation,NEW.created_at)
 IS DISTINCT FROM ROW(OLD.id,OLD.project_id,OLD.run_id,OLD.cell_id,OLD.attempt_id,OLD.provider,OLD.slot,OLD.fence,OLD.generation,OLD.created_at)
 OR (OLD.state='released' AND NEW IS DISTINCT FROM OLD) OR (OLD.state='dispatch_unknown' AND NEW.state='held')
 OR NEW.lease_until<OLD.lease_until THEN RAISE EXCEPTION 'immutable fenced capacity binding'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER benchmark_capacity_binding BEFORE UPDATE OR DELETE ON anvil.benchmark_capacity_claims FOR EACH ROW EXECUTE FUNCTION anvil.guard_benchmark_capacity();

DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['benchmark_receipt_tasks','benchmark_qualifications','benchmark_qualification_events','benchmark_version_bindings','benchmark_version_tasks','benchmark_comparisons','benchmark_comparison_groups','benchmark_cells','benchmark_cell_attempts','benchmark_attempt_events','benchmark_evaluator_calls','benchmark_criterion_results','benchmark_score_revisions','benchmark_score_reviews','benchmark_spend_bindings','benchmark_dispatch_intents','benchmark_capacity_claims'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY project_scope ON anvil.%I USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id))',t);
 EXECUTE format('CREATE INDEX ON anvil.%I(project_id)',t);
 EXECUTE format('GRANT SELECT,INSERT ON anvil.%I TO anvil_app',t);
 IF t<>'benchmark_capacity_claims' THEN
 EXECUTE format('CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.%I FOR EACH ROW EXECUTE FUNCTION anvil.immutable()',t);
 END IF;
 END LOOP;
END $$;
CREATE INDEX ON anvil.benchmark_cells(project_id,run_id,id);
CREATE INDEX ON anvil.benchmark_attempt_events(project_id,attempt_id,event_seq);
CREATE INDEX ON anvil.benchmark_score_revisions(project_id,run_id,revision DESC);
CREATE INDEX ON anvil.benchmark_capacity_claims(project_id,run_id,state,lease_until);
INSERT INTO anvil.schema_versions(version) VALUES(41);
