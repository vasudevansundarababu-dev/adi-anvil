"""Installation generation credentials in a pre-provisioned GCP Secret Manager secret.

Local immutable indexes contain version locators only, never keys. VM workload identity
authenticates requests; no service-account file or SDK credential is accepted.
"""

import base64
import json
import os
import re
import stat
from pathlib import Path
from uuid import UUID, uuid4

import httpx

from anvil.config import private_file_owner


def resource():
    value = os.environ.get("ANVIL_GENERATION_SECRET_RESOURCE", "")
    if not re.fullmatch(r"projects/[0-9]+/secrets/anvil-import-generation", value):
        raise ValueError("Managed generation secret is not configured")
    return value


def request(method, path, body=None):
    with httpx.Client(trust_env=False, timeout=15, follow_redirects=False) as client:
        token = client.get(
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"},
        )
        token.raise_for_status()
        response = client.request(
            method,
            "https://secretmanager.googleapis.com/v1/" + path,
            headers={"Authorization": "Bearer " + token.json()["access_token"]},
            json=body,
        )
        response.raise_for_status()
        if len(response.content) > 65536:
            raise ValueError("Managed secret response exceeds bound")
        return response.json()


def index():
    path = Path(os.environ.get("ANVIL_CLOUD_SECRET_INDEX", "/app/.data/secret-index"))
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = os.fstat(fd)
    if not private_file_owner(info.st_uid) or info.st_mode & 0o077:
        os.close(fd)
        raise ValueError("Unsafe managed secret index")
    return fd


def save(value, binding):
    if binding.get("scope") != "installation_import_generation":
        raise ValueError("Cloud evaluation credential entry is disabled")
    identifier = str(uuid4())
    data = json.dumps({"id": identifier, "binding": binding, "secret": value}).encode()
    if len(data) > 32768:
        raise ValueError("Credential exceeds bound")
    fd = index()
    try:
        version = request(
            "POST",
            resource() + ":addVersion",
            {"payload": {"data": base64.b64encode(data).decode()}},
        )["name"]
        if not re.fullmatch(re.escape(resource()) + r"/versions/[0-9]+", version):
            raise ValueError("Unexpected managed secret version")
        out = os.open(
            identifier, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd
        )
        with os.fdopen(out, "w") as stream:
            json.dump({"version": version}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(fd)
    finally:
        os.close(fd)
    return identifier


def load(identifier, binding):
    if binding.get("scope") != "installation_import_generation":
        raise ValueError("Cloud evaluation credential entry is disabled")
    name = str(UUID(str(identifier)))
    fd = index()
    try:
        item = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        with os.fdopen(item) as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or not private_file_owner(info.st_uid)
                or info.st_mode & 0o077
                or info.st_size > 4096
            ):
                raise ValueError("Unsafe managed secret locator")
            version = json.load(stream)["version"]
    finally:
        os.close(fd)
    if not re.fullmatch(re.escape(resource()) + r"/versions/[0-9]+", version):
        raise ValueError("Unexpected managed secret locator")
    response = request("GET", version + ":access")
    if response.get("name") != version:
        raise ValueError("Managed secret version mismatch")
    value = json.loads(base64.b64decode(response["payload"]["data"], validate=True))
    if (
        value.get("id") != name
        or value.get("binding") != binding
        or not isinstance(value.get("secret"), str)
    ):
        raise ValueError("Managed credential binding mismatch")
    return value["secret"]
