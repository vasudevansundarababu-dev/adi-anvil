"""Pure facade/rights metadata comparisons, never world or rights qualification."""

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from anvil.marketing_native_boundary import (
    DOCUMENT_CAP,
    PURPOSE,
    MarketingCampaignRequestV1,
    _bounded_canonical,
    _digest,
    prepare_marketing_request,
)
from anvil.marketing_native_records import _parse_record

FACADE_SYMBOL = "anvil.marketing_paid_world.QualifiedWorld"
FACADE_SOURCE_SHA256 = "86fb9468a37c26962ea80e453e770546516799abc33ed6018ae18886796a1761"
CANDIDATE_FACADE_SOURCE_SHA256 = "3037bac7d80271727f882b00369ad0e597ec7f32accd42b85501ceaa2d388750"
WORLD_RPC_SOURCES = {
    "marketing_paid_world.py": FACADE_SOURCE_SHA256,
    "marketing_paid_world_transport.py": "16d5b504fbd5e2498550f2d9e5dcfa1942372b411f93c9677732ada2470bbbd1",
    "marketing_paid_world_rpc.py": "6098089949b7c538793b51870ba127061318a049c6ff8d046689e403d626da8e",
}
CANDIDATE_GRAPH_SOURCES = {
    "marketing_paid_world.py": CANDIDATE_FACADE_SOURCE_SHA256,
    "marketing_paid_world_transport.py": "10a1ad6bbd7858cf2c1d3dfe7c54f87a5763f73c3fa80d5cdd2779519b6fdc85",
    "marketing_paid_world_rpc.py": "6098089949b7c538793b51870ba127061318a049c6ff8d046689e403d626da8e",
    "marketing_paid_graph.py": "584575065df5080220d1db48af603072b8a2c400e65a22605a6847c67f70fc30",
    "marketing_graph_result.py": "9383df2084681c54c85ee1a15d24dbea0d590b53831945b93f3ad61331581f31",
    "marketing_world_role.py": "8926b03fb7915cc78ec8c5b6e3b12e3eb2182b3578f6ac16a101d636a5770327",
    "marketing_paid_execution.py": "e3166a8f0a72abf07c65d002075e484adda67b4566d246e6868b1ec92c144919",
    "worker_dispatch_broker.py": "ca6e463453390944acefb84fb7d2ac3f55a2ad09c1270cb684a4f67d03900db7",
    "marketing_paid_dispatch_rpc.py": "167fe95fec59ed3818c34b508b46fd178d59007530e862678b193f37baada99e",
    "marketing_paid_dispatch_transport.py": "4dd8c06845c6b1318646c6bdf81c55a845640eb41e9e9c0b9e6ab86197a9014b",
    "marketing_world_quiescence.py": "ae75846bcfc96c27975ce330413a452f673f132fbf8004bc94eebb1cd9949d91",
}
PROJECTION_FIELDS = frozenset({
    "schema_version", "project_id", "actor_id", "job_id", "plan_id",
    "world_binding_id", "world_binding_sha256", "episode_id", "generation",
    "case_id", "case_snapshot_sha256", "execution_sha256", "native_binding_sha256",
    "source_manifest_sha256", "dataset_qualification_sha256", "rights_receipt_sha256", "rights_ref",
})

# Separate source nomination only. Neither operating nor predecessor candidate
# pins above are changed; this v3 root path still requires native qualification.
OPENING_SOURCE_MANIFEST_SHA256 = "2cca90e1823dddfd3e79f57f0bd7e1107779c2d84c2b229d39c70a33e3537a6e"
OPENING_GRAPH_SOURCES = {
    "marketing_graph_result.py": "577a57b7dc81cbe73aa4941770e94720e419206f19fd7ab18e9fe3729864e367",
    "marketing_paid_dispatch_rpc.py": "167fe95fec59ed3818c34b508b46fd178d59007530e862678b193f37baada99e",
    "marketing_paid_dispatch_transport.py": "4dd8c06845c6b1318646c6bdf81c55a845640eb41e9e9c0b9e6ab86197a9014b",
    "marketing_paid_execution.py": "e3166a8f0a72abf07c65d002075e484adda67b4566d246e6868b1ec92c144919",
    "marketing_paid_graph.py": "8222adda18f5994343c38918911635a047fdabf0a2b51b7adbe3c35aae2af1f4",
    "marketing_paid_world.py": "7c94f762641abaf8db94b1b8ae121f0dc8506044b765e412abb8d9d30b6c17db",
    "marketing_paid_world_rpc.py": "6098089949b7c538793b51870ba127061318a049c6ff8d046689e403d626da8e",
    "marketing_paid_world_transport.py": "10a1ad6bbd7858cf2c1d3dfe7c54f87a5763f73c3fa80d5cdd2779519b6fdc85",
    "marketing_world_quiescence.py": "4cdb918d16aa0aea7223a4e5c4658952b7d4fd9ec3ef31eaf4d65cbdd2df9441",
    "marketing_world_role.py": "8926b03fb7915cc78ec8c5b6e3b12e3eb2182b3578f6ac16a101d636a5770327",
    "worker_dispatch_broker.py": "9aa091debc4969d10535ccb137712495494e3618767427fdb1a945bbd1faa515",
}


@dataclass(frozen=True, slots=True)
class WorldBindingBytesV1:
    request_sha256: str
    projection_sha256: str
    # Public immutable metadata only; no lease/context/private fixture/authority.
    canonical_projection: bytes


def validate_world_binding(request, projection_raw, world_record_raw):
    return _validate_world_binding(request, projection_raw, world_record_raw, candidate=False)


def validate_candidate_world_binding(request, projection_raw, world_record_raw):
    return _validate_world_binding(request, projection_raw, world_record_raw, candidate=True)


def validate_opening_world_binding(request, projection_raw, world_record_raw):
    return _validate_world_binding(request, projection_raw, world_record_raw, candidate=True, opening=True)


def validate_private_world_binding(request, projection_raw, world_record_raw):
    return _validate_world_binding(request, projection_raw, world_record_raw, candidate=True, opening=True, private=True)


def opening_source_nomination(*, private=False):
    if type(private) is not bool:
        raise ValueError('marketing_explicit_source_nomination_required')
    if private:
        from anvil.marketing_native_private_sources import PRIVATE_SOURCE_MANIFEST_SHA256

        return PRIVATE_SOURCE_MANIFEST_SHA256
    return OPENING_SOURCE_MANIFEST_SHA256


def retained_source_nomination(store, root):
    """Select only the independently reconciled original context's variant."""
    intent = _parse_record(store._read(root, 'component-context-intent.json'))
    version = intent.get('schema_version')
    if version == 'anvil.marketing-component-context-intent.v3':
        if intent.get('private_program_sha256') != hashlib.sha256(store._read(root, 'private-verifier-program.json')).hexdigest():
            raise ValueError('marketing_original_private_program_source_nomination_required')
        return opening_source_nomination(private=True)
    if version != 'anvil.marketing-component-context-intent.v2':
        raise ValueError('marketing_original_opening_source_context_required')
    return opening_source_nomination()


def _validate_world_binding(request, projection_raw, world_record_raw, *, candidate, opening=False, private=False):
    if type(private) is not bool or private and not opening:
        raise ValueError('marketing_explicit_private_world_binding_required')
    sources = OPENING_GRAPH_SOURCES
    if private:
        from anvil.marketing_native_private_sources import PRIVATE_GRAPH_SOURCES

        sources = PRIVATE_GRAPH_SOURCES
    if type(request) is not MarketingCampaignRequestV1:
        raise ValueError("marketing_exact_typed_request_required")
    prepare_marketing_request(request.canonical_bytes)
    value = json.loads(request.canonical_bytes)
    projection = _parse_record(projection_raw)
    record = _parse_record(world_record_raw)
    context = _digest({key: item for key, item in value.items() if key != "asset_manifest_sha256"})
    if (
        set(record) != {"schema_version", "purpose", "request_context_sha256", "payload"}
        or record["schema_version"] != (
            "anvil.marketing-native-world.v3" if opening else
            "anvil.marketing-native-world.v2" if candidate else "anvil.marketing-native-world.v1")
        or record["purpose"] != PURPOSE or record["request_context_sha256"] != context
        or type(record["payload"]) is not dict
    ):
        raise ValueError("marketing_distinct_world_record_required")
    payload = record["payload"]
    if (
        set(payload) != ({"facade_symbol", "facade_source_sha256", "binding_projection"}
                         | ({"stop_scope"} if candidate else set())
                         | ({"source_nomination_sha256"} if opening else set()))
        or payload["facade_symbol"] != FACADE_SYMBOL
        or payload["facade_source_sha256"] != (
            sources['marketing_paid_world.py'] if opening else
            CANDIDATE_FACADE_SOURCE_SHA256 if candidate else FACADE_SOURCE_SHA256)
        or opening and payload.get('source_nomination_sha256') != opening_source_nomination(private=private)
        or type(payload["binding_projection"]) is not dict
        or _bounded_canonical(payload["binding_projection"], DOCUMENT_CAP) != projection_raw
    ):
        raise ValueError("marketing_independent_world_projection_changed")
    if (
        set(projection) != PROJECTION_FIELDS
        or projection["schema_version"] != "anvil.marketing-world-attachment.v1"
        or type(projection["generation"]) is not int
        or projection["generation"] != value["generation"]
        or projection["case_id"] != value["case_assignment"]["case_id"]
        or projection["case_snapshot_sha256"] != value["case_assignment"]["snapshot_sha256"]
        or any(projection[key] != value[key] for key in (
            "project_id", "actor_id", "job_id", "plan_id", "episode_id", "execution_sha256",
            "native_binding_sha256", "source_manifest_sha256", "dataset_qualification_sha256", "rights_ref",
        ))
    ):
        raise ValueError("marketing_exact_world_request_projection_required")
    for key in ("project_id", "actor_id", "job_id", "plan_id", "world_binding_id", "episode_id"):
        if type(projection[key]) is not str or str(UUID(projection[key])) != projection[key]:
            raise ValueError("marketing_canonical_world_uuid_required")
    for key in ("world_binding_sha256", "rights_receipt_sha256"):
        if type(projection[key]) is not str or not re.fullmatch(r"[a-f0-9]{64}", projection[key]):
            raise ValueError("marketing_exact_world_receipt_pin_required")
    if projection["rights_ref"] != "anvil-rights-receipt:sha256:" + projection["rights_receipt_sha256"]:
        raise ValueError("marketing_exact_rights_reference_receipt_required")
    return WorldBindingBytesV1(
        hashlib.sha256(request.canonical_bytes).hexdigest(),
        hashlib.sha256(projection_raw).hexdigest(), projection_raw,
    )


def validate_expected_world_record(request, world_record_raw):
    """Compare independent expected bytes BEFORE any future one-way attach."""
    record = _parse_record(world_record_raw)
    try:
        projection_raw = _bounded_canonical(record["payload"]["binding_projection"], DOCUMENT_CAP)
    except (KeyError, TypeError):
        raise ValueError("marketing_expected_world_projection_required") from None
    return validate_world_binding(request, projection_raw, world_record_raw)


def validate_prepared_world_binding(request, prepared, world_record_raw):
    """Compare once-prepared public identity before read-only attach, no API call.

    Campaign context is validated by the fixed facade against pinned native data;
    this projection contains immutable public binding/rights identities only.
    """
    projection = _prepared_world_projection(prepared)
    return validate_world_binding(request, projection, world_record_raw)


def _prepared_world_projection(prepared):
    if type(prepared) is not dict or type(prepared.get("world_attachment")) is not dict:
        raise ValueError("marketing_once_prepared_world_required")
    attachment = prepared["world_attachment"]
    if (set(attachment) != (PROJECTION_FIELDS - {"rights_ref"}) | {"campaign_context"}
            or type(attachment["campaign_context"]) is not dict
            or prepared.get("world_attachment_sha256") != _digest(attachment)
            or type(attachment["rights_receipt_sha256"]) is not str
            or not re.fullmatch(r"[a-f0-9]{64}", attachment["rights_receipt_sha256"])):
        raise ValueError("marketing_exact_prepared_attachment_bytes_required")
    projection = {key: item for key, item in attachment.items() if key != "campaign_context"}
    projection["rights_ref"] = "anvil-rights-receipt:sha256:" + attachment["rights_receipt_sha256"]
    return _bounded_canonical(projection, DOCUMENT_CAP)


def validate_candidate_prepared_world_binding(request, prepared, world_record_raw):
    """Independent v2 stop scope BEFORE intent, never learned from a stop reply."""
    return _validate_candidate_prepared_world_binding(request, prepared, world_record_raw, opening=False)


def validate_opening_prepared_world_binding(request, prepared, world_record_raw):
    return _validate_candidate_prepared_world_binding(request, prepared, world_record_raw, opening=True)


def validate_private_prepared_world_binding(request, prepared, world_record_raw):
    return _validate_candidate_prepared_world_binding(request, prepared, world_record_raw, opening=True, private=True)


def _validate_candidate_prepared_world_binding(request, prepared, world_record_raw, *, opening, private=False):
    from anvil.marketing_world_quiescence import Scope

    projection = _prepared_world_projection(prepared)
    binding = (validate_private_world_binding if private else
               validate_opening_world_binding if opening else validate_candidate_world_binding)(
        request, projection, world_record_raw)
    record = _parse_record(world_record_raw)
    expected = record['payload']['stop_scope']
    observed = prepared.get('world_stop_scope')
    scope = Scope.model_validate(expected).model_dump(mode='json')
    if (scope != expected or Scope.model_validate(observed).model_dump(mode='json') != observed
            or _bounded_canonical(scope, DOCUMENT_CAP) != _bounded_canonical(observed, DOCUMENT_CAP)):
        raise ValueError('marketing_independent_prepared_stop_scope_required')
    public = _parse_record(projection)
    if any(scope[key] != public[key] for key in (
        'project_id', 'job_id', 'plan_id', 'world_binding_id', 'world_binding_sha256',
        'episode_id', 'generation', 'execution_sha256',
    )):
        raise ValueError('marketing_original_prepared_stop_scope_changed')
    # source_qualification_sha256 remains its distinct independently held private
    # world receipt reference; dataset_qualification_sha256 is never substituted.
    return binding, _bounded_canonical(scope, DOCUMENT_CAP)


def _verify_source_file(filename, expected):
    if filename not in WORLD_RPC_SOURCES or expected != WORLD_RPC_SOURCES[filename]:
        raise ValueError("marketing_fixed_world_source_allowlist_required")
    return _read_source_file(filename, expected)


def _read_source_file(filename, expected):
    path = Path(__file__).with_name(filename)
    if path.resolve() != path:
        raise ValueError("marketing_fixed_facade_source_path_required")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
            or before.st_mode & 0o022 or before.st_nlink != 1 or before.st_size > DOCUMENT_CAP
        ):
            raise ValueError("marketing_facade_source_custody_required")
        raw = stream.read(DOCUMENT_CAP + 1)
        after = os.fstat(stream.fileno())
    if (
        len(raw) > DOCUMENT_CAP
        or (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        or hashlib.sha256(raw).hexdigest() != expected
    ):
        raise ValueError("marketing_reviewed_facade_source_changed")
    return path


def verify_facade_source():
    """Three fixed source files, not full loaded-origin/interpreter qualification."""
    verified = {name: _verify_source_file(name, pin) for name, pin in WORLD_RPC_SOURCES.items()}
    return verified["marketing_paid_world.py"]


def verify_candidate_graph_sources():
    """Candidate file custody only, not full loaded-code/runtime qualification."""
    return {name: _read_source_file(name, pin) for name, pin in CANDIDATE_GRAPH_SOURCES.items()}


def verify_opening_graph_sources(*, private=False):
    """Nominated file custody only; no loaded-origin/native qualification."""
    if type(private) is not bool:
        raise ValueError('marketing_explicit_private_source_nomination_required')
    if private:
        from anvil.marketing_native_private_sources import PRIVATE_GRAPH_SOURCES

        return {name: _read_source_file(name, pin) for name, pin in PRIVATE_GRAPH_SOURCES.items()}
    return {name: _read_source_file(name, pin) for name, pin in OPENING_GRAPH_SOURCES.items()}
