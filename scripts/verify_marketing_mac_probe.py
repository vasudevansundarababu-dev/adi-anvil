"""Fake resources only; require enforced profile stack, NNP and zero caps."""

import json
import pathlib
import select
import socket
import subprocess
import sys
import tempfile

operator = "forge-mkt-proc-probe-20261117-v3-operator"
actor = "forge-mkt-proc-probe-20261117-v3-actor"
attr = "/proc/thread-self/attr/apparmor/current"
assert pathlib.Path(attr).read_text().strip() == operator + " (enforce)"
status = pathlib.Path("/proc/self/status").read_text()
assert "NoNewPrivs:\t1" in status
root = tempfile.mkdtemp(prefix="forge-fake-admin-")
controlroot = tempfile.mkdtemp(prefix="forge-fake-control-")
listener = socket.socket(socket.AF_UNIX)
listener.bind(controlroot + "/control.sock")
listener.listen(1)
listener.settimeout(5)
helper_code = """import ctypes,json,os,socket,sys,time
listener=socket.socket(socket.AF_UNIX);listener.bind(sys.argv[1]+'/fake-admin.sock');listener.listen(1)
print(json.dumps({'pid':os.getpid(),'dumpable':ctypes.CDLL(None).prctl(3,0,0,0,0)}),flush=True)
time.sleep(15)
"""
preexec = """import ctypes,os,sys
assert ctypes.CDLL(None).prctl(4,0,0,0,0)==0
os.execve(sys.executable,[sys.executable,'-I','-S','-c',sys.argv[1],sys.argv[2]],{'LANG':'C.UTF-8'})
"""
helper = subprocess.Popen(
    [sys.executable, "-I", "-S", "-c", preexec, helper_code, root],
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
    text=True,
)
child = None
try:
    assert select.select([helper.stdout], [], [], 5)[0]
    observed = json.loads(helper.stdout.readline())
    assert observed == {"pid": helper.pid, "dumpable": 1}
    actor_code = """import errno,json,os,pathlib,socket,sys
attr='/proc/thread-self/attr/apparmor/current';operator=sys.argv[1];actor=sys.argv[2];pid=int(sys.argv[3]);root=sys.argv[4];control=sys.argv[5]
label=pathlib.Path(attr).read_text().strip();assert label.endswith(' (enforce)') and set(label.removesuffix(' (enforce)').split('//&'))=={operator,actor}
status=pathlib.Path('/proc/self/status').read_text();assert 'CapEff:\\t0000000000000000' in status and 'NoNewPrivs:\\t1' in status
stat=pathlib.Path('/proc/'+str(pid)+'/stat').read_text();tail=stat[stat.rfind(')')+2:].split();assert int(tail[19])>0
denials={}
for name,path in [('proc_root','/proc/'+str(pid)+'/root'+root+'/fake-admin.sock'),('direct_admin',root+'/fake-admin.sock')]:
 connection=socket.socket(socket.AF_UNIX);connection.settimeout(1)
 try:connection.connect(path)
 except OSError as e:assert e.errno in ((errno.EACCES,errno.EPERM,errno.ECONNREFUSED,errno.ENOTSOCK) if name=='direct_admin' else (errno.EACCES,errno.EPERM));denials[name]=True
 else:raise AssertionError(name+' forbidden fake admin path accessible')
 finally:connection.close()
try:fd=os.open('/proc/'+str(pid)+'/fd/1',os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC)
except OSError as e:assert e.errno in (errno.EACCES,errno.EPERM);denials['foreign_fd']=True
else:os.close(fd);raise AssertionError('Foreign helper fd accessible')
try:os.kill(pid,0)
except OSError as e:assert e.errno in (errno.EACCES,errno.EPERM);denials['foreign_signal']=True
else:raise AssertionError('Foreign helper signal permitted')
try:
 with open(attr,'w') as f:f.write('changeprofile '+operator)
except OSError as e:assert e.errno in (errno.EACCES,errno.EPERM);denials['reverse_transition']=True
else:raise AssertionError('Actor profile could be removed')
assert os.readlink('/proc/self/fd/0')
connection=socket.socket(socket.AF_UNIX);connection.settimeout(2);connection.connect(control+'/control.sock');connection.sendall(b'control');connection.close()
print(json.dumps({'denials':denials,'operator_start_ticks_read':True,'own_fd_read':True,'intended_control_connection':True,'profile_persisted_after_exec':True,'native_qualified':False}),flush=True)
"""
    stack = """import ctypes,os,sys
libc=ctypes.CDLL(None,use_errno=True);libc.mount.argtypes=[ctypes.c_char_p,ctypes.c_char_p,ctypes.c_char_p,ctypes.c_ulong,ctypes.c_void_p]
assert libc.unshare(0x00020000)==0
assert libc.mount(None,b'/',None,(1<<18)|16384,None)==0
mask=(sys.argv[4]+'/fake-admin.sock').encode()
assert libc.mount(b'/dev/null',mask,None,4096,None)==0
assert libc.mount(None,mask,None,4096|32|1|2|4|8,None)==0
last=int(open('/proc/sys/kernel/cap_last_cap').read());assert 0<=last<=63
for capability in range(last+1):assert libc.prctl(24,capability,0,0,0)==0
class Header(ctypes.Structure):_fields_=[('version',ctypes.c_uint32),('pid',ctypes.c_int)]
class Data(ctypes.Structure):_fields_=[('effective',ctypes.c_uint32),('permitted',ctypes.c_uint32),('inheritable',ctypes.c_uint32)]
header=Header(0x20080522,0);data=(Data*2)();assert libc.capset(ctypes.byref(header),ctypes.byref(data))==0
with open('/proc/thread-self/attr/apparmor/current','w') as f:f.write('stack '+sys.argv[2])
os.execve(sys.executable,[sys.executable,'-I','-S','-c',sys.argv[6],*sys.argv[1:6]],{'LANG':'C.UTF-8'})
"""
    child = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-S",
            "-c",
            stack,
            operator,
            actor,
            str(helper.pid),
            root,
            controlroot,
            actor_code,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        close_fds=True,
    )
    assert select.select([child.stdout, child.stderr, listener], [], [], 8)[0]
    if not select.select([listener], [], [], 5)[0]:
        if child.poll() is None:
            child.kill()
        out, err = child.communicate(timeout=2)
        raise RuntimeError("Synthetic actor probe refused before control: " + err[-1500:])
    connection, _ = listener.accept()
    assert connection.recv(8) == b"control"
    connection.close()
    out, err = child.communicate(timeout=5)
    assert child.returncode == 0, "Confinement probe failed: " + err[-1000:]
    check = socket.socket(socket.AF_UNIX)
    check.settimeout(1)
    check.connect(root + "/fake-admin.sock")
    check.close()
    print(
        json.dumps(
            {
                "parent_socket_namespace_unchanged": True,
                "scope": "fake_socket_private_mount_and_MAC_predicate_only",
                "result": json.loads(out),
                "model_calls": 0,
                "native_qualified": False,
            }
        )
    )
finally:
    for process in (child, helper):
        if process is not None:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=2)
    listener.close()
