"""G6 (KYC Judgment v1 C3): scenario events in the evidence.

Studio's runtime appends a fired record (scenario-event.v1 `$defs/fired`) to the episode state when an event fires;
RL Gym reads them from the end snapshot (collection `scenario_events_fired`, Studio cc7af5a; each record holds both
versions and both text hashes) and keeps them in the sealed bundle with the notices the agent was shown (the one-line
`notices` on the next observation), the notices it read (notices.read), and any fired notice it never read.
The rule in force at the recommend call is graded from these records (scoring/judgment.py). None when the episode had
no events, so other bundles keep their shape.
"""

COLLECTION = "scenario_events_fired"  # Studio runtime cc7af5a (generator up to 2.3.0)


def _fired_270(end):
    """Studio generator 2.7.0: what was published sits in `notices` (with published_at_sequence, rule_id, version);
    `scenario_events` holds the case's definitions (supersedes = the version replaced). → (fired, published)."""
    published = [
        n
        for n in end.get("notices") or []
        if isinstance(n, dict) and n.get("published_at_sequence") is not None
    ]
    defs = {d.get("notice_id"): d for d in end.get("scenario_events") or [] if isinstance(d, dict)}
    fired = []
    for n in published:
        d = defs.get(n.get("notice_id")) or {}
        fired.append(
            {
                "event_id": d.get("event_id"),
                "notice_id": n.get("notice_id"),
                "rule_id": n.get("rule_id") or d.get("rule_id"),
                "from_version": d.get("supersedes"),
                "to_version": n.get("version")
                if n.get("version") is not None
                else d.get("version"),
                "published_at_sequence": n["published_at_sequence"],
                "text_sha256": n.get("text_sha256"),
            }
        )
    return fired, published


def scenario_events(snapshots, transcript, studio=None):
    """`studio`: Studio's sealed evidence for the episode (GET /evidence/{generation}: scenario_events_fired,
    notices_published), the source of record; else the end snapshot's older collections; else 2.7.0's notices."""
    end = (snapshots or {}).get("end") or {}
    if isinstance(studio, dict) and isinstance(studio.get(COLLECTION), list):
        fired = [r for r in studio[COLLECTION] if isinstance(r, dict)]
        published = [r for r in studio.get("notices_published") or [] if isinstance(r, dict)]
    elif COLLECTION in end or "notices_published" in end:
        fired = [r for r in end.get(COLLECTION) or [] if isinstance(r, dict)]
        published = [r for r in end.get("notices_published") or [] if isinstance(r, dict)]
    else:
        fired, published = _fired_270(end)
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
    if not fired and not read and not shown and not published:
        return None
    seen = {n["notice_id"] for n in read}
    return {
        "fired": fired,
        "notices_published": published,
        "notices_read": read,
        "notices_shown": shown,
        "unread": [
            f["notice_id"] for f in fired if f.get("notice_id") and f["notice_id"] not in seen
        ],
    }
