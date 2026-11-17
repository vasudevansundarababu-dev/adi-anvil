"""Fixed private API grade preparation over genuine retained originals.

No source qualification, private program calibration or native acceptance is
generated here. Missing original qualified profile remains an Anvil requirement.
"""

from typing import Literal
from uuid import UUID

from pydantic import Field

from anvil.campaign_semantic_contract import bounded_json
from anvil.dataset_export_contract import Model, Sha
from anvil.marketing_attester_enrollment import OriginalBinding
from anvil.marketing_capture_database import remaining
from anvil.marketing_private_actor_auth import VerifiedActor
from anvil.marketing_private_actor_auth import verify as verify_actor
from anvil.marketing_private_grade_auth import VerifiedPrivateGrade, verify
from anvil.praxis_generic_contract import canonical, digest


class PrivateGradeProfile(Model):
    schema_version: Literal["anvil.marketing-private-grade-profile-binding.v1"]
    verifier_source_sha256: Sha
    rubric_id: str = Field(min_length=1, max_length=200)
    rubric_version: str = Field(min_length=1, max_length=200)
    policy_pins: dict[str, Sha] = Field(min_length=1, max_length=128)


async def _prepare_original_reply(connection, enrollment, *, absolute_deadline, api_source_sha256):
    """Protected fixed caller; one original read-only connection/deadline.

    Entire actual controller inventory, actor bytes and authenticated framework
    identity are joined before invoking the fixed private binder. No synthetic
    controller/SQL seal, arbitrary callback or public author payload substitutes.
    """
    from anvil.marketing_private_actor_store import load_original
    from anvil.marketing_private_grade_binding import prepare_from_native_evidence
    from anvil.marketing_private_grade_evidence import load_native_evidence
    from anvil.marketing_private_grade_reply import encode_reply

    remaining(absolute_deadline)
    remaining(connection.capture_deadline)
    connection.capture_deadline = min(connection.capture_deadline, absolute_deadline)
    bounded_json(enrollment.get("private_grade_profile"), 32768, max_nodes=2000, max_depth=8)
    profile = PrivateGradeProfile.model_validate_json(canonical(enrollment["private_grade_profile"]))
    if any(not 0 < len(key) <= 200 for key in profile.policy_pins):
        raise ValueError("Original private policy source identities required")
    original = OriginalBinding.model_validate_json(canonical({
        **{key: enrollment[key] for key in ("peer_binding_id", "enrollment_id", "request_sha256", "operation_nonce",
                                           "boot_id", "profile_sha256", "producer_qualification_sha256", "scope", "expires_at")},
        "status_transport_sha256": digest(enrollment["status_transport"]),
    }))
    actor = await load_original(connection, enrollment, api_source_sha256=api_source_sha256)
    evidence = await load_native_evidence(connection, original, UUID(enrollment["manifest_id"]), digest(enrollment["descriptor"]),
                                          absolute_deadline=connection.capture_deadline)
    prepared = await prepare_from_native_evidence(
        evidence, identity=enrollment["identity"], actor_output=actor.raw,
        verifier_source_sha256=profile.verifier_source_sha256,
        rubric_id=profile.rubric_id, rubric_version=profile.rubric_version, policy_pins=profile.policy_pins,
    )
    remaining(connection.capture_deadline)
    # The source binder preserves missing original calibrated anchors as null.
    # No current-program authority is inferred from mere crosswalk/profile pins.
    return encode_reply(prepared, enrollment)


async def prepare_private_reply(connection, enrollment, verified, *, absolute_deadline, api_source_sha256):
    """Explicit signed GET consistency utility, never an unverified SDK caller."""
    if type(verified) is not VerifiedPrivateGrade:
        raise ValueError("Actual private-grade authentication required")
    if verify(verified.original_header, enrollment, api_source_sha256=api_source_sha256) != verified:
        raise ValueError("Original private-grade verification changed")
    return await _prepare_original_reply(connection, enrollment, absolute_deadline=absolute_deadline,
                                        api_source_sha256=api_source_sha256)


async def prepare_after_actor(connection, enrollment, verified, *, absolute_deadline, api_source_sha256):
    """Fixed producer after actual actor COMMIT; no GET signer or forged header.

    The actor signature independently authorizes only this original collector
    artifact flow. Recorded private files are not returned in the actor receipt;
    reading them still requires the distinct private-grade GET signature.
    """
    if type(verified) is not VerifiedActor:
        raise ValueError("Actual original actor transport verification required")
    if verify_actor(verified.original_header, enrollment, api_source_sha256=api_source_sha256) != verified:
        raise ValueError("Original actor transport verification changed")
    return await _prepare_original_reply(connection, enrollment, absolute_deadline=absolute_deadline,
                                        api_source_sha256=api_source_sha256)
