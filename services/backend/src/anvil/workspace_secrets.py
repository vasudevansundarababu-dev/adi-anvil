"""Local-only encrypted write-only credential storage; never an inference authority."""

import json
import os
import stat
from contextlib import contextmanager
from uuid import UUID, uuid4

from cryptography.fernet import Fernet

from anvil.config import CLOUD, ROOT


class StoreUnavailable(Exception):
    pass


def directory():
    if CLOUD:
        raise StoreUnavailable("Local credential storage is unavailable in cloud mode")
    parent = ROOT / ".local"
    target = parent / "workspace-secrets"
    if parent.is_symlink() or target.is_symlink():
        raise StoreUnavailable("Credential storage path is unsafe")
    return target


def read_private(path, directory_fd):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise StoreUnavailable("Credential storage permissions are unsafe")
        if info.st_size > 32768:
            raise StoreUnavailable("Credential ciphertext exceeds the storage bound")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            return stream.read(32768)
    finally:
        os.close(fd)


def write_private(path, data, directory_fd):
    if len(data) > 32768:
        raise StoreUnavailable("Credential ciphertext exceeds the storage bound")
    fd = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd
    )
    try:
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(directory_fd)


@contextmanager
def opened_store(create=False):
    directory()  # Enforce local-only operation before touching any directory.
    descriptors = []
    try:
        root = os.open(ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(root)
        root_info = os.fstat(root)
        if root_info.st_uid != os.getuid() or root_info.st_mode & 0o022:
            raise StoreUnavailable("Credential storage parent permissions are unsafe")
        if create:
            try:
                os.mkdir(".local", mode=0o700, dir_fd=root)
            except FileExistsError:
                pass
        parent = os.open(".local", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root)
        descriptors.append(parent)
        info = os.fstat(parent)
        if info.st_uid != os.getuid() or info.st_mode & 0o022:
            raise StoreUnavailable("Credential storage parent permissions are unsafe")
        if create:
            try:
                os.mkdir("workspace-secrets", mode=0o700, dir_fd=parent)
                os.fsync(parent)
            except FileExistsError:
                pass
        target = os.open(
            "workspace-secrets", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
        )
        descriptors.append(target)
        info = os.fstat(target)
        if info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise StoreUnavailable("Credential storage permissions are unsafe")
        yield target
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def wrapping_cipher(directory_fd, create=False):
    key = "wrapping-key.v1"
    entries = os.listdir(directory_fd)
    if create and key not in entries:
        if entries:
            raise StoreUnavailable("Existing credentials require wrapping-key recovery")
        try:
            write_private(key, Fernet.generate_key(), directory_fd)
        except FileExistsError:
            pass
    return Fernet(read_private(key, directory_fd))


def save(value, binding):
    """Append a ciphertext blob. An uncommitted database write may leave an inert orphan."""
    try:
        if CLOUD:
            from anvil import cloud_secrets

            return cloud_secrets.save(value, binding)
        with opened_store(create=True) as fd:
            cipher = wrapping_cipher(fd, create=True)
            identifier = str(uuid4())
            payload = json.dumps({"binding": binding, "secret": value}, sort_keys=True).encode(
                "utf-8"
            )
            write_private(identifier, cipher.encrypt(payload), fd)
            return identifier
    except Exception:
        raise StoreUnavailable(
            "Local credential store unavailable; no credential was activated"
        ) from None


def load(identifier, binding):
    try:
        if CLOUD:
            from anvil import cloud_secrets

            return cloud_secrets.load(identifier, binding)
        name = str(UUID(str(identifier)))
        with opened_store() as fd:
            value = json.loads(wrapping_cipher(fd).decrypt(read_private(name, fd)))
        if value.get("binding") != binding or not isinstance(value.get("secret"), str):
            raise StoreUnavailable("Credential binding mismatch")
        return value["secret"]
    except Exception:
        raise StoreUnavailable("Local credential version unavailable") from None
