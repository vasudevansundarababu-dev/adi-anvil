# Shares the authenticated test-client fixture with every integration module.
import pytest
from test_api_security import client_factory  # noqa: F401

from anvil.config import ROOT

STUB_REGISTRY = "http://127.0.0.1:8211"


def _followed_registry():
    """The registry the running stack follows, as `pnpm dev` reads it from the worktree's .env."""
    path = ROOT / ".env"
    if not path.exists():
        return None
    for line in path.read_text().splitlines():
        if line.startswith("RLGYM_STUDIO_URL="):
            return line.split("=", 1)[1].strip().strip('"')
    return None


def pytest_sessionstart(session):
    # The running API dispatches the same outbox as the tests. While it follows another registry it would deliver the
    # tests' inbox items and evaluator events there (22 Nov 2026: test items reached the local Studio as inb-0004..6).
    followed = _followed_registry()
    if followed and followed.rstrip("/") != STUB_REGISTRY:
        pytest.exit(
            f"The running stack follows {followed}; integration tests would send test traffic there. Switch to the "
            "stub first: python3 scripts/local.py rlgym-registry stub (then restart pnpm dev).",
            returncode=3,
        )
