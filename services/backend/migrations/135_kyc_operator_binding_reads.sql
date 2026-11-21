-- Read-only public runtime metadata for the enrolled disjoint policy operator.
-- No private expected answers/scenarios, no application writes, no seeded login.
DO $$ DECLARE runtime name;BEGIN
 IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anvil_kyc_qualifier'
  AND (rolcanlogin OR rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole OR rolreplication))
 THEN RAISE EXCEPTION 'restricted qualifier role required';END IF;
 FOREACH runtime IN ARRAY ARRAY['anvil_app','anvil_worker','anvil_golden_scheduler','anvil_golden_grader',
   'anvil_kyc_expectation_loader','anvil_kyc_context_owner','anvil_private_grade_owner'] LOOP
  IF pg_has_role(runtime,'anvil_kyc_qualifier','MEMBER')
   OR pg_has_role('anvil_kyc_qualifier',runtime,'MEMBER')
  THEN RAISE EXCEPTION 'disjoint qualifier read capability required';END IF;
 END LOOP;
END $$;
GRANT USAGE ON SCHEMA banking TO anvil_kyc_qualifier;
DO $$ DECLARE schema_name text;table_name text;BEGIN
 FOR schema_name,table_name IN SELECT * FROM (VALUES
  ('banking','anvil_imports'),('banking','packs'),('banking','applications'),
  ('anvil','environment_versions'),('anvil','environment_task_bindings'),
  ('anvil','evaluator_configurations'),('anvil','evaluator_validation_receipts'),('anvil','evaluator_revocations')) AS t(s,n)
 LOOP
  IF NOT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname=schema_name AND c.relname=table_name AND c.relrowsecurity AND c.relforcerowsecurity)
  THEN RAISE EXCEPTION 'forced public binding row security required';END IF;
  EXECUTE format('GRANT SELECT ON %I.%I TO anvil_kyc_qualifier',schema_name,table_name);
  EXECUTE format('CREATE POLICY kyc_operator_binding_read ON %I.%I FOR SELECT TO anvil_kyc_qualifier USING(anvil.kyc_policy_operator_scope(project_id))',schema_name,table_name);
  -- Existing PUBLIC policies are OR alternatives. Enrollment must also be an
  -- AND requirement, including for a LOGIN with forged project/Admin GUCs.
  EXECUTE format('CREATE POLICY kyc_operator_binding_enrollment ON %I.%I AS RESTRICTIVE FOR SELECT TO anvil_kyc_qualifier USING(anvil.kyc_policy_operator_scope(project_id))',schema_name,table_name);
 END LOOP;
END $$;
INSERT INTO anvil.schema_versions(version) VALUES(135);
