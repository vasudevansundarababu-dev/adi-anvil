-- RL Gym v2, live models (built behind the owner's approval; no live call without one).
-- An approval names the exact provider and model (and the pinned Hugging Face revision), a per-run cap and a total cap,
-- the prices the approver verified, who approved and when it expires. A live run, key test, probe, judge or generator
-- call needs a matching approval that is not expired or revoked. Approvals are append-only except revocation.
CREATE TABLE systems.live_approvals(
 id text NOT NULL, workspace_id uuid NOT NULL,
 provider text NOT NULL CHECK (provider IN ('anthropic','openai','google','vertex','huggingface')),
 model_id text NOT NULL CHECK (length(trim(model_id)) > 0),
 hf_revision text CHECK (hf_revision IS NULL OR hf_revision ~ '^[0-9a-f]{40}$'),
 uses text[] NOT NULL CHECK (uses <@ ARRAY['agent','judge','generator','probe','key_test']::text[] AND cardinality(uses) > 0),
 per_run_cap_usd numeric NOT NULL CHECK (per_run_cap_usd > 0),
 total_cap_usd numeric NOT NULL CHECK (total_cap_usd >= per_run_cap_usd),
 price_in_per_mtok_usd numeric NOT NULL CHECK (price_in_per_mtok_usd >= 0),
 price_out_per_mtok_usd numeric NOT NULL CHECK (price_out_per_mtok_usd >= 0),
 prices_note text NOT NULL CHECK (length(trim(prices_note)) > 0),
 approved_by text NOT NULL, approved_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL,
 revoked_at timestamptz, revoked_by text, revoke_reason text,
 CHECK (expires_at > approved_at),
 CHECK (provider <> 'huggingface' OR hf_revision IS NOT NULL),
 PRIMARY KEY (workspace_id, id));
CREATE FUNCTION systems.live_approval_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.id, NEW.workspace_id, NEW.provider, NEW.model_id, NEW.hf_revision, NEW.uses, NEW.per_run_cap_usd,
     NEW.total_cap_usd, NEW.price_in_per_mtok_usd, NEW.price_out_per_mtok_usd, NEW.prices_note, NEW.approved_by,
     NEW.approved_at, NEW.expires_at) IS DISTINCT FROM
    (OLD.id, OLD.workspace_id, OLD.provider, OLD.model_id, OLD.hf_revision, OLD.uses, OLD.per_run_cap_usd,
     OLD.total_cap_usd, OLD.price_in_per_mtok_usd, OLD.price_out_per_mtok_usd, OLD.prices_note, OLD.approved_by,
     OLD.approved_at, OLD.expires_at) OR OLD.revoked_at IS NOT NULL THEN
  RAISE EXCEPTION 'a live approval is final; only an unrevoked approval can be revoked';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER live_approval_final BEFORE UPDATE ON systems.live_approvals
 FOR EACH ROW EXECUTE FUNCTION systems.live_approval_guard();
CREATE TRIGGER live_approval_no_delete BEFORE DELETE ON systems.live_approvals
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();

-- Every live call, attempted or not answered, with its tokens and cost (append-only). Spend against an approval is
-- the sum of its rows; an ambiguous dispatch (sent, no answer) is counted at its maximum cost and never retried.
CREATE TABLE systems.live_calls(
 id bigserial PRIMARY KEY, workspace_id uuid NOT NULL, approval_id text NOT NULL,
 use text NOT NULL CHECK (use IN ('agent','judge','generator','probe','key_test')),
 run_id text, episode_id text, provider text NOT NULL, model_id text NOT NULL,
 request_id text, status text NOT NULL CHECK (status IN ('ok','error','ambiguous','refused')),
 tokens_in int NOT NULL DEFAULT 0 CHECK (tokens_in >= 0), tokens_out int NOT NULL DEFAULT 0 CHECK (tokens_out >= 0),
 cost_usd numeric NOT NULL DEFAULT 0 CHECK (cost_usd >= 0), note text,
 at timestamptz NOT NULL DEFAULT now(),
 FOREIGN KEY (workspace_id, approval_id) REFERENCES systems.live_approvals(workspace_id, id));
CREATE INDEX live_calls_approval ON systems.live_calls (workspace_id, approval_id);
CREATE INDEX live_calls_run ON systems.live_calls (run_id);
CREATE TRIGGER live_calls_append_only BEFORE UPDATE OR DELETE ON systems.live_calls
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();

-- Which approval a run uses per live model, frozen at admission.
ALTER TABLE runs.runs ADD COLUMN live_approvals jsonb;

DO $$
DECLARE t text;
BEGIN
 FOREACH t IN ARRAY ARRAY['systems.live_approvals','systems.live_calls'] LOOP
  EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', t);
  EXECUTE format('CREATE POLICY workspace_isolation ON %s USING (workspace_id = infra.current_workspace()) WITH CHECK (workspace_id = infra.current_workspace())', t);
 END LOOP;
END $$;
GRANT SELECT, INSERT, UPDATE ON systems.live_approvals TO anvil_app;
GRANT SELECT, INSERT ON systems.live_calls TO anvil_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA systems TO anvil_app;
