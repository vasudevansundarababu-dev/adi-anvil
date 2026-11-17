"""Real TEST-key crypto and strict status DTOs; no transport qualification."""

import base64
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from test_marketing_capture_attestation import header as upload_header
from test_marketing_capture_attestation import signing_packet
from test_marketing_capture_evidence import packet as evidence_packet

from anvil.marketing_capture_attestation import verify as verify_upload
from anvil.marketing_capture_evidence import prepare
from anvil.marketing_capture_status import CONTROLS, DOMAIN, PATH, claims, validate_response, verify
from anvil.praxis_generic_contract import canonical, digest


def packet(*, now=None, include_quiescence=False):
    now = datetime(2026, 11, 14, 18, tzinfo=timezone.utc) if now is None else now
    enrollment, _, _, upload, key, _ = signing_packet(now=now)
    context, rows, _ = evidence_packet()
    enrollment["scope"] = context["scope"]
    enrollment["status_transport"] = {"schema_version": "anvil.marketing-status-transport-qualification.v1",
                                      "origin": "https://anvil-qa.adi-labs.ai", "path": PATH, "method": "GET",
                                      "api_image_digest": "sha256:" + "a" * 64, "source_sha256": "1" * 64,
                                      "ingress_evidence_sha256": "b" * 64, "ca_bundle_sha256": "c" * 64,
                                      "not_after": (now + timedelta(seconds=90)).isoformat(), "cleanup_reserve_seconds": 10,
                                      "controls": {name: {"status": "passed", "evidence_sha256": "d" * 64} for name in CONTROLS}}
    context.update(enrollment_id=enrollment["enrollment_id"], request_sha256=enrollment["request_sha256"],
                   operation_nonce=enrollment["operation_nonce"], expires_at=(now + timedelta(seconds=60)).isoformat(),
                   materialize_before=(now + timedelta(seconds=50)).isoformat())
    context["quiescence"]["observed_at"] = now.isoformat().replace("+00:00", "Z")
    context["quiescence"].pop("receipt_sha256")
    context["quiescence"]["receipt_sha256"] = digest(context["quiescence"])
    prepared = prepare(context, rows, now=now)
    status = {"schema_version": "anvil.marketing-api-evidence-status.v1", "scope": deepcopy(context["scope"]),
              **{field: context[field] for field in ("manifest_id", "enrollment_id", "request_sha256", "operation_nonce")},
              "state": "ready", "descriptor": deepcopy(prepared.descriptor), "capture_accepted": False, "native_qualified": False}
    result = (enrollment, status, key, now, upload)
    return result + (deepcopy(context["quiescence"]),) if include_quiescence else result


def sign(enrollment, key, *, values=None, domain=DOMAIN):
    raw = canonical(claims(enrollment) if values is None else values)
    def encode(value):
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode()

    return "v1." + encode(raw) + "." + encode(key.sign(domain + raw))


def test_fixed_empty_get_signature_authenticates_original_scope_without_upload_authority():
    enrollment, status, key, now, upload = packet()
    signed = sign(enrollment, key)
    assert verify(signed, enrollment, now=now, api_source_sha256="1" * 64).enrollment_id == enrollment["enrollment_id"]
    assert validate_response(canonical(status), enrollment, now=now).state == "ready"
    with pytest.raises(ValueError, match="attestation_rejected"):
        verify_upload(signed, enrollment, now=now)
    with pytest.raises(ValueError, match="status_authentication_rejected"):
        verify(upload_header(upload, key), enrollment, now=now)


@pytest.mark.parametrize("field,value", [("method", "POST"), ("path", "/internal/v1/marketing/native-capture"),
                                         ("audience", "https://other.invalid"), ("scope_sha256", "f" * 64),
                                         ("operation_nonce", "f" * 64), ("body_sha256", "f" * 64),
                                         ("role", "api"), ("alg", "none")])
def test_even_a_valid_test_signature_cannot_change_status_purpose_scope_or_key_selection(field, value):
    enrollment, _, key, now, _ = packet()
    value = claims(enrollment) | {field: value}
    with pytest.raises(ValueError, match="status_authentication_rejected"):
        verify(sign(enrollment, key, values=value), enrollment, now=now)


def test_original_transport_and_current_api_source_are_required_not_an_owner_ready_boolean():
    enrollment, _, key, now, _ = packet()
    signed = sign(enrollment, key)
    with pytest.raises(ValueError):
        verify(signed, enrollment, now=now, api_source_sha256="2" * 64)
    missing = deepcopy(enrollment)
    missing.pop("status_transport")
    with pytest.raises(ValueError):
        verify(signed, missing, now=now)
    with pytest.raises(ValueError):
        verify(sign(enrollment, key, domain=b""), enrollment, now=now)


def test_get_expiry_reserves_physical_cleanup_and_cannot_be_extended():
    enrollment, status, key, now, _ = packet()
    signed = sign(enrollment, key)
    with pytest.raises(ValueError):
        verify(signed, enrollment, now=now + timedelta(seconds=50))
    with pytest.raises(ValueError):
        validate_response(canonical(status), enrollment, now=now + timedelta(seconds=50))
    altered = claims(enrollment) | {"expires_at": (now + timedelta(seconds=61)).isoformat().replace("+00:00", "Z")}
    with pytest.raises(ValueError):
        verify(sign(enrollment, key, values=altered), enrollment, now=now)


@pytest.mark.parametrize("change", ["extra", "scope", "acceptance", "unknown_ready", "manifest", "incomplete_counts", "noncanonical"])
def test_response_must_be_complete_original_canonical_api_content_not_owner_projection(change):
    enrollment, status, _, now, _ = packet()
    if change == "extra":
        status["caller_claimed_ready"] = True
    elif change == "scope":
        status["scope"]["generation"] += 1
    elif change == "acceptance":
        status["capture_accepted"] = 0
    elif change == "unknown_ready":
        status["state"] = "materialization_unknown"
    elif change == "manifest":
        status["descriptor"]["manifest_id"] = "11111111-1111-4111-8111-111111111111"
    elif change == "incomplete_counts":
        status["descriptor"]["category_counts"]["sdk_prompts"] = 0
    raw = canonical(status)
    if change == "noncanonical":
        raw += b" "
    with pytest.raises(ValueError):
        validate_response(raw, enrollment, now=now)
