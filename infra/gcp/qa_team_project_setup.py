"""Bootstrap one isolated, labelled QA acceptance project for existing QA identities."""

import json
import os
import socket
import subprocess
from pathlib import Path
from uuid import uuid4


def main():
    assert socket.gethostname() == "anvil-overnight-qa-20261110" and os.getuid() == 0
    root = Path("/var/lib/anvil-overnight-qa")
    receipt = root / "qa-team-project-public.json"
    if receipt.exists():
        print(receipt.read_text())
        return
    value = {"project_id": str(uuid4()), "name": "QA acceptance: isolated imports and labelled software controls",
             "admin_id": "113c5a26-1060-442b-be9e-955de21c391c",
             "engineer_id": "47e92d1c-2125-4897-bf4f-cc22af0cfc55",
             "origin": "owner_authorized_synthetic_qa_acceptance_project",
             "provider_credentials_in_project": False, "human_source_approvals": False}
    program = '''import json,os,sys,psycopg
from anvil.db import audit
d=json.load(sys.stdin)
with psycopg.connect(os.environ['MIGRATION_DATABASE_URL']) as c:
 org=c.execute("SELECT org_id FROM anvil.users WHERE id=%s",(d['admin_id'],)).fetchone()[0]
 c.execute("INSERT INTO anvil.projects(id,org_id,name) VALUES(%s,%s,%s)",(d['project_id'],org,d['name']))
 for user,role in ((d['admin_id'],'admin'),(d['engineer_id'],'rl-engineer')):
  assert c.execute("SELECT org_id FROM anvil.users WHERE id=%s",(user,)).fetchone()[0]==org
  c.execute("INSERT INTO anvil.memberships(project_id,user_id,role) VALUES(%s,%s,%s)",(d['project_id'],user,role))
 audit(c,d['project_id'],None,'qa_acceptance_project_bootstrap',metadata={'origin':d['origin'],'human_approval':False,'paid_enabled':False})
 assert c.execute("SELECT count(*) FROM anvil.memberships WHERE project_id=%s AND active",(d['project_id'],)).fetchone()[0]==2
print('Isolated QA project and two scoped memberships verified')
'''
    command = ["docker", "compose", "-f", str(root / "config/compose.json"), "run", "--rm", "-T", "migrate", "python", "-c", program]
    subprocess.run(command, input=json.dumps(value).encode(), check=True)
    receipt.write_text(json.dumps(value))
    print(json.dumps(value))


if __name__ == "__main__":
    main()
