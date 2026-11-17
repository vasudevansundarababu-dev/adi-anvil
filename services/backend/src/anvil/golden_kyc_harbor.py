"""Golden binding to Anvil's pinned Harbor actor/collection/separate verifier.

Dedicated native host only. No Docker capability is added to API/scheduler roles.
This controlled script path proves software custody, never model performance.
"""

import hashlib
import json
import sys
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path

from anvil.db import digest, project_fence
from anvil.environment_harbor import execute_fixed_software as harbor_execute_fixed
from anvil.golden_kyc_data import VERSION
from anvil.golden_kyc_runtime import create_trial, locked, step, tick


@dataclass(frozen=True)
class SoftwareScriptContext:
    """Host-only context. Never serialize the connection factory or trial token."""

    connections: object = field(repr=False)
    project: object
    user: object
    trial_id: object
    trial_token: str = field(repr=False)
    script: tuple = field(repr=False)
    snapshot_sha256: str


def execute_software_script(context):
    """Actual deterministic KYC operation; fixed dependencies, not a generic callback.

    This top-level function intentionally takes explicit host context. It is not
    admitted through the raw no-argument/no-global callback path. A separately
    reviewed fixed-operation dispatcher is still required before it may run.
    """
    observations = []
    for item in context.script:
        with context.connections() as c:
            tick(c, context.project, context.user, context.trial_id, active_seconds=1)
            result = step(
                c,
                context.project,
                context.user,
                context.trial_id,
                0,
                context.trial_token,
                item["action"],
                item["arguments"],
            )
            observations.append(result)
            row = locked(c, context.project, context.user, context.trial_id)
        if row["closed"]:
            break
    public_output = {"observations": observations, "recommendation": row["state"]["final"]}
    receipt = {
        "trial_id": context.trial_id,
        "generation": 0,
        "snapshot_sha256": context.snapshot_sha256,
        "script_sha256": digest(list(context.script)),
        "state_sha256": digest(row["state"]),
        "public_output_sha256": digest(public_output),
        "model_performance": False,
    }
    return public_output, receipt


@dataclass(frozen=True)
class OwnedSoftwareScriptCallback:
    """Descriptor adapter remains unadmitted by the strict raw callback guard."""

    context: SoftwareScriptContext = field(repr=False)

    def __call__(self):
        return execute_software_script(self.context)


FIXED_ACTIONS = (
    b'[{"action":"application.read","arguments":{}},{"action":"documents.list","arguments":{}}]'
)


@dataclass(frozen=True)
class FixedSoftwareRequest:
    """Immutable host request, never a callable/connection/token from an API."""

    actor_bytes: bytes
    context_bytes: bytes
    script_bytes: bytes = FIXED_ACTIONS

    def validate(self):
        if type(self.actor_bytes) is not bytes or type(self.context_bytes) is not bytes:
            raise ValueError("Immutable fixed software request required")
        if (
            len(self.actor_bytes) > 8192
            or len(self.context_bytes) > 8192
            or type(self.script_bytes) is not bytes
            or self.script_bytes != FIXED_ACTIONS
        ):
            raise ValueError("Fixed two-read software request required")
        actor, context = json.loads(self.actor_bytes), json.loads(self.context_bytes)
        if (
            type(actor) is not dict
            or type(context) is not dict
            or self.actor_bytes
            != json.dumps(actor, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
            or self.context_bytes
            != json.dumps(context, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ):
            raise ValueError("Canonical immutable actor/context bytes required")
        if (
            context.get("kind") != "golden_kyc_software_v1"
            or context.get("paid_calls") is not False
            or actor.get("paid_calls") is not False
            or context.get("script_sha256") != digest(json.loads(FIXED_ACTIONS))
            or any(
                actor.get(k) != context.get(k)
                for k in (
                    "application_id",
                    "environment_version",
                    "snapshot_sha256",
                    "script_sha256",
                )
            )
        ):
            raise ValueError("Fixed software actor/context mismatch")
        return actor, context


@dataclass(frozen=True)
class FixedSoftwareAdapter:
    """Only the real KYC operation; raw callback validation stays separate.

    Dispatch remains blocked by the source-only operation producer and by the
    missing qualified native Trial bridge. No raw function is specially allowed.
    """

    request: FixedSoftwareRequest
    connections: object = field(repr=False)

    def validate(self):
        if type(self.request) is not FixedSoftwareRequest:
            raise ValueError("Exact fixed software request type required")
        return self.request.validate()

    def dispatch(self):
        from anvil.environment_harbor import fixed_trial_gate

        # Only the separately bounded worker may enter the private fixed method.
        fixed_trial_gate()

    def _dispatch_claimed(self, store, *, native_identity):
        actor, binding_context = self.validate()
        # Reload independent custody and fsync O_EXCL intent before any factory.
        binding = store.enter_operation(actor, binding_context, native_identity=native_identity)
        trial_id = None

        @contextmanager
        def scoped_connections():
            with self.connections() as c:
                c.execute("SET LOCAL statement_timeout=1500")
                c.execute("SET LOCAL lock_timeout=500")
                c.execute(
                    "SELECT set_config('anvil.project',%s,true),set_config('anvil.user',%s,true)",
                    (binding_context["project_id"], binding_context["user_id"]),
                )
                project_fence(c, binding_context["project_id"])
                scope = c.execute(
                    "SELECT current_user AS effective,banking.runtime_scope(%s) AS allowed,"
                    "(SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname=current_user) AS bypass",
                    (binding_context["project_id"],),
                ).fetchone()
                active = c.execute(
                    "SELECT 1 FROM anvil.memberships m JOIN anvil.users u ON u.id=m.user_id "
                    "WHERE m.project_id=%s AND m.user_id=%s AND m.active AND u.active "
                    "AND m.role IN ('admin','rl-engineer') LIMIT 1",
                    (binding_context["project_id"], binding_context["user_id"]),
                ).fetchone()
                if (
                    not scope
                    or scope["effective"] != "anvil_golden_scheduler"
                    or scope["bypass"] is not False
                    or not scope["allowed"]
                    or not active
                ):
                    raise ValueError("Current scoped scheduler membership required")
                yield c

        try:
            with scoped_connections() as c:
                current = c.execute(
                    "SELECT snapshot_sha256 FROM banking.applications "
                    "WHERE project_id=%s AND pack_id=%s AND id=%s FOR SHARE",
                    (
                        binding_context["project_id"],
                        binding_context["pack_id"],
                        binding_context["application_id"],
                    ),
                ).fetchone()
                if not current or current["snapshot_sha256"] != binding_context["snapshot_sha256"]:
                    raise ValueError("KYC snapshot changed after fixed preflight")
                trial = create_trial(
                    c,
                    binding_context["project_id"],
                    binding_context["user_id"],
                    binding_context["pack_id"],
                    binding_context["application_id"],
                    "harbor-fixed-" + binding["operation_nonce"],
                    1,
                )
            trial_id = str(trial["trial_id"])
            output, receipt = execute_software_script(
                SoftwareScriptContext(
                    scoped_connections,
                    binding_context["project_id"],
                    binding_context["user_id"],
                    trial["trial_id"],
                    trial["trial_token"],
                    tuple(json.loads(self.request.script_bytes)),
                    binding_context["snapshot_sha256"],
                )
            )
            native_bytes = json.dumps(
                {"output": output, "receipt": receipt},
                sort_keys=True,
                separators=(",", ":"),
                default=str,
                allow_nan=False,
            ).encode()
            if trial["trial_token"].encode() in native_bytes:
                raise ValueError("Trial credentials must remain host-only")
            store.finish_operation(
                binding,
                trial_id=trial_id,
                output_sha256=hashlib.sha256(native_bytes).hexdigest(),
                state="completed",
            )
            return output, receipt
        except BaseException:
            # Failure after durable entry is never a second invocation opportunity.
            store.finish_operation(binding, trial_id=trial_id, output_sha256=None, state="unknown")
            raise


def run_script(connections, project, user, pack, application, script, *, folder, host, python):
    if not isinstance(script, list) or not 1 <= len(script) <= 100:
        raise ValueError("Bounded declared software script required")
    if any(not isinstance(item, dict) or set(item) != {"action", "arguments"} for item in script):
        raise ValueError("Invalid declared tool script")
    script = deepcopy(script)
    with connections() as c:
        snapshot = c.execute(
            "SELECT snapshot,snapshot_sha256 FROM banking.applications WHERE project_id=%s AND pack_id=%s AND id=%s",
            (project, pack, application),
        ).fetchone()
    if not snapshot:
        raise ValueError("KYC application unavailable")
    actor = {
        "assignment": "Golden Bank KYC Investigation Agent",
        "application_id": application,
        "environment_version": VERSION,
        "snapshot_sha256": snapshot["snapshot_sha256"],
        "script_sha256": digest(script),
        "mode": "declared_software_script",
        "paid_calls": False,
    }
    context_binding = {
        "kind": "golden_kyc_software_v1",
        "project_id": str(project),
        "user_id": str(user),
        "pack_id": str(pack),
        "application_id": str(application),
        "environment_version": VERSION,
        "snapshot_sha256": snapshot["snapshot_sha256"],
        "script_sha256": digest(script),
        "paid_calls": False,
    }
    # No trial/clock/event factory precedes complete typed/native preflight.
    request = FixedSoftwareRequest(
        json.dumps(actor, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(),
        json.dumps(
            context_binding, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode(),
        json.dumps(script, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(),
    )
    return harbor_execute_fixed(
        Path(folder), FixedSoftwareAdapter(request, connections), host=host, python=Path(python)
    )


def fixed_worker_main(arguments):
    """Fixed child entry, never an uploaded callback or serialized connection."""
    from anvil.environment_harbor import (
        ROOT,
        fixed_trial_gate,
        operator_proof_module,
        owned_json,
        validate_fixed_assets,
    )

    fixed_trial_gate()
    if len(arguments) != 3 or arguments[0] != "--fixed-worker":
        raise ValueError("Exact fixed worker entry required")
    _, job_id, actor_hash = arguments
    module = operator_proof_module()
    if not module.hash_value(actor_hash):
        raise ValueError("Bound operator actor hash required")
    with module.OperatorProofStore(ROOT) as store:
        stored = module.parse(store._read("operation-bindings", actor_hash + ".json"))
        actor = stored["request_capsule"]["actor"]
        context = stored["request_capsule"]["business_context"]
        binding = store.load_operation(actor, context)
        if binding["job_id"] != job_id or binding["actor_sha256"] != actor_hash:
            raise ValueError("Fixed worker request identity changed")
        docs = store.operation_assets(binding)
        host = docs["host_image_custody"]
        validate_fixed_assets(
            store,
            binding,
            folder=Path(host["folder"]),
            host=host["docker_host"],
            python=Path(host["python"]),
        )
        # Credentials are read only in this independently admitted host process.
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
        from psycopg.rows import dict_row

        provider = host["database_provider"]
        params = conninfo_to_dict(store.scheduler_secret(provider))
        if (
            set(params) - {"host", "port", "user", "password", "dbname", "sslmode"}
            or params.get("dbname") != provider["database"]
        ):
            raise ValueError("Fixed scheduler connection target changed")

        @contextmanager
        def connections():
            with psycopg.connect(
                **params,
                connect_timeout=2,
                options="-c statement_timeout=1500 -c lock_timeout=500",
                row_factory=dict_row,
            ) as c:
                identity = c.execute(
                    "SELECT current_database() AS database,version() AS version"
                ).fetchone()
                if (
                    identity["database"] != provider["database"]
                    or provider["server_version"] not in identity["version"]
                ):
                    raise ValueError("Fixed database identity changed")
                yield c

        request = FixedSoftwareRequest(module.canonical(actor), module.canonical(context))
        store.validate_loaded_origins(docs["runtime_seal"], component="backend")
        native_identity = owned_json(Path(host["folder"]), "framework-entry.json")
        output, receipt = FixedSoftwareAdapter(request, connections)._dispatch_claimed(
            store, native_identity=native_identity
        )
        store.validate_runtime_seal(docs["runtime_seal"])
        raw = json.dumps(
            {"output": output, "receipt": receipt},
            sort_keys=True,
            separators=(",", ":"),
            default=str,
            allow_nan=False,
        ).encode()
        if len(raw) > 1048576:
            raise ValueError("Fixed callback output limit exceeded")
        sys.stdout.buffer.write(raw)


if __name__ == "__main__":
    try:
        fixed_worker_main(sys.argv[1:])
    except BaseException:  # Do not emit private connection errors or credentials.
        sys.stdout.write('{"status":"blocked_or_unknown_no_replay"}')
        raise SystemExit(1) from None
