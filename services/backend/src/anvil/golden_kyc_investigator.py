"""Transparent evidence-driven software candidate for Anvil qualification only.

Inputs are the assigned tool surface and scheduler wait service. No scenario,
expected decision, private grading data, SQL or provider client is available.
This is never labelled as a model or used to establish model performance.
"""

from anvil.golden_kyc_data import VERSION, age


def investigate(tool, wait):
    reads = []
    app = tool("application.read", {})
    reads.append(app["id"])
    policy = tool("policy.read", {})
    reads.append(VERSION)
    search = tool(
        "search",
        {
            "source": "intranet",
            "query": "identity verification and account authority policy",
            "purpose": "Find approved verification procedure",
        },
    )
    for resource in search.get("results", [])[:1]:
        tool("search.read", {"resource_id": resource["resource_id"]})
    documents = {}
    operations = []
    outstanding = []
    referrals = []

    def load_documents():
        for record in tool("documents.list", {}):
            if record["id"] not in documents:
                documents[record["id"]] = tool("document.read", {"id": record["id"]})
                reads.append(record["id"])

    def verify():
        results = []
        for party in app["parties"]:
            if party["role"] == "beneficiary":
                continue
            kinds = [
                ("identity", "identity_evidence"),
                ("address", "address_evidence"),
                ("screening", None),
            ]
            if party["role"] in ("adult_owner", "custodian"):
                kinds.append(("authority", "authority"))
            for kind, document_kind in kinds:
                ids = (
                    [
                        d["id"]
                        for d in documents.values()
                        if d["party_id"] == party["id"] and d["kind"] == document_kind
                    ]
                    if document_kind
                    else []
                )
                key = f"{party['id']}-{kind}-revision-{app['revision']}"
                accepted = tool(
                    kind + ".check",
                    {
                        "party_id": party["id"],
                        "document_ids": ids,
                        "input_revision": app["revision"],
                        "idempotency_key": key,
                    },
                )
                if not accepted.get("accepted"):
                    if accepted.get("nonacceptance_established"):
                        wait("service_retry", 1)
                        accepted = tool(
                            kind + ".check",
                            {
                                "party_id": party["id"],
                                "document_ids": ids,
                                "input_revision": app["revision"],
                                "idempotency_key": key,
                            },
                        )
                    else:
                        outstanding.append(
                            {
                                "responsible_role": "service_operator",
                                "party_id": party["id"],
                                "required_item": "reconcile uncertain verification acceptance",
                            }
                        )
                        continue
                operation_id = accepted.get("operation_id")
                if accepted.get("client_timeout"):
                    lookup = tool("operation.lookup", {"idempotency_key": key})
                    operation_id = lookup.get("operation_id")
                if not operation_id:
                    continue
                result = None
                for _ in range(5):
                    wait("service_poll", 1)
                    result = tool("operation.read", {"id": operation_id})
                    if result.get("status") == "completed":
                        break
                if result and result.get("status") == "completed":
                    reads.append(operation_id)
                    results.append(result | {"kind": kind, "id": operation_id})
                    operations.append(result | {"kind": kind, "id": operation_id})
        return results

    load_documents()
    results = verify()
    requests = []
    for party in app["parties"]:
        if party["role"] == "beneficiary":
            continue
        needed = [
            kind
            for kind in ("identity_evidence", "address_evidence", "agreement")
            if not any(
                d["party_id"] == party["id"] and d["kind"] == kind for d in documents.values()
            )
        ]
        if needed:
            request = tool(
                "information.request",
                {
                    "party_id": party["id"],
                    "items": needed,
                    "reason": "The required assigned-party supporting evidence is missing; please supply these specific items through the secure portal.",
                    "round_key": "round-one",
                },
            )
            requests.append((party, needed, request))
    if requests:
        wait("customer_response", 5)
        for party, needed, request in requests:
            response = tool("information.read", {"id": request["id"]})
            if response.get("response"):
                reads.append(request["id"])
            missing = [
                kind
                for kind in needed
                if not response.get("response")
                or not any(d["kind"] == kind for d in response["response"]["documents"])
            ]
            for kind in missing:
                outstanding.append(
                    {
                        "responsible_role": "applicant",
                        "party_id": party["id"],
                        "information_request_id": request["id"],
                        "required_item": kind,
                    }
                )
        app = tool("application.read", {})
        load_documents()
        if not outstanding:
            results = verify()
    conflicts = [d for d in documents.values() if d["kind"] == "authority_conflict"]
    if conflicts:
        referral = tool(
            "specialist.refer",
            {
                "question": "Determine the controlling authority from the supplied competing instructions; agent authority is insufficient to resolve the conflict.",
                "evidence_ids": [d["id"] for d in conflicts],
            },
        )
        referrals.append(referral["id"])
    product = app["product"]
    ineligible = app["requested_product"] != product
    if product in ("individual", "adult_joint"):
        ineligible = ineligible or any(
            age(p["birth_date"], app["assessment_date"]) < 18 for p in app["parties"]
        )
    if product == "teen_joint":
        ineligible = ineligible or any(
            not (13 <= age(p["birth_date"], app["assessment_date"]) <= 17)
            if p["role"] == "teen_owner"
            else age(p["birth_date"], app["assessment_date"]) < 18
            for p in app["parties"]
        )
    unresolved = [
        r
        for r in results
        if r.get("verification_status") != "corroborated" or r["input_revision"] != app["revision"]
    ]
    legal_pending = (
        policy["state_modules"][app["governing_state"]]["legal_qualification"] != "approved"
        or not app["charter_applicability"]["reviewed"]
    )
    decision = (
        "not_eligible_for_requested_product"
        if ineligible
        else "specialist_review"
        if conflicts
        else "request_information"
        if outstanding or unresolved
        else "specialist_review"
        if legal_pending
        else "ready_for_approval"
    )
    exceptions = (
        [
            {
                "code": "ENVIRONMENT_POLICY_REVIEW_PENDING",
                "responsible_role": "benchmark_operator",
                "customer_fault": False,
            }
        ]
        if legal_pending
        else []
    )
    if unresolved and not outstanding:
        outstanding.append(
            {
                "responsible_role": "service_operator",
                "required_item": "Resolve inconclusive or stale verification evidence; do not treat it as failed identity",
            }
        )
    for exception in exceptions:
        outstanding.append(
            {
                "responsible_role": exception["responsible_role"],
                "required_item": "Reviewed state and charter applicability module",
            }
        )
    parties = []
    for party in app["parties"]:
        evidence = [
            r["id"]
            for r in results
            if r.get("party_id") == party["id"]
            and r.get("verification_status") == "corroborated"
            and r["input_revision"] == app["revision"]
        ]
        parties.append(
            {
                "party_id": party["id"],
                "role": party["role"],
                "status": "assessed",
                "verification_evidence_ids": evidence,
            }
        )
    # Keep the final citation set bounded while retaining party-specific results.
    final_refs = [app["id"], VERSION] + [r["id"] for r in results] + [d["id"] for d in conflicts]
    output = {
        "decision": decision,
        "assessed_revision": app["revision"],
        "account_type": product,
        "policy_bundle": VERSION,
        "evidence_ids": list(dict.fromkeys(final_refs))[:30],
        "party_assessments": parties,
        "reason": "Evidence-backed software investigation. Outstanding conditions are retained; bank-product ineligibility is limited to the requested product. Environment policy review gaps are not customer faults.",
        "outstanding_actions": outstanding,
        "execution_exceptions": exceptions,
        "specialist_referral_ids": referrals,
    }
    return tool("recommend", output)
