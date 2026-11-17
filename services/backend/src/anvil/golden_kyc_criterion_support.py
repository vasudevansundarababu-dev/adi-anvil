"""Mechanical subject/check-scoped follow-up and citation evidence.

A generic hold reason is not evidence that every missing requirement was handled.
These checks do not adjudicate policy meaning or replace reviewed case references.
"""

from anvil.golden_kyc_data import VERSION


def support(state, final, people, latest, verified, unresolved):
    read = set(state["reads"])
    citations = set(final.get("evidence_ids", []))
    hold = final.get("decision") in {"request_information", "specialist_review"}
    required = [party for party in people if party["role"] != "beneficiary"]
    items = {
        "identity": "identity_evidence",
        "address": "address_evidence",
        "authority": "authority",
        "agreement": "agreement",
    }

    def pending(party, kind):
        item = items.get(kind)
        output = []
        for request in state["requests"].values():
            if (
                not item
                or request["party_id"] != party
                or item not in request["items"]
                or not request.get("reason")
            ):
                continue
            response = request.get("response")
            if response is None or not any(
                doc.get("party_id") == party and doc.get("kind") == item
                for doc in response.get("documents", [])
            ):
                output.append(request["id"])
        return output

    def scoped_action(operation):
        if operation is None or operation["result"]["input_revision"] != state["revision"]:
            return []
        identifier = operation["id"]
        refs = [
            key
            for key, referral in state["specialists"].items()
            if identifier in referral.get("evidence_ids", []) and referral.get("question")
        ]
        refs += [
            key
            for key, finding in state["findings"].items()
            if finding.get("status") == "open"
            and identifier in finding.get("evidence_ids", [])
            and finding.get("issue")
        ]
        return refs

    def check_refs(party, kind):
        operation = latest.get((party, kind))
        if (party, kind) in verified and operation is not None:
            return [operation["id"]]
        if not hold:
            return []
        if (
            operation is not None
            and operation["id"] in read
            and operation["result"]["input_revision"] == state["revision"]
        ):
            action = scoped_action(operation)
            if action:
                return [operation["id"], *action]
        requests = pending(party, kind)
        if (
            requests
            and operation is not None
            and operation["id"] in read
            and operation["result"]["input_revision"] == state["revision"]
        ):
            return [operation["id"], *requests]
        return requests

    identity = [check_refs(party["id"], "identity") for party in required]
    screening = [check_refs(party["id"], "screening") for party in required]
    agreements = []
    for party in required:
        documents = [
            doc["id"]
            for doc in state["application"]["documents"]
            if doc["party_id"] == party["id"] and doc["kind"] == "agreement" and doc["id"] in read
        ]
        agreements.append(documents[:1] or (pending(party["id"], "agreement") if hold else []))
    authority = [
        check_refs(party["id"], "authority") for party in required if party["role"] == "adult_owner"
    ]
    exception_refs = [
        check_refs(operation["result"]["party_id"], operation["kind"]) for operation in unresolved
    ]
    followup = {
        "identification_verification": all(identity),
        "screening": all(screening),
        "account_agreements": all(agreements),
        "account_authority": all(authority),
        "account_exceptions": all(exception_refs) and all(identity) and all(screening),
        "account_resolution": all(identity)
        and all(screening)
        and all(agreements)
        and all(exception_refs),
    }

    def union(groups):
        return {identifier for group in groups for identifier in group}

    profile = {state["application"]["id"]}
    policy = {VERSION}
    substantive = (
        profile
        | {doc["id"] for doc in state["application"]["documents"]}
        | set(state["operations"])
    )
    source_refs = {
        "identification_parties": profile,
        "profile": profile,
        "identification_verification": union(identity),
        "screening": union(screening),
        "decision": profile | policy | union(identity + screening),
        "next_action": union(identity + screening + agreements + exception_refs),
        "evidence": profile | policy,
        "revision_integrity": profile,
        "account_structure": profile | policy,
        "account_roles": profile,
        "account_eligibility": profile | policy,
        "account_agreements": union(agreements),
        "account_authority": union(authority),
        "account_party_separation": union(identity),
        "account_exceptions": union(exception_refs) if unresolved else union(identity + screening),
        "account_resolution": union(identity + screening + agreements + exception_refs),
    }
    cited = {
        criterion: bool(needed) and needed <= citations and needed <= read
        for criterion, needed in source_refs.items()
    }
    evidence = bool(citations & substantive) and citations <= read
    return followup, cited, evidence
