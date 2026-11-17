"""Closed component hooks: read-only profile and current mount checks.

Snapshot/entry producers, actual SDK components and native operation admission
remain unimplemented/unqualified. File contents alone never prove native start.
"""

import hashlib
import json
import os
import stat
from uuid import UUID

from anvil.marketing_native_attempt import MarketingAttemptStore, _owned
from anvil.marketing_native_boundary import (
    DOCUMENT_CAP,
    _bounded_canonical,
    _digest,
    _pairs,
    marketing_native_gate,
)
from anvil.marketing_native_mounts import ROLE_GID, ROLE_UID, _capture_inputs, _context_version
from anvil.marketing_native_records import _parse_record


def _document(raw):
    try:
        value = json.loads(raw, object_pairs_hook=_pairs)
        if type(value) is not dict:
            raise ValueError("document")
        _bounded_canonical(value, DOCUMENT_CAP)
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ValueError("marketing_bounded_actual_projection_required") from None


def _profile(store, root, claim, plan, role, phase):
    trial = store._walk(root, ["trials", claim["trial_name"]])
    try:
        filename = "marketing-" + phase + "-compose-" + role + ".json"
        document = _document(store._read(trial, filename))
    finally:
        os.close(trial)
    expected_name = claim["trial_name"] + ("__env" if role == "environment" else "__verifier__trial")
    if (set(document) != {"name", "services"} or document["name"] != expected_name
            or type(document["services"]) is not dict or set(document["services"]) != {"main"}
            or type(document["services"]["main"]) is not dict):
        raise ValueError("marketing_actual_role_session_service_required")
    service = document["services"]["main"]
    if _digest(service) != plan["expected_effective_services"][role]:
        raise ValueError("marketing_independent_actual_service_pin_changed")
    task = store._walk(root, ["task", role])
    try:
        declared = _document(store._read(task, "docker-compose.yaml"))["services"]["main"]
    finally:
        os.close(task)
    keys = ("image", "pull_policy", "user", "read_only", "network_mode", "cap_drop", "security_opt",
            "cpus", "mem_limit", "memswap_limit", "pids_limit", "working_dir", "command", "environment", "tmpfs")
    if (_bounded_canonical({key: service.get(key) for key in keys}, DOCUMENT_CAP)
            != _bounded_canonical({key: declared[key] for key in keys}, DOCUMENT_CAP)):
        raise ValueError("marketing_actual_role_isolation_changed")
    banned = ("build", "privileged", "ports", "devices", "pid", "ipc", "gpus", "runtime", "entrypoint",
              "userns_mode", "volumes_from", "links", "external_links", "credential_spec", "secrets", "configs",
              "env_file", "extra_hosts", "dns", "dns_search", "sysctls", "group_add", "develop", "post_start", "pre_stop")
    if any(service.get(key) for key in banned):
        raise ValueError("marketing_actual_role_extension_denied")
    mounts = service.get("volumes")
    expected = {row["target"]: row for row in declared["volumes"]}
    if type(mounts) is not list or len(mounts) != len(expected):
        raise ValueError("marketing_actual_role_mount_set_changed")
    seen = set()
    for mount in mounts:
        if type(mount) is not dict or mount.get("target") not in expected or mount["target"] in seen:
            raise ValueError("marketing_actual_role_mount_set_changed")
        base = expected[mount["target"]]
        if (mount.get("type") != "bind" or mount.get("source") != base["source"]
                or type(mount.get("read_only", False)) is not bool
                or mount.get("read_only", False) is not base["read_only"]):
            raise ValueError("marketing_actual_role_mount_custody_changed")
        seen.add(mount["target"])
    return document


def _role_access(store, root, claim, role):
    receipt = _parse_record(store._read(root, role + "-mount-receipt.json"))
    if (receipt.get("schema_version") != "anvil.marketing-role-mount-receipt.v1" or receipt.get("role") != role
            or any(receipt.get(key) != claim[key] for key in ("scope", "request_sha256", "plan_sha256", "trial_name"))
            or type(receipt.get("uid")) is not int or receipt["uid"] != ROLE_UID
            or type(receipt.get("gid")) is not int or receipt["gid"] != ROLE_GID
            or receipt.get("log_mode") != "0700" or receipt.get("role_started_by_handoff") is not False
            or receipt.get("native_qualification_granted") is not False):
        raise ValueError("marketing_bound_role_permission_receipt_required")
    paths = (("agent",), ("artifacts", "logs", "artifacts")) if role == "environment" else (("verifier",),)
    for parts in paths:
        parent = store._walk(root, ["trials", claim["trial_name"], *parts[:-1]])
        try:
            fd = os.open(parts[-1], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            try:
                info = os.fstat(fd)
                _owned(info, ROLE_UID, directory=True, private=True)
                if info.st_gid != ROLE_GID or stat.S_IMODE(info.st_mode) != 0o700:
                    raise ValueError("marketing_current_role_directory_access_changed")
            finally:
                os.close(fd)
        finally:
            os.close(parent)
    parts = ["task", "environment", "actor"] if role == "environment" else ["sealed"]
    public = store._walk(root, parts)
    try:
        expected = {"context.json", "binding.json"} if role == "environment" else {"actor-output.json", "collection-receipt.json"}
        if stat.S_IMODE(os.fstat(public).st_mode) != 0o555 or set(os.listdir(public)) != expected:
            raise ValueError("marketing_exact_readonly_role_inputs_required")
        for name in expected:
            fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=public)
            try:
                info = os.fstat(fd)
                _owned(info, store.owner)
                if stat.S_IMODE(info.st_mode) != 0o444:
                    raise ValueError("marketing_exact_readonly_role_file_mode_required")
            finally:
                os.close(fd)
    finally:
        os.close(public)


def _framework_entry(store, root, claim):
    entry = _parse_record(store._read(root, "framework-entry.json"))
    if (set(entry) != {"schema_version", "request_sha256", "plan_sha256", "trial_name", "job_id", "scope", "framework_trial_id", "operation_nonce"}
            or entry.get("schema_version") != "anvil.marketing-framework-entry.v1"
            or any(entry.get(key) != claim[key] for key in ("request_sha256", "plan_sha256", "trial_name", "job_id", "scope"))
            or type(entry.get("framework_trial_id")) is not str
            or str(UUID(entry["framework_trial_id"])) != entry["framework_trial_id"]):
        raise ValueError("marketing_current_framework_entry_required")
    nonce = entry["operation_nonce"]
    if type(nonce) is not str or len(nonce) != 64 or any(c not in "0123456789abcdef" for c in nonce):
        raise ValueError("marketing_current_framework_nonce_required")


def _check(store, request, *, role, stage, opening=False):
    if role not in {"environment", "tests"} or stage not in {"before_start", "before_business", "before_collection"}:
        raise ValueError("marketing_fixed_component_hook_required")
    if stage == "before_business" and role != "environment" or stage == "before_collection" and role != "tests":
        raise ValueError("marketing_fixed_component_hook_required")
    root, claim, plan = _context_version(store, request, opening=opening)
    try:
        preflight = {name: _profile(store, root, claim, plan, name, "preflight") for name in ("environment", "tests")}
        _role_access(store, root, claim, role)
        if stage != "before_start" or role == "tests":
            actual = _profile(store, root, claim, plan, "environment", "start")
            if _bounded_canonical(actual, DOCUMENT_CAP) != _bounded_canonical(preflight["environment"], DOCUMENT_CAP):
                raise ValueError("marketing_actor_start_preflight_changed")
            _framework_entry(store, root, claim)
        if role == "tests":
            output, receipt, _ = _capture_inputs(store, root, claim, plan, opening=opening)
            sealed = store._walk(root, ["sealed"])
            try:
                if store._read(sealed, "actor-output.json") != output or store._read(sealed, "collection-receipt.json") != receipt:
                    raise ValueError("marketing_current_sealed_capture_changed")
            finally:
                os.close(sealed)
        if stage == "before_collection":
            actual = _profile(store, root, claim, plan, "tests", "start")
            if _bounded_canonical(actual, DOCUMENT_CAP) != _bounded_canonical(preflight["tests"], DOCUMENT_CAP):
                raise ValueError("marketing_verifier_start_preflight_changed")
        return {"scope": store.scope, "role": role, "stage": stage,
                "request_sha256": claim["request_sha256"], "plan_sha256": claim["plan_sha256"],
                "profile_bytes_sha256": {name: hashlib.sha256(_bounded_canonical(doc, DOCUMENT_CAP)).hexdigest() for name, doc in preflight.items()},
                "native_qualified": False, "role_started": False}
    finally:
        os.close(root)


def before_role_start(request, role):
    marketing_native_gate()
    with MarketingAttemptStore() as store:
        return _check(store, request, role=role, stage="before_start")


def before_business(request):
    marketing_native_gate()
    with MarketingAttemptStore() as store:
        return _check(store, request, role="environment", stage="before_business")


def before_verifier_collection(request):
    marketing_native_gate()
    with MarketingAttemptStore() as store:
        return _check(store, request, role="tests", stage="before_collection")
