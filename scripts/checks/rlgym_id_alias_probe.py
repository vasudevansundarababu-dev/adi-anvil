# Run: cd services/backend && set -a && . ../../.env && set +a && .venv/bin/python ../../scripts/checks/rlgym_id_alias_probe.py
# Result 24 Nov 2026: 140 edge cases, 971 tool calls, 0 with a tag phrase or real ID visible.
"""Read-only check: for every edge-case case on golden-kyc-openenv@8, everything an agent can read about its own case
(and the unscoped document list) shows no edge-case tag phrase and no real ID once aliased."""

import collections
import json
import os
import re
import time

import psycopg
from psycopg.rows import dict_row

from anvil.rlgym import integrations
from anvil.rlgym.runs import aliasing, images, openenv

c = psycopg.connect(os.environ["MIGRATION_DATABASE_URL"].strip('"'), row_factory=dict_row)
env = c.execute(
    "select * from catalog.environment_versions where id='golden-kyc-openenv@8'"
).fetchone()
rec = openenv.recipe(env)
img = c.execute(
    "select local_image_id from runs.instances where environment_version_id='golden-kyc-openenv@8' order by started_at desc limit 1"
).fetchone()["local_image_id"]
cases = integrations.registry_get("/versions/golden-kyc-openenv@8/cases")["cases"]
edge = [x for x in cases if x["edge_cases"]]
tags = sorted({t for x in cases for t in x["edge_cases"]})
phrases = set()
for t in tags:
    phrases |= {t, t.replace("_", "-"), t.replace("_", " ")}
pat = re.compile("|".join(re.escape(p) for p in sorted(phrases, key=len, reverse=True)), re.I)
container, _ = openenv.start_instance("aliasprobe", env, img)
stats = collections.Counter()
bad = []
try:
    s = openenv.OpenEnvSession(container, rec, time.monotonic() + 3000)
    s.request({"op": "reset", "case_id": edge[0]["case_id"], "inject": None})
    start = s.request({"op": "snapshot"})["collections"]
    real_ids = set()
    for t, k in (
        ("applications", "application_id"),
        ("parties", "party_id"),
        ("documents", "document_id"),
    ):
        real_ids |= {r[k] for r in start[t]}
    t0 = time.time()
    for x in edge:
        cid = x["case_id"]
        s.request({"op": "reset", "case_id": cid, "inject": None})
        al = aliasing.Aliaser(cid, start)
        seen = [al.out(f"Application under review: {cid}")]

        def call(tool, args):
            obs = s.request({"op": "call", "tool": tool, "args": al.back(args)})
            v = al.out(obs)
            seen.append(v)
            stats[(tool, obs.get("ok"))] += 1
            return v

        app_alias = al.forward[cid]
        call("application.read", {"application_id": app_alias})
        ps = call("parties.list", {"application_id": app_alias})
        parties = [r["party_id"] for r in (ps.get("output") or {}).get("records") or []]
        for p in parties:
            docs = call("documents.list", {"party_id": p})
            for d in (docs.get("output") or {}).get("records") or []:
                call("document.read", {"id": d["document_id"]})
        if x is edge[0]:
            call("documents.list", {})
        text = json.dumps(seen)
        hits = sorted(set(m.group(0) for m in pat.finditer(text)))
        leaked = [r for r in real_ids if r in text]
        if hits or leaked:
            bad.append({"case": cid, "tags": hits[:5], "real_ids": leaked[:3]})
        # round trip: every alias the agent saw maps back to the real ID
        assert al.back(al.out(cid)) == cid
    print("cases", len(edge), "tags", tags, "seconds", round(time.time() - t0, 1))
    print("calls", dict(stats))
    print("cases with a tag phrase or real ID visible:", len(bad))
    for b in bad[:5]:
        print("  ", b)
    s.close()
finally:
    images.stop_instance(container)
