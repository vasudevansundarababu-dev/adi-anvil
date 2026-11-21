"""Prepare a private draft from exact Gym proposals; never grant review/admission."""
import argparse
import csv
import io
import json
import os
import secrets
from pathlib import Path
from uuid import UUID

from anvil.db import digest
from anvil.kyc_expectation_reviews import Expected, Packet, PrivateCase, subject_for
from anvil.praxis_generic_contract import canonical, load


def write(path, raw):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), "wb") as stream:
        stream.write(raw)


def prepare(bundle, output, project, pack, policies):
    from check_kyc_context_bundle import verify

    verify(bundle)
    apps = load((bundle / "actor-input.json").read_bytes())["applications"]
    proposals = json.loads((bundle / "private/expectations.json").read_bytes())
    proposed = {item["application_id"]: item for item in proposals}
    if len(proposed) != len(proposals) or set(proposed) != {app["id"] for app in apps}:
        raise ValueError("Exact complete private proposal membership required")
    policy_by_cell = {}
    for item in policies["subjects"]:
        if digest(item["subject"]) != item["subject_sha256"]:
            raise ValueError("Exact staged policy subject hash required")
        cell = item["subject"]["policy_set"]
        key = (cell["product"], cell["governing_state"])
        if key in policy_by_cell:
            raise ValueError("Unique product/state policy subjects required")
        policy_by_cell[key] = item["subject_sha256"]
    cases, rows = [], []
    for app in sorted(apps, key=lambda app: app["id"]):
        source = proposed[app["id"]]
        if source["snapshot_sha256"] != digest(app) or source["expectation"].get("independent_expectation_review") != "pending":
            raise ValueError("Only exact unreviewed child proposals may form this draft")
        note = ("UNREVIEWED GYM PROPOSAL. Confirm this disposition against the changed child context. "
                "No state-reference or criterion-reference approval is inferred from the parent. "
                "Missing normative references remain unscored.")
        expected = Expected(intended_decision=source["expectation"]["intended_decision"], notes=note)
        policy = policy_by_cell[(app["product"], app["governing_state"])]
        cases.append(PrivateCase(application_id=app["id"], snapshot_sha256=digest(app),
                                 salt=secrets.token_hex(32), expectation=expected, policy_subject_sha256=policy))
        rows.append({"application_id": app["id"], "product": app["product"], "state": app["governing_state"],
                     "assessment_date": app["assessment_date"], "snapshot_sha256": digest(app),
                     "proposed_disposition": expected.intended_decision, "owner_review": "PENDING",
                     "owner_notes": "", "state_reference": "NOT PROVIDED", "normative_criterion_references": "NOT PROVIDED"})
    packet = Packet(schema_version="anvil.kyc-private-expectation-packet.v1", project_id=project, pack_id=pack, cases=cases)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    write(output / "private-review-packet.canonical.json", canonical(packet.model_dump(mode="json")))
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    write(output / "private-review-worksheet.csv", stream.getvalue().encode())
    subject = subject_for(packet)
    write(output / "review-metadata.json", canonical({"subject": subject.model_dump(mode="json"),
        "subject_sha256": digest(subject.model_dump(mode="json")), "status": "DRAFT_NOT_REVIEWED_NOT_STAGED",
        "missing_state_reference_cases": len(cases), "missing_normative_criterion_reference_cases": len(cases),
        "review_granted": False, "run_authority": "not_granted", "model_calls": 0}))
    return {"case_count": len(cases), "private_packet_sha256": subject.private_packet_sha256,
            "population_sha256": subject.population_sha256, "status": "draft_requires_owner_review",
            "missing_state_reference_cases": len(cases), "review_granted": False, "run_authority": "not_granted"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project", type=UUID, required=True)
    parser.add_argument("--pack", type=UUID, required=True)
    parser.add_argument("--policy-subjects", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.bundle, args.output, args.project, args.pack, load(args.policy_subjects.read_bytes()))
    print(canonical(result).decode())


if __name__ == "__main__":
    main()
