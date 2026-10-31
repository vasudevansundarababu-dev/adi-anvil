CREATE TABLE anvil.harbor_agent_plans (
 id uuid PRIMARY KEY, project_id uuid NOT NULL, package_id uuid NOT NULL, connection_id uuid NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id), config jsonb NOT NULL, subject_hash char(64) NOT NULL,
 state text NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','launched')),
 check_id uuid, window_id uuid, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,id),
 FOREIGN KEY(project_id,package_id) REFERENCES anvil.harbor_packages(project_id,id),
 FOREIGN KEY(project_id,connection_id) REFERENCES anvil.connections(project_id,id),
 FOREIGN KEY(project_id,check_id) REFERENCES anvil.harbor_checks(project_id,id),
 FOREIGN KEY(project_id,window_id) REFERENCES anvil.evaluation_spend_windows(project_id,id)
);
CREATE TABLE anvil.harbor_agent_reviews (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,plan_id uuid NOT NULL,approved_by uuid NOT NULL REFERENCES anvil.users(id),
 subject_hash char(64) NOT NULL,rationale text NOT NULL,rights_evidence_id uuid NOT NULL,
 self_approved boolean NOT NULL,created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(plan_id,approved_by),UNIQUE(project_id,id),
 FOREIGN KEY(project_id,plan_id) REFERENCES anvil.harbor_agent_plans(project_id,id),
 FOREIGN KEY(project_id,rights_evidence_id) REFERENCES anvil.artifacts(project_id,id)
);
CREATE TABLE anvil.harbor_agent_calls (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,plan_id uuid NOT NULL,stage_index int NOT NULL,
 request_sha256 char(64) NOT NULL,reserved_micro_usd bigint NOT NULL CHECK(reserved_micro_usd>0),
 status text NOT NULL CHECK(status IN ('dispatching','completed','execution_unknown')),
 output_json jsonb,usage jsonb,request_id text,actual_micro_usd bigint,
 created_at timestamptz NOT NULL DEFAULT now(),finished_at timestamptz,
 UNIQUE(plan_id,stage_index), FOREIGN KEY(project_id,plan_id) REFERENCES anvil.harbor_agent_plans(project_id,id)
);
CREATE TABLE anvil.harbor_agent_review_revocations (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,review_id uuid NOT NULL UNIQUE,
 revoked_by uuid NOT NULL REFERENCES anvil.users(id),rationale text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY(project_id,review_id) REFERENCES anvil.harbor_agent_reviews(project_id,id)
);
ALTER TABLE anvil.harbor_checks ADD COLUMN agent_plan_id uuid;
ALTER TABLE anvil.harbor_checks ADD FOREIGN KEY(project_id,agent_plan_id) REFERENCES anvil.harbor_agent_plans(project_id,id);
ALTER TABLE anvil.harbor_checks DROP CONSTRAINT harbor_checks_candidate_check;
ALTER TABLE anvil.harbor_checks ADD CHECK(candidate IN ('reference','empty_output','constraint_failure','agent'));
ALTER TABLE anvil.harbor_checks ADD CHECK((candidate='agent')=(agent_plan_id IS NOT NULL));
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['harbor_agent_plans','harbor_agent_reviews','harbor_agent_calls','harbor_agent_review_revocations'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY project_scope ON anvil.%I USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id))',t);
 EXECUTE format('CREATE INDEX ON anvil.%I(project_id)',t);
 EXECUTE format('GRANT SELECT,INSERT ON anvil.%I TO anvil_app',t);
 END LOOP;
END $$;
GRANT UPDATE ON anvil.harbor_agent_plans,anvil.harbor_agent_calls TO anvil_app;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.harbor_agent_reviews FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.harbor_agent_review_revocations FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE FUNCTION anvil.guard_harbor_agent_plan() RETURNS trigger LANGUAGE plpgsql AS $$
 BEGIN
 IF ROW(NEW.id,NEW.project_id,NEW.package_id,NEW.connection_id,NEW.created_by,NEW.config,NEW.subject_hash,NEW.created_at)
 IS DISTINCT FROM ROW(OLD.id,OLD.project_id,OLD.package_id,OLD.connection_id,OLD.created_by,OLD.config,OLD.subject_hash,OLD.created_at)
 OR (OLD.state='launched' AND NEW IS DISTINCT FROM OLD)
 THEN RAISE EXCEPTION 'immutable Harbor agent plan'; END IF;
 RETURN NEW;
 END $$;
CREATE TRIGGER guard_harbor_agent_plan BEFORE UPDATE OR DELETE ON anvil.harbor_agent_plans FOR EACH ROW EXECUTE FUNCTION anvil.guard_harbor_agent_plan();
CREATE FUNCTION anvil.guard_harbor_agent_call() RETURNS trigger LANGUAGE plpgsql AS $$
 BEGIN
 IF ROW(NEW.id,NEW.project_id,NEW.plan_id,NEW.stage_index,NEW.request_sha256,NEW.reserved_micro_usd,NEW.created_at)
 IS DISTINCT FROM ROW(OLD.id,OLD.project_id,OLD.plan_id,OLD.stage_index,OLD.request_sha256,OLD.reserved_micro_usd,OLD.created_at)
 OR (OLD.status<>'dispatching' AND NEW IS DISTINCT FROM OLD)
 THEN RAISE EXCEPTION 'immutable Harbor agent call evidence'; END IF;
 RETURN NEW;
 END $$;
CREATE TRIGGER guard_harbor_agent_call BEFORE UPDATE OR DELETE ON anvil.harbor_agent_calls FOR EACH ROW EXECUTE FUNCTION anvil.guard_harbor_agent_call();
CREATE OR REPLACE FUNCTION anvil.guard_harbor_check() RETURNS trigger LANGUAGE plpgsql AS $$
 BEGIN
 IF ROW(NEW.id,NEW.project_id,NEW.package_id,NEW.created_by,NEW.candidate,NEW.agent_plan_id,NEW.created_at)
 IS DISTINCT FROM ROW(OLD.id,OLD.project_id,OLD.package_id,OLD.created_by,OLD.candidate,OLD.agent_plan_id,OLD.created_at)
 THEN RAISE EXCEPTION 'immutable Harbor execution binding'; END IF;
 IF OLD.state NOT IN ('queued','running') AND NEW IS DISTINCT FROM OLD
 THEN RAISE EXCEPTION 'immutable terminal Harbor evidence'; END IF;
 IF NEW.invocation_count < OLD.invocation_count OR NEW.invocation_count > 1
 THEN RAISE EXCEPTION 'invalid Harbor invocation count'; END IF;
 RETURN NEW;
 END $$;
CREATE UNIQUE INDEX harbor_authority_reference ON anvil.evaluation_spend_windows(authority_reference) WHERE authority_reference LIKE 'harbor:%';
INSERT INTO anvil.schema_versions(version) VALUES(23);
