-- Studio's test channel (registry record channel "test"): mirrored so RL Gym lets only test-only projects bind such a
-- version, keeps it off leaderboards and labels it TEST. Additive: one nullable column; every mirrored release keeps NULL.
ALTER TABLE catalog.environment_versions ADD COLUMN channel text;
