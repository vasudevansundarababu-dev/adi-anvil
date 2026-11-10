"""Worker-side managed credential resolution probe; no provider calls or values."""

import json
import os
import sys
from pathlib import Path


def main():
    assert os.getuid() == 10001
    events = []

    def trace(frame, event, value):
        if event == "exception" and Path(frame.f_code.co_filename).name in {
            "cloud_secrets.py", "workspace_secrets.py"
        }:
            error = value[1]
            response = getattr(error, "response", None)
            events.append({"module": Path(frame.f_code.co_filename).name,
                           "line": frame.f_lineno, "type": type(error).__name__,
                           "http_status": getattr(response, "status_code", None)})
        return trace

    from anvil.db import transaction
    from anvil.workspace_credentials import resolve

    bindings = json.loads(Path(sys.argv[1]).read_text())
    results = []
    sys.settrace(trace)
    for value in bindings["credentials"]:
        try:
            with transaction(bindings["project"], "113c5a26-1060-442b-be9e-955de21c391c") as c:
                key = resolve(c, value["credential_id"], value["version_id"])
                assert len(key.get_secret_value()) >= 8
                del key
            results.append({"provider": value["provider"], "resolved": True})
        except Exception as error:
            results.append({"provider": value["provider"], "resolved": False,
                            "exception_type": type(error).__name__})
    sys.settrace(None)
    receipt = {"credentials": results, "diagnostic_locations": events,
               "provider_calls": 0, "secret_values_logged": False}
    Path("/var/lib/anvil-qa-native/credential-probe-public.json").write_text(json.dumps(receipt))
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
