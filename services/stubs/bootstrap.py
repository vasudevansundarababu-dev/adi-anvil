"""`pnpm rlgym:demo`: drive the local stubs so the RL Gym receives Golden KYC V8 and V9 (gated) the way Studio and ADI Forge would
send it. Synthetic data only; no model is called. Idempotent: repeating it changes nothing.

  --studio-only   registry versions, evaluators and template activation, but no ADI Forge export
"""

import json
import sys

import httpx

STUDIO = "http://127.0.0.1:8211"
FORGE = "http://127.0.0.1:8212"


def main():
    with httpx.Client(timeout=300, trust_env=False) as client:
        studio = client.post(STUDIO + "/stub/bootstrap").json()
        failed = [e for e in studio["evaluators"] if e.get("state") != "qualified"]
        print(
            f"Studio stub: versions {studio['versions']}; {len(studio['evaluators']) - len(failed)} of "
            f"{len(studio['evaluators'])} evaluator configurations qualified; template activation "
            f"{(studio.get('activation') or {}).get('state')}"
        )
        if failed:
            print(json.dumps(failed, indent=1))
            raise SystemExit(1)
        if "--studio-only" in sys.argv:
            return
        for pid in ("prj_7f3a91c2", "prj_d4e9b1a7"):
            export = client.post(FORGE + f"/stub/projects/{pid}/export", json={}).json()
            receipt = (export.get("response") or {}).get("data") or export.get("response")
            print(
                f"ADI Forge stub: {pid} export exp-0001 → HTTP {export['status']}: {json.dumps(receipt)[:300]}"
            )
            if export["status"] >= 300:
                raise SystemExit(1)


if __name__ == "__main__":
    main()
