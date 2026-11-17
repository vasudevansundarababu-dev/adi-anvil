"""API comparison of actual six-document private capture against retained originals.

Only a current independent original channel qualification can root these physical
observations. Shape/hash agreement alone cannot qualify an attester or runtime.
"""

import hashlib
import math
import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import AwareDatetime

from anvil.dataset_export_contract import Model, Sha, json_object
from anvil.marketing_capture_attestation import STOP, _instant
from anvil.marketing_capture_status import Control
from anvil.marketing_capture_submission import Submission
from anvil.marketing_native_wire_bounds import bounded_json
from anvil.praxis_generic_contract import canonical, digest

CONTROLS = frozenset({"original_root_children", "pidfd_start_identity", "root_outside_scope",
    "fixed_engine_profile", "captured_actor_before_grading", "separate_verifier_process",
    "complete_private_result_custody", "final_frozen_empty_scope", "actual_owned_containers_stopped",
    "original_api_manifest", "no_actor_private_mount", "bounded_cancellation_cleanup"})
KINDS = frozenset({"operation_binding", "kernel_scope", "process_join", "container_shutdown", "verifier_result", "capture_seal"})


class PrivateCaptureProfile(Model):
    schema_version: Literal["anvil.marketing-private-capture-qualification.v1"]
    api_source_sha256: Sha
    deployment_release_sha256: Sha
    binding_source_sha256: Sha
    ordinal_mapping_sha256: Sha
    runtime_image_digest: str
    private_program_sha256: Sha
    tls_certificate_sha256: Sha
    actor_scope_profile: Literal["opening-framework-graph-host-helpers-cgroup2-v1"]
    not_after: AwareDatetime
    controls: dict[str, Control]


def _exact(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError("Complete original physical evidence fields required")


def _flags(value, *keys):
    if any(value.get(key) is not False for key in keys):
        raise ValueError("Producer observations cannot grant native authority")


def _pins(value, *keys):
    if any(type(value.get(key)) is not str or not re.fullmatch(r"[a-f0-9]{64}", value[key]) for key in keys):
        raise ValueError("Exact original physical evidence digests required")


def _positive(value, *keys):
    if any(type(value.get(key)) is not int or value[key] <= 0 for key in keys):
        raise ValueError("Exact original kernel/process identity required")


def _same(value, original, keys):
    if any(value.get(key) != original[key] for key in keys):
        raise ValueError("Physical evidence differs from retained original")


def _moment(value, deadline):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value < deadline:
        raise ValueError("Original bounded physical observation time required")


def check_process(raw, binding, *, profile, frame_sha256, result_raw, input_seal, verifier_document, actor, enrollment):
    """Exact host producer schema; acceptance still requires final whole-root proof."""
    value = json_object(raw)
    bounded_json(value, 1048576, max_nodes=20000, max_depth=12)
    _exact(value, {"schema_version", "identity", "scope", "role", "session_id", "container_id", "image_id", "argv",
        "source_sha256", "sdk_binding_sha256", "program_sha256", "input_seal_receipt_sha256", "input_sha256", "input_files",
        "mounts", "container_binding_sha256", "created_inspect_sha256", "started_inspect_sha256", "completed_inspect_sha256",
        "engine_wait", "exit_code", "started_at", "finished_at", "output", "actor_capture_sha256",
        "actor_stop", "actor_capture_proof", "whole_operation_stopped", "capture_accepted", "native_qualified", "run_authority"})
    original = binding.model_dump(mode="json")
    if (canonical(value) != raw or value["schema_version"] != "anvil.marketing-private-verifier-process-observed.v1"
            or value["role"] != "tests" or value["argv"] != ["python3", "-I", "-B", "-m", "anvil_harbor.marketing_private_verifier"]
            or value["image_id"] != profile.runtime_image_digest or type(value["container_id"]) is not str
            or not re.fullmatch(r"[a-f0-9]{64}", value["container_id"]) or type(value["session_id"]) is not str
            or not 1 <= len(value["session_id"]) <= 120 or not value["session_id"].endswith("__verifier__trial")
            or value["sdk_binding_sha256"] != digest(original) or value["program_sha256"] != profile.private_program_sha256
            or value["input_seal_receipt_sha256"] != digest(input_seal)
            or value["run_authority"] != "not_granted" or input_seal["api_frame_sha256"] != frame_sha256):
        raise ValueError("Original private process/input qualification mismatch")
    _same(value, original, ("identity", "scope", "source_sha256", "input_sha256", "input_files"))
    _flags(value, "whole_operation_stopped", "capture_accepted", "native_qualified")
    _pins(value, "container_binding_sha256", "created_inspect_sha256", "started_inspect_sha256",
          "completed_inspect_sha256", "actor_capture_sha256")
    stop, proof = value["actor_stop"], value["actor_capture_proof"]
    if (digest(stop) != actor.actor_stop_sha256 or digest(proof) != value["actor_capture_sha256"]
            or stop.get("native_stop_receipt_sha256") != value["actor_capture_sha256"]
            or stop.get("actor_output_sha256") != actor.sha256
            or stop.get("collection_receipt_sha256") != actor.collection_receipt_sha256
            or stop.get("schema_version") != "anvil.marketing-actor-stop.v2"
            or stop.get("state") != "actor_stopped_observed"
            or stop.get("scope_kind") != "actor_graph_and_environment_container"
            or proof.get("schema_version") != "anvil.marketing-actor-scope-stop-observed.v1"
            or proof.get("actor_output_sha256") != actor.sha256 or proof.get("diagnostic_only") is not True
            or proof.get("quiescence_sha256") != enrollment["descriptor"]["quiescence_receipt_sha256"]
            or any(proof.get("api_scope", {}).get(key) != expected for key, expected in enrollment["scope"].items())):
        raise ValueError("Original authenticated actor stop and physical capture bytes required")
    for observed in (stop, proof):
        _same(observed, original["identity"], ("framework_trial_id", "request_sha256", "plan_sha256", "operation_nonce"))
    _flags(proof, "whole_operation_stopped", "native_qualified", "capture_accepted")
    _same(verifier_document, value, ("sdk_binding_sha256", "input_seal_receipt_sha256"))
    if verifier_document["private_program_sha256"] != value["program_sha256"]:
        raise ValueError("Original private program changed")
    waited = value["engine_wait"]
    if (type(waited) is not dict or set(waited) - {"StatusCode", "Error"}
            or type(waited.get("StatusCode")) is not int or waited["StatusCode"] != 0
            or waited.get("Error") not in (None, {}) or type(value["exit_code"]) is not int or value["exit_code"] != 0):
        raise ValueError("Actual private verifier successful process completion required")
    times = []
    for key in ("started_at", "finished_at"):
        if type(value[key]) is not str or value[key].startswith("0001-"):
            raise ValueError("Actual private verifier process timestamps required")
        moment = datetime.fromisoformat(value[key].replace("Z", "+00:00"))
        if moment.tzinfo is None:
            raise ValueError("Actual aware process timestamps required")
        times.append(moment)
    if not times[0] <= times[1] < profile.not_after:
        raise ValueError("Original process qualification time exceeded")
    output = value["output"]
    _exact(output, {"source", "device", "inode", "uid", "gid", "mode", "links", "bytes", "sha256"})
    _positive(output, "device", "inode", "links", "bytes")
    if (output["source"] != "/logs/verifier/result.json" or output["uid"] != 10001 or output["gid"] != 10001
            or type(output["uid"]) is not int or type(output["gid"]) is not int
            or output["mode"] != "0600" or output["links"] != 1 or output["bytes"] != len(result_raw)
            or output["sha256"] != hashlib.sha256(result_raw).hexdigest()):
        raise ValueError("Original completed verifier file custody required")
    mounts = value["mounts"]
    if type(mounts) is not list or not 1 <= len(mounts) <= 20:
        raise ValueError("Actual complete private verifier mount inventory required")
    by_target = {}
    for mount in mounts:
        if type(mount) is not dict or type(mount.get("Destination")) is not str or mount["Destination"] in by_target:
            raise ValueError("Actual unique verifier mounts required")
        by_target[mount["Destination"]] = mount
    private = by_target.get("/sealed-verifier")
    if (type(private) is not dict or private.get("Type") != "bind" or private.get("RW") is not False
            or private.get("Propagation") != "rprivate" or type(private.get("Source")) is not str
            or not private["Source"].startswith("/") or not private["Source"].endswith("/sealed-verifier")):
        raise ValueError("Actual isolated read-only original verifier inputs required")
    return value


def check(submission, enrollment, context, frame, actor, result_files, result_checked, result_id, *, api_source_sha256):
    """All inputs except submitted documents come from protected actual API rows."""
    if type(submission) is not Submission or submission.body_schema != "anvil.marketing-native-capture-submission.v2":
        raise ValueError("Explicit private six-document capture required")
    profile = PrivateCaptureProfile.model_validate_json(canonical(context["qualification"]["private_capture_profile"]))
    if (set(profile.controls) != CONTROLS or not re.fullmatch(r"sha256:[a-f0-9]{64}", profile.runtime_image_digest)
            or profile.api_source_sha256 != api_source_sha256
            or profile.not_after > STOP
            or not datetime.now(timezone.utc) < min(profile.not_after, _instant(enrollment["expires_at"]), STOP)
            or _instant(enrollment["expires_at"]) > profile.not_after):
        raise ValueError("Current independent original physical qualification required")
    originals = dict(submission.documents)
    if set(originals) != KINDS:
        raise ValueError("Complete original six-document inventory required")
    docs = {kind: json_object(raw) for kind, raw in originals.items()}
    identity = enrollment["identity"]
    op, kernel, joined, containers, verifier, seal = (docs[k] for k in
        ("operation_binding", "kernel_scope", "process_join", "container_shutdown", "verifier_result", "capture_seal"))
    _exact(op, {"schema_version", "identity", "scope", "enrollment_id", "manifest_id", "boot_id",
                "original_deadline_monotonic", "actor_scope_binding", "child_binding",
                "original_peer_receipt_sha256", "public_ready_sha256", "api_descriptor_sha256",
                "capture_accepted", "native_qualified", "run_authority"})
    _exact(verifier, {"schema_version", "identity", "scope", "custody", "input_seal_receipt_sha256",
                      "private_program_sha256", "sdk_binding_sha256", "capture_accepted", "native_qualified", "run_authority"})
    _exact(seal, {"schema_version", "identity", "scope", "enrollment_id", "manifest_id", "documents_sha256",
                  "own_api_status_sha256", "own_api_tls_certificate_sha256", "api_descriptor_sha256",
                  "actor_output_sha256", "collection_receipt_sha256", "actor_stop_sha256", "input_seal",
                  "capture_accepted", "native_qualified", "run_authority"})
    for document in (op, verifier, seal):
        _same(document, enrollment, ("identity", "scope"))
        _flags(document, "capture_accepted", "native_qualified")
        if document.get("run_authority") != "not_granted":
            raise ValueError("Producer cannot issue Run authority")
    if (op.get("schema_version") != "anvil.marketing-private-operation-binding.v1"
            or verifier.get("schema_version") != "anvil.marketing-private-verifier-custody-reference.v1"
            or seal.get("schema_version") != "anvil.marketing-private-whole-capture-seal.v1"):
        raise ValueError("Exact original private capture schemas required")
    for value in (op, seal):
        _same(value, enrollment, ("enrollment_id", "manifest_id"))
        if value.get("api_descriptor_sha256") != digest(enrollment["descriptor"]):
            raise ValueError("Exact original API descriptor required")
    peer_raw = context["peer_receipt_canonical"].encode()
    peer = json_object(peer_raw)
    pre = peer["preG_actor_observation"]
    if (op.get("original_peer_receipt_sha256") != hashlib.sha256(peer_raw).hexdigest()
            or op.get("public_ready_sha256") != digest(peer["public_ready"]) or op.get("boot_id") != enrollment["boot_id"]):
        raise ValueError("Original independently retained peer enrollment required")
    deadline = pre["original_deadline_monotonic"]
    if type(deadline) not in (int, float) or not math.isfinite(deadline) or deadline <= 0 or op.get("original_deadline_monotonic") != deadline:
        raise ValueError("Original shared operation deadline required")
    root = op["actor_scope_binding"]
    _same(root, enrollment, ("request_sha256", "operation_nonce", "boot_id"))
    _exact(root, {"schema_version", "request_sha256", "plan_sha256", "operation_nonce", "boot_id",
                  "original_deadline_monotonic", "cgroup_device", "cgroup_inode", "cgroup_mount_id"})
    if (root.get("schema_version") != "anvil.marketing-original-kernel-scope.v1"
            or root.get("plan_sha256") != identity["plan_sha256"] or root.get("original_deadline_monotonic") != deadline
            or any(root.get("cgroup_" + k) != pre["original_actor_scope"][k] for k in ("device", "inode", "mount_id"))):
        raise ValueError("Original root kernel identity changed")
    children = op["child_binding"]
    if (children.get("schema_version") != "anvil.marketing-original-actor-scope-children.v2"
            or children.get("binding_sha256") != digest(root) or set(children.get("children", {})) != {"framework", "graph", "host_helpers"}):
        raise ValueError("Original SDK/graph/helper scope binding required")
    for role in ("framework", "graph"):
        if any(children["children"][role][key] != pre["children"][role]["cgroup_" + key] for key in ("device", "inode", "mount_id")):
            raise ValueError("Original pre-G child kernel identities changed")
    if pre.get("actor_scope_binding_sha256") != digest(root):
        raise ValueError("Original pre-G root binding changed")
    if (kernel.get("schema_version") != "anvil.marketing-empty-kernel-scope-observation.v1"
            or kernel.get("independent_binding_sha256") != digest(root) or kernel.get("boot_id") != enrollment["boot_id"]):
        raise ValueError("Original whole-root kernel observation required")
    _flags(kernel, "whole_actor_stopped", "capture_ready", "native_qualified")
    _moment(kernel["observed_monotonic"], deadline)
    snapshots = []
    for name in ("snapshot_first", "snapshot_second"):
        rows = kernel[name]
        if type(rows) is not list or len(rows) != 4 or {r.get("relative") for r in rows} != {".", "./framework", "./graph", "./host_helpers"}:
            raise ValueError("Complete whole-root subtree required")
        normalized = []
        for row in rows:
            expected = ({key: root["cgroup_" + key] for key in ("device", "inode", "mount_id")}
                        if row["relative"] == "." else children["children"][row["relative"][2:]])
            _same(row, expected, ("device", "inode", "mount_id"))
            raw = row["raw_kernel_files"]
            _exact(raw, {"cgroup.events", "cgroup.procs", "cgroup.threads"})
            events = [line.split() for line in raw["cgroup.events"].splitlines()]
            if sorted(events) != [["frozen", "1"], ["populated", "0"]] or raw["cgroup.procs"].strip() or raw["cgroup.threads"].strip():
                raise ValueError("Original whole-root subtree not frozen and empty")
            normalized.append({key: value for key, value in row.items() if key != "raw_fdinfo"})
        snapshots.append(sorted(normalized, key=lambda row: row["relative"]))
    if snapshots[0] != snapshots[1]:
        raise ValueError("Whole-root identity changed between actual observations")
    if (joined.get("schema_version") != "anvil.marketing-private-original-process-exits.v1"
            or joined.get("kernel_scope_sha256") != hashlib.sha256(originals["kernel_scope"]).hexdigest()
            or joined.get("before_G_sha256") != digest(pre) or joined.get("original_deadline_monotonic") != deadline
            or set(joined.get("actors", {})) != {"framework", "graph"}):
        raise ValueError("Original exited process identities required")
    _pins(joined, "receiver_kernel_scope_sha256")
    _same(joined, enrollment, ("request_sha256", "operation_nonce", "boot_id"))
    _flags(joined, "capture_accepted", "native_qualified")
    for role, actual in joined["actors"].items():
        _same(actual, pre["children"][role], ("pid", "start_ticks"))
        if actual.get("pidfd_exit_observed") is not True:
            raise ValueError("Original retained pidfd exit required")
    framework, graph = joined["framework_exit"], joined["graph_join"]
    for role, document, exit_key in (("framework", framework, "returncode"), ("graph", graph, "wait_status")):
        _same(document, pre["children"][role], ("pid", "start_ticks"))
        _same(document, identity, ("request_sha256", "plan_sha256"))
        if type(document.get(exit_key)) is not int or document[exit_key] != 0:
            raise ValueError("Actual original SDK and graph successful exits required")
    _moment(framework["observed_monotonic"], deadline)
    if (seal.get("documents_sha256") != {kind: hashlib.sha256(raw).hexdigest() for kind, raw in originals.items() if kind != "capture_seal"}
            or seal.get("own_api_status_sha256") != digest(context["current_status"])
            or seal.get("own_api_tls_certificate_sha256") != profile.tls_certificate_sha256
            or seal.get("actor_output_sha256") != actor.sha256 or seal.get("actor_stop_sha256") != actor.actor_stop_sha256
            or seal.get("collection_receipt_sha256") != actor.collection_receipt_sha256):
        raise ValueError("Exact original capture seal and retained actor required")
    input_seal = seal["input_seal"]
    if (input_seal.get("schema_version") != "anvil.marketing-private-input-sealed.v1"
            or input_seal.get("api_frame_sha256") != frame.sha256
            or input_seal.get("file_sha256") != json_object(frame.raw)["file_sha256"]
            or input_seal.get("sdk_binding_sha256") != digest(frame.binding.model_dump(mode="json"))
            or input_seal.get("provenance_sha256") != json_object(frame.raw)["provenance_sha256"]):
        raise ValueError("Original API grade input seal required")
    _same(input_seal, enrollment, ("identity", "scope"))
    _flags(input_seal, "capture_accepted", "native_qualified")
    directory = input_seal.get("directory")
    if (type(directory) is not dict or directory.get("mode") != "0555" or type(directory.get("uid")) is not int
            or directory["uid"] != 0 or input_seal.get("run_authority") != "not_granted"):
        raise ValueError("Actual root-owned read-only private input directory required")
    _positive(directory, "device", "inode")
    process = check_process(result_files.process_receipt, frame.binding, profile=profile, frame_sha256=frame.sha256,
                            result_raw=result_files.verifier_result, input_seal=input_seal, verifier_document=verifier,
                            actor=actor, enrollment=enrollment)
    if (process["actor_capture_proof"].get("operation_scope_binding_sha256") != digest(root)
            or process["actor_capture_proof"].get("child_binding_sha256") != digest(children)
            or process["actor_capture_proof"].get("graph_process_join_sha256") != digest(graph)):
        raise ValueError("Original actor capture/root/graph proof changed")
    custody = verifier["custody"]
    if (custody.get("id") != result_id or custody.get("schema_version") != "anvil.marketing-private-result-custody.v1"
            or custody.get("raw_sha256") != result_files.wire_sha256
            or custody.get("grade_frame_sha256") != frame.sha256 or custody.get("grade_status") != result_checked.status
            or custody.get("verifier_result_sha256") != result_files.verifier_result_sha256
            or custody.get("process_receipt_sha256") != result_files.process_receipt_sha256):
        raise ValueError("Actual API result custody reference required")
    _same(custody, enrollment, ("enrollment_id", "manifest_id"))
    _flags(custody, "capture_accepted", "native_qualified")
    if custody.get("run_authority") != "not_granted" or custody.get("raw_bytes") != len(result_files.wire):
        raise ValueError("Actual complete result custody without execution authority required")
    if (containers.get("schema_version") != "anvil.marketing-private-owned-containers-stopped.v1"
            or set(containers.get("roles", {})) != {"environment", "tests"}):
        raise ValueError("Complete original owned container shutdown required")
    _same(containers, enrollment, ("request_sha256", "operation_nonce"))
    _flags(containers, "capture_accepted", "native_qualified")
    for role, container in containers["roles"].items():
        b, state, stop = container["binding"], container["current_state"], container["stop_observation"]
        _same(b, identity, ("job_id", "framework_trial_id", "request_sha256", "plan_sha256", "operation_nonce"))
        if (b.get("schema_version") != "anvil.marketing-owned-container.v1" or b.get("role") != role
                or b.get("image_id") != profile.runtime_image_digest or type(container.get("restart_count")) is not int
                or container["restart_count"] != 0
                or container.get("identity_fields_sha256") != b.get("inspect_config_sha256")
                or state.get("Running") is not False or type(state.get("Pid")) is not int or state["Pid"] != 0
                or state.get("Status") != "exited" or any(state.get(k) is not False for k in ("Paused", "Restarting", "Dead"))
                or stop.get("container_stopped_observed") is not True or stop.get("binding_sha256") != digest(b)
                or stop.get("binding_origin") != "completed_start" or stop.get("late_start_effects_unqualified") is not False):
            raise ValueError("Actual original containers must be stopped without identity changes")
        _pins(container, "current_inspect_sha256", "identity_fields_sha256")
        _same(stop, identity, ("framework_trial_id", "request_sha256", "plan_sha256", "operation_nonce"))
        if stop.get("role") != role or stop.get("container_id") != b.get("container_id") or stop.get("boot_id") != enrollment["boot_id"]:
            raise ValueError("Original owned container stop identity changed")
        _moment(stop["observed_monotonic"], deadline)
        if role == "tests" and (type(state.get("ExitCode")) is not int or state["ExitCode"] != 0
                or b["container_id"] != process["container_id"] or digest(b) != process["container_binding_sha256"]):
            raise ValueError("Original completed private verifier container changed")
    return {"wire_sha256": submission.wire_sha256, "grade_frame_sha256": frame.sha256,
            "verifier_result_id": result_id, "verifier_result_sha256": result_files.verifier_result_sha256,
            "process_receipt_sha256": result_files.process_receipt_sha256, "grade_status": result_checked.status}
