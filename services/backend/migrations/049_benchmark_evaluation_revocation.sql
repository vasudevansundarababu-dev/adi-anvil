CREATE TABLE anvil.benchmark_evaluator_registry_revocations(
 project_id uuid NOT NULL,registry_id uuid NOT NULL,revoked_by uuid NOT NULL REFERENCES anvil.users(id),
 rationale text NOT NULL CHECK(length(rationale) BETWEEN 10 AND 2000),created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(project_id,registry_id),FOREIGN KEY(project_id,registry_id) REFERENCES anvil.benchmark_evaluator_registrations(project_id,id)
);
ALTER TABLE anvil.benchmark_evaluator_registry_revocations ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.benchmark_evaluator_registry_revocations FORCE ROW LEVEL SECURITY;
CREATE POLICY project_scope ON anvil.benchmark_evaluator_registry_revocations USING(anvil.in_scope(project_id));
CREATE POLICY revoke_admin ON anvil.benchmark_evaluator_registry_revocations AS RESTRICTIVE FOR INSERT WITH CHECK(
 revoked_by=nullif(current_setting('anvil.user',true),'')::uuid AND anvil.benchmark_is_admin(project_id,revoked_by));
GRANT SELECT,INSERT ON anvil.benchmark_evaluator_registry_revocations TO anvil_app;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.benchmark_evaluator_registry_revocations FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE FUNCTION anvil.guard_evaluation_input_projection() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=anvil,pg_temp AS $$ BEGIN
 IF EXISTS(SELECT 1 FROM anvil.benchmark_evaluation_requests q WHERE q.project_id=NEW.project_id AND q.job_id=NEW.job_id)
 AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_evaluation_requests q JOIN anvil.benchmark_evaluator_registrations r ON r.project_id=q.project_id AND r.id=q.registry_id
 JOIN anvil.benchmark_evaluator_jobs j ON j.project_id=q.project_id AND j.id=q.job_id
 WHERE q.project_id=NEW.project_id AND q.job_id=NEW.job_id AND j.state='queued' AND NEW.artifact_id IN (r.policy_artifact_id,j.sealed_output_artifact_id))
 THEN RAISE EXCEPTION 'sealed evaluator input projection'; END IF;RETURN NEW;END $$;
CREATE TRIGGER evaluation_input_projection BEFORE INSERT ON anvil.benchmark_evaluator_job_inputs FOR EACH ROW EXECUTE FUNCTION anvil.guard_evaluation_input_projection();
CREATE OR REPLACE FUNCTION anvil.evaluation_review_live(p uuid,r uuid,u uuid) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=anvil,pg_temp AS $$
 SELECT EXISTS(SELECT 1 FROM anvil.benchmark_evaluator_registrations g
 JOIN anvil.benchmark_evaluator_bindings b ON b.id=g.binding_id AND b.project_id=g.project_id
 JOIN anvil.memberships m ON m.project_id=g.project_id AND m.user_id=g.reviewed_by AND m.active AND m.role='admin'
 JOIN anvil.users v ON v.id=m.user_id AND v.active
 JOIN anvil.artifacts a ON a.project_id=g.project_id AND a.id=g.policy_artifact_id AND a.classification='benchmark_eval' AND a.sha256=g.policy_sha256
 WHERE g.project_id=p AND g.id=r AND g.expires_at>now() AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_evaluator_registry_revocations z WHERE z.project_id=p AND z.registry_id=r)
 AND b.implementation_sha256=g.implementation_sha256 AND b.policy_sha256=g.policy_sha256
 AND EXISTS(SELECT 1 FROM anvil.memberships x JOIN anvil.users y ON y.id=x.user_id AND y.active WHERE x.project_id=p AND x.user_id=u AND x.active)
 AND EXISTS(SELECT 1 FROM anvil.benchmark_private_assignments x WHERE x.project_id=p AND x.user_id=u AND x.scope='evaluation_review'
 AND x.artifact_id IS NULL AND x.expires_at>now() AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_private_revocations y WHERE y.project_id=p AND y.assignment_id=x.id))
 AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_review_revocations x JOIN anvil.benchmark_source_reviews y ON y.project_id=x.project_id AND y.id=x.review_id WHERE x.project_id=p AND y.evaluator_binding_id=b.id AND x.target='evaluator')) $$;
INSERT INTO anvil.schema_versions(version) VALUES(49);
