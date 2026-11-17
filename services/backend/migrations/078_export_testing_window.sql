-- Legacy hour credentials retain original expiry. No pilot/budget changes.
ALTER TABLE anvil.dataset_export_clients
 ADD COLUMN lifetime_mode text NOT NULL DEFAULT 'hours'
 CHECK(lifetime_mode IN('hours','testing_window')),
 ADD COLUMN pilot_environment text CHECK(pilot_environment IN('qa','staging')),
 ADD COLUMN pilot_end_at timestamptz,
 ADD CONSTRAINT export_testing_window_bound CHECK(
 (lifetime_mode='hours' AND pilot_environment IS NULL AND pilot_end_at IS NULL)
 OR (lifetime_mode='testing_window' AND pilot_environment IS NOT NULL
 AND pilot_end_at IS NOT NULL AND expires_at=pilot_end_at
 AND pilot_end_at<='2026-12-11T05:48:04Z'));
