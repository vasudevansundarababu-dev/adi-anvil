"""Schema-driven Marketing file projection; no materialization or native launch.

Declared Compose files are not actual resolved/start profiles. Every operational
entry is closed. Typed inputs/pins establish consistency, never asset admission.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

from anvil.marketing_native_boundary import (
    DOCUMENT_CAP,
    PURPOSE,
    MarketingCampaignRequestV1,
    _bounded_canonical,
    _digest,
    marketing_native_gate,
    prepare_marketing_request,
    validate_prepared_graph_binding,
)
from anvil.marketing_native_records import _parse_record
from anvil.marketing_task2_contract import WIRE_ROLES

FILES = frozenset({
    "environment/actor/context.json", "environment/actor/binding.json",
    "environment/docker-compose.yaml", "tests/docker-compose.yaml",
    "instruction.md", "tests/test.sh", "task.toml",
})
LIFECYCLE_PHASES = (
    "admitted_API_prepare_ONCE_allocates_world_NO_replay",
    "independent_freeze_prepared_attachment_full_request_source_world_assets_and_Run",
    "exclusive_materialization_and_context_same_deadline",
    "paired_actual_config_before_native_effects",
    "one_way_native_intent_WITHOUT_API_prepare",
    "owned_framework_start_matching_preflight",
    "readonly_component_preflight_matching_retained_pair",
    "fixed_existing_world_attach_and_graph_once_same_deadline",
    "API_quiescence_and_actor_process_container_stop_bounded_capture",
    "separate_verifier_start_matching_preflight", "whole_tree_cleanup_and_readonly_reconciliation",
)


@dataclass(frozen=True, slots=True)
class MarketingRenderAssetsV1:
    canonical_bytes: bytes


@dataclass(frozen=True, slots=True)
class MarketingRenderAssetsV2:
    canonical_bytes: bytes


@dataclass(frozen=True, slots=True)
class MarketingTaskProjectionV1:
    files: tuple[tuple[str, bytes], ...]
    lifecycle_plan: bytes


@dataclass(frozen=True, slots=True)
class MarketingTaskProjectionV2:
    files: tuple[tuple[str, bytes], ...]
    lifecycle_plan: bytes


def _schedule(value, graph, *, opening):
    roles = [role['id'] for role in graph['roles']]
    if not opening:
        return {'role_ids': roles, 'windows': list(range(1, 13)),
                'workflow_graph_sha256': value['workflow_graph_sha256']}
    return {
        'schema_version': 'anvil.marketing-operator-schedule.v2',
        'program_id': 'marketing-opening0-and-twelve-reviews-v1',
        'role_ids': roles, 'opening_index': 0,
        'review_indices': list(range(1, 13)), 'observation_indices': list(range(13)),
        'weekly_cycle_backedges': 12, 'workflow_graph_sha256': value['workflow_graph_sha256'],
    }


def _sha(value):
    return type(value) is str and re.fullmatch(r"[a-f0-9]{64}", value)


def _exact(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        raise ValueError("marketing_exact_renderer_asset_fields_required")


def _positive(values):
    if any(type(v) is not int or not 1 <= v <= 9007199254740991 for v in values):
        raise ValueError("marketing_explicit_positive_renderer_bounds_required")


def _render_files(value, prepared, assets, *, operator_program=None):
    """Pure byte generator; caller must run the strict pin/profile checks below."""
    root, name = assets["attempt_root"], assets["trial_name"]
    resource, bounds = assets["resources"], assets["bounds"]
    image = assets["image"]["digest"]
    actor = prepared["public_actor"]
    roles = [role["id"] for role in prepared["execution"]["workflow_graph"]["roles"]]
    files = {
        "environment/actor/context.json": _bounded_canonical(actor, DOCUMENT_CAP),
        "environment/actor/binding.json": _bounded_canonical({
            "schema_version": "anvil.marketing-public-role-binding.v1",
            "workflow_graph_sha256": value["workflow_graph_sha256"],
            "public_actor_sha256": value["public_actor_sha256"],
            "case_id": value["case_assignment"]["case_id"],
            "role_ids": roles, "windows": list(range(1, 13)),
        }, DOCUMENT_CAP),
        "instruction.md": b"Execute the complete published five-role Marketing campaign through the trusted API mediator. Preserve all twelve reporting windows and frozen graph transitions. No provider credential, private fixture or evaluator is available to the actor. Collection custody is separate from task quality.\n",
        # Fail closed under stock execution: no empty script can award a pass.
        # A separately reviewed Marketing collection adapter is still required.
        "tests/test.sh": b"#!/bin/sh\nset -eu\necho 'Marketing collection adapter is not admitted' >&2\nexit 43\n",
    }
    if operator_program is not None:
        files['environment/actor/binding.json'] = _bounded_canonical({
            'schema_version': 'anvil.marketing-public-role-binding.v2',
            'workflow_graph_sha256': value['workflow_graph_sha256'],
            'public_actor_sha256': value['public_actor_sha256'],
            'case_id': value['case_assignment']['case_id'], 'role_ids': roles,
            'opening_window': 0, 'review_windows': list(range(1, 13)),
            'windows': list(range(13)), 'operator_program_sha256': _digest(operator_program),
        }, DOCUMENT_CAP)
        files['instruction.md'] = (
            b'Execute the original opening step 0 from its qualified API release, then review windows 1 through 12. '
            b'Preserve the same published five-role graph and twelve loopbacks for every model. '
            b'Opening is separate from the twelve weekly reviews; original call, spending and lifecycle limits still apply. '
            b'No provider credential, private fixture or evaluator is available to the actor. '
            b'Collection custody is separate from task quality.\n'
        )
    for role in ("environment", "tests"):
        mounts = [{
            "type": "bind", "source": root + ("/task/environment/actor" if role == "environment" else "/sealed"),
            "target": "/workspace/inputs" if role == "environment" else "/sealed", "read_only": True,
        }]
        logs = {"environment": (("agent", "/logs/agent"), ("artifacts/logs/artifacts", "/logs/artifacts")),
                "tests": (("verifier", "/logs/verifier"),)}[role]
        mounts += [{"type": "bind", "source": root + "/trials/" + name + "/" + source,
                    "target": target, "read_only": False} for source, target in logs]
        tmp = str(resource["tmpfs_mb"]) + "m"
        service = {
            "image": image, "pull_policy": "never", "user": "10001:10001",
            "read_only": True, "network_mode": "none", "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges:true"], "cpus": resource["cpus"],
            "mem_limit": resource["memory_mb"] * 1048576,
            "memswap_limit": resource["memory_mb"] * 1048576,
            "pids_limit": resource["pids_limit"], "working_dir": "/workspace" if role == "environment" else "/tmp",
            "command": ["sleep", "infinity"],
            "environment": {"HOME": "/tmp", "PYTHONDONTWRITEBYTECODE": "1"},
            "tmpfs": ["/workspace:rw,nosuid,nodev,size=" + tmp + ",uid=10001,gid=10001",
                      "/tmp:rw,nosuid,nodev,noexec,size=" + tmp + ",uid=10001,gid=10001"]
                     + (["/logs/artifacts:rw,nosuid,nodev,noexec,size=" + tmp + ",uid=10001,gid=10001"] if role == "tests" else []),
            "volumes": mounts,
        }
        files[role + "/docker-compose.yaml"] = _bounded_canonical({"services": {"main": service}}, DOCUMENT_CAP)
    files["task.toml"] = f'''schema_version = "1.4"
[[artifacts]]
source = "/workspace/output.json"
destination = "agent-output.json"
service = "main"
[agent]
timeout_sec = {bounds["actor_seconds"]}
user = "10001:10001"
[environment]
docker_image = "{image}"
network_mode = "no-network"
cpus = {resource["cpus"]}
memory_mb = {resource["memory_mb"]}
storage_mb = {resource["storage_mb"]}
[verifier]
timeout_sec = {bounds["verifier_seconds"]}
environment_mode = "separate"
[verifier.environment]
docker_image = "{image}"
network_mode = "no-network"
cpus = {resource["cpus"]}
memory_mb = {resource["memory_mb"]}
storage_mb = {resource["storage_mb"]}
'''.encode()
    return files


def project_marketing_task(request, prepared, assets):
    """Pure file/lifecycle projection, not SDK rendering, writing or admission."""
    if type(request) is not MarketingCampaignRequestV1 or type(assets) is not MarketingRenderAssetsV1:
        raise ValueError("marketing_exact_typed_renderer_inputs_required")
    return _project_task(request, prepared, assets, opening=False)


def project_marketing_opening_task(request, prepared, assets):
    """Explicit candidate v2 projection; never silently admitted as a v1 plan."""
    if type(request) is not MarketingCampaignRequestV1 or type(assets) is not MarketingRenderAssetsV2:
        raise ValueError('marketing_exact_opening_renderer_inputs_required')
    return _project_task(request, prepared, assets, opening=True)


def _project_task(request, prepared, assets, *, opening):
    prepare_marketing_request(request.canonical_bytes)
    value = json.loads(request.canonical_bytes)
    prepared = json.loads(validate_prepared_graph_binding(request, prepared))
    data = _parse_record(assets.canonical_bytes)
    _exact(data, {"schema_version", "purpose", "request_context_sha256", "attempt_root", "trial_name",
                  "image", "task", "resources", "bounds", "runtime", "expected_files", "expected_effective_services"}
           | ({'operator_program'} if opening else set()))
    context = _digest({key: item for key, item in value.items() if key != "asset_manifest_sha256"})
    schema = 'anvil.marketing-render-assets.v2' if opening else 'anvil.marketing-render-assets.v1'
    if data["schema_version"] != schema or data["purpose"] != PURPOSE or data["request_context_sha256"] != context:
        raise ValueError("marketing_renderer_context_changed")
    name, root = data["trial_name"], data["attempt_root"]
    if (type(name) is not str or not re.fullmatch(r"anvil-marketing-[a-f0-9]{20}", name)
            or type(root) is not str or str(PurePosixPath(root)) != root
            or root != "/var/lib/anvil-qa-v1/runtime-functional/marketing-attempts/" + name):
        raise ValueError("marketing_fixed_attempt_projection_required")
    _exact(data["image"], {"digest", "platform", "admission_sha256"})
    if (data["image"]["platform"] != "linux/amd64" or not _sha(data["image"]["admission_sha256"])
            or type(data["image"]["digest"]) is not str
            or not re.fullmatch(r"us-west1-docker\.pkg\.dev/adi-anvil-mvp-2026/[a-z0-9][a-z0-9._-]*(?:/[a-z0-9][a-z0-9._-]*)+@sha256:[a-f0-9]{64}", data["image"]["digest"])):
        raise ValueError("marketing_exact_Anvil_image_candidate_required")
    _exact(data["task"], {"task_id", "revision_id"})
    native = prepared["native_binding"]
    graph = prepared["execution"]["workflow_graph"]
    roles = [role["id"] for role in graph["roles"]]
    schedule = _schedule(value, graph, opening=opening)
    if opening and _bounded_canonical(data['operator_program'], DOCUMENT_CAP) != _bounded_canonical(schedule, DOCUMENT_CAP):
        raise ValueError('marketing_exact_model_independent_opening_program_required')
    if (data["task"] != {key: native[key] for key in ("task_id", "revision_id")}
            or native["fixture_manifest_sha256"] != value["source_manifest_sha256"]
            or native["dataset_qualification"]["receipt_sha256"] != value["dataset_qualification_sha256"]
            or len(roles) != 5 or set(roles) != set(WIRE_ROLES)
            or _digest(graph["roles"]) != value["role_policy_sha256"]
            or _digest(schedule) != value["schedule_sha256"]
            or _digest(native["cases"]) != value["membership_sha256"]
            or not any(loop.get("id") == "weekly_cycle" and type(loop.get("maxIterations")) is int
                       and loop["maxIterations"] == 12 for loop in graph["loops"])):
        raise ValueError("marketing_complete_frozen_task_roles_windows_membership_required")
    _exact(data["resources"], {"cpus", "memory_mb", "storage_mb", "pids_limit", "tmpfs_mb"})
    _positive(data["resources"].values())
    _exact(data["bounds"], {"actor_seconds", "verifier_seconds", "lifecycle_seconds", "cleanup_seconds",
                           "stdout_bytes", "stderr_bytes", "output_bytes", "receipt_bytes"})
    bounds = data["bounds"]
    _positive(bounds.values())
    if (bounds["lifecycle_seconds"] != value["episode_timeout_seconds"]
            or bounds["actor_seconds"] > bounds["lifecycle_seconds"]
            or bounds["verifier_seconds"] > bounds["lifecycle_seconds"]
            or any(bounds[key] > DOCUMENT_CAP for key in ("stdout_bytes", "stderr_bytes", "output_bytes", "receipt_bytes"))):
        raise ValueError("marketing_aggregate_renderer_bounds_required")
    _exact(data["runtime"], {"coordinator_source_sha256", "helper_source_sha256", "interpreter_sha256",
                            "stdlib_manifest_sha256", "environment_sha256", "command_sha256"})
    if not all(_sha(v) for v in data["runtime"].values()):
        raise ValueError("marketing_complete_renderer_runtime_pins_required")
    _exact(data["expected_effective_services"], {"environment", "tests"})
    if not all(_sha(v) for v in data["expected_effective_services"].values()):
        raise ValueError("marketing_independent_actual_profile_pins_required")
    _exact(data["expected_files"], FILES)
    if not all(_sha(v) for v in data["expected_files"].values()):
        raise ValueError("marketing_exact_task_file_pins_required")
    files = _render_files(value, prepared, data, operator_program=schedule if opening else None)
    if {key: hashlib.sha256(raw).hexdigest() for key, raw in files.items()} != data["expected_files"]:
        raise ValueError("marketing_independent_task_file_projection_changed")
    plan = {
        "schema_version": ('anvil.marketing-native-lifecycle-plan.v2' if opening
                           else 'anvil.marketing-native-lifecycle-plan.v1'), "purpose": PURPOSE,
        "request_sha256": hashlib.sha256(request.canonical_bytes).hexdigest(),
        "attempt_root": root, "trial_name": name, "expected_files": data["expected_files"],
        "bounds": bounds, "runtime": data["runtime"],
        "expected_effective_services": data["expected_effective_services"],
        "phases": list(LIFECYCLE_PHASES),
    }
    if opening:
        plan['operator_program'] = schedule
        plan['operator_program_sha256'] = value['schedule_sha256']
    projection = MarketingTaskProjectionV2 if opening else MarketingTaskProjectionV1
    return projection(tuple(sorted(files.items())), _bounded_canonical(plan, DOCUMENT_CAP))


def render_marketing_task(request, prepared):
    marketing_native_gate()
    from anvil.marketing_native_records import resolve_marketing_records

    records = resolve_marketing_records(request)
    return _render_from_records(request, prepared, records, opening=False)


def render_marketing_opening_task(request, prepared):
    marketing_native_gate()
    from anvil.marketing_native_records import resolve_marketing_opening_records

    records = resolve_marketing_opening_records(request)
    return _render_from_records(request, prepared, records, opening=True)


def _render_from_records(request, prepared, records, *, opening):
    task = _parse_record(dict(records.records)["task"])
    _exact(task["payload"], {"render_assets"})
    data = task["payload"]["render_assets"]
    value = json.loads(request.canonical_bytes)
    bindings = {
        "image": data["image"], "runtime": data["runtime"],
        "profile": data["expected_effective_services"], "recovery": data["bounds"],
        "host": {key: data[key] for key in ("attempt_root", "trial_name")},
        "roles": {key: value[key] for key in ("role_policy_sha256", "schedule_sha256", "membership_sha256")},
    }
    for section, expected in bindings.items():
        payload = _parse_record(dict(records.records)[section])["payload"]
        if _bounded_canonical(payload.get("renderer_binding"), DOCUMENT_CAP) != _bounded_canonical(expected, DOCUMENT_CAP):
            raise ValueError("marketing_independent_renderer_section_mismatch")
    raw = _bounded_canonical(data, DOCUMENT_CAP)
    if opening:
        return project_marketing_opening_task(request, prepared, MarketingRenderAssetsV2(raw))
    return project_marketing_task(request, prepared, MarketingRenderAssetsV1(raw))
