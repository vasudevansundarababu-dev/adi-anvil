-- Criterion citations bind actual deliverable bytes, not the JSON seal wrapper.
CREATE TABLE anvil.benchmark_captured_outputs (
 project_id uuid NOT NULL,attempt_id uuid NOT NULL,path text NOT NULL CHECK(path~'^[A-Za-z0-9][A-Za-z0-9_./-]{0,239}$'),
 fence uuid NOT NULL,manifest_artifact_id uuid NOT NULL,required boolean NOT NULL,
 outcome text NOT NULL CHECK(outcome IN ('captured','absent','invalid')),
 artifact_id uuid,sha256 text CHECK(sha256~'^[a-f0-9]{64}$'),byte_size bigint CHECK(byte_size>=0),
 absence_event_id uuid,created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(project_id,attempt_id,path),UNIQUE(project_id,absence_event_id),
 FOREIGN KEY(project_id,attempt_id) REFERENCES anvil.benchmark_cell_attempts(project_id,id),
 FOREIGN KEY(project_id,manifest_artifact_id) REFERENCES anvil.artifacts(project_id,id),
 FOREIGN KEY(project_id,artifact_id) REFERENCES anvil.artifacts(project_id,id),
 FOREIGN KEY(project_id,absence_event_id) REFERENCES anvil.benchmark_attempt_events(project_id,id),
 CHECK((artifact_id IS NULL AND sha256 IS NULL AND byte_size IS NULL AND outcome='absent' AND absence_event_id IS NOT NULL)
 OR (artifact_id IS NOT NULL AND sha256 IS NOT NULL AND byte_size IS NOT NULL AND outcome<>'absent')),
 CHECK(byte_size IS NULL OR byte_size>0 OR (outcome='invalid' AND absence_event_id IS NOT NULL))
);
ALTER TABLE anvil.benchmark_captured_outputs ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.benchmark_captured_outputs FORCE ROW LEVEL SECURITY;
CREATE POLICY project_scope ON anvil.benchmark_captured_outputs USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id));
GRANT SELECT,INSERT ON anvil.benchmark_captured_outputs TO anvil_app;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.benchmark_captured_outputs FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE FUNCTION anvil.guard_captured_output_binding() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NOT EXISTS(SELECT 1 FROM anvil.benchmark_offline_runtime rt
 JOIN anvil.benchmark_cell_attempts attempt ON attempt.project_id=rt.project_id AND attempt.id=rt.attempt_id
 JOIN anvil.benchmark_cells cell ON cell.project_id=attempt.project_id AND cell.id=attempt.cell_id
 JOIN anvil.revisions task ON task.project_id=cell.project_id AND task.id=cell.task_revision_id,
 LATERAL jsonb_array_elements(task.content->'outputs') declared
 WHERE rt.project_id=NEW.project_id AND rt.attempt_id=NEW.attempt_id AND rt.fence=NEW.fence
 AND rt.state='captured' AND rt.output_artifact_id=NEW.manifest_artifact_id
 AND declared->>'path'=NEW.path AND (declared->>'required')::boolean=NEW.required
 AND (NEW.artifact_id IS NULL OR EXISTS(SELECT 1 FROM anvil.artifacts artifact WHERE artifact.project_id=NEW.project_id
 AND artifact.id=NEW.artifact_id AND artifact.classification='benchmark_sealed'
 AND artifact.sha256=NEW.sha256 AND artifact.byte_size=NEW.byte_size AND artifact.byte_size<=(declared->>'max_bytes')::bigint)))
 THEN RAISE EXCEPTION 'captured output requires exact frozen path, manifest, fence and file bytes'; END IF;
 IF NEW.absence_event_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_attempt_events event
 WHERE event.project_id=NEW.project_id AND event.id=NEW.absence_event_id AND event.attempt_id=NEW.attempt_id
 AND event.fence=NEW.fence AND event.sealed_output_artifact_id=NEW.manifest_artifact_id
 AND event.reason_code IN ('required_output_absent','output_content_absent')
 AND (NEW.artifact_id IS NULL OR NEW.byte_size=0))
 THEN RAISE EXCEPTION 'absence requires its exact attempt, fence and absent/empty path';END IF;
 RETURN NEW;END $$;
CREATE TRIGGER exact_capture BEFORE INSERT ON anvil.benchmark_captured_outputs FOR EACH ROW EXECUTE FUNCTION anvil.guard_captured_output_binding();
CREATE FUNCTION anvil.guard_benchmark_criterion_citation() RETURNS trigger LANGUAGE plpgsql AS $$
 DECLARE attempt uuid; BEGIN
 SELECT ec.attempt_id INTO attempt FROM anvil.benchmark_evaluator_calls ec WHERE ec.project_id=NEW.project_id AND ec.id=NEW.evaluator_call_id;
 IF NOT EXISTS(SELECT 1 FROM anvil.benchmark_cell_attempts a JOIN anvil.benchmark_cells cell ON cell.project_id=a.project_id AND cell.id=a.cell_id
 JOIN anvil.benchmark_comparisons b ON b.project_id=cell.project_id AND b.run_id=cell.run_id
 JOIN anvil.benchmark_protocol_bindings frozen ON frozen.project_id=b.project_id AND frozen.protocol_revision_id=b.protocol_revision_id
 WHERE a.project_id=NEW.project_id AND a.id=attempt) THEN RETURN NEW;END IF;
 IF NOT EXISTS(SELECT 1 FROM anvil.benchmark_captured_outputs output
 JOIN anvil.benchmark_cell_attempts a ON a.project_id=output.project_id AND a.id=output.attempt_id
 JOIN anvil.benchmark_cells cell ON cell.project_id=a.project_id AND cell.id=a.cell_id
 JOIN anvil.revisions task ON task.project_id=cell.project_id AND task.id=cell.task_revision_id,
 LATERAL jsonb_array_elements(task.content->'criteria') criterion
 WHERE output.project_id=NEW.project_id AND output.attempt_id=attempt AND criterion->>'id'=NEW.criterion_id
 AND criterion->>'output_path'=output.path
 AND ((NEW.output_artifact_id IS NOT NULL AND output.artifact_id=NEW.output_artifact_id
 AND output.sha256=NEW.output_sha256 AND output.byte_size>0 AND NEW.evidence_end<=output.byte_size)
 OR (NEW.absence_event_id IS NOT NULL AND output.absence_event_id=NEW.absence_event_id
 AND (output.artifact_id IS NULL OR output.byte_size=0) AND NEW.earned_points=0)))
 THEN RAISE EXCEPTION 'criterion evidence requires its actual deliverable span or typed path absence';END IF;
 RETURN NEW;END $$;
CREATE TRIGGER exact_output_citation BEFORE INSERT ON anvil.benchmark_criterion_results FOR EACH ROW EXECUTE FUNCTION anvil.guard_benchmark_criterion_citation();
CREATE TABLE anvil.benchmark_attempt_policy_outcomes (
 project_id uuid NOT NULL,attempt_id uuid NOT NULL,fence uuid NOT NULL,report_artifact_id uuid NOT NULL,
 terminal_event_id uuid NOT NULL,hard_constraint_ids jsonb NOT NULL,unresolved_required_paths jsonb NOT NULL,
 PRIMARY KEY(project_id,attempt_id),
 FOREIGN KEY(project_id,attempt_id) REFERENCES anvil.benchmark_cell_attempts(project_id,id),
 FOREIGN KEY(project_id,report_artifact_id) REFERENCES anvil.artifacts(project_id,id),
 FOREIGN KEY(project_id,terminal_event_id) REFERENCES anvil.benchmark_attempt_events(project_id,id),
 CHECK(jsonb_typeof(hard_constraint_ids)='array' AND jsonb_typeof(unresolved_required_paths)='array')
);
ALTER TABLE anvil.benchmark_attempt_policy_outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE anvil.benchmark_attempt_policy_outcomes FORCE ROW LEVEL SECURITY;
CREATE POLICY project_scope ON anvil.benchmark_attempt_policy_outcomes USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id));
GRANT SELECT,INSERT ON anvil.benchmark_attempt_policy_outcomes TO anvil_app;
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.benchmark_attempt_policy_outcomes FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
CREATE FUNCTION anvil.guard_attempt_policy_outcome() RETURNS trigger LANGUAGE plpgsql AS $$
 DECLARE definition jsonb; unresolved text[]; BEGIN
 SELECT task.content INTO definition FROM anvil.benchmark_offline_runtime rt
 JOIN anvil.benchmark_cell_attempts a ON a.project_id=rt.project_id AND a.id=rt.attempt_id
 JOIN anvil.benchmark_cells cell ON cell.project_id=a.project_id AND cell.id=a.cell_id
 JOIN anvil.revisions task ON task.project_id=cell.project_id AND task.id=cell.task_revision_id
 JOIN anvil.benchmark_attempt_events event ON event.project_id=rt.project_id AND event.id=NEW.terminal_event_id
 WHERE rt.project_id=NEW.project_id AND rt.attempt_id=NEW.attempt_id AND rt.state='captured'
 AND rt.fence=NEW.fence AND rt.report_artifact_id=NEW.report_artifact_id
 AND event.attempt_id=rt.attempt_id AND event.fence=rt.fence AND event.sealed_output_artifact_id=rt.output_artifact_id AND event.state IN ('completed','model_failed');
 IF definition IS NULL THEN RAISE EXCEPTION 'policy outcome requires its exact captured attempt';END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(definition->'outputs') declared
 WHERE NOT EXISTS(SELECT 1 FROM anvil.benchmark_captured_outputs output
 WHERE output.project_id=NEW.project_id AND output.attempt_id=NEW.attempt_id AND output.fence=NEW.fence
 AND output.path=declared->>'path' AND output.required=(declared->>'required')::boolean))
 THEN RAISE EXCEPTION 'terminal policy requires complete declared deliverable custody'; END IF;
 IF EXISTS(SELECT 1 FROM jsonb_array_elements_text(NEW.hard_constraint_ids) AS item(violated)
 WHERE NOT EXISTS(SELECT 1 FROM jsonb_array_elements(definition->'constraints') declared
 WHERE declared->>'id'=violated AND (declared->>'hard_failure')::boolean))
 THEN RAISE EXCEPTION 'whole-task zero requires an explicitly frozen hard safety constraint';END IF;
 SELECT coalesce(array_agg(path ORDER BY path),ARRAY[]::text[]) INTO unresolved FROM anvil.benchmark_captured_outputs output
 WHERE output.project_id=NEW.project_id AND output.attempt_id=NEW.attempt_id AND output.required AND output.outcome<>'captured'
 AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements(definition->'criteria') criterion WHERE criterion->>'output_path'=output.path);
 IF unresolved IS DISTINCT FROM ARRAY(SELECT path FROM jsonb_array_elements_text(NEW.unresolved_required_paths) AS item(path) ORDER BY path)
 THEN RAISE EXCEPTION 'unmapped required-output absence must remain explicitly unresolved';END IF;
 IF EXISTS(SELECT 1 FROM anvil.benchmark_attempt_events event WHERE event.id=NEW.terminal_event_id
 AND ((cardinality(unresolved)>0 AND event.validity<>'unresolved') OR (cardinality(unresolved)=0 AND event.validity<>'valid')))
 THEN RAISE EXCEPTION 'terminal validity must reflect unresolved required-output policy';END IF;
 RETURN NEW;END $$;
CREATE TRIGGER exact_policy BEFORE INSERT ON anvil.benchmark_attempt_policy_outcomes FOR EACH ROW EXECUTE FUNCTION anvil.guard_attempt_policy_outcome();
CREATE FUNCTION anvil.require_terminal_policy_outcome() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
 IF NEW.state IN ('completed','model_failed') AND EXISTS(
 SELECT 1 FROM anvil.benchmark_cell_attempts attempt
 JOIN anvil.benchmark_cells cell ON cell.project_id=attempt.project_id AND cell.id=attempt.cell_id
 JOIN anvil.benchmark_comparisons comparison ON comparison.project_id=cell.project_id AND comparison.run_id=cell.run_id
 JOIN anvil.benchmark_protocol_bindings binding ON binding.project_id=comparison.project_id AND binding.protocol_revision_id=comparison.protocol_revision_id
 WHERE attempt.project_id=NEW.project_id AND attempt.id=NEW.attempt_id)
 AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_attempt_policy_outcomes outcome
 WHERE outcome.project_id=NEW.project_id AND outcome.terminal_event_id=NEW.id AND outcome.attempt_id=NEW.attempt_id)
 THEN RAISE EXCEPTION 'terminal comparison evidence requires an exact frozen policy outcome'; END IF;
 RETURN NULL; END $$;
CREATE CONSTRAINT TRIGGER terminal_policy AFTER INSERT ON anvil.benchmark_attempt_events
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION anvil.require_terminal_policy_outcome();
INSERT INTO anvil.schema_versions(version) VALUES(58);
