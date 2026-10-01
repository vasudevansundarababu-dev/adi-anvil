import os
import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    "overrides",
    [
        {"ANVIL_ENV": "production"},
        {"ANVIL_ENV": "staging"},
        {"WEB_ORIGIN": "https://example.invalid"},
    ],
)
def test_development_bootstrap_refuses_nonlocal_configuration(overrides):
    result = subprocess.run(
        [sys.executable, "-c", "import anvil.config"],
        env={**os.environ, **overrides},
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "local-only" in result.stderr or "Unqualified web origin" in result.stderr


CLOUD = {
    "ANVIL_ENV": "cloud",
    "WEB_ORIGIN": "https://anvil.example.test",
    "OIDC_ISSUER": "https://auth.example.test/realms/anvil",
    "ANVIL_LIVE_PROVIDERS_ENABLED": "false",
    "ANVIL_REAL_EMAIL_ENABLED": "false",
    "ANVIL_SESSION_KEY": "x" * 43,
}


def run_config(overrides, code="import anvil.config"):
    return subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, **overrides},
        capture_output=True,
        text=True,
    )


def test_cloud_mode_accepts_explicit_https_configuration():
    result = run_config(CLOUD, "import anvil.config as c; print(c.CLOUD)")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"


@pytest.mark.parametrize(
    "overrides",
    [
        {"WEB_ORIGIN": "http://anvil.example.test"},
        {"WEB_ORIGIN": "https://127.0.0.1:3202"},
        {"WEB_ORIGIN": "https://anvil.example.test/"},
        {"WEB_ORIGIN": "https://anvil.example.test/app"},
        {"OIDC_ISSUER": "http://auth.example.test/realms/anvil"},
        {"OIDC_ISSUER": "https://auth.example.test/anvil"},
        {"OIDC_ISSUER": "https://auth.example.test/realms/"},
        {"ANVIL_LIVE_PROVIDERS_ENABLED": "true"},
        {"ANVIL_REAL_EMAIL_ENABLED": "true"},
        {"ANVIL_SESSION_KEY": "short"},
    ],
)
def test_cloud_mode_refuses_unqualified_settings(overrides):
    result = run_config({**CLOUD, **overrides})
    assert result.returncode != 0
    assert "cloud" in result.stderr or "Unqualified" in result.stderr


@pytest.mark.parametrize(
    "code",
    [
        "from anvil.cli import seed; seed()",
        "from anvil.operations import new_demo; new_demo('cloud demo')",
        "from anvil.operations import backup; backup()",
    ],
)
def test_synthetic_identities_and_local_operations_refuse_cloud(code):
    result = run_config(CLOUD, code)
    assert result.returncode != 0
    assert "local-only" in result.stderr


def test_invitation_validation_rejects_unknown_roles_and_bad_usernames():
    result = run_config(
        CLOUD,
        "from anvil.invitations import validate\n"
        "for args in [('Bad User','a@b.co',['admin'],[]),('good','nope',['admin'],[]),"
        "('good','a@b.co',['owner'],[]),('good','a@b.co',[],[]),('good','a@b.co',['admin'],['root'])]:\n"
        "    try:\n        validate(*args)\n    except ValueError:\n        continue\n"
        "    raise SystemExit('accepted ' + repr(args))\n"
        "validate('vasu.admin','a@b.co',['admin','researcher'],['release_owner'])\n",
    )
    assert result.returncode == 0, result.stderr


def test_local_mode_refuses_invitations():
    result = run_config(
        {},
        "from anvil.invitations import invite\n"
        "invite('someone','a@b.co','Someone','P',['researcher'])",
    )
    assert result.returncode != 0
    assert "cloud-only" in result.stderr
