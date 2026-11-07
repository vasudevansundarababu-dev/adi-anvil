import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from anvil.budget import reconcile, reserve
from anvil.config import ROOT
from anvil.db import one, transaction, uid


def test_concurrent_shared_ceiling_and_unknown_reservation(journey):
    project = journey["project_id"]
    user = json.loads((ROOT / ".local/demo-identities.json").read_text())["researcher"]
    window = uid()
    with transaction(project, user) as c:
        protocol = one(
            c,
            "SELECT current_revision_id FROM anvil.resources WHERE id=%s AND kind='protocol' AND lifecycle='approved'",
            (journey["protocol"]["id"],),
        )
        assert protocol, "the provisioned journey protocol must be approved"
        runs = [uid(), uid()]
        c.execute(
            "INSERT INTO anvil.evaluation_spend_windows(id,project_id,cap_micro_usd,end_at,status,authority_reference) VALUES(%s,%s,100,%s,'active','synthetic ledger concurrency test - no dispatch authority')",
            (window, project, datetime.now(timezone.utc) + timedelta(hours=1)),
        )
        for rid in runs:
            c.execute(
                "INSERT INTO anvil.runs(id,project_id,protocol_revision_id,origin,created_by) VALUES(%s,%s,%s,'illustrative',%s)",
                (rid, project, protocol["current_revision_id"], user),
            )
            c.execute(
                "INSERT INTO anvil.run_budgets(project_id,run_id,window_id,cap_micro_usd) VALUES(%s,%s,%s,100)",
                (project, rid, window),
            )

    def attempt(rid):
        try:
            with transaction(project, user) as c:
                return reserve(c, project, window, rid, 60, "synthetic-concurrency:" + rid)
        except HTTPException as e:
            assert e.status_code == 409
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, runs))
    assert sum(r is not None for r in results) == 1
    winner = next(r for r in results if r)
    with transaction(project, user) as c:
        replay = reserve(c, project, window, winner["run_id"], 60, winner["operation_key"])
        assert replay["id"] == winner["id"]
        reconcile(c, project, winner["id"])
        assert (
            one(
                c,
                "SELECT reserved_micro_usd FROM anvil.evaluation_spend_windows WHERE id=%s",
                (window,),
            )["reserved_micro_usd"]
            == 60
        )
        reconcile(c, project, winner["id"], actual=25)
        reconcile(c, project, winner["id"], actual=25)
        state = one(c, "SELECT * FROM anvil.evaluation_spend_windows WHERE id=%s", (window,))
        assert state["reserved_micro_usd"] == 0 and state["settled_micro_usd"] == 25
