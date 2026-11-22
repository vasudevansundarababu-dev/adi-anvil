"""The controlled mock provider: the only model provider this local build calls.

It is deterministic, makes no network request and is labelled synthetic everywhere. Its answers are predetermined
behaviour profiles; they never count as model performance. Run behaviour (episodes) arrives with work package 2.7;
here it answers connection probes (a no-op echo episode).
"""

import hashlib
import json
import time

PROFILES = {
    "mock/diligent-v1": "Follows the workflow and answers from the application record.",
    "mock/skips-screening-v1": "Follows the workflow but never calls screening.check.",
    "mock/erratic-v1": "Calls random tools and guesses decisions (seeded by case id).",
}


def respond(model_id, payload):
    if model_id not in PROFILES:
        raise ValueError(f"unknown mock profile {model_id}")
    started = time.perf_counter()
    body = json.dumps(payload, sort_keys=True)
    out = {
        "echo": payload,
        "profile": model_id,
        "digest": hashlib.sha256(body.encode()).hexdigest()[:16],
    }
    return out, int((time.perf_counter() - started) * 1000) + 1
