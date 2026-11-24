-- E-005 §2.2: a suite can pin another environment version as an experiment (one person, with a reason). Such a suite
-- is marked "Experiment: not leaderboard-eligible". Widens one CHECK to allow source 'experiment'; no row changes.
ALTER TABLE suites.suite_bindings DROP CONSTRAINT IF EXISTS suite_bindings_source_check;
ALTER TABLE suites.suite_bindings ADD CONSTRAINT suite_bindings_source_check
  CHECK (source IN ('project_default','ai_suggestion','custom','experiment'));
ALTER TABLE suites.suite_bindings ADD CONSTRAINT suite_bindings_experiment_reason
  CHECK (source <> 'experiment' OR length(trim(coalesce(reason,''))) > 0);
