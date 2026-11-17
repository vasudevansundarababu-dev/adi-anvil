-- Fail closed on malformed internal policy JSON; no authority expansion.
CREATE OR REPLACE FUNCTION anvil.guard_report_authority() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE actor uuid; administrator boolean; result_hash text; BEGIN
 actor:=nullif(current_setting('anvil.user',true),'')::uuid;
 SELECT EXISTS(SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id AND u.active WHERE m.project_id=NEW.project_id AND m.user_id=actor AND m.active AND m.role='admin') INTO administrator;
 IF TG_TABLE_NAME='benchmark_report_policies' THEN
  IF NEW.created_by IS DISTINCT FROM actor OR NOT administrator THEN RAISE EXCEPTION 'authenticated Admin policy author required';END IF;
  RETURN NEW;
 END IF;
 IF NEW.actor_id IS DISTINCT FROM actor THEN RAISE EXCEPTION 'actual authenticated actor required';END IF;
 IF NEW.target_kind='rehearsal' THEN
  SELECT result->>'result_sha256' INTO result_hash FROM anvil.benchmark_rehearsals WHERE id=NEW.target_id AND project_id=NEW.project_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'exact rehearsal target required';END IF;
 ELSE
  PERFORM 1 FROM anvil.benchmark_comparisons WHERE run_id=NEW.target_id AND project_id=NEW.project_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'exact comparison target required';END IF;
 END IF;
 IF TG_TABLE_NAME='benchmark_report_authorizations' THEN
  IF NEW.admin_run_exempt AND NOT administrator THEN RAISE EXCEPTION 'actual Admin run required';END IF;
  IF jsonb_typeof(NEW.policy) IS DISTINCT FROM 'object' OR NOT(NEW.policy ?& ARRAY['version','policy_id','required_reviewers','admin_run_exempt','admin_approval_exempt','policy_sha256','revision'])
   OR NEW.policy-ARRAY['version','policy_id','required_reviewers','admin_run_exempt','admin_approval_exempt','policy_sha256','revision']<>'{}'::jsonb
   THEN RAISE EXCEPTION 'complete exact report policy object required';END IF;
  IF jsonb_typeof(NEW.policy->'version') IS DISTINCT FROM 'number' OR NEW.policy->>'version' IS DISTINCT FROM '2'
   OR jsonb_typeof(NEW.policy->'required_reviewers') IS DISTINCT FROM 'number' OR (NEW.policy->>'required_reviewers') !~ '^(0|[1-9]|10)$'
   OR jsonb_typeof(NEW.policy->'admin_run_exempt') IS DISTINCT FROM 'boolean' OR NEW.policy->>'admin_run_exempt' IS DISTINCT FROM 'true'
   OR jsonb_typeof(NEW.policy->'admin_approval_exempt') IS DISTINCT FROM 'boolean' OR NEW.policy->>'admin_approval_exempt' IS DISTINCT FROM 'true'
   OR jsonb_typeof(NEW.policy->'policy_sha256') IS DISTINCT FROM 'string' OR NEW.policy->>'policy_sha256' !~ '^[a-f0-9]{64}$'
   OR NEW.policy_sha256 IS DISTINCT FROM NEW.policy->>'policy_sha256'
   OR jsonb_typeof(NEW.policy->'revision') IS DISTINCT FROM 'string'
   THEN RAISE EXCEPTION 'typed bounded frozen policy required';END IF;
  IF jsonb_typeof(NEW.policy->'policy_id') NOT IN ('null','string') THEN RAISE EXCEPTION 'typed policy revision required';END IF;
  IF jsonb_typeof(NEW.policy->'policy_id')='string' THEN
   IF NEW.policy->>'policy_id' !~ '^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$' OR NEW.policy->>'revision' IS DISTINCT FROM NEW.policy->>'policy_id' THEN RAISE EXCEPTION 'exact policy UUID revision required';END IF;
  ELSIF NEW.policy->>'revision' IS DISTINCT FROM 'default-v2' THEN RAISE EXCEPTION 'exact default revision required';END IF;
  IF NEW.policy->>'policy_id' IS NULL THEN
   IF NEW.policy->>'required_reviewers'<>'1' THEN RAISE EXCEPTION 'safe default report policy required';END IF;
  ELSIF NOT EXISTS(SELECT 1 FROM anvil.benchmark_report_policies p WHERE p.id=(NEW.policy->>'policy_id')::uuid AND p.project_id=NEW.project_id AND p.required_reviewers=(NEW.policy->>'required_reviewers')::integer) THEN RAISE EXCEPTION 'exact frozen policy revision required';END IF;
 ELSIF TG_TABLE_NAME='benchmark_report_admin_executions' THEN
  IF NOT administrator OR result_hash IS NULL THEN RAISE EXCEPTION 'actual Admin completed execution required';END IF;
 ELSE
  IF NEW.target_kind='rehearsal' AND result_hash IS DISTINCT FROM NEW.result_sha256 THEN RAISE EXCEPTION 'exact stored rehearsal hash required';END IF;
  IF NEW.target_kind='comparison' AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_score_revisions WHERE run_id=NEW.target_id AND project_id=NEW.project_id AND projection_sha256=NEW.result_sha256) THEN RAISE EXCEPTION 'exact stored score revision required';END IF;
  IF NEW.decision='admin_approved' THEN
   IF NOT administrator THEN RAISE EXCEPTION 'authenticated Admin approval required';END IF;
  ELSIF NOT EXISTS(SELECT 1 FROM anvil.benchmark_private_assignments a WHERE a.project_id=NEW.project_id AND a.id=NEW.assignment_id AND a.user_id=actor AND a.scope='evaluation_review' AND a.artifact_id IS NULL AND a.expires_at>now() AND NOT EXISTS(SELECT 1 FROM anvil.benchmark_private_revocations r WHERE r.assignment_id=a.id)) THEN RAISE EXCEPTION 'actual current human duty required';END IF;
 END IF;
 RETURN NEW;END $$;
INSERT INTO anvil.schema_versions(version) VALUES('063') ON CONFLICT DO NOTHING;
