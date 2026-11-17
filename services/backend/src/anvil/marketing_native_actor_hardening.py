"""Fixed Linux amd64 child privilege reductions; not runtime qualification.

Only called in gated operation children. Never modifies the control parent's
mount namespace/capabilities. Actual kernel/library/isolation tests are required.
"""

import ctypes
import errno
import os
import sys

ARCH = 0xC000003E  # AUDIT_ARCH_X86_64
ALLOW = 0x7FFF0000
KILL = 0x80000000
DENY = 0x00050000 | errno.EPERM
NO_SYSCALL = 0x00050000 | errno.ENOSYS
NAMESPACE_FLAGS = 0x7E020080
# Linux x86 syscall_64.tbl. Deny file-handle/process descriptor escape paths,
# and io_uring's separate operation submission path as well as mount syscalls.
# https://github.com/torvalds/linux/blob/master/arch/x86/entry/syscalls/syscall_64.tbl
DENIED_SYSCALLS = (101, 165, 166, 272, 298, 303, 304, 308, 310, 311, 312, 321,
                   425, 426, 427, 428, 429, 430, 431, 432, 433, 438, 442, 467)


def filter_program():
    # Classic BPF over seccomp_data: arch@4, nr@0, clone arg0 low word@16.
    code = [(0x20, 0, 0, 4), (0x15, 1, 0, ARCH), (0x06, 0, 0, KILL),
            (0x20, 0, 0, 0), (0x45, 0, 1, 0x40000000), (0x06, 0, 0, NO_SYSCALL)]
    for number in DENIED_SYSCALLS:
        code += [(0x15, 0, 1, number), (0x06, 0, 0, DENY)]
    # clone3's pointed-to flags cannot be safely inspected by classic BPF.
    # ENOSYS permits normal libc fallback to the inspected legacy clone path.
    code += [(0x15, 0, 1, 435), (0x06, 0, 0, NO_SYSCALL),
             (0x15, 0, 3, 56), (0x20, 0, 0, 16), (0x45, 0, 1, NAMESPACE_FLAGS),
             (0x06, 0, 0, DENY), (0x06, 0, 0, ALLOW)]
    return code


def _platform():
    if sys.platform != 'linux' or os.uname().machine != 'x86_64' or os.geteuid() != 0:
        raise ValueError('marketing_fixed_root_linux_amd64_child_required')


def _libc():
    libc = ctypes.CDLL(None, use_errno=True)
    # prctl is variadic in libc, but these fixed five ABI words must retain a
    # full-width pointer for sock_fprog on amd64 (never a default C int).
    libc.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    libc.prctl.restype = ctypes.c_int
    return libc


def _capabilities(libc):
    class Header(ctypes.Structure):
        _fields_ = [('version', ctypes.c_uint32), ('pid', ctypes.c_int)]

    class Data(ctypes.Structure):
        _fields_ = [('effective', ctypes.c_uint32), ('permitted', ctypes.c_uint32), ('inheritable', ctypes.c_uint32)]

    descriptor = os.open('/proc/sys/kernel/cap_last_cap', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        raw = os.read(descriptor, 17)
    finally:
        os.close(descriptor)
    if len(raw) > 16 or not raw.strip().isdigit() or not 0 <= int(raw) <= 63:
        raise ValueError('marketing_qualified_kernel_capability_range_required')
    for capability in range(int(raw) + 1):
        if libc.prctl(24, capability, 0, 0, 0) != 0:  # PR_CAPBSET_DROP
            raise OSError(ctypes.get_errno(), 'child capability bounding drop failed')
    header, data = Header(0x20080522, 0), (Data * 2)()
    if libc.capset(ctypes.byref(header), ctypes.byref(data)) != 0:
        raise OSError(ctypes.get_errno(), 'child effective/permitted/inheritable capability drop failed')


def _filter(libc):
    class Instruction(ctypes.Structure):
        _fields_ = [('code', ctypes.c_ushort), ('jt', ctypes.c_ubyte), ('jf', ctypes.c_ubyte), ('k', ctypes.c_uint32)]

    class Program(ctypes.Structure):
        _fields_ = [('len', ctypes.c_ushort), ('filter', ctypes.POINTER(Instruction))]

    values = filter_program()
    instructions = (Instruction * len(values))(*(Instruction(*value) for value in values))
    program = Program(len(values), instructions)
    address = ctypes.cast(ctypes.pointer(program), ctypes.c_void_p).value
    if libc.prctl(22, 2, address, 0, 0) != 0:  # PR_SET_SECCOMP/FILTER
        raise OSError(ctypes.get_errno(), 'fixed child seccomp installation failed')


def harden_graph():
    _platform()
    libc = _libc()
    libc.mount.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_ulong, ctypes.c_void_p]
    libc.unshare.argtypes = [ctypes.c_int]
    if libc.unshare(0x00020000) != 0:  # CLONE_NEWNS
        raise OSError(ctypes.get_errno(), 'private child mount namespace unavailable')
    # Make all propagation private before installing a readonly cgroup view.
    if libc.mount(None, b'/', None, (1 << 18) | 16384, None) != 0:  # MS_PRIVATE|MS_REC
        raise OSError(ctypes.get_errno(), 'private child mount propagation failed')
    target = b'/sys/fs/cgroup'
    if libc.mount(target, target, None, 4096 | 16384, None) != 0:  # MS_BIND|MS_REC
        raise OSError(ctypes.get_errno(), 'child cgroup bind failed')
    if libc.mount(None, target, None, 4096 | 32 | 1 | 2 | 4 | 8, None) != 0:
        raise OSError(ctypes.get_errno(), 'readonly child cgroup remount failed')
    if libc.prctl(38, 1, 0, 0, 0) != 0 or libc.prctl(4, 0, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'child no-new-privileges/undumpable policy failed')
    _capabilities(libc)
    _filter(libc)


def harden_watchdog():
    _platform()
    libc = _libc()
    # This child needs its existing delegated cgroup writes. It does not get the
    # actor's readonly mount view, and no signer/key exists in its parent image.
    if libc.prctl(38, 1, 0, 0, 0) != 0 or libc.prctl(4, 0, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'outside watchdog privacy policy failed')
    _capabilities(libc)
    _filter(libc)


def harden_private_control():
    """Dedicated control ONLY, after all local SDK/graph/watchdog spawning.

    Future helper launches belong to the independent receiver. Drop root's
    ability to inspect the attester or regain capabilities across exec, and
    prevent actor proc/root traversal through a dumpable control parent.
    Actual kernel enforcement remains a required independent qualification.
    """
    _platform()
    libc = _libc()
    # NOROOT/NO_SETUID_FIXUP/NO_CAP_AMBIENT_RAISE, each locked.
    if libc.prctl(28, 1 | 2 | 4 | 8 | 64 | 128, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'dedicated control securebits unavailable')
    if libc.prctl(38, 1, 0, 0, 0) != 0 or libc.prctl(4, 0, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'dedicated control privacy policy failed')
    _capabilities(libc)
    _filter(libc)


def protect_independent_receiver():
    """Privileged fixed receiver only; its heap/environment are not actor data.

    Retain only the independently qualified operator's existing capabilities
    needed for actual handle verification and fixed helper child isolation.
    Those capabilities are never transferred to SDK/graph/helper/key children
    after their startup hardening. This does not mint that qualification.
    """
    _platform()
    libc = _libc()
    if libc.prctl(38, 1, 0, 0, 0) != 0 or libc.prctl(4, 0, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'independent receiver privacy policy failed')
