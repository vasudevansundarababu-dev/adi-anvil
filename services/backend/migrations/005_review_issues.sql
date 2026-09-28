CREATE TABLE anvil.review_issues (
 id uuid PRIMARY KEY, project_id uuid NOT NULL, episode_id uuid NOT NULL,
 reported_by uuid NOT NULL REFERENCES anvil.users(id), code text NOT NULL,
 rationale text NOT NULL, status text NOT NULL DEFAULT 'open' CHECK(status IN ('open','resolved')),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(project_id,id),
 FOREIGN KEY(project_id,episode_id) REFERENCES anvil.episodes(project_id,id)
);
CREATE UNIQUE INDEX one_open_issue_per_episode ON anvil.review_issues(episode_id) WHERE status='open';
CREATE TABLE anvil.review_resolutions (
 id uuid PRIMARY KEY, project_id uuid NOT NULL, issue_id uuid NOT NULL UNIQUE,
 episode_id uuid NOT NULL, resolved_by uuid NOT NULL REFERENCES anvil.users(id),
 decision text NOT NULL CHECK(decision IN ('invalid','resume_review')), rationale text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(project_id,id),
 FOREIGN KEY(project_id,issue_id) REFERENCES anvil.review_issues(project_id,id),
 FOREIGN KEY(project_id,episode_id) REFERENCES anvil.episodes(project_id,id)
);
ALTER TABLE anvil.episodes ADD invalidity_resolution_id uuid;
ALTER TABLE anvil.episodes ADD FOREIGN KEY(project_id,invalidity_resolution_id) REFERENCES anvil.review_resolutions(project_id,id);
ALTER TABLE anvil.episodes ADD CHECK(final_assessment_id IS NULL OR invalidity_resolution_id IS NULL);
CREATE TRIGGER immutable BEFORE UPDATE OR DELETE ON anvil.review_resolutions FOR EACH ROW EXECUTE FUNCTION anvil.immutable();
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['review_issues','review_resolutions'] LOOP
 EXECUTE format('ALTER TABLE anvil.%I ENABLE ROW LEVEL SECURITY',t);
 EXECUTE format('ALTER TABLE anvil.%I FORCE ROW LEVEL SECURITY',t);
 EXECUTE format('CREATE POLICY project_scope ON anvil.%I USING(anvil.in_scope(project_id)) WITH CHECK(anvil.in_scope(project_id))',t);
 EXECUTE format('GRANT SELECT,INSERT,UPDATE ON anvil.%I TO anvil_app',t);
 END LOOP;
END $$;
REVOKE UPDATE ON anvil.review_resolutions FROM anvil_app;
INSERT INTO anvil.schema_versions(version) VALUES(5);
