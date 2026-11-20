"""QA operator publication from actual probe and independent review only.

No DB connection, probe replay, migration, project approval or model dispatch.
The installed-image verification runs with network=none and a read-only preview.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

BASE = Path("/var/lib/anvil-qa-v1")
SCOPE = "capture_api_database_target_only"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def exclusive(path, raw, mode=0o600):
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode), "wb") as stream:
        os.fchmod(stream.fileno(), mode)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def main(args):
    if os.geteuid() != 0 or os.uname().nodename != "anvil-qa-v1":
        raise ValueError("Existing QA root operator required")
    os.umask(0o077)
    raw_manifest, raw_review = args.manifest.read_bytes(), args.review.read_bytes()
    if sha(raw_manifest) != args.manifest_sha256 or sha(raw_review) != args.review_sha256:
        raise ValueError("Exact release and independent review bytes required")
    release, review = json.loads(raw_manifest), json.loads(raw_review)
    expiry = datetime.fromisoformat(review["expires_at"].replace("Z", "+00:00"))
    if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
        raise ValueError("Independent capture review is expired")
    root = args.evidence_root
    if (not re.fullmatch(str(BASE) + r"/runtime-functional/capture-probe-[a-f0-9]{7}-v[1-9][0-9]*", str(root))
            or root.resolve() != root or root.stat().st_uid != 0 or root.stat().st_mode & 0o077):
        raise ValueError("Original private root-owned capture evidence required")
    raw = (root / "evidence.json").read_bytes()
    evidence = json.loads(raw)
    image = release["images"]["backend"]
    identity = evidence["runtime_identity"]
    if (review.get("schema_version") != "anvil.independent-capture-database-evidence-review.v1"
            or review.get("origin") != "independent_agent_read_only_review" or review.get("status") != "passed"
            or review.get("findings") != [] or review.get("scope") != SCOPE
            or review.get("spending_authority") is not False or review.get("human_legal_rights_approval") is not False
            or review.get("revision") != release["revision"]
            or review.get("probe_evidence_sha256") != sha(raw)
            or review.get("checks") != evidence["checks"]
            or review.get("runtime_identity") != identity
            or review.get("role_profile_sha256") != evidence["role_profile_sha256"]
            or review.get("observed_target_sha256") != evidence["observed_target_sha256"]
            or review.get("target_sha256") != evidence["target_sha256"]
            or image.rsplit("sha256:", 1)[-1] != identity["image_sha256"]):
        raise ValueError("Actual exact independently reviewed capture evidence required")
    body = {"schema_version": "anvil.capture-database-runtime-qualification.v1", "origin": "independent_qa",
            "scope": SCOPE, "qualified": True, "revoked": False, "spending_authority": False,
            "issued_at": review["issued_at"], "expires_at": review["expires_at"],
            "target_sha256": evidence["target_sha256"], "runtime_identity": identity,
            "role_profile_sha256": evidence["role_profile_sha256"],
            "observed_target_sha256": evidence["observed_target_sha256"],
            "probe_evidence_sha256": sha(raw), "review_receipt_sha256": sha(raw_review), "checks": evidence["checks"]}
    # All receipt values are ASCII strings, booleans or bounded integers; the
    # installed verifier below confirms this exact digest against RFC8785.
    planned = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    preview = root / "receipt-preview"
    destination = BASE / "runtime-functional/capture-database-qualification"
    if args.mode == "verify":
        preview.mkdir(mode=0o755)
        preview.chmod(0o755)
        exclusive(preview / "current.json", planned, 0o644)
        code = (
            "import json;from anvil.marketing_capture_database_qualification import installed;"
            "from anvil.marketing_capture_database_target import readiness;"
            "from anvil.golden_kyc_source import source_hash;"
            "q=installed(" + repr(body["target_sha256"]) + ");r=readiness();"
            "assert q and q['receipt_sha256']==" + repr(sha(planned)) + ";"
            "assert source_hash()==" + repr(release["source_sha256"]) + ";"
            "assert r['ready'] is True and r['connection_probe_performed'] is False;"
            "print(json.dumps({'qualification':q,'readiness':r,'scope':'verified_not_published'}))"
        )
        name = "forge-capture-receipt-verify-" + release["revision"][:7]
        command = ["docker", "create", "--pull=never", "--name", name, "--read-only", "--user", "10001:10001",
            "--network", "none", "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--memory", "512m",
            "--pids-limit", "128", "--cpus", "1", "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=32m",
            "--env-file", str(root / "capture.private.env"),
            "--mount", f"type=bind,src={preview},dst=/app/.data/runtime-qualification/capture-database,readonly",
            "--mount", f"type=bind,src={BASE}/runtime-functional/capture-database-trust,dst=/app/.data/capture-database-trust,readonly",
            "-e", "ANVIL_ENV=local", "-e", "WEB_ORIGIN=http://127.0.0.1:3202",
            "-e", "ANVIL_CAPTURE_DATABASE_QUALIFICATION_FILE=/app/.data/runtime-qualification/capture-database/current.json",
            "-e", "ANVIL_CAPTURE_DATABASE_TARGET_SHA256=" + body["target_sha256"],
            "-e", "ANVIL_CAPTURE_DATABASE_IMAGE_DIGEST=" + identity["image_sha256"],
            "-e", "ANVIL_LIVE_PROVIDERS_ENABLED=false", "-e", "ANVIL_HARBOR_LIVE_PROVIDERS_ENABLED=false",
            "-e", "ANVIL_PRAXIS_TEMPLATE_CALLS_ENABLED=false", "-e", "ANVIL_REAL_EMAIL_ENABLED=false",
            "--entrypoint", "/app/services/backend/.venv/bin/python", image, "-I", "-B", "-c", code]
        created = subprocess.check_output(command, timeout=30).decode().strip()
        if not re.fullmatch(r"[a-f0-9]{64}", created):
            raise RuntimeError("Original capture verifier identity unavailable")
        exclusive(root / "receipt-verifier-intent.json", json.dumps({"id": created,
            "receipt_sha256": sha(planned), "attempts": 1}).encode())
        process = subprocess.Popen(["docker", "start", "--attach", created], stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout = stderr = b""
        info = None
        try:
            stdout, stderr = process.communicate(timeout=60)
            info = json.loads(subprocess.check_output(["docker", "inspect", created], timeout=15))[0]
            if (process.returncode or info["Id"] != created or info["State"]["Running"]
                    or info["State"]["Pid"] or info["State"]["ExitCode"]):
                raise RuntimeError("Capture verifier did not terminate successfully")
        except BaseException:
            failures = []
            try:
                subprocess.run(["docker", "stop", "--time", "1", created], capture_output=True, timeout=6, check=True)
            except BaseException as error:
                failures.append(type(error).__name__)
            try:
                stdout, stderr = process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                failures.append("cli_killed_after_owned_stop")
                try:
                    stdout, stderr = process.communicate(timeout=3)
                except BaseException as error:
                    failures.append(type(error).__name__)
            terminal = False
            try:
                after = json.loads(subprocess.check_output(["docker", "inspect", created], timeout=6))[0]
                terminal = after["Id"] == created and not after["State"]["Running"] and after["State"]["Pid"] == 0
            except BaseException as error:
                failures.append(type(error).__name__)
            exclusive(root / "receipt-verifier-unknown.json", json.dumps({"id": created,
                "terminal": terminal, "failures": failures, "qualification_published": False}).encode())
            raise RuntimeError("Capture verifier outcome unknown; no publication or replay") from None
        finally:
            exclusive(root / "receipt-verifier.private.stderr", stderr)
            exclusive(root / "receipt-verifier.stdout", stdout)
        exclusive(root / "receipt-verified.json", json.dumps({"receipt_sha256": sha(planned),
            "review_sha256": sha(raw_review), "manifest_sha256": sha(raw_manifest), "verifier_id": info["Id"]}).encode())
        print(json.dumps({"status": "verified_not_published", "receipt_sha256": sha(planned)}))
    else:
        verified = json.loads((root / "receipt-verified.json").read_bytes())
        if (verified["receipt_sha256"] != sha(planned) or verified["review_sha256"] != sha(raw_review)
                or verified["manifest_sha256"] != sha(raw_manifest) or (preview / "current.json").read_bytes() != planned):
            raise ValueError("Exact installed-image verification required before publication")
        destination.mkdir(mode=0o755, exist_ok=True)
        if (destination.resolve() != destination or destination.stat().st_uid != 0
                or destination.stat().st_mode & 0o022):
            raise ValueError("Fixed operator-controlled capture qualification destination required")
        destination.chmod(0o755)
        if destination.stat().st_mode & 0o777 != 0o755:
            raise ValueError("Readable root-owned qualification directory required")
        exclusive(root / "publication-intent.json", json.dumps(verified | {"attempts": 1}).encode())
        exclusive(destination / "current.json", planned, 0o644)
        descriptor = os.open(destination, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        print(json.dumps({"status": "capture_api_target_qualified_not_project_or_spending_authority",
                          "receipt_sha256": sha(planned), "expires_at": body["expires_at"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--review-sha256", required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--mode", choices=("verify", "publish"), required=True)
    main(parser.parse_args())
