-- D-054 (owner, 24 Nov 2026: "Flag, exclude from score"): a case episode the provider ended with refusals is a flagged,
-- non-model outcome. Its grader output for a scoring pass is kept here, read-only, instead of in episode_scores and
-- criterion_receipts, so no score, pass rate or leaderboard counts it. Additive only: one new append-only table.
CREATE TABLE scoring.refused_episodes(
 episode_id text NOT NULL REFERENCES runs.episodes, pass_id uuid NOT NULL REFERENCES scoring.scoring_passes,
 workspace_id uuid NOT NULL, refusal jsonb NOT NULL, would_score numeric, would_pass boolean,
 failed_criteria text[] NOT NULL, receipts jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (episode_id, pass_id));
CREATE TRIGGER refused_episodes_final BEFORE UPDATE OR DELETE ON scoring.refused_episodes
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();
ALTER TABLE scoring.refused_episodes ENABLE ROW LEVEL SECURITY;
CREATE POLICY workspace_isolation ON scoring.refused_episodes USING (workspace_id = infra.current_workspace())
 WITH CHECK (workspace_id = infra.current_workspace());
GRANT SELECT, INSERT ON scoring.refused_episodes TO anvil_app;
