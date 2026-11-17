"""Bounded protected grader frame. No private facts go to an actor projection.

Encoding is not qualification or transport authentication. The caller must be
the authenticated private API path with genuine original custody. Candidate
mapping frames remain explicitly unqualified and cannot start a verifier.
"""

import hashlib

from anvil.campaign_semantic_contract import bounded_json
from anvil.dataset_export_contract import json_object
from anvil.marketing_capture_verifier import Identity, OriginalVerifierBinding
from anvil.marketing_private_grade_auth import FILES, PrivateGradeTransport, claims
from anvil.marketing_world_quiescence import Scope
from anvil.praxis_generic_contract import canonical

SCHEMA = "anvil.marketing-private-grade-input-reply.v1"


def encode_reply(prepared, enrollment):
    """Retain all4 original files and exact SDK/provenance bytes or reject.

    No truncation, replacement file, made-up reference, copied expected answer or
    larger-cap fallback. No identity is inferred from the prepared response.
    """
    from anvil.marketing_private_grade_binding import PreparedPrivateGrade

    if type(prepared) is not PreparedPrivateGrade:
        raise ValueError("Original fixed private-grade producer required")
    expected = claims(enrollment)
    identity = Identity.model_validate_json(canonical(enrollment["identity"])).model_dump(mode="json")
    scope = Scope.model_validate(enrollment["scope"]).model_dump(mode="json")
    bounded_json(enrollment["private_grade_transport"], 32768, max_nodes=1000, max_depth=8)
    transport = PrivateGradeTransport.model_validate_json(canonical(enrollment["private_grade_transport"]))
    if (type(prepared.mapping_qualified) is not bool or prepared.capture_accepted is not False
            or prepared.native_qualified is not False or type(prepared.files) is not tuple
            or len(prepared.files) != 3):
        raise ValueError("Exact original private producer state required")
    originals = {"verifier-input.json": prepared.manifest}
    for name, raw in prepared.files:
        if name in originals:
            raise ValueError("Duplicate original private verifier input")
        originals[name] = raw
    if set(originals) != FILES:
        raise ValueError("Exact original private verifier file set required")
    texts, hashes, objects = {}, {}, {}
    for name, raw in originals.items():
        if type(raw) is not bytes or not 0 < len(raw) <= transport.file_limits[name]:
            raise ValueError("Complete original file exceeds qualified preflight bound")
        objects[name] = json_object(raw)
        texts[name], hashes[name] = raw.decode(), hashlib.sha256(raw).hexdigest()
    bounded_json(prepared.sdk_binding, transport.reply_metadata_limit, max_nodes=4000, max_depth=12)
    sdk = OriginalVerifierBinding.model_validate_json(canonical(prepared.sdk_binding)).model_dump(mode="json")
    manifest = objects["verifier-input.json"]
    if (set(manifest) != {"schema_version", "identity", "scope", "profile", "source_sha256", "files"}
            or manifest["schema_version"] != "anvil.marketing-private-input.v1"
            or manifest["profile"] != "anvil.marketing-private-verifier.v1"
            or manifest["identity"] != identity or manifest["scope"] != scope
            or sdk["identity"] != identity or sdk["scope"] != scope
            or sdk["source_sha256"] != manifest["source_sha256"]
            or sdk["input_sha256"] != hashes["verifier-input.json"]
            or manifest["files"] != {name: value for name, value in hashes.items() if name != "verifier-input.json"}
            or sdk["input_files"] != manifest["files"]):
        raise ValueError("Private verifier frame differs from original framework/input identity")
    provenance_raw = prepared.provenance
    if type(provenance_raw) is not bytes or not 0 < len(provenance_raw) <= transport.reply_metadata_limit:
        raise ValueError("Original private provenance exceeds qualified bound")
    provenance = json_object(provenance_raw)
    native = provenance.get("native_evidence")
    if (type(native) is not dict or native.get("origin") != "api_immutable_native_records"
            or any(native.get(key) != enrollment[key] for key in
                   ("enrollment_id", "manifest_id", "request_sha256", "operation_nonce"))
            or native.get("scope") != scope or native.get("descriptor_sha256") != expected["descriptor_sha256"]
            or native.get("identity") != identity
            or provenance.get("mapping_status") != ("qualified_source_crosswalk" if prepared.mapping_qualified else "candidate_unqualified")
            or provenance.get("capture_accepted") is not False or provenance.get("native_qualified") is not False):
        raise ValueError("Genuine complete API original provenance required")
    metadata_size = len(canonical(sdk)) + len(provenance_raw)
    if metadata_size > transport.reply_metadata_limit:
        raise ValueError("Whole original SDK/provenance metadata exceeds preflight bound")
    value = {"schema_version": SCHEMA,
             **{key: enrollment[key] for key in ("enrollment_id", "manifest_id", "request_sha256", "operation_nonce")},
             "scope": scope, "identity": identity, "files": texts, "file_sha256": hashes,
             "sdk_binding": sdk, "provenance": provenance_raw.decode(),
             "provenance_sha256": hashlib.sha256(provenance_raw).hexdigest(),
             "mapping_qualified": prepared.mapping_qualified,
             "capture_accepted": False, "native_qualified": False, "run_authority": "not_granted"}
    bounded_json(value, transport.response_limit, max_nodes=100000, max_depth=24)
    raw = canonical(value)
    maximum = 4096 + 2 * sum(transport.file_limits.values()) + 2 * transport.reply_metadata_limit
    if len(raw) > min(maximum, transport.response_limit):
        raise ValueError("Whole original private reply exceeds its qualified preflight bound")
    return raw
