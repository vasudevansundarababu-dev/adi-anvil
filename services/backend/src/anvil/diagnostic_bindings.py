"""Resolve selected diagnostic evaluators; never turn a Boolean into a ratio.

Old executions with no binding keep their explicitly labelled legacy engine.
New bound executions require the exact saved typed evaluator and current
independent qualification. Custom metric execution is not inferred from a
custom Pass/Fail program; unsupported choices stay unscored.
"""

import hashlib
import os
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException

from anvil.db import digest, one
from anvil.diagnostic_measures import evaluate, measure_contract, unknown, valid_sha
from anvil.native_diagnostic import VERSION, compatible
from anvil.native_diagnostic import source_hash as measurement_source


def source_hash():
    return digest(
        {
            "dispatch": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "measurement_source": measurement_source(),
        }
    )


def binding_record(ref, config, descriptor):
    if not compatible(config, descriptor):
        raise ValueError("Typed diagnostic target and exact measurement contract required")
    return {
        "target": ref["target"],
        "configuration_id": str(ref["id"]),
        "configuration_sha256": ref["sha256"],
        "program_sha256": digest(config["configuration"]["native_diagnostic"]),
        "measure_contract_sha256": digest(descriptor["scale"]["measures"]),
    }


def freeze(c, snapshot, descriptors):
    from anvil.evaluator_configurations import get

    profiles, records, gaps = {}, [], []
    targets = {
        row["target"]: row for row in descriptors["skill_requirements"] if not row["official"]
    }
    for section in ("workflow", "policy", "data", "rubric", "safety"):
        for ref in snapshot.get(section, []):
            if ref["kind"] != "evaluator":
                continue
            if ref["id"] not in profiles:
                profiles[ref["id"]] = get(c, ref["id"])
            config = profiles[ref["id"]]
            if config["configuration"].get("native_diagnostic") is not None and (
                section != "rubric"
                or ref["target"] not in targets
                or not compatible(config, targets[ref["target"]])
            ):
                raise HTTPException(
                    422, {"code": "native_diagnostic_target_not_supported", "target": ref["target"]}
                )
    for descriptor in descriptors["skill_requirements"]:
        if descriptor["official"]:
            continue
        refs = [
            ref
            for ref in snapshot["rubric"]
            if ref["target"] == descriptor["target"]
            and ref["kind"] in {"evaluator", "custom_python"}
        ]
        code = None
        if len(refs) != 1:
            code = "diagnostic_exact_evaluator_binding_required"
        elif refs[0]["kind"] == "custom_python":
            code = "custom_python_typed_diagnostic_runtime_required"
        else:
            ref = refs[0]
            if ref["id"] not in profiles:
                profiles[ref["id"]] = get(c, ref["id"])
            config = profiles[ref["id"]]
            if config["configuration_sha256"] != ref["sha256"] or not compatible(
                config, descriptor
            ):
                code = "typed_diagnostic_evaluator_required"
            else:
                records.append(binding_record(ref, config, descriptor))
        if code:
            gaps.append(
                {
                    "section": "rubric",
                    "target": descriptor["target"],
                    "code": code,
                    "owner": "anvil",
                }
            )
    return {"native_diagnostic_bindings": records, "diagnostic_binding_gaps": gaps}


def valid_record(record):
    if not isinstance(record, dict) or set(record) != {
        "target",
        "configuration_id",
        "configuration_sha256",
        "program_sha256",
        "measure_contract_sha256",
    }:
        return False
    try:
        UUID(record["configuration_id"])
    except (ValueError, TypeError, AttributeError):
        return False
    return bool(
        isinstance(record["target"], str)
        and record["target"]
        and all(
            valid_sha(record[key])
            for key in ("configuration_sha256", "program_sha256", "measure_contract_sha256")
        )
    )


def qualified(record, controls, *, current_source=None):
    if not valid_record(record):
        return False
    expected = record | {
        "source_sha256": current_source or source_hash(),
        "version": VERSION,
        "status": "passed",
        "typed_measurements_verified": True,
        "missing_evidence_unscored_verified": True,
        "zero_official_points_verified": True,
        "role_and_reference_context_verified": True,
    }
    return isinstance(controls, list) and any(
        isinstance(item, dict)
        and all(
            item.get(key) is value if type(value) is bool else item.get(key) == value
            for key, value in expected.items()
        )
        for item in controls
    )


def qualification_gaps(snapshot, evidence):
    records = snapshot.get("native_diagnostic_bindings", [])
    gaps = snapshot.get("diagnostic_binding_gaps", [])
    if (
        not isinstance(records, list)
        or not isinstance(gaps, list)
        or any(not valid_record(row) for row in records)
        or any(not isinstance(row, dict) for row in gaps)
    ):
        return [{"section": "rubric", "code": "diagnostic_binding_invalid", "owner": "anvil"}]
    controls = evidence.get("native_diagnostic", []) if isinstance(evidence, dict) else []
    return gaps + [
        {
            "section": "rubric",
            "target": row["target"],
            "code": "native_diagnostic_qualification_required",
            "owner": "anvil",
        }
        for row in records
        if not qualified(row, controls)
    ]


class Dispatcher:
    """One private grading transaction; cache identities, never grant authority."""

    def __init__(self, c, project, preparation):
        self.c, self.project, self.preparation = c, project, preparation or {}
        self.profiles, self.locks = {}, {}
        self.source = source_hash()
        self.binding, self.qualification, self.reason = None, None, None
        frozen = self.preparation.get("project_binding") or {}
        self.legacy = (
            not frozen
            and not self.preparation.get("rubric")
            and not self.preparation.get("native_diagnostic_bindings")
        )
        if self.legacy:
            return
        release = os.environ.get("ANVIL_DEPLOYMENT_QUALIFICATION_SHA256")
        if not release or not frozen.get("id"):
            self.reason = "diagnostic_exact_frozen_binding_required"
            return
        self.binding = one(
            c,
            "SELECT * FROM anvil.project_binding_versions WHERE project_id=%s AND id=%s",
            (project, frozen["id"]),
        )
        if (
            not self.binding
            or self.binding["snapshot_sha256"] != frozen.get("snapshot_sha256")
            or digest(self.binding["snapshot"]) != frozen["snapshot_sha256"]
            or self.preparation.get("skill_mapping_bindings", [])
            != self.binding["snapshot"].get("skill_mapping_bindings", [])
        ):
            self.reason = "diagnostic_binding_or_role_mapping_changed"
            return
        self.qualification = one(
            c,
            "SELECT q.* FROM anvil.project_binding_qualifications q WHERE q.project_id=%s AND q.binding_id=%s AND q.release_sha256=%s AND q.expires_at>clock_timestamp() AND NOT EXISTS(SELECT 1 FROM anvil.project_binding_qualification_revocations r WHERE r.qualification_id=q.id) ORDER BY q.created_at DESC,q.id DESC LIMIT 1",
            (project, frozen["id"], release),
        )
        if (
            not self.qualification
            or digest(self.qualification["evidence"]) != self.qualification["evidence_sha256"]
        ):
            self.reason = "diagnostic_current_independent_qualification_required"
            return
        available = one(
            c, "SELECT to_regprocedure('anvil.lock_native_ordinal_award(uuid,uuid)') AS function"
        )
        if not available or not available["function"]:
            self.reason = "diagnostic_authority_runtime_required"

    def missing(self, identifier, reason):
        result = unknown(identifier, reason, owner="anvil")
        required = sorted(measure_contract(identifier))
        return result | {
            "measure_coverage": {
                "required": required,
                "measured": [],
                "missing": required,
                "complete": False,
            }
        }

    def run(self, descriptor, context, actual, reference):
        from anvil.evaluator_configurations import get

        identifier, target = descriptor["skill_id"], descriptor["target"]
        if self.legacy:
            return evaluate(identifier, context, actual, reference) | {
                "evaluator_binding": {
                    "mode": "legacy_unbound_diagnostic_engine",
                    "version": "anvil.diagnostic-measure.v1",
                }
            }
        if self.reason:
            return self.missing(identifier, self.reason)
        snapshot = self.binding["snapshot"]
        refs = [
            ref
            for ref in snapshot["rubric"]
            if ref["target"] == target and ref["kind"] in {"evaluator", "custom_python"}
        ]
        if len(refs) != 1:
            return self.missing(identifier, "diagnostic_exact_selected_evaluator_required")
        ref = refs[0]
        if ref["kind"] == "custom_python":
            return self.missing(identifier, "custom_python_typed_diagnostic_runtime_required")
        key = str(ref["id"])
        if key not in self.locks:
            row = one(
                self.c,
                "SELECT anvil.lock_native_ordinal_award(%s,%s) AS allowed",
                (self.binding["id"], key),
            )
            self.locks[key] = bool(row and row["allowed"])
        if not self.locks[key]:
            return self.missing(identifier, "diagnostic_current_author_or_binding_access_required")
        # Read latest validation after the shared evaluator lock, which
        # conflicts with validation/revocation insertion.
        if key not in self.profiles:
            try:
                self.profiles[key] = get(self.c, UUID(key))
            except (ValueError, HTTPException):
                self.profiles[key] = None
        config = self.profiles[key]
        if (
            not config
            or config["status"] != "ready"
            or config["configuration_sha256"] != ref["sha256"]
            or not compatible(config, descriptor)
        ):
            return self.missing(identifier, "diagnostic_current_typed_evaluator_required")
        record = binding_record(ref, config, descriptor)
        if record not in snapshot.get("native_diagnostic_bindings", []) or not qualified(
            record,
            self.qualification["evidence"].get("native_diagnostic"),
            current_source=self.source,
        ):
            return self.missing(
                identifier, "diagnostic_exact_selected_program_qualification_required"
            )
        result = evaluate(identifier, context, actual, reference)
        current = one(
            self.c,
            "SELECT q.id FROM anvil.project_binding_qualifications q WHERE q.project_id=%s AND q.id=%s AND q.expires_at>clock_timestamp() AND NOT EXISTS(SELECT 1 FROM anvil.project_binding_qualification_revocations r WHERE r.qualification_id=q.id)",
            (self.project, self.qualification["id"]),
        )
        if not current:
            return self.missing(identifier, "diagnostic_qualification_expired_or_revoked")
        return result | {
            "evaluator_binding": record
            | {
                "mode": "selected_typed_diagnostic",
                "version": VERSION,
                "source_sha256": self.source,
                "binding_id": str(self.binding["id"]),
                "binding_sha256": self.binding["snapshot_sha256"],
                "qualification_id": str(self.qualification["id"]),
            }
        }
