"""Create separate labelled QA-team OIDC users scoped only to the acceptance project."""

import json
import os
import secrets
import socket
import subprocess
from pathlib import Path
from uuid import uuid4


def main():
    assert socket.gethostname() == "anvil-overnight-qa-20261110" and os.getuid() == 0
    root = Path("/var/lib/anvil-overnight-qa")
    private = root / "qa-team-oidc-fixture.json"
    assert not private.exists(), "Existing QA team identities require reconciliation"
    project = json.loads((root / "qa-team-project-public.json").read_text())["project_id"]
    compose = ["docker", "compose", "-f", str(root / "config/compose.json")]
    subprocess.run([*compose, "exec", "-T", "keycloak", "sh", "-c", 'exec /opt/keycloak/bin/kcadm.sh config credentials --config /tmp/anvil-qa-team-kcadm.json --server http://127.0.0.1:8080 --realm master --user "$KC_BOOTSTRAP_ADMIN_USERNAME" --password "$KC_BOOTSTRAP_ADMIN_PASSWORD"'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    value = {"origin": "qa_team_acceptance_only", "project": project, "users": {}}
    for role in ("admin", "rl-engineer"):
        user = {"id": str(uuid4()), "username": "qa-team-" + role, "password": secrets.token_urlsafe(32), "role": role}
        body = {"id": user["id"], "username": user["username"], "enabled": True, "firstName": "QA Test", "lastName": role, "email": user["username"] + "@example.invalid", "emailVerified": False, "attributes": {"origin": [value["origin"]]}, "credentials": [{"type": "password", "value": user["password"], "temporary": False}]}
        subprocess.run([*compose, "exec", "-T", "keycloak", "/opt/keycloak/bin/kcadm.sh", "create", "users", "-r", "anvil-overnight-qa", "--config", "/tmp/anvil-qa-team-kcadm.json", "-f", "-"], input=json.dumps(body).encode(), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        observed = json.loads(subprocess.check_output([*compose, "exec", "-T", "keycloak", "/opt/keycloak/bin/kcadm.sh", "get", "users", "-r", "anvil-overnight-qa", "--config", "/tmp/anvil-qa-team-kcadm.json", "-q", "username=" + user["username"], "-q", "exact=true"]))
        assert len(observed) == 1 and observed[0]["username"] == user["username"]
        user["id"] = observed[0]["id"]
        value["users"][role] = user
    program = '''import json,os,sys,psycopg
from anvil.db import audit
d=json.load(sys.stdin)
with psycopg.connect(os.environ['MIGRATION_DATABASE_URL']) as c:
 org=c.execute("SELECT org_id FROM anvil.projects WHERE id=%s",(d['project'],)).fetchone()[0]
 for role,u in d['users'].items():
  c.execute("INSERT INTO anvil.users(id,org_id,issuer,subject,name,is_synthetic) VALUES(%s,%s,%s,%s,%s,true)",(u['id'],org,os.environ['OIDC_ISSUER'],u['id'],'QA Test '+role))
  c.execute("INSERT INTO anvil.memberships(project_id,user_id,role) VALUES(%s,%s,%s)",(d['project'],u['id'],role))
  assert c.execute("SELECT count(*) FROM anvil.memberships WHERE user_id=%s AND active",(u['id'],)).fetchone()[0]==1
 audit(c,d['project'],None,'qa_team_test_accounts_created',metadata={'origin':d['origin'],'human_approval':False,'other_project_access':False})
print('Two QA-team accounts scoped only to acceptance project')
'''
    subprocess.run([*compose, "run", "--rm", "-T", "migrate", "python", "-c", program], input=json.dumps(value).encode(), check=True)
    fd = os.open(private, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as out:
        json.dump(value, out)
    subprocess.run(["install", "-m", "0600", "-o", "vasudevan_sundarababu_adi_labs_a", "-g", "vasudevan_sundarababu_adi_labs_a", str(private), "/home/vasudevan_sundarababu_adi_labs_a/qa-team-access-fixture.json"], check=True)
    public = {"project": project, "origin": value["origin"], "users": {role: {"id": user["id"], "username": user["username"]} for role, user in value["users"].items()}, "other_project_access": False, "provider_keys_in_project": False}
    (root / "qa-team-accounts-public.json").write_text(json.dumps(public))
    print(json.dumps(public))


if __name__ == "__main__":
    main()
