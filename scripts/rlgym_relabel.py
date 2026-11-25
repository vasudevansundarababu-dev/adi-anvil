"""D-054 relabel of one finished run: a new append-only re-score pass with the latest pass's evaluator versions.

    python scripts/rlgym_relabel.py <workspace_id> <run_id> <approving_person_id> "<reason>" [--apply]

Without --apply it runs inside a transaction that is rolled back and prints the figures it would produce. With
--apply it commits. Earlier passes are never changed. Run it only with the owner's approval for that run.
"""

import json
import sys

from anvil.rlgym.common import system_scope
from anvil.rlgym.runs import service as runs
from anvil.rlgym.scoring import service as scoring


def main(argv):
    apply = "--apply" in argv
    ws, run_id, person, reason = [a for a in argv if a != "--apply"]
    with system_scope(ws) as c:
        result = runs.relabel(c, ws, run_id, person, reason, "rlgym-relabel")
        stats = scoring.run_statistics(c, run_id, result["pass_id"])
        out = {
            "mode": "applied" if apply else "dry run (rolled back)",
            **result,
            "systems": [
                {
                    k: s[k]
                    for k in (
                        "system_id",
                        "system_version",
                        "case_episodes",
                        "scored",
                        "provider_refused",
                        "errored",
                        "timed_out",
                        "mean_score",
                        "pass_rate",
                    )
                }
                for s in stats["systems"]
            ],
        }
        if not apply:
            c.rollback()
        print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main(sys.argv[1:])
