"""E-007 §1: independent KYC assertions. A second path that reads the sealed trace and state and decides, on its own,
whether the episode did what the case needs. It must never import the grader's logic (anvil.rlgym.scoring); a test
enforces that. Comparing its answer with the grader's verdict catches a grader that is wrong but reproducible (the
D-041 wrong-party request scored 25/25 under next_action v1).

Each assertion returns {"id", "criterion", "outcome": PASS|FAIL|NOT_APPLICABLE, "expected", "observed"}.
"""

ADDRESS_KINDS = ("proof_of_address", "utility_bill", "bank_statement", "lease", "council_tax_bill")
ID_DOCS = ("government_id", "passport", "drivers_licence", "drivers_license", "driver_license")


def _events(bundle):
    return [e for e in bundle.get("tool_events") or [] if isinstance(e, dict)]


def _ok(e):
    return e.get("ok", True) and not e.get("blocked")


def _end(bundle):
    return ((bundle.get("snapshots") or {}).get("end")) or {}


def _start(bundle):
    return ((bundle.get("snapshots") or {}).get("start")) or {}


def _parties(bundle):
    case = bundle.get("case_id")
    return [
        p
        for p in _start(bundle).get("parties") or []
        if isinstance(p, dict) and p.get("application_id") == case
    ]


def _documents(bundle, party_ids):
    return [
        d
        for d in _start(bundle).get("documents") or []
        if isinstance(d, dict) and d.get("party_id") in party_ids
    ]


def _recommendation(bundle):
    rows = [r for r in _end(bundle).get("recommendations") or [] if isinstance(r, dict)]
    if rows:
        return rows[-1].get("recommendation")
    for e in reversed(_events(bundle)):
        if e.get("tool") == "recommend" and _ok(e):
            return (e.get("args") or {}).get("decision")
    return None


def _first(bundle, tool, party=None):
    for i, e in enumerate(_events(bundle)):
        if (
            e.get("tool") == tool
            and _ok(e)
            and (party is None or (e.get("args") or {}).get("party_id") == party)
        ):
            return i
    return None


def _result(aid, criterion, ok, expected, observed, applicable=True):
    return {
        "id": aid,
        "criterion": criterion,
        "outcome": "NOT_APPLICABLE" if not applicable else ("PASS" if ok else "FAIL"),
        "expected": expected,
        "observed": observed,
    }


def recommendation_matches(bundle, ref):
    want = ref.get("recommendation")
    got = _recommendation(bundle)
    return _result(
        "KYC.RECOMMENDATION", "decision", got == want, want, got, applicable=want is not None
    )


def every_party_before_recommend(bundle, tool, aid, criterion):
    rec = _first(bundle, "recommend")
    parties = [p.get("party_id") for p in _parties(bundle)]
    missing = [
        p
        for p in parties
        if (_first(bundle, tool, p) is None) or (rec is not None and _first(bundle, tool, p) > rec)
    ]
    return _result(
        aid,
        criterion,
        not missing and rec is not None,
        f"{tool} for each party before recommend",
        {"parties_not_checked_first": missing, "recommended": rec is not None},
        applicable=bool(parties),
    )


def party_lacking(request_type, bundle):
    """Independent of the grader: which party's start-state record lacks what `request_type` asks for."""
    parties = _parties(bundle)
    ids = {p.get("party_id") for p in parties}
    docs = _documents(bundle, ids)
    submitted = str(
        next(
            (
                a.get("submitted_at")
                for a in _start(bundle).get("applications") or []
                if isinstance(a, dict) and a.get("application_id") == bundle.get("case_id")
            ),
            "",
        )
        or ""
    )[:10]

    def content(d):
        return d.get("content") if isinstance(d.get("content"), dict) else {}

    if request_type == "tin":
        out = {
            d.get("party_id")
            for d in docs
            if "tin" in content(d) and content(d).get("tin") in (None, "", "missing")
        }
        if not out:
            out = {
                p.get("party_id")
                for p in parties
                if p.get("role") == "minor"
                and not any(
                    content(d).get("tin") not in (None, "", "missing")
                    for d in docs
                    if d.get("party_id") == p.get("party_id")
                )
            }
        return out
    if request_type == "id_document":
        out = {
            d.get("party_id")
            for d in docs
            if d.get("kind") in ID_DOCS
            and submitted
            and str(content(d).get("expires_on") or "9999")[:10] < submitted
        }
        return out or {
            pid
            for pid in ids
            if not any(d.get("kind") in ID_DOCS for d in docs if d.get("party_id") == pid)
        }
    if request_type == "proof_of_address":
        return {
            pid
            for pid in ids
            if (mine := [d for d in docs if d.get("party_id") == pid])
            and not any(d.get("kind") in ADDRESS_KINDS for d in mine)
        }
    return None


def request_party(bundle, ref):
    want = ref.get("request_type")
    asked = [r for r in _end(bundle).get("information_requests") or [] if isinstance(r, dict)]
    if want in (None, "", "none"):
        return _result(
            "KYC.REQUEST_PARTY",
            "next_action",
            not asked,
            "no information request",
            [r.get("type") for r in asked],
        )
    should = party_lacking(want, bundle)
    if should is None:
        same = [r for r in asked if r.get("type") == want]
        return _result(
            "KYC.REQUEST_PARTY",
            "next_action",
            bool(same),
            f"a {want} request",
            [r.get("type") for r in asked],
        )
    got = [r.get("party_id") for r in asked if r.get("type") == want]
    return _result(
        "KYC.REQUEST_PARTY",
        "next_action",
        any(p in should for p in got),
        {"type": want, "party_lacking": sorted(x for x in should if x)},
        {"requested_for": got},
        applicable=bool(should),
    )


def referral(bundle, ref):
    want = ref.get("referral")
    got = [r.get("specialty") for r in _end(bundle).get("referrals") or [] if isinstance(r, dict)]
    if want in (None, "", "none"):
        return _result("KYC.REFERRAL", "screening", not got, "no referral", got)
    return _result("KYC.REFERRAL", "screening", want in got, want, got)


def run_all(bundle, ref):
    """Every KYC assertion for one case episode (sealed bundle + the case's reference answers)."""
    return [
        recommendation_matches(bundle, ref),
        every_party_before_recommend(
            bundle, "screening.check", "KYC.SCREEN_BEFORE_RECOMMEND", "screening"
        ),
        every_party_before_recommend(
            bundle, "identity.check", "KYC.ID_BEFORE_RECOMMEND", "identification_verification"
        ),
        request_party(bundle, ref),
        referral(bundle, ref),
    ]
