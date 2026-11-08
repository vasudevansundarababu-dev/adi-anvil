"""Separate checkouts may change only the local port, never the local origin host."""

import os
import subprocess
import sys

import pytest


def configured(tmp_path, port=None, origin="http://127.0.0.1:3202"):
    env = {
        "PATH": os.defpath,
        "ANVIL_ROOT": str(tmp_path),
        "ANVIL_ENV": "local",
        "WEB_ORIGIN": origin,
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if port is not None:
        env["ANVIL_LOCAL_WEB_PORT"] = port
    return subprocess.run(
        [sys.executable, "-c", "from anvil.config import LOCAL_ORIGIN; print(LOCAL_ORIGIN)"],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )


def test_default_local_origin_remains_unchanged(tmp_path):
    result = configured(tmp_path)
    assert result.returncode == 0
    assert result.stdout.strip() == "http://127.0.0.1:3202"


@pytest.mark.parametrize("port", ["1024", "53202", "65535"])
def test_separate_loopback_port_is_supported(tmp_path, port):
    origin = "http://127.0.0.1:" + port
    result = configured(tmp_path, port, origin)
    assert result.returncode == 0
    assert result.stdout.strip() == origin


@pytest.mark.parametrize(
    "port",
    [
        "",
        "0",
        "1023",
        "65536",
        "-1",
        "3.2",
        " 3202",
        "3202 ",
        "３２０２",
        "3202/path",
        "localhost:3202",
    ],
)
def test_invalid_ports_fail_closed(tmp_path, port):
    result = configured(tmp_path, port)
    assert result.returncode != 0
    assert "Invalid local web port" in result.stderr


@pytest.mark.parametrize(
    "origin",
    [
        "http://127.0.0.1:3202",
        "http://localhost:53202",
        "http://0.0.0.0:53202",
        "https://127.0.0.1:53202",
        "http://example.test:53202",
        "http://127.0.0.1:53202/path",
        "http://127.0.0.1:53202/",
    ],
)
def test_port_override_cannot_authorize_another_origin(tmp_path, origin):
    result = configured(tmp_path, "53202", origin)
    assert result.returncode != 0
    assert "Unqualified web origin" in result.stderr
