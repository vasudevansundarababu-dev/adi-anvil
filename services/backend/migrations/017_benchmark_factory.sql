ALTER TABLE anvil.resources DROP CONSTRAINT resources_kind_check;
ALTER TABLE anvil.resources ADD CONSTRAINT resources_kind_check CHECK(kind IN
 ('objective','case','task','rubric','suite','protocol','finding','report','release',
 'sales_kit','candidate','task_profile','benchmark','recommendation'));
INSERT INTO anvil.schema_versions(version) VALUES(17);
