-- RL Gym v2: the registry mirror keeps sequence numbers, event ids and cursors per registry, so switching the RL Gym
-- from the local Studio stub (8211) to the real local Studio (8060) neither drops Studio's first events as duplicates
-- nor confuses their event ids. Existing rows came from the stub.
ALTER TABLE catalog.registry_events ADD COLUMN registry text NOT NULL DEFAULT 'http://127.0.0.1:8211';
ALTER TABLE catalog.registry_events ALTER COLUMN registry DROP DEFAULT;
ALTER TABLE catalog.registry_events DROP CONSTRAINT registry_events_pkey;
ALTER TABLE catalog.registry_events DROP CONSTRAINT registry_events_event_id_key;
ALTER TABLE catalog.registry_events ADD PRIMARY KEY (registry, seq);
ALTER TABLE catalog.registry_events ADD CONSTRAINT registry_events_event_id UNIQUE (registry, event_id);
UPDATE catalog.registry_cursor SET consumer = 'rlgym-catalog@http://127.0.0.1:8211' WHERE consumer = 'rlgym-catalog';
-- Which registry each mirrored version came from; a later registry may only confirm the same identity.
ALTER TABLE catalog.environment_versions ADD COLUMN registry text NOT NULL DEFAULT 'http://127.0.0.1:8211';
ALTER TABLE catalog.environment_versions ALTER COLUMN registry DROP DEFAULT;
-- A version's state sequence belongs to its registry: it may restart only when a different registry confirms the same
-- identity (the identity columns stay final).
CREATE OR REPLACE FUNCTION catalog.environment_version_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.id, NEW.contract_id, NEW.version, NEW.spec_sha256, NEW.image_digest, NEW.seed_ref, NEW.seed_sha256,
     NEW.seed_family) IS DISTINCT FROM
    (OLD.id, OLD.contract_id, OLD.version, OLD.spec_sha256, OLD.image_digest, OLD.seed_ref, OLD.seed_sha256,
     OLD.seed_family) THEN
  RAISE EXCEPTION 'released environment version % is final', OLD.id;
 END IF;
 IF NEW.registry = OLD.registry AND NEW.state_seq < OLD.state_seq THEN
  RAISE EXCEPTION 'registry sequence moved backwards';
 END IF;
 RETURN NEW;
END $$;
