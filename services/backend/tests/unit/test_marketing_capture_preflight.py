"""New full-envelope budget and original-scope controls; no provider or SQL."""

import hashlib
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_marketing_capture_submission import packet

from anvil.marketing_capture_store import AuthenticatedProducer, begin, require_sdk_capture_budget
from anvil.marketing_capture_submission import KINDS, WIRE_CAP, parse, wire_budget
from anvil.marketing_world_registry import require_sdk
from anvil.praxis_generic_contract import canonical


class Connection:
    def __init__(self, value):
        self.value, self.calls = value, []

    def execute(self, sql, args):
        self.calls.append((sql, args))
        return SimpleNamespace(fetchone=lambda: {"value": self.value})


def context():
    value, _ = packet()
    scope = {key: str(uuid4()) for key in ("project_id", "job_id", "plan_id", "world_binding_id", "episode_id")}
    scope.update({key: "a" * 64 for key in ("world_binding_sha256", "lease_sha256", "source_qualification_sha256", "execution_sha256")})
    scope["generation"] = 0
    value.update(scope=scope, **{key: scope[key] for key in ("project_id", "job_id", "plan_id")})
    return value


def test_individually_legal_documents_cannot_silently_exceed_whole_wire_cap():
    enrollment, _ = packet()
    enrollment["document_limits"] = {kind: WIRE_CAP for kind in KINDS}
    with pytest.raises(ValueError, match="requires_complete_api_held_bulk_refs"):
        wire_budget(enrollment)


def test_full_wire_upper_bound_covers_utf8_and_worst_escaped_inline_documents():
    enrollment, value = packet()
    document = canonical({"quoted": ('"\\\n' * 200), "unicode": "🦉" * 100}).decode()
    value["documents"] = {kind: document for kind in KINDS}
    raw = canonical(value)
    bound = wire_budget(enrollment)
    assert len(raw) <= bound["maximum_wire_bytes"] <= WIRE_CAP
    assert parse(raw, enrollment).wire == raw


def test_absent_original_capture_profile_denies_before_spending():
    connection = Connection(None)
    claim = SimpleNamespace(job_id=uuid4(), lease_token=uuid4(), plan_id=uuid4())
    with pytest.raises(RuntimeError, match="required_before_spending"):
        require_sdk_capture_budget(connection, claim)
    assert len(connection.calls) == 1


def test_real_sdk_readiness_entry_requires_capture_preflight_before_other_runtime_or_secret_access():
    connection = Connection(None)
    claim = SimpleNamespace(job_id=uuid4(), lease_token=uuid4(), plan_id=uuid4(), actor_id=uuid4())
    plan = {"id": claim.plan_id, "created_by": claim.actor_id}
    with pytest.raises(RuntimeError, match="required_before_spending"):
        require_sdk(connection, claim, plan)
    assert len(connection.calls) == 1 and "capture_plan_preflight" in connection.calls[0][0]


@pytest.mark.parametrize("field", ["project_id", "job_id", "plan_id"])
def test_original_world_scope_cannot_be_swapped_by_enrollment_context(field):
    value = context()
    value[field] = str(uuid4())
    connection = Connection(value)
    identity = AuthenticatedProducer("operator_attested_root_peer_v1", "c" * 64, None)
    with pytest.raises(ValueError, match="original_world_scope_changed"):
        begin(connection, identity, value["enrollment_id"])
    assert len(connection.calls) == 1


def test_matching_private_scope_and_bounded_profile_remain_intake_only_not_acceptance():
    value = context()
    connection = Connection(value)
    identity = AuthenticatedProducer("operator_attested_root_peer_v1", "c" * 64, None)
    result = begin(connection, identity, value["enrollment_id"])
    assert result is value and "accepted_capture_reference" not in result


@pytest.mark.parametrize("changed", ["project_id", "job_id", "plan_id", "lease"])
def test_foreign_original_scope_or_lease_cannot_pass_provider_capture_preflight(changed):
    value = context()
    claim = SimpleNamespace(**{key: value[key] for key in ("project_id", "job_id", "plan_id")}, lease_token=uuid4())
    value["scope"]["lease_sha256"] = hashlib.sha256(str(claim.lease_token).encode()).hexdigest()
    if changed == "lease":
        claim.lease_token = uuid4()
    else:
        setattr(claim, changed, uuid4())
    with pytest.raises(ValueError, match="original_sdk_scope_changed"):
        require_sdk_capture_budget(Connection(value), claim)


def test_original_scope_and_lease_can_pass_only_wire_budget_not_native_admission():
    value = context()
    claim = SimpleNamespace(**{key: value[key] for key in ("project_id", "job_id", "plan_id")}, lease_token=uuid4())
    value["scope"]["lease_sha256"] = hashlib.sha256(str(claim.lease_token).encode()).hexdigest()
    result = require_sdk_capture_budget(Connection(value), claim)
    assert result == wire_budget(value)
