-- A lock capability, not general UPDATE authority over projects. The caller
-- must already possess the disjoint scheduler LOGIN and current project/user.
CREATE FUNCTION anvil.golden_scheduler_project_fence(p uuid) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE principal record;parent_count integer;locked_project uuid;
BEGIN
 IF pg_catalog.current_setting('transaction_isolation')<>'read committed'
 THEN RETURN false;END IF;
 SELECT r.* INTO principal FROM pg_catalog.pg_roles r WHERE r.rolname=session_user;
 IF principal.oid IS NULL OR NOT principal.rolcanlogin OR principal.rolsuper
  OR principal.rolbypassrls OR principal.rolcreatedb OR principal.rolcreaterole
  OR principal.rolreplication THEN RETURN false;END IF;
 SELECT count(*) INTO parent_count FROM pg_catalog.pg_auth_members m
  WHERE m.member=principal.oid;
 IF parent_count<>1 OR NOT EXISTS(
  SELECT 1 FROM pg_catalog.pg_auth_members m JOIN pg_catalog.pg_roles r ON r.oid=m.roleid
  WHERE m.member=principal.oid AND r.rolname='anvil_golden_scheduler')
  OR NOT pg_catalog.pg_has_role(session_user,'anvil_golden_scheduler','MEMBER')
  OR pg_catalog.pg_has_role(session_user,'anvil_app','MEMBER')
  OR pg_catalog.pg_has_role(session_user,'anvil_worker','MEMBER')
  OR pg_catalog.pg_has_role(session_user,'anvil_golden_grader','MEMBER')
  OR pg_catalog.has_table_privilege(session_user,'banking_private.expectations','SELECT')
  OR p::text IS DISTINCT FROM pg_catalog.current_setting('anvil.project',true)
  OR nullif(pg_catalog.current_setting('anvil.user',true),'') IS NULL
 THEN RETURN false;END IF;
 -- Refuse an unauthorized lock before taking it, then reread membership after
 -- the project fence to observe a revocation that committed while waiting.
 IF NOT EXISTS(SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id
  WHERE m.project_id=p AND m.user_id::text=pg_catalog.current_setting('anvil.user',true)
   AND m.active AND u.active AND m.role IN('admin','rl-engineer'))
 THEN RETURN false;END IF;
 -- Match administrative revocation lock order: project first, then membership.
 SELECT x.id INTO locked_project FROM anvil.projects x WHERE x.id=p FOR KEY SHARE;
 IF locked_project IS NULL THEN RETURN false;END IF;
 RETURN EXISTS(SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id
  WHERE m.project_id=p AND m.user_id::text=pg_catalog.current_setting('anvil.user',true)
   AND m.active AND u.active AND m.role IN('admin','rl-engineer'));
END $$;
REVOKE ALL ON FUNCTION anvil.golden_scheduler_project_fence(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION anvil.golden_scheduler_project_fence(uuid) TO anvil_golden_scheduler;
INSERT INTO anvil.schema_versions(version) VALUES(132);
