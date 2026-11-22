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
        "ANVIL_COMPOSE_PROJECT": os.environ.get("ANVIL_COMPOSE_PROJECT", "adi-anvil"),
        "RLGYM_V2": os.environ.get("RLGYM_V2", "1"),
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
        # ADI Labs Forge sign-in (shared/BRANDING.md, RL Gym 2.13): infra/keycloak/themes/adi-labs-forge.
        "loginTheme": "adi-labs-forge",
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


RLGYM_SETTINGS = {
    "RLGYM_V2": lambda: "1",
    "RLGYM_STUDIO_URL": lambda: "http://127.0.0.1:8211",
    "RLGYM_FORGE_URL": lambda: "http://127.0.0.1:8212",
    "RLGYM_API_URL": lambda: "http://127.0.0.1:8200",
    "RLGYM_WORKSPACE": lambda: "adi-labs-research",
    "RLGYM_FORGE_CLIENT_KEY": lambda: secrets.token_urlsafe(32),
    "RLGYM_STUDIO_CLIENT_KEY": lambda: secrets.token_urlsafe(32),
    "RLGYM_ANVIL_KEY": lambda: secrets.token_urlsafe(32),
    "RLGYM_REGISTRY_WEBHOOK_SECRET": lambda: secrets.token_urlsafe(32),
}


def ensure_rlgym_settings():
    """Append missing RL Gym v2 settings (local stub client keys) to .env; existing values are never replaced."""
    path = ROOT / ".env"
    if not path.exists():
        return
    present = {line.split("=", 1)[0] for line in path.read_text().splitlines() if "=" in line}
    missing = [k for k in RLGYM_SETTINGS if k not in present]
    if missing:
        with path.open("a") as f:
            f.write("".join(f"{k}={RLGYM_SETTINGS[k]()}\n" for k in missing))
        print(f"Added {len(missing)} RL Gym v2 local settings to .env (values not printed).")


REGISTRIES = {"stub": "http://127.0.0.1:8211", "studio": "http://127.0.0.1:8060"}


def refuse_while_linked(suite):
    """Test suites share the outbox with the running API; while it follows Studio it would deliver test traffic there."""
    followed = (env().get("RLGYM_STUDIO_URL") or REGISTRIES["stub"]).rstrip("/")
    if followed != REGISTRIES["stub"]:
        raise SystemExit(
            f"The running stack follows {followed}; the {suite} suite would send test traffic there. "
            "Run `python3 scripts/local.py rlgym-registry stub`, restart `pnpm dev`, then run the suite."
        )


def rlgym_registry(target):
    """Check the local Studio's routes the RL Gym needs, or switch which registry the RL Gym follows."""
    import json
    import urllib.error
    import urllib.request

    values = env()
    if target == "check":
        base = REGISTRIES["studio"]
        key = values.get("RLGYM_ANVIL_KEY", "")
        # Studio issues `<contract>@<n>` ids; override with RLGYM_LINK_SAMPLE_VERSION if it releases another number.
        sample = values.get("RLGYM_LINK_SAMPLE_VERSION", "golden-kyc-openenv@3")
        probes = [
            ("registry event log", "GET", "/api/v1/registry/events?after_seq=0", {}),
            ("version record", "GET", f"/api/v1/registry/versions/{sample}", {}),
            (
                "cases (actor fields)",
                "GET",
                f"/api/v1/registry/versions/{sample}/cases",
                {},
            ),
            (
                "image recipe",
                "GET",
                f"/api/v1/registry/versions/{sample}/image-context",
                {},
            ),
            (
                "references (scorer only)",
                "GET",
                f"/api/v1/registry/versions/{sample}/references?ids=kyc-individual-001",
                {"X-ADI-Audience": "scorer"},
            ),
            ("environment simulator", "GET", f"/stub/env/{sample}/health", {}),
        ]
        ready = True
        for label, method, path, extra in probes:
            request = urllib.request.Request(
                base + path, method=method, headers={"Authorization": f"Bearer {key}", **extra}
            )
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    status = response.status
                    body = response.read(2000)
            except urllib.error.HTTPError as exc:
                status, body = exc.code, b""
            except OSError as exc:
                status, body = None, str(exc).encode()
            ok = status == 200
            ready &= ok
            print(f"{'ok ' if ok else 'NO '} {label}: {status} {path}")
            if ok and label == "references (scorer only)" and b"reference" not in body:
                print("    references answered without reference answers")
        print(
            json.dumps(
                {
                    "studio": base,
                    "ready_for_switch": ready,
                    "following_now": values.get("RLGYM_STUDIO_URL", REGISTRIES["stub"]),
                }
            )
        )
        if not ready:
            raise SystemExit(1)
        return
    if target not in REGISTRIES:
        raise SystemExit("Use: rlgym-registry check | studio | stub")
    path = ROOT / ".env"
    lines = path.read_text().splitlines()
    url = REGISTRIES[target]
    found = False
    for i, line in enumerate(lines):
        if line.startswith("RLGYM_STUDIO_URL="):
            lines[i], found = f"RLGYM_STUDIO_URL={url}", True
    if not found:
        lines.append(f"RLGYM_STUDIO_URL={url}")
    path.write_text("\n".join(lines) + "\n")
    print(
        f"The RL Gym now follows {target} ({url}). Restart with `pnpm stop` then `pnpm dev`. The mirror keeps a "
        "separate event sequence per registry; Studio's first event is applied from its own seq 1."
    )


PLUGIN_BASE = "python@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e"


def plugin_build(name):
    """Build a verifier plug-in image offline (pinned local base, verified vendored wheel, --network none) and write
    its manifest with the built image id to .local/plugins/<id>-<version>.json for Admin → Evaluators → Install."""
    import hashlib
    import json
    import shutil

    src = ROOT / "services/plugins" / name
    manifest = json.loads((src / "manifest.json").read_text())
    up = manifest["upstream"]
    if "lockfile_sha256" in up:
        return _node_plugin_build(name, src, manifest)
    wheel = LOCAL / "vendor" / name / up["wheel"]
    if not wheel.is_file() or hashlib.sha256(wheel.read_bytes()).hexdigest() != up["sha256"]:
        raise SystemExit(
            f"{wheel} is missing or does not match its pinned SHA-256; nothing is downloaded here"
        )
    build = LOCAL / "plugins" / f"build-{name}"
    shutil.rmtree(build, ignore_errors=True)
    shutil.copytree(
        src, build, ignore=shutil.ignore_patterns("manifest.json", "*.jdm.json", "__pycache__")
    )
    shutil.copy2(wheel, build / up["wheel"])
    tag = f"rlgym-local/verifier-{name}:{manifest['version']}"
    run(
        [
            "docker",
            "build",
            "--quiet",
            "--network",
            "none",
            "--build-arg",
            f"BASE_IMAGE={PLUGIN_BASE}",
            "--build-arg",
            f"ZEN_WHEEL={up['wheel']}",
            "-t",
            tag,
            str(build),
        ]
    )
    image = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", tag],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    manifest["image"] = image
    out = LOCAL / "plugins" / f"{manifest['id']}-{manifest['version']}.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"image": image, "tag": tag, "manifest": str(out.relative_to(ROOT))}))


def _node_plugin_build(name, src, manifest):
    """A Node plug-in: the dependency tree installed once from the committed lockfile (owner-approved download) is
    copied into the build context; the build itself has no network."""
    import hashlib
    import json
    import shutil

    up = manifest["upstream"]
    vendor = LOCAL / "vendor" / name
    lock = (src / "package-lock.json").read_bytes()
    if hashlib.sha256(lock).hexdigest() != up["lockfile_sha256"]:
        raise SystemExit("package-lock.json does not match the manifest's lockfile_sha256")
    if not (vendor / "node_modules").is_dir() or (vendor / "package-lock.json").read_bytes() != lock:
        raise SystemExit(f"{vendor} must hold node_modules installed from this lockfile; nothing is downloaded here")
    build = LOCAL / "plugins" / f"build-{name}"
    shutil.rmtree(build, ignore_errors=True)
    shutil.copytree(src, build, ignore=shutil.ignore_patterns("manifest.json", "__pycache__"))
    shutil.copytree(vendor / "node_modules", build / "node_modules", symlinks=True)
    tag = f"rlgym-local/verifier-{name}:{manifest['version']}"
    run(["docker", "build", "--quiet", "--network", "none", "--build-arg", f"BASE_IMAGE={up['base_image']}", "-t", tag, str(build)])
    image = subprocess.run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", tag], capture_output=True, text=True, check=True
    ).stdout.strip()
    manifest["image"] = image
    out = LOCAL / "plugins" / f"{manifest['id']}-{manifest['version']}.json"
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    shutil.rmtree(build / "node_modules", ignore_errors=True)
    print(json.dumps({"image": image, "tag": tag, "manifest": str(out.relative_to(ROOT))}))


def keycloak_theme():
    """Apply the ADI Labs Forge login theme to an existing local realm: recreate the Keycloak container so the theme is
    mounted (its data volume is kept), then set the realm's loginTheme through the local admin API (loopback only)."""
    import json
    import time
    import urllib.parse
    import urllib.request

    compose("up", "-d", "keycloak")
    values = env()
    base = f"http://127.0.0.1:{values.get('ANVIL_OIDC_PORT', '8180')}"
    form = urllib.parse.urlencode(
        {
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": "anvil-bootstrap",
            "password": values["ANVIL_OIDC_ADMIN_PASSWORD"],
        }
    ).encode()
    token = None
    for _ in range(60):
        try:
            with urllib.request.urlopen(
                f"{base}/realms/master/protocol/openid-connect/token", form, timeout=5
            ) as r:
                token = json.load(r)["access_token"]
                break
        except OSError:
            time.sleep(2)
    if not token:
        raise SystemExit("Keycloak did not answer on loopback")
    req = urllib.request.Request(
        f"{base}/admin/realms/anvil",
        data=json.dumps({"loginTheme": "adi-labs-forge"}).encode(),
        method="PUT",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10):
        pass
    print(json.dumps({"realm": "anvil", "loginTheme": "adi-labs-forge"}))


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
            env().get("ANVIL_COMPOSE_PROJECT", "adi-anvil"),
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
    ensure_rlgym_settings()
    backend("health")
    if (LOCAL / "processes.json").exists():
        raise SystemExit("Process registry exists; use pnpm stop before restarting.")
    for port in (3202, 8200, 8211, 8212):
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
    stubs = [
        (
            [
                str(PY),
                "-m",
                "uvicorn",
                "studio_stub:app",
                "--app-dir",
                "services/stubs",
                "--host",
                "127.0.0.1",
                "--port",
                "8211",
                "--no-access-log",
            ],
            "studio_stub:app",
        ),
        (
            [
                str(PY),
                "-m",
                "uvicorn",
                "forge_stub:app",
                "--app-dir",
                "services/stubs",
                "--host",
                "127.0.0.1",
                "--port",
                "8212",
                "--no-access-log",
            ],
            "forge_stub:app",
        ),
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
    if runtime.get("RLGYM_V2") == "1":
        commands = commands + stubs
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
                    page = response.read()
                    # `/` serves the previous workspace, or redirects to RL Gym Evaluation with RLGYM_V2=1.
                    healthy = (
                        healthy
                        and response.status == 200
                        and (b"ADI Anvil" in page or b"ADI Labs Forge" in page)
                    )
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
    if runtime.get("RLGYM_V2") == "1":
        print(
            "RL Gym v2: http://127.0.0.1:3202/gym | Studio stub: http://127.0.0.1:8211 | ADI Forge stub: http://127.0.0.1:8212"
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
        ensure_rlgym_settings()
        backend("migrate")
        backend("seed")
        backend("rlgym-seed")
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
        run(
            [
                str(PY),
                "-m",
                "ruff",
                "check",
                "services/backend",
                "services/stubs",
                "scripts",
                "tests",
            ],
            env=env(),
        )
        run(
            [
                str(PY),
                "-m",
                "ruff",
                "format",
                "--check",
                "services/backend",
                "services/stubs",
                "scripts",
                "tests",
            ],
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
        if cmd == "integration":
            refuse_while_linked("integration")
            # Workspace tests read a reviewed diagnostic run; rebuild it when missing or stale (needs pnpm dev).
            run([str(PY), "tests/prepare_journey_fixture.py", "--if-missing"], env=env())
        run([str(PY), "-m", "pytest", f"services/backend/tests/{cmd}", "-q"], env=env())
    elif cmd in ["e2e", "smoke"]:
        if cmd == "e2e":
            refuse_while_linked("e2e")
            run([str(PY), "tests/prepare_journey_fixture.py", "--if-missing"], env=env())
        run(["pnpm", "exec", "playwright", "test", *args], env=env())
    elif cmd == "plugin-build":
        plugin_build(args[0] if args else "gorules-zen")
    elif cmd == "keycloak-theme":
        keycloak_theme()
    elif cmd == "rlgym-registry":
        rlgym_registry(args[0] if args else "check")
    elif cmd == "rlgym-demo":
        ensure_rlgym_settings()
        run([str(PY), "services/stubs/bootstrap.py", *args], env=env())
    elif cmd in [
        "migrate",
        "seed",
        "rlgym-seed",
        "live",
        "demo-new",
        "graph-rebuild",
        "backup",
        "restore-test",
    ]:
        backend(cmd, *args)
    else:
        raise SystemExit(f"Unknown command: {cmd}")


if __name__ == "__main__":
    main()
