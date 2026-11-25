"""G6 (KYC Judgment v1 C3): scenario events in the evidence.

Studio's runtime appends a fired record (scenario-event.v1 `$defs/fired`) to the episode state when an event fires;
RL Gym reads them from the end snapshot (collection `scenario_events_fired`, Studio cc7af5a; each record holds both
versions and both text hashes) and keeps them in the sealed bundle with the notices the agent was shown (the one-line
`notices` on the next observation), the notices it read (notices.read), and any fired notice it never read.
The rule in force at the recommend call is graded from these records (scoring/judgment.py). None when the episode had
no events, so other bundles keep their shape.
"""

COLLECTION = "scenario_events_fired"  # Studio runtime cc7af5a


def scenario_events(snapshots, transcript):
    fired = [
        r for r in ((snapshots or {}).get("end") or {}).get(COLLECTION) or [] if isinstance(r, dict)
    ]
    read, shown = [], []
    for t in transcript or []:
        obs = t.get("observation") or {}
        for n in obs.get("notices") or []:
            nid = n.get("notice_id") if isinstance(n, dict) else None
            shown.append(
                {
                    "notice_id": nid,
                    "shown_at_sequence": obs.get("sequence") or t.get("step"),
                    "text": n if isinstance(n, str) else n.get("summary"),
                }
            )
        if t.get("tool") != "notices.read" or not obs.get("ok"):
            continue
        for n in (obs.get("output") or {}).get("records") or []:
            if isinstance(n, dict) and n.get("notice_id"):
                read.append(
                    {
                        "notice_id": n["notice_id"],
                        "read_at_sequence": obs.get("sequence") or t.get("step"),
                        "source": n.get("source"),
                    }
                )
    if not fired and not read and not shown:
        return None
    seen = {n["notice_id"] for n in read}
    return {
        "fired": fired,
        "notices_read": read,
        "notices_shown": shown,
        "unread": [
            f["notice_id"] for f in fired if f.get("notice_id") and f["notice_id"] not in seen
        ],
    }
