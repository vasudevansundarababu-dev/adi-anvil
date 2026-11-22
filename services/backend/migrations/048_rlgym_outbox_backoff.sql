-- RL Gym v2: outbox deliveries wait between retries, and a permanent refusal is not retried.
ALTER TABLE infra.outbox ADD COLUMN next_attempt_at timestamptz;
ALTER TABLE infra.outbox ADD COLUMN refused boolean NOT NULL DEFAULT false;
