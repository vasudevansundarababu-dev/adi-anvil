"""Synthetic kernel probe: fake socket only, no host mounts or inference."""

import json
import os
import pathlib
import subprocess
import sys
import tempfile

assert sys.platform == "linux" and os.uname().machine == "x86_64" and os.geteuid() == 0
assert "CapEff:\t0000000000000000" in pathlib.Path("/proc/self/status").read_text()

root = tempfile.mkdtemp(prefix="forge-fake-admin-")
stage2 = """import ctypes,json,os,socket,sys
listener=socket.socket(socket.AF_UNIX);listener.bind(sys.argv[1]+'/fake-admin.sock');listener.listen(1)
print(json.dumps({'pid':os.getpid(),'dumpable':ctypes.CDLL(None).prctl(3,0,0,0,0)}),flush=True)
listener.settimeout(5);connection,_=listener.accept();assert connection.recv(8)==b'control';connection.close();listener.close()
"""
stage1 = """import ctypes,os,sys
assert ctypes.CDLL(None).prctl(4,0,0,0,0)==0
os.execve(sys.executable,[sys.executable,'-I','-S','-c',sys.argv[1],sys.argv[2]],{'LANG':'C.UTF-8'})
"""
helper = subprocess.Popen(
    [sys.executable, "-I", "-S", "-c", stage1, stage2, root],
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
    text=True,
)
try:
    observation = json.loads(helper.stdout.readline())
    assert observation["pid"] == helper.pid
    actor = """import json,os,socket,sys
assert os.geteuid()==0
status=open('/proc/self/status').read();assert 'CapEff:\\t0000000000000000' in status
connection=socket.socket(socket.AF_UNIX);connection.settimeout(2)
connection.connect('/proc/'+sys.argv[1]+'/root'+sys.argv[2]+'/fake-admin.sock');connection.sendall(b'control');connection.close()
print(json.dumps({'same_uid_proc_root_fake_socket_connection':True,'capabilities':'zero'}))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-S", "-c", actor, str(helper.pid), root],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, "Synthetic proc-root connection failed; no bypass claimed"
    helper.wait(timeout=5)
    assert helper.returncode == 0
    print(
        json.dumps(
            {
                "scope": "synthetic_same_uid_exec_proc_boundary_only",
                "ordinary_exec_dumpable": observation["dumpable"],
                "actor_observation": json.loads(result.stdout),
                "host_mounts": 0,
                "model_calls": 0,
                "native_qualified": False,
                "security_result": "shared_uid_host_pid_recipe_requires_additional_isolation",
            }
        )
    )
finally:
    if helper.poll() is None:
        helper.kill()
    helper.wait(timeout=2)
