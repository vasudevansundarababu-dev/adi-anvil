-- Preserve original publication bytes; recognize only the two published spellings.
-- Migration130 is already deployed and remains immutable.
DO $$ DECLARE body text;field text;old text;new text;BEGIN
 SELECT pg_get_functiondef('anvil.check_offline_publication()'::regprocedure) INTO body;
 FOREACH field IN ARRAY ARRAY['status','publication_status'] LOOP
  old=format('((b->''record'') ? %L AND b#>>%L IS DISTINCT FROM ''published'')',field,'{record,'||field||'}');
  new=format('((b->''record'') ? %L AND (b#>>%L IS NULL OR b#>>%L NOT IN (''published'',''PUBLISHED'')))',
             field,'{record,'||field||'}','{record,'||field||'}');
  IF strpos(body,old)=0 THEN RAISE EXCEPTION 'exact original offline publication status guard required';END IF;
  body=replace(body,old,new);
 END LOOP;
 EXECUTE body;
END $$;
INSERT INTO anvil.schema_versions(version) VALUES(131);
