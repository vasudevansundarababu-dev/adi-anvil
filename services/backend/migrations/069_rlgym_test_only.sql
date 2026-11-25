-- Authoring's test-only marker (Project.testOnly, exported as `test_only: true`). Additive: one column, false for every
-- existing project. Test-only projects, their suites, runs and reports are labelled TEST and never on a leaderboard.
ALTER TABLE projects.projects ADD COLUMN test_only boolean NOT NULL DEFAULT false;
