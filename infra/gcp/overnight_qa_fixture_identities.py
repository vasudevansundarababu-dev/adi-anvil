"""Create labelled QA-only OIDC fixtures, never real-user or source approvals."""

import json
import os
import secrets
import socket
import subprocess
from pathlib import Path
from uuid import uuid4


def main():
    if socket.gethostname() != "anvil-overnight-qa-20261110" or os.getuid() != 0:
        raise ValueError("Owned QA operator required")
    root = Path("/var/lib/anvil-overnight-qa")
    fixture = root / "synthetic-oidc-test-fixture.json"
    if fixture.exists():
        raise ValueError("Existing QA fixture identities must not be overwritten")
    compose = ["docker", "compose", "-f", str(root / "config/compose.json")]
    command = 'exec /opt/keycloak/bin/kcadm.sh config credentials --config /tmp/anvil-qa-fixture-kcadm.json --server http://127.0.0.1:8080 --realm master --user "$KC_BOOTSTRAP_ADMIN_USERNAME" --password "$KC_BOOTSTRAP_ADMIN_PASSWORD"'
    subprocess.run(
        compose + ["exec", "-T", "keycloak", "sh", "-c", command],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    data = {
        "origin": "synthetic_oidc_protocol_qa_only",
        "org": str(uuid4()),
        "project": str(uuid4()),
        "users": {},
    }
    for role in ("admin", "rl-engineer"):
        identity = {
            "id": str(uuid4()),
            "username": "synthetic-qa-" + role,
            "password": secrets.token_urlsafe(32),
            "role": role,
        }
        # Separate actual Keycloak subjects, visibly synthetic; no human impersonation.
        body = {
            "id": identity["id"],
            "username": identity["username"],
            "enabled": True,
            "firstName": "Synthetic QA",
            "lastName": role,
            "email": identity["username"] + "@example.invalid",
            "emailVerified": False,
            "attributes": {"origin": [data["origin"]]},
            "credentials": [
                {"type": "password", "value": identity["password"], "temporary": False}
            ],
        }
        subprocess.run(
            compose
            + [
                "exec",
                "-T",
                "keycloak",
                "/opt/keycloak/bin/kcadm.sh",
                "create",
                "users",
                "-r",
                "anvil-overnight-qa",
                "--config",
                "/tmp/anvil-qa-fixture-kcadm.json",
                "-f",
                "-",
            ],
            input=json.dumps(body).encode(),
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        observed = json.loads(
            subprocess.check_output(
                compose
                + [
                    "exec",
                    "-T",
                    "keycloak",
                    "/opt/keycloak/bin/kcadm.sh",
                    "get",
                    "users",
                    "-r",
                    "anvil-overnight-qa",
                    "--config",
                    "/tmp/anvil-qa-fixture-kcadm.json",
                    "-q",
                    "username=" + identity["username"],
                    "-q",
                    "exact=true",
                ]
            )
        )
        if len(observed) != 1 or observed[0]["username"] != identity["username"]:
            raise ValueError("Actual QA OIDC subject readback required")
        identity["id"] = observed[0]["id"]
        data["users"][role] = identity
    fd = os.open(fixture, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(data, stream)
    # Bind only labelled test identities in a fresh test Project. No assignments,
    # reviews, rights clearances, model activation or real-account grants.
    sql_script = """import json,os,sys,psycopg
from anvil.db import audit
d=json.load(sys.stdin)
with psycopg.connect(os.environ['MIGRATION_DATABASE_URL']) as c:
 c.execute("INSERT INTO anvil.organizations(id,name) VALUES(%s,'Synthetic overnight protocol QA')",(d['org'],))
 c.execute("INSERT INTO anvil.projects(id,org_id,name) VALUES(%s,%s,'Synthetic QA only: no source approvals')",(d['project'],d['org']))
 for role,u in d['users'].items():
  c.execute("INSERT INTO anvil.users(id,org_id,issuer,subject,name) VALUES(%s,%s,%s,%s,%s)",(u['id'],d['org'],os.environ['OIDC_ISSUER'],u['id'],'Synthetic QA '+role))
  c.execute("INSERT INTO anvil.memberships(project_id,user_id,role) VALUES(%s,%s,%s)",(d['project'],u['id'],role))
 audit(c,d['project'],None,'synthetic_qa_oidc_identity_bootstrap',metadata={'origin':d['origin'],'human_approval':False})
print('Synthetic SQL fixture identities bound; zero approvals created')
"""
    subprocess.run(
        compose + ["run", "--rm", "-T", "migrate", "python", "-c", sql_script],
        input=json.dumps(data).encode(),
        check=True,
    )
    (root / "identity-public.json").write_text(
        json.dumps(
            {
                "origin": data["origin"],
                "project": data["project"],
                "users": {
                    role: {"id": u["id"], "username": u["username"]}
                    for role, u in data["users"].items()
                },
                "human_approvals_created": 0,
                "real_owner_onboarded": False,
            }
        )
    )
    print("Two synthetic QA identities created; real owner identity and live activation untouched")


if __name__ == "__main__":
    main()
