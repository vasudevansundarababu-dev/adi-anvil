"""Repository-scoped command contract. Never deletes volumes or calls a model."""

import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / ".local"
PY = ROOT / "services/backend/.venv/bin/python"
USERS = [
    "researcher",
    "advisor",
    "product-owner",
    "data-engineer",
    "reviewer-1",
    "reviewer-2",
    "adjudicator",
    "sales",
    "admin-1",
    "admin-2",
    "outsider",
]


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def env():
    e = os.environ.copy()
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                e[k] = v
    e["UV_CACHE_DIR"] = str(LOCAL / "uv-cache")
    e["UV_PYTHON_INSTALL_DIR"] = str(LOCAL / "python")
    e["ANVIL_ROOT"] = str(ROOT)
    return e


def private_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(data)


def bootstrap():
    LOCAL.mkdir(exist_ok=True, mode=0o700)
    (ROOT / ".secrets").mkdir(exist_ok=True, mode=0o700)
    if (ROOT / ".env").exists():
        if not (LOCAL / "realm.json").exists():
            raise SystemExit(
                "Existing .env without realm: manual recovery required; not overwritten."
            )
        return
    passwords = {name: secrets.token_urlsafe(24) for name in USERS}
    ids = {name: str(uuid.uuid4()) for name in USERS}
    owner, app, worker, oidc, graph, admin = [secrets.token_urlsafe(32) for _ in range(6)]
    values = {
        "ANVIL_ENV": "local",
        "ANVIL_FIXTURE_MODE": "true",
        "ANVIL_LIVE_PROVIDERS_ENABLED": "false",
        "ANVIL_REAL_EMAIL_ENABLED": "false",
        "ANVIL_WEB_PORT": "3202",
        "ANVIL_API_PORT": "8200",
        "ANVIL_POSTGRES_PORT": "5542",
        "ANVIL_OIDC_PORT": "8180",
        "ANVIL_NEO4J_HTTP_PORT": "7475",
        "ANVIL_NEO4J_BOLT_PORT": "7688",
        "ANVIL_DB_OWNER_PASSWORD": owner,
        "ANVIL_DB_APP_PASSWORD": app,
        "ANVIL_DB_WORKER_PASSWORD": worker,
        "ANVIL_OIDC_ADMIN_PASSWORD": admin,
        "ANVIL_NEO4J_PASSWORD": graph,
        "DATABASE_URL": f"postgresql://anvil_app:{app}@127.0.0.1:5542/anvil_local",
        "MIGRATION_DATABASE_URL": f"postgresql://anvil_migration:{owner}@127.0.0.1:5542/anvil_local",
        "WORKER_DATABASE_URL": f"postgresql://anvil_worker:{worker}@127.0.0.1:5542/anvil_local",
        "OIDC_ISSUER": "http://127.0.0.1:8180/realms/anvil",
        "OIDC_CLIENT_ID": "anvil-web",
        "OIDC_CLIENT_SECRET": oidc,
        "WEB_ORIGIN": "http://127.0.0.1:3202",
        "NEO4J_URI": "bolt://127.0.0.1:7688",
        "LANGSMITH_TRACING": "false",
        "ANVIL_SESSION_KEY": secrets.token_urlsafe(32),
    }
    realm = {
        "realm": "anvil",
        "enabled": True,
        "registrationAllowed": False,
        "sslRequired": "none",
        "loginWithEmailAllowed": False,
        "clients": [
            {
                "clientId": "anvil-web",
                "secret": oidc,
                "enabled": True,
                "publicClient": False,
                "standardFlowEnabled": True,
                "directAccessGrantsEnabled": False,
                "redirectUris": ["http://127.0.0.1:3202/api/v1/auth/callback"],
                "webOrigins": ["http://127.0.0.1:3202"],
                "attributes": {"pkce.code.challenge.method": "S256"},
            }
        ],
        "users": [
            {
                "id": ids[n],
                "username": n,
                "enabled": True,
                "firstName": n,
                "lastName": "Synthetic local identity",
                "email": f"{n}@anvil.invalid",
                "emailVerified": True,
                "credentials": [{"type": "password", "value": passwords[n], "temporary": False}],
            }
            for n in USERS
        ],
    }
    private_write(LOCAL / "realm.json", json.dumps(realm))
    private_write(LOCAL / "demo-identities.json", json.dumps(ids))
    private_write(
        LOCAL / "demo-accounts.md",
        "# Local synthetic OIDC identities\n\n"
        "Local test roles only; never paid approvals.\n\n"
        + "\n".join(f"- {n}: `{passwords[n]}`" for n in USERS),
    )
    private_write(ROOT / ".env", "\n".join(f"{k}={v}" for k, v in values.items()) + "\n")
    print("Generated owner-only .env and .local/demo-accounts.md; no secret values printed.")


def compose(*args):
    run(
        [
            "docker",
            "compose",
            "--env-file",
            str(ROOT / ".env"),
            "-f",
            "infra/local/compose.yaml",
            "-p",
            "adi-anvil",
            *args,
        ],
        env=env(),
    )


def backend(*args):
    run([str(PY), "-m", "anvil.cli", *args], env=env())


def preflight():
    failed = False
    for tool in ["node", "pnpm", "python3", "uv", "git", "docker"]:
        if not shutil.which(tool):
            print(f"MISSING {tool}")
            failed = True
        else:
            run([tool, "--version"])
    try:
        run(["docker", "info", "--format", "{{.ServerVersion}}"])
        run(["docker", "compose", "version"])
    except subprocess.CalledProcessError:
        failed = True
    for port in [3202, 8200, 5542, 7475, 7688, 8180]:
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                print(f"Port {port}: available")
            except OSError:
                print(f"Port {port}: occupied (verify Anvil ownership before startup)")
    print(f"Free disk GiB: {shutil.disk_usage(ROOT).free // 2**30}; live calls disabled")
    if failed:
        raise SystemExit(1)


def process_stamp(pid):
    return subprocess.check_output(["ps", "-p", str(pid), "-o", "lstart="], text=True).strip()


def stop():
    path = LOCAL / "processes.json"
    if path.exists():
        for item in json.loads(path.read_text()):
            try:
                actual = subprocess.check_output(
                    ["ps", "-p", str(item["pid"]), "-o", "command="], text=True
                )
                if item["marker"] not in actual or (
                    item.get("started") and process_stamp(item["pid"]) != item["started"]
                ):
                    print(f"Refusing to stop reused PID {item['pid']}")
                    continue
                os.killpg(item["pid"], signal.SIGTERM)
            except (ProcessLookupError, subprocess.CalledProcessError):
                pass
        path.unlink()


def dev():
    backend("health")
    if (LOCAL / "processes.json").exists():
        raise SystemExit("Process registry exists; use pnpm stop before restarting.")
    for port in (3202, 8200):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                raise SystemExit(
                    f"Port {port} is occupied; no processes were started or stopped."
                ) from None
    commands = [
        (
            [
                str(PY),
                "-m",
                "uvicorn",
                "anvil.api:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8200",
                "--no-access-log",
            ],
            "anvil.api:app",
        ),
        ([str(PY), "-m", "anvil.worker"], "anvil.worker"),
        (["pnpm", "--filter", "@anvil/web", "dev"], "pnpm"),
    ]
    runtime = env()
    if runtime.get("ANVIL_HARBOR_WORKER_ENABLED") == "synthetic-checks-only":
        if runtime.get("ANVIL_ENV") != "local" or not runtime.get("ANVIL_HARBOR_DOCKER_HOST"):
            raise SystemExit(
                "Dedicated Harbor startup requires local mode and an explicit Docker host"
            )
        if not (LOCAL / "harbor-venv/bin/harbor").is_file():
            raise SystemExit("Pinned local Harbor executable missing; no worker was started")
        commands.append(([str(PY), "-m", "anvil.harbor_worker"], "anvil.harbor_worker"))
    procs, handles = [], []
    try:
        for i, (cmd, marker) in enumerate(commands):
            with (LOCAL / f"process-{i}.log").open("ab") as log:
                p = subprocess.Popen(
                    cmd,
                    cwd=ROOT,
                    env=env(),
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    start_new_session=True,
                )
            handles.append(p)
            procs.append({"pid": p.pid, "marker": marker, "started": process_stamp(p.pid)})
        (LOCAL / "processes.json").write_text(json.dumps(procs))
        deadline = time.monotonic() + 45
        while True:
            if any(p.poll() is not None for p in handles):
                raise RuntimeError(
                    "Anvil process exited during startup; inspect .local/process-*.log"
                )
            try:
                with urlopen("http://127.0.0.1:8200/api/v1/health", timeout=2) as response:
                    healthy = json.load(response)["data"]["api"] == "ready"
                with urlopen("http://127.0.0.1:3202", timeout=2) as response:
                    healthy = healthy and response.status == 200 and b"ADI Anvil" in response.read()
                if healthy:
                    break
            except (URLError, TimeoutError, ConnectionError, ValueError):
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("Anvil HTTP readiness timed out; inspect .local/process-*.log")
            time.sleep(0.25)
    except Exception:
        for p in handles:
            if p.poll() is None:
                os.killpg(p.pid, signal.SIGTERM)
        (LOCAL / "processes.json").unlink(missing_ok=True)
        raise
    print(
        "Anvil web: http://127.0.0.1:3202 | API: http://127.0.0.1:8200 | logs: .local/process-*.log"
    )


def restart_worker():
    path = LOCAL / "processes.json"
    procs = json.loads(path.read_text())
    worker = next(p for p in procs if p["marker"] == "anvil.worker")
    actual = subprocess.check_output(["ps", "-p", str(worker["pid"]), "-o", "command="], text=True)
    if "anvil.worker" not in actual or (
        worker.get("started") and process_stamp(worker["pid"]) != worker["started"]
    ):
        raise SystemExit("Worker PID ownership mismatch")
    os.killpg(worker["pid"], signal.SIGTERM)
    time.sleep(1)
    with (LOCAL / "process-1.log").open("ab") as log:
        p = subprocess.Popen(
            [str(PY), "-m", "anvil.worker"],
            cwd=ROOT,
            env=env(),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
        )
    worker["pid"] = p.pid
    worker["started"] = process_stamp(p.pid)
    path.write_text(json.dumps(procs))
    print("Restarted only the registered Anvil worker; checkpoints preserved.")


def main():
    cmd = sys.argv[1]
    args = [a for a in sys.argv[2:] if a != "--"]
    if cmd == "preflight":
        preflight()
    elif cmd == "bootstrap":
        bootstrap()
    elif cmd == "setup":
        bootstrap()
        run(["pnpm", "install", "--frozen-lockfile"], env=env())
        run(["uv", "sync", "--frozen", "--project", "services/backend"], env=env())
        compose("up", "-d", "--wait", "--wait-timeout", "180")
        backend("migrate")
        backend("seed")
        backend("health")
    elif cmd == "services-up":
        bootstrap()
        compose("up", "-d", "--wait", "--wait-timeout", "180")
    elif cmd == "services-down":
        compose("down")
    elif cmd == "dev":
        dev()
    elif cmd == "stop":
        stop()
    elif cmd == "worker-restart":
        restart_worker()
    elif cmd == "check":
        run([str(PY), "-m", "ruff", "check", "services/backend", "scripts", "tests"], env=env())
        run(
            [str(PY), "-m", "ruff", "format", "--check", "services/backend", "scripts", "tests"],
            env=env(),
        )
        run(
            [
                "pnpm",
                "exec",
                "prettier",
                "--check",
                "apps/web/src",
                "tests/e2e",
                "tests/load_fixture_batch.mjs",
                "tests/demo_walkthrough.mjs",
                "playwright.config.ts",
            ],
            env=env(),
        )
        run(["pnpm", "--filter", "@anvil/web", "check"], env=env())
        run(["pnpm", "--filter", "@anvil/web", "build"], env=env())
        backend("contracts")
    elif cmd in ["unit", "integration"]:
        run([str(PY), "-m", "pytest", f"services/backend/tests/{cmd}", "-q"], env=env())
    elif cmd in ["e2e", "smoke"]:
        run(["pnpm", "exec", "playwright", "test", *args], env=env())
    elif cmd in ["migrate", "seed", "live", "demo-new", "graph-rebuild", "backup", "restore-test"]:
        backend(cmd, *args)
    else:
        raise SystemExit(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
