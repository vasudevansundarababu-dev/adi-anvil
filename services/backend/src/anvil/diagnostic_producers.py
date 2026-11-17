"""Private diagnostic producers over exact sealed SQL evidence.

No actor compliance flag, label or invented reference becomes an award. Missing
normalizers, reviewed obligations or calibrated judgments remain explicit gaps.
The producer runs for each real captured episode; diagnostics add no points.
"""

from anvil.db import digest
from anvil.golden_targets import design_metadata, requirements
from anvil.skill_step_bindings import mapped, public_mapping


def kyc_observations(target, state, events):
    completed = [event for event in events if event["record"].get("status") == "completed"]
    if target == "K.FILE":
        # This environment delivers canonical JSON documents, not raw PDF/image
        # bytes. Count actual complete document deliveries, never documents.list
        # or a document's existence as ingestion/understanding evidence.
        versions = state.get("application_versions", {}).values()
        documents = {
            digest(document)
            for app in [state["application"], *versions]
            for document in app.get("documents", [])
        }
        records, seen = [], set()
        for event in completed:
            if event["action"] != "document.read":
                continue
            value = event["record"].get("result")
            if (
                not isinstance(value, dict)
                or not isinstance(value.get("id"), str)
                or digest(value) not in documents
            ):
                return [], False
            identity = (value["id"], digest(value))
            if identity not in seen:
                records.append({"document_id": identity[0], "sha256": identity[1]})
                seen.add(identity)
        return records, True
    if target == "K.PERSIST":
        return [
            {
                "action_id": "event:" + str(event["sequence"]),
                "subject_id": state["application"]["id"],
                "arguments_sha256": event["record"]["arguments_sha256"],
                "persisted_state_sha256": digest(state["final"]),
            }
            for event in completed
            if event["action"] == "recommend" and event["record"]["result"].get("submitted") is True
        ], True
    if target == "K.COMPARE":
        documents = {row["id"]: row for row in state["application"]["documents"]}
        records = []
        for event in completed:
            if event["action"] != "document.compare":
                continue
            for comparison in event["record"]["result"].get("comparisons", []):
                values = comparison["values"]
                if len(values) != 2 or any(
                    value["document_id"] not in documents for value in values
                ):
                    return [], False
                left, right = [documents[value["document_id"]] for value in values]
                records.append(
                    {
                        "left_document_id": left["id"],
                        "left_revision": left["revision"],
                        "right_document_id": right["id"],
                        "right_revision": right["revision"],
                        "party_id": left["party_id"],
                        "field": comparison["field"],
                        "old_value": values[0]["value"],
                        "new_value": values[1]["value"],
                    }
                )
        return records, True
    if target == "K.ASYNC":
        requests = {value["operation_id"]: key for key, value in state["idempotency"].items()}
        dispositions = {
            party["party_id"]: party.get("status")
            for party in (state["final"] or {}).get("party_assessments", [])
        }
        records = []
        for event in completed:
            observed = event["record"]["result"]
            if event["action"] != "operation.read" or observed.get("status") != "completed":
                continue
            if observed["id"] not in requests or not dispositions.get(observed["party_id"]):
                return [], False
            records.append(
                {
                    "operation_id": observed["id"],
                    "terminal_status": observed["status"],
                    "input_revision": observed["input_revision"],
                    "request_id": requests[observed["id"]],
                    "disposition": dispositions[observed["party_id"]],
                }
            )
        return records, True
    return [], False


def kyc_persistence_effects(state, events, role):
    """Reconcile the actual closed recommendation with its completed tool call."""
    invocations = []
    for event in events:
        if event["action"] != "recommend" or event["record"].get("status") != "completed":
            continue
        final, result = state.get("final"), event["record"].get("result")
        if (
            not isinstance(final, dict)
            or not isinstance(result, dict)
            or result.get("submitted") is not True
            or result.get("authority") != "recommendation_only"
            or result.get("decision") != final.get("decision")
            or digest(final) != event["record"].get("arguments_sha256")
        ):
            return [], False
        invocations.append(
            {
                "invocation_id": "event:" + str(event["sequence"]),
                "operation": "recommend",
                "subject_id": state["application"]["id"],
                "role": role,
                "arguments": final,
                "arguments_sha256": digest(final),
                "response": result,
                "response_sha256": digest(result),
                "persisted_state": final,
                "persisted_state_sha256": digest(final),
                "effect_verified": True,
            }
        )
    return invocations, True


def kyc_process_events(reference, events):
    """Join reviewed obligation selectors to real completed tool effects.

    No actor-provided obligation IDs, policy verdicts or inferred text meanings
    enter this mapping. The private reference supplies explicit mechanical
    operation/result predicates; semantic completion needs separate assessment.
    """
    if not isinstance(reference, dict) or reference.get("status") != "reviewed":
        return [], True  # Common evaluator retains missing-reference ownership.
    from anvil.golden_kyc_paid_session import TOOLS

    obligations = reference.get("obligations")
    if not isinstance(obligations, list) or not 1 <= len(obligations) <= 1000:
        return [], False
    identities = [item.get("id") for item in obligations if isinstance(item, dict)]
    if (
        len(identities) != len(obligations)
        or any(not isinstance(key, str) or not key for key in identities)
        or len(set(identities)) != len(identities)
    ):
        return [], False
    remaining = {item["id"]: item for item in obligations}
    done = set()
    while remaining:
        ready = [
            key
            for key, item in remaining.items()
            if isinstance(item.get("after"), list)
            and all(isinstance(prior, str) and prior in done for prior in item["after"])
        ]
        if not ready:
            return [], False  # Cyclic/foreign/unmapped prerequisites are not Fail.
        for key in ready:
            item = remaining.pop(key)
            selector = item.get("event_selector")
            if (
                not isinstance(selector, dict)
                or set(selector) != {"operation", "result_match"}
                or selector["operation"] not in TOOLS
                or not isinstance(selector["result_match"], dict)
                or not 1 <= len(selector["result_match"]) <= 20
                or any(not isinstance(key, str) or not key for key in selector["result_match"])
            ):
                return [], False
            done.add(key)
    observed = []
    for item in obligations:
        selector = item["event_selector"]
        matches = [
            event
            for event in events
            if event["action"] == selector["operation"]
            and event["record"].get("status") == "completed"
            and isinstance(event["record"].get("result"), dict)
            and all(
                key in event["record"]["result"]
                and digest(event["record"]["result"][key]) == digest(value)
                for key, value in selector["result_match"].items()
            )
        ]
        if matches:
            event = min(matches, key=lambda value: value["sequence"])
            observed.append(
                {
                    "obligation_id": item["id"],
                    "sequence": event["sequence"],
                    "effect_verified": True,
                    "operation": event["action"],
                    "event_sha256": digest(event),
                }
            )
    return observed, True


def register(
    c,
    project,
    run,
    cell,
    task,
    context,
    evidence,
    actual_by_target,
    references,
    *,
    reference_metadata=None,
    source_resolved=True,
    preparation=None,
):
    """Common source/role-bound pipeline for all39 registered diagnostics."""
    from anvil.diagnostic_bindings import Dispatcher
    from anvil.expert_reviews import register_target

    outputs = []
    dispatcher = Dispatcher(c, project, preparation)
    for descriptor in mapped(requirements(task), preparation or {}):
        if descriptor["official"]:
            continue
        target = descriptor["skill_id"]
        actual = actual_by_target.get(target) or {}
        reference = references.get(target)
        target_context = context | {"role": descriptor["role"]}
        result = dispatcher.run(descriptor, target_context, actual, reference)
        if not actual.get("normalizer_available", True) and result["status"] != "not_applicable":
            result = result | {
                "status": "unscored",
                "owner": actual.get("normalizer_gap_owner", "anvil"),
                "unscored_reason": actual.get(
                    "normalizer_gap", "source_bound_diagnostic_normalizer_required"
                ),
                "measurements": {},
                "measure_coverage": {
                    "required": result["measure_coverage"]["required"],
                    "measured": [],
                    "missing": result["measure_coverage"]["required"],
                    "complete": False,
                },
            }
            result.pop("counts", None)
            result.pop("population_coverage", None)
        if not source_resolved:
            result = result | {
                "status": "unscored",
                "owner": "anvil",
                "unscored_reason": "exact_task_source_unresolved",
                "measurements": {},
                "measure_coverage": {
                    "required": result["measure_coverage"]["required"],
                    "measured": [],
                    "missing": result["measure_coverage"]["required"],
                    "complete": False,
                },
            }
        content = {
            **design_metadata(descriptor["domain"], descriptor["id"]),
            **public_mapping(descriptor),
            "case_id": context["case_id"],
            "model_key": cell["model_key"],
            "repetition": cell["repetition"],
            "role": descriptor["role"],
            "step": descriptor["step"],
            "skill_id": target,
            "skill": descriptor["skill"],
            "criterion_id": None,
            "scale": descriptor["scale"],
            "weight": 0,
            "official": False,
            "applicability": "not_applicable"
            if result["status"] == "not_applicable"
            else "required"
            if reference and reference.get("applicability") == "required"
            else "unknown",
            "automated": {
                "award": None,
                "status": result["status"],
                "measurements": result["measurements"],
                "measure_coverage": result["measure_coverage"],
                "population_coverage": result.get("population_coverage"),
                "reason": result.get("unscored_reason"),
                "owner": result.get("owner"),
                "ran": result["ran"],
                "evaluator": (result.get("comparison_contract") or {}).get(
                    "method", "anvil-diagnostic-measure.v1"
                ),
                "comparison_contract": result.get("comparison_contract"),
                "evaluator_binding": result.get("evaluator_binding"),
                "origin": cell["capture"].get(
                    "origin", "sealed_capture_origin_retained_separately"
                ),
            },
            "expected": descriptor["evidence_contract"],
            "observed": "Exact sealed episode evidence; unavailable measures remain unscored",
            "evidence": evidence,
            "source": {key: task[key] for key in ("task_id", "task_version", "payload_sha256")},
            "evidence_contract": {
                "source_evidence_sha256": actual.get("source_evidence_sha256"),
                "context_sha256": digest(target_context),
                "official_points": 0,
                "definition_register_sha256": descriptor["register_sha256"],
                "reference_sha256": digest(reference) if reference is not None else None,
                "reference_binding": reference_metadata,
                "source_identity_status": "resolved" if source_resolved else "unresolved",
                "normalizer_scope": actual.get("normalizer_scope"),
                "observation_projection_sha256": actual.get("observation_projection_sha256"),
                "normalizer_source_sha256": actual.get("normalizer_source_sha256"),
                "observed_source_refs": actual.get("observed_source_refs", []),
                "evaluator_binding": result.get("evaluator_binding"),
            },
        }
        register_target(c, project, run, str(cell["id"]) + ":" + target, content)
        outputs.append(result)
    return outputs


def kyc(c, project, run, cell, task, evidence, *, source_resolved=True, preparation=None):
    captured = cell["capture"]
    trial, generation = captured["trial_id"], captured["generation"]
    sealed = c.execute(
        "SELECT s.state,s.state_sha256,t.pack_id,t.application_id FROM banking.seals s JOIN banking.trials t ON t.id=s.trial_id AND t.project_id=s.project_id WHERE s.project_id=%s AND s.trial_id=%s AND s.generation=%s",
        (project, trial, generation),
    ).fetchone()
    if not sealed or digest(sealed["state"]) != sealed["state_sha256"]:
        raise ValueError("Exact sealed diagnostic episode required")
    events = c.execute(
        "SELECT action,record,sequence FROM banking.events WHERE project_id=%s AND trial_id=%s AND generation=%s ORDER BY sequence",
        (project, trial, generation),
    ).fetchall()
    snapshot = c.execute(
        "SELECT snapshot_sha256 FROM banking.applications WHERE project_id=%s AND pack_id=%s AND id=%s",
        (project, sealed["pack_id"], sealed["application_id"]),
    ).fetchone()
    reference = c.execute(
        "SELECT expectation FROM banking_private.expectations WHERE project_id=%s AND pack_id=%s AND application_id=%s",
        (project, sealed["pack_id"], sealed["application_id"]),
    ).fetchone()
    context = {
        "task_id": task["task_id"],
        "revision": task["task_version"],
        "payload_sha256": task["payload_sha256"],
        "case_id": sealed["application_id"],
        "snapshot_sha256": snapshot["snapshot_sha256"],
    }
    # This digest comes only from actual sealed SQL bytes. A label cannot fill
    # in or substitute an actor/client-provided capture fingerprint.
    source_digest = digest(
        {
            "state_sha256": sealed["state_sha256"],
            "events": events,
            "snapshot_sha256": snapshot["snapshot_sha256"],
        }
    )
    actuals = {}
    references = (reference["expectation"].get("diagnostic_references") or {}) if reference else {}
    from anvil.diagnostic_projection import SUPPORTED, kyc_role_complete, kyc_sources, normalize

    observed_sources = (
        kyc_sources(sealed["state"], events)
        if any(
            isinstance(value, dict) and value.get("observation_projection")
            for value in references.values()
        )
        else []
    )
    actor_completed = kyc_role_complete(sealed["state"], events)
    for descriptor in mapped(requirements(task), preparation or {}):
        if descriptor["official"]:
            continue
        records, available = kyc_observations(descriptor["skill_id"], sealed["state"], events)
        target_context = context | {"role": descriptor["role"]}
        projection = None
        if not available and descriptor["skill_id"] in SUPPORTED:
            projection = normalize(
                descriptor["skill_id"],
                target_context,
                references.get(descriptor["skill_id"]),
                observed_sources,
                complete_capture=actor_completed and descriptor["role"] == "kyc_analyst",
            )
            if projection["available"]:
                records, available = projection["records"], True
        actuals[descriptor["skill_id"]] = {
            "execution_receipt_sha256": source_digest,
            "source_evidence_sha256": source_digest,
            "complete_capture": available,
            "normalizer_available": available,
            "context_sha256": digest(target_context),
            "observed_records": records,
            "invalid_record_count": projection["invalid_record_count"] if projection else 0,
        }
        if projection:
            actuals[descriptor["skill_id"]].update(
                normalizer_scope=projection["scope"],
                normalizer_gap=projection.get("reason"),
                observation_projection_sha256=projection.get("projection_sha256"),
                normalizer_source_sha256=projection.get("projection_source_sha256"),
                observed_source_refs=projection.get("observed_source_refs", []),
            )
        if descriptor["skill_id"] == "K.FILE":
            actuals["K.FILE"]["normalizer_scope"] = (
                "canonical_json_document_delivery_not_raw_file_or_understanding"
            )
        if descriptor["skill_id"] == "K.PERSIST":
            invocations, available = kyc_persistence_effects(
                sealed["state"], events, descriptor["role"]
            )
            actuals["K.PERSIST"].update(
                complete_capture=available,
                normalizer_available=available,
                observed_invocations=invocations,
                normalizer_scope="reviewed_logical_effect_subsets_not_free_text_semantics",
            )
        if descriptor["skill_id"] == "K.PROCESS":
            ordered, available = kyc_process_events(references.get("K.PROCESS"), events)
            actuals["K.PROCESS"].update(
                complete_capture=available,
                normalizer_available=available,
                obligation_events=ordered,
                normalizer_gap="reviewed_obligation_event_mapping_required",
                normalizer_gap_owner="anvil",
                normalizer_scope="mechanical_completed_tool_effects_not_semantic_correctness",
            )
    return register(
        c,
        project,
        run,
        cell,
        task,
        context,
        evidence,
        actuals,
        references,
        reference_metadata={
            "kind": "immutable_banking_pack_case",
            "pack_id": str(sealed["pack_id"]),
            "case_id": sealed["application_id"],
            "sha256": digest(reference["expectation"]) if reference else None,
            "status": "present" if reference else "missing",
        },
        source_resolved=source_resolved,
        preparation=preparation,
    )
