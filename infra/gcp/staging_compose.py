"""Render an isolated Compose preparation contract to stdout; never run Compose.

Explicit operator-provided env files and reviewed runtime initialization are required.
This renderer does not create files, retrieve secrets, pull images, or start services.
The optional fictional benchmark API profile is preparation only. Current human
rights/reviewer/identity gates and exact-source native qualification remain required;
application deployment needs separate approval. It never starts native operators.
"""
import argparse
import json
from pathlib import Path


def render(images, *, fictional_benchmark_demo=False):
    if type(fictional_benchmark_demo) is not bool:
        raise ValueError("Fictional benchmark demo opt-in must be an explicit boolean")
    required = {"backend", "web", "postgres", "neo4j", "keycloak", "caddy"}
    import re
    if set(images) != required or any(not re.fullmatch(r".+@sha256:[0-9a-f]{64}", value) for value in images.values()):
        raise ValueError("Exactly six reviewed immutable image references required")
    root = "/var/lib/anvil-staging"
    def service(image, env, volumes=None, command=None):
        result = {"image": images[image], "restart": "no", "env_file": [f"{root}/config/{env}.env"], "networks": ["staging"], "logging": {"driver": "json-file", "options": {"max-size": "10m", "max-file": "3"}}}
        if volumes:
            result["volumes"] = volumes
        if command:
            result["command"] = command
        return result
    artifact_volumes = [f"{root}/artifacts:/app/.data/artifacts"]
    # Only the API owns gated raw-intake/private metadata operations. General
    # workers and migrations must not inherit its private mount or credentials.
    api_volumes = artifact_volumes + [f"{root}/benchmark-vault:/app/.data/benchmark-vault"]
    paid_off = {"ANVIL_LIVE_PROVIDERS_ENABLED": "false", "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED": "false", "ANVIL_IMPORT_GENERATION_ENABLED": "false", "ANVIL_REAL_EMAIL_ENABLED": "false", "ANVIL_BENCHMARK_ENABLED": "false", "ANVIL_BENCHMARK_EVALUATION_ENABLED": "false", "ANVIL_BENCHMARK_OFFLINE_ENABLED": "false", "ANVIL_TEST_HARBOR": "0", "ANVIL_SUPPORT_VERTEX_PROJECT": "", "ANVIL_SUPPORT_MODEL": "", "ANVIL_BENCHMARK_VAULT_ROOT": "/app/.data/benchmark-vault"}
    services = {
        "postgres": service("postgres", "postgres", [f"{root}/postgres:/var/lib/postgresql/data"]),
        "neo4j": service("neo4j", "neo4j", [f"{root}/neo4j:/data"]),
        "keycloak": service("keycloak", "keycloak", [f"{root}/config/realm.json:/opt/keycloak/data/import/anvil-staging.json:ro"], ["start", "--import-realm"]),
        "migrate": service("backend", "migrate", command=["python", "-m", "anvil.cli", "migrate"]),
        "api": service("backend", "app", api_volumes, ["python", "-m", "uvicorn", "anvil.api:app", "--host", "0.0.0.0", "--port", "8200", "--no-access-log", "--proxy-headers", "--forwarded-allow-ips", "*"]),
        "worker": service("backend", "worker", artifact_volumes, ["python", "-m", "anvil.worker"]),
        "web": service("web", "web"),
        "caddy": service("caddy", "caddy", [f"{root}/config/Caddyfile:/etc/caddy/Caddyfile:ro", f"{root}/caddy:/data"]),
    }
    for name in ("migrate", "api", "worker"):
        services[name]["environment"] = paid_off.copy()
    if fictional_benchmark_demo:
        # API gates only; current policy/SQL authorization still admits every
        # action. Native workers remain explicit separate-host one-shots.
        for flag in ("ANVIL_BENCHMARK_ENABLED", "ANVIL_BENCHMARK_EVALUATION_ENABLED", "ANVIL_BENCHMARK_OFFLINE_ENABLED"):
            services["api"]["environment"][flag] = "true"
    services["worker"]["environment"].pop("ANVIL_BENCHMARK_VAULT_ROOT")
    services["migrate"]["environment"].pop("ANVIL_BENCHMARK_VAULT_ROOT")
    services["api"]["expose"] = ["8200"]
    services["web"]["expose"] = ["3202"]
    services["caddy"]["ports"] = ["80:80"]
    services["api"]["depends_on"] = {"migrate": {"condition": "service_completed_successfully"}}
    services["worker"]["depends_on"] = {"migrate": {"condition": "service_completed_successfully"}}
    # No qualification or evaluator service is invented: explicit native CLI and
    # audited executor/SQL-role wiring remain a separate reviewed implementation.
    return {"name": "adi-anvil-staging", "services": services, "networks": {"staging": {"name": "adi-anvil-staging"}}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, required=True, help="Non-secret map of six reviewed image digests")
    parser.add_argument("--fictional-benchmark-demo", action="store_true", help="Prepare only fictional benchmark API gates; no operators, paid calls or deployment")
    args = parser.parse_args()
    try:
        result = render(json.loads(args.images.read_text()), fictional_benchmark_demo=args.fictional_benchmark_demo)
    except (OSError, ValueError, TypeError):
        print(json.dumps({"ready": False, "error": "Missing or invalid immutable image manifest"}))
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
