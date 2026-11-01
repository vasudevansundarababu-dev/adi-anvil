CREATE TABLE anvil.workspace_execution_groups (
 id uuid PRIMARY KEY,project_id uuid NOT NULL,preparation_id uuid NOT NULL,
 created_by uuid NOT NULL REFERENCES anvil.users(id),created_at timestamptz NOT NULL DEFAULT now(),
 snapshot jsonb NOT NULL,subject_hash char(64) NOT NULL,
 state text NOT NULL DEFAULT 'draft' CHECK(state IN ('draft','launched')),
 window_id uuid,
 UNIQUE(project_id,id),
 FOREIGN KEY(project_id,preparation_id) REFERENCES anvil.workspace_run_preparations(project_id,id),
 FOREIGN KEY(project_id,window_id) REFERENCES anvil.evaluation_spend_windows(project_id,id)
);
CREATE TABLE anvil.workspace_execution_models (
 project_id uuid NOT NULL,group_id uuid NOT NULL,ordinal int NOT NULL CHECK(ordinal BETWEEN 0 AND 7),
 plan_id uuid NOT NULL,check_id uuid,
 PRIMARY KEY(project_id,group_id,ordinal),UNIQUE(project_id,plan_id),UNIQUE(project_id,check_id),
 FOREIGN KEY(project_id,group_id) REFERENCES anvil.workspace_execution_groups(project_id,id),
 FOREIGN KEY(project_id,plan_id) REFERENCES anvil.harbor_agent_plans(project_id,id),
 FOREIGN KEY(project_id,check_id) REFERENCES anvil.harbor_checks(project_id,id)
);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['workspace_execution_groups','workspace_execution_models'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY project_scope ON anvil.%I USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id))',t);
 EXECUTE format('GRANT SELECT,INSERT,UPDATE ON anvil.%I TO anvil_app',t);
 END LOOP;
END $$;
CREATE FUNCTION anvil.guard_workspace_execution_group() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='DELETE' OR ROW(NEW.id,NEW.project_id,NEW.preparation_id,NEW.created_by,NEW.created_at,NEW.snapshot,NEW.subject_hash)
 IS DISTINCT FROM ROW(OLD.id,OLD.project_id,OLD.preparation_id,OLD.created_by,OLD.created_at,OLD.snapshot,OLD.subject_hash)
 OR (OLD.state='launched' AND NEW IS DISTINCT FROM OLD)
 OR (NEW.state='launched' AND NEW.window_id IS NULL)
 THEN RAISE EXCEPTION 'immutable workspace group binding'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER immutable_binding BEFORE UPDATE OR DELETE ON anvil.workspace_execution_groups FOR EACH ROW EXECUTE FUNCTION anvil.guard_workspace_execution_group();
CREATE FUNCTION anvil.guard_workspace_execution_model() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF TG_OP='DELETE' OR ROW(NEW.project_id,NEW.group_id,NEW.ordinal,NEW.plan_id)
 IS DISTINCT FROM ROW(OLD.project_id,OLD.group_id,OLD.ordinal,OLD.plan_id)
 OR (OLD.check_id IS NOT NULL AND NEW IS DISTINCT FROM OLD)
 THEN RAISE EXCEPTION 'immutable workspace child binding'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER immutable_binding BEFORE UPDATE OR DELETE ON anvil.workspace_execution_models FOR EACH ROW EXECUTE FUNCTION anvil.guard_workspace_execution_model();
-- All children are durable at admission. Only a child whose predecessors succeeded can
-- be claimed, even with several workers. Unknown/failed/cancelled predecessors stop it.
CREATE OR REPLACE FUNCTION anvil.claim_harbor_job() RETURNS SETOF anvil.jobs LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$ BEGIN
 RETURN QUERY UPDATE anvil.jobs SET status='leased',lease_token=gen_random_uuid(),
 lease_until=now()+interval '60 seconds',attempts=attempts+1
 WHERE id=(SELECT j.id FROM anvil.jobs j WHERE j.kind='harbor_check' AND
 (j.status='queued' OR (j.status='leased' AND j.lease_until<now())) AND j.attempts<3
 AND NOT EXISTS (
 SELECT 1 FROM anvil.workspace_execution_models m
 JOIN anvil.workspace_execution_models prior ON prior.group_id=m.group_id AND prior.project_id=m.project_id AND prior.ordinal<m.ordinal
 JOIN anvil.harbor_checks h ON h.id=prior.check_id AND h.project_id=prior.project_id
 WHERE m.check_id=j.target_id AND m.project_id=j.project_id AND h.state<>'succeeded')
 ORDER BY j.created_at,j.id FOR UPDATE OF j SKIP LOCKED LIMIT 1) RETURNING *;
END $$;
INSERT INTO anvil.schema_versions(version) VALUES(31);
