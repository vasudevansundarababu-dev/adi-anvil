"""State checks consume reviewed, versioned references and actual delivered rules.

No state law is invented here. Unavailable/unreviewed reference or captured policy
delivery remains unknown. A residence string does not select governing law.
"""

from datetime import date

from anvil.db import digest

KEYS = ("state_applicability", "state_rule_selection", "state_dates", "state_instrument")


def materialized(c, project, trial, generation, governing_state, *, user=None, absolute_deadline=None, document_id=None):
    """Only a current exact-source privileged materialization reaches the actor."""
    from anvil.golden_kyc_source import source_hash

    if absolute_deadline is not None:
        from anvil.golden_kyc_policy_runtime import trial as current_trial

        product, public = current_trial(project,user,trial,generation,governing_state,absolute_deadline=absolute_deadline,
                                        **({"document_id": document_id} if document_id is not None else {}))
        if product:
            return public
    else:
        # Legacy software controls have no paid episode. A real product trial
        # must never use this branch or silently fall back to093.
        mode = c.execute("SELECT banking.product_policy_trial_mode(%s,%s) AS value", (trial,generation)).fetchone()
        if mode and mode["value"] == "reusable_application_workflow":
            raise ValueError("Original product episode policy deadline required")
    if document_id is not None:
        raise ValueError("Policy documents require the exact current product trial binding")
    row = c.execute(
        "SELECT banking.bound_state_policy_materialization(%s,%s) AS value", (trial, generation)
    ).fetchone()["value"]
    if row is None:
        return None
    if (
        str(row["project_id"]) != str(project)
        or row["governing_state"] != governing_state
        or not row["active"]
        or row["runtime_source_sha256"] != source_hash()
        or digest(row["content"]) != row["content_sha256"]
    ):
        raise ValueError("Bound state policy materialization changed, expired or revoked")
    body = row["content"]
    if (
        set(body) != {"schema_version", "governing_state", "bound_state_rules"}
        or body["schema_version"] != "anvil.bound-state-policy.v1"
        or body["governing_state"] != governing_state
        or not isinstance(body["bound_state_rules"], list)
        or not body["bound_state_rules"]
    ):
        raise ValueError("Explicit versioned state policy materialization required")
    for rule in body["bound_state_rules"]:
        required = {
            "id",
            "version",
            "content_sha256",
            "governing_state",
            "effective_from",
            "effective_until",
            "text",
            "source_location",
        }
        if (
            not isinstance(rule, dict)
            or set(rule) != required
            or rule["governing_state"] != governing_state
            or not rule["text"]
            or not rule["source_location"]
            or len(rule["content_sha256"]) != 64
        ):
            raise ValueError("Complete public state rule source and date metadata required")
    return body


def evaluate_state(snapshot, state, events, reference):
    unknown = dict.fromkeys(KEYS)
    if (
        not isinstance(reference, dict)
        or reference.get("review_status") != "approved"
        or reference.get("schema_version") != "anvil.reviewed-state-reference.v1"
    ):
        return unknown, "reviewed_state_reference_required"
    body = reference.get("content")
    if not isinstance(body, dict) or reference.get("content_sha256") != digest(body):
        return unknown, "state_reference_integrity_required"
    if body.get("governing_state") != snapshot.get("governing_state") or body.get(
        "assessment_date"
    ) != snapshot.get("assessment_date"):
        return unknown, "state_reference_scope_mismatch"
    rules = body.get("applicable_rules")
    instruments = body.get("required_instruments")
    if not isinstance(rules, list) or not rules or not isinstance(instruments, list):
        return unknown, "explicit_state_rules_and_instruments_required"
    try:
        assessed = date.fromisoformat(snapshot["assessment_date"])
        for rule in rules:
            if (
                set(rule)
                != {
                    "id",
                    "version",
                    "content_sha256",
                    "governing_state",
                    "effective_from",
                    "effective_until",
                }
                or rule["governing_state"] != snapshot["governing_state"]
            ):
                return unknown, "state_rule_scope_required"
            if rule["effective_from"] is not None:
                date.fromisoformat(rule["effective_from"])
            if rule["effective_until"] is not None:
                date.fromisoformat(rule["effective_until"])
    except (KeyError, TypeError, ValueError):
        return unknown, "explicit_state_rule_effective_intervals_required"
    delivered = []
    for event in events:
        record = event.get("record", {})
        if event.get("action") != "policy.read" or record.get("status") != "completed":
            continue
        payload = record.get("result", {})
        if isinstance(payload, dict):
            delivered.extend(payload.get("bound_state_rules", []))
    from anvil.golden_kyc_policy_observations import delivered_state_rules

    delivered.extend(delivered_state_rules(events, application_id=snapshot.get("id")))
    if not delivered:
        return unknown, "bound_state_policy_delivery_unavailable"
    exact = all(
        any(
            isinstance(observed, dict)
            and all(
                observed.get(k) == rule[k]
                for k in (
                    "id",
                    "version",
                    "content_sha256",
                    "governing_state",
                    "effective_from",
                    "effective_until",
                )
            )
            for observed in delivered
        )
        for rule in rules
    )
    citations = set((state.get("final") or {}).get("evidence_ids", []))
    required_ids = {rule["id"] + "@" + rule["version"] for rule in rules}
    selected = required_ids <= citations
    current = all(
        (rule["effective_from"] is None or date.fromisoformat(rule["effective_from"]) <= assessed)
        and (
            rule["effective_until"] is None
            or assessed < date.fromisoformat(rule["effective_until"])
        )
        for rule in rules
    )
    documents = {doc["id"]: doc for doc in state["application"]["documents"]}
    valid_instruments = all(
        isinstance(item, dict)
        and set(item) == {"document_id", "kind", "party_id", "revision"}
        and item["document_id"] in citations
        and item["document_id"] in state["reads"]
        and item["document_id"] in documents
        and all(
            documents[item["document_id"]].get(k) == item[k]
            for k in ("kind", "party_id", "revision")
        )
        for item in instruments
    )
    return {
        "state_applicability": exact and body["governing_state"] == snapshot["governing_state"],
        "state_rule_selection": exact and selected,
        "state_dates": exact and selected and current,
        "state_instrument": valid_instruments if instruments else None,
    }, None if instruments else "state_instrument_not_applicable_no_anchor_inferred"
