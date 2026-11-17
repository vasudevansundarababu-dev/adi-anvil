"""Exact v7 public policy bytes; never source creation or legal approval.

Only a genuine current product-scope policy qualification may select a public
materialization. Legacy093 latest-state materializations are not read here.
"""

import asyncio
import hashlib
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator

from anvil.dataset_export_contract import Identifier, Model, Sha, json_object
from anvil.golden_kyc_policy_registry import ProductRegistryScope, RegistryRecord
from anvil.marketing_native_wire_bounds import bounded_json, remaining
from anvil.praxis_case_dataset import PolicyRef
from anvil.praxis_generic_contract import canonical, digest

MAX_BODY = 131072
MAX_PUBLIC_TEXT = 8192
MAX_RECORDS = 100


class PolicyArtifact(Model):
    kind: Literal["common", "state"]
    reference: PolicyRef
    hash_scheme: Literal["sha256_raw_utf8", "sha256_rfc8785_json"]
    artifact_utf8: str = Field(min_length=1, max_length=MAX_BODY)
    artifact_sha256: Sha
    public_text_pointer: str | None = Field(default=None, max_length=1000)
    public_text_utf8: str = Field(min_length=1, max_length=MAX_PUBLIC_TEXT)
    public_text_sha256: Sha

    @model_validator(mode="after")
    def exact_original(self):
        raw, text = self.artifact_utf8.encode(), self.public_text_utf8.encode()
        if (len(raw)>MAX_BODY or len(text)>MAX_PUBLIC_TEXT or hashlib.sha256(raw).hexdigest()!=self.artifact_sha256
                or hashlib.sha256(text).hexdigest()!=self.public_text_sha256):
            raise ValueError("Exact public policy artifact and delivered text required")
        if self.hash_scheme == "sha256_raw_utf8":
            if self.public_text_pointer is not None or raw != text or self.reference.content_sha256 != self.artifact_sha256:
                raise ValueError("Raw policy content reference must hash the complete original UTF8 bytes")
        else:
            document = json_object(raw)
            bounded_json(document, MAX_BODY, max_nodes=20000, max_depth=24)
            if digest(document) != self.reference.content_sha256 or type(self.public_text_pointer) is not str:
                raise ValueError("Canonical policy reference and explicit public-text pointer required")
            value = document
            if not self.public_text_pointer.startswith("/"):
                raise ValueError("Explicit original public policy text location required")
            for part in self.public_text_pointer[1:].split("/"):
                if "~" in part.replace("~0", "").replace("~1", ""):
                    raise ValueError("Invalid policy public text pointer")
                key = part.replace("~1", "/").replace("~0", "~")
                if type(value) is dict:
                    if key not in value:
                        raise ValueError("Published public policy text pointer does not resolve")
                    value = value[key]
                elif type(value) is list and key.isdecimal() and str(int(key)) == key and int(key)<len(value):
                    value = value[int(key)]
                else:
                    raise ValueError("Published public policy text pointer does not resolve")
            if type(value) is not str or value.encode()!=text:
                raise ValueError("Delivered policy text must match the original published artifact")
        return self


class Materialization(Model):
    schema_version: Literal["anvil.kyc-application-policy-materialization.v1"]
    id: UUID
    qualification_id: UUID
    scope: ProductRegistryScope
    policy_set_sha256: Sha
    application_id: Identifier | None = None
    artifacts: list[PolicyArtifact] = Field(min_length=1, max_length=200)
    expires_at: AwareDatetime


@dataclass(frozen=True, slots=True)
class PolicyDelivery:
    status: str
    requirement: str | None
    public: dict | None = None
    materialization_id: str | None = None
    content_sha256: str | None = None
    run_authority: str = "not_granted"


def validate_materialization(raw, parent, *, application_id, checked_at):
    if type(raw) is not bytes or not 0<len(raw)<=MAX_BODY or type(parent) is not RegistryRecord:
        raise ValueError("Exact original policy materialization and qualified parent required")
    value = json_object(raw)
    bounded_json(value, MAX_BODY, max_nodes=30000, max_depth=24)
    if canonical(value)!=raw:
        raise ValueError("Complete canonical policy materialization required")
    body = Materialization.model_validate_json(raw)
    if (type(parent.scope) is not ProductRegistryScope or body.scope!=parent.scope
            or body.qualification_id!=parent.id or body.policy_set_sha256!=parent.policy_set_sha256
            or body.application_id not in (None, application_id)
            or not checked_at<body.expires_at<=parent.expires_at):
        raise ValueError("Exact current v7 application policy qualification required")
    expected = {(kind, ref.id, ref.version, ref.content_sha256, ref.publication_ref)
                for kind, refs in (("common",parent.policy_set.federal_refs),("state",parent.policy_set.state_refs)) for ref in refs}
    actual = [(a.kind,a.reference.id,a.reference.version,a.reference.content_sha256,a.reference.publication_ref) for a in body.artifacts]
    if len(actual)!=len(set(actual)) or set(actual)!=expected or sum(len(a.public_text_utf8.encode()) for a in body.artifacts)>MAX_PUBLIC_TEXT:
        raise ValueError("Complete common and applicable state policy texts required within existing delivery bound")
    rules = {"common":[],"state":[]}
    for artifact in body.artifacts:
        ref = artifact.reference
        rules[artifact.kind].append({"id":ref.id,"version":ref.version,"content_sha256":ref.content_sha256,
            "source_location":ref.publication_ref,"text":artifact.public_text_utf8,
            "public_text_sha256":artifact.public_text_sha256,"artifact_sha256":artifact.artifact_sha256,
            "hash_scheme":artifact.hash_scheme,"effective_from":parent.policy_set.effective_from.isoformat(),
            "effective_until":parent.policy_set.effective_until.isoformat(),"governing_state":parent.policy_set.governing_state})
    public = {"schema_version":"anvil.bound-application-policy.v1","application_id":application_id,
        "product":parent.policy_set.product,"governing_state":parent.policy_set.governing_state,
        "charter_profile":parent.policy_set.charter_profile,"policy_set_sha256":parent.policy_set_sha256,
        "bound_common_rules":rules["common"],"bound_state_rules":rules["state"],
        "qualification_id":str(parent.id),"materialization_id":str(body.id),"legal_acceptance":"not_established"}
    bounded_json(public,32768,max_nodes=10000,max_depth=12)
    return PolicyDelivery("exact_policy_materialized_not_run_authority",None,public,str(body.id),hashlib.sha256(raw).hexdigest())


READ_SQL = """
SELECT m.id,m.body_canonical,m.content_sha256,m.expires_at,q.body AS parent,q.content_sha256 AS parent_sha256,
 statement_timestamp() AS checked_at
FROM anvil.kyc_application_policy_materializations m
JOIN anvil.kyc_application_policy_qualifications q ON q.project_id=m.project_id AND q.id=m.qualification_id
WHERE m.project_id=%s AND q.id=%s AND q.scope_sha256=%s
 AND q.expires_at>statement_timestamp() AND m.expires_at>statement_timestamp()
 AND (m.application_id IS NULL OR m.application_id=%s)
 AND NOT EXISTS(SELECT 1 FROM anvil.kyc_application_policy_revocations r WHERE r.project_id=q.project_id AND r.qualification_id=q.id)
 AND NOT EXISTS(SELECT 1 FROM anvil.kyc_application_policy_materialization_revocations r WHERE r.project_id=m.project_id AND r.materialization_id=m.id)
LIMIT 101
"""


def _validated_rows(rows, scope, application_id, qualification_id):
    if len(rows)!=1:
        return PolicyDelivery("blocked","AV_KYC_EXACT_POLICY_TEXT_PROVISIONING_REQUIRED" if not rows else "AV_KYC_POLICY_TEXT_AMBIGUOUS")
    row=rows[0]
    parent = RegistryRecord.model_validate_json(canonical(row["parent"]))
    raw=row["body_canonical"].encode()
    if digest(row["parent"])!=row["parent_sha256"] or hashlib.sha256(raw).hexdigest()!=row["content_sha256"]:
        raise ValueError("Actual original policy materialization integrity changed")
    result=validate_materialization(raw,parent,application_id=application_id,checked_at=row["checked_at"])
    if (result.materialization_id!=str(row["id"]) or parent.scope!=scope
            or str(parent.id)!=str(qualification_id)
            or Materialization.model_validate_json(raw).expires_at!=row["expires_at"]):
        raise ValueError("Actual exact qualified policy materialization scope changed")
    return result


def _parameters(scope, application_id, qualification_id):
    if type(scope) is not ProductRegistryScope:
        raise ValueError("Exact original product policy scope required")
    return (scope.project_id, qualification_id, digest(scope.model_dump(mode="json")), application_id)


def load(connection, scope, application_id, qualification_id):
    """Synchronous consistency utility; does not establish runtime admission."""
    parameters = _parameters(scope, application_id, qualification_id)
    exists = connection.execute("SELECT to_regclass('anvil.kyc_application_policy_materializations') AS relation").fetchone()
    if not exists or not exists["relation"]:
        return PolicyDelivery("blocked","AV_KYC_EXACT_POLICY_TEXT_PROVISIONING_REQUIRED")
    rows = connection.execute(READ_SQL, parameters).fetchmany(MAX_RECORDS+1)
    return _validated_rows(rows, scope, application_id, qualification_id)


async def load_async(connection, scope, application_id, qualification_id, *, absolute_deadline):
    """Use the original read-only connection and cutoff; no connection or retry."""
    parameters = _parameters(scope, application_id, qualification_id)
    remaining(absolute_deadline)
    remaining(connection.capture_deadline)
    hard = min(absolute_deadline, connection.capture_deadline)
    connection.capture_deadline = hard
    async with asyncio.timeout(remaining(hard)):
        cursor = await connection.execute("SELECT to_regclass('anvil.kyc_application_policy_materializations') AS relation")
        exists = await cursor.fetchone()
        remaining(hard)
        if not exists or not exists["relation"]:
            return PolicyDelivery("blocked","AV_KYC_EXACT_POLICY_TEXT_PROVISIONING_REQUIRED")
        cursor = await connection.execute(READ_SQL, parameters)
        rows = await cursor.fetchmany(MAX_RECORDS+1)
        remaining(hard)
        result = _validated_rows(rows, scope, application_id, qualification_id)
        remaining(hard)
        return result
