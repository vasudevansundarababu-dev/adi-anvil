"""Synthetic transport diagnosis only: no SQL, provider, account or Task grading."""

import json
import os
import socket
from pathlib import Path


def main():
    assert socket.gethostname() == "anvil-overnight-qa-20261110" and os.getuid() == 10001
    os.environ.clear()
    os.environ.update(
        {
            "PATH": "/usr/bin:/bin",
            "HOME": "/home/anvilqa",
            "ANVIL_ROOT": "/opt/anvil-overnight-qa/source",
            "ANVIL_ENV": "cloud",
            "WEB_ORIGIN": "https://anvil-qa.127.0.0.1.sslip.io:8443",
            "OIDC_ISSUER": "https://auth-anvil-qa.127.0.0.1.sslip.io:8443/realms/anvil-overnight-qa",
            "ANVIL_SESSION_KEY": "synthetic-native-probe-only-not-an-account-session",
            "ANVIL_ENVIRONMENT_NATIVE_ENABLED": "true",
            "ANVIL_ENVIRONMENT_NATIVE_TMP_ROOT": "/var/lib/anvil-qa-native",
            "ANVIL_HARBOR_DOCKER_HOST": "unix:///run/anvil-qa-docker/docker.sock",
        }
    )
    from anvil.environment_harbor import execute
    from anvil.environment_temp import workspace

    home = workspace("anvil-env-native-")
    result = {
        "origin": "synthetic_native_transport_probe",
        "provider_calls": 0,
        "task_scoring": "not_evaluated",
    }
    try:
        receipt = execute(
            home / "attempt",
            {"origin": "synthetic_transport_probe"},
            lambda: ({"tool_results": []}, {"origin": "synthetic_transport_probe"}),
            host=os.environ["ANVIL_HARBOR_DOCKER_HOST"],
            python="/opt/anvil-overnight-qa/harbor/bin/python",
        )
        result.update(status="passed", actor_probe=receipt.get("actor_probe"))
    except Exception as exc:
        # Emit only recognized categories, never raw gateway tokens or private logs.
        result.update(status="failed", exception_type=type(exc).__name__)
        texts = str(exc)
        log = home / "attempt/harbor-private.log"
        if log.is_file():
            texts += log.read_text(errors="replace")
        labels = (
            "Permission denied",
            "No such file",
            "not found",
            "address too long",
            "invalid mount",
            "connection refused",
            "Exact native session unavailable",
            "Native Harbor lifecycle failed",
            "ModuleNotFoundError",
            "AssertionError",
            "RuntimeError",
            "ValidationError",
        )
        result["diagnostic_categories"] = [
            label for label in labels if label.lower() in texts.lower()
        ]
        result["errno"] = getattr(exc, "errno", None)
        filename = getattr(exc, "filename", "") or ""
        result["path_category"] = next(
            (
                name
                for name, prefix in (
                    ("qa_runtime_executable", "/opt/anvil-overnight-qa/"),
                    ("qa_actor_socket", "/run/anvil-qa-docker/"),
                    ("qa_native_workspace", "/var/lib/anvil-qa-native/"),
                    ("installed_docker", "/usr/bin/docker"),
                )
                if str(filename).startswith(prefix)
            ),
            "other_or_absent",
        )
    output = Path("/var/lib/anvil-qa-native/probe-public.json")
    output.write_text(json.dumps(result))
    print(json.dumps(result))


if __name__ == "__main__":
    main()
