-- RL Gym v2 foundation (work packages 2.1-2.4): admin, catalog, projects and infra schemas.
-- One PostgreSQL schema per module (rl-gym/ARCHITECTURE.md 6). Cross-schema references are IDs only.
-- The existing anvil schema is untouched; RL Gym v2 sits next to it behind RLGYM_V2=1.
CREATE SCHEMA IF NOT EXISTS admin;
CREATE SCHEMA IF NOT EXISTS catalog;
CREATE SCHEMA IF NOT EXISTS projects;
CREATE SCHEMA IF NOT EXISTS infra;

-- Generic guards -----------------------------------------------------------------------------
CREATE FUNCTION infra.forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'immutable record: % on %.%', TG_OP, TG_TABLE_SCHEMA, TG_TABLE_NAME; END $$;

-- Current workspace for row-level security; set per transaction by the API after it has checked
-- the person's active membership or the service client's key.
CREATE FUNCTION infra.current_workspace() RETURNS uuid LANGUAGE sql STABLE AS $$
 SELECT nullif(current_setting('rlgym.workspace', true), '')::uuid $$;

-- admin --------------------------------------------------------------------------------------
CREATE TABLE admin.workspaces(
 id uuid PRIMARY KEY, slug text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}$'),
 name text NOT NULL, tier text NOT NULL CHECK (tier IN ('dev','staging','prod')),
 legacy_org_id uuid, created_at timestamptz NOT NULL DEFAULT now());
-- Profiles are labels (Admin, RL Engineer, Viewer); binding_approver is the one server-enforced flag.
CREATE TABLE admin.users(
 id uuid NOT NULL, workspace_id uuid NOT NULL REFERENCES admin.workspaces,
 email text NOT NULL, name text NOT NULL,
 profile text NOT NULL CHECK (profile IN ('admin','rl_engineer','viewer')),
 binding_approver boolean NOT NULL DEFAULT false,
 status text NOT NULL CHECK (status IN ('invited','active','removed')),
 last_seen_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (workspace_id, id), UNIQUE (workspace_id, email));
CREATE TABLE admin.audit_events(
 id bigserial PRIMARY KEY, workspace_id uuid NOT NULL, actor text NOT NULL,
 actor_kind text NOT NULL CHECK (actor_kind IN ('person','service','system')),
 action text NOT NULL, subject text NOT NULL, reason text, details jsonb NOT NULL DEFAULT '{}',
 at timestamptz NOT NULL DEFAULT now());
CREATE TRIGGER audit_append_only BEFORE UPDATE OR DELETE ON admin.audit_events
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();
-- To do items: opened and closed only by events (ARCHITECTURE 10.1).
CREATE TABLE admin.notifications(
 id text PRIMARY KEY, workspace_id uuid NOT NULL,
 kind text NOT NULL, todo_group text NOT NULL CHECK (todo_group IN
  ('ready_to_run','bindings','review','import_export','studio_inbox')),
 project_id text, subject text NOT NULL, title text NOT NULL, reason text NOT NULL,
 action_label text, link text NOT NULL, severity text NOT NULL DEFAULT 'ok' CHECK (severity IN ('ok','warn','bad')),
 audience text NOT NULL CHECK (audience IN ('workspace','binding_approvers','user')), user_id uuid,
 opened_by_event text NOT NULL, closed_by_event text,
 created_at timestamptz NOT NULL DEFAULT now(), closed_at timestamptz);
CREATE INDEX ON admin.notifications (workspace_id) WHERE closed_at IS NULL;
CREATE UNIQUE INDEX notifications_one_open ON admin.notifications (workspace_id, kind, subject) WHERE closed_at IS NULL;

-- infra --------------------------------------------------------------------------------------
CREATE TABLE infra.outbox(
 id uuid PRIMARY KEY, workspace_id uuid, topic text NOT NULL, key text NOT NULL,
 payload jsonb NOT NULL, destination text NOT NULL DEFAULT 'internal'
  CHECK (destination IN ('internal','studio','forge','registry')),
 attempts int NOT NULL DEFAULT 0, last_error text,
 created_at timestamptz NOT NULL DEFAULT now(), published_at timestamptz);
CREATE INDEX ON infra.outbox (created_at) WHERE published_at IS NULL;
CREATE TABLE infra.inbox(event_id text NOT NULL, consumer text NOT NULL, processed_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (consumer, event_id));
CREATE TABLE infra.idempotency_keys(
 client text NOT NULL, key text NOT NULL, route text NOT NULL, request_sha256 char(64) NOT NULL,
 response jsonb NOT NULL, status int NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (client, route, key));

-- catalog: environment versions mirror Studio's central registry (registry consumer only) ------
CREATE TABLE catalog.environment_versions(
 id text PRIMARY KEY, contract_id text NOT NULL, version int NOT NULL,
 spec_sha256 char(64) NOT NULL, image_digest text NOT NULL,
 seed_ref text NOT NULL, seed_sha256 char(64) NOT NULL, seed_family text NOT NULL,
 runtime_profile text NOT NULL, tools int NOT NULL,
 release_id text, released_at timestamptz, reset_strategy text, operations jsonb,
 schema_tables jsonb NOT NULL DEFAULT '[]', image_recipe jsonb,
 state text NOT NULL CHECK (state IN ('registered','qualified','failed','deprecated','revoked','deleted')),
 state_reason text, state_seq bigint NOT NULL,
 case_catalog jsonb, mirrored_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (contract_id, version));
CREATE FUNCTION catalog.environment_version_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.id, NEW.contract_id, NEW.version, NEW.spec_sha256, NEW.image_digest, NEW.seed_ref, NEW.seed_sha256,
     NEW.seed_family) IS DISTINCT FROM
    (OLD.id, OLD.contract_id, OLD.version, OLD.spec_sha256, OLD.image_digest, OLD.seed_ref, OLD.seed_sha256,
     OLD.seed_family) THEN
  RAISE EXCEPTION 'released environment version % is final', OLD.id;
 END IF;
 IF NEW.state_seq < OLD.state_seq THEN RAISE EXCEPTION 'registry sequence moved backwards'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER environment_version_final BEFORE UPDATE ON catalog.environment_versions
 FOR EACH ROW EXECUTE FUNCTION catalog.environment_version_guard();
CREATE TRIGGER environment_version_no_delete BEFORE DELETE ON catalog.environment_versions
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();
CREATE TABLE catalog.registry_cursor(consumer text PRIMARY KEY, last_seq bigint NOT NULL,
 resynced_at timestamptz, updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE catalog.registry_events(seq bigint PRIMARY KEY, event_id text NOT NULL UNIQUE, type text NOT NULL,
 subject text NOT NULL, payload jsonb NOT NULL, received_at timestamptz NOT NULL DEFAULT now(), via text NOT NULL
 CHECK (via IN ('webhook','resync')));
CREATE TRIGGER registry_events_append_only BEFORE UPDATE OR DELETE ON catalog.registry_events
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();

-- catalog: evaluation frameworks and evaluator configurations, owned by the RL Gym (option B) --
CREATE TABLE catalog.framework_versions(
 id text PRIMARY KEY, runtime_id text NOT NULL CHECK (runtime_id IN ('zen','promptfoo','pramaana','python')),
 version text NOT NULL, image_digest text NOT NULL, evidence_types text[] NOT NULL,
 installed_locally boolean NOT NULL DEFAULT false, install_note text,
 state text NOT NULL CHECK (state IN ('registered','qualified','failed','deprecated','revoked')),
 state_reason text, state_changed_by text, state_changed_at timestamptz,
 created_by text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE (runtime_id, version));
CREATE TABLE catalog.evaluator_configurations(
 workspace_id uuid NOT NULL, id text NOT NULL, version int NOT NULL CHECK (version > 0),
 framework_version_id text NOT NULL REFERENCES catalog.framework_versions,
 capability text NOT NULL, criterion_id text NOT NULL, evidence_type text NOT NULL,
 verdict_vocabulary text[] NOT NULL DEFAULT '{pass,partial,fail,blocked}',
 weight numeric NOT NULL DEFAULT 1,
 config jsonb NOT NULL, config_sha256 char(64) NOT NULL,
 fix_of_version int, fix_reason text, fix_source text,
 known_cases jsonb NOT NULL, known_case_receipt_id text,
 source_template_id text NOT NULL, source_template_key text NOT NULL, source_template_version int NOT NULL,
 state text NOT NULL CHECK (state IN ('registered','qualified','failed','deprecated','revoked')),
 state_reason text, state_changed_by text, state_changed_at timestamptz, replaced_by_version int,
 created_by text NOT NULL CHECK (created_by IN ('studio','rlgym')),
 created_at timestamptz NOT NULL DEFAULT now(),
 CHECK (fix_of_version IS NULL OR (fix_reason IS NOT NULL AND created_by = 'rlgym')),
 PRIMARY KEY (workspace_id, id, version), UNIQUE (workspace_id, id, config_sha256));
CREATE FUNCTION catalog.evaluator_configuration_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.workspace_id, NEW.id, NEW.version, NEW.framework_version_id, NEW.capability, NEW.criterion_id,
     NEW.evidence_type, NEW.verdict_vocabulary, NEW.config, NEW.config_sha256, NEW.known_cases,
     NEW.fix_of_version, NEW.created_by) IS DISTINCT FROM
    (OLD.workspace_id, OLD.id, OLD.version, OLD.framework_version_id, OLD.capability, OLD.criterion_id,
     OLD.evidence_type, OLD.verdict_vocabulary, OLD.config, OLD.config_sha256, OLD.known_cases,
     OLD.fix_of_version, OLD.created_by) THEN
  RAISE EXCEPTION 'evaluator configuration version %:% never changes; create a new version', OLD.id, OLD.version;
 END IF;
 IF OLD.state = 'revoked' AND NEW.state <> 'revoked' THEN RAISE EXCEPTION 'revocation is final'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER evaluator_configuration_final BEFORE UPDATE ON catalog.evaluator_configurations
 FOR EACH ROW EXECUTE FUNCTION catalog.evaluator_configuration_guard();
CREATE TRIGGER evaluator_configuration_no_delete BEFORE DELETE ON catalog.evaluator_configurations
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();
CREATE TABLE catalog.qualification_receipts(
 receipt_id text PRIMARY KEY, workspace_id uuid,
 subject_kind text NOT NULL CHECK (subject_kind IN ('environment_version','evaluator_configuration','framework_version')),
 subject_id text NOT NULL, subject_version text NOT NULL,
 result text NOT NULL CHECK (result IN ('qualified','failed')),
 failure_class text CHECK (failure_class IS NULL OR failure_class IN ('environment_defect','infrastructure','evaluator_defect')),
 mode text NOT NULL, checks jsonb NOT NULL, receipt_sha256 char(64) NOT NULL, issued_at timestamptz NOT NULL DEFAULT now(),
 CHECK ((result = 'failed') = (failure_class IS NOT NULL)));
CREATE TRIGGER receipts_append_only BEFORE UPDATE OR DELETE ON catalog.qualification_receipts
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();
CREATE TABLE catalog.template_activations(
 workspace_id uuid NOT NULL, template_id text NOT NULL, version int NOT NULL,
 template_key text NOT NULL, name text NOT NULL, mode text NOT NULL CHECK (mode IN ('single_agent','multi_agent')),
 spec_sha256 char(64) NOT NULL, template_sha256 char(64) NOT NULL,
 forge_template_id text NOT NULL, forge_version int NOT NULL, studio_release text,
 default_bindings jsonb NOT NULL, workflow jsonb NOT NULL, case_dimensions jsonb NOT NULL,
 pass_mark numeric NOT NULL, checks jsonb NOT NULL,
 state text NOT NULL CHECK (state IN ('validated','active','blocked','revoked')), state_reason text,
 activated_at timestamptz, activated_by text NOT NULL,
 PRIMARY KEY (workspace_id, template_id, version));
CREATE TABLE catalog.template_criteria(
 workspace_id uuid NOT NULL, template_id text NOT NULL, version int NOT NULL, criterion_id text NOT NULL,
 capability text NOT NULL, skill_group text NOT NULL, weight numeric NOT NULL, is_gate boolean NOT NULL DEFAULT false,
 configuration_id text NOT NULL, evidence_type text NOT NULL, verdict_vocabulary text[] NOT NULL,
 PRIMARY KEY (workspace_id, template_id, version, criterion_id),
 FOREIGN KEY (workspace_id, template_id, version) REFERENCES catalog.template_activations);
-- Next-version inbox items the RL Gym sends to Studio (D17).
CREATE TABLE catalog.inbox_items(
 id text PRIMARY KEY, studio_id text UNIQUE,
 workspace_id uuid NOT NULL, project_id text, suite_version_id uuid,
 kind text NOT NULL CHECK (kind IN ('more_data','new_case_kind','environment_defect','evaluator_defect','template_wording')),
 template_id text NOT NULL, template_version int NOT NULL,
 environment_version_id text, evaluator_configuration text,
 summary text NOT NULL CHECK (length(trim(summary)) > 0), evidence jsonb NOT NULL,
 needed_by date, urgent boolean NOT NULL DEFAULT false,
 state text NOT NULL CHECK (state IN ('queued','sent','received','planned','released','declined','closed')),
 planned_version text, released_version text, decline_reason text,
 timeline jsonb NOT NULL DEFAULT '[]',
 sent_by text NOT NULL, sent_at timestamptz NOT NULL DEFAULT now());

-- projects -----------------------------------------------------------------------------------
CREATE TABLE projects.projects(
 workspace_id uuid NOT NULL, project_id text NOT NULL CHECK (project_id ~ '^prj_[a-z0-9]{4,40}$'),
 name text NOT NULL, template_id text NOT NULL, template_version int NOT NULL,
 spec_sha256 char(64) NOT NULL, forge_template_id text NOT NULL, forge_version int NOT NULL,
 mode text NOT NULL CHECK (mode IN ('single_agent','multi_agent')),
 config jsonb NOT NULL DEFAULT '{}',
 state text NOT NULL CHECK (state IN ('ready','blocked','running','revoked')), state_reason text,
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY (workspace_id, project_id));
CREATE TABLE projects.project_exports(
 workspace_id uuid NOT NULL, project_id text NOT NULL, export_id text NOT NULL,
 export_sha256 char(64) NOT NULL, received_at timestamptz NOT NULL DEFAULT now(),
 new_count int NOT NULL, superseding_count int NOT NULL, unchanged_count int NOT NULL,
 blocked_count int NOT NULL DEFAULT 0, reason text, blocked jsonb NOT NULL DEFAULT '[]',
 receipt jsonb NOT NULL, receipt_sha256 char(64) NOT NULL,
 PRIMARY KEY (workspace_id, project_id, export_id), UNIQUE (workspace_id, project_id, export_sha256),
 FOREIGN KEY (workspace_id, project_id) REFERENCES projects.projects);
CREATE TRIGGER exports_append_only BEFORE UPDATE OR DELETE ON projects.project_exports
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();
CREATE TABLE projects.task_imports(
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, project_id text NOT NULL, export_id text NOT NULL,
 task_id text NOT NULL, revision int NOT NULL CHECK (revision > 0), title text NOT NULL,
 package_ref text NOT NULL, package_sha256 char(64) NOT NULL,
 case_selector jsonb NOT NULL,
 actor_payload text NOT NULL, private_payload text NOT NULL,
 state text NOT NULL CHECK (state IN ('received','verified','ready','blocked','superseded','revoked')),
 state_reason text, corrects_id uuid REFERENCES projects.task_imports(id), sme_batch_id text,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE (workspace_id, project_id, task_id, revision),
 UNIQUE (workspace_id, project_id, package_sha256),
 FOREIGN KEY (workspace_id, project_id) REFERENCES projects.projects);
CREATE FUNCTION projects.task_import_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF (NEW.id, NEW.workspace_id, NEW.project_id, NEW.export_id, NEW.task_id, NEW.revision, NEW.package_sha256,
     NEW.case_selector, NEW.actor_payload, NEW.private_payload, NEW.corrects_id) IS DISTINCT FROM
    (OLD.id, OLD.workspace_id, OLD.project_id, OLD.export_id, OLD.task_id, OLD.revision, OLD.package_sha256,
     OLD.case_selector, OLD.actor_payload, OLD.private_payload, OLD.corrects_id) THEN
  RAISE EXCEPTION 'imported task revisions are immutable; ADI Forge sends a new revision';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER task_import_immutable BEFORE UPDATE ON projects.task_imports
 FOR EACH ROW EXECUTE FUNCTION projects.task_import_guard();
CREATE TRIGGER task_import_no_delete BEFORE DELETE ON projects.task_imports
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();
-- Package content, split by audience. The private part (graders, references) is read only by
-- scoring and by audited "Reviewer only" views; it is never sent to a runner, model or export.
CREATE TABLE projects.task_payloads(
 package_sha256 char(64) NOT NULL, workspace_id uuid NOT NULL, part text NOT NULL CHECK (part IN ('actor','private')),
 content jsonb NOT NULL, content_sha256 char(64) NOT NULL,
 PRIMARY KEY (workspace_id, package_sha256, part));
CREATE TRIGGER task_payloads_append_only BEFORE UPDATE OR DELETE ON projects.task_payloads
 FOR EACH ROW EXECUTE FUNCTION infra.forbid_change();
CREATE TABLE projects.selection_rules(
 workspace_id uuid NOT NULL, project_id text NOT NULL, alias text NOT NULL,
 contract_id text NOT NULL, kind text NOT NULL CHECK (kind IN ('pinned','same_data','latest')),
 pinned_version_id text, seed_family text,
 template_rule jsonb NOT NULL, override_id uuid,
 resolved_version_id text,
 change_cause text NOT NULL CHECK (change_cause IN ('initial','override','override_removed','automatic_revoked','automatic_new_version','automatic_deprecated','automatic_failed')),
 change_note text,
 valid_from timestamptz NOT NULL DEFAULT clock_timestamp(), valid_to timestamptz,
 CHECK (kind <> 'pinned' OR pinned_version_id IS NOT NULL),
 CHECK (kind <> 'same_data' OR seed_family IS NOT NULL),
 PRIMARY KEY (workspace_id, project_id, alias, valid_from),
 FOREIGN KEY (workspace_id, project_id) REFERENCES projects.projects);
CREATE UNIQUE INDEX selection_rules_current ON projects.selection_rules (workspace_id, project_id, alias) WHERE valid_to IS NULL;
CREATE TABLE projects.evaluator_selection_rules(
 workspace_id uuid NOT NULL, project_id text NOT NULL, criterion_id text NOT NULL,
 configuration_id text NOT NULL, kind text NOT NULL CHECK (kind IN ('latest_qualified','pinned')),
 pinned_version int, CHECK (kind <> 'pinned' OR pinned_version IS NOT NULL),
 resolved_version int,
 change_cause text NOT NULL CHECK (change_cause IN ('initial','override','override_removed','automatic_revoked','automatic_new_version','automatic_deprecated','pinned_by_project','unpinned')),
 change_note text, changed_by text,
 valid_from timestamptz NOT NULL DEFAULT clock_timestamp(), valid_to timestamptz,
 PRIMARY KEY (workspace_id, project_id, criterion_id, valid_from),
 FOREIGN KEY (workspace_id, project_id) REFERENCES projects.projects);
CREATE UNIQUE INDEX evaluator_rules_current ON projects.evaluator_selection_rules (workspace_id, project_id, criterion_id) WHERE valid_to IS NULL;
CREATE TABLE projects.rule_overrides(
 id uuid PRIMARY KEY, short_id text NOT NULL, workspace_id uuid NOT NULL, project_id text NOT NULL,
 target_kind text NOT NULL DEFAULT 'alias' CHECK (target_kind IN ('alias','criterion')),
 alias text NOT NULL, from_rule jsonb NOT NULL, to_rule jsonb NOT NULL,
 from_version_id text, to_version_id text, data_change boolean NOT NULL,
 reason text NOT NULL CHECK (length(trim(reason)) > 0),
 new_cohort_acknowledged boolean NOT NULL DEFAULT false,
 requested_by uuid NOT NULL, requested_at timestamptz NOT NULL DEFAULT now(),
 decided_by uuid, decided_at timestamptz, decision_note text,
 removed_by uuid, removed_at timestamptz,
 decision text NOT NULL CHECK (decision IN ('requested','approved','rejected','removed')),
 CHECK (decided_by IS NULL OR decided_by <> requested_by),
 CHECK (decision <> 'rejected' OR length(trim(coalesce(decision_note, ''))) > 0),
 CHECK (decision NOT IN ('approved','removed') OR NOT data_change OR new_cohort_acknowledged),
 UNIQUE (workspace_id, short_id),
 FOREIGN KEY (workspace_id, project_id) REFERENCES projects.projects);
CREATE UNIQUE INDEX one_open_override ON projects.rule_overrides (workspace_id, project_id, alias) WHERE decision = 'requested';

-- Row-level security: every workspace-scoped table is visible only inside its workspace. ------
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['admin.users','admin.audit_events','admin.notifications',
  'catalog.evaluator_configurations','catalog.template_activations','catalog.template_criteria','catalog.inbox_items',
  'projects.projects','projects.project_exports','projects.task_imports','projects.task_payloads',
  'projects.selection_rules','projects.evaluator_selection_rules','projects.rule_overrides'] LOOP
  EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', t);
  EXECUTE format('CREATE POLICY workspace_isolation ON %s USING (workspace_id = infra.current_workspace()) WITH CHECK (workspace_id = infra.current_workspace())', t);
 END LOOP; END $$;
-- Workspace lookup by slug happens before a workspace is chosen; membership rows are checked by id.
CREATE FUNCTION admin.membership(ws uuid, person uuid) RETURNS TABLE(profile text, binding_approver boolean, status text)
 LANGUAGE sql STABLE SECURITY DEFINER SET search_path = admin, pg_temp AS $$
 SELECT profile, binding_approver, status FROM admin.users WHERE workspace_id = ws AND id = person $$;
CREATE FUNCTION admin.workspaces_of(person uuid) RETURNS TABLE(id uuid, slug text, name text, profile text)
 LANGUAGE sql STABLE SECURITY DEFINER SET search_path = admin, pg_temp AS $$
 SELECT w.id, w.slug, w.name, u.profile FROM admin.workspaces w JOIN admin.users u ON u.workspace_id = w.id
 WHERE u.id = person AND u.status = 'active' ORDER BY w.name $$;
REVOKE ALL ON FUNCTION admin.membership(uuid, uuid), admin.workspaces_of(uuid) FROM PUBLIC;

GRANT USAGE ON SCHEMA admin, catalog, projects, infra TO anvil_app;
GRANT SELECT ON admin.workspaces TO anvil_app;
GRANT SELECT, INSERT, UPDATE ON admin.users, admin.notifications TO anvil_app;
GRANT SELECT, INSERT ON admin.audit_events TO anvil_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA admin TO anvil_app;
GRANT EXECUTE ON FUNCTION admin.membership(uuid, uuid), admin.workspaces_of(uuid), infra.current_workspace() TO anvil_app;
GRANT SELECT, INSERT, UPDATE ON infra.outbox, infra.idempotency_keys TO anvil_app;
GRANT SELECT, INSERT ON infra.inbox TO anvil_app;
GRANT SELECT, INSERT, UPDATE ON catalog.environment_versions, catalog.registry_cursor, catalog.framework_versions,
 catalog.evaluator_configurations, catalog.template_activations, catalog.inbox_items TO anvil_app;
GRANT SELECT, INSERT ON catalog.registry_events, catalog.qualification_receipts, catalog.template_criteria TO anvil_app;
GRANT SELECT, INSERT, UPDATE ON projects.projects, projects.task_imports, projects.selection_rules,
 projects.evaluator_selection_rules, projects.rule_overrides TO anvil_app;
GRANT SELECT, INSERT ON projects.project_exports, projects.task_payloads TO anvil_app;
